"""Bounded, resumable eBay detail pilot. Writes private previews only."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import quote, urlencode

from valuation.ebay_access import EbayAccessClient, EbayCredentials, EbayRequestError, ENVIRONMENT_HOSTS, default_request_json
from valuation.ebay_active_listings import EbayBrowseSession
from valuation.offline_valuation_review import isbn, binding, read_csv

VERSION='live-pilot-v1'
FIELDS=['catalog_id','source','lookup_status','observation_date','lookup_strategy','search_query',
        'listing_url','raw_reference','listing_title','listing_author','asking_price','currency','condition',
        'listing_isbn13','listing_isbn10','listing_isbns','listing_binding','listing_condition_grade',
        'listing_publisher','listing_year','listing_edition','listing_format_raw','listing_condition_description','buying_options','detail_status','metadata_basis']


def stamp():return datetime.now(timezone.utc).isoformat()

def clean(value,limit=1000):
    if not isinstance(value,(str,int,float)):return ''
    value=' '.join(str(value).split())[:limit]
    value=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email omitted]',value)
    return value


def atomic(path,value):
    path=Path(path);temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8') as f:
        os.chmod(temp,0o600);json.dump(value,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def condition_grade(value):
    value=clean(value).lower().replace('_',' ')
    for text,grade in [('like new','like_new'),('brand new','new'),('very good','very_good'),('acceptable','acceptable'),('good','good'),('new','new')]:
        if re.search(r'\b'+text+r'\b',value):return grade
    return ''


def normalize_detail(item,book,query,strategy,*,observed_at):
    """Allowlist listing facts only. Never retain seller/raw payload or infer ISBN from query."""
    aspects={}
    def add(name,value):
        name=clean(name).casefold()
        if name and isinstance(value,(str,int,float)):
            aspects.setdefault(name,[]).append(clean(value))
    for aspect in item.get('localizedAspects',[]) or []:
        if isinstance(aspect,dict):add(aspect.get('name'),aspect.get('value'))
    product=item.get('product',{})
    if not isinstance(product,dict):product={}
    for group in product.get('aspectGroups',[]) or []:
        if not isinstance(group,dict):continue
        for aspect in group.get('aspects',[]) or []:
            if not isinstance(aspect,dict):continue
            for value in aspect.get('localizedValues',[]) or []:add(aspect.get('localizedName'),value)
    def values(*names):return [v for name in names for v in aspects.get(name,[])]
    candidates=[item.get('gtin',''),*(product.get('gtins',[]) or []),*values('isbn','isbn-13','isbn 13','isbn13','isbn-10','isbn 10','isbn10','ean')]
    normalized=set()
    for v in candidates:
        # Multiple identifiers may be supplied in an aspect, but target ISBN is never an input.
        for token in re.findall(r'[0-9Xx][0-9Xx\s-]{8,30}[0-9Xx]',clean(v)):
            value=isbn(token)
            if value:normalized.add(value)
        value=isbn(clean(v))
        if value:normalized.add(value)
    # Conflicting returned identifiers remain explicit and cannot be verified.
    chosen=next(iter(normalized)) if len(normalized)==1 else ''
    formats=values('format','binding','book format')
    bindings={binding(v) for v in formats if binding(v)}
    actual_binding=next(iter(bindings)) if len(bindings)==1 else ''
    price=item.get('price',{})
    if not isinstance(price,dict):price={}
    options=item.get('buyingOptions',[]) or []
    if not isinstance(options,list):options=[]
    condition=clean(item.get('condition',''))
    url=clean(item.get('itemWebUrl',''))
    # No seller-derived URLs are fetched; this field is display evidence only.
    from urllib.parse import urlsplit
    try:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or not (parsed.hostname=='ebay.com' or parsed.hostname.endswith('.ebay.com')) or parsed.username:url=''
    except ValueError:url=''
    description=clean(item.get('conditionDescription',''),2000)
    description=re.sub(r'https?://\S+','[link omitted]',description)
    description=re.sub(r'(?<!\w)(?:\+?\d[ ()-]*){10,}(?!\w)','[contact number omitted]',description)
    row=dict.fromkeys(FIELDS,'')
    row.update(catalog_id=book['catalog_item_id'],source='ebay_active_listings',lookup_status='observed',
               observation_date=observed_at,lookup_strategy=strategy,search_query=query,
               listing_url=url,raw_reference=clean(item.get('itemId','')),
               listing_title=clean(item.get('title','')),listing_author='; '.join(values('author','authors')),
               asking_price=clean(price.get('value','')),currency=clean(price.get('currency','')),
               condition=condition,listing_isbn13=chosen,listing_isbns='; '.join(sorted(normalized)),
               listing_binding=actual_binding,listing_condition_grade=condition_grade(condition),
               listing_publisher='; '.join(values('publisher')),listing_year='; '.join(values('publication year','year')),
               listing_edition='; '.join(values('edition')),listing_format_raw='; '.join(formats),listing_condition_description=description,buying_options='; '.join(clean(x) for x in options),
               detail_status='retrieved',metadata_basis='eBay getItem structured fields; missing values remain unknown')
    if len(normalized)>1:row['detail_status']='conflicting_isbns'
    if len(bindings)>1:row['detail_status']='conflicting_bindings'
    if 'FIXED_PRICE' not in options:row['lookup_status']='excluded_buying_option'
    return row


class BudgetExceeded(RuntimeError):pass


class PilotApi:
    def __init__(self,credentials,state,save,*,delay=1.0,request_json=default_request_json,sleep=time.sleep):
        self.credentials=credentials;self.state=state;self.save=save;self.sleep=sleep;self.delay=delay
        def guarded(request,timeout):
            if state['request_count']>=state['manifest']['request_budget']:raise BudgetExceeded('Pilot request budget exhausted')
            state['request_count']+=1;save();sleep(delay)
            return request_json(request,timeout)
        self.access=EbayAccessClient(credentials,request_json=guarded)
        self.session=EbayBrowseSession(self.access)
    def get(self,path,params=None):
        host,_=ENVIRONMENT_HOSTS[self.credentials.environment]
        from urllib.request import Request
        url=host+'/buy/browse/v1/'+path+('?' + urlencode(params) if params else '')
        for attempt in range(2):
            token=self.session.current_token().value
            request=Request(url,headers={'Authorization':'Bearer '+token,'X-EBAY-C-MARKETPLACE-ID':self.credentials.marketplace_id,'Accept':'application/json'})
            try:return self.access._safe_request(request,'pilot detail/search',token)
            except EbayRequestError as e:
                if attempt==0 and e.status_code==401:self.session.refresh_token();continue
                if attempt==0 and (e.status_code in {500,502,503,504} or e.failure_kind=='network'):
                    self.sleep(2);continue
                raise
        raise RuntimeError('Request failed')
    def search(self,book,limit):
        target=isbn(book.get('isbn13') or book.get('isbn10',''))
        mode=self.state['manifest'].get('search_mode')
        used_only=mode in {'used_isbn','used_preferred'}
        if mode=='used_isbn' and not target:raise ValueError('Used follow-up requires a valid ISBN')
        if used_only:
            strategy='used_isbn_keyword' if target else 'used_title_author'
            query=target or ' '.join(x for x in [book.get('title',''),book.get('author','')] if x)
            params={'q':query,'limit':limit,'filter':'buyingOptions:{FIXED_PRICE},conditions:{USED}'}
        elif target:strategy='gtin';query=target;params={'gtin':target,'limit':limit,'filter':'buyingOptions:{FIXED_PRICE}'}
        else:
            strategy='title_author';query=' '.join(x for x in [book.get('title',''),book.get('author','')] if x)
            params={'q':query,'limit':limit,'filter':'buyingOptions:{FIXED_PRICE}'}
        payload=self.get('item_summary/search',params)
        items=payload.get('itemSummaries',[])
        if not isinstance(items,list):raise ValueError('Invalid search response')
        # Single controlled keyword fallback when catalog GTIN indexing has no result.
        if not items and target and not used_only:
            strategy='isbn_keyword';payload=self.get('item_summary/search',{'q':target,'limit':limit,'filter':'buyingOptions:{FIXED_PRICE}'})
            items=payload.get('itemSummaries',[])
            if not isinstance(items,list):raise ValueError('Invalid fallback response')
        ids=[]
        for item in items[:limit]:
            if not isinstance(item,dict):continue
            item_id=clean(item.get('itemId',''))
            if re.fullmatch(r'v1\|\d+\|\d+',item_id) and item_id not in ids:ids.append(item_id)
        return dict(query=query,strategy=strategy,item_ids=ids,total=payload.get('total',0))
    def detail(self,item_id):
        if not re.fullmatch(r'v1\|\d+\|\d+',item_id):raise ValueError('Invalid eBay item ID')
        return self.get('item/'+quote(item_id,safe=''),{'fieldgroups':'PRODUCT'})


def collect(pilot_path,output_dir,credentials,*,max_results=10,request_budget=400,delay=1.0,api_factory=PilotApi,progress=print,search_mode=None):
    pilot_path=Path(pilot_path).resolve();output_dir=Path(output_dir).resolve()
    if credentials.environment!='production':raise ValueError('Pilot requires explicitly configured production access')
    if not 1<=max_results<=10 or not 1<=request_budget<=400 or delay<0:raise ValueError('Pilot limits exceeded')
    if 'data' in output_dir.parts:raise ValueError('Use a private output directory, not canonical data')
    if search_mode not in {None,'used_isbn','used_preferred'}:raise ValueError('Unknown search mode')
    pilot=read_csv(pilot_path);ids=[b.get('catalog_item_id','') for b in pilot]
    if not 1<=len(ids)<=30 or not all(ids) or len(set(ids))!=len(ids):raise ValueError('Pilot requires 1–30 distinct catalog identities')
    manifest=dict(version=VERSION,pilot_sha256=hashlib.sha256(pilot_path.read_bytes()).hexdigest(),catalog_ids=ids,
                  max_results=max_results,request_budget=request_budget,marketplace=credentials.marketplace_id,environment=credentials.environment)
    if search_mode:manifest['search_mode']=search_mode
    output_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (output_dir/'.run.lock').open('a') as lock:
        os.chmod(output_dir/'.run.lock',0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=output_dir/'checkpoint.json'
        if path.exists():
            state=json.loads(path.read_text())
            if state['manifest']!=manifest:raise ValueError('Checkpoint differs from pilot/configuration; use a new run directory')
        else:
            if any(p.name!='.run.lock' for p in output_dir.iterdir()):raise ValueError('Output directory contains another run')
            state=dict(manifest=manifest,started_at=stamp(),request_count=0,books={},status='collecting')
            atomic(path,state)
        save=lambda:atomic(path,state)
        api=api_factory(credentials,state,save,delay=delay)
        state['status']='collecting';save()
        for book in pilot:
            cid=book['catalog_item_id'];entry=state['books'].setdefault(cid,dict(details={}))
            if entry.get('completed'):continue
            try:
                if 'search' not in entry:
                    entry['search']=api.search(book,max_results);save()
                search=entry['search']
                for item_id in search['item_ids']:
                    if item_id in entry['details']:continue
                    try:
                        item=api.detail(item_id)
                        if item.get('itemId')!=item_id:raise ValueError('Item response identity mismatch')
                        row=normalize_detail(item,book,search['query'],search['strategy'],observed_at=stamp())
                    except EbayRequestError as e:
                        if e.status_code in {401,403,429} or e.status_code is None or e.status_code>=500:raise
                        row=dict.fromkeys(FIELDS,'');row.update(catalog_id=cid,source='ebay_active_listings',lookup_status='source_unavailable',observation_date=stamp(),raw_reference=item_id,detail_status='HTTP '+str(e.status_code))
                    entry['details'][item_id]=row;save()
                entry['completed']=True;entry.pop('error',None);save()
                progress(f"Completed {sum(bool(v.get('completed')) for v in state['books'].values())}/{len(pilot)} books; API requests {state['request_count']}")
            except Exception as e:
                # Never store response bodies, credentials or arbitrary exception text.
                entry['error']=dict(type=type(e).__name__,http_status=getattr(e,'status_code',None))
                state['status']='paused';save();materialize(output_dir,state)
                raise RuntimeError(f"Pilot paused at {cid}; {type(e).__name__}, HTTP {getattr(e,'status_code',None)}. Details retained for safe resume.") from None
        state['status']='complete';state['completed_at']=stamp();save();materialize(output_dir,state)
        return state


def materialize(output_dir,state):
    rows=[]
    for cid in state['manifest']['catalog_ids']:
        entry=state['books'].get(cid,{})
        rows.extend(entry.get('details',{}).values())
        if entry.get('completed') and not entry.get('search',{}).get('item_ids'):
            r=dict.fromkeys(FIELDS,'');r.update(catalog_id=cid,source='ebay_active_listings',lookup_status='no_results',observation_date=state['started_at'],detail_status='no_results')
            rows.append(r)
    path=output_dir/'observations.csv';temp=output_dir/'observations.csv.tmp'
    with temp.open('w',newline='',encoding='utf-8') as f:
        os.chmod(temp,0o600);w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--credentials',type=Path,required=True);p.add_argument('--confirm-production',action='store_true')
    p.add_argument('--search-mode',choices=['used_isbn','used_preferred'],default=None)
    p.add_argument('--max-results',type=int,default=10);p.add_argument('--request-budget',type=int,default=400)
    a=p.parse_args()
    if not a.confirm_production:p.error('Explicit --confirm-production is required')
    import certifi
    os.environ['SSL_CERT_FILE']=certifi.where()
    credentials=EbayCredentials.from_environment(json.loads(a.credentials.read_text()))
    collect(a.pilot,a.output_dir,credentials,max_results=a.max_results,request_budget=a.request_budget,search_mode=a.search_mode)
