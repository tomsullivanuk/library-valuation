from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tests.test_steward_workspace import model_for, catalog_row
from valuation.workspace_service import WorkspaceStore, load_model
from valuation import estimate_reviews as er
from valuation.steward_workspace import render_steward_workspace


def fixture(tmp_path):
    model=model_for(tmp_path,[catalog_row()])
    store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)
    task=next(t for t in store.actions if t['category']=='Estimate research')
    values=dict(kind='estimate',revision=0,id=task['id'],fingerprint=task['fingerprint'],
        book_identity=er.book_identity(model.books[0]),reviewed=True,low='10.25',high='20.75',currency='USD',
        researched_on=datetime.now(ZoneInfo('America/Chicago')).date().isoformat(),
        note='Three matching paperback copies in good condition.',source_urls=['https://example.test/listing'])
    return store,values


def test_estimate_updates_value_and_completes_task_across_reload(tmp_path):
    store,request=fixture(tmp_path)
    original={p.name:p.read_bytes() for p in store.data_dir.iterdir() if p.is_file()}
    result=store.update(request)
    price=result['estimate_updates']['BK000001']
    assert price['estimated_value_precise_low']=='10.25' and price['estimated_value_precise_high']=='20.75'
    assert price['estimated_value_display']=='$10–$21'
    assert price['usable_market_estimate'] and price['reviewed_estimate_id']
    task=next(t for t in result['actions'] if t['id']==request['id'])
    assert task['status']=='complete' and task['note']==request['note']
    assert not any(t['id']==request['id'] for t in store.actions)
    fresh=WorkspaceStore(store.data_dir,store.output_dir)
    book=fresh.model.books[0]
    assert book.reviewed_estimate_id==price['reviewed_estimate_id']
    assert book.estimated_value_sort_low=='10' and book.estimated_value_sort_high=='21'
    assert fresh.snapshot()['actions'][0]['status']=='complete'
    html=render_steward_workspace(fresh.model).decode()
    assert 'Your reviewed estimate' in html
    for name,content in original.items():assert (store.data_dir/name).read_bytes()==content


def test_revision_appends_history_and_archived_task_can_be_reopened(tmp_path):
    store,request=fixture(tmp_path);first=store.update(request)
    review_id=first['estimate_updates']['BK000001']['reviewed_estimate_id']
    store.update(dict(kind='action',revision=1,id=request['id'],fingerprint=request['fingerprint'],
                      status='open',note=request['note']))
    updated=store.update(dict(request,revision=2,previous_estimate_review_id=review_id,low='12',high='18'))
    rows=er.load_reviews(store.data_dir)
    assert len(rows)==2 and rows[1]['supersedes']==rows[0]['review_id']
    assert rows[0]['low']=='10.25' and rows[1]['low']=='12.00'
    assert len(updated['estimate_history']['BK000001'])==2
    assert updated['actions'][0]['status']=='complete'


@pytest.mark.parametrize('change',[
    dict(low='21',high='20'),dict(low='-1'),dict(low='NaN'),dict(high='Infinity'),
    dict(low='1.123'),dict(currency='XXX'),dict(note=''),dict(source_urls=['javascript:alert(1)']),
    dict(source_urls=['https://user:secret@example.test/']),dict(reviewed=False),
    dict(researched_on='not a date'),dict(researched_on='2999-01-01')])
def test_invalid_estimates_do_not_write_records(tmp_path,change):
    store,request=fixture(tmp_path)
    with pytest.raises(ValueError):store.update(dict(request,**change))
    assert not (store.data_dir/er.FILE_NAME).exists()
    assert not store.path.exists()


def test_stale_revision_and_book_identity_are_rejected(tmp_path):
    store,request=fixture(tmp_path)
    with pytest.raises(RuntimeError):store.update(dict(request,book_identity='wrong'))
    store.update(request)
    before=(store.data_dir/er.FILE_NAME).read_bytes()
    with pytest.raises(RuntimeError):store.update(request)
    assert (store.data_dir/er.FILE_NAME).read_bytes()==before
    with pytest.raises(RuntimeError):store.update(dict(request,revision=1))
    assert (store.data_dir/er.FILE_NAME).read_bytes()==before


def test_estimate_and_task_publish_roll_back_together(tmp_path,monkeypatch):
    import valuation.completed_inventory as completed
    store,request=fixture(tmp_path)
    replace_file=completed.os.replace
    def fail_state(source,target):
        if Path(target)==store.path:raise OSError('Simulated state write failure')
        replace_file(source,target)
    monkeypatch.setattr(completed.os,'replace',fail_state)
    with pytest.raises(OSError):store.update(request)
    assert not store.path.exists() and not (store.data_dir/er.FILE_NAME).exists()
    assert not store.model.books[0].reviewed_estimate_id


def test_changed_catalog_identity_does_not_inherit_reviewed_estimate(tmp_path):
    from valuation.libib_catalog import StrictCatalogRepository
    store,request=fixture(tmp_path);store.update(request)
    repo=StrictCatalogRepository(store.data_dir/'catalog_items.csv');rows=repo.load()
    rows[0]['isbn13']='9780198786221';rows[0]['isbn10']='0198786220'
    repo.path.write_bytes(repo.rendered_bytes(rows))
    fresh=load_model(store.data_dir,store.output_dir)
    assert not fresh.books[0].reviewed_estimate_id and not fresh.books[0].usable_market_estimate
    assert len(er.load_reviews(store.data_dir))==1


def test_review_does_not_overwrite_market_evidence(tmp_path):
    from dataclasses import replace
    from tests.test_workspace_service import market_fixture
    store,request=fixture(tmp_path)
    market=market_fixture('unknown_market_confidence')
    store.model=replace(store.model,market_evidence=(market,))
    store.update(request)
    assert store.model.market_evidence==(market,)
    assert store.model.market_evidence[0].likely_low=='10'
    assert store.model.books[0].estimated_value_precise_low=='10.25'


def test_preview_is_distinct_from_saving_and_updates_reach_the_client(tmp_path):
    store,request=fixture(tmp_path)
    html=render_steward_workspace(store.model).decode()
    editor=html.split('function estimateEditor(task, note)',1)[1].split('function actionStatus',1)[0]
    assert 'Confirm the revised range' in editor and 'Previous range' in editor
    assert 'Save estimate and complete task' in editor
    assert 'save.addEventListener("click"' in editor
    assert 'previous_estimate_review_id' in editor
    assert 'applyEstimateUpdates();' in html and 'Object.assign(book, values)' in html
