"""Public applications and owner-reviewed access. Private records stay in SQLite."""
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import html
import json
from pathlib import Path
import re
import secrets
import uuid

from valuation import family_requests as ledger, family_users as users
from valuation import family_notifications as mail


def schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS registration_applications(
      id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,address TEXT NOT NULL,
      status TEXT NOT NULL,version INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,
      token_hash TEXT NOT NULL,expires TEXT NOT NULL,verified TEXT,note TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS registration_events(id INTEGER PRIMARY KEY,application TEXT,actor TEXT,created TEXT,action TEXT,note TEXT);
    CREATE TABLE IF NOT EXISTS registration_limits(bucket TEXT PRIMARY KEY,count INTEGER NOT NULL);
    ''')


def initialize(config):
    with closing(ledger.connect(config['database'])) as db:
        schema(db)
        if config.get('owner_email'):
            users.schema(db,dict(config,allowed_emails=config.get('allowed_emails',[])))


def text(value, label, limit, required=True):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError('Enter a valid '+label)
    value=value.strip()
    if required and not value:raise ValueError('Enter your '+label)
    return value


def address(body):
    if body.get('country','US')!='US':raise ValueError('Registration is limited to U.S. mailing addresses')
    result=dict(country='US',street=text(body.get('street',''),'street address',200),
                unit=text(body.get('unit',''),'apartment or unit',100,False),
                postal=text(body.get('postal',''),'postal code',20),
                city=text(body.get('city',''),'city',100),region=text(body.get('region',''),'state or region',100,False))
    if not re.fullmatch(r'\d{5}(-\d{4})?',result['postal']):raise ValueError('Enter a five-digit ZIP or ZIP+4')
    if not re.fullmatch('[A-Za-z]{2}',result['region']):raise ValueError('Confirm the two-letter mailing state')
    result['region']=result['region'].upper()
    return result


def throttle(db, identity, now, limit=5):
    # Fixed-window counts are durable across workers/restarts. No raw IP is kept.
    hour=now.strftime('%Y%m%d%H')
    key=hour+':'+identity
    count=db.execute('SELECT count FROM registration_limits WHERE bucket=?',(key,)).fetchone()
    if count and count[0]>=limit:raise ValueError('Too many attempts. Please try again later.')
    db.execute('INSERT INTO registration_limits VALUES(?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1',(key,))
    db.execute('DELETE FROM registration_limits WHERE bucket<?',((now-timedelta(days=2)).strftime('%Y%m%d%H'),))


def client_identity(config, ip):
    # Salt with a private stable server value; never publish network identifiers.
    salt=Path(config['registration']['secret_file']).read_text().strip()
    import hmac
    return hmac.new(salt.encode(),ip.encode(),hashlib.sha256).hexdigest()


def queue(db, config, key, recipient, subject, body):
    mail.enqueue(db,key,subject,body,recipient=recipient)


def apply(config, body, identity, now=None):
    now=now or datetime.now(timezone.utc)
    email=users.email(body.get('email',''))
    name=text(body.get('name',''),'name',100)
    postal=address(body)
    if body.get('website'):return # honeypot: normal generic response without mail
    stamp=now.isoformat()
    with closing(ledger.connect(config['database'])) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            throttle(db,identity,now)
            throttle(db,'global',now,30)
            throttle(db,'email:'+hashlib.sha256(email.encode()).hexdigest(),now,2)
            existing=db.execute('SELECT * FROM registration_applications WHERE email=?',(email,)).fetchone()
            if existing and (existing['status']!='unverified' or existing['expires']>stamp):return
            # Existing guests use their current access; submitting a form never enables/re-enables them.
            if email==config['owner_email'] or db.execute('SELECT 1 FROM family_users WHERE email=?',(email,)).fetchone():return
            ident=existing['id'] if existing else str(uuid.uuid4())
            token=secrets.token_urlsafe(32)
            digest=hashlib.sha256(token.encode()).hexdigest()
            expires=(now+timedelta(hours=24)).isoformat()
            if existing:
                db.execute("UPDATE registration_applications SET name=?,address=?,version=version+1,created=?,updated=?,token_hash=?,expires=? WHERE id=?",
                           (name,json.dumps(postal),stamp,stamp,digest,expires,ident))
            else:
                db.execute('INSERT INTO registration_applications(id,email,name,address,status,version,created,updated,token_hash,expires) VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (ident,email,name,json.dumps(postal),'unverified',0,stamp,stamp,digest,expires))
            queue(db,config,'registration/verify/'+digest,email,'Confirm your library registration',
                  'Please confirm your email address to submit your application for access to the Thomas D Sullivan Library.\n\n'+
                  config['origin']+'/register/verify?token='+token+
                  '\n\nThis link expires in 24 hours. Confirming your email does not grant access; Tom will review your application. If you did not apply, ignore this email.')


def token_row(db, token, now):
    if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,100}',token):raise ValueError('This confirmation link is invalid or expired. Please register again.')
    row=db.execute('SELECT * FROM registration_applications WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row or row['expires']<now.isoformat():raise ValueError('This confirmation link is invalid or expired. Please register again.')
    return row


def format_address(value):
    a=json.loads(value) if isinstance(value,str) else value
    return ', '.join(v for v in (a['street'],a.get('unit'),a['city'],a.get('region'),a['postal'],a['country']) if v)


def verify(config, token, now=None):
    now=now or datetime.now(timezone.utc)
    with closing(ledger.connect(config['database'])) as db,db:
        db.execute('BEGIN IMMEDIATE')
        row=token_row(db,token,now)
        if row['status']!='unverified':return
        db.execute("UPDATE registration_applications SET status='pending',version=version+1,verified=?,updated=? WHERE id=?",(now.isoformat(),now.isoformat(),row['id']))
        db.execute('INSERT INTO registration_events(application,actor,created,action,note) VALUES(?,?,?,?,?)',(row['id'],row['email'],now.isoformat(),'email_verified',''))
        queue(db,config,'registration/owner/'+row['id'],mail.RECIPIENT,'Library access application — '+row['name'],
              'New verified application\n\nName: '+row['name']+'\nEmail: '+row['email']+'\nAddress: '+format_address(row['address'])+
              '\n\nReview application (Owner sign-in required):\n'+config['origin']+'/owner/#users/'+row['id']+
              '\n\nOpening this link does not approve or decline access. Review the details and confirm your decision on the Users page.')


def state(config):
    with closing(ledger.connect(config['database'])) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='registration_applications'").fetchone():return []
        rows=[dict(r) for r in db.execute("SELECT id,email,name,address,status,version,created,updated,verified,note FROM registration_applications WHERE status!='unverified' ORDER BY CASE WHEN status IN ('pending','approving') THEN 0 ELSE 1 END,created DESC")]
        for row in rows:row['address']=json.loads(row['address'])
    return rows


@contextmanager
def decision_lock(config):
    with Path(config['database']).with_suffix('.registration.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield


def decide(config,actor,body,provider=None):
    if actor!=config['owner_email']:raise PermissionError('Owner access required')
    action=body.get('action');note=body.get('note','')
    if not isinstance(note,str) or len(note)>1000 or any(ord(c)<32 and c not in '\n\t' for c in note):raise ValueError('Enter a valid note of at most 1000 characters')
    note=note.strip()
    if action not in {'approve','decline'} or type(body.get('version')) is not int:raise ValueError('Invalid application decision')
    with decision_lock(config),closing(ledger.connect(config['database'])) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM registration_applications WHERE id=?',(body.get('id'),)).fetchone()
            if not row:raise ValueError('Unknown application')
            if row['version']!=body['version'] or row['status'] not in {'pending','approving'}:raise ledger.Conflict('This application changed. Refresh before deciding.')
            if row['status']=='approving' and action=='decline':raise ValueError('Access approval is in progress. Resolve it before declining.')
            stamp=datetime.now(timezone.utc).isoformat()
            status='approving' if action=='approve' else 'declined'
            db.execute('UPDATE registration_applications SET status=?,version=version+1,updated=?,note=? WHERE id=?',(status,stamp,note,row['id']))
            db.execute('INSERT INTO registration_events(application,actor,created,action,note) VALUES(?,?,?,?,?)',(row['id'],actor,stamp,action,note))
        if action=='approve':
            current=next((u for u in users.state(config)['users'] if u['email']==row['email']),None)
            if not current:
                users.update(config,actor,dict(action='add',email=row['email'],name=row['name']),provider)
            elif not (current['active'] and current['sync']=='synced'):
                users.update(config,actor,dict(action='enable' if not current['desired'] else 'sync',email=row['email'],version=current['version']),provider)
            current=next(u for u in users.state(config)['users'] if u['email']==row['email'])
            if not (current['active'] and current['sync']=='synced'):
                return dict(applications=state(config),notice='Access is not yet confirmed. Retry approval to finish synchronization; no approval email has been sent.')
            with db:
                db.execute("UPDATE registration_applications SET status='approved',version=version+1,updated=? WHERE id=?",(stamp,row['id']))
                queue(db,config,'registration/approved/'+row['id'],row['email'],'Your library access is approved',
                      'Hi '+row['name']+',\n\nYour access to the Thomas D Sullivan Library has been approved.\n\nOpen '+config['origin']+
                      '/ and sign in using '+row['email']+'. Cloudflare will email a one-time access code to that address. Check Spam if it does not arrive.\n\nBrowse the collection, add books to My List, and submit your requests when ready. Requests are subject to availability and owner confirmation.\n\n'+
                      ('Note from Tom: '+note+'\n\n' if note else '')+'If you need help, contact Tom at '+config['owner_email']+'.')
        else:
            with db:
                queue(db,config,'registration/declined/'+row['id'],row['email'],'About your library access application',
                      'Hi '+row['name']+',\n\nYour application for access to the Thomas D Sullivan Library has not been approved. Please contact Tom directly at '+config['owner_email']+' to review your application.\n\n'+
                      ('Note from Tom: '+note+'\n' if note else ''))
    return dict(applications=state(config))


def lookup_zip(postal):
    if not re.fullmatch(r'\d{5}',postal):raise ValueError('Enter a five-digit ZIP')
    import requests
    try:
        response=requests.get('https://api.zippopotam.us/us/'+postal,timeout=4)
        response.raise_for_status()
        places=response.json()['places']
        return dict(places=[dict(city=text(p['place name'],'city',100),region=text(p['state abbreviation'],'state',2)) for p in places[:30]])
    except (requests.RequestException,KeyError,ValueError,TypeError):
        return dict(places=[],notice='City and state could not be filled in. Please enter them below.')


STYLE='body{max-width:680px;margin:2rem auto;padding:1rem;font:18px/1.5 system-ui;color:#25372e;background:#faf9f5}h1,a{color:#245d49}label{display:block;margin:.8rem 0}input,select,button,textarea{box-sizing:border-box;font:inherit;padding:.65rem;max-width:100%;width:100%}button{background:#245d49;color:white;border:0;border-radius:6px;margin-top:1rem;min-height:44px}.muted{color:#5d6a62}.trap{position:absolute;left:-9999px}[hidden]{display:none!important}.registration-brand{margin:0 0 1.5rem;text-align:center}.registration-brand img{display:block;width:min(100%,380px);height:auto;margin:0 auto;border-radius:8px}@media(max-width:480px){body{margin:.75rem auto}.registration-brand{margin-bottom:1rem}.registration-brand img{max-width:280px}}'


def page(content, script=False):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Library registration</title><style>'+STYLE+'</style><main><header class="registration-brand"><img src="/register/emblem.png" width="1536" height="1024" alt="Thomas D. Sullivan Library &amp; Archive emblem, showing Thomas reading among bookshelves" fetchpriority="high" decoding="async"></header>'+content+'</main>'+('<script src="/register/app.js" defer></script>' if script else '')+'</html>'


def form_page():
    return page('''<h1>Request library access</h1><p>Apply to browse and request books from the Thomas D Sullivan Library.</p>
<p class="muted">Your name and mailing address are required to facilitate pickup and delivery. Registration is limited to U.S. mailing addresses.</p>
<form id="registration"><label>Name<input name="name" autocomplete="name" maxlength="100" required></label><label>Email<input name="email" type="email" autocomplete="email" maxlength="254" required></label>
<label>Street address<input name="street" autocomplete="address-line1" maxlength="200" required></label><label>Apartment / unit (optional)<input name="unit" autocomplete="address-line2" maxlength="100"></label>
<label id="postal-label">ZIP code<input name="postal" autocomplete="postal-code" inputmode="numeric" maxlength="10" required></label><p id="zip-status" class="muted" role="status">Enter your ZIP and we’ll suggest the mailing city and state.</p>
<label id="place-choice" hidden>Mailing city<select id="places"></select></label><details id="city-details"><summary id="city-summary">City and state — filled from ZIP; open to correct</summary><label>City<input name="city" autocomplete="address-level2" maxlength="100" required></label><label>State<input name="region" autocomplete="address-level1" maxlength="100"></label></details>
<label class="trap" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label><button>Send confirmation email</button><p id="form-status" role="status"></p></form><p><a href="/">Already approved? Sign in to the library</a></p>''',True)


def verify_page(config,token):
    with closing(ledger.connect(config['database'])) as db:row=token_row(db,token,datetime.now(timezone.utc))
    if row['status']!='unverified':return page('<h1>Email confirmed</h1><p>Your application has been submitted. You’ll receive an email after it has been reviewed.</p>')
    return page('<h1>Confirm your email</h1><p>Confirm your email to submit your library access application. This does not grant access yet.</p><form id="verify"><input type="hidden" name="token" value="'+html.escape(token,quote=True)+'"><button>Confirm email and submit application</button><p id="form-status" role="status"></p></form>',True)


def public_request(config, handler, path, write):
    """Exact public routes only; callers dispatch before Access authentication."""
    from urllib.parse import parse_qs, urlsplit
    if not config.get('registration',{}).get('enabled'):
        return handler.reply(404,{'error':'Registration is not open'})
    if not write:
        if path in {'/register','/register/'}:return handler.reply(200,form_page(),'text/html')
        if path=='/register/emblem.png':return handler.reply(200,(Path(__file__).parent/'assets/library-emblem.png').read_bytes(),'image/png')
        if path=='/register/app.js':return handler.reply(200,Path(__file__).with_name('registration_app.js').read_text(),'text/javascript')
        if path=='/register/verify':
            token=parse_qs(urlsplit(handler.path).query).get('token',[''])[0]
            try:return handler.reply(200,verify_page(config,token),'text/html')
            except ValueError as exc:return handler.reply(400,page('<h1>Confirmation link unavailable</h1><p>'+html.escape(str(exc))+'</p><a href="/register">Register again</a>'),'text/html')
        if path=='/register/zip':
            with closing(ledger.connect(config['database'])) as db,db:
                db.execute('BEGIN IMMEDIATE')
                throttle(db,'zip:'+client_identity(config,handler.headers.get('CF-Connecting-IP') or handler.client_address[0]),datetime.now(timezone.utc),60)
            return handler.reply(200,lookup_zip(parse_qs(urlsplit(handler.path).query).get('postal',[''])[0]))
        return handler.reply(404,{'error':'Not found'})
    if path not in {'/register/submit','/register/confirm'}:return handler.reply(404,{'error':'Not found'})
    if handler.headers.get('Origin')!=config['origin'] or handler.headers.get('Content-Type')!='application/json' or handler.headers.get('X-Registration')!='1':
        return handler.reply(403,{'error':'Open the registration page before submitting'})
    length=int(handler.headers.get('Content-Length','0'))
    if not 0<length<=8192:return handler.reply(413,{'error':'Application is too large'})
    body=json.loads(handler.rfile.read(length))
    if not isinstance(body,dict):raise ValueError('Invalid application')
    identity=client_identity(config,handler.headers.get('CF-Connecting-IP') or handler.client_address[0])
    if path=='/register/submit':apply(config,body,identity)
    else:
        with closing(ledger.connect(config['database'])) as db,db:
            db.execute('BEGIN IMMEDIATE');throttle(db,'verify:'+identity,datetime.now(timezone.utc),30)
        verify(config,body.get('token'))
    return handler.reply(200,dict(ok=True))
