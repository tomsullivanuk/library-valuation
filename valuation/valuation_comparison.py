"""Read-only comparison of completed asking-price scenarios with live estimates.

No network collection, condition assignment, estimate writes or source repair.
The existing private review report gains a separate comparison artifact.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import html
import json
from pathlib import Path

from valuation import whole_library_review as whole
from valuation.offline_valuation_review import isbn, listing_key
from valuation.workspace_service import load_model

POLICY = dict(minimum_offers=3, maximum_spread_exclusive='3',
              relative_endpoint_attention='0.50', usd_endpoint_attention='25',
              max_age_days=30, actual_condition='ungraded', publication='disabled',
              legacy_pilot_binding='Validate pooled source bounds, then split by retained listing binding')
LABELS = {
    'no_scenario': 'No retained used-price scenario',
    'limited_only': 'Only limited or uncertain comparisons',
    'no_current': 'Stronger scenario; no comparable current estimate',
    'lower': 'All stronger scenarios below current range',
    'higher': 'All stronger scenarios above current range',
    'mixed': 'Result depends on condition or binding',
    'overlap': 'Stronger scenarios overlap current range',
}


def number(value):
    try:
        n = Decimal(str(value))
        return n if n.is_finite() and n > 0 else None
    except (InvalidOperation, ValueError):
        return None


def unique(rows, field='catalog_item_id'):
    result = {}
    for row in rows:
        key = row[field]
        if not key or key in result:
            raise ValueError('Missing or duplicate catalog identity')
        result[key] = row
    return result


def assess_scenarios(book, current, as_of):
    """Recompute every scenario from retained listings before comparing endpoints."""
    if book.get('publishable') or book.get('actual_condition') != 'ungraded' or book.get('condition_assumed'):
        raise ValueError('Unexpected publication or assigned-condition state')
    retained = [d for d in book['listing_decisions'] if d['review_disposition'] == 'retained_candidate']
    rows = []
    seen = set()
    lo, hi = number(current['low']), number(current['high'])
    baseline_valid = bool(current['usable'] and lo and hi and lo <= hi and current['currency'])
    normalized=[]
    for raw in book['condition_scenarios']:
        if 'listing_binding' in raw:
            normalized.append(dict(raw,legacy_binding_split=False));continue
        offers=[d for d in retained if d['listing_condition_grade']==raw['hypothetical_grade'] and d['currency']==raw['currency']]
        prices=[number(d['asking_price']) for d in offers]
        if (not offers or any(p is None for p in prices) or len(offers)!=raw['listing_count'] or
                min(prices)!=number(raw['low']) or max(prices)!=number(raw['high'])):
            raise ValueError('Legacy scenario differs from its retained evidence')
        groups=defaultdict(list)
        for d in offers:groups[d.get('listing_binding') or 'unknown'].append(number(d['asking_price']))
        for fmt,values in sorted(groups.items()):
            normalized.append(dict(raw,listing_binding=fmt,low=str(min(values)),high=str(max(values)),
                                   listing_count=len(values),high_spread=max(values)>=3*min(values),
                                   legacy_binding_split=True))
    for raw in normalized:
        s = dict(raw)
        if s['hypothetical_grade'] not in {'acceptable','good','very_good','like_new'}:
            raise ValueError('Only labelled used-condition scenarios are permitted')
        key = (s['hypothetical_grade'], s['listing_binding'], s['currency'])
        if key in seen or s.get('publishable') or s.get('scenario_only') is not True:
            raise ValueError('Duplicate or non-scenario output')
        seen.add(key)
        offers = [d for d in retained if (d['listing_condition_grade'], d.get('listing_binding') or 'unknown', d['currency']) == key]
        prices = [number(d['asking_price']) for d in offers]
        if not offers or any(p is None for p in prices) or len({listing_key(d) for d in offers}) != len(offers):
            raise ValueError('Invalid or duplicate scenario offers')
        low, high = number(s['low']), number(s['high'])
        if low != min(prices) or high != max(prices) or s['listing_count'] != len(offers):
            raise ValueError('Scenario differs from its retained evidence')
        wide = high >= 3 * low
        if s['high_spread'] != wide:
            raise ValueError('Scenario spread differs from its evidence')
        target = isbn(book.get('identity_evidence', {}).get('target_isbn', ''))
        independent = bool(target) and all(isbn(d.get('listing_isbn13') or d.get('listing_isbn10', '')) == target for d in offers)
        fresh = all(0 <= (as_of - date.fromisoformat(d['observation_date'][:10])).days <= POLICY['max_age_days'] for d in offers)
        reasons = []
        if len(offers) < 3: reasons.append('Fewer than three offers')
        if wide: reasons.append('Asking prices span at least threefold')
        if s['listing_binding'] == 'unknown': reasons.append('Listing binding is unknown')
        if not book['identity_supported_from_records'] or not independent: reasons.append('Edition identity needs review')
        if not fresh: reasons.append('Evidence is stale or future-dated')
        s.update(stronger=not reasons, support_notes='; '.join(reasons),
                 evidence_label='; '.join(reasons) if reasons else 'Stronger conditional scenario', actual_condition='ungraded',
                 comparison='no comparable current estimate', delta_low='', delta_high='',
                 delta_low_percent='', delta_high_percent='', material_change=False,
                 offers=[dict(url=d['listing_url'], price=d['asking_price'], date=d['observation_date'],
                              isbn=d.get('listing_isbn13') or d.get('listing_isbn10', '')) for d in offers])
        if baseline_valid and current['currency'] == s['currency']:
            dl, dh = low-lo, high-hi
            relation = 'below' if high < lo else 'above' if low > hi else 'overlap'
            material = (abs(dl)/lo >= Decimal('.5') or abs(dh)/hi >= Decimal('.5') or
                        (s['currency'] == 'USD' and max(abs(dl), abs(dh)) >= 25))
            s.update(comparison=relation, delta_low=str(dl), delta_high=str(dh),
                     delta_low_percent=str(100*dl/lo), delta_high_percent=str(100*dh/hi),
                     material_change=bool(material))
        elif baseline_valid:
            s['comparison'] = 'currency differs; not converted'
        rows.append(s)
    return rows


def compare_one(current, book, as_of, physical_tasks):
    scenarios = assess_scenarios(book, current, as_of) if book else []
    stronger = [s for s in scenarios if s['stronger']]
    comparable = [s for s in stronger if s['comparison'] in {'below', 'above', 'overlap'}]
    directions = {s['comparison'] for s in comparable}
    category = ('no_scenario' if not scenarios else 'limited_only' if not stronger else
                'no_current' if not comparable else 'lower' if directions == {'below'} else
                'higher' if directions == {'above'} else 'overlap' if directions == {'overlap'} else 'mixed')
    material = any(s['material_change'] for s in comparable)
    flags = []
    if category == 'no_scenario': flags.append('Further market research: no retained used-price scenario')
    if category == 'limited_only': flags.append('Strengthen comparisons before proposing a replacement')
    if category == 'no_current': flags.append('No usable current range in the same currency to compare')
    if category in {'lower','higher','mixed'}: flags.append(LABELS[category])
    if material: flags.append('Review an endpoint change of at least 50% or USD 25')
    if scenarios and len(stronger) < len(scenarios): flags.append('Some condition scenarios have limited support')
    if len({s['listing_binding'] for s in scenarios}) > 1: flags.append('Different listing bindings must remain separate')
    if physical_tasks: flags.append('Existing copy-specific check remains deferred')
    dispositions = Counter(d['review_disposition'] for d in book['listing_decisions']) if book else Counter()
    held = {k:v for k,v in dispositions.items() if k.startswith('held_')}
    if held: flags.append('Held listings remain excluded from the working scenarios')
    max_change = max((max(abs(Decimal(s['delta_low'])), abs(Decimal(s['delta_high']))) for s in comparable), default=Decimal(0))
    priority = 'Review large change' if material else 'Research comparisons' if category in {'no_scenario','limited_only'} else 'Review conditional range' if category != 'overlap' else 'No large change flagged'
    return dict(**current, category=category, category_label=LABELS[category], priority=priority,
                material_change=material, maximum_endpoint_change=str(max_change),
                stronger_scenarios=len(stronger), scenario_count=len(scenarios), flags=flags,
                held_listing_counts=held, scenarios=scenarios, physical_tasks=physical_tasks,
                actual_condition='ungraded', publishable=False)


def load_reviews(project, job, inputs):
    manifest = json.loads((job/'manifest.json').read_text())
    whole.verify_frozen(job, manifest)
    if json.loads((job/'status.json').read_text())['state'] != 'complete':
        raise ValueError('Whole-library collection is not complete')
    reviews, cohorts, origins = [], [], {}
    for batch in manifest['batches']:
        folder = job/batch['folder']; receipt = folder/'result.json'
        result = json.loads(receipt.read_text()); path = folder/result['report_json']
        inputs[str(path)] = whole.sha(path)
        rows = json.loads(path.read_text())['reviews']
        expected = whole.read_csv(folder/'cohort.csv')
        if set(unique(rows)) != set(unique(expected)):
            raise ValueError('Completed batch scope mismatch')
        reviews.extend(rows);cohorts.extend(expected)
        origins.update({r['catalog_item_id']:str(folder/result['report']) for r in rows})
    base = project/'output/valuation_review_20261106'
    pilot_specs = [
        ('pilot_candidates.csv','live_ebay_pilot_v1/used_followup_v1/review_final/review.json'),
        ('scale_test_100_v1/cohort.csv','scale_test_100_v1/refined_review_v2/review/review.json'),
    ]
    missing_pilot_reviews = []
    for cohort_name, review_name in pilot_specs:
        cp, rp = base/cohort_name, base/review_name
        inputs[str(cp)], inputs[str(rp)] = whole.sha(cp), whole.sha(rp)
        doc = json.loads(rp.read_text())
        for name,digest in doc['input_hashes'].items():
            if not Path(name).is_file() or whole.sha(name) != digest:
                raise ValueError('Pilot evidence changed or is unavailable')
            inputs[name] = digest
        cohort, rows = whole.read_csv(cp), doc['reviews']
        if not set(unique(rows)) <= set(unique(cohort)):
            raise ValueError('Pilot review scope mismatch')
        missing_pilot_reviews.extend(sorted(set(unique(cohort))-set(unique(rows))))
        reviews.extend(rows);cohorts.extend(cohort)
        origins.update({r['catalog_item_id']:str(rp.with_suffix('.html')) for r in rows})
    return unique(reviews), unique(cohorts), origins, missing_pilot_reviews


def build(project, job, output, as_of):
    project, job, output = map(lambda p:Path(p).resolve(), (project,job,output))
    if output.exists() or 'data' in output.parts or output == job or job in output.parents:
        raise ValueError('Choose a new private output directory outside source/production data')
    before = whole.protected(project)
    inputs = {str(project/k):v for k,v in before.items()}
    template = Path(__file__).with_name('valuation_comparison_template.html')
    inputs[str(template)] = whole.sha(template)
    reviews, cohorts, origins, missing = load_reviews(project,job,inputs)
    model = load_model(project/'data',project/'output')
    active = set(model.completed_inventory.catalog_item_ids)
    if active != set(cohorts): raise ValueError('Comparison does not cover the exact active catalog')
    sidecar = project/'output/valuation_review_20261106/all_batch_check_review_v1/results'
    physical_path = sidecar/'physical_checks_only.csv'
    inputs[str(physical_path)] = whole.sha(physical_path)
    physical = whole.read_csv(physical_path); tasks = defaultdict(list)
    for task in physical: tasks[task['catalog_item_id']].append(task)
    # The cumulative source review owns these questions; do not recreate raw flags.
    from valuation.records_check_scope import validate_completed
    output.mkdir(parents=True,mode=0o700)
    coverage = validate_completed(job,sidecar.parent/'scope/review_packet.json',sidecar/'adjudications.json',output/'records_validation')
    books=[]
    whole_ids={r['catalog_item_id'] for r in whole.read_csv(job/'cohort.csv')}
    for b in model.books:
        if b.catalog_item_id not in active:continue
        current=dict(catalog_item_id=b.catalog_item_id,title=b.title,author=b.author,
                     isbn=b.isbn13 or b.isbn10,location=b.location_summary,copy_count=b.copy_count,
                     low=b.estimated_value_precise_low,high=b.estimated_value_precise_high,
                     currency=b.estimated_value_currency,current_display=b.estimated_value_display,
                     usable=b.usable_market_estimate,reviewed_estimate_id=b.reviewed_estimate_id,
                     evidence_report=origins.get(b.catalog_item_id,''))
        item=compare_one(current,reviews.get(b.catalog_item_id),as_of,tasks[b.catalog_item_id])
        item['pilot_identification_checks']=([c for c in reviews[b.catalog_item_id]['physical_checks']
                  if c['kind'] in {'edition','inferred_copy_identity'}]
                  if b.catalog_item_id in reviews and b.catalog_item_id not in whole_ids else [])
        if item['pilot_identification_checks']:
            item['flags'].append('Earlier pilot identity checks need reconciliation before adding owner tasks')
        books.append(item)
    books.sort(key=lambda b:(not b['material_change'], -Decimal(b['maximum_endpoint_change']) if b['currency']=='USD' else 0,b['title'].casefold(),b['catalog_item_id']))
    summary=dict(records=len(books),physical_copies=model.completed_inventory.source_copies,
                 linked_physical_copies=sum(b['copy_count'] for b in books),
                 unidentified_inventory_entries=len(model.completed_inventory.unresolved_observation_ids),
                 categories=dict(Counter(b['category'] for b in books)),
                 books_with_scenarios=sum(bool(b['scenarios']) for b in books),
                 books_with_stronger_scenarios=sum(bool(b['stronger_scenarios']) for b in books),
                 material_change_books=sum(b['material_change'] for b in books),
                 scenarios=sum(b['scenario_count'] for b in books),
                 stronger_scenarios=sum(b['stronger_scenarios'] for b in books),
                 missing_original_pilot_reviews=len(missing),existing_whole_batch_physical_tasks=len(physical),
                 pilot_books_with_identity_checks=sum(bool(b['pilot_identification_checks']) for b in books),
                 physical_grading='deferred',estimates_changed=0,source_requests=0,publication='disabled')
    report=dict(as_of=as_of.isoformat(),summary=summary,policy=POLICY,books=books,
                missing_original_pilot_reviews=missing,records_coverage=coverage,
                input_hashes=inputs,comparison_code_sha256=whole.sha(__file__))
    if before != whole.protected(project) or any(whole.sha(p)!=digest for p,digest in inputs.items()):
        raise ValueError('Source or current estimates changed during comparison')
    whole.atomic(output/'comparison.json',report)
    rows=[]
    for b in books:
        for s in b['scenarios']:
            rows.append(dict(catalog_item_id=b['catalog_item_id'],title=b['title'],location=b['location'],
                             current_low=b['low'],current_high=b['high'],current_currency=b['currency'],
                             **{k:v for k,v in s.items() if k!='offers'}))
    whole.save_csv(output/'scenario_comparisons.csv',safe_csv(rows),list(rows[0]) if rows else ['catalog_item_id'])
    bookrows=[{k:v for k,v in b.items() if k not in ('scenarios','physical_tasks','held_listing_counts','pilot_identification_checks')} for b in books]
    for b in bookrows:b['flags']='; '.join(b['flags'])
    whole.save_csv(output/'book_comparisons.csv',safe_csv(bookrows),list(bookrows[0]))
    render(report,output/'index.html')
    whole.atomic(output/'verification.json',dict(canonical_unchanged=before==whole.protected(project),
                 exact_active_scope=True,scenario_values_recomputed=True,publication='disabled',
                 physical_grading='deferred',files={p.name:whole.sha(p) for p in output.iterdir() if p.is_file()}))
    return report


def safe_csv(rows):
    return [{k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()} for row in rows]


def render(report, path):
    template = Path(__file__).with_name('valuation_comparison_template.html').read_text()
    data = json.dumps(report,ensure_ascii=False).replace('<',r'\u003c')
    page = template.replace('__COMPARISON_DATA__',data)
    path.write_text(page);path.chmod(0o600)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True);p.add_argument('--job',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--as-of',type=date.fromisoformat,required=True)
    a=p.parse_args();print(json.dumps(build(a.project,a.job,a.output,a.as_of)['summary'],indent=2))
