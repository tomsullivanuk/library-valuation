from datetime import date
import copy
import pytest
from valuation.market_flag_adjudication import fields,page_offer,working_groups,adjudicate

ISBN='9780198809647'
TODAY=date(2026,11,16)


def receipt(**changes):
    r=dict(url='https://www.abebooks.com/example/1234/bd',observed_at='2026-11-16T15:00:00Z',role='used_context',source_observation_id='A1',details='Title\nExample\nPublisher\nExample Press\nPublication year\n2020\nCondition\nGood\nBinding\nPaperback\nISBN 13\n'+ISBN,price_context='Condition: Used - Good\nUS$ 12.50\nUS$ 4.99 shipping')
    r.update(changes);return r


def offer(i,price,**changes):
    r=dict(source='ebay_active_listings',url=f'https://www.ebay.com/itm/{i}',isbn=ISBN,binding='paperback',grade='good',native_grade='Good',price=str(price),currency='USD',observed_at='2026-11-08')
    r.update(changes);return r


def test_page_identity_is_returned_metadata_not_query_and_shipping_excluded():
    o=page_offer(receipt(),ISBN,TODAY)
    assert o['eligible'] and o['price']=='12.50'
    assert not page_offer(receipt(), '9780715619032',TODAY)['eligible']
    assert 'different_listing_isbn' in page_offer(receipt(), '9780715619032',TODAY)['issues']
    assert not page_offer(receipt(details=''),ISBN,TODAY)['eligible']
    assert not page_offer(receipt(),ISBN,date(2027,1,1))['eligible']


def test_fair_and_as_new_are_not_translated_to_ebay_grades():
    for label in ['Fair','As New','Near Fine','Fine']:
        r=receipt();r['details']=r['details'].replace('Condition\nGood','Condition\n'+label)
        o=page_offer(r,ISBN,TODAY)
        assert o['native_grade']==label and not o['eligible']


def test_pool_only_matching_grade_format_currency_and_keep_thin_groups():
    rows=[offer(1,10),offer(2,12),offer(3,14,source='abebooks',url='https://www.abebooks.com/example/3/bd'),offer(4,9,binding='hardcover'),offer(5,8,grade='very_good'),offer(6,7,currency='GBP')]
    groups,_=working_groups(rows)
    supported=[g for g in groups if g['supported']]
    assert len(supported)==1 and supported[0]['low']=='10' and supported[0]['high']=='14'
    assert len(supported[0]['sources'])==2
    assert len(groups)==4


def test_isolated_high_outlier_is_held_not_deleted_and_inputs_unchanged():
    rows=[offer(i,p) for i,p in enumerate([10,11,12,80],1)];before=copy.deepcopy(rows)
    groups,decisions=working_groups(rows)
    assert groups[0]['supported'] and groups[0]['high']=='12'
    assert len(groups[0]['held'])==1 and len(decisions)==4 and rows==before


def test_cheaper_new_requires_two_distinct_matching_binding_currency_offers():
    rows=[offer(1,40),offer(2,42),offer(3,44),offer(4,20,grade='new')]
    assert not any(r['hold'] for r in working_groups(rows)[1])
    rows.append(offer(5,22,grade='new',binding='hardcover'))
    assert not any(r['hold'] for r in working_groups(rows)[1])
    rows.append(offer(6,23,grade='new'))
    assert sum(r['hold']=='above_two_matching_new_offers' for r in working_groups(rows)[1])==3


def test_conflicting_duplicate_never_increases_support():
    rows=[offer(1,10),offer(1,99),offer(2,11),offer(3,12)]
    groups,decisions=working_groups(rows)
    assert not groups[0]['supported']
    assert any(o['hold']=='duplicate_metadata_conflict' for o in decisions)


def test_large_spread_kept_for_research_not_a_proposed_range():
    groups,_=working_groups([offer(1,10),offer(2,20),offer(3,40)])
    assert not groups[0]['supported']


def test_old_offer_identity_check_does_not_claim_historical_proof():
    book=dict(catalog_item_id='BK1',isbn13=ISBN,isbn10='',title='Example',location_summary='1',estimated_value_precise_low='10',estimated_value_precise_high='15',estimated_value_currency='USD',reviewed_estimate_id='')
    raw=[dict(review_disposition='retained_candidate',listing_isbn13=ISBN,listing_isbn10='',asking_price=str(p),listing_binding='paperback',listing_condition_grade='good',observation_date='2026-11-08',listing_url=f'https://www.ebay.com/itm/{i}',currency='USD') for i,p in enumerate([20,22,25],100)]
    detailed=dict(identity_supported_from_records=True,listing_decisions=raw)
    old=receipt(role='previous_range');old['details']=old['details'].replace(ISBN,'9780715619032')
    r=adjudicate(book,{},detailed,[receipt(),old],[],TODAY)
    assert r['status']=='cross_source_conditional_range'
    assert r['previous_offer_checks'][0]['different_edition']
    assert not r['previous_offer_checks'][0]['historical_metadata_verified']
    assert not r['publishable'] and r['actual_condition']=='ungraded'
    book['reviewed_estimate_id']='EST-1'
    assert adjudicate(book,{},detailed,[receipt()],[],TODAY)['status']=='saved_review_protected'


@pytest.mark.parametrize('blocked',[False,True])
def test_incomplete_or_blocked_page_review_fails_before_writing(tmp_path,blocked):
    import json
    from valuation.market_flag_adjudication import build
    root=tmp_path/'inputs';root.mkdir();output=tmp_path/'output';original=tmp_path/'original.json'
    docs={'scope.json':dict(flagged=['BK1'],pilots=[]),'source_records_with_pilots.json':dict(unchanged=True,current_books=[dict(catalog_item_id='BK1')]),'listing_details.json':[dict(url='https://www.abebooks.com/example/1234/bd',blocked=True)] if blocked else [],'full_listing_plan.json':[dict(url='https://www.abebooks.com/example/1234/bd')],'previous_observations.json':{},'pilot_decisions.json':[],'all_source_notes.json':[]}
    for name,value in docs.items():(root/name).write_text(json.dumps(value))
    original.write_text(json.dumps(dict(books=[dict(catalog_item_id='BK1')])) )
    with pytest.raises(ValueError,match='access block|incomplete'):build(root,original,output,TODAY)
    assert not output.exists()
