"""Quota-aware, checkpointed read-only review of the remaining physical library.

A finite job: it exits after completion or a critical integrity failure. Production
catalog, estimates and decisions are never written by this module.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import fcntl
import hashlib
import html
import json
import os
import shutil
from pathlib import Path
import time
from urllib.request import Request

from valuation.ebay_access import EbayAccessClient, EbayCredentials, EbayRequestError, default_request_json
from valuation.live_valuation_pilot import PilotApi, FIELDS, atomic, collect, stamp
from valuation.offline_valuation_review import read_csv, isbn

VERSION='whole-library-review-v1'
RULE_FILES=['whole_library_review.py','live_valuation_pilot.py','offline_valuation_review.py',
            'candidate_record_review.py','live_pilot_report.py','pilot_followup.py']
RESERVE=100


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).timestamp()
def parse_time(value):return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def rules():return {name:sha(Path(__file__).parent/name) for name in RULE_FILES}


def private_root(path):
    root=Path(path).resolve()
    if 'data' in root.parts:raise ValueError('Use a private output directory outside canonical data')
    return root


def protected(project):
    project=Path(project)
    paths=[*(project/'data').glob('*.csv'),*(project/'data').glob('*.json'),
           project/'output/libib_inventory_20261020/combined_market_evidence_summary.csv']
    return {str(p.relative_to(project)):sha(p) for p in paths}


def save_csv(path,rows,fields):
    path=Path(path);temp=path.with_name(path.name+'.tmp')
    with temp.open('w',newline='',encoding='utf-8') as f:
        os.chmod(temp,0o600);writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def remaining_records(records,excluded):
    ids=[b['catalog_item_id'] for b in records]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate active catalog identity')
    excluded=set(excluded)
    if not excluded<=set(ids):raise ValueError('Previously reviewed records differ from active inventory')
    return sorted((dict(b) for b in records if b['catalog_item_id'] not in excluded),
                  key=lambda b:hashlib.sha256(('whole-library-v1'+b['catalog_item_id']).encode()).hexdigest())


def prepare(project,root,previous_cohorts):
    """Freeze authoritative records into disjoint batches, with explicit review-only policy."""
    from valuation.workspace_service import WorkspaceStore
    project=Path(project).resolve();root=private_root(root)
    if root.exists():raise ValueError('Choose a new job directory; prior work is preserved')
    before=protected(project);store=WorkspaceStore(project/'data',project/'output');model=store.model
    active=set(model.completed_inventory.catalog_item_ids)
    cohorts=[read_csv(p) for p in previous_cohorts];excluded=[r['catalog_item_id'] for rows in cohorts for r in rows]
    if len(excluded)!=len(set(excluded)):raise ValueError('Previous cohorts overlap')
    records=[]
    for b in model.books:
        if b.catalog_item_id in active:
            records.append(dict(catalog_item_id=b.catalog_item_id,title=b.title,author=b.author,
                isbn13=b.isbn13,isbn10=b.isbn10,location=b.location_summary,
                previous_low=b.estimated_value_precise_low,previous_high=b.estimated_value_precise_high,
                currency=b.estimated_value_currency,reviewed_estimate_id=b.reviewed_estimate_id,
                target_binding='',target_condition=''))
    selected=remaining_records(records,excluded)
    if not selected:raise ValueError('No remaining active catalog records')
    catalog={r['catalog_item_id']:r for r in read_csv(project/'data/catalog_items.csv')}
    holdings=read_csv(project/'data/inventory_holdings.csv');acquisitions=read_csv(project/'data/acquisitions.csv')
    observations={r['inventory_observation_id']:r for r in read_csv(project/'data/inventory_observations.csv')}
    source_notes_path=project/'output/libib_review_20261103/reviewed_source_notes.json'
    source_notes=json.loads(source_notes_path.read_text()) if source_notes_path.exists() else []
    root.mkdir(parents=True,mode=0o700)
    save_csv(root/'cohort.csv',selected,list(selected[0]));atomic(root/'protected_before.json',before)
    batches=[]
    for index,start in enumerate(range(0,len(selected),25),1):
        folder=root/'batches'/f'{index:03}';folder.mkdir(parents=True,mode=0o700)
        books=selected[start:start+25];ids={b['catalog_item_id'] for b in books};packet={}
        save_csv(folder/'cohort.csv',books,list(selected[0]))
        for cid in ids:
            hs=[h for h in holdings if h['catalog_item_id']==cid]
            obs=[observations[h['latest_inventory_observation_id']] for h in hs if h['latest_inventory_observation_id'] in observations]
            obs_ids={o['inventory_observation_id'] for o in obs}
            packet[cid]=dict(catalog=catalog[cid],holdings=hs,observations=obs,
                acquisitions=[a for a in acquisitions if a['catalog_item_id']==cid],
                source_notes=[n for n in source_notes if n.get('observation_id') in obs_ids])
        atomic(folder/'record_packet.json',packet)
        atomic(folder/'notes.json',{b['catalog_item_id']:'Whole-library review: seller-reported binding and condition define hypothetical asking-price scenarios only. Actual copy grades remain unassigned. Existing source-page notes are retained; physical grading is deferred. Saved estimates and decisions remain unchanged.' for b in books})
        atomic(folder/'condition_policy.json',dict(schema_version=1,approval_source='Explicit owner authorization for remaining library, batch-to-batch continuation except critical defects',catalog_item_ids=sorted(ids),mode='labelled_used_scenarios',physical_grading='defer_until_handled',default_grade=None,publication='disabled'))
        batches.append(dict(number=index,folder=str(folder.relative_to(root)),books=len(books),inputs={n:sha(folder/n) for n in ('cohort.csv','record_packet.json','notes.json','condition_policy.json')}))
    if before!=protected(project):raise ValueError('Source data changed while freezing the plan')
    manifest=dict(version=VERSION,created_at=stamp(),project=str(project),active_records=len(active),previously_reviewed=len(excluded),remaining_records=len(selected),batch_size=25,batches=batches,cohort_sha256=sha(root/'cohort.csv'),previous_cohorts={str(p):sha(p) for p in previous_cohorts},rule_fingerprints=rules(),publication='disabled',physical_grading='deferred',max_requests_per_batch=400,max_results_per_book=10,source_notes_sha256=sha(source_notes_path) if source_notes_path.exists() else None)
    atomic(root/'manifest.json',manifest);atomic(root/'status.json',dict(state='ready',completed_batches=0,completed_books=0,requests=0,updated_at=stamp()))
    dashboard(root);return manifest


def verify_frozen(root,manifest):
    if rules()!=manifest['rule_fingerprints']:raise ValueError('Review code changed during the frozen run')
    if sha(root/'cohort.csv')!=manifest['cohort_sha256']:raise ValueError('Frozen cohort changed')
    if any(sha(path)!=digest for path,digest in manifest.get('previous_cohorts',{}).items()):raise ValueError('Previous cohort provenance changed')
    if protected(manifest['project'])!=json.loads((root/'protected_before.json').read_text()):raise ValueError('Canonical records or active estimate state changed')
    for batch in manifest['batches']:
        folder=root/batch['folder']
        if (folder/'result.json').exists():
            result=json.loads((folder/'result.json').read_text())
            if not result.get('complete') or sha(folder/'collection/checkpoint.json')!=result['checkpoint_sha256'] or sha(folder/'collection/observations.csv')!=result['observations_sha256']:raise ValueError('Completed collection changed')
            if any(sha(folder/name)!=digest for name,digest in result['report_files'].items()):raise ValueError('Completed report changed')
        if any(sha(folder/name)!=digest for name,digest in batch['inputs'].items()):raise ValueError('Frozen batch input changed')


class QuotaPause(EbayRequestError):
    def __init__(self):super().__init__('Quota boundary reached; resume after refresh',status_code=429,failure_kind='quota')


class QuotaLedger:
    """Conservative persisted allowance, not dependent on fresh server telemetry."""
    def __init__(self,path,clock=now):self.path=Path(path);self.clock=clock
    def update(self,remaining,reset):
        if not isinstance(remaining,int) or remaining<0 or parse_time(reset)<=self.clock():raise ValueError('Invalid quota response')
        old=json.loads(self.path.read_text()) if self.path.exists() else None
        same=old and old['reset']==reset
        value=min(remaining,old['remaining']) if same else remaining
        state=dict(remaining=value,reset=reset,updated_at=stamp());atomic(self.path,state);return state
    def state(self):return json.loads(self.path.read_text())
    def charge(self):
        s=self.state()
        if self.clock()>=parse_time(s['reset']) or s['remaining']<=RESERVE:raise QuotaPause()
        s['remaining']-=1;atomic(self.path,s)
    def ready(self,budget=400):
        s=self.state();return self.clock()<parse_time(s['reset']) and s['remaining']>=budget+RESERVE


def refresh_quota(credentials,root,ledger):
    client=EbayAccessClient(credentials);token=client.acquire_application_token()
    payload=client._safe_request(Request('https://api.ebay.com/developer/analytics/v1_beta/rate_limit/?api_context=buy&api_name=browse',headers={'Authorization':'Bearer '+token}),'quota check',token)
    rates=[r for api in payload.get('rateLimits',[]) for resource in api.get('resources',[]) if resource.get('name')=='buy.browse' for r in resource.get('rates',[]) if r.get('timeWindow')==86400]
    if len(rates)!=1:raise ValueError('Unrecognized daily Browse quota response')
    r=rates[0];state=ledger.update(r['remaining'],r['reset'])
    path=root/'quota_history.json';history=json.loads(path.read_text()) if path.exists() else []
    history.append(dict(at=stamp(),reported_remaining=r['remaining'],effective_remaining=state['remaining'],limit=r.get('limit'),reset=r['reset'],control_requests=2));atomic(path,history)
    return state


def validate_collection(folder):
    state=json.loads((folder/'collection/checkpoint.json').read_text());books=read_csv(folder/'cohort.csv');ids=[b['catalog_item_id'] for b in books]
    if state['status']!='complete' or state['manifest']['catalog_ids']!=ids or set(state['books'])!=set(ids):raise ValueError('Incomplete or unexpected batch scope')
    if state['manifest']['pilot_sha256']!=sha(folder/'cohort.csv') or state['manifest'].get('search_mode')!='used_preferred' or state['request_count']>400:raise ValueError('Collection manifest mismatch')
    expected=[]
    for cid in ids:
        entry=state['books'][cid]
        if not entry.get('completed'):raise ValueError('Incomplete book')
        expected.extend(entry.get('details',{}).values())
        if not entry.get('search',{}).get('item_ids'):
            row=dict.fromkeys(FIELDS,'');row.update(catalog_id=cid,source='ebay_active_listings',lookup_status='no_results',observation_date=state['started_at'],detail_status='no_results');expected.append(row)
    signature=lambda r:json.dumps(r,sort_keys=True)
    if Counter(map(signature,expected))!=Counter(map(signature,read_csv(folder/'collection/observations.csv'))):raise ValueError('Evidence differs from checkpoint')
    return state


def review_batch(folder):
    from valuation.live_pilot_report import report
    from valuation.candidate_record_review import run_review
    state=validate_collection(folder)
    attempts=sorted(folder.glob('report_attempt_*'));attempt=folder/f'report_attempt_{len(attempts)+1:03}';attempt.mkdir(mode=0o700)
    as_of=datetime.now(timezone.utc).date().isoformat()
    shutil.copy2(folder/'collection/observations.csv',attempt/'observations.csv');shutil.copy2(folder/'collection/checkpoint.json',attempt/'checkpoint.json')
    report(folder/'cohort.csv',attempt/'observations.csv',attempt/'checkpoint.json',attempt/'preliminary',as_of=as_of)
    summary=run_review(folder/'record_packet.json',folder/'notes.json',attempt/'preliminary/review.json',attempt/'observations.csv',attempt/'review',condition_policy_path=folder/'condition_policy.json',include_all_books=True)
    reviews=json.loads((attempt/'review/review.json').read_text())['reviews'];books={b['catalog_item_id']:b for b in read_csv(folder/'cohort.csv')}
    if summary['condition_checks_deferred']!=len(books):raise ValueError('Grading deferral invariant failed')
    for book in reviews:
        if book['publishable'] or book['actual_condition']!='ungraded':raise ValueError('Publication or grade invariant failed')
        target=isbn(books[book['catalog_item_id']].get('isbn13') or books[book['catalog_item_id']].get('isbn10',''))
        for d in book['listing_decisions']:
            if d['review_disposition']=='retained_candidate' and (not target or isbn(d.get('listing_isbn13') or d.get('listing_isbn10',''))!=target):raise ValueError('Retained listing identity invariant failed')
    result=dict(complete=True,completed_at=stamp(),books=len(books),requests=state['request_count'],summary=summary,report=str(attempt.relative_to(folder)/'review/review.html'),report_json=str(attempt.relative_to(folder)/'review/review.json'),checkpoint_sha256=sha(folder/'collection/checkpoint.json'),observations_sha256=sha(folder/'collection/observations.csv'),report_sha256=sha(attempt/'review/review.json'))
    result['report_files']={str(p.relative_to(folder)):sha(p) for p in attempt.rglob('*') if p.is_file()}
    atomic(folder/'result.json',result);return result


def consolidate(root,manifest):
    books=[];scenarios=[];checks=[];exceptions=[];inputs={};seen=set()
    for batch in manifest['batches']:
        folder=root/batch['folder'];receipt=folder/'result.json'
        if not receipt.exists():continue
        result=json.loads(receipt.read_text());report=folder/result['report_json'];inputs[str(report.relative_to(root))]=sha(report)
        for book in json.loads(report.read_text())['reviews']:
            cid=book['catalog_item_id']
            if cid in seen:raise ValueError('Duplicate catalog identity across completed batches')
            seen.add(cid);books.append(dict(batch=batch['number'],reviewed_at=result['completed_at'],book=book))
            base=dict(catalog_item_id=cid,title=book['title'],location=book['location'])
            for scenario in book['condition_scenarios']:scenarios.append(dict(**base,actual_condition='ungraded',**scenario))
            for check in book['physical_checks']:checks.append(dict(**base,kind=check['kind'],status=check.get('status','open'),question=check['question']))
            if not book['retained_used_context'] or any(s['listing_count']<3 or s['high_spread'] or s['listing_binding']=='unknown' for s in book['condition_scenarios']):
                exceptions.append(dict(**base,next_steps=' '.join(book['research_next_steps'])))
    atomic(root/'reviewed_books.json',dict(complete=len(books)==manifest['remaining_records'],reviewed_records=len(books),expected_records=manifest['remaining_records'],publication='disabled',physical_grading='deferred',input_hashes=inputs,books=books))
    def export(name,rows,fields):
        safe=[{k:("'"+str(v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()} for row in rows]
        save_csv(root/name,safe,list(rows[0]) if rows else fields)
    export('review_scenarios.csv',scenarios,['catalog_item_id','title','location','actual_condition','hypothetical_grade','listing_binding','currency','low','high','listing_count','evidence_label','high_spread','scenario_only','publishable'])
    export('deferred_physical_checks.csv',checks,['catalog_item_id','title','location','kind','status','question'])
    export('research_exceptions.csv',exceptions,['catalog_item_id','title','location','next_steps'])


def dashboard(root):
    """Atomic private progress page; no changes to the production workspace."""
    manifest=json.loads((root/'manifest.json').read_text());status=json.loads((root/'status.json').read_text());done=[];links=[]
    for batch in manifest['batches']:
        path=root/batch['folder']/'result.json'
        if path.exists():
            result=json.loads(path.read_text());done.append(result)
            links.append('<li><a href="'+html.escape(batch['folder']+'/'+result['report'])+'">Batch '+str(batch['number'])+' · '+str(result['books'])+' records</a></li>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Whole-library review progress</title><style>body{font:18px system-ui;max-width:1000px;margin:40px auto;padding:20px;color:#243c33}a,h1{color:#215a45}p,li{line-height:1.6}.notice{background:#fff4d7;padding:18px}</style><h1>Whole-library review progress</h1><p class="notice">Review only. Current estimates and saved decisions are unchanged. Actual copies are ungraded; physical grading is deferred. Scenarios show asking prices excluding shipping, not sale proceeds or approved values.</p>'
    page+='<p>Status: '+html.escape(status['state'].replace('_',' '))+'. Updated '+html.escape(status['updated_at'])+'.</p>'
    page+=f'<p>{sum(r["books"] for r in done):,} of {manifest["remaining_records"]:,} remaining records reviewed in {len(done)} of {len(manifest["batches"])} batches. {manifest["previously_reviewed"]} records were reviewed earlier and are excluded from new requests.</p>'
    page+=f'<p>Completed batch requests: {sum(r["requests"] for r in done):,}. Retained used-copy context: {sum(r["summary"]["books_with_retained_used_context"] for r in done):,} books. No results and thin comparisons remain flagged.</p>'
    if status.get('next_attempt_at'):page+='<p>Next automatic attempt: '+html.escape(datetime.fromtimestamp(status['next_attempt_at'],timezone.utc).isoformat())+'.</p>'
    if status.get('issue'):page+='<p>Stopped issue: '+html.escape(status['issue'])+'. No publication occurred.</p>'
    page+='<p><a href="review_scenarios.csv">Condition scenarios</a> · <a href="deferred_physical_checks.csv">Deferred grading and edition checks</a> · <a href="research_exceptions.csv">Research exceptions</a> · <a href="reviewed_books.json">Combined review data</a></p>' if (root/'reviewed_books.json').exists() else ''
    page+='<p><a href="status.json">Inspect progress</a> · <a href="manifest.json">Inspect frozen scope</a></p><h2>Completed review batches</h2><ul>'+''.join(links)+'</ul></html>'
    path=root/'index.html';temp=root/'index.html.tmp';temp.write_text(page);temp.chmod(0o600);os.replace(temp,path)


def run(root,credentials,*,once=False,sleep=time.sleep,clock=now):
    root=private_root(root);manifest=json.loads((root/'manifest.json').read_text());ledger=QuotaLedger(root/'quota_ledger.json',clock=clock)
    with (root/'.controller.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 'already_running'
        status=json.loads((root/'status.json').read_text())
        completed=[json.loads((root/b['folder']/'result.json').read_text()) for b in manifest['batches'] if (root/b['folder']/'result.json').exists()]
        status.update(completed_batches=len(completed),completed_books=sum(r['books'] for r in completed),requests=sum(r['requests'] for r in completed))
        if (root/'critical_stop.json').exists():return 'critical_stop'
        if status['state'] in {'complete','critical_stop'}:return status['state']
        def update(state,**kwargs):
            status.update(kwargs,state=state,updated_at=stamp());atomic(root/'status.json',status);dashboard(root)
        failures=0
        while True:
            if status.get('next_attempt_at',0)>clock():
                if once:return status['state']
                sleep(min(60,status['next_attempt_at']-clock()));continue
            status.pop('next_attempt_at',None)
            try:
                verify_frozen(root,manifest)
                pending=[b for b in manifest['batches'] if not (root/b['folder']/'result.json').exists()]
                if not pending:
                    consolidate(root,manifest)
                    update('complete');atomic(root/'completion_verification.json',dict(completed_at=stamp(),canonical_unchanged=True,protected=protected(manifest['project']),publication='disabled'));return 'complete'
                batch=pending[0];folder=root/batch['folder'];checkpoint=folder/'collection/checkpoint.json'
                if checkpoint.exists() and json.loads(checkpoint.read_text()).get('status')=='complete':
                    # A zero-request completed rerun repairs missing/stale derived CSV after a crash.
                    collect(folder/'cohort.csv',folder/'collection',credentials,search_mode='used_preferred',max_results=10,request_budget=400,delay=.5,progress=lambda _:None)
                    result=review_batch(folder)
                else:
                    quota=refresh_quota(credentials,root,ledger)
                    if not ledger.ready():
                        update('waiting_for_quota',next_attempt_at=parse_time(quota['reset'])+120,current_batch=batch['number'])
                        if once:return 'waiting_for_quota'
                        continue
                    update('collecting',current_batch=batch['number'])
                    def charged_request(request,timeout):ledger.charge();return default_request_json(request,timeout)
                    def factory(c,s,save,**kwargs):return PilotApi(c,s,save,request_json=charged_request,**kwargs)
                    def progress(message):
                        status['last_progress']=message;update('collecting');print(f'Batch {batch["number"]}: {message}',flush=True)
                    collect(folder/'cohort.csv',folder/'collection',credentials,search_mode='used_preferred',max_results=10,request_budget=400,delay=.5,api_factory=factory,progress=progress)
                    verify_frozen(root,manifest);result=review_batch(folder)
                verify_frozen(root,manifest)
                status['completed_batches']=batch['number'];status['completed_books']=status.get('completed_books',0)+result['books'];status['requests']=status.get('requests',0)+result['requests']
                consolidate(root,manifest)
                update('between_batches');failures=0
                if once:return 'batch_complete'
            except Exception as error:
                # Store only safe structured categories, never arbitrary exception text.
                code=getattr(error,'status_code',None);budget=False;errors=[]
                if 'folder' in locals() and (folder/'collection/checkpoint.json').exists():
                    cp=json.loads((folder/'collection/checkpoint.json').read_text());budget=cp['request_count']>=400
                    errors=[b.get('error',{}) for b in cp['books'].values() if b.get('error')]
                    if errors:code=errors[-1].get('http_status',code)
                error_kind=errors[-1].get('type') if 'errors' in locals() and errors else type(error).__name__
                transient=isinstance(error,(RuntimeError,EbayRequestError)) and error_kind in {'EbayRequestError','QuotaPause','RuntimeError'} and not budget and code not in {401,403}
                failures+=1
                if transient and failures<=5:
                    update('retrying',error_type=type(error).__name__,http_status=code,next_attempt_at=clock()+min(1800,60*2**(failures-1)))
                    if once:return 'retrying'
                    continue
                issue='request_budget_exhausted' if budget else 'access_failure' if code in {401,403} else 'integrity_or_review_failure'
                update('critical_stop',issue=issue,error_type=type(error).__name__,http_status=code)
                atomic(root/'critical_stop.json',dict(at=stamp(),issue=issue,error_type=type(error).__name__,http_status=code));return 'critical_stop'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--project',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--previous-cohort',type=Path,action='append',required=True)
    p=sub.add_parser('run');p.add_argument('--root',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if args.command=='prepare':
        m=prepare(args.project,args.root,args.previous_cohort);print(json.dumps({k:m[k] for k in ('active_records','previously_reviewed','remaining_records')}))
    else:
        import certifi
        os.environ['SSL_CERT_FILE']=certifi.where()
        c=EbayCredentials.from_environment(json.loads(args.credentials.expanduser().read_text()));print(run(args.root,c,once=args.once))
