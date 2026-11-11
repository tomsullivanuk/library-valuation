import csv
import json
from pathlib import Path
import urllib.parse

import pytest
from valuation.ebay_access import EbayCredentials,EbayRequestError
from valuation.live_valuation_pilot import collect,normalize_detail,PilotApi,condition_grade

CREDS=EbayCredentials('synthetic-id','synthetic-secret','EBAY_US','production')
BOOK=dict(catalog_item_id='BK1',title='Example Philosophy',author='Alice Scholar',isbn13='9780198829171')

def item(n='1'):
    return dict(itemId='v1|'+n+'|0',title='Example Philosophy',price={'value':'12','currency':'USD'},
                buyingOptions=['FIXED_PRICE'],itemWebUrl='https://www.ebay.com/itm/'+n,condition='Very Good',
                localizedAspects=[{'name':'ISBN','value':'9780198829171'},{'name':'Format','value':'Paperback'},
                                  {'name':'Author','value':'Alice Scholar'},{'name':'Publisher','value':'Example Press'}],
                seller={'username':'DO-NOT-SAVE'},description='PRIVATE RAW DESCRIPTION')

def normalized(payload):return normalize_detail(payload,BOOK,BOOK['isbn13'],'gtin',observed_at='2026-11-06T00:00:00Z')

def pilot(tmp_path,n=2):
    p=tmp_path/'pilot.csv';rows=[dict(BOOK,catalog_item_id='BK'+str(i)) for i in range(n)]
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return p


def test_details_capture_actual_metadata_and_exclude_seller_payload():
    r=normalized(item())
    assert r['listing_isbn13']==BOOK['isbn13'] and r['listing_binding']=='paperback'
    assert r['listing_condition_grade']=='very_good' and r['listing_author']=='Alice Scholar'
    assert 'DO-NOT-SAVE' not in json.dumps(r) and 'PRIVATE RAW' not in json.dumps(r)


def test_missing_returned_isbn_stays_missing_despite_isbn_query():
    i=item();i['localizedAspects']=[]
    r=normalized(i);assert r['listing_isbn13']=='' and r['listing_binding']==''


def test_product_gtins_aspects_and_isbn10_equivalence():
    i=item();i['localizedAspects']=[]
    i['product']={'gtins':['0198829175'],'aspectGroups':[{'aspects':[{'localizedName':'Format','localizedValues':['Softcover']}]}]}
    r=normalized(i);assert r['listing_isbn13']==BOOK['isbn13'] and r['listing_binding']=='paperback'


def test_conflicting_isbns_and_binding_remain_unknown():
    i=item();i['gtin']='9780486600819'
    r=normalized(i);assert r['listing_isbn13']=='' and r['detail_status']=='conflicting_isbns'
    i=item();i['localizedAspects'].append({'name':'Binding','value':'Hardcover'})
    assert normalized(i)['listing_binding']==''


def test_auction_and_external_urls_are_not_accepted_as_fixed_price_evidence():
    i=item();i['buyingOptions']=['AUCTION'];i['itemWebUrl']='https://not-ebay.test/token'
    r=normalized(i);assert r['lookup_status']=='excluded_buying_option' and r['listing_url']==''

@pytest.mark.parametrize('raw,grade',[('Good','good'),('Very Good','very_good'),('Like New','like_new'),('Brand New','new'),('Used',''),('Acceptable','acceptable')])
def test_condition_mapping_does_not_guess_generic_used(raw,grade):assert condition_grade(raw)==grade


def test_requests_use_gtin_and_item_details_and_request_budget_is_persisted():
    seen=[];state={'manifest':{'request_budget':4},'request_count':0};saved=[]
    def request(req,timeout):
        seen.append(req)
        if req.get_method()=='POST':return {'access_token':'PRIVATE_TOKEN','expires_in':7200}
        if 'item_summary' in req.full_url:return {'itemSummaries':[{'itemId':'v1|1|0'}],'total':1}
        return item()
    api=PilotApi(CREDS,state,lambda:saved.append(state['request_count']),request_json=request,sleep=lambda _:None)
    search=api.search(BOOK,10);api.detail(search['item_ids'][0])
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(seen[1].full_url).query)['gtin']==[BOOK['isbn13']]
    assert 'fieldgroups=PRODUCT' in seen[2].full_url
    assert state['request_count']==3 and saved==[1,2,3]
    state['manifest']['request_budget']=3
    with pytest.raises(EbayRequestError):api.detail('v1|2|0')
    assert state['request_count']==3


def test_checkpoint_resume_retains_completed_details_and_never_stores_errors_or_raw_payload(tmp_path):
    p=pilot(tmp_path);out=tmp_path/'run';calls=[]
    class Fake:
        fail=True
        def __init__(self,*args,**kwargs):pass
        def search(self,b,limit):return dict(query='example',strategy='title_author',item_ids=['v1|1|0','v1|2|0'])
        def detail(self,id):
            calls.append(id)
            if id=='v1|2|0' and Fake.fail:raise EbayRequestError('PRIVATE_SECRET',status_code=429)
            return item(id.split('|')[1])
    with pytest.raises(RuntimeError,match='paused'):
        collect(p,out,CREDS,api_factory=Fake,progress=lambda _:None)
    text=(out/'checkpoint.json').read_text();assert 'PRIVATE_SECRET' not in text and 'DO-NOT-SAVE' not in text
    Fake.fail=False
    s=collect(p,out,CREDS,api_factory=Fake,progress=lambda _:None)
    assert s['status']=='complete' and calls.count('v1|1|0')==2 # once per book; first book wasn't refetched
    before=list(calls);collect(p,out,CREDS,api_factory=Fake,progress=lambda _:None);assert calls==before
    assert (out/'observations.csv').stat().st_mode & 0o777==0o600
    with pytest.raises(ValueError,match='Checkpoint differs'):
        collect(p,out,CREDS,max_results=3,api_factory=Fake)


def test_no_results_are_explicit_for_each_book_and_inputs_unchanged(tmp_path):
    p=pilot(tmp_path);before=p.read_bytes()
    class Empty:
        def __init__(self,*a,**k):pass
        def search(self,*a):return dict(item_ids=[],query='example',strategy='title_author')
    collect(p,tmp_path/'run',CREDS,api_factory=Empty,progress=lambda _:None)
    with (tmp_path/'run/observations.csv').open() as f:rows=list(csv.DictReader(f))
    assert len(rows)==2 and all(r['lookup_status']=='no_results' for r in rows)
    assert p.read_bytes()==before


def test_item_response_mismatch_pauses_and_no_metadata_is_saved(tmp_path):
    class Wrong:
        def __init__(self,*a,**k):pass
        def search(self,*a):return dict(item_ids=['v1|1|0'],query='example',strategy='title_author')
        def detail(self,*a):return item('2')
    with pytest.raises(RuntimeError,match='paused'):
        collect(pilot(tmp_path),tmp_path/'run',CREDS,api_factory=Wrong,progress=lambda _:None)
    assert not json.loads((tmp_path/'run/checkpoint.json').read_text())['books']['BK0']['details']


def test_invalid_limits_scope_and_data_destination_fail_before_requests(tmp_path):
    p=pilot(tmp_path)
    for kwargs in [dict(max_results=11),dict(request_budget=401)]:
        with pytest.raises(ValueError):collect(p,tmp_path/'run',CREDS,**kwargs)
    with pytest.raises(ValueError):collect(p,tmp_path/'data/run',CREDS)
    with pytest.raises(ValueError):collect(pilot(tmp_path,31),tmp_path/'run',CREDS)


def test_condition_notes_are_bounded_and_contact_details_are_not_saved():
    i=item();i['conditionDescription']='Good copy. Email seller@example.test or call 555-123-4567. https://example.test/private'
    r=normalized(i)
    assert 'seller@example.test' not in r['listing_condition_description']
    assert '555-123-4567' not in r['listing_condition_description']
    assert 'https://' not in r['listing_condition_description']
    assert r['listing_format_raw']=='Paperback'


def test_auth_retry_is_once_and_gtin_empty_falls_back_to_keyword():
    state={'manifest':{'request_budget':10},'request_count':0};searches=[];detail_calls=[];tokens=[]
    def request(req,timeout):
        if req.get_method()=='POST':tokens.append(1);return {'access_token':'PRIVATE_TOKEN','expires_in':7200}
        params=urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        if 'item_summary' in req.full_url:
            searches.append(params)
            return {'itemSummaries':[] if 'gtin' in params else [{'itemId':'v1|1|0'}]}
        detail_calls.append(1)
        if len(detail_calls)==1:raise EbayRequestError('Unauthorized',status_code=401)
        return item()
    api=PilotApi(CREDS,state,lambda:None,request_json=request,sleep=lambda _:None)
    s=api.search(BOOK,3);assert s['strategy']=='isbn_keyword'
    api.detail('v1|1|0')
    assert len(tokens)==2 and len(detail_calls)==2 and len(searches)==2
    assert state['request_count']==6


def test_used_followup_filters_used_and_never_broadens_empty_search():
    seen=[];state={'manifest':{'request_budget':3,'search_mode':'used_isbn'},'request_count':0}
    def request(req,timeout):
        seen.append(req)
        return {'access_token':'token','expires_in':7200} if req.get_method()=='POST' else {'itemSummaries':[]}
    api=PilotApi(CREDS,state,lambda:None,request_json=request,sleep=lambda _:None)
    result=api.search(BOOK,10)
    params=urllib.parse.parse_qs(urllib.parse.urlsplit(seen[1].full_url).query)
    assert params['q']==[BOOK['isbn13']]
    assert params['filter']==['buyingOptions:{FIXED_PRICE},conditions:{USED}']
    assert result['strategy']=='used_isbn_keyword' and len(seen)==2
    with pytest.raises(ValueError,match='valid ISBN'):api.search(dict(BOOK,isbn13=''),10)


def test_search_mode_is_pinned_for_resume(tmp_path):
    class Empty:
        def __init__(self,*a,**k):pass
        def search(self,*a):return dict(item_ids=[],query='example',strategy='used_isbn_keyword')
    p=pilot(tmp_path);out=tmp_path/'run'
    collect(p,out,CREDS,search_mode='used_isbn',api_factory=Empty,progress=lambda _:None)
    with pytest.raises(ValueError,match='Checkpoint differs'):collect(p,out,CREDS,api_factory=Empty)
