import fcntl
import json

from valuation import whole_library_review as whole
from valuation import quota_recovery as recovery
from test_whole_library_review import fixture, patch_source, CREDS


def test_recovers_without_topping_up_or_modifying_frozen_inputs(tmp_path, monkeypatch):
    root, project = fixture(tmp_path)
    patch_source(monkeypatch)
    ledger = whole.QuotaLedger(root / 'quota_ledger.json')
    ledger.update(470, '2099-01-01T00:00:00Z')
    before = whole.protected(project)
    manifest = whole.sha(root / 'manifest.json')
    assert not ledger.ready()
    assert recovery.recover_one(root, CREDS) == 'batch_complete'
    assert ledger.state()['remaining'] == 467  # OAuth, search, detail
    assert whole.sha(root / 'manifest.json') == manifest
    assert whole.protected(project) == before
    whole.verify_frozen(root, json.loads((root / 'manifest.json').read_text()))
    result = json.loads((root / 'batches/001/result.json').read_text())
    assert result['summary']['estimates_changed'] == 0
    assert result['summary']['condition_checks_deferred'] == 1
    assert whole.run(root, CREDS, once=True) == 'waiting_for_quota'


def test_low_allowance_and_shared_lock_prevent_collection(tmp_path, monkeypatch):
    root, _ = fixture(tmp_path)
    patch_source(monkeypatch)
    ledger = whole.QuotaLedger(root / 'quota_ledger.json')
    ledger.update(110, '2099-01-01T00:00:00Z')
    with (root / '.controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert recovery.recover_one(root, CREDS) == 'already_running'
    assert recovery.recover_one(root, CREDS) == 'insufficient_conservative_allowance'
    assert not (root / 'batches/001/collection').exists()


def test_remaining_bound_uses_checkpoint_and_preserves_retry_margin(tmp_path):
    root, _ = fixture(tmp_path)
    folder = root / 'batches/001'
    assert recovery.required_requests(folder) == 36
    (folder / 'collection').mkdir()
    whole.atomic(folder / 'collection/checkpoint.json', dict(books={'BK0': dict(
        search=dict(item_ids=['a', 'b']), details={'a': {}}, completed=False)}))
    assert recovery.required_requests(folder) == 26


def test_full_batch_bound_keeps_reserve_and_does_not_admit_next_batch(tmp_path):
    root, _ = fixture(tmp_path)
    folder = root / 'batches/001'
    books = whole.read_csv(folder / 'cohort.csv') * 25
    whole.save_csv(folder / 'cohort.csv', books, list(books[0]))
    assert recovery.required_requests(folder) == 300
    ledger = whole.QuotaLedger(root / 'quota_ledger.json')
    ledger.update(470, '2099-01-01T00:00:00Z')
    assert ledger.ready(recovery.required_requests(folder))
    for _ in range(171):
        ledger.charge()
    assert not ledger.ready(recovery.required_requests(folder))
    for _ in range(199):
        ledger.charge()
    import pytest
    with pytest.raises(whole.QuotaPause):
        ledger.charge()
    assert ledger.state()['remaining'] == 100


def test_failure_stops_and_preserves_canonical_data(tmp_path, monkeypatch):
    import pytest
    root, project = fixture(tmp_path)
    patch_source(monkeypatch)
    before = whole.protected(project)
    def fail(*a, **kwargs):
        raise ValueError('synthetic integrity failure')
    monkeypatch.setattr(whole, 'review_batch', fail)
    with pytest.raises(ValueError):
        recovery.recover_one(root, CREDS)
    assert (root / 'critical_stop.json').exists()
    assert recovery.recover_one(root, CREDS) == 'critical_stop'
    assert whole.protected(project) == before


def provider_samples(monkeypatch, balances):
    samples = iter(balances)
    def refresh(credentials, root, ledger):
        remaining = next(samples)
        state = ledger.update(remaining, '2099-01-01T00:00:00Z')
        path = root / 'quota_history.json'
        history = json.loads(path.read_text()) if path.exists() else []
        history.append(dict(reported_remaining=remaining, limit=5000,
                            reset=state['reset'], effective_remaining=state['remaining'],
                            control_requests=2, at='synthetic'))
        whole.atomic(path, history)
        return state
    monkeypatch.setattr(whole, 'refresh_quota', refresh)


def test_explicit_fresh_balance_runs_exactly_one_and_compares_separate_counts(tmp_path, monkeypatch):
    root, project = fixture(tmp_path)
    patch_source(monkeypatch)
    provider_samples(monkeypatch, [1330, 1328])
    ledger = whole.QuotaLedger(root / 'quota_ledger.json')
    ledger.update(283, '2099-01-01T00:00:00Z')
    before = whole.protected(project)
    manifest = whole.sha(root / 'manifest.json')
    assert recovery.recover_one(root, CREDS, use_fresh_balance=True) == 'batch_complete'
    path = next(p for p in (root / 'quota_recovery_receipts').glob('batch_001_fresh_*.json')
                if not p.name.endswith('.requests.json'))
    receipt = json.loads(path.read_text())
    assert receipt['ledger_before_refresh']['remaining'] == 283
    assert receipt['allowance_before'] == 1330
    assert receipt['allowance_after'] == 1327
    assert receipt['provider_decrease'] == 2
    assert receipt['request_counts'] == dict(oauth=1, search=1, detail=1, other=0)
    assert ledger.state()['remaining'] == 1327  # Post-batch comparison never tops up.
    assert len(json.loads(path.with_suffix('.requests.json').read_text())) == 3
    assert not (root / 'batches/002/collection').exists()
    assert whole.sha(root / 'manifest.json') == manifest
    assert whole.protected(project) == before
    assert whole.run(root, CREDS, once=True) == 'waiting_for_quota'


def test_fresh_low_balance_still_requires_reserve(tmp_path, monkeypatch):
    root, _ = fixture(tmp_path)
    patch_source(monkeypatch)
    provider_samples(monkeypatch, [110])
    assert recovery.recover_one(root, CREDS, use_fresh_balance=True) == 'insufficient_conservative_allowance'
    assert not (root / 'batches/001/collection').exists()


def test_out_of_range_provider_balance_cannot_increase_ledger(tmp_path, monkeypatch):
    import pytest
    root, _ = fixture(tmp_path)
    patch_source(monkeypatch)
    ledger = whole.QuotaLedger(root / 'quota_ledger.json')
    ledger.update(283, '2099-01-01T00:00:00Z')
    provider_samples(monkeypatch, [5001])
    with pytest.raises(ValueError):
        recovery.recover_one(root, CREDS, use_fresh_balance=True)
    assert ledger.state()['remaining'] == 283
    assert not (root / 'batches/001/collection').exists()
