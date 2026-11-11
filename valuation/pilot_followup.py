"""Merge private pilot evidence without counting repeat listing fetches twice."""
from collections import Counter
from datetime import datetime
import csv
import hashlib
from pathlib import Path
from valuation.live_valuation_pilot import FIELDS, atomic
from valuation.offline_valuation_review import listing_key, read_csv


def merge_observations(inputs, output):
    inputs=list(map(Path,inputs));output=Path(output)
    if output.exists() or 'data' in output.resolve().parts:
        raise ValueError('Choose a new private evidence output outside canonical data')
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    latest={};outcomes=[];repeats=0
    for path in inputs:
        for row in read_csv(path):
            if row['lookup_status']!='observed':
                outcomes.append(row);continue
            key=(row['catalog_id'],row['source'],listing_key(row))
            if not key[2]:raise ValueError('Observed listing has no stable identity')
            observed=datetime.fromisoformat(row['observation_date'].replace('Z','+00:00'))
            if observed.tzinfo is None:raise ValueError('Observation timestamp needs a timezone')
            if key in latest:
                repeats+=1;old_time,old=latest[key]
                if observed==old_time and row!=old:
                    raise ValueError('Conflicting listing records at the same timestamp')
                if observed<=old_time:continue
            latest[key]=(observed,row)
    rows=[r for _,r in latest.values()]+outcomes
    rows.sort(key=lambda r:(r['catalog_id'],r['source'],listing_key(r),r['observation_date']))
    if hashes!={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}:raise ValueError('Input changed during merge')
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with output.open('x',newline='') as f:
        output.chmod(0o600);writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    receipt=dict(input_hashes=hashes,repeat_fetches_not_counted=repeats,distinct_observed_listings=len(latest),observed_by_book=dict(Counter(r['catalog_id'] for _,r in latest.values())),publication='disabled')
    atomic(output.with_suffix('.receipt.json'),receipt)
    return receipt
