from contextlib import closing
import csv
import io
import json
import pytest
from valuation import email_history as h, family_notifications as n
from valuation.family_requests import connect


def fixture(tmp_path):
    c=dict(database=str(tmp_path/'history.sqlite'),email_notifications={'from':'Library <library@example.org>'})
    n.initialize(c['database'])
    with closing(connect(c['database'])) as db,db:
        n.enqueue(db,'registration/approved/a','Current subject','Current body','reader@example.org')
        db.execute("UPDATE notification_outbox SET payload=?,state='sent',first_attempt=?,accepted_at=?",(json.dumps(dict(to=['actual@example.org'],subject='<script>unsafe</script>',text='=HYPERLINK("bad")',sender='Library <library@example.org>')),'2026-11-22T05:59:00+00:00','2026-11-22T06:01:00+00:00'))
        n.enqueue(db,'visitors/2026-11-22','Visitors','Summary')
    return c


def test_frozen_payload_filters_and_central_date(tmp_path):
    c=fixture(tmp_path)
    rows=h.records(c,dict(recipient='ACTUAL',status='sent',type='registration',**{'from':'2026-11-22','to':'2026-11-22'}))
    assert len(rows)==1 and rows[0]['recipient']=='actual@example.org'
    assert rows[0]['basis']=='Accepted' and '00:01:00 CST' in rows[0]['time']
    assert not h.records(c,dict(recipient='reader@example.org'))
    with pytest.raises(ValueError):h.records(c,dict(status='bogus'))
    with pytest.raises(ValueError):h.records(c,{'from':'2026-12-01','to':'2026-11-01'})


def test_html_escapes_message_and_csv_protects_formulas(tmp_path):
    c=fixture(tmp_path);rows=h.records(c,dict(status='sent'))
    page=h.page(c,dict(status='sent'))
    assert '<script>unsafe</script>' not in page and '&lt;script&gt;' in page
    parsed=list(csv.reader(io.StringIO(h.csv_export(rows).decode('utf-8-sig'))))
    assert len(parsed)==2 and parsed[1][6].startswith("'=HYPERLINK")
    assert 'status=sent' in page and 'No emails match' in h.page(c,dict(recipient='absent'))


def test_legacy_times_not_fabricated(tmp_path):
    c=fixture(tmp_path)
    with closing(connect(c['database'])) as db,db:
        db.execute("UPDATE notification_outbox SET created=NULL,accepted_at=NULL,first_attempt=NULL")
    assert all(r['time']=='Not recorded' for r in h.records(c,{}))
    assert not h.records(c,{'from':'2026-11-22'})
