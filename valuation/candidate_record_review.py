"""Review saved pilot comparisons against existing records; no source writes."""
from collections import Counter,defaultdict
from decimal import Decimal
import csv
import hashlib
import html
import json
from pathlib import Path
import re
from statistics import median

from valuation.offline_valuation_review import isbn,binding,listing_key,read_csv
from valuation.live_valuation_pilot import condition_grade

VERSION='record-review-v1'
USED={'acceptable','good','very_good','like_new'}


def bounds(rows):
    groups=defaultdict(list)
    for r in rows:groups[r['currency']].append(Decimal(r['asking_price']))
    return {c:dict(count=len(v),low=format(min(v),'.2f'),high=format(max(v),'.2f')) for c,v in sorted(groups.items())}


def review_one(book,packet,rows,accepted_keys,note):
    target=isbn(book.get('isbn13') or book.get('isbn10',''))
    acquisitions=packet['acquisitions'];observations=packet['observations']
    purchases=[r['acquisition_id'] for r in acquisitions if target and isbn(r.get('isbn13') or r.get('isbn10',''))==target]
    scans=[r['inventory_observation_id'] for r in observations if target and isbn(r.get('normalized_isbn13') or r.get('normalized_isbn10',''))==target]
    unknown=[r['inventory_observation_id'] for r in observations if not isbn(r.get('normalized_isbn13') or r.get('normalized_isbn10',''))]
    identity=bool(target and purchases and scans)
    recorded_notes=[n.get('notes','') for n in packet.get('source_notes',[]) if n.get('notes')]
    copyright_years=sorted({int(y) for note in recorded_notes for y in re.findall(r'Copyright\s+(\d{4})',note,re.I)})
    results=[]
    for raw in rows:
        r=dict(raw);r['review_reasons']=[];r['review_disposition']='not_in_preliminary_candidates'
        if listing_key(r) not in accepted_keys:results.append(r);continue
        r['review_disposition']='retained_candidate'
        if not target:
            publisher=r.get('listing_publisher','').casefold()
            wanted=packet['catalog'].get('publisher','').casefold()
            if 'crown' in wanted and publisher and 'crown' not in publisher:
                r['review_disposition']='excluded_different_publisher';r['review_reasons'].append('Existing Libib publisher is Crown; the returned listing names another publisher.')
            elif copyright_years and re.search(r'\b(?:18|19|20)\d{2}\b',r.get('listing_year','')) and int(re.search(r'\b(?:18|19|20)\d{2}\b',r['listing_year'])[0])<min(copyright_years):
                r['review_disposition']='excluded_earlier_publication_claim';r['review_reasons'].append('The listing claims a publication year earlier than the copyright recorded in the existing source-page transcription.')
            else:
                r['review_disposition']='held_for_target_edition';r['review_reasons'].append('Target ISBN, physical binding or printing is still unconfirmed; matching title/publisher alone does not choose a copy-specific edition.')
            results.append(r);continue
        actual=isbn(r.get('listing_isbn13') or r.get('listing_isbn10',''))
        if not actual or actual!=target:
            r['review_disposition']='held_for_listing_identity';r['review_reasons'].append('Independently returned listing ISBN is missing or differs from the purchased/scanned target ISBN.')
        title_format=binding(r.get('listing_title',''));structured=binding(r.get('listing_binding',''))
        if title_format and structured and title_format!=structured:
            r['review_disposition']='held_metadata_conflict';r['review_reasons'].append('The listing title and structured binding disagree; neither is chosen as physical truth.')
        label=re.search(r'(?:[-–|]|\bcondition\s*:)\s*(Very Good|Like New|Acceptable|Good|Brand New)\b',r.get('listing_title',''),re.I)
        if label and condition_grade(label[1])!=r.get('listing_condition_grade','') and r.get('listing_condition_grade'):
            r['review_disposition']='held_metadata_conflict';r['review_reasons'].append('The listing title and structured condition disagree; omit this offer from the working comparison.')
        results.append(r)
    retained=[r for r in results if r['review_disposition']=='retained_candidate']
    # Working comparison holds, not assertions that a seller's price is wrong.
    same_grade=defaultdict(list)
    for r in retained:
        if r.get('listing_condition_grade') in USED:
            same_grade[(r['currency'],r.get('listing_binding',''),r['listing_condition_grade'])].append(r)
    for group in same_grade.values():
        if len(group)<4:continue
        high=max(group,key=lambda r:Decimal(r['asking_price']));others=[r for r in group if r is not high]
        values=[Decimal(r['asking_price']) for r in others]
        if min(values)>0 and max(values)/min(values)<=Decimal('1.5') and Decimal(high['asking_price'])>3*median(values):
            high['review_disposition']='held_high_outlier';high['review_reasons'].append('Three or more same-format/grade offers form a tight lower cluster; hold this >3× cluster-median asking price for review, without deleting it.')
    for r in retained:
        if r['review_disposition']!='retained_candidate' or r.get('listing_condition_grade') not in USED:continue
        cheaper=[n for n in retained if n.get('listing_condition_grade')=='new' and n['currency']==r['currency'] and Decimal(n['asking_price'])<Decimal(r['asking_price']) and (not n.get('listing_binding') or not r.get('listing_binding') or n['listing_binding']==r['listing_binding'])]
        if len({listing_key(n) for n in cheaper})>=2 and Decimal(r['asking_price'])>Decimal('1.25')*min(Decimal(n['asking_price']) for n in cheaper):
            r['review_disposition']='held_above_new_context';r['review_reasons'].append('Used asking price exceeds at least two compatible-ISBN new-copy item prices and is >25% above the lowest. Hold as weak working evidence; shipping and delivered costs have not been compared.')
    working=[r for r in results if r['review_disposition']=='retained_candidate']
    used=[r for r in working if r.get('listing_condition_grade') in USED]
    new=[r for r in working if r.get('listing_condition_grade')=='new']
    groups={}
    for grade in sorted({r.get('listing_condition_grade','') for r in used}):groups[grade]=bounds([r for r in used if r.get('listing_condition_grade')==grade])
    recorded_publishers=sorted({r.get('raw_publisher','') for r in observations if r.get('raw_publisher')})
    formats=Counter(r['listing_binding'] for r in working if r.get('listing_binding'))
    binding_inference=next(iter(formats)) if len(formats)==1 else ''
    physical=[]
    if not identity:
        question=('Existing source notes already establish copyright '+', '.join(map(str,copyright_years))+'. Confirm the actual binding and printing statement; note any ISBN and the jacket/condition. Do not assume copyright year is the printing date.' if copyright_years else 'Read the title/copyright pages: publisher, year/printing, binding, translator/editor and any ISBN. Photograph those pages if convenient. For an older hardcover, note the dust jacket.')
        physical.append(dict(kind='edition',priority='before any book-specific estimate',question=question,required=True))
    inferred_locations=sorted({o.get('source_collection_label','').removeprefix('Box ') for o in observations if o.get('inventory_observation_id') in unknown and o.get('source_collection_label')})
    if target and unknown:physical.append(dict(location=', '.join(inferred_locations) or book.get('location',''),kind='inferred_copy_identity',priority='before copy-specific sale or estimate',question='One linked physical observation has no recorded ISBN. Preserve the existing medium-confidence link; check that copy’s ISBN/edition when it is handled.',required=False,observation_ids=unknown))
    physical.append(dict(kind='condition',priority='when handling the book or before a copy-specific estimate',question='For each copy, note binding, jacket if applicable, highlighting/notes, loose pages, damage and an honest condition grade. Existing records do not establish the current physical grade.',required=False))
    research=[]
    if not identity:research.append('Resolve the physical edition check before further market research; keep the Crown-labelled possibilities separate.')
    elif not used:research.append('Further market research: no retained ordinary-used comparison. New-copy offers are context, not evidence of your copy’s condition or sale proceeds.')
    elif len(used)<3:research.append('Further market research: fewer than three retained used offers; keep the comparison thin rather than assigning the work to the owner.')
    else:research.append('Used comparisons are available by grade. Target physical condition remains unrecorded; keep grade scenarios explicit rather than silently assuming a grade.')
    return dict(catalog_item_id=book['catalog_item_id'],title=book['title'],location=book.get('location',''),note=note,
                identity_supported_from_records=identity,identity_evidence=dict(target_isbn=target,acquisition_ids=purchases,scanned_observation_ids=scans),
                inferred_copy_observation_ids=unknown if target else [],recorded_publishers=recorded_publishers,recorded_source_notes=recorded_notes,recorded_copyright_years=copyright_years,
                edition_binding_inference=dict(value=binding_inference,source_listing_counts=dict(formats),physical_verification=False),
                saved_range=dict(low=book.get('previous_low',''),high=book.get('previous_high',''),currency=book.get('currency','')),
                retained_used_context=bounds(used),retained_used_by_grade=groups,new_copy_context=bounds(new),
                listing_decisions=results,physical_checks=physical,research_next_steps=research,
                publishable=False,condition_assumed=False)


def run_review(packet_path,notes_path,preliminary_path,observations_path,output_dir,*,condition_policy_path=None):
    paths=list(map(Path,(packet_path,notes_path,preliminary_path,observations_path)))
    policy=json.loads(Path(condition_policy_path).read_text()) if condition_policy_path else None
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if condition_policy_path:hashes[str(Path(condition_policy_path))]=hashlib.sha256(Path(condition_policy_path).read_bytes()).hexdigest()
    packet,notes,prelim=[json.loads(p.read_text()) for p in paths[:3]];rows=read_csv(paths[3])
    expected=[v for k,v in prelim.get('summary',{}).get('input_hashes',{}).items() if Path(k).name==paths[3].name]
    if expected and (len(expected)!=1 or expected[0]!=hashes[str(paths[3])]):raise ValueError('Observations differ from the reviewed pilot evidence')
    candidates=[v for v in prelim['books'] if any(s['candidate_ranges'] for s in v['review']['sources'].values())]
    ids={v['book']['catalog_item_id'] for v in candidates}
    if set(packet)!=ids or set(notes)!=ids:raise ValueError('Evidence packet and authored notes must cover exactly the candidate cohort')
    if condition_policy_path and (not isinstance(policy,dict) or policy.get('mode')!='labelled_used_scenarios' or policy.get('physical_grading')!='defer_until_handled' or policy.get('publication')!='disabled' or policy.get('default_grade') is not None or set(policy.get('catalog_item_ids',[]))!=ids):
        raise ValueError('Condition policy must explicitly cover this cohort, defer grading, and forbid publication')
    out=Path(output_dir)
    if out.exists() or 'data' in out.resolve().parts:raise ValueError('Use a new private report directory outside canonical data')
    reviews=[]
    for v in candidates:
        b=v['book'];cid=b['catalog_item_id']
        if packet[cid]['catalog']['catalog_item_id']!=cid:raise ValueError('Catalog identity mismatch in packet')
        if isbn(packet[cid]['catalog'].get('isbn13') or packet[cid]['catalog'].get('isbn10',''))!=isbn(b.get('isbn13') or b.get('isbn10','')):raise ValueError('Target edition changed since pilot')
        keys={d['listing'] for d in v['review']['decisions'] if d['disposition'] in {'candidate_only','verified_comparable'}}
        reviews.append(review_one(b,packet[cid],[r for r in rows if r['catalog_id']==cid],keys,notes[cid]))
        if policy:
            item=reviews[-1];item['actual_condition']='ungraded';item['condition_policy']='labelled_used_scenarios'
            item['condition_scenarios']=[dict(hypothetical_grade=grade,currency=currency,low=g['low'],high=g['high'],listing_count=g['count'],evidence_label=('limited evidence' if g['count']<3 else 'wide price spread; further review needed' if Decimal(g['high'])>=3*Decimal(g['low']) else 'three or more offers; comparability still requires review'),high_spread=Decimal(g['high'])>=3*Decimal(g['low']),scenario_only=True,publishable=False) for grade,groups in item['retained_used_by_grade'].items() for currency,g in groups.items()]
            for check in item['physical_checks']:
                if check['kind']=='condition':check.update(status='deferred_until_handled',priority='when you handle the copies')
            if item['identity_supported_from_records'] and item['condition_scenarios']:
                item['research_next_steps']=[step for step in item['research_next_steps'] if not step.startswith('Used comparisons are available by grade.')]
                item['research_next_steps'].append('Use the clearly labelled condition scenarios for review now. Grade each actual copy when it is handled; no scenario assigns its present condition.')
    summary=dict(reviewed_books=len(reviews),identity_supported=sum(r['identity_supported_from_records'] for r in reviews),edition_checks=sum(any(p['kind']=='edition' for p in r['physical_checks']) for r in reviews),inferred_copy_checks=sum(bool(r['inferred_copy_observation_ids']) for r in reviews),books_with_retained_used_context=sum(bool(r['retained_used_context']) for r in reviews),books_without_used_context=sum(not r['retained_used_context'] for r in reviews),books_with_three_used_offers=sum(any(g['count']>=3 for g in r['retained_used_context'].values()) for r in reviews),books_with_three_same_grade_offers=sum(any(g['count']>=3 for grades in r['retained_used_by_grade'].values() for g in grades.values()) for r in reviews),listing_decisions=dict(Counter(d['review_disposition'] for r in reviews for d in r['listing_decisions'])),estimates_changed=0,source_requests=0)
    if policy:
        summary.update(condition_scenarios=sum(len(r['condition_scenarios']) for r in reviews),condition_checks_deferred=sum(c.get('status')=='deferred_until_handled' for r in reviews for c in r['physical_checks']))
    assert hashes=={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in hashes}
    out.mkdir(parents=True,mode=0o700)
    def save(name,content):p=out/name;p.write_text(content,encoding='utf-8');p.chmod(0o600)
    save('review.json',json.dumps(dict(version=VERSION,input_hashes=hashes,summary=summary,condition_policy=policy,owner_policy_status='applied' if policy else 'pending',owner_policy_question=None if policy else 'Should ungraded books be shown under explicit used-condition scenarios, or remain without a copy-specific range until condition is checked? No default grade has been assumed.',reviews=reviews),indent=2)+'\n')
    checks=[]
    for r in reviews:
        for c in r['physical_checks']:checks.append(dict(catalog_item_id=r['catalog_item_id'],title=r['title'],location=c.get('location',r['location']),kind=c['kind'],priority=c['priority'],question=c['question'],required_before_any_estimate=c['required'],status=c.get('status','open')))
    with (out/'physical_checks.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader()
        for c in sorted(checks,key=lambda c:(not c['required_before_any_estimate'],c['location'],c['title'])):w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in c.items()})
    (out/'physical_checks.csv').chmod(0o600)
    if policy:
        fields=['catalog_item_id','title','hypothetical_grade','currency','low','high','listing_count','evidence_label','actual_condition','high_spread','scenario_only','publishable']
        with (out/'condition_scenarios.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for item in reviews:
                for scenario in item['condition_scenarios']:
                    row=dict(catalog_item_id=item['catalog_item_id'],title=item['title'],actual_condition='ungraded',**scenario)
                    w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()})
        (out/'condition_scenarios.csv').chmod(0o600)
    def esc(v):return html.escape(str(v))
    def display(groups):return '; '.join(f"{c} {g['low']}–{g['high']} ({g['count']} offers)" for c,g in groups.items()) or 'No retained used comparison'
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Candidate record review</title><style>body{font:17px system-ui;color:#243c33;max-width:1150px;margin:32px auto;padding:20px}h1,h2{color:#215a45}p,li{line-height:1.5}details{border:1px solid #ccd6d0;padding:16px;margin:12px 0;border-radius:8px}summary{font-weight:bold;cursor:pointer}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #ddd}.notice{padding:16px;background:#fff4d7}.scroll{overflow:auto}</style><h1>Candidate comparisons reviewed against your records</h1><p class="notice">Review only. No Library estimates, source records or existing Action Item statuses have been changed. Source listings and earlier pilot reports are preserved.</p>']
    parts.append('<p>'+esc(f"{summary['reviewed_books']} comparisons reviewed; {summary['identity_supported']} ISBN identities supported by purchase and inventory records. {summary['edition_checks']} edition check requires the book. Used and new offers are separated; held prices remain evidence, not corrections to a seller’s listing.")+'</p>')
    if policy:
        parts.append('<h2>Your condition policy is applied</h2><p>Use clearly labelled used-condition scenarios for review now. Actual copies remain ungraded; physical grading is deferred until you handle them. No default grade is selected and estimates remain unchanged.</p><p><a href="condition_scenarios.csv">Download condition scenarios</a> · <a href="physical_checks.csv">Download deferred physical-check checklist</a></p>')
    else:
        parts.append('<h2>Your one policy decision</h2><p>May ungraded books be compared under clearly labelled used-condition scenarios, or should a copy-specific range wait until its condition is checked? No condition grade is currently assumed. This decision does not authorize publication.</p>')
    parts.append('<h2>Priority physical edition checks</h2>')
    for r in reviews:
        for c in r['physical_checks']:
            if c['kind'] in {'edition','inferred_copy_identity'}:parts.append('<p><b>'+esc(r['title'])+'</b> · Location '+esc(c.get('location',r['location']))+' · '+esc(c['priority'])+'<br>'+esc(c['question'])+'</p>')
    parts.append('<h2>Condition checks, when you handle the copies</h2><p>Current condition is not established for these 26 books. Record it when retrieving a book or before a copy-specific estimate/sale; these are not 26 urgent edition investigations. The downloadable checklist keeps condition checks separate from edition questions and market research.</p><h2>All 26 reviewed comparisons</h2>')
    for r in reviews:
        parts.append('<details><summary>'+esc(r['title'])+'</summary><p>Location: '+esc(r['location'])+'</p><p>'+esc(r['note'])+'</p><p>Identity from existing records: '+('supported by purchased and scanned ISBN' if r['identity_supported_from_records'] else 'edition still unresolved')+'.</p>')
        parts.append('<p>Recorded inventory publisher: '+esc('; '.join(r['recorded_publishers']))+'</p>')
        if policy:
            parts.append('<h3>Used-condition scenarios · your copy is ungraded</h3>')
            if not r['condition_scenarios']:parts.append('<p>No retained used evidence supports a scenario. New-copy prices are shown separately as context; no used price is invented.</p>')
            for scenario in r['condition_scenarios']:
                parts.append('<p><b>If your copy is '+esc(scenario['hypothetical_grade'].replace('_',' '))+':</b> '+esc(scenario['currency']+' '+scenario['low']+'–'+scenario['high'])+' in asking-price evidence ('+esc(scenario['listing_count'])+' offers; '+esc(scenario['evidence_label'])+'). This is not an assigned condition or an approved estimate.</p>')
        else:
            parts.append('<p>Retained used asking-price context: '+esc(display(r['retained_used_context']))+'</p>')
            for grade,values in r['retained_used_by_grade'].items():parts.append('<p>'+esc(grade.replace('_',' ')+': '+display(values))+'</p>')
        parts.append('<p>New-copy context: '+esc(display(r['new_copy_context']).replace('No retained used comparison','No new-copy context'))+'</p>')
        if r['edition_binding_inference']['value']:parts.append('<p>Listing metadata suggests '+esc(r['edition_binding_inference']['value'])+' for this ISBN; the physical copy has not been inspected.</p>')
        parts.append('<ul>'+''.join('<li>'+esc(x)+'</li>' for x in r['research_next_steps'])+'</ul><div class="scroll"><table><thead><tr><th>Saved listing</th><th>Price / condition</th><th>Review decision</th></tr></thead><tbody>')
        for d in r['listing_decisions']:
            if d['review_disposition']=='not_in_preliminary_candidates':continue
            parts.append('<tr><td>'+esc(d.get('listing_title',''))+'<br>'+esc(d.get('raw_reference',''))+'</td><td>'+esc(d.get('currency','')+' '+d.get('asking_price','')+' / '+d.get('condition',''))+'</td><td>'+esc(d['review_disposition'].replace('_',' '))+'<br>'+esc(' '.join(d['review_reasons']))+'</td></tr>')
        parts.append('</tbody></table></div></details>')
    save('review.html',''.join(parts)+'</html>')
    return summary
