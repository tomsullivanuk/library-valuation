import csv
import json
import threading
from dataclasses import replace
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pytest

from tests.test_steward_workspace import model_for, catalog_row, model_with_inventory
from valuation.workspace_service import WorkspaceStore, build_actions, make_server
from valuation.repositories import CollectorReviewRepository
from valuation.steward_presentation import AcquisitionView, _book_steward_summaries


def store_for(tmp_path):
    model = model_for(tmp_path, [catalog_row()])
    store = WorkspaceStore(tmp_path/'data', tmp_path/'output', model=model)
    store.actions = [dict(id='check:one', fingerprint='first', title='A book', action='Check ISBN', category='Book checks', location='Box 1', evidence='', catalog_item_id='BK000001', route='book/BK000001')]
    return store


def test_decisions_survive_restart_and_preserve_evidence(tmp_path):
    store = store_for(tmp_path)
    before = {p.name:p.read_bytes() for p in store.data_dir.iterdir() if p.is_file()}
    store.update(dict(kind='action', id='check:one', fingerprint='first', status='complete', note='ISBN checked', revision=0))
    store.update(dict(kind='disposition', id='BK000001', value='keep', revision=1))
    fresh = WorkspaceStore(store.data_dir, store.output_dir, model=store.model)
    fresh.actions = store.actions
    snapshot = fresh.snapshot()
    assert snapshot['revision'] == 2
    assert snapshot['actions'][0]['status'] == 'complete'
    assert snapshot['actions'][0]['note'] == 'ISBN checked'
    assert snapshot['dispositions']['BK000001'] == 'keep'
    assert len(fresh.read()['events']) == 2
    for name,content in before.items():
        if name != 'collector_reviews.csv':
            assert (store.data_dir/name).read_bytes() == content
    # A changed question reopens rather than hiding behind a prior completion.
    fresh.actions = [dict(store.actions[0], fingerprint='changed')]
    assert fresh.snapshot()['actions'][0]['status'] == 'open'
    assert fresh.read()['events'][0]['note'] == 'ISBN checked'


def test_stale_writes_invalid_ids_and_deferred_dates_do_not_mutate(tmp_path):
    store = store_for(tmp_path)
    request = dict(kind='action', id='check:one', fingerprint='first', status='deferred', revision=0)
    with pytest.raises(ValueError):
        store.update(request)
    assert not store.path.exists()
    future = (datetime.now(ZoneInfo('America/Chicago')).date()+timedelta(days=3)).isoformat()
    store.update(dict(request, deferred_until=future))
    before = store.path.read_bytes()
    with pytest.raises(RuntimeError):
        store.update(dict(request, deferred_until=future))
    with pytest.raises(ValueError):
        store.update(dict(kind='disposition', id='missing', value='keep', revision=1))
    with pytest.raises(ValueError):
        store.update(dict(kind='disposition', id='BK000001', value='anything', revision=1))
    assert store.path.read_bytes() == before
    store.update(dict(kind='action', id='check:one', fingerprint='first', status='dismissed', revision=1))
    assert store.snapshot()['actions'][0]['deferred_until'] == ''
    store.update(dict(kind='action', id='check:one', fingerprint='first', status='open', revision=2))
    assert store.snapshot()['actions'][0]['status'] == 'open'


def test_disposition_preserves_other_review_fields_and_can_be_cleared(tmp_path):
    store = store_for(tmp_path)
    repo = CollectorReviewRepository(store.data_dir/'collector_reviews.csv')
    old = dict.fromkeys(repo.fieldnames,'')
    old.update(catalog_item_id='BK000001', review_notes='Preserve my notes', workflow_state='research', created_at='2020-01-01')
    repo.save([old])
    store.update(dict(kind='disposition', id='BK000001', value='donate', revision=0))
    row = repo.load()[0]
    for key in ('review_notes','workflow_state','created_at'):
        assert row[key] == old[key]
    store.update(dict(kind='disposition', id='BK000001', value='', revision=1))
    assert repo.load()[0]['disposition'] == ''


def test_http_requires_local_origin_token_and_restricts_files(tmp_path):
    store = store_for(tmp_path)
    server = make_server(store, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(base+'/api/state') as response:
            state=json.load(response)
        body=json.dumps(dict(kind='disposition', id='BK000001', value='sell', revision=0)).encode()
        for headers in [{}, {'X-Workspace-Token':state['token'], 'Origin':'https://example.com'}]:
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base+'/api/state',data=body,headers={'Content-Type':'application/json',**headers}))
            assert error.value.code == 403
        with urlopen(Request(base+'/api/state', data=body, headers={'Content-Type':'application/json','X-Workspace-Token':state['token'],'Origin':base})) as response:
            assert json.load(response)['dispositions']['BK000001']=='sell'
        for path in ['/../data/acquisitions.csv','/backup_before_followups/data/acquisitions.csv']:
            with pytest.raises(HTTPError) as error:urlopen(base+path)
            assert error.value.code == 404
    finally:
        server.shutdown();server.server_close();thread.join()


def test_checks_deduplicate_inventory_recommendations(tmp_path):
    model = model_with_inventory(tmp_path)
    oid=model.holdings[0].latest_inventory_observation_id
    actions=build_actions(model,[dict(inventory_observation_id=oid,title='Observed book',question='Check this book',collection='Box 1')])
    assert sum(a['id']=='book-check:'+oid for a in actions)==1
    assert not any(a['action']=='Assign a durable location later' for a in actions)
    assert all(a['category']!='Review newly discovered books' for a in actions)


def test_purchase_cost_uses_latest_unit_price_with_half_up_rounding():
    old=AcquisitionView('a','a','BK1','amazon','2021-02-01','1','USD','19.50','19.50')
    latest=AcquisitionView('b','b','BK1','amazon','2026-05-02','2','USD','34.50','69.00')
    base=dict(acquisition_source_status='current',inventory_source_status='current',holdings=[],market_source_status='unavailable',market=None,review_source_status='current',review=None)
    assert _book_steward_summaries(acquisitions=[old],**base)['purchase_summary']=='Amazon • Feb 2021 • $20'
    assert _book_steward_summaries(acquisitions=[old,latest],**base)['purchase_summary']=='2 records • latest May 2026 • $35'
    assert _book_steward_summaries(acquisitions=[replace(latest,item_price='')],**base)['purchase_summary']=='Amazon • May 2026'


def test_location_uses_libib_collection_and_lists_every_location():
    result=_book_steward_summaries(acquisition_source_status='current',acquisitions=[],inventory_source_status='current',holdings=[dict(source_collection_label=v,current_location_id='internal') for v in ['Box 8','Box 1','Box 3 and 3A','Box 1']],market_source_status='unavailable',market=None,review_source_status='current',review=None)
    assert result['location_summary']=='1, 3 and 3A, 8'
    assert result['disposition']==''


def test_distinct_titles_are_counted_from_inventory_not_catalog(tmp_path):
    from valuation.completed_inventory import CompletedInventoryScope
    model=model_with_inventory(tmp_path)
    original=model.observations[0]
    same=replace(original, inventory_observation_id='same-title', title='  '+original.title.upper()+'  ')
    model=replace(model, observations=(*model.observations,same), completed_inventory=CompletedInventoryScope(completed=True,holding_ids=tuple(h.holding_id for h in model.holdings),unresolved_observation_ids=('same-title',)))
    store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)
    expected=len({' '.join(o.title.casefold().split()) for o in model.observations})
    assert store.snapshot()['distinct_titles']==expected
    assert len(model.observations)>expected


def test_two_service_instances_reject_stale_saves(tmp_path):
    first=store_for(tmp_path)
    second=WorkspaceStore(first.data_dir,first.output_dir,model=first.model)
    first.update(dict(kind='disposition',id='BK000001',value='keep',revision=0))
    with pytest.raises(RuntimeError):
        second.update(dict(kind='disposition',id='BK000001',value='sell',revision=0))
    assert second.snapshot()['dispositions']['BK000001']=='keep'
