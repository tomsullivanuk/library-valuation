from contextlib import closing
from datetime import datetime,timedelta,timezone
import json
from urllib.parse import urlsplit,parse_qs
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


def token(c):
    message=rows(c,'notification_outbox')[-1]['text']
    url=next(line for line in message.splitlines() if '/register/verify?' in line)
    return parse_qs(urlsplit(url).query)['token'][0]


def confirmed(c):
    reg.apply(c,body(),'client')
    value=token(c);reg.verify(c,value)
    return reg.state(c)[0]


class Provider:
    def __init__(self,fail=False):self.fail=fail;self.calls=[]
    def sync(self,desired,known,owner):
        self.calls.append(desired)
        if self.fail:raise users.SyncFailed('Provider not ready')


def test_verification_no_get_side_effects_no_access_and_owner_notice_once(config):
    reg.apply(config,body(),'client')
    t=token(config)
    assert not reg.state(config)
    assert 'Confirm your email' in reg.verify_page(config,t)
    assert not reg.state(config) and len(rows(config,'notification_outbox'))==1
    assert not users.allowed(config,'new@example.org')
    reg.verify(config,t);reg.verify(config,t)
    a=reg.state(config)[0]
    assert a['status']=='pending' and a['address']['postal']=='00501'
    assert 'token_hash' not in a and 'expires' not in a
    out=rows(config,'notification_outbox');assert len(out)==2
    assert out[0]['recipient']=='new@example.org' and out[1]['recipient']==mail.RECIPIENT
    assert '/owner/#users/'+a['id'] in out[1]['text']
    assert not users.allowed(config,'new@example.org')


def test_approval_verifies_access_before_email_and_stale_decisions(config):
    a=confirmed(config)
    with pytest.raises(PermissionError):reg.decide(config,'other@example.org',dict(id=a['id'],action='approve',version=a['version']))
    p=Provider();result=reg.decide(config,config['owner_email'],dict(id=a['id'],action='approve',version=a['version'],note='Welcome!'),p)
    assert result['applications'][0]['status']=='approved' and users.allowed(config,'new@example.org')
    approval=rows(config,'notification_outbox')[-1]
    assert approval['recipient']=='new@example.org'
    assert all(s in approval['text'] for s in ['Welcome!','one-time access code','My List','new@example.org'])
    with pytest.raises(ledger.Conflict):reg.decide(config,config['owner_email'],dict(id=a['id'],action='decline',version=a['version']),p)
    assert len(rows(config,'notification_outbox'))==3


def test_provider_failure_then_retry_sends_one_approval(config):
    a=confirmed(config)
    result=reg.decide(config,config['owner_email'],dict(id=a['id'],action='approve',version=a['version']),Provider(True))
    assert result['notice'] and result['applications'][0]['status']=='approving'
    assert not users.allowed(config,'new@example.org') and len(rows(config,'notification_outbox'))==2
    a=reg.state(config)[0]
    with pytest.raises(ValueError):reg.decide(config,config['owner_email'],dict(id=a['id'],action='decline',version=a['version']))
    result=reg.decide(config,config['owner_email'],dict(id=a['id'],action='approve',version=a['version']),Provider())
    assert result['applications'][0]['status']=='approved' and len(rows(config,'notification_outbox'))==3


def test_decline_preserves_address_and_contacts_owner_without_grant(config):
    a=confirmed(config)
    reg.decide(config,config['owner_email'],dict(id=a['id'],action='decline',version=a['version'],note='Please call me.'))
    assert not users.allowed(config,'new@example.org')
    assert reg.state(config)[0]['address']['street']=='100 Example St'
    notice=rows(config,'notification_outbox')[-1]
    assert notice['recipient']=='new@example.org' and 'contact Tom directly at owner@example.org' in notice['text'] and 'Please call me.' in notice['text']


def test_bad_expired_tokens_and_duplicate_application(config):
    now=datetime.now(timezone.utc)
    reg.apply(config,body(),'client',now)
    t=token(config)
    reg.apply(config,body(name='Changed by duplicate'),'other',now)
    assert len(rows(config,'notification_outbox'))==1
    with pytest.raises(ValueError):reg.verify(config,t+'x',now)
    with pytest.raises(ValueError):reg.verify(config,t,now+timedelta(hours=25))
    reg.apply(config,body(),'client',now+timedelta(hours=25))
    with pytest.raises(ValueError):reg.verify(config,t,now+timedelta(hours=25))
    reg.verify(config,token(config),now+timedelta(hours=25))
    assert reg.state(config)[0]['name']=='New Reader'


def test_validation_honeypot_throttle_and_existing_guest(config):
    for patch in [dict(postal='123'),dict(region='Not a state'),dict(email='bad'),dict(street=''),dict(name='x\nInjected')]:
        with pytest.raises(ValueError):reg.apply(config,body(**patch),'client')
    reg.apply(config,body(website='spam'),'client')
    reg.apply(config,body(email='existing@example.org'),'client')
    assert not rows(config,'registration_applications') and not rows(config,'notification_outbox')
    for i in range(5):reg.apply(config,body(email=f'reader{i}@example.org'),'same-client')
    with pytest.raises(ValueError):reg.apply(config,body(email='six@example.org'),'same-client')


def test_lookup_only_zip_and_international_address(config,monkeypatch):
    import requests
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'places':[{'place name':'Test City','state abbreviation':'NY'}]}
    monkeypatch.setattr(requests,'get',lambda url,**kwargs:calls.append(url) or Response())
    assert reg.lookup_zip('00501')['places']==[dict(city='Test City',region='NY')]
    assert calls==['https://api.zippopotam.us/us/00501']
    reg.apply(config,body(country='United Kingdom',postal='SW1A 1AA',region='',city='London'),'client')
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
    assert len(sent)==1 and sent[0][3]==['new@example.org'] and str(sent[0][1]['To'])=='new@example.org'
