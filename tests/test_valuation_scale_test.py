from collections import Counter
from copy import deepcopy
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest
from valuation.valuation_scale_test import select_cohort,GROUPS
from valuation.live_valuation_pilot import PilotApi
from valuation.ebay_access import EbayCredentials


def records():
    result=[]
    for group,_ in GROUPS:
        for i in range(45):
            result.append(dict(catalog_item_id=f'{group}-{i}',title='Synthetic',isbn13='' if group=='missing_isbn' else '9780198829171',previous_confidence='ambiguous_edition_match' if group=='edition_flags' else 'unknown_market_confidence' if group=='uncertain_prices' else 'thin_market_evidence',copy_count=2 if group=='multiple_copies' else 1,usable_market_estimate=group.startswith('usable'),currency='USD',previous_high='10' if group=='usable_low' else '40' if group=='usable_mid' else '100'))
    return result


def test_100_book_sample_is_deterministic_disjoint_and_covers_strata():
    source=records();before=deepcopy(source)
    a=select_cohort(source,{'usable_high-1'});b=select_cohort(list(reversed(source)),{'usable_high-1'})
    assert a==b and len(a)==len({r['catalog_item_id'] for r in a})==100
    assert Counter(r['group'] for r in a)==dict(GROUPS)
    assert not any(r['catalog_item_id']=='usable_high-1' for r in a)
    assert source==before
    assert len({r['group'] for r in a[:25]})==8


def test_sample_rejects_duplicate_identity_and_insufficient_pool():
    rs=records()
    with pytest.raises(ValueError,match='Duplicate'):select_cohort(rs+[rs[0]])
    with pytest.raises(ValueError,match='Insufficient'):select_cohort(rs[:3])


def test_used_preferred_missing_isbn_remains_a_title_search_with_used_filter():
    seen=[];state={'manifest':{'request_budget':3,'search_mode':'used_preferred'},'request_count':0}
    def request(req,timeout):
        seen.append(req.full_url)
        return {'access_token':'synthetic','expires_in':7200} if req.get_method()=='POST' else {'itemSummaries':[]}
    api=PilotApi(EbayCredentials('id','secret','EBAY_US','production'),state,lambda:None,request_json=request,sleep=lambda _:None)
    result=api.search(dict(catalog_item_id='BK1',title='Synthetic Book',author='Author',isbn13=''),10)
    from urllib.parse import parse_qs,urlsplit
    query=parse_qs(urlsplit(seen[1]).query)
    assert query['q']==['Synthetic Book Author'] and 'conditions:{USED}' in query['filter'][0]
    assert result['strategy']=='used_title_author' and len(seen)==2


def test_real_process_termination_resumes_persisted_details_without_refetch(tmp_path):
    script=r'''
import csv,json,sys,time
from pathlib import Path
from valuation.live_valuation_pilot import collect
from valuation.ebay_access import EbayCredentials
root=Path(sys.argv[1]);phase=sys.argv[2]
class Fake:
 def __init__(self,*a,**k):self.cid=''
 def log(self,kind,item=''):
  with (root/'events').open('a') as f:f.write(json.dumps([phase,kind,self.cid,item])+'\n');f.flush()
 def search(self,b,limit):
  self.cid=b['catalog_item_id'];self.log('search');return dict(query='synthetic',strategy='used_isbn_keyword',item_ids=['v1|1|0','v1|2|0','v1|3|0'])
 def detail(self,id):
  self.log('detail',id)
  if phase=='first' and self.cid=='BK2' and id=='v1|2|0':
   (root/'ready').write_text('ready');time.sleep(30)
  return dict(itemId=id,title='Synthetic',price={'value':'10','currency':'USD'},buyingOptions=['FIXED_PRICE'])
collect(root/'cohort.csv',root/'collection',EbayCredentials('id','secret','EBAY_US','production'),api_factory=Fake,progress=lambda _:None)
'''
    cohort=tmp_path/'cohort.csv'
    with cohort.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['catalog_item_id','title']);w.writeheader();w.writerows([dict(catalog_item_id='BK1',title='Synthetic'),dict(catalog_item_id='BK2',title='Synthetic')])
    child=subprocess.Popen([sys.executable,'-c',script,str(tmp_path),'first'])
    try:
        deadline=time.monotonic()+10
        while not (tmp_path/'ready').exists() and time.monotonic()<deadline:
            assert child.poll() is None;time.sleep(.01)
        assert (tmp_path/'ready').exists()
        child.terminate();child.wait(timeout=5)
        before=json.loads((tmp_path/'collection/checkpoint.json').read_text())
        assert before['books']['BK1']['completed'] and len(before['books']['BK2']['details'])==1
        subprocess.run([sys.executable,'-c',script,str(tmp_path),'resume'],check=True,timeout=10)
        after=json.loads((tmp_path/'collection/checkpoint.json').read_text())
        assert after['status']=='complete'
        for cid,b in before['books'].items():
            for key,value in b['details'].items():assert after['books'][cid]['details'][key]==value
        resumed=[json.loads(x) for x in (tmp_path/'events').read_text().splitlines() if json.loads(x)[0]=='resume']
        assert [e[1] for e in resumed]==['detail','detail']
        assert [e[3] for e in resumed]==['v1|2|0','v1|3|0']
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=5)


def test_recovery_verifier_rejects_repeated_work_or_changed_details():
    from valuation.valuation_scale_test import verify_recovery
    paused=dict(manifest={'cohort':'frozen'},request_count=3,books={'BK1':dict(completed=True,search={},details={'one':{'price':'10'}}),'BK2':dict(search={},details={'two':{'price':'20'}})})
    resumed=deepcopy(paused);resumed.update(status='complete',request_count=5);resumed['books']['BK2']['completed']=True
    assert verify_recovery(paused,resumed,[])['status']=='passed'
    for operation,item in [('search',None),('detail','two')]:
        with pytest.raises(ValueError,match='repeated'):verify_recovery(paused,resumed,[dict(phase='after_interruption',catalog_item_id='BK2',operation=operation,item_id=item)])
    changed=deepcopy(resumed);changed['books']['BK1']['details']['one']['price']='11'
    with pytest.raises(ValueError,match='changed'):verify_recovery(paused,changed,[])


def scale_fixture(root):
    import hashlib
    from valuation.live_valuation_pilot import FIELDS,atomic
    books=[dict(catalog_item_id=f'BK{i:03}',title='Synthetic book',author='Synthetic Author',isbn13='9780198829171',group='test',previous_low='8',previous_high='12',currency='USD') for i in range(100)]
    def save(path,rows,fields):
        with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    save(root/'cohort.csv',books,list(books[0]));packet={}
    for b in books:
        cid=b['catalog_item_id'];packet[cid]=dict(catalog=b,acquisitions=[],observations=[dict(inventory_observation_id=cid,normalized_isbn13=b['isbn13'])])
    atomic(root/'record_packet.json',packet);atomic(root/'review_notes.json',{b['catalog_item_id']:'Synthetic review' for b in books})
    atomic(root/'condition_policy.json',dict(mode='labelled_used_scenarios',physical_grading='defer_until_handled',publication='disabled',catalog_item_ids=[b['catalog_item_id'] for b in books],default_grade=None))
    atomic(root/'manifest.json',dict(cohort_sha256=hashlib.sha256((root/'cohort.csv').read_bytes()).hexdigest()))
    for n in range(1,5):
        batch=books[(n-1)*25:n*25];p=root/f'batch_{n}.csv';save(p,batch,list(books[0]))
        out=root/f'collection_{n}';out.mkdir()
        state=dict(manifest=dict(pilot_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),catalog_ids=[b['catalog_item_id'] for b in batch],request_budget=400,search_mode='used_preferred'),started_at='2026-11-06T00:00:00Z',request_count=25,status='complete',books={b['catalog_item_id']:dict(completed=True,search={'item_ids':[]},details={}) for b in batch})
        atomic(out/'checkpoint.json',state)
        rows=[]
        for b in batch:
            r=dict.fromkeys(FIELDS,'');r.update(catalog_id=b['catalog_item_id'],source='ebay_active_listings',lookup_status='no_results',observation_date=state['started_at'],detail_status='no_results');rows.append(r)
        save(out/'observations.csv',rows,FIELDS)
        if n==1:
            paused=deepcopy(state);paused.pop('status');paused['books'][batch[1]['catalog_item_id']]['completed']=False;atomic(root/'interrupted_checkpoint.json',paused);atomic(out/'request_events.json',[])


def test_scale_report_accounts_for_all_100_no_result_books_and_preserves_inputs(tmp_path):
    from valuation.valuation_scale_test import build_scale_report
    scale_fixture(tmp_path);before=(tmp_path/'record_packet.json').read_bytes()
    result=build_scale_report(tmp_path,as_of='2026-11-06')
    assert result['selected_books']==100 and result['collection']['api_requests']==100
    assert result['record_review']['books_without_used_context']==100
    assert result['record_review']['condition_checks_deferred']==100 and result['estimates_changed']==0
    assert (tmp_path/'record_packet.json').read_bytes()==before
    assert 'Review all 100 books' in (tmp_path/'index.html').read_text()
    with pytest.raises(ValueError,match='Prior report'):build_scale_report(tmp_path,as_of='2026-11-06')


def test_scale_report_refuses_materialized_evidence_that_differs_from_checkpoint(tmp_path):
    from valuation.valuation_scale_test import build_scale_report
    scale_fixture(tmp_path)
    p=tmp_path/'collection_2/observations.csv';p.write_text(p.read_text().replace('no_results','observed'))
    with pytest.raises(ValueError,match='durable checkpoint'):build_scale_report(tmp_path,as_of='2026-11-06')
    assert not (tmp_path/'review').exists()
