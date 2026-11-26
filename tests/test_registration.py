from contextlib import closing
from datetime import datetime,timedelta,timezone
import json
import pytest
from valuation import registration as reg, family_notifications as mail, family_requests as ledger, family_users as users


@pytest.fixture
def config(tmp_path):
    secret=tmp_path/'secret';secret.write_text('test-registration-salt')
    c=dict(database=str(tmp_path/'db.sqlite'),origin='https://library.example.org',owner_email='owner@example.org',allowed_emails=['owner@example.org','existing@example.org'],registration=dict(enabled=True,secret_file=str(secret)))
    mail.initialize(c['database']);reg.initialize(c)
    return c


def body(**patch):return dict(name='New Reader',email='new@example.org',street='100 Example St',unit='2',country='US',postal='00501',city='Example',region='NY',website='')|patch


def rows(c,table):
    with closing(ledger.connect(c['database'])) as db:return [dict(r) for r in db.execute('SELECT * FROM '+table)]


def submitted(c):
    reg.apply(c,body(),'client')
    return reg.state(c)[0]


class Provider:
    def __init__(self,fail=False):self.fail=fail;self.calls=[]
    def sync(self,desired,known,owner):
        self.calls.append(desired)
        if self.fail:raise users.SyncFailed('Provider not ready')


def test_direct_registration_pending_acknowledgment_and_owner_notice_once(config):
    reg.apply(config,body(),'client')
    a=reg.state(config)[0]
    assert a['status']=='pending' and a['address']['postal']=='00501' and a['verified'] is None
    assert 'token_hash' not in a and 'expires' not in a
    out=rows(config,'notification_outbox');assert len(out)==2
    assert out[0]['recipient']=='new@example.org' and out[1]['recipient']==mail.RECIPIENT
    assert 'under review' in out[0]['text'] and 'within 24 hours' in out[0]['text']
    assert 'Spam or Junk' in out[0]['text']
    assert '/register/verify?' not in out[0]['text'] and 'No action is needed now' in out[0]['text']
    assert '/owner/#users/'+a['id'] in out[1]['text'] and 'verified application' not in out[1]['text']
    reg.apply(config,body(name='Changed by duplicate'),'other')
    assert len(rows(config,'notification_outbox'))==2 and reg.state(config)[0]['name']=='New Reader'
    assert not users.allowed(config,'new@example.org')


def test_approval_verifies_access_before_email_and_stale_decisions(config):
    a=submitted(config)
    with pytest.raises(PermissionError):reg.decide(config,'other@example.org',dict(id=a['id'],action='approve',version=a['version']))
    p=Provider();result=reg.decide(config,config['owner_email'],dict(id=a['id'],action='approve',version=a['version'],note='Welcome!'),p)
    assert result['applications'][0]['status']=='approved' and users.allowed(config,'new@example.org')
    approval=rows(config,'notification_outbox')[-1]
    assert approval['recipient']=='new@example.org'
    assert all(s in approval['text'] for s in ['Welcome!','one-time login code','noreply@notify.cloudflare.com','Spam or Junk','My List','new@example.org'])
    with pytest.raises(ledger.Conflict):reg.decide(config,config['owner_email'],dict(id=a['id'],action='decline',version=a['version']),p)
    assert len(rows(config,'notification_outbox'))==3


def test_provider_failure_then_retry_sends_one_approval(config):
    a=submitted(config)
    result=reg.decide(config,config['owner_email'],dict(id=a['id'],action='approve',version=a['version']),Provider(True))
    assert result['notice'] and result['applications'][0]['status']=='approving'
    assert not users.allowed(config,'new@example.org') and len(rows(config,'notification_outbox'))==2
    a=reg.state(config)[0]
    with pytest.raises(ValueError):reg.decide(config,config['owner_email'],dict(id=a['id'],action='decline',version=a['version']))
    result=reg.decide(config,config['owner_email'],dict(id=a['id'],action='approve',version=a['version']),Provider())
    assert result['applications'][0]['status']=='approved' and len(rows(config,'notification_outbox'))==3


def test_decline_preserves_address_and_contacts_owner_without_grant(config):
    a=submitted(config)
    reg.decide(config,config['owner_email'],dict(id=a['id'],action='decline',version=a['version'],note='Please call me.'))
    assert not users.allowed(config,'new@example.org')
    assert reg.state(config)[0]['address']['street']=='100 Example St'
    notice=rows(config,'notification_outbox')[-1]
    assert notice['recipient']=='new@example.org' and 'contact Tom directly at owner@example.org' in notice['text'] and 'Please call me.' in notice['text']


def test_legacy_unverified_applications_move_to_review_without_duplicate_mail(config):
    now=datetime.now(timezone.utc).isoformat()
    with closing(ledger.connect(config['database'])) as db,db:
        db.execute('INSERT INTO registration_applications(id,email,name,address,status,version,created,updated,token_hash,expires) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   ('legacy','legacy@example.org','Existing Reader',json.dumps(reg.address(body())),'unverified',0,now,now,'old-hash',now))
        mail.enqueue(db,'registration/verify/old-hash','Old verification','Old link',recipient='legacy@example.org')
    reg.initialize(config);reg.initialize(config)
    a=reg.state(config)[0]
    assert a['status']=='pending' and a['name']=='Existing Reader' and a['address']['street']=='100 Example St'
    out=rows(config,'notification_outbox')
    assert len(out)==3 and out[0]['state']=='cancelled'
    assert len([r for r in out if r['id'].startswith('registration/received/')])==1
    assert len(rows(config,'registration_events'))==1
    assert not users.allowed(config,'legacy@example.org')
    assert 'No email confirmation needed' in reg.verify_page(config,'old-token')
    assert reg.state(config)[0]['status']=='pending'


def test_validation_honeypot_throttle_and_existing_guest(config):
    for patch in [dict(postal='123'),dict(region='Not a state'),dict(email='bad'),dict(street=''),dict(name='x\nInjected')]:
        with pytest.raises(ValueError):reg.apply(config,body(**patch),'client')
    reg.apply(config,body(website='spam'),'client')
    assert reg.apply(config,body(email='existing@example.org'),'client') =='active'
    assert not rows(config,'registration_applications')
    out=rows(config,'notification_outbox')
    assert len(out)==1 and out[0]['recipient']=='existing@example.org' and 'already registered' in out[0]['subject']
    for i in range(5):reg.apply(config,body(email=f'reader{i}@example.org'),'same-client')
    with pytest.raises(ValueError):reg.apply(config,body(email='six@example.org'),'same-client')


def test_lookup_only_zip_and_us_address(config,monkeypatch):
    import requests
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'places':[{'place name':'Test City','state abbreviation':'NY'}]}
    monkeypatch.setattr(requests,'get',lambda url,**kwargs:calls.append(url) or Response())
    assert reg.lookup_zip('00501')['places']==[dict(city='Test City',region='NY')]
    assert calls==['https://api.zippopotam.us/us/00501']
    with pytest.raises(ValueError,match='U.S.'):
        reg.apply(config,body(country='United Kingdom',postal='SW1A 1AA',region='',city='London'),'client')
    domestic=body();domestic.pop('country')
    reg.apply(config,domestic,'client')
    assert rows(config,'registration_applications')[0]['address'] and json.loads(rows(config,'registration_applications')[0]['address'])['country']=='US'
    with pytest.raises(ValueError):reg.lookup_zip('../private')
    assert len(calls)==1


def test_registration_outbox_delivers_to_applicant_not_owner(config,tmp_path,monkeypatch):
    from tests.test_family_notifications import fake_smtp
    key=tmp_path/'password';key.write_text('synthetic')
    config['email_notifications']=dict(enabled=True,provider='icloud',password_file=str(key),smtp_username='test@icloud.com',**{'from':'Library <library@wearyfather.org>'})
    reg.apply(config,body(),'client')
    calls=fake_smtp(monkeypatch)
    mail.tick(config)
    sent=[r for r in calls if r[0]=='send']
    assert len(sent)==2
    assert sent[0][3]==['new@example.org'] and str(sent[0][1]['To'])=='new@example.org'
    assert sent[1][3]==[mail.RECIPIENT]


def test_active_guest_acknowledged_once_without_application_or_access_changes(config):
    before=users.state(config)
    now=datetime.now(timezone.utc)
    assert reg.apply(config,body(email='existing@example.org'),'client',now)=='active'
    assert reg.apply(config,body(email='existing@example.org'),'client',now)=='active'
    assert users.state(config)==before
    assert not rows(config,'registration_applications')
    out=rows(config,'notification_outbox')
    assert len(out)==1 and out[0]['recipient']=='existing@example.org'
    assert 'No further approval is needed' in out[0]['text'] and config['origin'] in out[0]['text']
    assert 'one-time access code' in out[0]['text'] and 'My List' in out[0]['text']
    assert not any(r['recipient']==mail.RECIPIENT for r in out)


def test_active_guest_with_prior_approved_application_still_gets_acknowledgment(config):
    a=submitted(config)
    reg.decide(config,config['owner_email'],dict(id=a['id'],action='approve',version=a['version']),Provider())
    reg.apply(config,body(),'client-two')
    out=rows(config,'notification_outbox')
    assert len([r for r in out if r['id'].startswith('registration/already-active/')])==1
    assert reg.state(config)[0]['status']=='approved'


def test_disabled_guest_is_not_told_access_is_active(config):
    u=next(u for u in users.state(config)['users'] if u['email']=='existing@example.org')
    users.update(config,config['owner_email'],dict(action='disable',email=u['email'],version=u['version']),Provider())
    assert reg.apply(config,body(email='existing@example.org'),'client') is None
    assert not rows(config,'notification_outbox') and not users.allowed(config,'existing@example.org')
