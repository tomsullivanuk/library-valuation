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
 def call(path,who='guest@example.org',data=None,origin='https://family.example'):
  req=Request('http://127.0.0.1:'+str(srv.server_port)+path,data=json.dumps(data).encode() if data is not None else None,headers={'Host':'family.example','Origin':origin,'Content-Type':'application/json','X-Family-Request':'1','Cf-Access-Jwt-Assertion':who})
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
