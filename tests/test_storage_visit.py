import pytest
from tests.test_workspace_service import store_for


def change(**extra):
    return dict(kind='storage_visit', source='action', id='check:one', fingerprint='first',
                visit_date='2026-11-19', done=True, note='Hardcover; barcode photographed.', revision=0, **extra)


def test_visit_answer_completes_action_and_survives_restart_without_inventory_changes(tmp_path):
    store = store_for(tmp_path)
    before = {p:p.read_bytes() for p in store.data_dir.iterdir() if p.is_file()}
    result = store.update(change())
    assert result['actions'][0]['status'] == 'complete'
    assert result['actions'][0]['note'] == 'Hardcover; barcode photographed.'
    assert result['storage_visits']['2026-11-19']['action:check:one']['done'] is True
    from valuation.workspace_service import WorkspaceStore
    fresh = WorkspaceStore(store.data_dir, store.output_dir, model=store.model)
    fresh.actions = store.actions
    assert fresh.snapshot()['storage_visits'] == result['storage_visits']
    for path, contents in before.items():
        assert path.read_bytes() == contents
    store.update(dict(change(), revision=1, done=False))
    assert store.snapshot()['actions'][0]['status'] == 'open'


def test_visit_pick_only_saves_visit_progress(tmp_path, monkeypatch):
    store = store_for(tmp_path)
    monkeypatch.setattr(store, 'visit_pick', lambda r:dict(submission='s', reference='r', slot='copy-2', title='A book'))
    result = store.update(dict(change(), source='pick', submission='s', reference='r', slot='copy-2'))
    assert result['actions'][0]['status'] == 'open'
    assert result['storage_visits']['2026-11-19']['pick:s:r:copy-2']['done']
    assert not result['dispositions']


def test_stale_device_cannot_overwrite_visit_notes(tmp_path):
    store = store_for(tmp_path)
    store.update(change())
    before = store.path.read_bytes()
    with pytest.raises(RuntimeError):
        store.update(dict(change(), note='Old device answer'))
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('extra', [dict(visit_date='tomorrow'), dict(visit_date='2026-02-30'),
    dict(done='yes'), dict(note='x'*4001), dict(fingerprint='changed'), dict(source='unknown')])
def test_invalid_visit_work_does_not_save(tmp_path, extra):
    store = store_for(tmp_path)
    with pytest.raises((ValueError, TypeError)):
        store.update(dict(change(), **extra))
    assert not store.path.exists()


def test_note_without_completion_keeps_deferred_status(tmp_path):
    store = store_for(tmp_path)
    store.update(dict(kind='action', id='check:one', fingerprint='first', status='deferred',
                      deferred_until='2099-01-01', note='Earlier', revision=0))
    result = store.update(dict(change(), done=False, revision=1))
    assert result['actions'][0]['status'] == 'deferred'
    assert result['actions'][0]['deferred_until'] == '2099-01-01'


@pytest.mark.parametrize('decision,review,slot,allowed', [
    ('approved',False,'copy-2',True), ('pending',True,'copy-2',True),
    ('transferred',False,'copy-2',False), ('declined',False,'copy-2',False),
    ('pending',False,'copy-2',False), ('approved',False,'old-copy',False),
])
def test_pick_saves_require_the_current_active_copy(tmp_path, monkeypatch, decision, review, slot, allowed):
    import sqlite3
    from valuation import family_owner, workspace_service
    store = store_for(tmp_path)
    monkeypatch.setattr(family_owner, 'settings', lambda:dict(database='unused'))
    monkeypatch.setattr(workspace_service, 'load_model', lambda *a, **k:store.model)
    monkeypatch.setattr(family_owner, 'live_facts', lambda *a:{})
    monkeypatch.setattr(family_owner.requests, 'connect', lambda p:sqlite3.connect(':memory:'))
    payload = dict(owner_pick='review', owner_pick_slots={'r':'copy-2'}) if review else {}
    rows=[dict(id='s', payload=payload, items=[dict(reference='r',title='A book',
        decision=dict(state=decision,slot=None if review else 'copy-2'))])]
    monkeypatch.setattr(family_owner, 'inbox', lambda *a:rows)
    request=dict(submission='s', reference='r', slot=slot)
    if allowed:
        assert store.visit_pick(request)['slot']=='copy-2'
    else:
        with pytest.raises(ValueError,match='reservation changed'):
            store.visit_pick(request)
    assert not store.path.exists()
