"""Install a private Cloudflare connection. Enter its token only at the hidden prompt."""
import argparse,getpass,json,os,shutil
from pathlib import Path
from datetime import datetime,timezone,date
from valuation.family_users import CloudflarePolicy,state
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path);p.add_argument('--account',required=True);p.add_argument('--policy',required=True);p.add_argument('--expires-on',type=date.fromisoformat);a=p.parse_args()
if a.expires_on and a.expires_on<=date.today():p.error('Expiry must be in the future')
c=json.loads(a.config.read_text());backup=a.config.with_name('config.before_users_connection_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json');shutil.copy2(a.config,backup);backup.chmod(0o600)
token=getpass.getpass('Cloudflare Access API token (hidden): ').strip()
if not token or any(x.isspace() for x in token):raise SystemExit('Invalid token')
token_path=a.config.parent/'cloudflare-access-token';candidate=token_path.with_suffix('.pending');fd=os.open(candidate,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f:f.write(token+'\n')
c['user_access']=dict(account_id=a.account,policy_id=a.policy,token_file=str(candidate))
if a.expires_on:c['user_access']['expires_on']=a.expires_on.isoformat()
try:
 remote=CloudflarePolicy(c).addresses(CloudflarePolicy(c).call('GET'));local={u['email'] for u in state(c)['users'] if u['desired']}
 if remote!=local:raise SystemExit('Existing Cloudflare and local user lists differ; configuration was not installed')
 os.replace(candidate,token_path);c['user_access']['token_file']=str(token_path)
 new=a.config.with_suffix('.pending');new.write_text(json.dumps(c,indent=2)+'\n');new.chmod(0o600);os.replace(new,a.config)
 print('Private user-access connection verified and installed. Restart the family service.')
finally:
 if candidate.exists():candidate.unlink()
