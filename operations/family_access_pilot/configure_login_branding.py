"""Apply library login appearance only; retain Access authentication settings."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import requests
from operations.family_access_pilot.configure_email import private_write


def configure(config_path):
    config_path=Path(config_path)
    config=json.loads(config_path.read_text())
    access=config['user_access']
    url='https://api.cloudflare.com/client/v4/accounts/'+access['account_id']+'/access/organizations'
    headers={'Authorization':'Bearer '+Path(access['token_file']).read_text().strip()}
    def call(method,body=None):
        r=requests.request(method,url,headers=headers,json=body,timeout=20,allow_redirects=False)
        if not r.ok:raise RuntimeError('Login branding connection returned HTTP '+str(r.status_code))
        data=r.json()
        if not data.get('success'):raise RuntimeError('Login branding was not confirmed')
        return data['result']
    before=call('GET')
    backup=config_path.parent/'login-branding-backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True,mode=0o700)
    private_write(backup/'organization-before.json',json.dumps(before,indent=2))
    design=dict(before.get('login_design') or {})
    design.update(logo_path=config['origin']+'/register/emblem.png',background_color='#faf9f5',text_color='#25372e',header_text='Thomas D Sullivan Library',footer_text='Enter your approved email address. Cloudflare, our secure sign-in service, will email your login code from noreply@notify.cloudflare.com. Check Spam or Junk if it does not arrive.')
    # A partial update changes appearance and display name only; never change auth_domain.
    call('PUT',dict(name='Thomas D Sullivan Library',login_design=design))
    after=call('GET')
    assert after.get('name')=='Thomas D Sullivan Library'
    assert all(after.get('login_design',{}).get(k)==v for k,v in design.items())
    for key,value in before.items():
        if key not in {'name','login_design','updated_at'}:
            assert after.get(key)==value, 'Unexpected change to organization setting: '+key
    print('Library login branding verified; authentication settings unchanged.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    configure(parser.parse_args().config)
