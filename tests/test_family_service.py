import json,threading
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from pathlib import Path
import pytest
from valuation.family_service import App,Identity
from valuation.family_catalog import FIELDS

@pytest.fixture
def server(tmp_path):
 snap=tmp_path/'catalog.json';snap.write_text(json.dumps([dict(zip(FIELDS,['ref','Title','Author','Press','2020','isbn','Physically inventoried']))]))
 config=dict(database=str(tmp_path/'db.sqlite'),snapshot=str(snap),origin='https://family.example',allowed_emails=['owner@example.org','guest@example.org'],owner_email='owner@example.org',family_search_enabled=True)
 def identity(token):
  if token not in ['owner@example.org','guest@example.org']:raise ValueError()
  return token
 app=App(config,identity);srv=ThreadingHTTPServer(('127.0.0.1',0),app.handler());threading.Thread(target=srv.serve_forever,daemon=True).start()
 def call(path,who='guest@example.org',data=None,origin='https://family.example',registration=False):
  req=Request('http://127.0.0.1:'+str(srv.server_port)+path,data=json.dumps(data).encode() if data is not None else None,headers={'Host':'family.example','Origin':origin,'Content-Type':'application/json','X-Family-Request':'1','Cf-Access-Jwt-Assertion':who,**({'X-Registration':'1'} if registration else {})})
  try:r=urlopen(req)
  except HTTPError as e:r=e
  return r.code,r.read()
 call.app=app
 yield call
 srv.shutdown();srv.server_close()

def test_http_ownership_and_csrf(server):
 assert server('/api/me',who='forged')[0]==403
 assert server('/api/inbox')[0]==403
 assert server('/owner/')[0]==403
 assert server('/owner/search-pilot')[0]==403
 assert server('/owner/search-pilot/report')[0]==403
 assert server('/owner/search-pilot/query',data={'query':'faith'})[0]==403
 assert server('/owner/search-pilot.js')[0]==403
 assert server('/owner/api/state')[0]==403
 assert server('/owner/api/family-requests',data={})[0]==403
 assert server('/api/list',data=dict(version=0,books=['ref']),origin='https://evil.example')[0]==403
 assert server('/api/list',data=dict(version=0,books=['ref']))[0]==200
 assert json.loads(server('/api/me',who='owner@example.org')[1])['draft']['books']==[]
 assert server('/api/submit',data=dict(version=1,key='retry'))[0]==200
 assert server('/api/submit',data=dict(version=1,key='retry'))[0]==200
 assert len(json.loads(server('/api/inbox',who='owner@example.org')[1]))==1
 assert server('/../../db.sqlite')[0]==404
 assert b'data-ref="ref"' in server('/')[1]

def test_recipient_api_exposes_only_own_owner_messages(server):
 from valuation import family_owner as owner,family_requests as requests
 server('/api/list',data=dict(version=0,books=['ref']))
 _,raw=server('/api/submit',data=dict(version=1,key='message-test'))
 submission=json.loads(raw)['id']
 with requests.connect(server.app.db) as db:
  owner.update(db,'owner@example.org',dict(submission=submission,reference='ref',state='declined',version=0,message='I am keeping this one.'),{})
 code,raw=server('/api/me')
 assert code==200
 book=json.loads(raw)['submissions'][0]['payload']['books'][0]
 assert book['request_status']=='declined'
 assert book['owner_messages'][0]['message']=='I am keeping this one.'
 assert set(book['owner_messages'][0])=={'created','message'}
 assert json.loads(server('/api/me',who='owner@example.org')[1])['submissions']==[]
 assert all(x not in raw.decode() for x in ['sale_amount','correction_reason','slot','private_notes'])

def test_real_signature_claim_validation(monkeypatch):
 import jwt,time
 from cryptography.hazmat.primitives.asymmetric import rsa
 key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
 other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
 verifier=Identity(dict(issuer='https://team.cloudflareaccess.com',audience='aud',allowed_emails=['guest@example.org']))
 class Keys:
  def get_signing_key_from_jwt(self,t):
   class K:pass
   k=K();k.key=key.public_key();return k
 verifier.keys=Keys()
 claims=dict(iss='https://team.cloudflareaccess.com',aud=['aud'],iat=int(time.time()),exp=int(time.time())+60,sub='subject',email='guest@example.org')
 assert verifier(jwt.encode(claims,key,algorithm='RS256'))=='guest@example.org'
 for patch in [dict(aud=['wrong']),dict(iss='wrong'),dict(exp=1),dict(email='stranger@example.org')]:
  with pytest.raises(Exception):verifier(jwt.encode(claims|patch,key,algorithm='RS256'))
 with pytest.raises(Exception):verifier(jwt.encode(claims,other,algorithm='RS256'))

def test_signing_keys_use_verified_ca_bundle(monkeypatch):
 import ssl
 seen={}
 def client(url,**kwargs):seen.update(kwargs);return object()
 monkeypatch.setattr('valuation.family_service.jwt.PyJWKClient',client)
 Identity(dict(issuer='https://team.cloudflareaccess.com'))
 assert seen['ssl_context'].verify_mode==ssl.CERT_REQUIRED
 assert seen['ssl_context'].check_hostname is True

def test_owner_badge_uses_verified_email_as_escaped_text():
 from valuation.family_service import owner_badge
 badge=owner_badge('owner@example.org')
 assert 'Signed in as owner@example.org' in badge and 'Owner' in badge
 assert '<script>' not in owner_badge('<script>')


def test_family_search_requires_identity_origin_and_is_read_only(server):
 assert server('/api/search',who='forged',data={'query':'Title'})[0]==403
 assert server('/api/search',origin='https://evil.example',data={'query':'Title'})[0]==403
 code,raw=server('/api/search',data={'query':'Title'})
 assert code==200
 body=json.loads(raw)
 assert body['engine']=='keyword' and body['results'][0]['reference']=='ref'
 assert all(k not in raw.decode() for k in ['purchase_price','sale_amount','location','private_notes'])
 assert json.loads(server('/api/me')[1])['draft']['version']==0
 assert server('/api/search',data={'query':'x'*501})[0]==400

def test_guest_cannot_access_user_administration(server):
 for path in ['/owner/api/users','/owner/users.js']:
  assert server(path)[0]==403
 assert server('/owner/api/users',data={'action':'add','email':'new@example.org'})[0]==403
 assert server('/api/users')[0]==404


def test_disabled_guest_session_is_rejected_immediately(server):
 from valuation import family_users
 config=server.app.config;x=next(u for u in family_users.state(config)['users'] if u['email']=='guest@example.org')
 class Provider:
  def sync(self,*args):raise family_users.SyncFailed('offline')
 family_users.update(config,'owner@example.org',dict(action='disable',email=x['email'],version=x['version']),Provider())
 assert server('/api/me')[0]==403
 assert server('/api/list',data={'version':0,'books':[]})[0]==403


def test_legacy_origin_redirect_is_fixed_and_rejects_old_writes(server):
 server.app.config['redirect_hosts']=['old.example.org']
 # Direct handler simulation avoids a real external redirect.
 import http.client
 # Use the already running fixture's call to test unknown Host denial and
 # explicit redirects through a second bound loopback server.
 from http.server import ThreadingHTTPServer
 srv=ThreadingHTTPServer(('127.0.0.1',0),server.app.handler());threading.Thread(target=srv.serve_forever,daemon=True).start()
 try:
  c=http.client.HTTPConnection('127.0.0.1',srv.server_port);c.request('GET','/owner/#users',headers={'Host':'old.example.org'});res=c.getresponse();assert res.status==302 and res.getheader('Location')=='https://family.example/owner/#users';res.read();c.close()
  c=http.client.HTTPConnection('127.0.0.1',srv.server_port);c.request('POST','/api/list',body='{}',headers={'Host':'old.example.org'});res=c.getresponse();assert res.status==409;res.read();c.close()
 finally:srv.shutdown();srv.server_close()


def test_topic_endpoint_is_authenticated_and_bibliographic_only(server):
 assert server('/api/topics',who='forged')[0]==403
 code,raw=server('/api/topics')
 assert code==200
 result=json.loads(raw)
 assert result['total']==1
 assert set(result['books'])=={'ref'}
 assert result['books']['ref']==['more']
 assert 'owner@example.org' not in raw.decode()
 assert 'request_decisions' not in raw.decode()


def test_owner_family_view_preserves_identity_and_separate_lists(server):
 code,raw=server('/browse?owner_return=%2Fowner%2F%23storage-visit',who='owner@example.org')
 assert code==200
 page=raw.decode()
 assert 'Return to Owner workspace' in page and 'href="/owner/#storage-visit"' in page
 assert 'My List and requests here belong to you.' in page
 assert 'src="/account.js"' in page
 assert server('/api/list',who='owner@example.org',data=dict(version=0,books=['ref']))[0]==200
 assert json.loads(server('/api/me',who='owner@example.org')[1])['draft']['books']==['ref']
 assert json.loads(server('/api/me')[1])['draft']['books']==[]
 guest=server('/browse?owner_return=%2Fowner%2F%23storage-visit')[1].decode()
 assert 'Return to Owner workspace' not in guest
 assert 'Family browsing · You are still signed in as Owner' not in guest
 assert 'Sign out / Switch account' in guest
 assert server('/owner/api/state')[0]==403


def test_sign_out_page_keeps_saved_lists_and_requires_authentication(server):
 server('/api/list',data=dict(version=0,books=['ref']))
 code,raw=server('/sign-out')
 assert code==200 and b'/cdn-cgi/access/logout' in raw
 assert b'guest@example.org' in raw and b'Unsaved storage drafts stay on this device' in raw
 assert b'href="/">Keep browsing' in raw
 assert json.loads(server('/api/me')[1])['draft']['books']==['ref']
 assert server('/sign-out',who='forged')[0]==403
 assert server('/account.js',who='forged')[0]==403
 owner=server('/sign-out?owner_return=%2Fowner%2F%23storage-visit',who='owner@example.org')[1]
 assert b'href="/owner/#storage-visit">Keep browsing' in owner


def test_owner_gateway_adds_view_switch_and_account_script(server,monkeypatch):
 from valuation import family_service
 class Upstream:
  code=200
  headers={'Content-Type':'text/html'}
  def read(self):return b'<html><body><div class="brand"><strong>Library Valuation</strong></div></body></html>'
 monkeypatch.setattr(family_service,'urlopen',lambda *a,**k:Upstream())
 code,raw=server('/owner/',who='owner@example.org')
 assert code==200
 assert b'data-family-view' in raw and b'data-sign-out' in raw
 assert b'/account.js' in raw and b'nonce=' in raw
 assert server('/owner/')[0]==403


@pytest.mark.parametrize('value',['https://evil.example/owner/','//evil.example/owner/','/owner/../admin','/owner/?redirect=evil','/owner/\n','http://[invalid'])
def test_view_switch_return_path_stays_in_owner_workspace(value):
 from valuation.family_service import owner_return_path
 assert owner_return_path(value)=='/owner/'


def test_recipient_sees_pulled_without_private_pickup_notes(server,tmp_path):
 from valuation import family_owner as owner,family_requests as requests
 server('/api/list',data=dict(version=0,books=['ref']))
 sid=json.loads(server('/api/submit',data=dict(version=1,key='pulled-test'))[1])['id']
 facts={'ref':dict(copies=[dict(id='copy-1')])}
 with requests.connect(server.app.db) as db:
  owner.update(db,'owner@example.org',dict(submission=sid,reference='ref',state='approved',slot='copy-1',version=0),facts)
 server.app.config['owner_data_dir']=str(tmp_path)
 server.app.catalog=server.app.raw_catalog  # This fixture has no owner inventory model.
 entry=dict(source='pick',submission=sid,reference='ref',slot='copy-1',done=True,updated_at='2099-01-01T00:00:00+00:00',note='PRIVATE PICKUP NOTE')
 (tmp_path/'workspace_actions.json').write_text(json.dumps(dict(storage_visits={'2026-11-20':{'pick':entry}})))
 code,raw=server('/api/me')
 assert code==200
 assert json.loads(raw)['submissions'][0]['payload']['books'][0]['request_status']=='pulled'
 assert b'PRIVATE PICKUP NOTE' not in raw
 assert b'copy-1' not in raw


def test_notification_status_private_and_visits_ignore_polling(server):
 from contextlib import closing
 from valuation.family_requests import connect
 assert server('/owner/email-notifications')[0]==403
 code,body=server('/owner/email-notifications',who='owner@example.org')
 assert code==200 and b'awaiting sender setup' in body
 assert b'api_key_file' not in body
 server('/api/me')
 with closing(connect(server.app.db)) as db:
  assert db.execute('SELECT count(*) FROM notification_visits').fetchone()[0]==0
 server('/browse')
 server('/browse')
 server('/browse',who='owner@example.org')
 with closing(connect(server.app.db)) as db:
  rows=db.execute('SELECT email FROM notification_visits').fetchall()
  assert [r[0] for r in rows]==['guest@example.org']


def test_public_registration_is_isolated_and_requires_origin(server,monkeypatch):
 from valuation import registration as reg
 from valuation.family_requests import connect
 from contextlib import closing
 config=server.app.config
 secret=Path(config['database']).parent/'registration-secret';secret.write_text('synthetic-secret')
 config['registration']=dict(enabled=True,secret_file=str(secret))
 monkeypatch.setattr(reg,'lookup_zip',lambda postal:dict(places=[dict(city='Example',region='NY')]))
 assert server('/register',who='forged')[0]==200
 assert server('/register/app.js',who='forged')[0]==200
 assert server('/register/zip?postal=00501',who='forged')[0]==200
 assert server('/register/../owner/',who='forged')[0] in {403,404}
 assert server('/owner/api/users',who='forged')[0]==403
 assert server('/api/me',who='forged')[0]==403
 # Existing fixture sends the family header, not the required registration header.
 form=dict(name='Reader',email='reader@example.org',street='100 Example',country='US',postal='00501',city='Example',region='NY')
 assert server('/register/submit',who='forged',data=form)[0]==403
 with closing(connect(config['database'])) as db:
  assert db.execute('SELECT count(*) FROM registration_applications').fetchone()[0]==0
 assert server('/register/submit',who='forged',data=form,registration=True,origin='https://evil.example')[0]==403
 assert server('/register/submit',who='forged',data=form,registration=True)[0]==200
 with closing(connect(config['database'])) as db:
  row=db.execute('SELECT status FROM registration_applications').fetchone()
  assert row[0]=='unverified'
 config['registration']['enabled']=False
 assert server('/register',who='forged')[0]==404
