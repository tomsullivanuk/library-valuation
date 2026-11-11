"""Install the invented-book pilot as a login startup service on the Mini."""
from pathlib import Path
import plistlib
import subprocess
import os

home = Path.home()
root = home / 'library-access-pilot'
public = root / 'public'
public.mkdir(parents=True, exist_ok=True)
source = Path(__file__).resolve().parents[2] / 'prototypes/sites-access-pilot/dist/index.html'
(public / 'index.html').write_bytes(source.read_bytes())
label = 'local.library-access-pilot'
plist = home / 'Library/LaunchAgents' / (label + '.plist')
plist.parent.mkdir(parents=True, exist_ok=True)
plist.write_bytes(plistlib.dumps(dict(
    Label=label, RunAtLoad=True, KeepAlive=True, ThrottleInterval=10,
    ProgramArguments=[str(home/'library-valuation/.venv/bin/python'), '-m', 'http.server',
                      '8877', '--bind', '127.0.0.1', '--directory', str(public)],
    StandardOutPath=str(root/'server.log'), StandardErrorPath=str(root/'server-error.log'))))
subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], capture_output=True)
subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(plist)], check=True)
print('Sample server installed; requires automatic user login after reboot.')
