from copy import deepcopy
import pytest
from tests.test_market_flag_adjudication import receipt,ISBN,TODAY
from valuation.remaining_market_research import reviewed_page,resolve,build
from valuation.market_flag_adjudication import working_groups


def book():
    return dict(catalog_item_id='BK1',title='Example',isbn13=ISBN,isbn10='',
        location_summary='1',estimated_value_precise_low='10',estimated_value_precise_high='20',
        estimated_value_currency='USD',reviewed_estimate_id='')


def details():return dict(identity_supported_from_records=True,listing_decisions=[],recorded_source_notes=[])


def pages(prices=(10,11,12)):
    return [receipt(url=f'https://www.abebooks.com/example/{100+i}/bd',price_context=f'US$ {p}') for i,p in enumerate(prices)]


def test_supported_ranges_are_read_only_and_ungraded():
    b=book();d=details();p=pages();before=deepcopy((b,d,p))
    r=resolve(b,d,p,TODAY)
    assert r['outcome']=='conditional_proposal'
    assert r['supported_groups'][0]['low']=='10' and r['supported_groups'][0]['high']=='12'
    assert not r['publishable'] and r['actual_condition']=='ungraded' and (b,d,p)==before
    b['reviewed_estimate_id']='EST1'
    assert resolve(b,d,p,TODAY)['outcome']=='saved_review_protected'
    assert not resolve(b,d,p,TODAY)['supported_groups']


def test_native_labels_are_separate_from_ebay_grade_equivalents():
    native=receipt();native['details']=native['details'].replace('Condition\nGood','Condition\nFair')
    n=reviewed_page(native,ISBN,'Example',TODAY);assert n['eligible'] and n['grade']=='AbeBooks label: fair'
    ordinary=reviewed_page(receipt(url='https://www.abebooks.com/example/4321/bd'),ISBN,'Example',TODAY)
    assert len(working_groups([n,ordinary])[0])==2


@pytest.mark.parametrize('changes',[{'unavailable':True},{'price_context':'US$ 12.50 This specific item is no longer available.'}])
def test_inactive_listing_is_context_not_support(changes):
    o=reviewed_page(receipt(**changes),ISBN,'Example',TODAY)
    assert not o['eligible'] and 'listing_no_longer_available' in o['issues']


def test_wrong_edition_and_wrong_volume_do_not_support_a_proposal():
    assert not reviewed_page(receipt(), '9780715619032','Example',TODAY)['eligible']
    r=receipt();r['details']=r['details'].replace('Title\nExample','Title\nExample Volume 2')
    assert not reviewed_page(r,ISBN,'Example Volume 1',TODAY)['eligible']


@pytest.mark.parametrize('prices,outcome',[((), 'no_eligible_used_offers'),((10,11),'too_few_comparable_offers'),((10,20,40),'prices_too_widely_spread')])
def test_evidence_gaps_have_concrete_distinct_outcomes(prices,outcome):
    assert resolve(book(),details(),pages(prices),TODAY)['outcome']==outcome


def test_preserved_profile_is_not_a_guessed_physical_isbn():
    b=book();b['isbn13']='';d=details();d.update(identity_supported_from_records=False,recorded_source_notes=['Example Press, 1967 printing; no ISBN shown.'])
    r=resolve(b,d,pages(),TODAY)
    assert r['outcome']=='edition_profile_research' and not r['supported_groups']
    assert b['isbn13']=='' and not any('physical_check' in k for k in r)


def test_incomplete_or_blocked_coverage_cannot_be_called_complete():
    p=pages();plan=[dict(url=r['url'],books=[dict(catalog_item_id='BK1')]) for r in p]
    with pytest.raises(ValueError,match='incomplete'):build(['BK1'],{'BK1':book()},{'BK1':details()},plan,p[:-1],TODAY)
    p[0]['blocked']=True
    with pytest.raises(ValueError,match='Blocked'):build(['BK1'],{'BK1':book()},{'BK1':details()},plan,p,TODAY)
