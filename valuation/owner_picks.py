"""Owner-created reservations and non-reserving storage review lists."""
import json
import uuid
from datetime import datetime, timezone
from valuation import family_owner, family_requests


def create(db, actor, body, facts, allowed):
    purpose = body.get('purpose')
    email = actor if purpose in ('self', 'review') else body.get('email')
    items, key = body.get('items'), body.get('key')
    message = body.get('message', '')
    if purpose not in ('self', 'other', 'review') or email not in allowed:
        raise ValueError('Choose yourself, an active user, or review')
    if not isinstance(items, list) or not 1 <= len(items) <= 3000 or not isinstance(key, str) or not 1 <= len(key) <= 80:
        raise ValueError('Select books before saving')
    if not isinstance(message, str) or len(message) > 2000:
        raise ValueError('Message must be at most 2000 characters')
    by_id = {f['catalog_item_id']: (ref, f) for ref, f in facts.items()}
    selected = []
    for item in items:
        if not isinstance(item, dict) or item.get('catalog_item_id') not in by_id:
            raise ValueError('A book is no longer in the catalog')
        ref, fact = by_id[item['catalog_item_id']]
        slot = item.get('slot')
        if not fact['copies'] or slot not in {c['id'] for c in fact['copies']}:
            raise ValueError('Choose an inventory copy for each book')
        selected.append((ref, fact, slot))
    if len({slot for _, _, slot in selected}) != len(selected):
        raise ValueError('Select each physical copy only once')
    fingerprint = json.dumps(dict(purpose=purpose, email=email, items=items, message=message), sort_keys=True)
    family_owner.schema(db)
    with db:
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT id,payload FROM submissions WHERE email=? AND key=?', (email, 'owner-pick:'+key)).fetchone()
        if prior:
            if json.loads(prior['payload']).get('owner_pick_fingerprint') != fingerprint:
                raise family_requests.Conflict('This saved selection changed. Reload before saving another list.')
            return dict(id=prior['id'], count=len(selected))
        used = {r['slot'] for r in db.execute("SELECT slot FROM request_decisions WHERE state IN ('approved','collected','transferred')")}
        if any(slot in used for _, _, slot in selected):
            raise family_requests.Conflict('A selected copy is reserved or transferred. Refresh the picking controls.')
        stamp = datetime.now(timezone.utc).isoformat()
        # Each submission can contain a title once; distribute repeated titles
        # across layers while keeping all copies in one atomic operation.
        layers = []
        for selection in selected:
            ref = selection[0]
            target = next((layer for layer in layers if all(x[0] != ref for x in layer)), None)
            if target is None:
                target = []; layers.append(target)
            target.append(selection)
        first_id = None
        for layer_number, layer in enumerate(layers):
            sid = str(uuid.uuid4())
            if first_id is None: first_id = sid
            payload = dict(books=[dict(reference=ref, title=f['title'], author=f['author']) for ref, f, _ in layer], message=message,
                           owner_pick=purpose, owner_pick_slots={ref:slot for ref, _, slot in layer}, owner_pick_fingerprint=fingerprint,
                           owner_pick_count=len(selected))
            layer_key = 'owner-pick:'+key + (':'+str(layer_number) if layer_number else '')
            db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)', (sid, email, layer_key, stamp, json.dumps(payload)))
            for ref, _, slot in layer:
                state = 'pending' if purpose == 'review' else 'approved'
                assigned = None if purpose == 'review' else slot
                db.execute('INSERT INTO request_decisions VALUES(?,?,?,?,?,?)', (sid, ref, state, assigned, 1, stamp))
                db.execute('INSERT INTO request_events(submission,reference,actor,created,payload) VALUES(?,?,?,?,?)',
                           (sid, ref, actor, stamp, json.dumps(dict(after=dict(state=state, slot=assigned), message=message, owner_pick=purpose))))
    return dict(id=first_id, count=len(selected))
