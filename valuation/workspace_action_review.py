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


def estimate_basis(book):
    """Invalidate a retained-baseline classification if its saved range changes."""
    fields = ('estimated_value_precise_low', 'estimated_value_precise_high',
              'estimated_value_currency', 'usable_market_estimate')
    return {key: getattr(book, key) for key in fields}


def classify_remaining(*, has_proposals, awaiting_physical, unresolved_price_flags,
                       usable_estimate):
    """Route reviewed outcomes; absence of a replacement is not a research task."""
    if has_proposals:
        return 'proposed'
    if awaiting_physical:
        return 'awaiting_physical'
    if unresolved_price_flags or not usable_estimate:
        return 'further_evidence'
    return 'retain_current'


def apply_review(data_dir, model, legacy, decisions=None):
    decisions = decisions or {}
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
            classification=review.get('classification','further_evidence') if applicable else 'further_evidence'
            if classification not in {'retain_current','awaiting_physical','further_evidence'}:
                raise ValueError('Invalid no-proposal research classification')
            if classification=='retain_current' and (not book.usable_market_estimate or review.get('estimate_basis')!=estimate_basis(book)):
                classification='further_evidence'
            owner_tasks=[t for t in tasks if t['category']=='Book checks' and t['catalog_item_id']==cid]
            pending_tasks=[t for t in owner_tasks if not (decisions.get(t['id'],{}).get('fingerprint')==t['fingerprint'] and decisions[t['id']].get('status')=='complete' and decisions[t['id']].get('note','').strip())]
            if classification=='awaiting_physical' and (not applicable or not pending_tasks):
                classification='further_evidence'
            if classification=='retain_current':
                task.update(category='Retain current estimate',audience='reference',read_only=True,default_status='complete',
                            action='Retain the current saved estimate provisionally; no replacement is justified by this review.',
                            reason='The saved estimate is usable under the existing catalog rules, and this review has no unresolved price-disagreement flag for this book. This is not a fresh independent verification of its value.',
                            next_step='No active research task. Revisit when stronger edition-matched evidence becomes available or before a sale.',
                            reviewed_on=doc['reviewed_on'])
            elif classification=='awaiting_physical':
                task.update(category='Awaiting physical check',audience='reference',read_only=True,
                            action='Estimate research is waiting for the existing physical-book check.',
                            reason='The copy details needed to select comparable listings remain unresolved. This is not a second owner task.',
                            next_step='Answer the linked check under Needs your input; then the assistant can reassess the market evidence.',
                            blocking_check_ids=[t['id'] for t in pending_tasks])
            else:
                task.update(category='Estimate research',action='Existing records and listings have been reviewed; further market evidence is needed.' if applicable and review.get('research_outcome') else 'Further market research is tracked with the assistant.',
                        reason=review.get('research_reason','The reviewed evidence does not yet support a replacement range.') if applicable else 'This book is new or its identity changed since the research review; its evidence needs reassessment.',
                        next_step=review.get('research_next_step','Check edition-matched offers, binding, seller condition and source-price differences.') if applicable else 'Reconcile the current edition with the research evidence before proposing a range.')
        if applicable and review.get('research_evidence'):task['evidence']=review['research_evidence']
        task['fingerprint']=fingerprint(task);tasks.append(task)
    return tasks,dict(loaded=True,review_id=doc['review_id'],reviewed_on=doc['reviewed_on'],
                      changed_or_new_books=len(changed),message='Research outcomes are installed. Saved book values are unchanged.')
