import hashlib
import json
from dataclasses import replace
from pathlib import Path
import pytest
from tests.test_steward_workspace import model_for,catalog_row
from valuation.workspace_service import WorkspaceStore
from valuation.workspace_action_review import FILE_NAME
from valuation.estimate_reviews import book_identity


def setup(tmp_path,proposal=True):
    model=model_for(tmp_path,[catalog_row()]);book=model.books[0]
    manifest=dict(schema_version=1,review_id='synthetic-review',reviewed_on='2026-11-16',
        books={book.catalog_item_id:dict(book_identity=book_identity(book),proposals=[dict(low='12',high='25',currency='USD',binding='paperback',grade='good',sources=['abebooks','ebay_active_listings'],source_urls=['https://example.test/book'],publishable=False)] if proposal else [],research_next_step='Check comparable editions')},
        owner_checks=[dict(id='check:one',title=book.title,catalog_item_id=book.catalog_item_id,inventory_observation_id='',question='Check only the binding',location='1',evidence='Existing photo lists alternatives')],resolved_checks=[],superseded_check_ids=[])
    path=tmp_path/'data'/FILE_NAME;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(manifest));return model,manifest,path


def test_review_queues_are_read_only_projections_and_do_not_apply_prices(tmp_path):
    model,m,path=setup(tmp_path);before={p.name:p.read_bytes() for p in path.parent.iterdir() if p.is_file()}
    store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model);state=store.snapshot()
    assert state['action_review']['loaded']
    assert {a['category'] for a in state['actions']}=={'Book checks','Proposed estimates'}
    assert next(a for a in state['actions'] if a['category']=='Book checks')['audience']=='owner'
    assert next(a for a in state['actions'] if a['category']=='Proposed estimates')['audience']=='assistant'
    assert store.model.books==model.books
    assert before=={p.name:p.read_bytes() for p in path.parent.iterdir() if p.is_file()}
    assert not (path.parent/'reviewed_estimates.json').exists()


def test_answer_completion_survives_restart_and_reworded_check_keeps_prior_answer(tmp_path):
    model,m,path=setup(tmp_path);store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)
    task=next(a for a in store.snapshot()['actions'] if a['id']=='check:one')
    store.update(dict(kind='action',id=task['id'],fingerprint=task['fingerprint'],revision=0,status='complete',note='It is paperback'))
    fresh=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)
    assert next(a for a in fresh.snapshot()['actions'] if a['id']=='check:one')['status']=='complete'
    m['owner_checks'][0]['question']='Read the cover ISBN';path.write_text(json.dumps(m))
    fresh=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model);task=next(a for a in fresh.snapshot()['actions'] if a['id']=='check:one')
    assert task['status']=='open' and task['previous_answer']=='It is paperback'
    assert fresh.read()['events'][0]['note']=='It is paperback'


def test_changed_identity_or_saved_manual_range_cannot_inherit_proposals(tmp_path):
    model,m,path=setup(tmp_path)
    changed=replace(model,books=(replace(model.books[0],title='Different edition'),))
    state=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=changed).snapshot()
    assert not any(a['category']=='Proposed estimates' for a in state['actions'])
    assert state['action_review']['changed_or_new_books']==1
    manual=replace(model,books=(replace(model.books[0],reviewed_estimate_id='EST-1'),))
    # Test projection independently: snapshot's history intentionally requires a real ledger.
    store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=manual)
    assert not any(a['category']=='Proposed estimates' for a in store.actions)
    assert not any(a['category']=='Estimate research' for a in store.actions)


def test_resolved_check_is_reference_not_a_pending_owner_task(tmp_path):
    model,m,path=setup(tmp_path,False);m['resolved_checks']=[dict(id='check:one',catalog_item_id=model.books[0].catalog_item_id,finding='Printed identifier is legible')];m['owner_checks']=[];path.write_text(json.dumps(m))
    state=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model).snapshot()
    t=next(a for a in state['actions'] if a['id']=='check:one')
    assert t['category']=='Resolved from records' and t['status']=='complete' and t['read_only']
    assert not any(a['audience']=='owner' for a in state['actions'])


@pytest.mark.parametrize('bad',['schema','duplicate','url','price','publishable'])
def test_invalid_review_cannot_be_loaded(tmp_path,bad):
    model,m,path=setup(tmp_path)
    if bad=='schema':m['schema_version']=99
    if bad=='duplicate':m['owner_checks']*=2
    if bad=='url':m['books'][model.books[0].catalog_item_id]['proposals'][0]['source_urls']=['javascript:bad']
    if bad=='price':m['books'][model.books[0].catalog_item_id]['proposals'][0]['high']='NaN'
    if bad=='publishable':m['books'][model.books[0].catalog_item_id]['proposals'][0]['publishable']=True
    path.write_text(json.dumps(m))
    with pytest.raises(ValueError):WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)


def test_explicit_individual_save_from_proposal_keeps_completed_history(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    model,m,path=setup(tmp_path);store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)
    task=next(t for t in store.actions if t['category']=='Proposed estimates')
    request=dict(kind='estimate',revision=0,id=task['id'],fingerprint=task['fingerprint'],book_identity=book_identity(model.books[0]),previous_estimate_review_id='',reviewed=False,low='12',high='25',currency='USD',researched_on=datetime.now(ZoneInfo('America/Chicago')).date().isoformat(),note='Explicit individual review of a synthetic copy',source_urls=['https://example.test/listing'])
    with pytest.raises(ValueError):store.update(request)
    assert not (tmp_path/'data'/'reviewed_estimates.json').exists()
    state=store.update(dict(request,reviewed=True))
    saved=next(t for t in state['actions'] if t['id']==task['id'])
    assert saved['status']=='complete' and state['estimate_updates'][model.books[0].catalog_item_id]['estimated_value_precise_low']=='12.00'
