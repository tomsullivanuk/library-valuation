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
 config=dict(database=str(tmp_path/'db.sqlite'),snapshot=str(snap),origin='https://family.example',allowed_emails=['owner@example.org','guest@example.org'],owner_email='owner@example.org')
 def identity(token):
  if token not in ['owner@example.org','guest@example.org']:raise ValueError()
  return token
 app=App(config,identity);srv=ThreadingHTTPServer(('127.0.0.1',0),app.handler());threading.Thread(target=srv.serve_forever,daemon=True).start()
 def call(path,who='guest@example.org',data=None,origin='https://family.example'):
  req=Request('http://127.0.0.1:'+str(srv.server_port)+path,data=json.dumps(data).encode() if data is not None else None,headers={'Host':'family.example','Origin':origin,'Content-Type':'application/json','X-Family-Request':'1','Cf-Access-Jwt-Assertion':who})
  try:r=urlopen(req)
  except HTTPError as e:r=e
  return r.code,r.read()
 yield call
 srv.shutdown();srv.server_close()

def test_http_ownership_and_csrf(server):
 assert server('/api/me',who='forged')[0]==403
 assert server('/api/inbox')[0]==403
 assert server('/api/list',data=dict(version=0,books=['ref']),origin='https://evil.example')[0]==403
 assert server('/api/list',data=dict(version=0,books=['ref']))[0]==200
 assert json.loads(server('/api/me',who='owner@example.org')[1])['draft']['books']==[]
 assert server('/api/submit',data=dict(version=1,key='retry'))[0]==200
 assert server('/api/submit',data=dict(version=1,key='retry'))[0]==200
 assert len(json.loads(server('/api/inbox',who='owner@example.org')[1]))==1
 assert server('/../../db.sqlite')[0]==404
 assert b'data-ref="ref"' in server('/')[1]

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
