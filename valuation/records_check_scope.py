"""Pre-review records-dependent identification flags across a frozen batch plan.

Only identification checks are predicted. Market prices/results are not predicted,
and a plan is not a claim that source collection or valuation is complete.
"""
import csv
import hashlib
import json
from pathlib import Path

from valuation.candidate_record_review import review_one
from valuation.live_valuation_pilot import atomic
from valuation.offline_valuation_review import read_csv
from valuation.whole_library_review import verify_frozen


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identification_checks(book):
    rows=[]
    for check in book['physical_checks']:
        if check['kind'] not in {'edition','inferred_copy_identity'}:continue
        row=dict(catalog_item_id=book['catalog_item_id'],title=book['title'],location=book['location']);row.update(check);rows.append(row)
    return rows


def signature(check):
    return json.dumps({k:check.get(k) for k in ('catalog_item_id','title','location','kind','priority','question','required','observation_ids')},sort_keys=True)


def prepare_scope(job_root,output_dir):
    job=Path(job_root).resolve();out=Path(output_dir).resolve()
    if out.exists() or 'data' in out.parts:raise ValueError('Choose a new private scope directory')
    manifest=json.loads((job/'manifest.json').read_text());verify_frozen(job,manifest)
    checks=[];books={};packets={};refs={};batches=[]
    for batch in manifest['batches']:
        folder=job/batch['folder'];packet=json.loads((folder/'record_packet.json').read_text())
        expected=[];cohort=read_csv(folder/'cohort.csv')
        done=(folder/'result.json').exists();actual={}
        if done:
            result=json.loads((folder/'result.json').read_text())
            actual={b['catalog_item_id']:b for b in json.loads((folder/result['report_json']).read_text())['reviews']}
        for b in cohort:
            cid=b['catalog_item_id'];predicted=review_one(b,packet[cid],[],set(),'Records-only preparation; no market evidence or copy grades assumed.')
            rows=identification_checks(predicted)
            if done and sorted(map(signature,rows))!=sorted(map(signature,identification_checks(actual[cid]))):
                raise ValueError('Records-only prediction differs from completed identification checks')
            if not rows:continue
            books[cid]=predicted;packets[cid]=packet[cid]
            refs[cid]=dict(number=batch['number'],folder=batch['folder'],inputs=batch['inputs'],collected=done)
            for row in rows:
                expected.append(row);checks.append(dict(row,batch=batch['number'],collection_phase='completed' if done else 'awaiting_collection'))
        batches.append(dict(number=batch['number'],folder=batch['folder'],inputs=batch['inputs'],book_ids=[b['catalog_item_id'] for b in cohort],expected_checks=expected))
    verify_frozen(job,manifest)
    out.mkdir(parents=True,mode=0o700)
    payload=dict(version='records-check-scope-v1',job_root=str(job),job_manifest_sha256=sha(job/'manifest.json'),
                 identification_rule_sha256=manifest['rule_fingerprints']['candidate_record_review.py'],
                 active_review_records=manifest['remaining_records'],checks=checks,books=books,packets=packets,batch_refs=refs,batches=batches,
                 scope='All frozen source-dependent identification checks; not a forecast of market results',publication='disabled')
    atomic(out/'review_packet.json',payload);return payload


def validate_completed(job_root,packet_path,adjudication_path,output_dir):
    """Apply prior authored coverage only to exact matching frozen/arriving flags."""
    job=Path(job_root).resolve();packet_path=Path(packet_path).resolve();adjudication_path=Path(adjudication_path).resolve();out=Path(output_dir).resolve()
    if out.exists() or 'data' in out.parts:raise ValueError('Choose a new private validation directory')
    packet=json.loads(packet_path.read_text());manifest=json.loads((job/'manifest.json').read_text());decisions=json.loads(adjudication_path.read_text())
    verify_frozen(job,manifest)
    if str(job)!=packet['job_root'] or sha(job/'manifest.json')!=packet['job_manifest_sha256']:raise ValueError('Frozen job differs from reviewed scope')
    matching=[digest for name,digest in decisions['input_hashes'].items() if Path(name).resolve()==packet_path]
    if matching!=[sha(packet_path)]:raise ValueError('Adjudication differs from the source-review plan')
    if packet['identification_rule_sha256']!=manifest['rule_fingerprints']['candidate_record_review.py']:raise ValueError('Identification rules differ')
    indexed={b['number']:b for b in packet['batches']}
    if set(indexed)!={b['number'] for b in manifest['batches']}:raise ValueError('Batch plan differs')
    complete=set();arrived=[]
    for batch in manifest['batches']:
        expected=indexed[batch['number']]
        if expected['inputs']!=batch['inputs'] or expected['folder']!=batch['folder']:raise ValueError('Batch source inputs differ')
        folder=job/batch['folder'];receipt=folder/'result.json'
        if not receipt.exists():continue
        result=json.loads(receipt.read_text());review=json.loads((folder/result['report_json']).read_text())
        if {b['catalog_item_id'] for b in review['reviews']}!=set(expected['book_ids']):raise ValueError('Unexpected completed record scope')
        actual=[c for book in review['reviews'] for c in identification_checks(book)]
        if sorted(map(signature,actual))!=sorted(map(signature,expected['expected_checks'])):
            raise ValueError('Unreviewed or changed identification flags; do not apply prior decisions')
        complete.add(batch['number']);arrived.extend(actual)
    approved={(d['catalog_item_id'],d['original_kind']) for d in decisions['decisions']}
    expected_keys={(c['catalog_item_id'],c['kind']) for c in packet['checks']}
    if approved!=expected_keys:raise ValueError('Adjudication does not cover the exact identification scope')
    physical=read_csv(adjudication_path.parent/'physical_checks_only.csv')
    arrived_ids={cid for cid,ref in packet['batch_refs'].items() if ref['number'] in complete}
    current=[row for row in physical if row['catalog_item_id'] in arrived_ids]
    out.mkdir(parents=True,mode=0o700)
    with (out/'physical_checks_collected_batches.csv').open('w',newline='') as f:
        (out/'physical_checks_collected_batches.csv').chmod(0o600)
        fields=list(physical[0]) if physical else ['catalog_item_id','title','location','question']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(current)
    coverage=dict(total_batches=len(manifest['batches']),completed_batches=len(complete),source_records_covered=packet['active_review_records'],
                  reviewed_check_books=len(packet['books']),reviewed_identification_flags=len(packet['checks']),flags_arrived=len(arrived),
                  flags_awaiting_collection=len(packet['checks'])-len(arrived),unreviewed_arrived_flags=0,
                  all_frozen_physical_tasks=len(physical),physical_tasks_in_collected_batches=len(current),
                  market_collection_complete=len(complete)==len(manifest['batches']),estimates_changed=0,publication='disabled',source_requests=0,
                  input_hashes={str(packet_path):sha(packet_path),str(adjudication_path):sha(adjudication_path)})
    atomic(out/'coverage.json',coverage);return coverage
