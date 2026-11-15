from datetime import date
import pytest
from valuation.combined_market_review import compare_book, ebay_scenarios, abe_context

TODAY=date(2026,11,15)
ISBN='9780198809647'

def fixture():
    b=dict(catalog_item_id='BK1',title='History of Continua',author='Stewart Shapiro',isbn13=ISBN,isbn10='',
           location_summary='1',copy_count=1,estimated_value_precise_low='10',estimated_value_precise_high='15',
           estimated_value_currency='USD',resale_market_summary='$10–$15',usable_market_estimate=True,reviewed_estimate_id='')
    offers=[dict(price=p,url=f'https://www.ebay.com/itm/{i}',date='2026-11-08',isbn=ISBN) for i,p in enumerate(['20','22','25'],100)]
    s=dict(currency='USD',offers=offers,low='20',high='25',listing_count=3,publishable=False,scenario_only=True,stronger=True,listing_binding='paperback',hypothetical_grade='good')
    previous=dict(scenarios=[s],physical_tasks=[],pilot_identification_checks=[])
    a=[dict(observation_id='A1',catalog_id='BK1',source='abebooks',lookup_status='observed',observation_date='2026-11-11',
            listing_url='https://www.abebooks.com/example/1234/bd',asking_price='5',currency='USD',condition='Used - Good',
            listing_title=b['title'],listing_author=b['author'],lookup_strategy='isbn13',search_query=ISBN,
            isbn13=ISBN,isbn10='',match_confidence='high')]
    return b,previous,a


def test_query_confidence_never_verifies_abebooks_or_changes_ebay_range():
    b,p,a=fixture();result=compare_book(b,p,a,TODAY)
    assert result['status']=='price_context_review'
    assert result['proposals'][0]['low']=='20'
    assert result['proposals'][0]['abebooks_context']=='below_ebay'
    assert result['abebooks'][0]['independently_verified'] is False
    assert result['abebooks'][0]['offers'][0]['returned_isbn'] is None
    assert result['publishable'] is False
    assert b['estimated_value_precise_low']=='10'


def test_stale_or_changed_isbn_scenarios_are_not_proposed():
    b,p,a=fixture()
    assert not ebay_scenarios(b,p,date(2026,12,15))[0]['eligible_now']
    b['isbn13']='9780715619032'
    assert not ebay_scenarios(b,p,TODAY)[0]['eligible_now']


@pytest.mark.parametrize('change',['duplicate','bounds','count','publishable'])
def test_corrupt_retained_scenario_fails_closed(change):
    b,p,a=fixture();s=p['scenarios'][0]
    if change=='duplicate':s['offers'][1]['url']=s['offers'][0]['url']
    if change=='bounds':s['high']='99'
    if change=='count':s['listing_count']=5
    if change=='publishable':s['publishable']=True
    with pytest.raises(ValueError):ebay_scenarios(b,p,TODAY)


def test_native_grades_new_prices_and_currencies_stay_separate():
    b,p,a=fixture()
    for idx,grade,currency in [(2,'Used - Fair','USD'),(3,'New','USD'),(4,'Used - Good','GBP')]:
        r=dict(a[0],observation_id=f'A{idx}',condition=grade,currency=currency,listing_url=f'https://www.abebooks.com/example/{idx}/bd');a.append(r)
    g,held=abe_context(b,a,TODAY)
    assert len(g)==4 and not held
    assert sum(x['used'] for x in g)==3
    r=compare_book(b,p,a,TODAY)
    assert any('new AbeBooks' in f for f in r['proposals'][0]['flags'])
    assert r['proposals'][0]['currency']=='USD'


def test_saved_review_and_existing_checks_block_routine_proposal():
    b,p,a=fixture();p['physical_tasks']=[dict(kind='binding',question='Check binding')]
    p['pilot_identification_checks']=[dict(question='Old pilot question')]
    result=compare_book(b,p,a,TODAY)
    assert result['status']=='physical_identity_check'
    assert len(result['physical_questions'])==1
    assert any('pilot' in step for step in result['research_next_steps'])
    b['reviewed_estimate_id']='EST-1'
    assert compare_book(b,p,a,TODAY)['status']=='saved_review_protected'


def test_no_eligible_ebay_does_not_promote_abe_context_to_replacement():
    b,p,a=fixture();p['scenarios'][0]['stronger']=False
    r=compare_book(b,p,a,TODAY)
    assert not r['proposals'] and r['status']=='more_market_evidence'
    assert r['abebooks']
