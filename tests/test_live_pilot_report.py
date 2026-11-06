import csv
import hashlib
import json

import pytest
from valuation.live_pilot_report import report


def fixture(tmp_path):
    book=dict(catalog_item_id='BK1',title='Example <script>alert(1)</script>',author='A Writer',isbn13='9780198829171',previous_low='8',previous_high='12',currency='USD')
    row=dict(catalog_id='BK1',source='ebay_active_listings',lookup_status='observed',observation_date='2026-11-06',listing_title=book['title'],listing_author='A Writer',listing_isbn13=book['isbn13'],listing_isbns=book['isbn13'],listing_binding='paperback',listing_format_raw='Paperback',listing_condition_grade='good',condition='Good',asking_price='10',currency='USD',listing_url='https://www.ebay.com/itm/1',detail_status='retrieved')
    paths=[]
    for name,rows in [('pilot.csv',[book]),('observations.csv',[row])]:
        p=tmp_path/name
        with p.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        paths.append(p)
    state=dict(manifest=dict(catalog_ids=['BK1'],pilot_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest()),status='complete',books={'BK1':{'completed':True}},request_count=3)
    checkpoint=tmp_path/'checkpoint.json';checkpoint.write_text(json.dumps(state));paths.append(checkpoint)
    return paths


def test_private_live_report_has_comparison_details_and_preserves_all_inputs(tmp_path):
    paths=fixture(tmp_path);before=[p.read_bytes() for p in paths]
    s=report(*paths,tmp_path/'report',as_of='2026-11-06')
    assert s['listing_details']==1 and s['isbn_present']==1 and s['binding_present']==1
    assert s['books_with_candidates']==1 and s['verified_proposals']==0 and s['publication']=='disabled'
    html=(tmp_path/'report/review.html').read_text()
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'https://www.ebay.com/itm/1' in html and 'Saved range: $8–$12' in html
    assert '9780198829171 / Paperback' in html and 'Good' in html
    assert [p.read_bytes() for p in paths]==before
    with pytest.raises(ValueError,match='new report directory'):report(*paths,tmp_path/'report',as_of='2026-11-06')


def test_report_rejects_changed_cohort_before_writing(tmp_path):
    paths=fixture(tmp_path);paths[0].write_text(paths[0].read_text()+'\n')
    with pytest.raises(ValueError,match='Pilot differs'):report(*paths,tmp_path/'report',as_of='2026-11-06')
    assert not (tmp_path/'report').exists()
