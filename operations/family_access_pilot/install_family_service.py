"""Install the isolated request service; private state remains outside the repository."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import time
from valuation.family_catalog import project
from valuation.completed_inventory import resolve_completed_inventory
from valuation.libib_catalog import StrictCatalogRepository


def install(home,owner,allowed):
    home=Path(home);root=home/'library-access-pilot';data=home/'library-valuation/data'
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in data.iterdir() if p.is_file()}
    records=project(StrictCatalogRepository(data/'catalog_items.csv').load(),resolve_completed_inventory(data))
    state=root/'state';state.mkdir(mode=0o700,exist_ok=True);os.chmod(state,0o700)
    for name,payload in [('catalog.json',records),('config.json',dict(database=str(state/'requests.sqlite'),snapshot=str(state/'catalog.json'),origin='https://library-pilot.wearyfather.org',issuer='https://frosty-rain-0886.cloudflareaccess.com',audience='d3cdd8afa98ff0e99e089fc0706e12569383c28e860367a46b0153d1294f247b',owner_data_dir=str(data),owner_output_dir=str(home/'library-valuation/output'),owner_email=owner,allowed_emails=sorted(set(allowed+[owner]))))]:
        path=state/name;tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(payload));tmp.chmod(0o600);tmp.replace(path)
    if before!={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in data.iterdir() if p.is_file()}:raise ValueError('Canonical data changed')
    plist=home/'Library/LaunchAgents/local.library-access-pilot.plist';backup=root/'static-server-before-requests.plist'
    if not backup.exists():backup.write_bytes(plist.read_bytes())
    d=plistlib.loads(plist.read_bytes());d['ProgramArguments']=[str(home/'library-valuation/.venv/bin/python'),'-m','valuation.family_service','--config',str(state/'config.json')];d['WorkingDirectory']=str(home/'library-valuation');plist.write_bytes(plistlib.dumps(d))
    subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/local.library-access-pilot'],check=True)
    deadline=time.monotonic()+10
    while True:
        result=subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],capture_output=True)
        if result.returncode==0:break
        if time.monotonic()>=deadline:raise RuntimeError('Pilot startup failed; inspect the private service logs')
        time.sleep(0.2)
    print(json.dumps(dict(records=len(records),canonical_unchanged=True,allowed_addresses=len(set(allowed+[owner])))))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--owner-email',required=True);p.add_argument('--allowed-email',action='append',default=[]);a=p.parse_args();install(Path.home(),a.owner_email.lower(),[e.lower() for e in a.allowed_email])
