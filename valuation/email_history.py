"""Read-only owner email history and spreadsheet-safe CSV export."""
import csv
import html
import io
import json
from contextlib import closing
from datetime import date, datetime
from urllib.parse import urlencode

from valuation.family_notifications import RECIPIENT, ZONE
from valuation.family_requests import connect

STATES={'queued':'Queued','sending':'Sending','sent':'Accepted for delivery','needs_review':'Needs attention','cancelled':'Cancelled'}
TYPES={'registration':'Registration','book-decision':'Book request decision','request':'Request / message alert','visitors':'Daily visitor summary','other':'Other'}
PATH='/owner/email-history'


def category(key):
    prefix=key.split('/')[0]
    return prefix if prefix in TYPES else 'other'


def records(config, params):
    """Return only displayable fields, using immutable sent payloads when available."""
    recipient=params.get('recipient','').strip().lower()[:254]
    status=params.get('status','');kind=params.get('type','')
    if status and status not in STATES:raise ValueError('Choose a valid email status')
    if kind and kind not in TYPES:raise ValueError('Choose a valid email type')
    start=date.fromisoformat(params['from']) if params.get('from') else None
    end=date.fromisoformat(params['to']) if params.get('to') else None
    if start and end and start>end:raise ValueError('The end date must follow the start date')
    result=[]
    with closing(connect(config['database'])) as db:
        for raw in db.execute('SELECT * FROM notification_outbox ORDER BY rowid DESC'):
            r=dict(raw);payload=json.loads(r['payload']) if r['payload'] else {}
            to=', '.join(payload.get('to') or [r['recipient'] or RECIPIENT])
            if recipient not in to.lower() or (status and status!=r['state']) or (kind and kind!=category(r['id'])):continue
            stamp=r.get('accepted_at') or r['first_attempt'] or r.get('created')
            when=datetime.fromisoformat(stamp).astimezone(ZONE) if stamp else None
            if (start or end) and (not when or (start and when.date()<start) or (end and when.date()>end)):continue
            basis='Accepted' if r.get('accepted_at') else 'First attempt' if r['first_attempt'] else 'Queued' if r.get('created') else 'Not recorded'
            result.append(dict(time=when.strftime('%Y-%m-%d %H:%M:%S %Z') if when else 'Not recorded',basis=basis,recipient=to,
                subject=payload.get('subject',r['subject']) or '',type=TYPES[category(r['id'])],status=STATES.get(r['state'],r['state']),
                text=payload.get('text',r['text']) or '',sender=payload.get('sender') or config.get('email_notifications',{}).get('from','Not configured'),
                error=r['error'] or '',attempts=r['attempts']))
    return result


def csv_export(rows):
    output=io.StringIO(newline='');writer=csv.writer(output)
    writer.writerow(['Date / time (Central)','Time represents','Recipient','Subject','Email type','Status','Message','Sender','Delivery note','Attempts'])
    def safe(value):
        text=str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
    for r in rows:writer.writerow([safe(r[k]) for k in ('time','basis','recipient','subject','type','status','text','sender','error','attempts')])
    return ('\ufeff'+output.getvalue()).encode('utf-8')


def page(config,params):
    rows=records(config,params);esc=lambda v:html.escape(str(v),quote=True)
    try:number=max(1,int(params.get('page','1')))
    except ValueError:number=1
    size=100;number=min(number,max(1,(len(rows)+size-1)//size));visible=rows[(number-1)*size:number*size]
    def options(values,current):return '<option value="">All</option>'+''.join('<option value="'+esc(k)+'"'+(' selected' if k==current else '')+'>'+esc(v)+'</option>' for k,v in values.items())
    filters={k:params.get(k,'') for k in ('recipient','status','type','from','to')}
    controls='<form method="get"><label>Recipient<input name="recipient" type="search" maxlength="254" value="'+esc(filters['recipient'])+'" placeholder="Email address"></label><label>Status<select name="status">'+options(STATES,filters['status'])+'</select></label><label>Email type<select name="type">'+options(TYPES,filters['type'])+'</select></label>'
    for k,title in [('from','From date'),('to','Through date')]:controls+='<label>'+title+'<input type="date" name="'+k+'" value="'+esc(filters[k])+'"></label>'
    controls+='<button>Apply filters</button><a href="'+PATH+'">Clear filters</a></form>'
    cards=''.join('<tr><td>'+esc(r['time'])+'<small>'+esc(r['basis'])+'</small></td><td>'+esc(r['recipient'])+'</td><td>'+esc(r['subject'])+'<small>'+esc(r['type'])+'</small><details><summary>View message</summary><p>From: '+esc(r['sender'])+'</p><pre>'+esc(r['text'])+'</pre>'+('<p>'+esc(r['error'])+'</p>' if r['error'] else '')+'</details></td><td>'+esc(r['status'])+'</td></tr>' for r in visible)
    links=[]
    for n,label in [(number-1,'Previous'),(number+1,'Next')]:
        if 1<=n<=max(1,(len(rows)+size-1)//size):links.append('<a href="'+PATH+'?'+esc(urlencode(dict(filters,page=n)))+'">'+label+'</a>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Email History — Library</title><style>body{max-width:1200px;margin:2rem auto;padding:1rem;font:17px/1.5 system-ui;color:#25372e;background:#faf9f5}a,h1{color:#245d49}form{display:flex;gap:1rem;align-items:end;flex-wrap:wrap;margin:1rem 0}label{display:grid;gap:.3rem}input,select,button{font:inherit;padding:.6rem;max-width:100%;box-sizing:border-box}button{background:#245d49;color:white;border:0;border-radius:6px}table{width:100%;border-collapse:collapse;background:white}td,th{text-align:left;vertical-align:top;padding:.8rem;border-bottom:1px solid #d4ddd6}td{overflow-wrap:anywhere}small{display:block;color:#606c65}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}summary{cursor:pointer;color:#245d49;margin-top:.5rem}.scroll{overflow-x:auto}nav{display:flex;gap:1rem}img{width:140px;height:auto} @media(max-width:600px){body{margin:.5rem auto}table{min-width:650px}input{width:100%}}</style><header><img src="/register/emblem.png" width="1536" height="1024" alt="Thomas D. Sullivan Library &amp; Archive"><p><a href="/owner/#settings">Back to Settings</a> · <a href="/owner/email-notifications">Delivery setup and status</a></p></header><h1>Email History</h1><p>Application emails only. Cloudflare login codes and manually sent emails are not included. Accepted for delivery means the email provider accepted the message; inbox or Junk delivery is not confirmed.</p><p>Times are Central. Older records show the first sending attempt when the exact acceptance time was not recorded. Older unsent records may have no recorded time.</p>'+controls+'<p>'+str(len(rows))+' matching emails · <a download="library-email-history.csv" href="'+PATH+'.csv?'+esc(urlencode(filters))+'">Export matching emails as CSV</a></p><div class="scroll"><table><thead><tr><th>Date / time</th><th>Recipient</th><th>Subject / type / message</th><th>Status</th></tr></thead><tbody>'+ (cards or '<tr><td colspan="4">No emails match these filters.</td></tr>')+'</tbody></table></div><nav><p>Page '+str(number)+'</p>'+''.join(links)+'</nav></html>'
