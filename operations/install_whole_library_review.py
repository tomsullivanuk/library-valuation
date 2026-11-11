"""Install a finite review job as a macOS user LaunchAgent (no administrator changes)."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys

LABEL='local.library-valuation.whole-review'


def configuration(project,root,credentials,python,logs,*,provider_counts=False):
    module='valuation.provider_quota_controller' if provider_counts else 'valuation.whole_library_review'
    return dict(Label=LABEL,ProgramArguments=[str(python),'-m',module,'run','--root',str(root),'--credentials',str(credentials)],WorkingDirectory=str(project),RunAtLoad=True,KeepAlive={'SuccessfulExit':False},ThrottleInterval=60,ProcessType='Background',EnvironmentVariables={'PYTHONUNBUFFERED':'1'},StandardOutPath=str(logs/'whole-library-review.log'),StandardErrorPath=str(logs/'whole-library-review.error.log'))


def install(project,root,credentials):
    if sys.platform!='darwin':raise ValueError('Requires the authoritative macOS host')
    project,root,credentials=map(lambda p:Path(p).expanduser().resolve(),(project,root,credentials))
    if not (root/'manifest.json').is_file() or not credentials.is_file():raise ValueError('Prepare the job and private credentials first')
    domain=f'gui/{os.getuid()}'
    subprocess.run(['launchctl','print',domain],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    logs=Path.home()/'Library/Logs/LibraryValuation';logs.mkdir(parents=True,exist_ok=True)
    directory=Path.home()/'Library/LaunchAgents';directory.mkdir(parents=True,exist_ok=True)
    path=directory/(LABEL+'.plist');config=configuration(project,root,credentials,sys.executable,logs,provider_counts=(root/'provider_quota_policy.json').exists())
    if path.exists():
        if plistlib.loads(path.read_bytes())!=config:raise ValueError('A different review job is already installed; preserve its state')
        print('The matching review job is already installed.');return
    with path.open('xb') as f:os.chmod(path,0o600);plistlib.dump(config,f)
    subprocess.run(['plutil','-lint',str(path)],check=True)
    subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
    print('Finite review job installed. It continues after login/reboot and exits on completion or a critical stop.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',required=True);p.add_argument('--root',required=True);p.add_argument('--credentials',required=True)
    a=p.parse_args();install(a.project,a.root,a.credentials)
