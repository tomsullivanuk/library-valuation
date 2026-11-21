from datetime import datetime, timedelta, timezone
from contextlib import closing
import json
from valuation import family_notifications as n
from valuation import family_requests as r


def setup(tmp_path):
    now=datetime(2026,11,21,16,tzinfo=timezone.utc)
    cfg=dict(database=str(tmp_path/'db.sqlite'),origin='https://library.example.org',owner_email='owner@example.org')
    n.initialize(cfg['database'],now)
    key=tmp_path/'key';key.write_text('test-only')
    cfg['email_notifications']=dict(enabled=True,api_key_file=str(key),**{'from':'Library <library@example.org>'})
    return cfg,now


def test_submission_alert_retry_and_no_draft_or_historical_mail(tmp_path):
    cfg,now=setup(tmp_path)
    with closing(r.connect(cfg['database'])) as db, db:
        payload=json.dumps(dict(books=[dict(title='A book')],message='Hello'))
        for ident,created in [('old',now-timedelta(days=1)),('new',now)]:
            db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)',(ident,'guest@example.org',ident,created.isoformat(),payload))
        db.execute('INSERT INTO drafts VALUES(?,?,?)',('other@example.org',1,payload))
    attempts=[]
    def fail(payload,key):
        attempts.append((payload,key));raise TimeoutError()
    n.tick(cfg,now,fail)
    cfg['email_notifications']['from']='Changed <changed@example.org>'
    n.tick(cfg,now+timedelta(minutes=2),lambda p,k:attempts.append((p,k)) or 'accepted')
    n.tick(cfg,now+timedelta(minutes=3),lambda p,k:attempts.append((p,k)))
    assert len(attempts)==2 and attempts[0]==attempts[1]
    assert attempts[0][0]['to']==[n.RECIPIENT]
    assert 'Hello' in attempts[0][0]['text'] and 'A book' in attempts[0][0]['text']
    with closing(r.connect(cfg['database'])) as db:
        assert [tuple(x) for x in db.execute('SELECT id,state FROM notification_outbox')]==[('request/new','sent')]


def test_daily_summary_unique_guests_empty_days_and_restart(tmp_path):
    cfg,now=setup(tmp_path)
    n.visit(cfg['database'],'guest@example.org',cfg['owner_email'],now)
    n.visit(cfg['database'],'guest@example.org',cfg['owner_email'],now+timedelta(hours=1))
    n.visit(cfg['database'],cfg['owner_email'],cfg['owner_email'],now)
    sent=[]
    send=lambda p,k:sent.append(p) or 'id'
    # 7 AM Central: not yet due.
    n.tick(cfg,datetime(2026,11,22,13,tzinfo=timezone.utc),send)
    assert not sent
    n.initialize(cfg['database'],now+timedelta(days=1))
    n.tick(cfg,now+timedelta(days=1),send)
    n.tick(cfg,now+timedelta(days=3),send)
    assert len(sent)==1
    assert sent[0]['text'].count('guest@example.org')==1
    assert 'owner@example.org' not in sent[0]['text']


def test_disabled_queue_and_ambiguous_delivery_expiry(tmp_path):
    cfg,now=setup(tmp_path)
    with closing(r.connect(cfg['database'])) as db, db:
        n.enqueue(db,'request/test','Title','Body')
    cfg['email_notifications']['enabled']=False
    def fail(*args):raise AssertionError('must not send')
    n.tick(cfg,now,fail)
    cfg['email_notifications']['enabled']=True
    def timeout(*args):raise TimeoutError()
    n.tick(cfg,now,timeout)
    n.tick(cfg,now+timedelta(hours=24),fail)
    with closing(r.connect(cfg['database'])) as db:
        row=db.execute('SELECT state,attempts FROM notification_outbox').fetchone()
        assert tuple(row)==('needs_review',1)
