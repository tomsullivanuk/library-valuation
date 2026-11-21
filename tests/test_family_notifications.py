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


def icloud_setup(tmp_path):
    cfg,now=setup(tmp_path)
    cfg['email_notifications']=dict(enabled=True,provider='icloud',smtp_username='owner@icloud.com',
        password_file=str(tmp_path/'key'),**{'from':'Library <library@wearyfather.org>'})
    with closing(r.connect(cfg['database'])) as db, db:
        n.enqueue(db,'request/smtp','Subject','Private body')
    return cfg,now


def fake_smtp(monkeypatch, failure=None):
    import smtplib
    calls=[]
    class SMTP:
        def __init__(self,host,port,timeout):calls.append(('connect',host,port))
        def ehlo(self):calls.append(('ehlo',))
        def starttls(self,context):
            import ssl
            assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
            calls.append(('tls',))
        def login(self,user,password):calls.append(('login',user))
        def send_message(self,msg,from_addr,to_addrs):
            calls.append(('send',msg,from_addr,to_addrs))
            if failure:raise failure
            return {}
        def close(self):calls.append(('close',))
    monkeypatch.setattr(smtplib,'SMTP',SMTP)
    return calls


def test_icloud_tls_auth_sender_recipient_and_success(tmp_path,monkeypatch):
    cfg,now=icloud_setup(tmp_path)
    calls=fake_smtp(monkeypatch)
    n.tick(cfg,now)
    n.tick(cfg,now+timedelta(minutes=1))
    assert calls[:5]==[('connect','smtp.mail.me.com',587),('ehlo',),('tls',),('ehlo',),('login','owner@icloud.com')]
    sends=[c for c in calls if c[0]=='send'];assert len(sends)==1
    msg=sends[0][1]
    assert str(msg['From'])=='Library <library@wearyfather.org>'
    assert sends[0][2:]==('library@wearyfather.org',[n.RECIPIENT])
    assert 'Private body' in msg.get_content()
    with closing(r.connect(cfg['database'])) as db:
        assert db.execute('SELECT state FROM notification_outbox').fetchone()[0]=='sent'


def test_icloud_ambiguous_timeout_and_interrupted_send_never_retry(tmp_path,monkeypatch):
    cfg,now=icloud_setup(tmp_path)
    calls=fake_smtp(monkeypatch,TimeoutError('private detail'))
    n.tick(cfg,now)
    n.tick(cfg,now+timedelta(days=2))
    assert len([c for c in calls if c[0]=='send'])==1
    with closing(r.connect(cfg['database'])) as db, db:
        row=db.execute('SELECT state,error FROM notification_outbox').fetchone()
        assert row['state']=='needs_review' and 'private detail' not in row['error']
        n.enqueue(db,'request/crash','Subject','Body')
        db.execute("UPDATE notification_outbox SET state='sending' WHERE id='request/crash'")
    n.tick(cfg,now+timedelta(days=3))
    assert len([c for c in calls if c[0]=='send'])==1
    with closing(r.connect(cfg['database'])) as db:
        assert db.execute("SELECT state FROM notification_outbox WHERE id='request/crash'").fetchone()[0]=='needs_review'


def test_icloud_explicit_rejection_can_retry(tmp_path,monkeypatch):
    import smtplib
    cfg,now=icloud_setup(tmp_path)
    fake_smtp(monkeypatch,smtplib.SMTPDataError(451,b'try later'))
    n.tick(cfg,now)
    with closing(r.connect(cfg['database'])) as db:
        assert db.execute('SELECT state FROM notification_outbox').fetchone()[0]=='queued'
    calls=fake_smtp(monkeypatch)
    n.tick(cfg,now+timedelta(minutes=2))
    assert len([c for c in calls if c[0]=='send'])==1


def test_attempted_delivery_cannot_switch_provider(tmp_path,monkeypatch):
    cfg,now=setup(tmp_path)
    with closing(r.connect(cfg['database'])) as db,db:n.enqueue(db,'request/test','Title','Body')
    def fail(*args):raise TimeoutError()
    n.tick(cfg,now,fail)
    cfg['email_notifications']=dict(enabled=True,provider='icloud',smtp_username='owner@icloud.com',
        password_file=str(tmp_path/'key'),**{'from':'Library <library@wearyfather.org>'})
    calls=fake_smtp(monkeypatch)
    n.tick(cfg,now+timedelta(minutes=2))
    assert not calls
    with closing(r.connect(cfg['database'])) as db:
        assert db.execute('SELECT state FROM notification_outbox').fetchone()[0]=='needs_review'


def test_private_icloud_setup_preserves_config_and_leaves_disabled(tmp_path):
    import stat
    from operations.family_access_pilot.configure_email import configure
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(database='existing.sqlite',origin='https://example.org',user_access={'keep':'private'})))
    configure(config,'owner@icloud.com','synthetic-app-password')
    result=json.loads(config.read_text())
    assert result['database']=='existing.sqlite' and result['user_access']=={'keep':'private'}
    assert result['email_notifications']['enabled'] is False
    assert 'synthetic-app-password' not in config.read_text()
    secret=tmp_path/'library-icloud-password'
    assert secret.read_text().strip()=='synthetic-app-password'
    for path in (config,secret,tmp_path/'config.before-icloud.json'):
        assert stat.S_IMODE(path.stat().st_mode)==0o600


def test_enriched_request_email_omits_unknowns_and_freezes_details(tmp_path,monkeypatch):
    cfg,now=setup(tmp_path)
    with closing(r.connect(cfg['database'])) as db,db:
        payload=json.dumps(dict(books=[dict(reference='ref',title='Geometry',author='An author',publisher='Press',year='1984'),dict(reference='unknown',title='Unknown edition')],message='Please reserve these.'))
        db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)',('new','reader@example.org','new',now.isoformat(),payload))
    details={'ref':dict(author='An author',publisher='Reviewed Press',year='1984',binding='Paperback (location 15A)',copies=[dict(location='15A')],availability='1 available; 1 reserved; 0 transferred',value='$12–$18')}
    calls=[]
    monkeypatch.setattr(n,'owner_book_details',lambda *args:calls.append(1) or details)
    cfg['email_notifications']['enabled']=False
    n.tick(cfg,now)
    details['ref']['availability']='0 available'
    n.tick(cfg,now+timedelta(minutes=1))
    assert len(calls)==1
    with closing(r.connect(cfg['database'])) as db:
        text=db.execute('SELECT text FROM notification_outbox').fetchone()[0]
    for value in ('Author: An author','Publication: Reviewed Press · 1984','Confirmed binding: Paperback (location 15A)','Storage location(s): 15A','1 available; 1 reserved','Estimated resale value: $12–$18','Please reserve these.','REVIEW REQUEST'):
        assert value in text
    assert 'ISBN' not in text and 'None' not in text
    unknown=text.split('Unknown edition')[1].split('Requester’s message')[0]
    assert 'Publication:' not in unknown and 'binding:' not in unknown and 'Estimated resale value:' not in unknown
