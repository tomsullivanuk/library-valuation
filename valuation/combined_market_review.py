"""Private, network-free proposals from retained eBay/AbeBooks comparisons.

Never publishes estimates or assigns the condition of an owned copy. AbeBooks
query ISBNs are deliberately never treated as returned listing ISBNs.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import csv
import hashlib
import json
from pathlib import Path

from valuation.offline_valuation_review import isbn, listing_key, number, review_book, timestamp

POLICY = dict(max_age_days=30, minimum_offers=3, maximum_spread_exclusive='3',
              proposal='Each supported eBay binding/grade/currency scenario remains separate',
              abebooks='Native seller grades and query-matched context only; binding and independent listing ISBN unavailable',
              publication='disabled', owned_condition='ungraded', shipping='excluded',
              material_change='At least 50% or USD 25 at either endpoint; review flag only')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unique(rows, field):
    result = {r[field]: r for r in rows}
    if len(result) != len(rows) or '' in result:
        raise ValueError('Missing or duplicate catalog identity')
    return result


def fresh(value, as_of):
    dt = timestamp(value)
    return bool(dt and 0 <= (as_of - dt.date()).days <= POLICY['max_age_days'])


def ebay_scenarios(book, previous, as_of):
    """Recheck bounds, dates, independent ISBNs and distinct offers for every row."""
    rows = []
    for raw in previous['scenarios']:
        s = dict(raw)
        offers = s['offers']
        prices = [number(o['price']) for o in offers]
        keys = [listing_key(dict(source='ebay_active_listings', listing_url=o['url'])) for o in offers]
        if (not offers or any(p is None for p in prices) or len(set(keys)) != len(keys)
                or not all(keys) or min(prices) != number(s['low']) or max(prices) != number(s['high'])
                or len(offers) != s['listing_count'] or s.get('publishable') or not s.get('scenario_only')):
            raise ValueError('Invalid retained eBay scenario')
        target = isbn(book.get('isbn13') or book.get('isbn10'))
        independent = bool(target) and all(isbn(o['isbn']) == target for o in offers)
        s['eligible_now'] = bool(s['stronger'] and independent and all(fresh(o['date'], as_of) for o in offers)
                                 and len(offers) >= 3 and max(prices) < 3*min(prices)
                                 and s['listing_binding'] in {'paperback', 'hardcover'})
        s['identity_matches_current'] = independent
        rows.append(s)
    return rows


def abe_context(book, rows, as_of):
    reviewed = review_book(book, rows, as_of=as_of)
    # The existing matcher sorts by canonical JSON. Keep the exact pairing.
    ordered = sorted(rows, key=lambda r: json.dumps(dict(r), sort_keys=True))
    groups, holds = defaultdict(list), []
    for raw, decision in zip(ordered, reviewed['decisions']):
        offer = dict(id=raw['observation_id'], url=raw['listing_url'], price=raw['asking_price'],
                     currency=raw['currency'], grade=raw['condition'], title=raw['listing_title'],
                     author=raw['listing_author'], observed_at=raw['observation_date'],
                     query=raw['search_query'], lookup_strategy=raw['lookup_strategy'],
                     returned_isbn=None, binding=None, reasons=decision['reasons'])
        # New offers are useful context, but cannot value a used owned copy.
        offer['used'] = raw['condition'].startswith('Used')
        if decision['disposition'] != 'candidate_only':
            offer['disposition'] = 'excluded'
            holds.append(offer)
            continue
        offer['disposition'] = 'query_matched_context'
        groups[(raw['condition'], raw['currency'])].append(offer)
    contexts = []
    for (grade, currency), offers in sorted(groups.items()):
        prices = [Decimal(o['price']) for o in offers]
        contexts.append(dict(native_grade=grade, currency=currency, low=str(min(prices)), high=str(max(prices)),
                             count=len(offers), used=offers[0]['used'], high_spread=max(prices) >= 3*min(prices),
                             offers=offers, independently_verified=False))
    return contexts, holds


def compare_book(book, previous, observations, as_of):
    scenarios = ebay_scenarios(book, previous, as_of)
    context, excluded = abe_context(book, observations, as_of)
    proposals = []
    questions = [dict(kind=t.get('kind'), question=t['question']) for t in previous['physical_tasks']]
    # The later consolidated record review already covers overlapping checks.
    # Retain canonical references in evidence without asking the owner twice.
    if not questions:
        for t in previous.get('canonical_checks', []):
            questions.append(dict(kind='canonical_book_check', question=t['action']))
    questions = list({q['question']:q for q in questions}.values())
    for s in scenarios:
        if not s['eligible_now']:
            continue
        low, high = Decimal(s['low']), Decimal(s['high'])
        used = [g for g in context if g['used'] and g['currency'] == s['currency']]
        new = [g for g in context if not g['used'] and g['native_grade'] == 'New' and g['currency'] == s['currency']]
        # This compares market context only; AbeBooks grades/bindings are not equated to eBay.
        alo = min((Decimal(g['low']) for g in used), default=None)
        ahi = max((Decimal(g['high']) for g in used), default=None)
        relation = ('unavailable' if alo is None else 'below_ebay' if ahi < low else
                    'above_ebay' if alo > high else 'overlapping_context')
        flags = []
        if relation in {'below_ebay', 'above_ebay'}:
            flags.append('AbeBooks used-price context is outside this eBay scenario; inspect listing editions and condition before choosing a value')
        if new and min(Decimal(g['low']) for g in new) < low:
            flags.append('A query-matched new AbeBooks offer is cheaper than the eBay low; check availability and edition before accepting this used-copy range')
        current_low, current_high = number(book['estimated_value_precise_low']), number(book['estimated_value_precise_high'])
        comparable = bool(book['usable_market_estimate'] and current_low and current_high and book['estimated_value_currency'] == s['currency'])
        material = comparable and any(abs(n-o)/o >= Decimal('.5') or
                                     (s['currency']=='USD' and abs(n-o) >= 25)
                                     for n,o in ((low,current_low),(high,current_high)))
        if material:
            flags.append('Large change from the current range: review before publication')
        proposals.append(dict(low=str(low), high=str(high), currency=s['currency'],
                              binding=s['listing_binding'], ebay_grade=s['hypothetical_grade'],
                              offer_count=s['listing_count'], offers=s['offers'],
                              abebooks_context=relation, material_change=bool(material),
                              flags=flags, publishable=False))
    status = ('saved_review_protected' if book['reviewed_estimate_id'] else
              'physical_identity_check' if questions else
              'price_context_review' if proposals and any(p['flags'] for p in proposals) else
              'conditional_proposal' if proposals else 'more_market_evidence')
    research = []
    if previous['pilot_identification_checks']:
        research.append('Reconcile the earlier pilot identity flags against existing source records before creating any new owner question')
    if context:
        research.append('Verify AbeBooks listing ISBN and binding; search-query matches alone cannot establish comparable editions')
    if not proposals:
        research.append('Gather at least three fresh edition-matched used offers in one binding, grade and currency with less than threefold spread')
    if any(p['flags'] for p in proposals):
        research.append('Resolve price-context differences using listing details; do not average the two sources')
    if book['reviewed_estimate_id']:
        research.append('Obtain an explicit decision before replacing the saved manually reviewed range')
    return dict(catalog_item_id=book['catalog_item_id'], title=book['title'], author=book['author'],
                isbn=book['isbn13'] or book['isbn10'], location=book['location_summary'], copies=book['copy_count'],
                current_low=book['estimated_value_precise_low'], current_high=book['estimated_value_precise_high'],
                current_currency=book['estimated_value_currency'], current_display=book['resale_market_summary'],
                status=status, proposals=proposals, abebooks=context, abebooks_excluded=excluded,
                ebay_scenarios=scenarios, physical_questions=questions, research_next_steps=research,
                canonical_check_references=previous.get('canonical_checks', []),
                publication_check='Confirm the owned copy’s binding, completeness and condition, then select the applicable scenario; no physical grade has been assigned',
                reviewed_estimate_id=book['reviewed_estimate_id'], publishable=False)


def csv_write(path, rows, fields):
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in rows:
            w.writerow({k:("'"+str(row.get(k,'')) if str(row.get(k,'')).startswith(('=','+','-','@')) else row.get(k,'')) for k in fields})
    path.chmod(0o600)


def build(inputs, output, as_of):
    inputs, output = Path(inputs), Path(output)
    if output.exists():
        raise ValueError('Choose a new output directory')
    hashes={p.name:sha(p) for p in inputs.iterdir() if p.is_file()}
    current=json.loads((inputs/'current_library.json').read_text())
    ebay=json.loads((inputs/'ebay_comparison.json').read_text())
    cohort=json.loads((inputs/'abebooks_cohort.json').read_text())
    receipt=json.loads((inputs/'abebooks_status.json').read_text())
    with (inputs/'abebooks_observations.csv').open(newline='') as f:observations=list(csv.DictReader(f))
    books=unique(current['books'],'catalog_item_id'); older=unique(ebay['books'],'catalog_item_id')
    frozen=unique(cohort,'catalog_id');groups=defaultdict(list)
    for r in observations:groups[r['catalog_id']].append(r)
    if (receipt['state']!='complete' or receipt['estimates_published'] or not receipt['source_data_unchanged']
            or receipt['completed']!=len(frozen) or set(frozen)!=set(older) or set(groups)!=set(frozen)):
        raise ValueError('Incomplete or mismatched retained collection scope')
    if not set(books)<=set(frozen):raise ValueError('Current inventory includes books outside collected scope')
    if sum(r['lookup_status']=='observed' for r in observations)!=receipt['observed_listings']:
        raise ValueError('AbeBooks receipt does not reconcile')
    checks=json.loads((inputs/'current_book_checks.json').read_text())
    for t in checks:
        if t.get('catalog_item_id') in older:
            older[t['catalog_item_id']].setdefault('canonical_checks',[]).append(t)
    result=[]
    for key,b in books.items():
        if isbn(b['isbn13'] or b['isbn10']) != isbn(frozen[key]['isbn13'] or frozen[key]['isbn10']):
            raise ValueError('Current edition differs from AbeBooks cohort')
        result.append(compare_book(b,older[key],groups[key],as_of))
    result.sort(key=lambda b:(not bool(b['physical_questions']),not any(p['material_change'] for p in b['proposals']),b['title'].casefold()))
    summary=dict(records=len(result),excluded_no_longer_active=len(frozen)-len(books),
                 linked_copies=sum(b['copies'] for b in result),physical_books=current['inventory']['source_copies'],
                 unidentified_entries=len(current['inventory']['unresolved_observation_ids']),
                 statuses=dict(Counter(b['status'] for b in result)),
                 books_with_conditional_proposals=sum(bool(b['proposals']) for b in result),
                 conditional_proposals=sum(len(b['proposals']) for b in result),
                 books_with_abe_used_context=sum(any(g['used'] for g in b['abebooks']) for b in result),
                 price_context_review_books=sum(any(p['flags'] for p in b['proposals']) for b in result),
                 large_change_books=sum(any(p['material_change'] for p in b['proposals']) for b in result),
                 books_with_existing_physical_questions=sum(bool(b['physical_questions']) for b in result),
                 pilot_records_flags_to_reconcile=sum(bool(older[b['catalog_item_id']]['pilot_identification_checks']) for b in result),
                 estimates_changed=0,source_requests=0)
    if hashes!={p.name:sha(p) for p in inputs.iterdir() if p.is_file()}:raise ValueError('Analysis input changed')
    report=dict(unidentified_book_checks=[t for t in checks if not t.get('catalog_item_id')],as_of=as_of.isoformat(),summary=summary,policy=POLICY,books=result,input_hashes=hashes,
                code_sha256=sha(__file__),canonical_baseline_hashes=current['protected'])
    output.mkdir(parents=True,mode=0o700)
    (output/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));(output/'review.json').chmod(0o600)
    proposal_rows=[];question_rows=[];book_rows=[]
    for b in result:
        common={k:b[k] for k in ('catalog_item_id','title','isbn','location','copies','status','current_low','current_high','current_currency')}
        book_rows.append(dict(common,conditional_proposals=len(b['proposals']),research_next_steps='; '.join(b['research_next_steps']),publication_check=b['publication_check']))
        for p in b['proposals']:
            proposal_rows.append(dict(common,**{k:p[k] for k in ('low','high','currency','binding','ebay_grade','offer_count','abebooks_context','material_change')},flags='; '.join(p['flags']),source_links='; '.join(o['url'] for o in p['offers']),publishable=False))
        if b['physical_questions']:
            question_rows.append(dict(common,kind='consolidated_existing_questions',question=' | '.join(q['question'] for q in b['physical_questions'])))
    for t in checks:
        if not t.get('catalog_item_id'):
            question_rows.append(dict(catalog_item_id='',title=t['title'],location=t['location'],kind='unidentified_inventory_entry',question=t['action']))
    csv_write(output/'book_review.csv',book_rows,list(book_rows[0]))
    csv_write(output/'conditional_proposals.csv',proposal_rows,list(proposal_rows[0]) if proposal_rows else ['catalog_item_id'])
    csv_write(output/'physical_questions.csv',question_rows,list(question_rows[0]) if question_rows else ['catalog_item_id'])
    template=Path(__file__).with_name('combined_market_review_template.html').read_text()
    (output/'index.html').write_text(template.replace('__DATA__',json.dumps(report,ensure_ascii=False).replace('<',r'\u003c')))
    (output/'index.html').chmod(0o600)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',required=True);p.add_argument('--output',required=True);p.add_argument('--as-of',type=date.fromisoformat,required=True)
    a=p.parse_args();print(json.dumps(build(a.inputs,a.output,a.as_of)['summary'],indent=2))
