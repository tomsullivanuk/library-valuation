"""Project an explicitly installed private research review into Action Items.

The manifest is a reviewed input, never inferred from arbitrary output files.
This module has no estimate, catalog or decision writer.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from valuation.estimate_reviews import book_identity

FILE_NAME='workspace_reviews/current.json'


def fingerprint(task):
    fields={k:v for k,v in task.items() if k not in {'fingerprint','audience','read_only'}}
    return hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()


def apply_review(data_dir, model, legacy):
    path=Path(data_dir)/FILE_NAME
    if not path.exists():
        tasks=[dict(t,audience='owner' if t['category']=='Book checks' else 'assistant') for t in legacy]
        return tasks,dict(loaded=False,message='The latest research review has not been installed.')
    doc=json.loads(path.read_text())
    if doc.get('schema_version')!=1 or not isinstance(doc.get('books'),dict) or not isinstance(doc.get('owner_checks'),list):
        raise ValueError('Unsupported workspace research review')
    books={b.catalog_item_id:b for b in model.books}
    active=set(model.completed_inventory.catalog_item_ids) if model.completed_inventory.completed else set(books)
    unresolved=set(model.completed_inventory.unresolved_observation_ids)
    ids=set();tasks=[];covered=set();changed=[]
    for row in doc['owner_checks']:
        cid=row['catalog_item_id'];oid=row.get('inventory_observation_id','')
        if cid and cid not in active:continue
        if not cid and oid not in unresolved:continue
        tid=row['id']
        if tid in ids or not row['question'].strip():raise ValueError('Duplicate or empty reviewed owner check')
        ids.add(tid);covered.add(tid)
        task=dict(id=tid,title=row['title'],action=row['question'],category='Book checks',
                  location=row['location'],evidence=row.get('evidence',''),catalog_item_id=cid,
                  route='book/'+cid if cid else 'observation/'+oid,audience='owner')
        if cid and doc['books'].get(cid,{}).get('book_identity')!=book_identity(books[cid]):
            task['reason']='Book metadata changed since this checklist review. Confirm the recorded question still applies before answering.'
        task['fingerprint']=fingerprint(task);tasks.append(task)
    resolved={r['id']:r for r in doc.get('resolved_checks',[])}
    for tid,row in resolved.items():
        cid=row['catalog_item_id']
        if cid not in active:continue
        if tid in ids:raise ValueError('Resolved and pending checks overlap')
        if doc['books'].get(cid,{}).get('book_identity')!=book_identity(books[cid]):
            continue  # Changed identities cannot silently inherit a photo resolution.
        covered.add(tid);ids.add(tid)
        task=dict(id=tid,title=books[cid].title,action=row['finding'],category='Resolved from records',
                  location=books[cid].location_summary,evidence=row.get('evidence',''),catalog_item_id=cid,
                  route='book/'+cid,audience='reference',read_only=True,default_status='complete')
        task['fingerprint']=fingerprint(task);tasks.append(task)
    # Keep genuinely new canonical questions, but suppress explicitly superseded ones.
    superseded=set(doc.get('superseded_check_ids',[]))
    for t in legacy:
        if t['category']=='Book checks' and t['id'] not in covered and (t['id'] not in superseded or t['id'] in resolved):
            tasks.append(dict(t,audience='owner'));ids.add(t['id'])
    for cid in sorted(active):
        book=books[cid];review=doc['books'].get(cid)
        if book.reviewed_estimate_id:
            continue  # Saved review tasks remain available through the service's history.
        applicable=bool(review and review.get('book_identity')==book_identity(book))
        if not applicable:changed.append(cid)
        proposals=review.get('proposals',[]) if applicable and not book.reviewed_estimate_id else []
        task=dict(id='estimate-research:'+cid,title=book.title,location=book.location_summary,
                  catalog_item_id=cid,book_identity=book_identity(book),route='book/'+cid,audience='assistant')
        if proposals:
            for p in proposals:
                if p.get('publishable') is not False or not p.get('currency') or not p.get('binding') or not p.get('grade'):
                    raise ValueError('Invalid conditional proposal in workspace review')
                from decimal import Decimal
                low,high=Decimal(p['low']),Decimal(p['high'])
                if not low.is_finite() or not high.is_finite() or low<=0 or high<low:raise ValueError('Invalid proposed range')
                for url in p.get('source_urls',[]):
                    u=urlsplit(url)
                    if u.scheme not in {'https','http'} or not u.hostname or u.username or u.password:raise ValueError('Unsafe research source URL')
            task.update(category='Proposed estimates',action='Research has produced conditional value ranges for later review.',
                        reason='These are per-copy asking-price ranges for the stated binding and seller condition. Your copy has not been graded. Saved values are unchanged.',
                        proposals=proposals,reviewed_on=doc['reviewed_on'],
                        next_step='Confirm the applicable copy details when handling the book. Individual estimate review is optional; no range is applied automatically.')
        else:
            task.update(category='Estimate research',action='Further market research is tracked with the assistant.',
                        reason='The reviewed evidence does not yet support a replacement range.' if applicable else 'This book is new or its identity changed since the research review; its evidence needs reassessment.',
                        next_step=review.get('research_next_step','Check edition-matched offers, binding, seller condition and source-price differences.') if applicable else 'Reconcile the current edition with the research evidence before proposing a range.')
            if book.reviewed_estimate_id:
                task.update(reason='The saved manually reviewed estimate is protected. Research proposals have not replaced it.',next_step='Reassess only if new evidence warrants revisiting the saved manual review.')
        task['fingerprint']=fingerprint(task);tasks.append(task)
    return tasks,dict(loaded=True,review_id=doc['review_id'],reviewed_on=doc['reviewed_on'],
                      changed_or_new_books=len(changed),message='Research outcomes are installed. Saved book values are unchanged.')
