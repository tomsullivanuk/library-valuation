from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path

import pytest
from valuation import whole_library_review as whole
from valuation.ebay_access import EbayCredentials,EbayRequestError
from valuation.live_valuation_pilot import atomic

CREDS=EbayCredentials('synthetic','secret','EBAY_US','production')
ISBN='9780198829171'


def fixture(tmp_path,n=2):
    project=tmp_path/'project';(project/'data').mkdir(parents=True);summary=project/'output/libib_inventory_20261020';summary.mkdir(parents=True)
    (project/'data/catalog_items.csv').write_text('original');(summary/'combined_market_evidence_summary.csv').write_text('original estimate')
    root=project/'output/review';root.mkdir();books=[dict(catalog_item_id=f'BK{i}',title='Synthetic Book',author='Synthetic Author',isbn13=ISBN,isbn10='',location='1',previous_low='8',previous_high='12',currency='USD',target_condition='',target_binding='') for i in range(n)]
    whole.save_csv(root/'cohort.csv',books,list(books[0]));batches=[]
    for i,b in enumerate(books,1):
        folder=root/'batches'/f'{i:03}';folder.mkdir(parents=True)
        whole.save_csv(folder/'cohort.csv',[b],list(b))
        atomic(folder/'record_packet.json',{b['catalog_item_id']:dict(catalog=b,acquisitions=[],observations=[dict(inventory_observation_id='O'+str(i),normalized_isbn13=ISBN)])})
        atomic(folder/'notes.json',{b['catalog_item_id']:'Synthetic evidence'})
        atomic(folder/'condition_policy.json',dict(catalog_item_ids=[b['catalog_item_id']],mode='labelled_used_scenarios',physical_grading='defer_until_handled',default_grade=None,publication='disabled'))
        batches.append(dict(number=i,folder=str(folder.relative_to(root)),books=1,inputs={name:whole.sha(folder/name) for name in ('cohort.csv','record_packet.json','notes.json','condition_policy.json')}))
    atomic(root/'protected_before.json',whole.protected(project));atomic(root/'manifest.json',dict(project=str(project),batches=batches,remaining_records=n,previously_reviewed=130,cohort_sha256=whole.sha(root/'cohort.csv'),rule_fingerprints=whole.rules()))
    atomic(root/'status.json',dict(state='ready',completed_books=0,completed_batches=0,requests=0,updated_at='test'))
    return root,project


def fake_requests(request,timeout):
    if request.get_method()=='POST':return dict(access_token='SYNTHETIC-TOKEN',expires_in=7200)
    if 'item_summary' in request.full_url:return dict(itemSummaries=[{'itemId':'v1|123|0'}])
    return dict(itemId='v1|123|0',itemWebUrl='https://www.ebay.com/itm/123',title='Synthetic Book',price={'value':'10','currency':'USD'},condition='Good',buyingOptions=['FIXED_PRICE'],localizedAspects=[dict(name='ISBN',value=ISBN),dict(name='Format',value='Paperback')])


def patch_source(monkeypatch):
    monkeypatch.setattr(whole,'default_request_json',fake_requests)
    def quota(c,root,ledger):return ledger.update(5000,'2099-01-01T00:00:00Z')
    monkeypatch.setattr(whole,'refresh_quota',quota)
    # All production guard and normalization logic still runs, without real waiting/network.
    from valuation.live_valuation_pilot import collect
    def fast(*a,**kwargs):kwargs['delay']=0;return collect(*a,**kwargs)
    monkeypatch.setattr(whole,'collect',fast)


def test_remaining_scope_is_deterministic_disjoint_and_checks_prior_records():
    books=[dict(catalog_item_id=str(i)) for i in range(100)]
    result=whole.remaining_records(books,{'1','2'})
    assert result==whole.remaining_records(list(reversed(books)),{'1','2'})
    assert len(result)==98 and not {'1','2'}&{r['catalog_item_id'] for r in result}
    with pytest.raises(ValueError):whole.remaining_records(books,{'absent'})
    with pytest.raises(ValueError):whole.remaining_records(books+[books[0]],set())


def test_quota_ledger_never_trusts_increased_stale_telemetry(tmp_path):
    ledger=whole.QuotaLedger(tmp_path/'quota.json',clock=lambda:1000)
    reset=datetime.fromtimestamp(2000,timezone.utc).isoformat();ledger.update(600,reset)
    for _ in range(101):ledger.charge()
    assert not ledger.ready()
    assert ledger.update(590,reset)['remaining']==499
    assert ledger.update(450,reset)['remaining']==450
    assert ledger.update(5000,datetime.fromtimestamp(3000,timezone.utc).isoformat())['remaining']==5000


def test_quota_expiry_and_reserve_stop_before_network(tmp_path):
    value=[1000];ledger=whole.QuotaLedger(tmp_path/'quota.json',clock=lambda:value[0]);reset=datetime.fromtimestamp(2000,timezone.utc).isoformat()
    ledger.update(100,reset)
    with pytest.raises(whole.QuotaPause):ledger.charge()
    ledger.update(99,reset);assert not ledger.ready()
    value[0]=2001
    with pytest.raises(whole.QuotaPause):ledger.charge()
    with pytest.raises(ValueError):ledger.update(5000,reset)


def test_all_batches_continue_without_permission_and_never_change_estimates(tmp_path,monkeypatch):
    root,project=fixture(tmp_path);patch_source(monkeypatch);before=whole.protected(project)
    assert whole.run(root,CREDS)=='complete'
    status=json.loads((root/'status.json').read_text());assert status['completed_books']==2 and status['completed_batches']==2
    assert whole.protected(project)==before
    for path in root.glob('batches/*/result.json'):
        result=json.loads(path.read_text());assert result['summary']['condition_checks_deferred']==1 and result['summary']['estimates_changed']==0
    assert whole.run(root,CREDS)=='complete'


def test_quota_wait_is_durable_and_resumes_automatically(tmp_path,monkeypatch):
    root,_=fixture(tmp_path,1);patch_source(monkeypatch)
    monkeypatch.setattr(whole,'refresh_quota',lambda c,r,l:l.update(450,'2099-01-01T00:00:00Z'))
    assert whole.run(root,CREDS,once=True)=='waiting_for_quota'
    status=json.loads((root/'status.json').read_text());assert status['next_attempt_at']>whole.now()
    assert not (root/'batches/001/collection').exists()
    status['next_attempt_at']=0;atomic(root/'status.json',status)
    # Represent a new account quota window, not stale telemetry inside the old one.
    monkeypatch.setattr(whole,'refresh_quota',lambda c,r,l:l.update(5000,'2099-01-02T00:00:00Z'))
    assert whole.run(root,CREDS)=='complete'


def test_canonical_change_causes_persistent_critical_stop(tmp_path,monkeypatch):
    root,project=fixture(tmp_path,1);patch_source(monkeypatch)
    (project/'data/new_decision.json').write_text('{}')
    assert whole.run(root,CREDS)=='critical_stop'
    assert (root/'critical_stop.json').exists() and not (root/'batches/001/collection').exists()
    assert whole.run(root,CREDS)=='critical_stop'


def test_completed_report_tampering_stops_before_next_batch(tmp_path,monkeypatch):
    root,_=fixture(tmp_path);patch_source(monkeypatch)
    assert whole.run(root,CREDS,once=True)=='batch_complete'
    result=json.loads((root/'batches/001/result.json').read_text());p=root/'batches/001'/result['report'];p.write_text('changed')
    assert whole.run(root,CREDS)=='critical_stop'
    assert not (root/'batches/002/collection').exists()


def test_crash_after_result_before_status_is_recovered_from_receipts(tmp_path,monkeypatch):
    root,_=fixture(tmp_path);patch_source(monkeypatch)
    assert whole.run(root,CREDS,once=True)=='batch_complete'
    status=json.loads((root/'status.json').read_text());status.update(completed_books=0,requests=0);atomic(root/'status.json',status)
    assert whole.run(root,CREDS)=='complete'
    assert json.loads((root/'status.json').read_text())['completed_books']==2


def test_incomplete_derived_csv_is_repaired_with_zero_source_calls(tmp_path,monkeypatch):
    root,_=fixture(tmp_path,1);patch_source(monkeypatch)
    original=whole.review_batch
    monkeypatch.setattr(whole,'review_batch',lambda folder:(_ for _ in ()).throw(ValueError('synthetic crash before report')))
    assert whole.run(root,CREDS)=='critical_stop'
    folder=root/'batches/001';(folder/'collection/observations.csv').unlink()
    status=json.loads((root/'status.json').read_text());status['state']='ready';atomic(root/'status.json',status)
    (root/'critical_stop.json').unlink();monkeypatch.setattr(whole,'review_batch',original)
    monkeypatch.setattr(whole,'default_request_json',lambda *a:(_ for _ in ()).throw(AssertionError('No source calls allowed')))
    assert whole.run(root,CREDS)=='complete'


def test_critical_marker_cannot_be_bypassed_by_stale_status(tmp_path,monkeypatch):
    root,_=fixture(tmp_path,1);patch_source(monkeypatch);atomic(root/'critical_stop.json',dict(issue='critical'))
    assert whole.run(root,CREDS)=='critical_stop'
    assert not (root/'batches/001/collection').exists()


def test_access_failure_stops_instead_of_retrying_or_publishing(tmp_path,monkeypatch):
    root,_=fixture(tmp_path,1);patch_source(monkeypatch)
    monkeypatch.setattr(whole,'refresh_quota',lambda *a:(_ for _ in ()).throw(EbayRequestError('synthetic secret',status_code=403)))
    assert whole.run(root,CREDS)=='critical_stop'
    text=(root/'critical_stop.json').read_text();assert 'synthetic secret' not in text
    assert json.loads(text)['issue']=='access_failure'


def test_transient_network_failure_is_durably_scheduled_for_retry(tmp_path,monkeypatch):
    root,_=fixture(tmp_path,1);patch_source(monkeypatch)
    monkeypatch.setattr(whole,'refresh_quota',lambda *a:(_ for _ in ()).throw(EbayRequestError('temporary',failure_kind='network')))
    assert whole.run(root,CREDS,once=True)=='retrying'
    assert json.loads((root/'status.json').read_text())['next_attempt_at']>whole.now()
    assert not (root/'critical_stop.json').exists()


def test_launch_configuration_restarts_crashes_but_not_critical_or_complete_exits():
    from operations.install_whole_library_review import configuration
    c=configuration(Path('/project'),Path('/job'),Path('/private/credentials'),Path('/python'),Path('/logs'))
    assert c['KeepAlive']=={'SuccessfulExit':False} and c['RunAtLoad']
    assert c['ProgramArguments'][2]=='valuation.whole_library_review'
    assert '--root' in c['ProgramArguments'] and 'secret' not in str(c)
    assert c['ThrottleInterval']==60


def test_combined_outputs_mark_partial_scope_and_keep_grades_unassigned(tmp_path,monkeypatch):
    root,_=fixture(tmp_path);patch_source(monkeypatch)
    assert whole.run(root,CREDS,once=True)=='batch_complete'
    partial=json.loads((root/'reviewed_books.json').read_text())
    assert not partial['complete'] and partial['reviewed_records']==1 and partial['expected_records']==2
    assert whole.run(root,CREDS)=='complete'
    result=json.loads((root/'reviewed_books.json').read_text())
    assert result['complete'] and len(result['books'])==2 and result['publication']=='disabled'
    from valuation.offline_valuation_review import read_csv
    scenarios=read_csv(root/'review_scenarios.csv')
    assert len(scenarios)==2 and all(r['actual_condition']=='ungraded' and r['publishable']=='False' for r in scenarios)
    assert (root/'research_exceptions.csv').exists() and (root/'deferred_physical_checks.csv').exists()
