"""Run a synthetic SWS replay and verify that canonical library files are untouched."""
import argparse
from datetime import date,datetime,timezone
import json
from pathlib import Path

from valuation.abebooks_sws import OfflineSwsClient,ReplayResponse,ReplayTransport,preview
from valuation.whole_library_review import protected,sha
from valuation.live_valuation_pilot import atomic


def run(project,output):
    project,output=Path(project).resolve(),Path(output).resolve()
    if output.exists() or any(p in output.parts for p in ('data','.git')):
        raise ValueError('Choose a new private output folder outside canonical data')
    before=protected(project)
    fixture=project/'tests/fixtures/abebooks_sws/long_results.xml'
    book=dict(catalog_item_id='SYNTHETIC-SWS-DEMO',title='Synthetic Methods',author='Synthetic Author',
              isbn13='9780198829171',reviewed_estimate_id='SYNTHETIC-SAVED-REVIEW')
    client=OfflineSwsClient(ReplayTransport([ReplayResponse(200,fixture.read_bytes())]))
    observed=datetime.now(timezone.utc).isoformat()
    rows=client.search(book,observed_at=observed)
    result=preview(book,rows,as_of=date.fromisoformat(observed[:10]))
    assert result['assessment']['status']=='manual_review_protected'
    assert result['condition_scenarios'][0]['listing_count']==3
    assert result['condition_scenarios'][0]['low']=='14.25'
    assert result['condition_scenarios'][0]['high']=='16.00'
    assert result['actual_condition']=='ungraded' and result['publishable'] is False
    if protected(project)!=before:raise ValueError('Canonical files changed during offline replay')
    output.mkdir(parents=True,mode=0o700)
    atomic(output/'synthetic_observations.json',rows)
    atomic(output/'synthetic_preview.json',result)
    receipt=dict(mode='synthetic_offline',live_requests=0,simulated_attempts=client.attempts,
                 synthetic_listings=len(rows),used_scenarios=len(result['condition_scenarios']),
                 expected_used_offers=3,wrong_edition_excluded=True,new_copy_kept_separate=True,
                 estimates_changed=0,canonical_unchanged=before==protected(project),
                 saved_manual_review_protected=True,physical_grading='deferred',publication='disabled',
                 fixture_sha256=sha(fixture),adapter_sha256=sha(project/'valuation/abebooks_sws.py'),
                 demo_sha256=sha(__file__),protected_hashes=before)
    atomic(output/'verification.json',receipt)
    return {k:v for k,v in receipt.items() if k!='protected_hashes'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.project,a.output),indent=2))
