"""Expose only /register in a separate Access application; preserve library policies."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
import requests
from operations.family_access_pilot.configure_email import private_write

NAME='Library public registration'


def enable(config_path):
    config_path=Path(config_path);config=json.loads(config_path.read_text())
    access=config['user_access'];token=Path(access['token_file']).read_text().strip()
    origin=urlsplit(config['origin'])
    if origin.scheme!='https' or origin.path or origin.query or origin.fragment:raise ValueError('Expected a secure library origin')
    domain=origin.netloc+'/register'
    base='https://api.cloudflare.com/client/v4/accounts/'+access['account_id']+'/access/apps'
    def call(method,url,body=None):
        response=requests.request(method,url,headers={'Authorization':'Bearer '+token},json=body,timeout=20,allow_redirects=False)
        if not response.ok:raise RuntimeError('Registration route setup failed (HTTP '+str(response.status_code)+'); existing library policies were not modified')
        payload=response.json()
        if not payload.get('success'):raise RuntimeError('Provider did not confirm registration route setup')
        return payload['result']
    before=call('GET',base)
    matches=[a for a in before if a.get('domain')==domain]
    if matches and (len(matches)!=1 or matches[0]['name']!=NAME):raise ValueError('A registration route already exists; review it manually')
    backup=config_path.parent/'registration-setup'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True,mode=0o700)
    private_write(backup/'access-applications-before.json',json.dumps(before,indent=2))
    private_write(backup/'config-before.json',config_path.read_text())
    if matches:application=matches[0]
    else:
        application=call('POST',base,dict(name=NAME,type='self_hosted',domain=domain,
            destinations=[dict(type='public',uri=domain)],app_launcher_visible=False))
    ident=application['id']
    # A fresh application is closed until this dedicated bypass policy is created.
    policies=call('GET',base+'/'+ident+'/policies')
    expected=dict(name='Public registration only',decision='bypass',include=[dict(everyone={})])
    if not policies:call('POST',base+'/'+ident+'/policies',expected)
    policies=call('GET',base+'/'+ident+'/policies')
    if len(policies)!=1 or any(policies[0].get(k)!=v for k,v in expected.items()) or policies[0].get('require') or policies[0].get('exclude'):
        raise RuntimeError('Registration policy differs; review before opening registration')
    after=call('GET',base)
    def signature(app):return {k:app.get(k) for k in ('id','domain','destinations','aud','policies')}
    for old in before:
        if old['id']==ident:continue
        current=next((a for a in after if a['id']==old['id']),None)
        if not current or signature(old)!=signature(current):raise RuntimeError('Existing Access settings changed during setup; review before proceeding')
    current=call('GET',base+'/'+ident)
    destinations=current.get('destinations') or [dict(type='public',uri=current.get('domain'))]
    if current.get('domain')!=domain or destinations!=[dict(type='public',uri=domain)]:raise RuntimeError('Unexpected public registration scope')
    secret_path=config_path.parent/'registration-secret'
    if not secret_path.exists():private_write(secret_path,secrets.token_urlsafe(48)+'\n')
    config['registration']=dict(enabled=True,secret_file=str(secret_path.resolve()),access_application_id=ident)
    private_write(config_path,json.dumps(config,indent=2)+'\n')
    private_write(backup/'result.json',json.dumps(dict(application_id=ident,domain=domain,existing_applications_unchanged=True)))
    print('Public registration route configured at '+config['origin']+'/register; existing library access policies preserved. Restart the family service.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default=str(Path.home()/'library-access-pilot/state/config.json'));a=p.parse_args();enable(a.config)
