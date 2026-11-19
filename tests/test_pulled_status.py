import json
import pytest
from tests.test_family_owner import setup, action
from tests.test_workspace_service import store_for
from valuation import family_owner as owner, family_requests
from valuation.storage_visit import pickup_records, request_status


def status(db,facts,ids,pickups):
    return next(row for row in owner.inbox(db,facts,pickups=pickups) if row['id']==ids[0])['items'][0]['decision']['status']


def test_saved_pull_updates_status_and_uncheck_reverts_without_releasing_copy(tmp_path,setup,monkeypatch):
    db,catalog,facts,ids=setup
    owner.update(db,'owner',action(ids[0],'approved',slot='hold:1'),facts)
    store=store_for(tmp_path)
    monkeypatch.setattr(store,'visit_pick',lambda r:dict(submission=ids[0],reference='ref',slot='hold:1',title='Book'))
    body=dict(kind='storage_visit',source='pick',submission=ids[0],reference='ref',slot='hold:1',
              visit_date='2026-11-20',done=True,note='At home',revision=0)
    store.update(body)
    assert status(db,facts,ids,pickup_records(store.data_dir))=='pulled'
    assert owner.decision(db,ids[0],'ref')['state']=='approved'
    # Approval still owns the same physical copy; no second requester can take it.
    with pytest.raises(family_requests.Conflict):
        owner.update(db,'owner',action(ids[1],'approved',slot='hold:1'),facts)
    assert 'ref' not in owner.available(db,catalog,{'ref':dict(facts['ref'],copies=[facts['ref']['copies'][0]])})
    store.update(dict(body,done=False,revision=1))
    assert status(db,facts,ids,pickup_records(store.data_dir))=='approved'
    assert owner.decision(db,ids[0],'ref')['slot']=='hold:1'
    assert store.snapshot()['dispositions']=={}


def test_latest_saved_action_wins_over_visit_date_and_transfer_has_precedence(tmp_path,setup):
    db,catalog,facts,ids=setup
    owner.update(db,'owner',action(ids[0],'approved',slot='hold:1'),facts)
    entry=dict(source='pick',submission=ids[0],reference='ref',slot='hold:1',done=True,updated_at='2090-01-01T00:00:00+00:00')
    path=tmp_path/'workspace_actions.json'
    path.write_text(json.dumps(dict(storage_visits={'2030-01-01':{'one':entry},'2020-01-01':{'two':dict(entry,done=False,updated_at='2090-01-02T00:00:00+00:00')}})))
    pickups=pickup_records(tmp_path)
    assert status(db,facts,ids,pickups)=='approved'
    pickups[(ids[0],'ref','hold:1')]=entry
    assert status(db,facts,ids,pickups)=='pulled'
    owner.update(db,'owner',dict(action(ids[0],'transferred',version=1),transfer_kind='gift'),facts)
    assert status(db,facts,ids,pickups)=='transferred'


def test_messages_preserve_pulled_but_reapproval_and_reassignment_do_not(setup):
    db,catalog,facts,ids=setup
    owner.update(db,'owner',action(ids[0],'approved',slot='hold:1'),facts)
    stamp=owner.decision(db,ids[0],'ref')['updated']
    pickups={(ids[0],'ref','hold:1'):dict(done=True,updated_at=stamp)}
    assert status(db,facts,ids,pickups)=='pulled'
    owner.update(db,'owner',dict(action(ids[0],'approved',version=1,slot='hold:1'),message='Delivery today'),facts)
    assert status(db,facts,ids,pickups)=='pulled'
    owner.update(db,'owner',action(ids[0],'pending',version=2),facts)
    owner.update(db,'owner',action(ids[0],'approved',version=3,slot='hold:1'),facts)
    assert status(db,facts,ids,pickups)=='approved'
    pickups[(ids[0],'ref','hold:1')]['updated_at']='2099-01-01T00:00:00+00:00'
    owner.update(db,'owner',action(ids[0],'approved',version=4,slot='hold:2'),facts)
    assert status(db,facts,ids,pickups)=='approved'


def test_pull_is_scoped_to_submission_and_copy(setup):
    db,catalog,facts,ids=setup
    owner.update(db,'owner',action(ids[0],'approved',slot='hold:1'),facts)
    owner.update(db,'owner',action(ids[1],'approved',slot='hold:2'),facts)
    pickups={(ids[0],'ref','hold:1'):dict(done=True,updated_at='2099-01-01T00:00:00+00:00')}
    rows=owner.inbox(db,facts,pickups=pickups)
    decisions={row['id']:row['items'][0]['decision']['status'] for row in rows}
    assert decisions[ids[0]]=='pulled'
    assert decisions[ids[1]]=='approved'
    assert decisions[ids[2]]=='pending'
