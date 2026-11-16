import json
from pathlib import Path
import pytest
from valuation import family_users as u,family_requests as r

@pytest.fixture
def config(tmp_path):return dict(database=str(tmp_path/'requests.sqlite'),owner_email='owner@example.org',allowed_emails=['owner@example.org','guest@example.org'],origin='https://library.example.org')

class Provider:
 def __init__(self,fail=False):self.fail=fail;self.calls=[]
 def sync(self,desired,known,owner):
  self.calls.append((desired,known,owner))
  if self.fail:raise u.SyncFailed('Unavailable')

def user(c,address):return next(x for x in u.state(c)['users'] if x['email']==address)

def test_add_verified_guest_and_name_edit(config):
 p=Provider();s=u.update(config,'owner@example.org',dict(action='add',email='New@example.org',name='New person'),p)
 assert u.allowed(config,'new@example.org')
 x=user(config,'new@example.org');assert x['active']==1 and x['role']=='guest'
 u.update(config,'owner@example.org',dict(action='edit',email=x['email'],name='Edited',version=x['version']),p)
 assert user(config,x['email'])['name']=='Edited' and len(p.calls)==1
 assert all('token' not in x for x in s)

def test_failed_enable_never_grants_and_retry_survives_restart(config):
 u.update(config,'owner@example.org',dict(action='add',email='new@example.org'),Provider(True))
 assert not u.allowed(config,'new@example.org')
 x=user(config,'new@example.org');assert x['sync']=='pending'
 u.update(dict(config),'owner@example.org',dict(action='sync',email=x['email'],version=x['version']),Provider())
 assert u.allowed(config,'new@example.org')

def test_disable_blocks_existing_session_even_on_provider_failure(config):
 x=user(config,'guest@example.org')
 u.update(config,'owner@example.org',dict(action='disable',email=x['email'],version=x['version']),Provider(True))
 assert not u.allowed(config,'guest@example.org')
 assert u.allowed(config,'owner@example.org')
 assert user(config,x['email'])['sync']=='pending'

def test_protected_owner_unauthorized_actor_and_stale_edits(config):
 with pytest.raises(PermissionError):u.update(config,'guest@example.org',dict(action='add',email='new@example.org'),Provider())
 for action in ['disable','edit','enable','sync','add']:
  with pytest.raises(ValueError):u.update(config,'owner@example.org',dict(action=action,email='owner@example.org',version=0),Provider())
 x=user(config,'guest@example.org');body=dict(action='edit',email=x['email'],version=x['version'],name='First')
 u.update(config,'owner@example.org',body,Provider())
 with pytest.raises(r.Conflict):u.update(config,'owner@example.org',body,Provider())

@pytest.mark.parametrize('address',['*','*@example.org','a?@example.org','everyone','a@*','a@example.org\nBcc:evil@example.org','a b@example.org'])
def test_individual_emails_only(address):
 with pytest.raises(ValueError):u.email(address)

def test_policy_update_preserves_settings_and_verifies():
 class CF(u.CloudflarePolicy):
  def __init__(self):self.policy=dict(name='Dedicated',decision='allow',include=[dict(email=dict(email='owner@example.org'))],require=[],exclude=[],session_duration='24h',connection_rules={'ssh':{'usernames':['test']}});self.puts=[]
  def call(self,method,payload=None):
   if method=='PUT':self.policy=dict(payload);self.puts.append(payload)
   return self.policy
 cf=CF();cf.sync({'owner@example.org','new@example.org'},{'owner@example.org','new@example.org'},'owner@example.org')
 assert cf.puts[0]['session_duration']=='24h' and cf.puts[0]['connection_rules']=={'ssh':{'usernames':['test']}}
 cf.policy['include'].append(dict(everyone={}))
 with pytest.raises(u.SyncFailed):cf.sync({'owner@example.org'},{'owner@example.org'},'owner@example.org')

def test_unexpected_provider_member_is_not_silently_removed():
 class CF(u.CloudflarePolicy):
  def call(self,method,payload=None):assert method=='GET';return dict(decision='allow',include=[dict(email=dict(email=x)) for x in ['owner@example.org','stranger@example.org']])
 with pytest.raises(u.SyncFailed):CF({}).sync({'owner@example.org'},{'owner@example.org'},'owner@example.org')

def test_missing_private_token_reports_pending_without_secret(config):
 s=u.update(config,'owner@example.org',dict(action='add',email='new@example.org'))
 assert s['notice'] and not u.allowed(config,'new@example.org')
 assert 'token_file' not in json.dumps(s)

def test_catalog_refresh_preserves_domain_connection_and_members(tmp_path):
 from operations.family_access_pilot.install_family_service import preserved_config
 state=tmp_path/'state';state.mkdir()
 before=dict(owner_email='owner@example.org',allowed_emails=['owner@example.org','guest@example.org'],origin='https://permanent.example.org',redirect_hosts=['old.example.org'],user_access={'token_file':'/private/server/token'},family_search_enabled=True)
 (state/'config.json').write_text(json.dumps(before))
 assert preserved_config(state,tmp_path/'data','owner@example.org',[])==before
 with pytest.raises(ValueError):preserved_config(state,tmp_path/'data','other@example.org',[])

def test_concurrent_first_visits_initialize_once(config):
 from concurrent.futures import ThreadPoolExecutor
 with ThreadPoolExecutor(max_workers=6) as pool:states=list(pool.map(lambda _:u.state(config),range(6)))
 assert all(len(s['users'])==2 for s in states)
