"""Owner workflow shared by the existing steward workspace and family service.

The request database is the reservation/collection event ledger. Source inventory
and purchase evidence remain intact; current availability applies this ledger.
"""
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from valuation import family_requests as requests


def settings():
    path=Path.home()/'library-access-pilot/state/config.json'
    return json.loads(path.read_text()) if path.exists() else None


def schema(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS request_decisions(
 submission TEXT NOT NULL,reference TEXT NOT NULL,state TEXT NOT NULL,slot TEXT,
 version INTEGER NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(submission,reference));
CREATE UNIQUE INDEX IF NOT EXISTS assigned_copy ON request_decisions(slot) WHERE state IN ('approved','collected');
CREATE TABLE IF NOT EXISTS request_events(id INTEGER PRIMARY KEY,submission TEXT,reference TEXT,actor TEXT,created TEXT,payload TEXT);''')


def decision(db,submission,reference):
    r=db.execute('SELECT * FROM request_decisions WHERE submission=? AND reference=?',(submission,reference)).fetchone()
    return dict(r) if r else dict(submission=submission,reference=reference,state='pending',slot=None,version=0,updated='')


def live_facts(model,data_dir):
    from valuation import estimate_reviews
    from valuation.steward_presentation import project_reviewed_estimate
    reviews=estimate_reviews.current_reviews(data_dir,model.books)
    holdings={h.holding_id:h for h in model.holdings if h.holding_id in model.completed_inventory.holding_ids and h.inventory_status=='verified_present'}
    result={}
    for original in model.books:
        ref=hashlib.sha256(('family-v1:'+original.catalog_item_id).encode()).hexdigest()[:20]
        b=project_reviewed_estimate(original,reviews[original.catalog_item_id]) if original.catalog_item_id in reviews else original
        slots=[]
        for h in holdings.values():
            if h.catalog_item_id!=b.catalog_item_id:continue
            location=h.source_collection_label
            if location.lower().startswith('box '):location=location[4:]
            for unit in range(1,int(h.copies)+1):
                slots.append(dict(id=h.holding_id+':'+str(unit),holding_id=h.holding_id,unit=unit,location=location,
                    label=f'{location or "Location not recorded"} · copy {unit} of {h.copies}',verified_at=h.last_verified_at))
        result[ref]=dict(catalog_item_id=b.catalog_item_id,title=b.title,author=b.author,
            value=b.estimated_value_display or b.resale_market_summary or 'No usable estimate',
            value_is_estimate=True,location=b.location_summary,copies=slots)
    return result


def inbox(db,facts):
    schema(db);rows=requests.submissions(db);people={}
    for row in rows:
        for b in row['payload']['books']:
            d=decision(db,row['id'],b['reference'])
            if d['state'] not in ('declined','collected'):people.setdefault(b['reference'],set()).add(row['email'])
    assigned={r['slot']:dict(r) for r in db.execute("SELECT * FROM request_decisions WHERE state IN ('approved','collected')")}
    for row in rows:
        details=[]
        for b in row['payload']['books']:
            ref=b['reference'];f=facts.get(ref,dict(title=b['title'],author=b['author'],value='Unavailable',location='',copies=[]))
            d=decision(db,row['id'],ref)
            copies=[dict(c,assignment=assigned.get(c['id'])) for c in f['copies']]
            details.append(dict(reference=ref,**{k:v for k,v in f.items() if k!='copies'},copies=copies,decision=d,
                other_requesters=sorted(people.get(ref,set())-{row['email']})))
        row['items']=details
    return rows


def update(db,actor,body,facts):
    schema(db)
    submission,ref,state,version=body['submission'],body['reference'],body['state'],body['version']
    if state not in ('pending','approved','declined','collected') or type(version) is not int:raise ValueError('Invalid decision')
    with db:
        db.execute('BEGIN IMMEDIATE')
        source=db.execute('SELECT payload FROM submissions WHERE id=?',(submission,)).fetchone()
        if not source or ref not in {b['reference'] for b in json.loads(source['payload'])['books']}:raise ValueError('Unknown request item')
        old=decision(db,submission,ref)
        if version!=old['version']:raise requests.Conflict('This request changed. Refresh before deciding.')
        if old['state']=='collected':raise requests.Conflict('Collection is recorded permanently. Contact Tom to reconcile a mistaken collection.')
        slot=body.get('slot') if state=='approved' else old['slot'] if state=='collected' else None
        if state in ('approved','collected'):
            if slot not in {c['id'] for c in facts.get(ref,{}).get('copies',[])}:raise requests.Conflict('This copy is no longer eligible. Refresh and check the inventory.')
            if state=='collected' and old['state']!='approved':raise ValueError('Approve and assign a copy before marking it collected')
            used=db.execute("SELECT submission,reference FROM request_decisions WHERE slot=? AND state IN ('approved','collected')",(slot,)).fetchone()
            if used and (used['submission'],used['reference'])!=(submission,ref):raise requests.Conflict('That physical copy is already assigned or collected.')
        stamp=datetime.now(timezone.utc).isoformat()
        db.execute('INSERT OR REPLACE INTO request_decisions VALUES(?,?,?,?,?,?)',(submission,ref,state,slot,version+1,stamp))
        db.execute('INSERT INTO request_events(submission,reference,actor,created,payload) VALUES(?,?,?,?,?)',(submission,ref,actor,stamp,json.dumps(dict(before=old,after=dict(state=state,slot=slot)))))
    return decision(db,submission,ref)


def available(db,records,facts):
    schema(db)
    taken={r['slot'] for r in db.execute("SELECT slot FROM request_decisions WHERE state IN ('approved','collected')")}
    return {ref:book for ref,book in records.items() if ref in facts and any(c['id'] not in taken for c in facts[ref]['copies'])}


def collected_overlay(model,config):
    """Current steward display reflects collections without erasing source evidence."""
    if not config or not Path(config['database']).exists():return model
    with closing(requests.connect(config['database'])) as db:
        schema(db);slots=[r['slot'] for r in db.execute("SELECT slot FROM request_decisions WHERE state='collected'")]
    counts={}
    for slot in slots:
        holding=slot.rsplit(':',1)[0];counts[holding]=counts.get(holding,0)+1
    holdings=tuple(replace(h,copies=str(max(0,int(h.copies)-counts.get(h.holding_id,0)))) for h in model.holdings)
    remaining={h.catalog_item_id for h in holdings if h.holding_id in model.completed_inventory.holding_ids and int(h.copies)>0}
    books=tuple(replace(b,copy_count=sum(int(h.copies) for h in holdings if h.catalog_item_id==b.catalog_item_id and h.holding_id in model.completed_inventory.holding_ids)) for b in model.books)
    effective=sum(min(int(h.copies),counts.get(h.holding_id,0)) for h in model.holdings if h.holding_id in model.completed_inventory.holding_ids)
    scope=replace(model.completed_inventory,source_copies=max(0,model.completed_inventory.source_copies-effective),catalog_item_ids=tuple(x for x in model.completed_inventory.catalog_item_ids if x in remaining),holding_ids=tuple(h.holding_id for h in holdings if h.holding_id in model.completed_inventory.holding_ids and int(h.copies)>0))
    return replace(model,holdings=holdings,books=books,completed_inventory=scope)
