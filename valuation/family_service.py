"""Loopback family service behind Cloudflare Access; no steward routes."""
from contextlib import closing
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import ssl
import requests
import secrets
import re
import time
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import jwt
from valuation import family_requests as store
from valuation.family_catalog import render

def owner_badge(email):
    import html
    return '<span style="font-size:.9rem">Signed in as '+html.escape(email,quote=True)+' · Owner</span>'

class Identity:
    def __init__(self,config):
        self.config=config
        self.keys=jwt.PyJWKClient(config['issuer']+'/cdn-cgi/access/certs',timeout=5,lifespan=300,
            ssl_context=ssl.create_default_context(cafile=requests.certs.where()))
    def __call__(self,token):
        key=self.keys.get_signing_key_from_jwt(token)
        c=jwt.decode(token,key.key,algorithms=['RS256'],audience=self.config['audience'],issuer=self.config['issuer'],options={'require':['exp','iat','sub','email','aud','iss']})
        email=c['email'].lower()
        if email not in self.config['allowed_emails']:raise ValueError('Not authorized')
        return email

class App:
    def __init__(self,config,identity=None):
        self.config=config;self.identity=identity or Identity(config)
        self.search_lock=threading.Lock();self.search_index=None;self.search_fingerprint=None
        self.db=Path(config['database']);self.db.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        store.connect(self.db).close();os.chmod(self.db,0o600)
    def raw_catalog(self):
        raw=Path(self.config['snapshot']).read_bytes();records=json.loads(raw)
        from valuation.family_catalog import FIELDS
        if not isinstance(records,list) or any(set(r) not in (set(FIELDS),set(FIELDS)-{'description'}) for r in records):raise ValueError('Invalid catalog snapshot')
        return {r['reference']:dict(r,description=r.get('description','')) for r in records},hashlib.sha256(raw).hexdigest()
    def catalog(self):
        records,snapshot=self.raw_catalog()
        if self.config.get('owner_data_dir'):
            from valuation import family_owner as owner
            from valuation.workspace_service import load_model
            facts=owner.live_facts(load_model(self.config['owner_data_dir'],self.config['owner_output_dir'],family_overlay=False),self.config['owner_data_dir'])
            with closing(store.connect(self.db)) as db:records=owner.available(db,records,facts)
        return records,snapshot
    def search_preview(self,query,owner_scope=False,catalog_ids=None):
        from valuation.family_search import Search,fingerprint
        records,snapshot=self.raw_catalog();mapping={}
        if owner_scope:
            from valuation.workspace_service import load_model
            model=load_model(self.config['owner_data_dir'],self.config['owner_output_dir'])
            active=set(model.completed_inventory.catalog_item_ids)
            if catalog_ids is not None:
                if not isinstance(catalog_ids,list) or any(not isinstance(x,str) for x in catalog_ids) or len(catalog_ids)>10000:raise ValueError('Invalid catalog filters')
                active&=set(catalog_ids)
            mapping={hashlib.sha256(('family-v1:'+cid).encode()).hexdigest()[:20]:cid for cid in active}
            available={ref:r for ref,r in records.items() if ref in mapping}
        else:available,_=self.catalog()
        with self.search_lock:
            if self.search_fingerprint!=snapshot:
                self.search_index=Search(list(records.values()));self.search_fingerprint=snapshot
            index=self.search_index
        start=time.monotonic();keyword=index.search(query,allowed=available,mode='keyword');keyword['elapsed_ms']=round((time.monotonic()-start)*1000,1)
        start=time.monotonic()
        try:
            root=Path(self.config['search_pilot_dir'])
            token=(root/'worker-token').read_text().strip()
            req=Request('http://127.0.0.1:8878/search',data=json.dumps(dict(query=query,allowed=list(available),fingerprint=fingerprint(list(records.values())))).encode(),headers={'Content-Type':'application/json','X-Search-Token':token})
            with urlopen(req,timeout=8) as response:hybrid=json.loads(response.read())
            # Never trust a stale worker to grant availability or inject unknown records.
            hybrid['results']=[r for r in hybrid['results'] if r['reference'] in available]
        except Exception:
            hybrid=dict(keyword,notice='Local AI worker unavailable; showing keyword results.')
        hybrid['elapsed_ms']=round((time.monotonic()-start)*1000,1)
        for result in (keyword,hybrid):
            for r in result['results']:
                book=available[r['reference']];r.update(title=book['title'],author=book['author'])
                if owner_scope:r['catalog_item_id']=mapping[r['reference']]
        return dict(keyword=keyword,hybrid=hybrid)

    def handler(self):
        app=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,payload,kind='application/json'):
                data=payload if isinstance(payload,bytes) else payload.encode() if isinstance(payload,str) else json.dumps(payload).encode()
                self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'");self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def handle_request(self,write=False):
                try:
                    if self.headers.get('Host')!=urlsplit(app.config['origin']).netloc:return self.reply(403,{'error':'Invalid host'})
                    try:email=app.identity(self.headers.get('Cf-Access-Jwt-Assertion',''))
                    except jwt.PyJWKClientConnectionError:
                        return self.reply(503,'<!doctype html><html lang="en"><title>Sign-in temporarily unavailable</title><h1>Sign-in temporarily unavailable</h1><p>We could not verify your sign-in right now. Please try again shortly.</p><a href="/">Try again</a></html>','text/html') if urlsplit(self.path).path=='/' else self.reply(503,{'error':'Sign-in verification temporarily unavailable. Please retry.'})
                    except Exception:
                        return self.reply(403,'<!doctype html><html lang="en"><title>Sign in required</title><h1>Sign in required</h1><p>Please sign in using one of the invited email addresses.</p><a href="/cdn-cgi/access/logout">Sign in again</a></html>','text/html') if urlsplit(self.path).path=='/' else self.reply(403,{'error':'Sign in with an invited email address.'})
                    if email not in app.config['allowed_emails']:return self.reply(403,{'error':'Not authorized'})
                    path=urlsplit(self.path).path
                    if write:
                        if self.headers.get('Origin')!=app.config['origin'] or self.headers.get('Content-Type')!='application/json' or (not path.startswith('/owner/') and self.headers.get('X-Family-Request')!='1'):return self.reply(403,{'error':'Invalid request origin'})
                        length=int(self.headers.get('Content-Length','0'))
                        if length<1 or length>300000:return self.reply(413,{'error':'Request too large'})
                        body=json.loads(self.rfile.read(length))
                    if path=='/owner' or path.startswith('/owner/'):
                        if email!=app.config['owner_email']:return self.reply(403,{'error':'Owner access required'})
                        if path.startswith('/owner/search-pilot'):
                            if not app.config.get('search_pilot_dir'):return self.reply(404,{'error':'Preview not enabled'})
                            if path=='/owner/search-pilot/query' and write:return self.reply(200,app.search_preview(body['query']))
                            if path=='/owner/search-pilot.js' and not write:return self.reply(200,Path(__file__).with_name('family_search_preview.js').read_text(),'text/javascript')
                            if path=='/owner/search-pilot/report' and not write:return self.reply(200,(Path(app.config['search_pilot_dir'])/'report.html').read_bytes(),'text/html')
                            if path=='/owner/search-pilot' and not write:
                                return self.reply(200,'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Private search preview</title><style>body{font:17px system-ui;color:#25372e;max-width:1200px;margin:2rem auto;padding:1rem}h1,h2,h3{color:#245d49}input,button{font:inherit;padding:.6rem}input{width:70%}.columns{display:grid;grid-template-columns:1fr 1fr;gap:2rem}article{border-bottom:1px solid #ccc;padding:1rem 0}small{color:#606c65}@media(max-width:700px){.columns{display:block}}</style><div style="display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap"><a href="/owner/">Owner workspace</a>'+owner_badge(email)+'</div><h1>Private search preview</h1><p>Compare ranked keywords with local AI. Only family-visible metadata and descriptions are indexed. Related-topic suggestions may be imperfect.</p><a href="/owner/search-pilot/report">42-query comparison report</a><form><label for="query">Find books</label><p><input id="query" maxlength="500" required placeholder="Try a title, ISBN or topic"><button>Compare</button></p></form><p id="notice" role="status"></p><div class="columns"><section id="keyword"></section><section id="hybrid"></section></div><script src="/owner/search-pilot.js" defer></script></html>','text/html')
                            return self.reply(404,{'error':'Not found'})
                        local=path[len('/owner'):] or '/'
                        headers={'Origin':'http://127.0.0.1:8765'}
                        payload=None
                        if write:
                            headers.update({'Content-Type':'application/json','X-Workspace-Token':self.headers.get('X-Workspace-Token','')})
                            payload=json.dumps(body).encode()
                        req=Request('http://127.0.0.1:8765'+local,data=payload,headers=headers)
                        try:r=urlopen(req,timeout=30)
                        except HTTPError as exc:r=exc
                        output=r.read();kind=r.headers.get('Content-Type','application/json').split(';')[0]
                        if kind=='text/html':
                            text=output.decode().replace('"/api/','"/owner/api/').replace('src="/requests.js"','src="/owner/requests.js"')
                            text=text.replace('<div class="brand">','<div class="brand" style="display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap">').replace('<strong>Library Valuation</strong>','<strong>Library Valuation</strong>'+owner_badge(email))
                            if app.config.get('search_pilot_dir'):
                                text=text.replace('</header>','<p style="margin:.4rem 0"><a href="/owner/search-pilot">Try the AI search preview</a> · Library search combines keywords and local AI.</p></header>',1)
                            nonce=secrets.token_urlsafe(20)
                            text=re.sub(r'<script(?=[ >])','<script nonce="'+nonce+'"',text)
                            self.send_response(r.code);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'nonce-"+nonce+"'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; frame-ancestors 'none'; base-uri 'none'");self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');output=text.encode();self.send_header('Content-Length',str(len(output)));self.end_headers();self.wfile.write(output);return
                        return self.reply(r.code,output,kind)
                    if path=='/' and email==app.config['owner_email']:
                        self.send_response(302);self.send_header('Location','/owner/');self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers();return
                    catalog,snapshot=app.catalog()
                    with closing(store.connect(app.db)) as db:
                        if write:
                            if path=='/api/search':
                                if not app.config.get('family_search_enabled'):return self.reply(404,{'error':'Search not enabled'})
                                return self.reply(200,app.search_preview(body['query'])['hybrid'])
                            if path=='/api/list':return self.reply(200,store.save(db,email,body['version'],body['books'],body.get('message',''),catalog))
                            if path=='/api/submit':return self.reply(200,store.submit(db,email,body['version'],body['key'],catalog,snapshot))
                            return self.reply(404,{'error':'Not found'})
                        if path=='/api/me':
                            from valuation import family_owner as owner
                            owner.schema(db);own=store.submissions(db,email)
                            for row in own:
                                for book in row['payload']['books']:
                                    book['request_status']=owner.decision(db,row['id'],book['reference'])['state']
                                    book['owner_messages']=owner.recipient_messages(db,row['id'],book['reference'])
                            return self.reply(200,dict(email=email,owner=email==app.config['owner_email'],draft=store.draft(db,email),submissions=own))
                        if path=='/api/inbox':
                            if email!=app.config['owner_email']:return self.reply(403,{'error':'Owner access required'})
                            return self.reply(200,store.submissions(db))
                        if path=='/app.js':return self.reply(200,Path(__file__).with_name('family_app.js').read_text(),'text/javascript')
                        if path=='/':
                            updated=datetime.fromtimestamp(Path(app.config['snapshot']).stat().st_mtime,timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                            page=render(list(catalog.values()),updated)
                            page=page[:page.index('<script>')]+ '<script src="/app.js" defer></script></html>'
                            page=page.replace('This is a read-only catalog.','You can save a personal list and submit requests to Tom.')
                            page=page.replace('<main>','<nav class="family-nav" aria-label="Library views"><button id="browse">Browse</button> <button id="mine">My List</button> <button id="inbox" hidden>Owner inbox</button></nav><p id="saved" role="status"></p><section id="panel" hidden></section><main>')
                            # Stable references supplied as escaped HTML attributes, never private catalog IDs.
                            import html
                            for r in catalog.values():
                                title='<h2>'+html.escape(r['title'],quote=True)+'</h2>'
                                # replace one at a time to distinguish repeated titles
                                marker='<article>'+title
                                page=page.replace(marker,'<article data-ref="'+r['reference']+'">'+title+'<button class="choose" type="button">Add to my list</button>',1)
                            return self.reply(200,page,'text/html')
                        return self.reply(404,{'error':'Not found'})
                except store.Conflict as e:self.reply(409,{'error':str(e)})
                except (ValueError,KeyError,TypeError):self.reply(400,{'error':'Invalid or stale request. Refresh and try again.'})
                except Exception:self.reply(503,{'error':'Unable to save right now. Your request is not confirmed; please retry.'})
            def do_GET(self):self.handle_request()
            def do_POST(self):self.handle_request(True)
        return Handler

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args();app=App(json.loads(Path(a.config).read_text()))
    ThreadingHTTPServer(('127.0.0.1',8877),app.handler()).serve_forever()
