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
    store.update(dict(kind='disposition', id='BK000001', value='gift_donate', revision=0))
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
    original=next(o for o in model.observations if o.inventory_observation_id==model.holdings[0].latest_inventory_observation_id)
    same=replace(original, inventory_observation_id='same-title', title='  '+original.title.upper()+'  ')
    model=replace(model, observations=(*model.observations,same), completed_inventory=CompletedInventoryScope(completed=True,holding_ids=tuple(h.holding_id for h in model.holdings),unresolved_observation_ids=('same-title',)))
    store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)
    selected={h.latest_inventory_observation_id for h in model.holdings}|{'same-title'}
    expected=len({' '.join(o.title.casefold().split()) for o in model.observations if o.inventory_observation_id in selected})
    assert store.snapshot()['distinct_titles']==expected
    assert len(model.observations)>expected


def test_two_service_instances_reject_stale_saves(tmp_path):
    first=store_for(tmp_path)
    second=WorkspaceStore(first.data_dir,first.output_dir,model=first.model)
    first.update(dict(kind='disposition',id='BK000001',value='keep',revision=0))
    with pytest.raises(RuntimeError):
        second.update(dict(kind='disposition',id='BK000001',value='sell',revision=0))
    assert second.snapshot()['dispositions']['BK000001']=='keep'


def test_outstanding_checks_come_from_durable_review_not_generated_csv(tmp_path):
    model=model_with_inventory(tmp_path)
    oid=model.holdings[0].latest_inventory_observation_id
    data=tmp_path/'data';out=tmp_path/'output'
    (data/'inventory_followup_reviews.json').write_text(json.dumps(dict(schema_version=1,reviews=[dict(status='physical_check_required',inventory_observation_id=oid,title='Reviewed book',question='Check the binding',collection='Box 1',bibliographic_evidence='Both ISBNs on copyright page')])))
    store=WorkspaceStore(data,out,model=model)
    assert not (out/'physical_book_checks.csv').exists()
    assert any(task['id']=='book-check:'+oid for task in store.actions)
    task=next(task for task in store.actions if task['id']=='book-check:'+oid)
    store.update(dict(kind='action',id=task['id'],fingerprint=task['fingerprint'],status='complete',revision=0))
    rebuilt=WorkspaceStore(data,out,model=model)
    assert next(t for t in rebuilt.snapshot()['actions'] if t['id']==task['id'])['status']=='complete'


def test_macos_background_service_is_owned_by_launchd(tmp_path, monkeypatch):
    import valuation.workspace_service as service
    calls=[]
    answers=iter([False,True])
    monkeypatch.setattr(service,'service_ready',lambda *args:next(answers))
    monkeypatch.setattr(service.sys,'platform','darwin')
    monkeypatch.setattr(service.subprocess,'run',lambda args,**kwargs:calls.append(args))
    service.start_background(tmp_path/'data',tmp_path/'output',8765)
    assert calls[0][:2]==['/bin/launchctl','remove']
    submit=calls[1]
    assert submit[:2]==['/bin/launchctl','submit']
    assert '/usr/bin/env' in submit
    assert any(arg.startswith('PYTHONPATH=') for arg in submit)
    assert 'valuation.workspace_service' in submit
    assert '--background' not in submit
    assert str((tmp_path/'data').resolve()) in submit


def test_background_start_reuses_only_the_matching_workspace(tmp_path, monkeypatch):
    import valuation.workspace_service as service
    monkeypatch.setattr(service,'service_ready',lambda *args:True)
    monkeypatch.setattr(service.subprocess,'run',lambda *args,**kwargs:pytest.fail('Should reuse the running service'))
    service.start_background(tmp_path/'data',tmp_path/'output',8765)
    assert service.workspace_id(tmp_path/'data')!=service.workspace_id(tmp_path/'other')
    with pytest.raises(ValueError):service.start_background(tmp_path/'data',tmp_path/'output',0)


def test_combined_gift_donate_choice_preserves_legacy_decisions(tmp_path):
    store=store_for(tmp_path)
    repo=CollectorReviewRepository(store.data_dir/'collector_reviews.csv')
    old=dict.fromkeys(repo.fieldnames,'')
    old.update(catalog_item_id='BK000001',disposition='gift',review_notes='For family')
    repo.save([old]);before=repo.path.read_bytes()
    state=store.snapshot()
    assert state['dispositions']['BK000001']=='gift_donate'
    assert 'gift_donate' in state['disposition_choices']
    assert 'gift' not in state['disposition_choices'] and 'donate' not in state['disposition_choices']
    assert repo.path.read_bytes()==before
    store.update(dict(kind='disposition',id='BK000001',value='gift_donate',revision=0))
    assert repo.load()[0]['disposition']=='gift_donate'
    assert repo.load()[0]['review_notes']=='For family'
    assert store.read()['events'][0]['previous']=='gift'


def market_fixture(confidence='moderate_confidence_market_evidence'):
    from valuation.steward_presentation import MarketEvidenceView
    return MarketEvidenceView('market:BK000001','BK000001','current','observed_listings',
        'AbeBooks','3',confidence,'10','15','20','USD','market_evidence_sufficient','',
        '2026-11-04','test')


@pytest.mark.parametrize('confidence,usable',[
    ('high_confidence_market_evidence',True),('moderate_confidence_market_evidence',True),
    ('thin_market_evidence',False),('ambiguous_edition_match',False),('unknown_market_confidence',False)])
def test_usable_estimate_requires_supported_matches_not_just_numbers(confidence,usable):
    base=dict(acquisition_source_status='current',acquisitions=[],inventory_source_status='current',holdings=[],
        market_source_status='current',market=market_fixture(confidence),review_source_status='current',review=None)
    result=_book_steward_summaries(**base)
    assert result['usable_market_estimate'] is usable
    assert result['resale_market_status']=='estimate_available'  # Original asking prices are preserved.
    assert not _book_steward_summaries(**dict(base,market_source_status='stale'))['usable_market_estimate']
    assert not _book_steward_summaries(**dict(base,market=replace(base['market'],currency='')))['usable_market_estimate']


def test_unpriced_book_has_executable_search_and_usable_book_has_no_score_task(tmp_path):
    from urllib.parse import parse_qs,urlsplit
    from valuation.steward_presentation import RecommendationView
    model=model_for(tmp_path,[catalog_row()]);book=model.books[0]
    rec=RecommendationView('old-score','research_candidate','assessment','catalog_item','BK000001',
        'Review research candidate','missing_oclc:+5','low',(),())
    model=replace(model,recommendations=(rec,))
    actions=build_actions(model,[])
    assert len(actions)==1
    task=actions[0]
    assert task['id']=='estimate-research:BK000001'
    assert 'ISBN '+book.isbn13 in task['next_step']
    assert 'Record useful asking prices' in task['next_step']
    assert 'OCLC' not in task['reason'] and 'purchase' not in task['reason']
    assert parse_qs(urlsplit(task['search_links'][0]['url']).query)['isbn']==[book.isbn13]
    usable=replace(model,books=(replace(book,usable_market_estimate=True),))
    assert build_actions(usable,[])==[]


@pytest.mark.parametrize('confidence,word',[
    ('thin_market_evidence','additional comparable copies'),
    ('ambiguous_edition_match','before using'),
    ('mixed_currency_evidence','one currency'),
    ('unknown_market_confidence','signed copies'),
    ('source_unavailable','AbeBooks and eBay')])
def test_estimate_tasks_follow_the_evidence_gap(tmp_path,confidence,word):
    from valuation.workspace_service import estimate_research_action
    model=model_for(tmp_path,[catalog_row()])
    task=estimate_research_action(model.books[0],market_fixture(confidence))
    assert word in task['next_step']
    assert task['reason'] and task['category']=='Estimate research'


def test_existing_book_check_remains_single_task_and_keeps_its_fingerprint(tmp_path):
    import hashlib
    model=model_with_inventory(tmp_path);holding=model.holdings[0]
    check=dict(inventory_observation_id=holding.latest_inventory_observation_id,title='Check book',
        question='Which binding is this?',collection='Box 1')
    actions=build_actions(model,[check])
    task=next(t for t in actions if t['id'].startswith('book-check:'))
    assert 'Record the answer' in task['next_step']
    assert not any(t['id']=='estimate-research:'+holding.catalog_item_id for t in actions)
    previous={k:v for k,v in task.items() if k not in {'next_step','fingerprint'}}
    assert task['fingerprint']==hashlib.sha256(json.dumps(previous,sort_keys=True).encode()).hexdigest()


def test_estimate_research_uses_title_when_no_isbn_and_excludes_history(tmp_path):
    from valuation.workspace_service import estimate_research_action
    from valuation.completed_inventory import CompletedInventoryScope
    from urllib.parse import urlsplit,parse_qs
    model=model_for(tmp_path,[catalog_row(),catalog_row('BK000002',title='Historical book')])
    no_isbn=replace(model.books[0],isbn13='',isbn10='')
    task=estimate_research_action(no_isbn,None)
    assert 'older books may have no ISBN' in task['next_step']
    assert parse_qs(urlsplit(task['search_links'][0]['url']).query)['tn']==[no_isbn.title]
    scoped=replace(model,completed_inventory=CompletedInventoryScope(completed=True,catalog_item_ids=('BK000001',)))
    assert [t['catalog_item_id'] for t in build_actions(scoped,[])]==['BK000001']
