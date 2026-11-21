"""Owner-only guest administration; credentials never cross the HTTP boundary."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import requests
from valuation import family_requests as ledger

class SetupRequired(ValueError): pass
class SyncFailed(ValueError): pass


def stamp():return datetime.now(timezone.utc).isoformat()


def email(value):
    if not isinstance(value,str) or len(value)>254 or '*' in value or '?' in value or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",value.strip()):raise ValueError('Enter a valid individual email address')
    return value.strip().lower()


def schema(db, config):
    db.executescript('''CREATE TABLE IF NOT EXISTS family_users(email TEXT PRIMARY KEY,name TEXT NOT NULL,desired INTEGER NOT NULL,active INTEGER NOT NULL,sync TEXT NOT NULL,version INTEGER NOT NULL,last_seen TEXT,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_events(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,email TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
    with db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("SELECT 1 FROM user_meta WHERE key='initialized'").fetchone():
            for address in set(config['allowed_emails']+[config['owner_email']]):
                db.execute('INSERT OR IGNORE INTO family_users VALUES(?,?,?,?,?,?,?,?)',(email(address),'',1,1,'synced',0,None,stamp()))
            db.execute("INSERT INTO user_meta VALUES('initialized','1')")


def allowed(config, address, touch=False):
    if address==config['owner_email']:return True
    with closing(ledger.connect(config['database'])) as db:
        schema(db,config)
        row=db.execute('SELECT active FROM family_users WHERE email=?',(address,)).fetchone()
        if not row or not row['active']:return False
        if touch:
            with db:db.execute('UPDATE family_users SET last_seen=? WHERE email=?',(stamp(),address))
        return True


@contextmanager
def locked(config):
    p=Path(config['database']).with_suffix('.users.lock')
    fd=os.open(p,os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(fd,'w') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield


class CloudflarePolicy:
    def __init__(self,config):
        self.config=config
    def call(self,method,payload=None):
        cfg=self.config.get('user_access',{})
        if not all(cfg.get(k) for k in ('account_id','policy_id','token_file')):raise SetupRequired('User administration needs its private access connection configured')
        if not re.fullmatch(r'[0-9a-f]{32}',cfg['account_id']) or not re.fullmatch(r'[0-9a-f-]{36}',cfg['policy_id']):raise SetupRequired('Invalid access connection')
        p=Path(cfg['token_file'])
        if not p.is_file() or p.stat().st_mode & 0o077:raise SetupRequired('The access token must be in a private server-side file')
        token=p.read_text().strip()
        if not token:raise SetupRequired('The access token file is empty')
        try:
            response=requests.request(method,f"https://api.cloudflare.com/client/v4/accounts/{cfg['account_id']}/access/policies/{cfg['policy_id']}",headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},json=payload,timeout=15,allow_redirects=False)
            if response.status_code!=200:raise SyncFailed('Access provider update failed; no successful invitation is confirmed')
            body=response.json()
            if not body.get('success') or not isinstance(body.get('result'),dict):raise SyncFailed('Access provider did not confirm the update')
            return body['result']
        except (requests.RequestException,json.JSONDecodeError):raise SyncFailed('Access provider is unavailable; retry synchronization') from None
    @staticmethod
    def addresses(policy):
        if policy.get('decision')!='allow' or not policy.get('include') or policy.get('require') or policy.get('exclude'):raise SyncFailed('Access policy changed; administrator review is required')
        result=set()
        for rule in policy['include']:
            if set(rule)!={'email'} or set(rule['email'])!={'email'}:raise SyncFailed('Only the dedicated individual-email policy can be managed')
            result.add(email(rule['email']['email']))
        return result
    def sync(self,desired,known,owner):
        before=self.call('GET');actual=self.addresses(before)
        if owner not in actual or not actual<=known:raise SyncFailed('Unexpected access-policy members; review the policy before syncing')
        # Preserve every non-identity setting; omit server-owned metadata only.
        fields={'name','decision','include','exclude','require','session_duration','approval_groups','approval_required','purpose_justification_prompt','purpose_justification_required','isolation_required','connection_rules','mfa_config'}
        body={k:v for k,v in before.items() if k in fields}
        body['include']=[{'email':{'email':a}} for a in sorted(desired)]
        if actual!=desired:self.call('PUT',body)
        after=self.call('GET')
        if self.addresses(after)!=desired:raise SyncFailed('Access-policy verification failed; local access stays restricted')


def state(config):
    with closing(ledger.connect(config['database'])) as db:
        schema(db,config)
        users=[]
        for row in db.execute('SELECT * FROM family_users ORDER BY email'):
            u=dict(row);u['role']='owner' if u['email']==config['owner_email'] else 'guest'
            u['request_count']=db.execute('SELECT count(*) FROM submissions WHERE email=?',(u['email'],)).fetchone()[0]
            users.append(u)
        history=[dict(r) for r in db.execute('SELECT actor,email,created,payload FROM user_events ORDER BY id DESC LIMIT 100')]
        for event in history:event['details']=json.loads(event.pop('payload'))
    cfg=config.get('user_access',{})
    return dict(users=users,history=history,origin=config['origin'],configured=bool(cfg.get('token_file') and Path(cfg['token_file']).is_file()),connection_expires_on=cfg.get('expires_on'),owner=config['owner_email'])


def update(config,actor,body,provider=None):
    if actor!=config['owner_email']:raise PermissionError('Owner access required')
    action=body.get('action');address=email(body.get('email',''));owner=config['owner_email']
    if action not in ('add','edit','enable','disable','sync'):raise ValueError('Unknown user action')
    if address==owner:raise ValueError('Owner access cannot be changed here')
    name=body.get('name','')
    if not isinstance(name,str) or len(name)>100 or any(ord(x)<32 for x in name):raise ValueError('Name must be at most 100 characters')
    with locked(config),closing(ledger.connect(config['database'])) as db:
        schema(db,config)
        old=db.execute('SELECT * FROM family_users WHERE email=?',(address,)).fetchone()
        if action=='add':
            if old:raise ledger.Conflict('That address already exists; edit or enable the existing user')
            with db:db.execute('INSERT INTO family_users VALUES(?,?,?,?,?,?,?,?)',(address,name.strip(),1,0,'pending',1,None,stamp()))
        else:
            if not old:raise ValueError('Unknown user')
            if type(body.get('version')) is not int or body['version']!=old['version']:raise ledger.Conflict('This user changed; refresh before editing')
            desired=0 if action=='disable' else 1 if action=='enable' else old['desired']
            with db:db.execute('UPDATE family_users SET name=?,desired=?,active=?,sync=?,version=version+1,updated=? WHERE email=?',
                (name.strip() if action=='edit' else old['name'],desired,0 if action=='disable' else old['active'],old['sync'] if action=='edit' else 'pending',stamp(),address))
        with db:db.execute('INSERT INTO user_events(actor,email,created,payload) VALUES(?,?,?,?)',(actor,address,stamp(),json.dumps(dict(action=action,before=dict(old) if old else None))))
        if action=='edit':return state(config)
        known={r[0] for r in db.execute('SELECT email FROM family_users')}
        desired={r[0] for r in db.execute('SELECT email FROM family_users WHERE desired=1')}|{owner}
        try:
            (provider or CloudflarePolicy(config)).sync(desired,known,owner)
        except (SetupRequired,SyncFailed) as exc:
            # Disable is already effective locally even if the remote gate fails.
            with db:db.execute("UPDATE family_users SET sync='pending' WHERE sync!='synced'")
            result=state(config);result['notice']=str(exc);return result
        with db:
            db.execute("UPDATE family_users SET active=desired,sync='synced',version=version+1 WHERE sync!='synced'")
            db.execute('INSERT INTO user_events(actor,email,created,payload) VALUES(?,?,?,?)',(actor,address,stamp(),json.dumps(dict(action='access_verified',active=address in desired))))
    return state(config)
