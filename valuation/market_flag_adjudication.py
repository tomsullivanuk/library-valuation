"""Read-only adjudication of retained market flags and listing-page receipts.

No collector, estimate writer, grade assignment or Action Item mutation exists.
Receipts are visible-page observations, not search-query identity assertions.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import csv
import hashlib
import json
from pathlib import Path
import re
from statistics import median

from valuation.offline_valuation_review import isbn, listing_key, number, timestamp, volume_numbers

FIELDS={'Title','Author','Publisher','Publication year','Condition','Binding','Language','ISBN 10','ISBN 13','Edition'}
# Only literally matching ordinary grade labels can share a working group.
# Fair, Fine, As New and Near Fine are not translated to eBay categories.
GRADES={'good':'good','very good':'very_good','acceptable':'acceptable','like new':'like_new','new':'new','brand new':'new'}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fields(receipt):
    lines=receipt.get('details','').splitlines()
    return {line:lines[i+1] for i,line in enumerate(lines[:-1]) if line in FIELDS}


def binding(value):
    value=re.sub(r'[\s-]+','',value.lower())
    return 'paperback' if value in {'paperback','softcover'} else 'hardcover' if value in {'hardcover','hardback'} else ''


def page_offer(receipt, target, as_of):
    f=fields(receipt);issues=[]
    actual=isbn(f.get('ISBN 13') or f.get('ISBN 10'))
    if not receipt.get('details'):issues.append('page_metadata_unavailable')
    if re.search(r'\b(ebook|e-book|audiobook|kindle|pdf|signed|inscribed|bundle)\b|\b(?:lot|set) of \d|\b\d+[ -]volume set', f.get('Title','')+' '+f.get('Edition',''), re.I):
        issues.append('special_copy_not_ordinary_comparable')
    if not actual:issues.append('returned_isbn_unavailable')
    elif actual!=target:issues.append('different_listing_isbn')
    fmt=binding(f.get('Binding',''))
    if not fmt:issues.append('listing_binding_unavailable')
    native=f.get('Condition','').strip();grade=GRADES.get(native.lower(),'')
    if not grade:issues.append('native_grade_kept_separate')
    observed=timestamp(receipt.get('observed_at',''))
    if observed is None or not 0 <= (as_of-observed.date()).days <= 30:issues.append('page_date_not_current')
    m=re.search(r'US\$\s*([\d,]+(?:\.\d{1,2})?)',receipt.get('price_context',''))
    price=number(m[1].replace(',','')) if m else None
    if price is None:issues.append('current_item_price_unavailable')
    # Keep new offers as context, never as the owned copy's condition.
    return dict(source='abebooks',url=receipt['url'],isbn=actual,binding=fmt,grade=grade,
                native_grade=native,price=str(price) if price else '',currency='USD' if price else '',
                observed_at=receipt.get('observed_at',''),issues=issues,title=f.get('Title',''),
                publisher=f.get('Publisher',''),year=f.get('Publication year',''),edition=f.get('Edition',''),
                target_match=bool(target and actual==target),eligible=not issues)


def fresh(value, as_of):
    t=timestamp(value)
    return t is not None and 0 <= (as_of-t.date()).days <= 30


def working_groups(offers):
    """Retain native-grade/format/currency boundaries and conservative holds."""
    unique={};conflicts=set()
    for offer in offers:
        key=(offer['source'],listing_key(dict(listing_url=offer['url'],source=offer['source'])))
        if not key[1]:raise ValueError('Offer lacks a stable URL')
        if key in unique and any(unique[key][k]!=offer[k] for k in ('price','isbn','binding','grade','currency')):
            conflicts.add(key)
        unique[key]=offer
    rows=[dict(o,hold='duplicate_metadata_conflict' if k in conflicts else '') for k,o in unique.items()]
    used=defaultdict(list);new=defaultdict(list)
    for o in rows:
        if o['hold']:continue
        key=(o['binding'],o['currency'])
        if o['grade']=='new':new[key].append(o)
        else:used[key+(o['grade'],)].append(o)
    result=[]
    for (fmt,currency,grade), group in sorted(used.items()):
        if len(group)>=4:
            high=max(group,key=lambda x:Decimal(x['price']));others=[o for o in group if o is not high]
            prices=[Decimal(o['price']) for o in others]
            if max(prices)/min(prices)<=Decimal('1.5') and Decimal(high['price'])>3*median(prices):
                high['hold']='isolated_high_outlier'
        for o in group:
            cheaper=[n for n in new[(fmt,currency)] if Decimal(n['price'])<Decimal(o['price'])]
            if len(cheaper)>=2 and Decimal(o['price'])>Decimal('1.25')*min(Decimal(n['price']) for n in cheaper):
                o['hold']='above_two_matching_new_offers'
        kept=[o for o in group if not o['hold']];prices=[Decimal(o['price']) for o in kept]
        if not prices:continue
        low,high=min(prices),max(prices)
        result.append(dict(binding=fmt,currency=currency,grade=grade,low=str(low),high=str(high),
                           offer_count=len(kept),sources=sorted({o['source'] for o in kept}),
                           supported=len(kept)>=3 and high<3*low,offers=kept,
                           held=[o for o in group if o['hold']],
                           interpretation='Observed asking-price envelope; seller labels agree literally, grading standards and independent sellers are not established',publishable=False))
    return result,rows


def adjudicate(book, prior, detailed, page_receipts, old_rows, as_of):
    target=isbn(book['isbn13'] or book['isbn10']);offers=[];page_review=[]
    # Prior source review owns exclusions; held evidence is never promoted here.
    for o in detailed['listing_decisions']:
        if o['review_disposition']!='retained_candidate':continue
        actual=isbn(o.get('listing_isbn13') or o.get('listing_isbn10'))
        price=number(o['asking_price']);fmt=binding(o.get('listing_binding',''));grade=o.get('listing_condition_grade','')
        if not(target and actual==target and price and fmt and grade in set(GRADES.values()) and fresh(o['observation_date'],as_of)):
            continue
        offers.append(dict(source='ebay_active_listings',url=o['listing_url'],isbn=actual,binding=fmt,
                           grade=grade,native_grade=grade.replace('_',' '),price=str(price),currency=o['currency'],
                           observed_at=o['observation_date']))
    for receipt in page_receipts:
        if receipt['role']=='previous_range':continue
        o=page_offer(receipt,target,as_of)
        wanted_volumes=volume_numbers(book['title']);actual_volumes=volume_numbers(o['title'])
        if wanted_volumes and actual_volumes and wanted_volumes.isdisjoint(actual_volumes):
            o['issues'].append('different_volume_in_listing_title');o['eligible']=False
        page_review.append(o)
        if o['eligible']:offers.append(o)
    groups,decisions=working_groups(offers)
    identity_ok=detailed['identity_supported_from_records']
    supported=[g for g in groups if g['supported'] and identity_ok]
    old_checks=[]
    for r in page_receipts:
        if r['role']!='previous_range':continue
        f=fields(r);actual=isbn(f.get('ISBN 13') or f.get('ISBN 10'))
        old_checks.append(dict(url=r['url'],observation_id=r['source_observation_id'],current_listing_isbn=actual,
                               target_isbn=target,different_edition=bool(actual and target and actual!=target),
                               metadata_checked_on=r['observed_at'],historical_metadata_verified=False))
    reasons=[]
    if any(o['different_edition'] for o in old_checks):
        reasons.append('At least one offer behind the previous title/author range now identifies another edition; the old range is not a verified same-edition baseline')
    elif old_rows and any(o.get('lookup_strategy')=='title_author' for o in old_rows):
        reasons.append('Previous range used title/author matches; a price change alone does not prove appreciation of the same edition')
    mismatches=[o for o in page_review if o['issues']]
    if any('different_listing_isbn' in o['issues'] for o in mismatches):reasons.append('Exclude selected AbeBooks context with a different returned listing ISBN')
    source_formats=defaultdict(set)
    for o in offers:source_formats[o['source']].add(o['binding'])
    if source_formats['abebooks'] and source_formats['ebay_active_listings'] and source_formats['abebooks'].isdisjoint(source_formats['ebay_active_listings']):
        reasons.append('The verified sources describe different bindings; their prices must remain separate')
    if any(o['hold']=='isolated_high_outlier' for o in decisions):reasons.append('Hold isolated high asking prices under the existing tight-cluster rule')
    if any(o['hold']=='above_two_matching_new_offers' for o in decisions):reasons.append('Hold used asking prices above two cheaper matching-ISBN/binding new offers')
    if book['reviewed_estimate_id']:status='saved_review_protected'
    elif not supported:status='market_research_retained'
    elif any(len(g['sources'])==2 for g in supported):status='cross_source_conditional_range'
    else:status='single_source_conditional_range'
    internal=[]
    if not supported:internal.append('Retained matched evidence is too thin or too widely spread; keep this with market research, not the owner checklist')
    if mismatches:internal.append('Some source offers remain excluded or unverified; preserve their specific reasons and seek suitable replacements if needed')
    if any(len(g['sources'])==1 for g in supported):internal.append('Some supported scenarios remain single-source; do not describe those as cross-source corroboration')
    if status=='saved_review_protected':internal.append('Saved manual review remains protected; no replacement is authorized')
    return dict(catalog_item_id=book['catalog_item_id'],title=book['title'],location=book['location_summary'],
                current_low=book['estimated_value_precise_low'],current_high=book['estimated_value_precise_high'],
                current_currency=book['estimated_value_currency'],status=status,reasons=reasons,
                supported_groups=supported,all_groups=groups,offer_decisions=decisions,
                abebooks_page_review=page_review,previous_offer_checks=old_checks,research_next_steps=internal,
                actual_condition='ungraded',publishable=False)


def write_csv(path,rows,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:w.writerow({k:("'"+str(r.get(k,'')) if str(r.get(k,'')).startswith(('=','+','-','@')) else r.get(k,'')) for k in fields})
    path.chmod(0o600)


def build(root, original, output, as_of):
    root,original,output=map(Path,(root,original,output))
    if output.exists():raise ValueError('Choose a new review output')
    names=['scope.json','source_records_with_pilots.json','listing_details.json','full_listing_plan.json','previous_observations.json','pilot_decisions.json','all_source_notes.json']
    hashes={name:digest(root/name) for name in names};hashes[str(original)]=digest(original)
    source=json.loads((root/'source_records_with_pilots.json').read_text());report=json.loads(original.read_text())
    scope=json.loads((root/'scope.json').read_text());previous={b['catalog_item_id']:b for b in report['books']};current={b['catalog_item_id']:b for b in source['current_books']}
    if not source['unchanged']:raise ValueError('Source records changed during snapshot')
    if not set(scope['flagged'])<=set(current):raise ValueError('Flagged inventory changed; refresh review scope')
    receipts=json.loads((root/'listing_details.json').read_text());plan=json.loads((root/'full_listing_plan.json').read_text())
    by_url={}
    for r in receipts:
        if r.get('details') or r.get('checked_after_wait'):by_url[r['url']]=r
    if any(r.get('blocked') for r in receipts):raise ValueError('Listing access block: hold collection and review separately')
    missing={p['url'] for p in plan}-set(by_url)
    if missing:raise ValueError(f'Listing review incomplete: {len(missing)} pages')
    by_book=defaultdict(list)
    for p in plan:
        by_book[p['catalog_item_id']].append(dict(by_url[p['url']],**p))
    old_rows=json.loads((root/'previous_observations.json').read_text());rows=[]
    for cid in scope['flagged']:
        b=current[cid];old=previous[cid]
        if any(b[a]!=old[z] for a,z in [('estimated_value_precise_low','current_low'),('estimated_value_precise_high','current_high'),('estimated_value_currency','current_currency')]):
            raise ValueError('Current saved value differs from prior review; do not silently reset baseline')
        rows.append(adjudicate(b,old,source['reviews'][cid],by_book[cid],old_rows.get(cid,[]),as_of))
    pilot=json.loads((root/'pilot_decisions.json').read_text())
    if len(pilot)!=len(scope['pilots']) or {p['catalog_item_id'] for p in pilot}!=set(scope['pilots']):raise ValueError('Pilot check coverage mismatch')
    source_notes=json.loads((root/'all_source_notes.json').read_text())
    for p in pilot:
        preserved={n.get('notes') for n in source_notes if n.get('observation_id') in p['source_observation_ids']}
        if (not p['source_notes'] or not set(p['source_notes'])<=preserved or p['copy_isbn_assigned'] or p['actual_condition']!='ungraded'
                or p['outcome'] not in {'record_profile_available','existing_physical_check','physical_check_required'}):
            raise ValueError('Pilot decision lacks preserved notes or assigns unsupported copy facts')
    owner={b['catalog_item_id']:dict(catalog_item_id=b['catalog_item_id'],title=b['title'],location=b['location'],question=' | '.join(q['question'] for q in b['physical_questions']),kind='existing_identity_check') for b in report['books'] if b['physical_questions']}
    for p in pilot:
        if p['outcome']=='physical_check_required':
            if p['catalog_item_id'] in owner:raise ValueError('New question duplicates an existing owner task')
            b=current[p['catalog_item_id']];owner[p['catalog_item_id']]=dict(catalog_item_id=p['catalog_item_id'],title=b['title'],location=p['location'],question=p['question'],kind='narrowed_pilot_identity_check')
    for i,b in enumerate(report['unidentified_book_checks']):owner[f'unidentified:{i}']=dict(catalog_item_id='',title=b['title'],location=b['location'],question=b['action'],kind='unidentified_inventory_entry')
    for row in owner.values():
        row['location']=row['location'].removeprefix('Box ');row['answer']=''
    def location_key(value):
        return tuple((0,int(x)) if x.isdigit() else (1,x.casefold()) for x in re.split(r'(\d+)',value))
    owner_rows=sorted(owner.values(),key=lambda r:(location_key(r['location']),r['title'].casefold()))
    summary=dict(flagged_books=len(rows),statuses=dict(Counter(b['status'] for b in rows)),
                 supported_conditional_groups=sum(len(b['supported_groups']) for b in rows),
                 old_range_books_with_different_listing_edition=sum(any(x['different_edition'] for x in b['previous_offer_checks']) for b in rows),
                 books_with_rejected_different_isbn_context=sum(any('different_listing_isbn' in o['issues'] for o in b['abebooks_page_review']) for b in rows),
                 pilot_outcomes=dict(Counter(p['outcome'] for p in pilot)),owner_check_rows=len(owner_rows),
                 listing_pages_checked=len(set(p['url'] for p in plan)),metadata_pages=sum(bool(r.get('details')) for r in by_url.values()),
                 saved_values_changed=0,canonical_tasks_changed=0,physical_grades_assigned=0)
    output.mkdir(parents=True,mode=0o700)
    payload=dict(as_of=as_of.isoformat(),summary=summary,books=rows,pilot_decisions=pilot,owner_checks=owner_rows,
                 input_hashes=hashes,code_sha256=digest(__file__),publication='disabled',
                 policy='Literal condition labels only; known matching ISBN/binding/currency; three distinct offers and less than threefold spread; no assertion of independent sellers; outlier and cheaper-new holds retained')
    (output/'adjudications.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2));(output/'adjudications.json').chmod(0o600)
    write_csv(output/'owner_physical_checks.csv',owner_rows,['catalog_item_id','title','location','kind','question','answer'])
    cases=[dict(catalog_item_id=b['catalog_item_id'],title=b['title'],location=b['location'],status=b['status'],findings='; '.join(b['reasons']),research_next_steps='; '.join(b['research_next_steps'])) for b in rows]
    write_csv(output/'case_decisions.csv',cases,list(cases[0]))
    scenarios=[]
    for b in rows:
        for g in b['supported_groups']:scenarios.append(dict(catalog_item_id=b['catalog_item_id'],title=b['title'],location=b['location'],current_low=b['current_low'],current_high=b['current_high'],current_currency=b['current_currency'],binding=g['binding'],grade=g['grade'],currency=g['currency'],proposed_low=g['low'],proposed_high=g['high'],offers=g['offer_count'],sources='; '.join(g['sources']),publishable=False))
    write_csv(output/'revised_conditional_proposals.csv',scenarios,list(scenarios[0]) if scenarios else ['catalog_item_id'])
    if any(digest(root/name)!=hashes[name] for name in names) or digest(original)!=hashes[str(original)]:raise ValueError('Review inputs changed')
    return payload


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--original',required=True);p.add_argument('--output',required=True);p.add_argument('--as-of',type=date.fromisoformat,required=True)
    a=p.parse_args();print(json.dumps(build(a.root,a.original,a.output,a.as_of)['summary'],indent=2))
