"""Render an authored records-only adjudication outside a frozen valuation job.

Closing an identification task does not verify a copy ISBN, assign a condition,
change a work link, or authorize an estimate. No network or repository writer.
"""
from collections import Counter
import csv
import hashlib
import html
import json
from pathlib import Path
import re

from valuation.offline_valuation_review import isbn
from valuation.live_valuation_pilot import atomic

OUTCOMES={'records_sufficient','requires_binding_check','requires_identifier_check'}


def compact(value):return re.sub(r'[^a-z0-9]','',value.casefold())


def validate_alternative(choice,source_notes):
    printed=choice['printed']
    if not any(compact(printed) in compact(note) for note in source_notes):
        raise ValueError('Identifier alternative is absent from recorded source notes')
    value=choice.get('candidate_isbn10',printed)
    normalized=isbn(value)
    if not normalized:raise ValueError('Invalid identifier cannot be promoted to a candidate')
    if choice.get('candidate_isbn10'):
        digits=re.sub(r'[^0-9Xx]','',printed).upper()
        if value!=digits and not (len(digits)==9 and value=='0'+digits):
            raise ValueError('Candidate transformation may not repair or replace printed digits')
    return dict(**choice,normalized_candidate_isbn13=normalized,assigned_to_copy=False,
                basis='Recorded alternative; optional leading-zero equivalent checksum-validated, not assigned to the physical copy')


def adjudicate(packet_path,findings_path,output_dir):
    packet_path,findings_path=map(Path,(packet_path,findings_path));out=Path(output_dir).resolve()
    if 'data' in out.parts or out.exists():raise ValueError('Choose a new private output directory outside canonical data')
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (packet_path,findings_path)}
    packet=json.loads(packet_path.read_text());findings=json.loads(findings_path.read_text())
    checks=packet['checks'];ids={c['catalog_item_id'] for c in checks}
    if set(findings)!=ids or set(packet['books'])!=ids or set(packet['packets'])!=ids:
        raise ValueError('Authored findings must cover exactly the frozen check cohort')
    keys=[(c['catalog_item_id'],c['kind']) for c in checks]
    if len(keys)!=len(set(keys)) or any(kind not in {'edition','inferred_copy_identity'} for _,kind in keys):
        raise ValueError('Unexpected or duplicate check scope')
    if any((cid,'edition') not in keys for cid in ids):raise ValueError('Missing edition task for reviewed book')
    books=[];decisions=[];physical=[]
    for cid in sorted(ids):
        finding=findings[cid];p=packet['packets'][cid];old=packet['books'][cid]
        if finding.get('outcome') not in OUTCOMES or not finding.get('finding'):
            raise ValueError('Every book requires an explicit authored outcome and reasoning')
        source_notes=[n['notes'] for n in p.get('source_notes',[]) if n.get('notes')]
        if not source_notes:raise ValueError('Records-only decisions require preserved source-page evidence')
        needed=finding['outcome']!='records_sufficient'
        if needed and not finding.get('physical_question'):raise ValueError('Unresolved book requires one precise physical question')
        if not needed and finding.get('physical_question'):raise ValueError('Resolved task cannot still require book handling')
        invalid=finding.get('recorded_invalid_identifier')
        if invalid and (isbn(invalid) or finding['outcome']!='requires_identifier_check' or not any(compact(invalid) in compact(note) for note in source_notes)):
            raise ValueError('An unresolved invalid identifier must remain a physical identifier check')
        alternatives=[validate_alternative(a,source_notes) for a in finding.get('alternatives',[])]
        title=next((o.get('raw_title') for o in p['observations'] if o.get('raw_title')),old['title'])
        base=dict(catalog_item_id=cid,title=title,location=old['location'])
        item=dict(base);item.update(finding)
        item.update(alternatives=alternatives,source_notes=source_notes,
                  observation_ids=[o['inventory_observation_id'] for o in p['observations']],
                  identification_scope='documented source-edition profile; no catalog ISBN assignment',
                  actual_condition='ungraded',physical_copy_isbn_verified=False,
                  existing_work_link='preserved without upgrading confidence',estimates_changed=0,
                  publishable=False,canonical_updates=False)
        books.append(item)
        for check in [c for c in checks if c['catalog_item_id']==cid]:
            outcome=('physical_check_required' if check['kind']=='edition' else 'merged_with_book_check') if needed else 'resolved_from_records'
            decisions.append(dict(**base,original_kind=check['kind'],outcome=outcome,
                                  reasoning=finding['finding'],original_check=check,review_only=True))
        if needed:
            physical.append(dict(**base,kind=finding['outcome'],question=finding['physical_question'],
                                 known_facts=finding['finding'],status='deferred_until_handled',
                                 actual_condition='ungraded',copy_isbn_assigned=False))
    summary=dict(original_checks=len(checks),reviewed_books=len(books),
                 original_edition_checks=sum(c['kind']=='edition' for c in checks),
                 original_inferred_copy_checks=sum(c['kind']=='inferred_copy_identity' for c in checks),
                 edition_checks_resolved=sum(d['original_kind']=='edition' and d['outcome']=='resolved_from_records' for d in decisions),
                 inferred_checks_resolved=sum(d['original_kind']=='inferred_copy_identity' and d['outcome']=='resolved_from_records' for d in decisions),
                 inferred_checks_merged=sum(d['outcome']=='merged_with_book_check' for d in decisions),
                 remaining_physical_tasks=len(physical),remaining_types=dict(Counter(c['kind'] for c in physical)),
                 estimates_changed=0,canonical_updates=0,source_requests=0,physical_grading='deferred',publication='disabled')
    assert hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (packet_path,findings_path)}
    out.mkdir(parents=True,mode=0o700)
    atomic(out/'adjudications.json',dict(version='edition-adjudication-v1',input_hashes=hashes,summary=summary,decisions=decisions,books=books))
    def sort_key(row):
        m=re.match(r'\d+',row['location']);return (int(m[0]) if m else 9999,row['location'],row['title'])
    physical.sort(key=sort_key)
    fields=['catalog_item_id','title','location','kind','question','known_facts','status','actual_condition','copy_isbn_assigned']
    with (out/'physical_checks_only.csv').open('w',newline='') as f:
        (out/'physical_checks_only.csv').chmod(0o600);w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in physical:w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()})
    esc=lambda value:html.escape(str(value))
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Edition checks reviewed</title><style>body{font:17px system-ui;max-width:1150px;margin:35px auto;padding:20px;color:#243c33}h1,h2,a{color:#215a45}p,li{line-height:1.6}table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid #ccd6d0}details{border:1px solid #ccd6d0;padding:15px;margin:12px 0;border-radius:8px}.notice{background:#fff4d7;padding:18px}.scroll{overflow:auto}</style><h1>Edition checks reviewed against existing records</h1>'
    page+='<p class="notice">Review only. Estimates, catalog records, work links and the frozen batch job are unchanged. Actual copies remain ungraded. An identified source edition is not a verified copy ISBN or an approved valuation.</p>'
    page+='<p>'+esc(f"{len(checks)} flags cover {len(books)} books. {summary['edition_checks_resolved']} edition questions and {summary['inferred_checks_resolved']} inferred-copy questions are resolved from records; {summary['inferred_checks_merged']} duplicate inferred-copy questions are merged into their books’ remaining physical questions. {len(physical)} focused tasks remain.")+'</p>'
    page+='<p>No immediate response is needed. Check these only when you handle the books or before a copy-specific estimate. Routine grading stays deferred separately. The original frozen reports retain their raw flags; this sidecar is the reviewed checklist for this exact cohort.</p><p><a href="physical_checks_only.csv">Download only the remaining physical checks</a> · <a href="adjudications.json">Inspect all decisions and evidence</a></p><h2>Only questions requiring the books</h2><div class="scroll"><table><tr><th>Location</th><th>Book</th><th>What to check</th></tr>'
    for row in physical:page+='<tr><td>'+esc(row['location'])+'</td><td>'+esc(row['title'])+'</td><td>'+esc(row['question'])+'</td></tr>'
    page+='</table></div><h2>Evidence and decisions for every book</h2>'
    for book in sorted(books,key=sort_key):
        page+='<details><summary>'+esc(book['title'])+' · '+esc(book['location'])+'</summary><p>'+esc(book['outcome'].replace('_',' '))+'. '+esc(book['finding'])+'</p>'
        if book.get('agent_followup'):page+='<p>Further work from records: '+esc(book['agent_followup'])+'</p>'
        for note in book['source_notes']:page+='<p>Existing source-page note: '+esc(note)+'</p>'
        for a in book['alternatives']:page+='<p>Recorded alternative: '+esc(a['printed'])+' ('+esc(a['label'])+'); checksum-valid ISBN-13 candidate '+esc(a['normalized_candidate_isbn13'])+'. Not assigned to your copy.</p>'
        page+='</details>'
    page+='</html>';p=out/'review.html';p.write_text(page);p.chmod(0o600)
    return summary
