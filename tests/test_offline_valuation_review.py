from copy import deepcopy
import csv
import json

import pytest
from valuation.offline_valuation_review import review_book, replay

BOOK=dict(catalog_item_id='BK1',title='Example Philosophy',author='Alice Scholar',isbn13='9780198829171',target_binding='paperback',target_condition='good')

def listing(n=1,price='10',**extra):
    return dict(catalog_id='BK1',source='abebooks',lookup_status='observed',observation_date='2026-11-01T12:00:00Z',listing_url=f'https://example.test/book/{n}',listing_title='Example Philosophy',listing_author='Alice Scholar',asking_price=price,currency='USD',listing_isbn13=BOOK['isbn13'],listing_binding='paperback',listing_condition_grade='good',**extra)

def run(rows,book=None,as_of='2026-11-06'):
    return review_book(book or BOOK,rows,as_of=as_of)

def three():return [listing(i,str(10+i)) for i in range(3)]

def reasons(result):return [reason for d in result['decisions'] for reason in d['reasons']]

def test_verified_comparables_produce_preview_per_copy_and_never_publish():
    r=run(three());assert r['status']=='proposed_for_review'
    assert r['proposal']==dict(source='abebooks',currency='USD',low='10.00',high='12.00',per_copy=True)
    assert r['publishable'] is False

def test_duplicate_tracking_urls_cannot_inflate_sample_size():
    rows=[dict(listing(),listing_url='https://example.test/book/1?tracking='+str(i)) for i in range(3)]
    r=run(rows)
    assert r['proposal'] is None
    assert sum(d['disposition']=='verified_comparable' for d in r['decisions'])==1
    assert reasons(r).count('duplicate')==2

def test_latest_price_replaces_older_version_and_invalid_latest_does_not_fall_back():
    old=dict(listing(),observation_date='2026-10-31T12:00:00Z')
    latest=dict(listing(),asking_price='20')
    r=run([old,latest]);assert r['sources']['abebooks']['candidate_ranges']['USD']['low']=='20.00'
    latest['asking_price']='NaN';r=run([old,latest])
    assert 'invalid_price' in reasons(r) and r['sources']['abebooks']['candidate_ranges']=={}

def test_conflicting_same_time_duplicate_is_not_arbitrarily_selected():
    r=run([listing(),dict(listing(),asking_price='11')])
    assert reasons(r)==['duplicate_conflict','duplicate_conflict']
    assert not r['sources']['abebooks']['candidate_ranges']

def test_unavailable_primary_does_not_suppress_verified_other_source():
    rows=[dict(listing(),lookup_status='source_unavailable')]+[dict(r,source='ebay_active_listings') for r in three()]
    r=run(rows);assert r['proposal']['source']=='ebay_active_listings'

def test_weak_and_wrong_edition_matches_do_not_contribute():
    wrong=dict(listing(9,'200'),listing_isbn13='9780486600819')
    weak=dict(listing(8,'100'),listing_isbn13='',listing_title='Unrelated Cookery',listing_author='Other Person',match_confidence='high')
    r=run(three()+[wrong,weak]);assert r['proposal']['high']=='12.00'
    assert {'isbn_mismatch','weak_match'}<=set(reasons(r))

def test_query_isbn_and_legacy_high_confidence_never_verify_listing_isbn():
    rows=[{k:v for k,v in r.items() if k!='listing_isbn13'} for r in three()]
    for r in rows:r.update(isbn13=BOOK['isbn13'],match_confidence='high',lookup_strategy='isbn13')
    r=run(rows);assert r['proposal'] is None
    assert r['sources']['abebooks']['candidate_ranges']['USD']['count']==3
    assert all(d['disposition']=='candidate_only' for d in r['decisions'])

def test_missing_target_binding_or_condition_stays_candidate_only():
    for key in ('target_binding','target_condition'):
        b=dict(BOOK);b.pop(key)
        r=run(three(),b);assert r['proposal'] is None

@pytest.mark.parametrize('changes,reason',[
 ({'detail_status':'conflicting_isbns'},'metadata_conflict'),
 ({'listing_condition_description':'Signed by author'},'special_copy'),
 ({'listing_binding':'hardcover'},'binding_mismatch'),
 ({'listing_condition_grade':'poor'},'condition_mismatch'),
 ({'listing_title':'Signed Example Philosophy'},'special_copy'),
 ({'listing_title':'Example Philosophy set of 3 books'},'special_copy'),
 ({'listing_title':'Example Philosophy ebook'},'special_copy'),
 ({'observation_date':'bad'},'invalid_date'),
 ({'observation_date':'2026-11-07'},'future'),
 ({'observation_date':'2026-10-06'},'stale'),
 ({'asking_price':'0'},'invalid_price'),
 ({'asking_price':'-1'},'invalid_price'),
 ({'asking_price':'Infinity'},'invalid_price'),
 ({'asking_price':'0.001'},'invalid_price'),
 ({'listing_url':'https://[malformed'},'identity'),
 ({'listing_url':'https://name:password@example.test/book'},'identity'),
 ({'currency':''},'currency'),
 ({'source':'unrecognized'},'source'),
 ({'listing_url':'https://example.test/servlet/SearchResults?isbn=123'},'identity'),
])
def test_bad_listing_is_excluded(changes,reason):
    r=run([dict(listing(),**changes)])
    assert reason in reasons(r) and r['proposal'] is None

def test_age_boundary_and_historical_replay_are_explicit():
    rows=[dict(r,observation_date='2026-10-07') for r in three()]
    assert run(rows)['proposal']
    rows=[dict(r,observation_date='2026-07-19') for r in three()]
    assert run(rows)['proposal'] is None
    assert run(rows,as_of='2026-07-20')['proposal']

def test_currencies_and_nonoverlapping_sources_require_review():
    ebay=[dict(r,source='ebay_active_listings',asking_price=str(30+i)) for i,r in enumerate(three())]
    assert run(three()+ebay)['status']=='source_disagreement'
    ebay=[dict(r,currency='GBP') for r in ebay]
    assert run(three()+ebay)['status']=='currency_review'

def test_high_spread_and_manual_review_are_never_silently_published():
    assert run([listing(1,'10'),listing(2,'12'),listing(3,'100')])['proposal'] is None
    r=run(three(),dict(BOOK,reviewed_estimate_id='EST-saved'))
    assert r['status']=='manual_review_protected' and r['proposal'] is None

def test_input_order_and_inputs_are_preserved():
    rows=three()+[dict(listing(0),observation_date='2026-10-31')];before=deepcopy(rows)
    assert run(rows)==run(list(reversed(rows)))
    assert rows==before

def test_replay_is_deterministic_private_and_refuses_overwrite(tmp_path):
    pilot=tmp_path/'pilot.csv';obs=tmp_path/'observations.csv'
    book=dict(BOOK,group='synthetic',previous_low='8',previous_high='15',currency='USD')
    for path,rows in [(pilot,[book]),(obs,three())]:
        with path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    original=(pilot.read_bytes(),obs.read_bytes())
    a=replay(pilot,[obs],tmp_path/'a',as_of='2026-11-06',historical_as_of='2026-11-02')
    b=replay(pilot,[obs],tmp_path/'b',as_of='2026-11-06',historical_as_of='2026-11-02')
    assert a==b and (tmp_path/'a/replay.json').read_bytes()==(tmp_path/'b/replay.json').read_bytes()
    assert (pilot.read_bytes(),obs.read_bytes())==original
    assert (tmp_path/'a/review.html').exists()
    assert (tmp_path/'a/replay.json').stat().st_mode & 0o777==0o600
    with pytest.raises(ValueError,match='new output directory'):
        replay(pilot,[obs],tmp_path/'a',as_of='2026-11-06',historical_as_of='2026-11-02')
    with pytest.raises(ValueError,match='data repository'):
        replay(pilot,[obs],tmp_path/'data/run',as_of='2026-11-06',historical_as_of='2026-11-02')
