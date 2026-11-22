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
    if 'recipient' not in {r[1] for r in db.execute('PRAGMA table_info(notification_outbox)')}:
        db.execute('ALTER TABLE notification_outbox ADD COLUMN recipient TEXT')
    for column in ('created','accepted_at'):
        if column not in {r[1] for r in db.execute('PRAGMA table_info(notification_outbox)')}:
            db.execute('ALTER TABLE notification_outbox ADD COLUMN '+column+' TEXT')
    with db:
        db.execute('INSERT OR IGNORE INTO notification_meta VALUES(?,?)', ('started', now.isoformat()))
        db.execute('INSERT OR IGNORE INTO notification_meta VALUES(?,?)', ('digest_day', now.astimezone(ZONE).date().isoformat()))
        has_events = db.execute("SELECT 1 FROM sqlite_master WHERE name='request_events' AND type='table'").fetchone()
        last = db.execute('SELECT coalesce(max(id),0) FROM request_events').fetchone()[0] if has_events else 0
        db.execute('INSERT OR IGNORE INTO notification_meta VALUES(?,?)', ('book_decision_cursor', str(last)))


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


def enqueue(db, key, subject, text, recipient=None):
    from valuation.family_users import email
    recipient = email(recipient or RECIPIENT)
    db.execute('INSERT OR IGNORE INTO notification_outbox(id,subject,text,recipient,created) VALUES(?,?,?,?,?)', (key, subject, text, recipient, datetime.now(timezone.utc).isoformat()))



def owner_book_details(config, db):
    """Owner-only enrichment; never add private fields to recipient snapshots."""
    if not config or not config.get('owner_data_dir'):
        return {}
    from valuation.workspace_service import load_model
    from valuation.family_owner import live_facts
    model = load_model(config['owner_data_dir'], config['owner_output_dir'], family_overlay=False)
    facts = live_facts(model, config['owner_data_dir'])
    books = {b.catalog_item_id:b for b in model.books}
    receipt = Path(config['owner_data_dir'])/'inventory_followup_reviews.json'
    reviews = json.loads(receipt.read_text()).get('reviews', []) if receipt.exists() else []
    bindings = {r['inventory_observation_id']:r['confirmed_binding'] for r in reviews
                if r.get('confirmed_binding') in {'hardcover','paperback'}}
    holdings = {h.holding_id:h for h in model.holdings}
    has_decisions = db.execute("SELECT 1 FROM sqlite_master WHERE name='request_decisions' AND type='table'").fetchone()
    assignments = {r['slot']:r['state'] for r in db.execute(
        "SELECT slot,state FROM request_decisions WHERE state IN ('approved','collected','transferred')")} if has_decisions else {}
    for f in facts.values():
        b = books[f['catalog_item_id']]
        f.update(publisher=b.publisher, year=b.publication_year)
        confirmed = []
        for copy in f['copies']:
            holding = holdings[copy['holding_id']]
            binding = bindings.get(holding.latest_inventory_observation_id)
            if binding:
                label = binding.capitalize()+' (location '+(copy['location'] or 'not recorded')+')'
                if label not in confirmed:confirmed.append(label)
        f['binding'] = '; '.join(confirmed)
        states = [assignments.get(c['id']) for c in f['copies']]
        f['availability'] = (str(states.count(None))+' available; '+str(states.count('approved'))+
                             ' reserved; '+str(sum(s in {'collected','transferred'} for s in states))+' transferred')
    return facts


def request_email(row, origin, details):
    data = json.loads(row['payload'])
    sections = []
    for book in data['books']:
        f = details.get(book.get('reference'), {})
        lines = [book['title']]
        author = f.get('author') or book.get('author')
        if author:lines.append('Author: '+author)
        edition = ' · '.join(str(v) for v in (f.get('publisher') or book.get('publisher'),
                                               f.get('year') or book.get('year')) if v)
        if edition:lines.append('Publication: '+edition)
        if f.get('binding'):lines.append('Confirmed binding: '+f['binding'])
        locations = list(dict.fromkeys(c['location'] for c in f.get('copies',[]) if c.get('location')))
        if locations:lines.append('Storage location(s): '+', '.join(locations))
        if f.get('availability'):lines.append('Availability when alert prepared: '+f['availability'])
        value = f.get('value', '')
        if value and value not in {'No usable estimate','No reliable estimate','Not researched','Unavailable'}:
            lines.append('Estimated resale value: '+value)
        sections.append('\n'.join(lines))
    return (f"From: {row['email']}\nSubmitted: {row['created']}\nBooks requested: {len(data['books'])}\n\n"+
            '\n\n'.join(sections)+'\n\nRequester’s message:\n'+(data.get('message') or '(No message)')+
            '\n\nREVIEW REQUEST\n'+origin+'/owner/#requests'+
            ('\n\nAvailability can change; confirm before approving.' if details else
             '\n\nLive inventory details unavailable; check Requests for current availability.'))

def prepare_book_decisions(db, origin):
    """Notify future committed owner decisions, grouping each recipient's batch."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='request_events' AND type='table'").fetchone():return
    cursor=int(db.execute("SELECT value FROM notification_meta WHERE key='book_decision_cursor'").fetchone()[0])
    events=db.execute('SELECT * FROM request_events WHERE id>? ORDER BY id',(cursor,)).fetchall()
    if not events:return
    latest={}
    for event in events:latest[(event['submission'],event['reference'])]=event
    groups={}
    for (sid,ref),event in latest.items():
        decision=json.loads(event['payload'])
        after=decision['after']['state']
        before=decision.get('before',{}).get('state')
        if after not in {'approved','declined'} or before is None or before==after:continue
        # Discard decisions superseded before preparing this notification.
        current=db.execute('SELECT state FROM request_decisions WHERE submission=? AND reference=?',(sid,ref)).fetchone()
        if not current or current['state']!=after:continue
        submission=db.execute('SELECT email,payload FROM submissions WHERE id=?',(sid,)).fetchone()
        if not submission:continue
        book=next((b for b in json.loads(submission['payload'])['books'] if b['reference']==ref),None)
        if not book:continue
        label=book['title']+(' — '+book['author'] if book.get('author') else '')
        groups.setdefault((submission['email'],after),[]).append(dict(id=event['id'],label=label,message=decision.get('message','')))
    for (recipient,state),items in groups.items():
        lines=['Your book request'+('s have' if len(items)>1 else ' has')+' been '+state+'.',
               '\n'+'\n'.join('• '+item['label'] for item in items)]
        notes={}
        for item in items:
            if item['message'].strip():notes.setdefault(item['message'],[]).append(item['label'])
        if len(notes)==1:lines.append('Message from Thomas:\n'+next(iter(notes)))
        elif notes:
            lines.append('Messages from Thomas:\n\n'+'\n\n'.join('\n'.join(labels)+'\n'+note for note,labels in notes.items()))
        if state=='approved':lines.append('Thomas will coordinate delivery directly with you.')
        lines.append('View your requests:\n'+origin+'/browse')
        key='book-decision/'+hashlib.sha256(','.join(str(i['id']) for i in items).encode()).hexdigest()
        enqueue(db,key,'Library book request'+('s' if len(items)>1 else '')+' '+state,'\n\n'.join(lines),recipient=recipient)
    db.execute("UPDATE notification_meta SET value=? WHERE key='book_decision_cursor'",(str(events[-1]['id']),))


def prepare(db, origin, now, config=None):
    """Reconcile committed submissions; restart-safe and no historical request blast."""
    start = db.execute("SELECT value FROM notification_meta WHERE key='started'").fetchone()[0]
    rows = db.execute("SELECT * FROM submissions WHERE created>=? AND NOT EXISTS (SELECT 1 FROM notification_outbox WHERE id='request/'||submissions.id) ORDER BY created", (start,)).fetchall()
    details = {}
    if rows:
        try:
            details = owner_book_details(config, db)
        except Exception:
            # Alerts must still arrive if inventory enrichment is temporarily unavailable.
            pass
    for row in rows:
        enqueue(db, 'request/'+row['id'], 'Library: new book request', request_email(row, origin, details))
    prepare_book_decisions(db, origin)
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
    message['To'] = ', '.join(payload['to'])
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
            refused = smtp.send_message(message, from_addr='library@wearyfather.org', to_addrs=payload['to'])
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
                prepare(db, config['origin'].rstrip('/'), now, config)
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
                    sender=mail['from'], to=[row['recipient'] or RECIPIENT], subject=row['subject'], text=row['text'], provider=provider)
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
                        db.execute("UPDATE notification_outbox SET state='sent',provider_id=?,accepted_at=?,error=NULL WHERE id=?", (provider_id,now.isoformat(),row['id']))
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
            '<a href="/owner/#settings">Back to Settings</a><h1>Email notifications</h1><p><a href="/owner/email-history">Email History — messages and CSV export</a></p>'
            '<p>Delivery '+('enabled' if enabled else 'awaiting sender setup')+'. Recipient: '+RECIPIENT+'</p>'
            '<p>New requests and their messages: within about 30 seconds when delivery is enabled. '
            'Visitor summary: daily at 8 a.m. Central for the previous day, skipping quiet days. Your owner activity is excluded.</p>'
            '<p>Saved book approval/decline decisions also email the requester. Registration acknowledgments and access decisions email the applicant.</p>'
            '<p>Queued: '+str(counts.get('queued',0))+' · Accepted by email provider: '+str(counts.get('sent',0))+
            ' · Needs review: '+str(counts.get('needs_review',0))+'</p>'
            '<p>Sender: '+html.escape(mail.get('from','Not configured'))+'</p>'
            '<p>Delivery: '+html.escape(mail.get('provider','resend'))+'</p>'
            '<p>iCloud setup requires library@wearyfather.org, your primary iCloud Mail username, and a private app-specific password file. Resend remains an alternative with a verified domain and API key. '
            'Messages awaiting setup stay queued. Items needing review must be checked against provider logs before resending. '
            'Provider acceptance does not confirm inbox delivery. Check the receiving inbox and sender mailbox for delivery failures.</p></html>')
