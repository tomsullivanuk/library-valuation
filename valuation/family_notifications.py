"""Private owner alerts, visitor summaries, and a durable email outbox."""
import hashlib
import json
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from valuation.family_requests import connect

RECIPIENT = 'tomsullivanuk@gmail.com'
ZONE = ZoneInfo('America/Chicago')


def schema(db, now):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS notification_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_visits(day TEXT,email TEXT,first TEXT,last TEXT,PRIMARY KEY(day,email));
    CREATE TABLE IF NOT EXISTS notification_outbox(id TEXT PRIMARY KEY,subject TEXT,text TEXT,payload TEXT,
      state TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,first_attempt TEXT,
      next_attempt TEXT,provider_id TEXT,error TEXT);
    ''')
    with db:
        db.execute('INSERT OR IGNORE INTO notification_meta VALUES(?,?)', ('started', now.isoformat()))
        db.execute('INSERT OR IGNORE INTO notification_meta VALUES(?,?)', ('digest_day', now.astimezone(ZONE).date().isoformat()))


def initialize(path, now=None):
    with closing(connect(path)) as db:
        schema(db, now or datetime.now(timezone.utc))


def visit(path, email, owner, now=None):
    if email == owner:
        return
    now = now or datetime.now(timezone.utc)
    with closing(connect(path)) as db, db:
        db.execute('''INSERT INTO notification_visits VALUES(?,?,?,?)
          ON CONFLICT(day,email) DO UPDATE SET last=excluded.last''',
          (now.astimezone(ZONE).date().isoformat(), email, now.isoformat(), now.isoformat()))


def enqueue(db, key, subject, text):
    db.execute('INSERT OR IGNORE INTO notification_outbox(id,subject,text) VALUES(?,?,?)', (key, subject, text))


def prepare(db, origin, now):
    """Reconcile committed submissions; restart-safe and no historical request blast."""
    start = db.execute("SELECT value FROM notification_meta WHERE key='started'").fetchone()[0]
    for row in db.execute('SELECT * FROM submissions WHERE created>=? ORDER BY created', (start,)).fetchall():
        data = json.loads(row['payload'])
        titles = '\n'.join('• '+b['title'] for b in data['books'])
        enqueue(db, 'request/'+row['id'], 'Library: new book request',
                f"From: {row['email']}\nSubmitted: {row['created']}\n\n{titles}\n\nMessage:\n{data.get('message') or '(No message)'}\n\nReview: {origin}/owner/#requests")
    local = now.astimezone(ZONE)
    if local.hour < 8:
        return
    day = datetime.fromisoformat(db.execute("SELECT value FROM notification_meta WHERE key='digest_day'").fetchone()[0]).date()
    while day < local.date():
        rows = db.execute('SELECT * FROM notification_visits WHERE day=? ORDER BY email', (day.isoformat(),)).fetchall()
        if rows:
            lines = []
            for r in rows:
                first = datetime.fromisoformat(r['first']).astimezone(ZONE).strftime('%I:%M %p')
                last = datetime.fromisoformat(r['last']).astimezone(ZONE).strftime('%I:%M %p')
                lines.append(f"{r['email']} — first visit {first}; last activity {last}")
            enqueue(db, 'visitors/'+day.isoformat(), 'Library visitors — '+day.isoformat(),
                    'Guest activity for '+day.isoformat()+' (America/Chicago)\n\n'+'\n'.join(lines)+
                    '\n\nThese are authenticated site visits, not fresh sign-ins. Owner activity is excluded.\n\n'+origin+'/owner/')
        day += timedelta(days=1)
        db.execute("UPDATE notification_meta SET value=? WHERE key='digest_day'", (day.isoformat(),))



class AmbiguousSMTP(Exception):
    """The server may have accepted DATA; retrying might duplicate the email."""


def send_icloud(mail, password, payload, key, first, mark_sending):
    import smtplib
    import ssl
    import requests
    from email.message import EmailMessage
    from email.utils import format_datetime
    message = EmailMessage()
    message['From'] = payload['sender']
    message['To'] = RECIPIENT
    message['Subject'] = payload['subject']
    message['Date'] = format_datetime(first)
    message['Message-ID'] = '<'+key+'@wearyfather.org>'
    message.set_content(payload['text'])
    # Apple's documented endpoint: mandatory TLS before authenticating. The
    # username is the full primary @icloud.com address, not the custom alias.
    smtp = smtplib.SMTP('smtp.mail.me.com', 587, timeout=20)
    try:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context(cafile=requests.certs.where()))
        smtp.ehlo()
        smtp.login(mail['smtp_username'], password)
        mark_sending()
        try:
            refused = smtp.send_message(message, from_addr='library@wearyfather.org', to_addrs=[RECIPIENT])
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
        except (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused):
            # Explicit rejection is safe to retry. Clear the marker via a
            # distinct exception caught by the worker below.
            raise RejectedSMTP() from None
        except Exception:
            raise AmbiguousSMTP() from None
        return str(message['Message-ID'])
    finally:
        # A QUIT/disconnect failure after successful DATA must not undo success.
        try:
            smtp.close()
        except Exception:
            pass


class RejectedSMTP(Exception):
    """SMTP explicitly rejected this message; it was not accepted."""

def tick(config, now=None, sender=None):
    """Single process lock also prevents multiple workers from sending concurrently."""
    import fcntl
    now = now or datetime.now(timezone.utc)
    path = Path(config['database'])
    with path.with_suffix('.notifications.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        with closing(connect(path)) as db:
            with db:
                prepare(db, config['origin'].rstrip('/'), now)
            mail = config.get('email_notifications', {})
            if not mail.get('enabled'):
                return
            provider = mail.get('provider', 'resend')
            if provider not in {'resend', 'icloud'}:
                raise ValueError('Unknown email delivery provider')
            # Read credentials before claiming work. Missing setup leaves mail queued.
            token = Path(mail['password_file'] if provider == 'icloud' else mail['api_key_file']).read_text().strip()
            if not token or not mail.get('from') or any(c in mail['from'] for c in '\r\n'):
                raise ValueError('Email sender is not configured')
            if provider == 'icloud':
                from email.utils import parseaddr
                if parseaddr(mail['from'])[1].lower() != 'library@wearyfather.org' or not mail.get('smtp_username'):
                    raise ValueError('iCloud requires the library sender and primary iCloud username')
            # SMTP has no provider idempotency guarantee. Never automatically repeat
            # a send interrupted after the durable sending marker.
            with db:
                db.execute("UPDATE notification_outbox SET state='needs_review',error='Interrupted SMTP send; confirm receipt before resending' WHERE state='sending'")
            for row in db.execute("SELECT * FROM notification_outbox WHERE state='queued' AND (next_attempt IS NULL OR next_attempt<=?) ORDER BY rowid LIMIT 20", (now.isoformat(),)).fetchall():
                first = datetime.fromisoformat(row['first_attempt']) if row['first_attempt'] else now
                if provider == 'resend' and now-first >= timedelta(hours=23):
                    with db:
                        db.execute("UPDATE notification_outbox SET state='needs_review',error='Retry window expired; check provider before resending' WHERE id=?", (row['id'],))
                    continue
                payload = json.loads(row['payload']) if row['payload'] else dict(
                    sender=mail['from'], to=[RECIPIENT], subject=row['subject'], text=row['text'], provider=provider)
                if payload.get('provider', 'resend') != provider:
                    with db:
                        db.execute("UPDATE notification_outbox SET state='needs_review',error='Delivery provider changed; confirm prior delivery before resending' WHERE id=?", (row['id'],))
                    continue
                # Persist the exact payload before any network attempt, even across config changes.
                with db:
                    db.execute('UPDATE notification_outbox SET payload=?,first_attempt=?,attempts=attempts+1 WHERE id=?',
                               (json.dumps(payload), first.isoformat(), row['id']))
                key = hashlib.sha256(row['id'].encode()).hexdigest()
                try:
                    if sender:
                        provider_id = sender(payload, key)
                    elif provider == 'icloud':
                        def mark_sending():
                            with db:
                                db.execute("UPDATE notification_outbox SET state='sending' WHERE id=?", (row['id'],))
                        provider_id = send_icloud(mail, token, payload, key, first, mark_sending)
                    else:
                        import requests
                        response = requests.post('https://api.resend.com/emails', json={
                            'from':payload['sender'], 'to':payload['to'], 'subject':payload['subject'], 'text':payload['text']},
                            headers={'Authorization':'Bearer '+token, 'Idempotency-Key':key}, timeout=15)
                        response.raise_for_status()
                        provider_id = response.json()['id']
                    with db:
                        db.execute("UPDATE notification_outbox SET state='sent',provider_id=?,error=NULL WHERE id=?", (provider_id,row['id']))
                except RejectedSMTP:
                    delay = min(3600, 60 * 2**min(row['attempts'], 6))
                    with db:
                        db.execute("UPDATE notification_outbox SET state='queued',next_attempt=?,error='SMTP rejected message; retry scheduled' WHERE id=?",
                                   ((now+timedelta(seconds=delay)).isoformat(), row['id']))
                except AmbiguousSMTP:
                    with db:
                        db.execute("UPDATE notification_outbox SET state='needs_review',error='SMTP result uncertain; confirm receipt before resending' WHERE id=?", (row['id'],))
                except Exception:
                    # Never log credentials, response bodies, or private messages.
                    delay = min(3600, 60 * 2**min(row['attempts'], 6))
                    with db:
                        db.execute("UPDATE notification_outbox SET state=CASE WHEN state='sending' THEN 'needs_review' ELSE state END,next_attempt=?,error=? WHERE id=?",
                                   ((now+timedelta(seconds=delay)).isoformat(), 'Delivery failed; retry scheduled', row['id']))


def run(config):
    def loop():
        while True:
            try:
                tick(config)
            except Exception:
                import logging
                logging.getLogger(__name__).error('Email worker unavailable; check private configuration and notification queue')
            threading.Event().wait(30)
    threading.Thread(target=loop, name='owner-email', daemon=True).start()


def status_page(config):
    """Owner-only setup/delivery status; never expose credentials or message bodies."""
    import html
    mail = config.get('email_notifications', {})
    with closing(connect(config['database'])) as db:
        counts = dict(db.execute('SELECT state,count(*) FROM notification_outbox GROUP BY state').fetchall())
    enabled = bool(mail.get('enabled'))
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Email notifications</title><style>body{max-width:700px;margin:2rem auto;padding:1rem;font:18px/1.6 system-ui;color:#25372e}a{color:#245d49}</style>'
            '<a href="/owner/#settings">Back to Settings</a><h1>Email notifications</h1>'
            '<p>Delivery '+('enabled' if enabled else 'awaiting sender setup')+'. Recipient: '+RECIPIENT+'</p>'
            '<p>New requests and their messages: within about 30 seconds when delivery is enabled. '
            'Visitor summary: daily at 8 a.m. Central for the previous day, skipping quiet days. Your owner activity is excluded.</p>'
            '<p>Queued: '+str(counts.get('queued',0))+' · Accepted by email provider: '+str(counts.get('sent',0))+
            ' · Needs review: '+str(counts.get('needs_review',0))+'</p>'
            '<p>Sender: '+html.escape(mail.get('from','Not configured'))+'</p>'
            '<p>Delivery: '+html.escape(mail.get('provider','resend'))+'</p>'
            '<p>iCloud setup requires library@wearyfather.org, your primary iCloud Mail username, and a private app-specific password file. Resend remains an alternative with a verified domain and API key. '
            'Messages awaiting setup stay queued. Items needing review must be checked against provider logs before resending. '
            'Provider acceptance does not confirm inbox delivery. Check the receiving inbox and sender mailbox for delivery failures.</p></html>')
