"""Install owner-only local AI preview after its offline index has been built."""
import json
import os
from pathlib import Path
import plistlib
import secrets
import subprocess
import time
from valuation.family_search import fingerprint
REVISION='1110a243fdf4706b3f48f1d95db1a4f5529b4d41'


def install(home,enable_family=False):
    home=Path(home);root=home/'library-access-pilot';private=root/'search-pilot'
    private.mkdir(exist_ok=True,mode=0o700);private.chmod(0o700)
    config_path=root/'state/config.json';config=json.loads(config_path.read_text())
    records=json.loads(Path(config['snapshot']).read_text())
    if json.loads((private/'manifest.json').read_text())['fingerprint']!=fingerprint(records):raise ValueError('Rebuild stale search index before installation')
    if not (private/'report.html').exists():raise ValueError('Evaluate before enabling preview')
    model=root/'model-cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots'/REVISION
    token=private/'worker-token'
    if not token.exists():token.write_text(secrets.token_urlsafe(32))
    token.chmod(0o600)
    label='local.library-search-pilot'
    plist=home/'Library/LaunchAgents'/ (label+'.plist')
    arguments=[str(root/'search-venv/bin/python'),'-m','valuation.family_search_pilot','serve','--snapshot',config['snapshot'],'--model',str(model),'--directory',str(private),'--token',str(token)]
    data=dict(Label=label,ProgramArguments=arguments,WorkingDirectory=str(home/'library-valuation'),RunAtLoad=True,KeepAlive=True,ThrottleInterval=20,EnvironmentVariables=dict(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1',TOKENIZERS_PARALLELISM='false'),StandardOutPath=str(private/'worker.out.log'),StandardErrorPath=str(private/'worker.err.log'))
    plist.write_bytes(plistlib.dumps(data));plist.chmod(0o600)
    subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+10
    while True:
        result=subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],capture_output=True)
        if not result.returncode:break
        if time.monotonic()>deadline:raise RuntimeError('Search worker startup failed')
        time.sleep(.2)
    backup=private/'config-before-preview.json'
    if not backup.exists():backup.write_bytes(config_path.read_bytes());backup.chmod(0o600)
    config['search_pilot_dir']=str(private)
    if enable_family:config['family_search_enabled']=True
    temp=config_path.with_suffix('.tmp');temp.write_text(json.dumps(config));temp.chmod(0o600);temp.replace(config_path)
    print(json.dumps(dict(owner_preview_configured=True,family_search_enabled=bool(config.get('family_search_enabled')))))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--enable-family',action='store_true');args=parser.parse_args();install(Path.home(),args.enable_family)
