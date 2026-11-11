"""Frozen 100-book test planning and auditable bounded collection workers.

Production records are read by the caller; this module writes private artifacts only.
"""
import hashlib
import json
from pathlib import Path
from valuation.live_valuation_pilot import PilotApi, atomic, collect
from valuation.offline_valuation_review import isbn

SEED='valuation-scale-100-v1'
GROUPS=[('missing_isbn',10),('multiple_copies',15),('edition_flags',15),('uncertain_prices',10),('usable_low',10),('usable_mid',10),('usable_high',5),('missing_or_weak',25)]


def select_cohort(records, excluded_ids=()):
    """Deterministic coverage sample, deliberately not a population estimate."""
    excluded=set(excluded_ids);available=[dict(r) for r in records if r['catalog_item_id'] not in excluded]
    ids=[r['catalog_item_id'] for r in available]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate catalog identity')
    available.sort(key=lambda r:hashlib.sha256((SEED+r['catalog_item_id']).encode()).hexdigest())
    def qualifies(r,group):
        has_isbn=bool(isbn(r.get('isbn13') or r.get('isbn10','')))
        confidence=r.get('previous_confidence','')
        if group=='missing_isbn':return not has_isbn
        if not has_isbn:return False
        if group=='multiple_copies':return int(r.get('copy_count',1))>1
        if group=='edition_flags':return confidence=='ambiguous_edition_match' or r.get('edition_flag',False)
        if group=='uncertain_prices':return confidence=='unknown_market_confidence'
        if group=='missing_or_weak':return not r.get('usable_market_estimate',False)
        if not r.get('usable_market_estimate') or r.get('currency')!='USD':return False
        upper=float(r.get('previous_high') or 0)
        return (upper<20 if group=='usable_low' else 20<=upper<75 if group=='usable_mid' else upper>=75)
    chosen=set();groups=[]
    for group,n in GROUPS:
        pool=[r for r in available if r['catalog_item_id'] not in chosen and qualifies(r,group)][:n]
        if len(pool)!=n:raise ValueError(f'Insufficient records for {group}: {len(pool)}/{n}')
        for r in pool:r['group']=group;chosen.add(r['catalog_item_id'])
        groups.append(pool)
    # Interleave strata so every sequential batch exercises varied book types.
    result=[rows[i] for i in range(max(map(len,groups))) for rows in groups if i<len(rows)]
    assert len(result)==100 and len(chosen)==100
    return result


def run_worker(pilot, output, credentials, *, phase, progress=print, delay=1.0):
    """No credentials/URLs in request journal; checkpoints remain the resume authority."""
    output=Path(output)
    class JournalApi(PilotApi):
        def event(self,operation,item_id=None):
            current=next(cid for cid in self.state['manifest']['catalog_ids'] if not self.state['books'].get(cid,{}).get('completed'))
            p=output/'request_events.json'
            events=json.loads(p.read_text()) if p.exists() else []
            events.append(dict(phase=phase,operation=operation,catalog_item_id=current,item_id=item_id))
            atomic(p,events)
        def search(self,book,limit):self.event('search');return super().search(book,limit)
        def detail(self,item_id):self.event('detail',item_id);return super().detail(item_id)
    return collect(pilot,output,credentials,search_mode='used_preferred',max_results=10,
                   request_budget=400,delay=delay,api_factory=JournalApi,progress=progress)


def verify_recovery(paused, resumed, events):
    """Verify durable work survived and resumed worker did not repeat it."""
    if resumed.get('status')!='complete':raise ValueError('Resume is incomplete')
    if paused['manifest']!=resumed['manifest']:raise ValueError('Resume configuration changed')
    if resumed['request_count']<paused['request_count']:raise ValueError('Request count went backwards')
    completed={cid for cid,b in paused['books'].items() if b.get('completed')}
    partial={cid for cid,b in paused['books'].items() if not b.get('completed') and 'search' in b}
    if not completed or not partial:raise ValueError('Recovery evidence needs completed and partially processed books')
    for cid,b in paused['books'].items():
        for item,row in b.get('details',{}).items():
            if resumed['books'][cid]['details'].get(item)!=row:raise ValueError('Persisted detail changed during recovery')
        if cid in completed and resumed['books'][cid]!=b:raise ValueError('Completed book changed during recovery')
    for event in events:
        if event['phase']!='after_interruption':continue
        cid=event['catalog_item_id'];before=paused['books'].get(cid,{})
        if cid in completed:raise ValueError('Completed book was requested again')
        if event['operation']=='search' and 'search' in before:raise ValueError('Saved search was repeated')
        if event['operation']=='detail' and event['item_id'] in before.get('details',{}):raise ValueError('Saved detail was repeated')
    return dict(persisted_details_unchanged=True,completed_books_not_repeated=True,saved_searches_not_repeated=True,
                saved_details_not_repeated=True,status='passed')


def build_scale_report(root, *, as_of, packet_name='record_packet.json', notes_name='review_notes.json'):
    """Validate all four collected batches, then build an isolated 100-book review."""
    from collections import Counter
    from valuation.live_valuation_pilot import FIELDS
    from valuation.offline_valuation_review import read_csv
    from valuation.pilot_followup import merge_observations
    from valuation.live_pilot_report import report
    from valuation.candidate_record_review import run_review
    root=Path(root).resolve()
    if 'data' in root.parts:raise ValueError('Use a private output directory')
    if any((root/name).exists() for name in ('review','preliminary_review','aggregate_checkpoint.json','merged_observations.csv','results.json')):raise ValueError('Prior report artifacts exist; preserve them and choose a fresh report run')
    manifest=json.loads((root/'manifest.json').read_text());cohort=root/'cohort.csv';books=read_csv(cohort)
    if hashlib.sha256(cohort.read_bytes()).hexdigest()!=manifest['cohort_sha256']:raise ValueError('Frozen cohort changed')
    ids=[b['catalog_item_id'] for b in books]
    if len(ids)!=100 or len(set(ids))!=100:raise ValueError('Scale test requires exactly 100 distinct books')
    states=[];paths=[];book_states={};total=0
    for n in range(1,5):
        pilot=root/f'batch_{n}.csv';checkpoint=root/f'collection_{n}/checkpoint.json'
        state=json.loads(checkpoint.read_text());expected=ids[(n-1)*25:n*25]
        if state['manifest']['pilot_sha256']!=hashlib.sha256(pilot.read_bytes()).hexdigest() or state['manifest']['catalog_ids']!=expected:raise ValueError('Batch differs from frozen cohort')
        if read_csv(pilot)!=books[(n-1)*25:n*25]:raise ValueError('Batch metadata differs from frozen cohort')
        if set(state['books'])!=set(expected):raise ValueError('Unexpected book in checkpoint')
        if state['status']!='complete' or not all(state['books'].get(cid,{}).get('completed') for cid in expected):raise ValueError('Batch is incomplete')
        if state['manifest']['request_budget']!=400 or state['request_count']>400:raise ValueError('Batch request ceiling violated')
        if state['manifest'].get('search_mode')!='used_preferred':raise ValueError('Unexpected batch search mode')
        expected_rows=[]
        for cid in expected:
            entry=state['books'][cid];expected_rows.extend(entry.get('details',{}).values())
            if not entry.get('search',{}).get('item_ids'):
                row=dict.fromkeys(FIELDS,'');row.update(catalog_id=cid,source='ebay_active_listings',lookup_status='no_results',observation_date=state['started_at'],detail_status='no_results');expected_rows.append(row)
        observed=read_csv(root/f'collection_{n}/observations.csv')
        signature=lambda row:json.dumps(row,sort_keys=True)
        if Counter(map(signature,expected_rows))!=Counter(map(signature,observed)):raise ValueError('Observations differ from durable checkpoint')
        states.append(state);book_states.update(state['books']);total+=state['request_count']
        paths.append(root/f'collection_{n}/observations.csv')
    if total>1600:raise ValueError('Scale request ceiling violated')
    first=json.loads((root/'interrupted_checkpoint.json').read_text())
    events=json.loads((root/'collection_1/request_events.json').read_text())
    recovery=verify_recovery(first,states[0],events)
    combined=dict(manifest=dict(pilot_sha256=manifest['cohort_sha256'],catalog_ids=ids,
                  derived_from={str(root/f'collection_{n}/checkpoint.json'):hashlib.sha256((root/f'collection_{n}/checkpoint.json').read_bytes()).hexdigest() for n in range(1,5)}),
                  status='complete',request_count=total,books=book_states)
    aggregate=root/'aggregate_checkpoint.json';atomic(aggregate,combined)
    merged=root/'merged_observations.csv';receipt=merge_observations(paths,merged)
    prelim=report(cohort,merged,aggregate,root/'preliminary_review',as_of=as_of)
    summary=run_review(root/packet_name,root/notes_name,root/'preliminary_review/review.json',merged,root/'review',condition_policy_path=root/'condition_policy.json',include_all_books=True)
    reviews=json.loads((root/'review/review.json').read_text())['reviews']
    scenario_count=sum(len(r['condition_scenarios']) for r in reviews)
    supported=sum(s['listing_count']>=3 and not s['high_spread'] and s['listing_binding']!='unknown' for r in reviews for s in r['condition_scenarios'])
    inputs=[cohort,root/'manifest.json',root/packet_name,root/notes_name,root/'condition_policy.json',root/'interrupted_checkpoint.json',root/'collection_1/request_events.json',*paths,*[root/f'collection_{n}/checkpoint.json' for n in range(1,5)]]
    fingerprints={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    code_root=Path(__file__).parent
    rule_fingerprints={name:hashlib.sha256((code_root/name).read_bytes()).hexdigest() for name in ('valuation_scale_test.py','candidate_record_review.py','offline_valuation_review.py','live_valuation_pilot.py','live_pilot_report.py','pilot_followup.py')}
    metrics=dict(version='scale-test-100-v1',rule_fingerprints=rule_fingerprints,input_hashes=fingerprints,selected_books=100,groups=dict(Counter(b['group'] for b in books)),collection=prelim,record_review=summary,
                 recovery=recovery,merge=receipt,condition_scenarios=scenario_count,three_offer_known_binding_narrow_scenarios=supported,
                 estimates_changed=0,physical_grading='deferred',publication='disabled',request_ceiling=1600)
    atomic(root/'results.json',metrics)
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>100-book valuation test</title><style>body{font:18px system-ui;max-width:1050px;margin:40px auto;padding:20px;color:#243c33}h1,a{color:#215a45}li,p{line-height:1.6}.notice{background:#fff4d7;padding:16px}</style><h1>100-book valuation test</h1><p class="notice">Review only. Current Library estimates and saved decisions remain unchanged. Actual copies remain ungraded; physical grading is deferred.</p>'
    page+=f'<p>All 100 additional books collected in four batches. {total} requests against a 1,600-request ceiling. Recovery passed: persisted details and saved searches were not repeated.</p>'
    page+=f'<p>{summary["books_with_retained_used_context"]} books have retained used-copy evidence, with {scenario_count} separate binding/condition/currency scenarios. {supported} scenarios have at least three distinct listings, known seller-reported binding, and a highest/lowest ratio below three. These are asking prices, not approved estimates or sale proceeds. Listing counts do not establish independent sellers.</p>'
    page+='<p>This is a deliberate coverage sample, not a random sample from which to estimate whole-library coverage. Missing ISBNs, conflicting metadata, thin evidence and unknown bindings stay flagged. The used-only search does not establish a fresh new-copy price ceiling.</p><ul><li><a href="review/review.html">Review all 100 books and evidence decisions</a></li><li><a href="review/condition_scenarios.csv">Download condition scenarios</a></li><li><a href="review/physical_checks.csv">Download deferred grading and edition checks</a></li><li><a href="preliminary_review/comparison.csv">Compare saved ranges with collected evidence</a></li><li><a href="results.json">Inspect test results and fingerprints</a></li></ul></html>'
    (root/'index.html').write_text(page);(root/'index.html').chmod(0o600)
    return metrics
