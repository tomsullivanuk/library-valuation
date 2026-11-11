import json
import pytest

from valuation import whole_library_review as whole
from valuation import provider_quota_controller as controller
from test_whole_library_review import fixture, patch_source, CREDS
from test_quota_recovery import provider_samples


def enable(root):
    whole.QuotaLedger(root/'quota_ledger.json').update(100, '2099-01-01T00:00:00Z')
    controller.enable(root)


def test_provider_count_replaces_local_ceiling_and_continues_to_completion(tmp_path, monkeypatch):
    root, project = fixture(tmp_path)
    patch_source(monkeypatch)
    provider_samples(monkeypatch, [600, 598, 597, 595])
    enable(root)
    original = whole.sha(root/'manifest.json')
    before = whole.protected(project)
    assert controller.run(root, CREDS) == 'complete'
    status=json.loads((root/'status.json').read_text())
    assert status['completed_batches'] == 2
    assert status['state'] == 'complete'
    assert whole.protected(project) == before
    assert whole.sha(root/'manifest.json') == original
    receipts=[json.loads(p.read_text()) for p in sorted((root/'quota_recovery_receipts').glob('*.json'))
              if not p.name.endswith('.requests.json')]
    assert [r['allowance_before'] for r in receipts] == [600,597]
    assert all(r['policy'] == controller.POLICY for r in receipts)


def test_partial_at_cushion_is_durable_and_resumes_after_reset(tmp_path, monkeypatch):
    root, project = fixture(tmp_path, 1)
    patch_source(monkeypatch)
    provider_samples(monkeypatch, [102])
    enable(root)
    before=whole.protected(project)
    assert controller.run(root, CREDS, once=True) == 'waiting_for_quota'
    assert whole.QuotaLedger(root/'quota_ledger.json').state()['remaining'] == 100
    assert not (root/'critical_stop.json').exists()
    assert not (root/'batches/001/result.json').exists()
    assert controller.run(root, CREDS, once=True) == 'waiting_for_quota'  # No new requests.
    state=json.loads((root/'provider_controller_state.json').read_text())
    state['next_attempt_at']=0
    whole.atomic(root/'provider_controller_state.json',state)
    provider_samples(monkeypatch,[600,598])
    assert controller.run(root,CREDS) == 'complete'
    assert whole.protected(project) == before
    result=json.loads((root/'batches/001/result.json').read_text())
    assert result['summary']['estimates_changed'] == 0
    assert result['summary']['condition_checks_deferred'] == 1


def test_changed_continuation_policy_stops_before_requests(tmp_path, monkeypatch):
    root,_=fixture(tmp_path)
    patch_source(monkeypatch)
    enable(root)
    path=root/'provider_quota_policy.json'
    policy=json.loads(path.read_text());policy['reserve']=99;whole.atomic(path,policy)
    assert controller.run(root,CREDS) == 'critical_stop'
    assert not (root/'quota_history.json').exists()
    assert (root/'critical_stop.json').exists()


def test_policy_cannot_be_silently_replaced(tmp_path):
    root,_=fixture(tmp_path)
    enable(root)
    with pytest.raises(ValueError):controller.enable(root)


def test_provider_launch_configuration(tmp_path):
    from operations.install_whole_library_review import configuration
    config=configuration(tmp_path,tmp_path,tmp_path/'credentials',tmp_path/'python',tmp_path,
                         provider_counts=True)
    assert config['ProgramArguments'][2] == 'valuation.provider_quota_controller'
    assert config['KeepAlive'] == {'SuccessfulExit':False}


def test_provider_429_waits_without_losing_checkpoint(tmp_path,monkeypatch):
    from valuation.ebay_access import EbayRequestError
    from test_whole_library_review import fake_requests
    root,_=fixture(tmp_path,1)
    patch_source(monkeypatch)
    provider_samples(monkeypatch,[600])
    def request(req,timeout):
        if req.get_method()=='POST':return fake_requests(req,timeout)
        raise EbayRequestError('Synthetic quota response',status_code=429,failure_kind='quota')
    monkeypatch.setattr(whole,'default_request_json',request)
    enable(root)
    assert controller.run(root,CREDS,once=True)=='waiting_for_quota'
    assert not (root/'critical_stop.json').exists()
    assert (root/'batches/001/collection/checkpoint.json').exists()
    assert whole.QuotaLedger(root/'quota_ledger.json').state()['remaining']==598
