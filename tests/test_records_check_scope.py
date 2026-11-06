import json
from pathlib import Path
import pytest
from valuation import records_check_scope as scope
from valuation.candidate_record_review import review_one
from valuation.edition_check_adjudication import adjudicate
from valuation.live_valuation_pilot import atomic
from valuation.whole_library_review import save_csv


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(scope,'verify_frozen',lambda *a:None)
    job=tmp_path/'job';job.mkdir();batches=[];books={};packets={}
    for n in (1,2):
        folder=job/f'batch_{n}';folder.mkdir();cid=f'B{n}'
        b=dict(catalog_item_id=cid,title='Synthetic '+cid,author='Author',isbn13='',isbn10='',location=str(n))
        p=dict(catalog=dict(b,publisher='Synthetic Press'),acquisitions=[],observations=[dict(inventory_observation_id='O'+cid,raw_title=b['title'])],source_notes=[])
        save_csv(folder/'cohort.csv',[b],list(b));atomic(folder/'record_packet.json',{cid:p})
        batches.append(dict(number=n,folder=folder.name,inputs={name:scope.sha(folder/name) for name in ('cohort.csv','record_packet.json')}))
        books[n]=b;packets[n]=p
    atomic(job/'manifest.json',dict(batches=batches,remaining_records=2,rule_fingerprints={'candidate_record_review.py':'frozen-rules'}))
    def complete(n,change=False):
        folder=job/f'batch_{n}';review=review_one(books[n],packets[n],[],set(),'synthetic')
        if change:review['physical_checks'][0]['question']='Changed question'
        atomic(folder/'review.json',dict(reviews=[review]));atomic(folder/'result.json',dict(report_json='review.json'))
    complete(1);packet=tmp_path/'scope';plan=scope.prepare_scope(job,packet)
    findings=tmp_path/'findings.json';atomic(findings,{cid:dict(outcome='requires_edition_check',finding='Source has no unique identifier.',physical_question='Read the identifier when handled.') for cid in plan['books']})
    report=tmp_path/'adjudication';adjudicate(packet/'review_packet.json',findings,report)
    return job,packet/'review_packet.json',report/'adjudications.json',complete


def test_all_frozen_checks_can_be_reviewed_before_collection_and_matched_later(tmp_path,monkeypatch):
    job,packet,adjudication,complete=fixture(tmp_path,monkeypatch)
    first=scope.validate_completed(job,packet,adjudication,tmp_path/'first')
    assert first['flags_arrived']==1 and first['flags_awaiting_collection']==1 and not first['market_collection_complete']
    assert first['all_frozen_physical_tasks']==2 and first['physical_tasks_in_collected_batches']==1
    complete(2);later=scope.validate_completed(job,packet,adjudication,tmp_path/'later')
    assert later['flags_arrived']==2 and later['market_collection_complete'] and later['unreviewed_arrived_flags']==0


def test_changed_later_checks_cannot_be_closed_by_prior_authored_findings(tmp_path,monkeypatch):
    job,packet,adjudication,complete=fixture(tmp_path,monkeypatch);complete(2,change=True)
    with pytest.raises(ValueError,match='Unreviewed or changed'):scope.validate_completed(job,packet,adjudication,tmp_path/'invalid')


def test_changed_job_manifest_cannot_reuse_a_prior_adjudication(tmp_path,monkeypatch):
    job,packet,adjudication,_=fixture(tmp_path,monkeypatch)
    manifest=json.loads((job/'manifest.json').read_text());manifest['remaining_records']=3;atomic(job/'manifest.json',manifest)
    with pytest.raises(ValueError,match='Frozen job differs'):scope.validate_completed(job,packet,adjudication,tmp_path/'invalid')
