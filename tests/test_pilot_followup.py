import csv
import pytest
from valuation.live_valuation_pilot import FIELDS
from valuation.pilot_followup import merge_observations


def save(path,price,date,cid='BK1'):
    row=dict.fromkeys(FIELDS,'');row.update(catalog_id=cid,source='ebay_active_listings',lookup_status='observed',listing_url='https://www.ebay.com/itm/123',asking_price=price,observation_date=date)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerow(row)


def test_repeat_fetch_uses_latest_price_once_and_keeps_book_identity(tmp_path):
    a,b,c=[tmp_path/n for n in ('a.csv','b.csv','c.csv')]
    save(a,'10','2026-11-05T00:00:00Z');save(b,'12','2026-11-06T00:00:00Z');save(c,'11','2026-11-06T00:00:00Z','BK2')
    out=tmp_path/'merged.csv';receipt=merge_observations([b,a,c],out)
    rows=list(csv.DictReader(out.open()))
    assert len(rows)==2 and rows[0]['asking_price']=='12'
    assert receipt['repeat_fetches_not_counted']==1
    with pytest.raises(ValueError):merge_observations([a],out)


def test_same_time_conflict_fails_without_writing(tmp_path):
    a,b=[tmp_path/n for n in ('a.csv','b.csv')]
    save(a,'10','2026-11-06T00:00:00Z');save(b,'12','2026-11-06T00:00:00Z')
    out=tmp_path/'merged.csv'
    with pytest.raises(ValueError,match='Conflicting'):merge_observations([a,b],out)
    assert not out.exists()
