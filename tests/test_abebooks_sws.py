from copy import deepcopy
from datetime import datetime,timezone
import gzip
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import pytest

from valuation.abebooks_sws import (OfflineSwsClient,ReplayTransport,ReplayResponse,ReplayClock,
    SwsError,search_plan,parse_response,preview,MAX_BYTES,OFFLINE_SOURCE)
from valuation.offline_valuation_review import review_book

FIXTURE=Path(__file__).parent/'fixtures/abebooks_sws/long_results.xml'
BOOK=dict(catalog_item_id='SYNTHETIC',title='Synthetic Methods',author='Synthetic Author',isbn13='9780198829171')
WHEN='2026-11-09T12:00:00+00:00'


def rows(body=None,book=None,headers=None,currency='USD'):
    b=book or BOOK
    return parse_response(ReplayResponse(200,FIXTURE.read_bytes() if body is None else body,headers or {}),
                          search_plan(b,currency=currency),b,observed_at=WHEN)


def xml(**changes):
    fields=dict(bookId='999999990001',isbn13=BOOK['isbn13'],title=BOOK['title'],author=BOOK['author'],
                listingPrice='12.00',itemCondition='Good',bindingType='S',
                listingUrl='https://www.abebooks.com/servlet/BookDetailsPL?bi=999999990001')
    fields.update(changes)
    from xml.sax.saxutils import escape
    return ('<Book>'+''.join('<'+k+'>'+escape(v)+'</'+k+'>' for k,v in fields.items() if v is not None)+'</Book>').encode()


def test_isbn_first_latin1_fallback_and_safe_repr():
    p=search_plan(BOOK);q=parse_qs(urlsplit(p.url).query)
    assert q['isbn']==[BOOK['isbn13']] and q['outputsize']==['long'] and q['bookcondition']==['used']
    assert q['maxresults']==['10'] and 'clientkey' not in p.parameters
    assert 'OFFLINE-SYNTHETIC-KEY' not in repr(p)
    p=search_plan(dict(BOOK,isbn13='',title='Hölderlin'))
    assert 'H%F6lderlin' in p.url and 'H%C3%B6' not in p.url
    p=search_plan(dict(BOOK,isbn13='invalid',isbn10='0198829175'))
    assert p.strategy=='isbn'


@pytest.mark.parametrize('kwargs',[dict(client_key='REAL-KEY-MUST-NOT-APPEAR'),dict(limit=11),dict(limit=True),dict(currency='euro')])
def test_invalid_requests_are_bounded_and_do_not_echo_secrets(kwargs):
    with pytest.raises(SwsError) as e:search_plan(BOOK,**kwargs)
    assert 'REAL-KEY-MUST-NOT-APPEAR' not in str(e.value)


def test_unsupported_unicode_does_not_silently_change_search():
    with pytest.raises(SwsError,match='Latin-1'):search_plan(dict(BOOK,isbn13='',title='哲學'))


def test_client_has_no_live_transport_and_does_not_accept_injected_network_clients():
    with pytest.raises(SwsError,match='live access is disabled'):OfflineSwsClient()
    with pytest.raises(SwsError):OfflineSwsClient(lambda *a:None)


def test_normalizes_documented_fields_without_inferring_target_or_vendor_currency():
    r=rows()[0]
    assert r['currency']=='USD' and r['vendor_currency']=='GBP' and r['asking_price']=='14.25'
    assert r['shipping_price']=='3.00' and r['total_listing_price']=='17.25'
    assert r['listing_binding']=='paperback' and r['listing_condition_grade']=='good'
    assert r['listing_isbn13']==BOOK['isbn13'] and r['quantity_available']=='14'
    assert r['source']==OFFLINE_SOURCE and 'cm_ven' not in r['listing_url']
    assert r['actual_condition']=='ungraded' and not r['publishable']


def test_missing_returned_isbn_is_not_filled_from_query():
    r=rows(xml(isbn13=None))[0]
    assert r['listing_isbn13']==''
    result=preview(BOOK,[r],as_of='2026-11-09')
    assert result['condition_scenarios']==[] and result['identity_held_candidates']==1


def test_wrong_and_conflicting_identifiers_cannot_support_scenarios():
    wrong=rows(xml(isbn13='9781567923254'))
    assert preview(BOOK,wrong,as_of='2026-11-09')['condition_scenarios']==[]
    conflict=rows(xml(isbn10='1567923259'))
    assert conflict[0]['lookup_status']=='metadata_conflict'
    assert preview(BOOK,conflict,as_of='2026-11-09')['condition_scenarios']==[]


@pytest.mark.parametrize('changes',[dict(title='Synthetic Methods Hardcover'),
    dict(listingCondition='NEW BOOK',itemCondition='Good'),dict(currency='EUR'),
    dict(firstBookShipCost='3.00',totalListingPrice='99.00'),dict(quantity='0')])
def test_contradictory_metadata_is_held(changes):
    r=rows(xml(**changes));assert r[0]['lookup_status']=='metadata_conflict'
    assert not preview(BOOK,r,as_of='2026-11-09')['condition_scenarios']


@pytest.mark.parametrize('native,expected',[('As New','as_new'),('Fine','fine'),('Near Fine','near_fine'),
    ('Very Good','very_good'),('Fair','fair'),('Poor','poor'),('As Described','as_described')])
def test_native_conditions_are_preserved(native,expected):
    r=rows(xml(itemCondition=native));assert r[0]['listing_condition_grade']==expected
    result=preview(BOOK,r,as_of='2026-11-09')
    assert bool(result['condition_scenarios'])==(expected!='as_described')
    assert result['actual_condition']=='ungraded'


@pytest.mark.parametrize('url',['https://abebooks.com.evil.test/servlet/BookDetailsPL?bi=999999990001',
    'https://user:password@www.abebooks.com/servlet/BookDetailsPL?bi=999999990001',
    'https://www.abebooks.com/servlet/BookDetailsPL?bi=wrong','file:///private/file'])
def test_untrusted_or_conflicting_listing_urls_are_not_used(url):
    r=rows(xml(listingUrl=url));assert r[0]['listing_url']==''
    assert not preview(BOOK,r,as_of='2026-11-09')['condition_scenarios']


def test_namespaces_and_gzip_are_supported_but_empty_shapes_are_explicit():
    body=xml().replace(b'<Book>',b'<Book xmlns="urn:synthetic">')
    assert rows(gzip.compress(body),headers={'Content-Encoding':'gzip'})[0]['asking_price']=='12.00'
    assert rows(b'<SearchResults><resultCount>0</resultCount></SearchResults>')==[]
    with pytest.raises(SwsError):rows(b'<SearchResults/>')


@pytest.mark.parametrize('body',[b'<broken',b'<html><body>blocked</body></html>',
    b'<Error><message>clientkey=DO-NOT-ECHO</message></Error>',
    b'<!DOCTYPE Book [<!ENTITY x "secret">]><Book>&x;</Book>',b'<Book>\x00</Book>',b'x'*(MAX_BYTES+1)])
def test_invalid_unsafe_and_error_xml_fail_safely(body):
    with pytest.raises(SwsError) as error:rows(body)
    assert 'DO-NOT-ECHO' not in str(error.value) and 'secret' not in str(error.value)


def test_gzip_expansion_is_bounded():
    with pytest.raises(SwsError,match='expanded response too large'):
        rows(gzip.compress(b'x'*(MAX_BYTES+1)),headers={'Content-Encoding':'gzip'})


def test_retry_and_pacing_use_bounded_virtual_time_and_count_attempts():
    t=ReplayTransport([ReplayResponse(429,b'',{'Retry-After':'2'}),ReplayResponse(503,b'',{'Retry-After':'4'}),ReplayResponse(200,xml())])
    clock=ReplayClock();client=OfflineSwsClient(t,clock=clock)
    assert len(client.search(BOOK,observed_at=WHEN))==1
    assert client.dispatch_times==[0,2,6] and client.attempts==3
    assert len(t.requests)==3


@pytest.mark.parametrize('status',[401,403,400,404])
def test_auth_and_parameter_errors_are_not_retried_or_echoed(status):
    t=ReplayTransport([ReplayResponse(status,b'clientkey=DO-NOT-ECHO')])
    c=OfflineSwsClient(t)
    with pytest.raises(SwsError) as e:c.search(BOOK,observed_at=WHEN)
    assert c.attempts==1 and 'DO-NOT-ECHO' not in str(e.value)


def test_budget_retry_exhaustion_long_retry_after_and_http_date():
    t=ReplayTransport([ReplayResponse(429,b'')]*3);c=OfflineSwsClient(t,budget=2)
    with pytest.raises(SwsError,match='budget'):c.search(BOOK,observed_at=WHEN)
    assert len(t.requests)==2
    c=OfflineSwsClient(ReplayTransport([ReplayResponse(429,b'',{'Retry-After':'120'})]))
    with pytest.raises(SwsError,match='cooldown'):c.search(BOOK,observed_at=WHEN)
    assert c.attempts==1
    clock=ReplayClock();c=OfflineSwsClient(ReplayTransport([
        ReplayResponse(429,b'',{'Retry-After':'Mon, 09 Nov 2026 12:00:10 GMT'}),ReplayResponse(200,xml())]),
        clock=clock,utc_now=lambda:datetime(2026,11,9,12,tzinfo=timezone.utc))
    c.search(BOOK,observed_at=WHEN);assert c.dispatch_times==[0,10]


def test_preview_exercises_shared_matcher_without_publishing_or_mixing_new_copies():
    original=deepcopy(BOOK);result=preview(BOOK,rows(),as_of='2026-11-09')
    assert result['condition_scenarios']==[dict(hypothetical_grade='good',condition_system='AbeBooks native seller condition',
        listing_binding='paperback',currency='USD',low='14.25',high='16.00',listing_count=3,high_spread=False,scenario_only=True,publishable=False)]
    assert result['new_copy_offers']==1 and result['assessment']['proposal'] is None
    assert not result['publishable'] and result['estimates_changed']==0 and result['live_requests']==0
    assert BOOK==original and result['actual_condition']=='ungraded'
    assert not any('ranges' in k for s in result['assessment']['sources'].values() for k in s)


def test_duplicate_offers_do_not_inflate_counts_and_saved_manual_reviews_stay_protected():
    r=rows(xml());result=preview(dict(BOOK,reviewed_estimate_id='SYNTHETIC-REVIEW'),r+r,as_of='2026-11-09')
    assert result['condition_scenarios'][0]['listing_count']==1
    assert result['assessment']['status']=='manual_review_protected'


def test_conflicting_duplicate_offer_ids_do_not_support_scenarios():
    r=rows(xml())+rows(xml(listingPrice='30.00'))
    result=preview(BOOK,r,as_of='2026-11-09')
    assert result['condition_scenarios']==[]
    assert all('duplicate_conflict' in d['reasons'] for d in result['assessment']['decisions'])


def test_distinct_query_based_book_ids_are_not_collapsed_by_shared_url_normalizer():
    result=preview(BOOK,rows(),as_of='2026-11-09')
    assert len({d['listing'] for d in result['assessment']['decisions']})==5
    assert result['condition_scenarios'][0]['listing_count']==3


def test_keyword_signed_copy_is_excluded_and_non_success_parser_fails():
    result=preview(BOOK,rows(xml(keywords='signed by the author')),as_of='2026-11-09')
    assert result['condition_scenarios']==[]
    with pytest.raises(SwsError):parse_response(ReplayResponse(401,xml()),search_plan(BOOK),BOOK,observed_at=WHEN)


def test_synthetic_rows_are_rejected_by_normal_production_review():
    result=review_book(BOOK,rows(),as_of='2026-11-09')
    assert result['proposal'] is None and all('source' in d['reasons'] for d in result['decisions'])


def test_offline_client_never_opens_a_socket(monkeypatch):
    import socket,urllib.request
    def forbidden(*args,**kwargs):raise AssertionError('Network access forbidden')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(urllib.request,'urlopen',forbidden)
    c=OfflineSwsClient(ReplayTransport([ReplayResponse(200,FIXTURE.read_bytes())]))
    result=preview(BOOK,c.search(BOOK,observed_at=WHEN),as_of='2026-11-09')
    assert result['live_requests']==0


def test_virtual_pacing_across_books_and_finite_retry_limit():
    c=OfflineSwsClient(ReplayTransport([ReplayResponse(200,xml()),ReplayResponse(200,xml())]),interval=.5)
    c.search(BOOK,observed_at=WHEN);c.search(BOOK,observed_at=WHEN)
    assert c.dispatch_times==[0,.5]
    c=OfflineSwsClient(ReplayTransport([ReplayResponse(503,b'')]*3))
    with pytest.raises(SwsError):c.search(BOOK,observed_at=WHEN)
    assert c.attempts==3


def test_result_count_caps_and_unknown_envelopes_fail_closed():
    with pytest.raises(SwsError):rows(b'<Other><resultCount>0</resultCount></Other>')
    body=b'<SearchResults><resultCount>0</resultCount>'+xml()+b'</SearchResults>'
    with pytest.raises(SwsError):rows(body)
    with pytest.raises(SwsError):
        parse_response(ReplayResponse(200,FIXTURE.read_bytes()),search_plan(BOOK,limit=3),BOOK,observed_at=WHEN)


def test_latin1_xml_equivalent_isbns_missing_price_and_unknown_binding():
    body=xml(title='Hölderlin',isbn10='0198829175').decode()
    body=('<?xml version="1.0" encoding="ISO-8859-1"?>'+body).encode('iso-8859-1')
    r=rows(body)[0]
    assert r['listing_title']=='Hölderlin' and r['listing_isbn13']==BOOK['isbn13']
    assert r['lookup_status']=='observed'
    assert preview(BOOK,rows(xml(listingPrice=None)),as_of='2026-11-09')['condition_scenarios']==[]
    result=preview(BOOK,rows(xml(bindingType=None)),as_of='2026-11-09')
    assert result['condition_scenarios'][0]['listing_binding']=='unknown'


def test_supplied_copy_condition_cannot_enable_an_offline_proposal():
    result=preview(dict(BOOK,target_condition='good',target_binding='paperback'),rows(),as_of='2026-11-09')
    assert result['assessment']['proposal'] is None and result['actual_condition']=='ungraded'
    assert result['physical_grading']=='deferred'


@pytest.mark.parametrize('price',['NaN','Infinity','-1','0','0.001','1000000000'])
def test_invalid_item_prices_never_become_scenarios(price):
    assert preview(BOOK,rows(xml(listingPrice=price)),as_of='2026-11-09')['condition_scenarios']==[]
