from copy import deepcopy
import csv
import hashlib
import json

import pytest
from valuation.candidate_record_review import review_one,run_review
from valuation.offline_valuation_review import listing_key

BOOK=dict(catalog_item_id='BK1',title='Example',isbn13='9780198829171',location='1',previous_low='8',previous_high='12',currency='USD')
PACKET=dict(catalog=dict(catalog_item_id='BK1',isbn13=BOOK['isbn13'],publisher='Example Press'),acquisitions=[dict(acquisition_id='A1',isbn13=BOOK['isbn13'])],observations=[dict(inventory_observation_id='O1',normalized_isbn13=BOOK['isbn13'],raw_publisher='Example Press')])

def row(n,price='10',grade='good',**extra):
 r=dict(catalog_id='BK1',listing_url=f'https://www.ebay.com/itm/{n}',raw_reference=f'v1|{n}|0',listing_title='Example Paperback',listing_isbn13=BOOK['isbn13'],listing_binding='paperback',listing_condition_grade=grade,condition=grade,asking_price=price,currency='USD',listing_publisher='Example Press')
 r.update(extra);return r

def review(rows,book=BOOK,packet=PACKET):
 return review_one(book,packet,rows,{listing_key(r) for r in rows},'Reviewed note')


def test_records_support_identity_without_inventing_condition_or_physical_binding():
 rs=[row(1)];before=deepcopy((BOOK,PACKET,rs));r=review(rs)
 assert r['identity_supported_from_records'] and r['condition_assumed'] is False
 assert r['edition_binding_inference']['value']=='paperback'
 assert r['edition_binding_inference']['physical_verification'] is False
 assert not r['publishable'] and not any(c['kind']=='edition' for c in r['physical_checks'])
 assert (BOOK,PACKET,rs)==before


def test_purchase_or_scanned_isbn_mismatch_is_not_resolved():
 p=deepcopy(PACKET);p['observations'][0]['normalized_isbn13']='9780486600819'
 r=review([row(1)],packet=p)
 assert not r['identity_supported_from_records'] and r['physical_checks'][0]['kind']=='edition'


def test_listing_title_conflicts_are_held_not_silently_fixed():
 r=review([row(1,listing_title='Example - hardcover, by Writer'),row(2,listing_title='Example - Paperback - Very Good')])
 assert all(x['review_disposition']=='held_metadata_conflict' for x in r['listing_decisions'])
 assert not r['retained_used_context']


def test_new_context_is_separate_and_above_new_used_prices_are_held():
 r=review([row(1,'150'),row(2,'100','new'),row(3,'110','new'),row(4,'80','very_good')])
 assert r['listing_decisions'][0]['review_disposition']=='held_above_new_context'
 assert r['retained_used_context']['USD']['high']=='80.00'
 assert r['new_copy_context']['USD']['count']==2


def test_tight_same_grade_cluster_holds_high_outlier_but_keeps_evidence():
 rs=[row(1,'11'),row(2,'12'),row(3,'13'),row(4,'50')]
 r=review(rs)
 assert r['listing_decisions'][3]['review_disposition']=='held_high_outlier'
 assert r['retained_used_context']['USD']['high']=='13.00'
 assert len(r['listing_decisions'])==4 and rs[3]['asking_price']=='50'


def test_condition_or_currency_differences_do_not_create_false_outlier_cluster():
 rs=[row(1,'11'),row(2,'12'),row(3,'13'),row(4,'50','like_new')]
 assert review(rs)['listing_decisions'][3]['review_disposition']=='retained_candidate'
 rs[3].update(listing_condition_grade='good',currency='GBP')
 assert review(rs)['listing_decisions'][3]['review_disposition']=='retained_candidate'


def test_missing_target_isbn_requires_physical_check_and_excludes_wrong_publisher():
 b=dict(BOOK,isbn13='');p=deepcopy(PACKET);p['catalog'].update(isbn13='',publisher='Crown Publishers')
 r=review([row(1,listing_publisher='Fingerprint'),row(2,listing_publisher='Crown Publishers')],book=b,packet=p)
 assert r['listing_decisions'][0]['review_disposition']=='excluded_different_publisher'
 assert r['listing_decisions'][1]['review_disposition']=='held_for_target_edition'
 assert not r['retained_used_context'] and r['physical_checks'][0]['required']


def test_previously_inferred_copy_link_is_preserved_as_optional_check():
 p=deepcopy(PACKET);p['observations'].append(dict(inventory_observation_id='O2',normalized_isbn13='',raw_publisher='Example Press',source_collection_label='Box 83 and 83a'))
 r=review([row(1)],packet=p)
 assert r['identity_supported_from_records'] and r['inferred_copy_observation_ids']==['O2']
 c=next(c for c in r['physical_checks'] if c['kind']=='inferred_copy_identity')
 assert not c['required'] and 'Preserve' in c['question'] and c['location']=='83 and 83a'


def test_artifacts_are_private_inputs_unchanged_and_cohort_must_be_complete(tmp_path):
 paths=[]
 row1=row(1)
 payloads=[('packet.json',{'BK1':PACKET}),('notes.json',{'BK1':'Evidence <script> is text'}),('prelim.json',{'books':[dict(book=BOOK,review=dict(sources={'ebay':dict(candidate_ranges={'USD':dict(low='10',high='10')})},decisions=[dict(listing=listing_key(row1),disposition='candidate_only')]))]})]
 for name,value in payloads:
  p=tmp_path/name;p.write_text(json.dumps(value));paths.append(p)
 obs=tmp_path/'obs.csv'
 with obs.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(row1));w.writeheader();w.writerow(row1)
 paths.append(obs);before=[p.read_bytes() for p in paths]
 summary=run_review(*paths,tmp_path/'review')
 assert summary['identity_supported']==1 and summary['estimates_changed']==0
 assert [p.read_bytes() for p in paths]==before
 assert '<script>' not in (tmp_path/'review/review.html').read_text()
 assert (tmp_path/'review/review.json').stat().st_mode & 0o777==0o600
 with pytest.raises(ValueError):run_review(*paths,tmp_path/'review')
 paths[1].write_text('{}')
 with pytest.raises(ValueError,match='exactly'):run_review(*paths,tmp_path/'incomplete')


def test_existing_copyright_transcription_narrows_check_without_inventing_printing_date():
 b=dict(BOOK,isbn13='');p=deepcopy(PACKET)
 p['catalog'].update(isbn13='',publisher='Crown Publishers')
 p['source_notes']=[dict(notes='Authorised translation by Robert W. Lawson. Copyright 1961 by the Estate of Albert Einstein.')]
 r=review([row(1,listing_publisher='Crown Publishers',listing_year='1931'),row(2,listing_publisher='Crown Publishers',listing_year='1961')],book=b,packet=p)
 assert r['listing_decisions'][0]['review_disposition']=='excluded_earlier_publication_claim'
 assert r['listing_decisions'][1]['review_disposition']=='held_for_target_edition'
 assert r['recorded_copyright_years']==[1961] and 'printing date' in r['physical_checks'][0]['question']
 assert r['identity_supported_from_records'] is False
