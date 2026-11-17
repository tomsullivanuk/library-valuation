"""Read-only, evidence-backed presentation summaries for book research history.

Generated summaries are not task identity and never reopen decisions or write
prices. Authored summaries and all underlying evidence remain intact.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation


def contained(proposals, book):
    if not book.usable_market_estimate or not proposals:
        return False
    try:
        low, high = Decimal(book.estimated_value_precise_low), Decimal(book.estimated_value_precise_high)
        if not low.is_finite() or not high.is_finite() or not 0 < low <= high:
            return False
        return all(p['currency'] == book.estimated_value_currency and
                   low <= Decimal(p['low']) <= Decimal(p['high']) <= high for p in proposals)
    except (InvalidOperation, KeyError, TypeError):
        return False


def pending(task):
    if task.get('status') == 'complete' and task.get('note', '').strip():
        return False
    # Dismissal is not proof of the missing fact; show no request to redo it.
    return task.get('status', 'open') not in {'dismissed'}


def summary(task, book, checks=(), reviewed_on=''):
    category = task['category']
    known, uncertain, sources = [], [], []
    headline = 'Research findings retained; no saved value changed.'
    if book.usable_market_estimate:
        known.append('The saved estimate is '+book.resale_market_summary+'. It has not been changed by this presentation update.')
    else:
        known.append('The saved record does not contain a usable market estimate. No price has been invented or applied.')
    default_next = 'No action is required from you now, and no additional search is scheduled. Revisit the evidence before selling or if stronger comparisons become available.'
    if book.reviewed_estimate_id:
        headline = 'Your explicitly reviewed estimate is saved; earlier comparisons remain history.'
        known.append('Your estimate was explicitly reviewed on '+book.reviewed_estimate_date+'.')
        if book.reviewed_estimate_note: known.append('Your recorded basis: '+book.reviewed_estimate_note)
        uncertain.append('Listing asking prices and a saved estimate do not guarantee the price a buyer will pay.')
        reviewed_on = book.reviewed_estimate_date
        sources = [dict(label='Source retained with your reviewed estimate', url=u) for u in book.reviewed_estimate_sources]
        next_step = default_next+' A revision still requires explicit review and save.'
    elif category == 'Proposed estimates':
        proposals = task.get('proposals', [])
        known.append(f'The retained research supports {len(proposals)} conditional comparison range'+('s' if len(proposals)!=1 else '')+'. The exact ranges, binding, seller condition labels and sources are shown below.')
        known.append('These are per-copy seller asking-price comparisons, excluding shipping, not confirmed completed-sale prices. The date shown records the research review; this presentation update does not collect fresh prices or verify current availability.')
        uncertain.append('A seller’s description does not establish the binding or condition of your physical copy. Different scenarios are not interchangeable.')
        uncertain.append('No sale proceeds or buyer demand are established by these asking prices.')
        if contained(proposals, book):
            headline = 'New comparisons fit inside the existing saved estimate; no change is needed now.'
            known.append('Every proposed range in the same currency falls within the current saved range.')
            next_step = 'Keep the current estimate. No immediate action is needed; check your copy’s condition when preparing it for sale. No additional search is scheduled.'
        else:
            headline = 'Conditional comparison ranges are available; they have not been applied.'
            next_step = 'Keep these comparisons for a future valuation review. No immediate action is required from you, and no additional search is scheduled. Before applying a copy-specific range, confirm the relevant binding and condition; saving remains an explicit choice.'
        for p in proposals:
            for u in p.get('source_urls', []):
                sources.append(dict(label='Listing retained for '+p['binding']+' / '+p['grade']+' comparisons', url=u))
    elif category == 'Retain current estimate':
        headline = 'Current estimate retained provisionally; no action is needed now.'
        known.append('The previous review found no unresolved price-disagreement flag requiring an active investigation and did not justify a replacement range.')
        uncertain.append('Retention is not fresh independent confirmation that the saved price is accurate today.')
        next_step = default_next
    elif category == 'Resolved from records':
        headline = 'The recorded question has been answered; no action is needed for it.'
        known.append(task['action'])
        uncertain.append('Resolving this question does not establish other unrecorded copy details or its physical condition.')
        next_step = 'No action is required for this resolved question. Any separate physical checks remain in Action Items. Saved values are unchanged; no additional search is scheduled.'
    elif category == 'Awaiting physical check':
        headline = 'Research depends on an existing physical-book check, not another task for you.'
        known.append('The missing copy details are already covered by the linked physical check in Action Items.')
        uncertain.append('The applicable edition or binding cannot yet be selected confidently from the recorded alternatives.')
        next_step = 'Answer the existing linked question when convenient, record the finding and mark it Complete. The assistant can then reassess the evidence. No additional physical task is created, and no market search runs automatically.'
        if not any(pending(c) for c in checks):
            next_step = 'No action is required from you now. The assistant should reconcile the existing check’s answer or dismissal before requesting any further physical inspection. No new task or automatic market search is created.'
    else:
        headline = 'The available evidence does not yet support a replacement value range.'
        if task.get('reason'): uncertain.append(task['reason'])
        else: uncertain.append('The retained record does not establish enough comparable market evidence for a new range.')
        known.append('The existing evidence and notes are retained below; the review date is not a claim that every listing was newly collected that day.')
        next_step = 'No action is required from you now, and no additional search is scheduled. If a current valuation is needed, request one bounded search for matching listings and completed sales. If evidence remains insufficient, keep that finding and revisit before sale rather than inventing a range.'
        if task.get('next_step'): next_step += ' Research focus: '+task['next_step']
    active = [c for c in checks if pending(c)]
    if active and category != 'Awaiting physical check':
        known.append('A separate physical-book check is already recorded for this book; it is not a new request created by these findings.')
        next_step += ' The existing physical check, if still open, can be answered through Action Items.'
    if category == 'Awaiting physical check':
        known.extend('Existing question: '+c['action'] for c in active)
    seen=set();unique=[]
    for source in sources:
        if source['url'] not in seen: seen.add(source['url']);unique.append(source)
    # Use the retained review date, never today's date to imply fresh research.
    if reviewed_on:
        date.fromisoformat(reviewed_on)
    return dict(headline=headline,reviewed_on=reviewed_on,what_we_know=known,
                what_is_uncertain=uncertain,next_step=next_step,sources=unique)


def project(actions, books, reviewed_on=''):
    checks=defaultdict(list)
    for task in actions:
        if task['category']=='Book checks': checks[task['catalog_item_id']].append(task)
    result=[]
    for task in actions:
        value=dict(task);book=books.get(task['catalog_item_id'])
        if book and task['category']!='Book checks' and not task.get('history_summary'):
            value['history_summary']=summary(task,book,checks[task['catalog_item_id']],task.get('reviewed_on') or reviewed_on)
        result.append(value)
    return result
