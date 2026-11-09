from copy import deepcopy
from datetime import date
import json
import re
import pytest

from valuation.valuation_comparison import assess_scenarios,compare_one,unique,render

TODAY=date(2026,11,9)
ISBN='9780198829171'


def example():
    current=dict(catalog_item_id='SYNTHETIC',title='Synthetic Book',low='20',high='24',currency='USD',usable=True)
    offers=[dict(source='ebay_active_listings',listing_url=f'https://www.ebay.com/itm/{i}',
                 asking_price=str(p),listing_condition_grade='good',listing_binding='paperback',
                 currency='USD',listing_isbn13=ISBN,observation_date='2026-11-07',
                 review_disposition='retained_candidate') for i,p in enumerate([10,11,12],1)]
    book=dict(actual_condition='ungraded',condition_assumed=False,publishable=False,
              listing_decisions=offers,identity_supported_from_records=True,identity_evidence=dict(target_isbn=ISBN),
              condition_scenarios=[dict(hypothetical_grade='good',listing_binding='paperback',currency='USD',
                                       low='10',high='12',listing_count=3,high_spread=False,
                                       scenario_only=True,publishable=False)])
    return current,book


def test_endpoint_comparison_uses_current_range_and_remains_hypothetical():
    current,book=example();before=deepcopy(book)
    result=compare_one(current,book,TODAY,[])
    assert result['category']=='lower' and result['material_change']
    assert float(result['scenarios'][0]['delta_low_percent'])==-50
    assert result['actual_condition']=='ungraded' and result['publishable'] is False
    assert book==before


def test_conditions_are_not_averaged_or_assigned():
    current,book=example();other=deepcopy(book['condition_scenarios'][0])
    other.update(hypothetical_grade='very_good',low='50',high='52')
    more=deepcopy(book['listing_decisions'])
    for i,d in enumerate(more):d.update(listing_condition_grade='very_good',asking_price=str(50+i),listing_url=f'https://www.ebay.com/itm/{i+10}')
    book['listing_decisions']+=more;book['condition_scenarios'].append(other)
    result=compare_one(current,book,TODAY,[])
    assert result['category']=='mixed' and len(result['scenarios'])==2
    assert 'proposed_low' not in result


@pytest.mark.parametrize('change',[{'listing_count':2},{'listing_binding':'unknown'},{'high_spread':True}])
def test_scenario_claims_must_match_retained_evidence(change):
    current,book=example();book['condition_scenarios'][0].update(change)
    with pytest.raises(ValueError):assess_scenarios(book,current,TODAY)


def test_currency_mismatch_missing_current_and_empty_evidence_are_not_zeroes():
    current,book=example();current['currency']='GBP'
    assert compare_one(current,book,TODAY,[])['category']=='no_current'
    current['usable']=False;current['low']='';current['high']=''
    assert not compare_one(current,book,TODAY,[])['material_change']
    assert compare_one(current,None,TODAY,[])['category']=='no_scenario'


def test_thin_unknown_identity_and_stale_offers_cannot_drive_large_change_flags():
    current,book=example()
    book['identity_supported_from_records']=False
    for d in book['listing_decisions']:d['observation_date']='2026-01-01'
    result=compare_one(current,book,TODAY,[])
    assert result['category']=='limited_only' and not result['material_change']


def test_duplicate_catalog_keys_and_assigned_grades_fail_closed():
    with pytest.raises(ValueError):unique([{'catalog_item_id':'A'},{'catalog_item_id':'A'}])
    current,book=example();book['actual_condition']='good'
    with pytest.raises(ValueError):assess_scenarios(book,current,TODAY)


def test_report_data_cannot_close_script_and_preserves_original_text(tmp_path):
    report={'unsafe':'</script><script>alert(1)</script>'}
    path=tmp_path/'report.html';render(report,path)
    text=path.read_text()
    encoded=re.search(r'<script id="data" type="application/json">(.*?)</script>',text,re.S)[1]
    assert '<' not in encoded and json.loads(encoded)==report


def test_legacy_pooled_binding_is_split_without_inventing_three_matching_offers():
    current,book=example()
    del book['condition_scenarios'][0]['listing_binding']
    book['listing_decisions'][-1]['listing_binding']='hardcover'
    result=compare_one(current,book,TODAY,[])
    assert len(result['scenarios'])==2
    assert result['category']=='limited_only' and result['stronger_scenarios']==0
    assert all(s['legacy_binding_split'] for s in result['scenarios'])
    assert all(s['evidence_label']==s['support_notes'] for s in result['scenarios'])
