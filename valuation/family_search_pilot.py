"""Build/evaluate the private search prototype; optional loopback preview worker."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import html
import json
import os
from pathlib import Path
import re
import time
from valuation.family_search import Search,normalize,fingerprint
from valuation.family_search_embeddings import Embeddings,build


def evaluate(records,engine):
    # Deterministic known-item tests plus explicit topical probes; no generated relevance claims.
    candidates=[r for r in sorted(records,key=lambda r:r['title']) if len(r['title'])>18 and r['isbn']]
    sample=[candidates[i*len(candidates)//10] for i in range(10)]
    cases=[]
    for r in sample:
        cases.extend([dict(kind='exact_title',query=r['title'][:500],expected=r['reference']),dict(kind='exact_isbn',query=r['isbn'],expected=r['reference'])])
    for r in sample[:8]:
        words=normalize(r['title']).split();i=max(range(len(words)),key=lambda i:len(words[i]));w=words[i];words[i]=w[:len(w)//2]+w[len(w)//2+1:]
        cases.append(dict(kind='typo',query=' '.join(words),expected=r['reference']))
    for query in ['approachable introduction to medieval philosophy','how Christianity relates to modern science','how the human mind and consciousness work','the history and interpretation of the gospels','books about learning to paint landscapes','how language evolved in humans','the origins of the universe','ancient Greek ideas about a good life','understanding probability and uncertainty','the development of Christian doctrine']:
        cases.append(dict(kind='topic_review',query=query))
    for query in ['9780000000000','zxqvplm nrtwzzzz','flibbertigibbet neutron toaster warranty','a guide to repairing Martian hoverboards']:
        cases.append(dict(kind='negative_review',query=query))
    results=[]
    for case in cases:
        row=dict(case)
        for mode in ('keyword','hybrid'):
            start=time.monotonic();out=engine.search(case['query'],mode=mode,limit=8);row[mode]=out;row[mode+'_ms']=round((time.monotonic()-start)*1000,1)
            if case.get('expected'):row[mode+'_hit5']=case['expected'] in [r['reference'] for r in out['results'][:5]]
        results.append(row)
    known=[r for r in results if r.get('expected')]
    return dict(cases=results,known_item_count=len(known),keyword_hit5=sum(r['keyword_hit5'] for r in known),hybrid_hit5=sum(r['hybrid_hit5'] for r in known),fingerprint=fingerprint(records),manual_topic_review_required=True)


def report(evaluation,records):
    byref={r['reference']:r for r in records};esc=lambda s:html.escape(str(s))
    rows=[]
    for r in evaluation['cases']:
        cells=[esc(r['kind']),esc(r['query'])]
        for mode in ('keyword','hybrid'):
            lines=[]
            for result in r[mode]['results'][:5]:
                book=byref[result['reference']];lines.append('<li><strong>'+esc(book['title'])+'</strong> — '+esc(book['author'])+'<br>'+esc(result['reason'])+'<br>'+esc(result['excerpt'])+'</li>')
            cells.append(str(r[mode+'_ms'])+' ms<ul>'+''.join(lines)+'</ul>')
        rows.append('<tr>'+''.join('<td>'+c+'</td>' for c in cells)+'</tr>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Private search comparison</title><style>body{font:16px system-ui;margin:2rem;color:#25372e}td,th{vertical-align:top;text-align:left;padding:1rem;border-bottom:1px solid #ccc}td{max-width:32rem}li{margin-bottom:1rem}</style><h1>Private search comparison</h1><p>Keyword and local AI results. Topic and negative queries require human review; these are candidates, not claims about a book. No catalog records or estimates were changed.</p><p>Known-item top-five hits: keyword '+str(evaluation['keyword_hit5'])+'/'+str(evaluation['known_item_count'])+'; hybrid '+str(evaluation['hybrid_hit5'])+'/'+str(evaluation['known_item_count'])+'.</p><table><tr><th>Test</th><th>Query</th><th>Keyword</th><th>Local AI + keyword</th></tr>'+''.join(rows)+'</table></html>'


def serve(engine,token_path):
    from secrets import compare_digest
    token=Path(token_path).read_text().strip();current=fingerprint(list(engine.records.values()))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            if self.headers.get('Host')!='127.0.0.1:8878' or not compare_digest(self.headers.get('X-Search-Token',''),token):self.send_error(403);return
            if self.path!='/search':self.send_error(404);return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<1 or size>200000:raise ValueError()
                body=json.loads(self.rfile.read(size))
                if body.get('fingerprint')!=current:self.send_error(409);return
                if not isinstance(body.get('allowed'),list) or any(not isinstance(ref,str) for ref in body['allowed']):raise ValueError()
                out=engine.search(body['query'],allowed=body['allowed'],mode=body.get('mode','hybrid'))
                data=json.dumps(out).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except (ValueError,KeyError,TypeError):self.send_error(400)
    ThreadingHTTPServer(('127.0.0.1',8878),Handler).serve_forever()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','evaluate','serve']);p.add_argument('--snapshot',required=True);p.add_argument('--model',required=True);p.add_argument('--directory',required=True);p.add_argument('--token');a=p.parse_args()
    records=json.loads(Path(a.snapshot).read_text());directory=Path(a.directory)
    if a.action=='build':print(json.dumps(build(records,a.model,directory)));return
    semantic=Embeddings(records,a.model,directory);engine=Search(records,semantic)
    if a.action=='serve':serve(engine,a.token);return
    result=evaluate(records,engine)
    for name,value in [('evaluation.json',json.dumps(result,indent=2)),('report.html',report(result,records))]:
        dest=directory/name;dest.write_text(value);dest.chmod(0o600)
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}))

if __name__=='__main__':main()
