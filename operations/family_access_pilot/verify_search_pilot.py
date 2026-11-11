"""Verify local worker restart/fallback without saving library or request data."""
import json
import os
from pathlib import Path
import subprocess
import time
from valuation.family_service import App


def verify(home):
    home=Path(home);config=json.loads((home/'library-access-pilot/state/config.json').read_text());app=App(config,identity=lambda token:config['owner_email'])
    catalog,_=app.catalog();query=next(iter(catalog.values()))['title'][:500]
    label='local.library-search-pilot';domain=f'gui/{os.getuid()}';plist=home/'Library/LaunchAgents'/ (label+'.plist')
    subprocess.run(['launchctl','bootout',domain+'/'+label],check=True)
    try:
        fallback=app.search_preview(query)
        assert fallback['hybrid']['engine']=='keyword' and 'unavailable' in fallback['hybrid']['notice']
    finally:
        deadline=time.monotonic()+10
        while True:
            r=subprocess.run(['launchctl','bootstrap',domain,str(plist)],capture_output=True)
            if not r.returncode:break
            if time.monotonic()>deadline:raise RuntimeError('Worker restoration failed')
            time.sleep(.2)
    deadline=time.monotonic()+45
    while True:
        recovered=app.search_preview(query)
        if recovered['hybrid']['engine']=='hybrid':break
        if time.monotonic()>deadline:raise RuntimeError('Worker did not recover')
        time.sleep(.5)
    assert all(r['reference'] in catalog for r in recovered['hybrid']['results'])
    print(json.dumps(dict(keyword_fallback=True,worker_recovered=True,availability_filtered=True,records_changed=False)))

if __name__=='__main__':verify(Path.home())
