"""Network-free, preview-only valuation model and diagnostic replay artifacts.

Legacy query confidence is never promoted to independently verified edition
identity. Candidate ranges are diagnostic; only verified comparables can support
a proposed range. This module has no publication or collection capability.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from valuation.libib import is_valid_isbn10, is_valid_isbn13, isbn10_to_isbn13

VERSION = 'offline-review-v1'
POLICY = dict(max_age_days=30, minimum_comparables=3, maximum_spread_ratio='3',
              currencies=['USD', 'GBP', 'EUR', 'CAD', 'AUD', 'CHF', 'JPY', 'NZD'],
              scope='per-copy asking prices; not realized proceeds',
              publication='disabled; candidate ranges are never publishable')
REASONS = {
 'metadata_conflict':'The listing returned conflicting edition or format facts; review the original listing.',
 'source':'The observation source is unsupported.',
 'status_row':'The source reported a lookup status, not a listing.',
 'invalid_date':'The observation date is missing or invalid.',
 'future':'The observation is later than the replay date.',
 'stale':'The observation is older than the allowed age.',
 'invalid_price':'The asking price is missing, nonpositive or invalid.',
 'currency':'The currency is missing or unsupported.',
 'identity':'A stable listing reference is missing.',
 'duplicate':'This is a duplicate or superseded version of the same listing.',
 'duplicate_conflict':'The same listing has conflicting records at the same observation time.',
 'special_copy':'The listing may be digital, signed, a bundle or a multi-copy lot; review it separately.',
 'weak_match':'Listing title/author or independently returned ISBN do not provide a plausible match.',
 'isbn_mismatch':'The listing ISBN differs from the target edition.',
 'binding_mismatch':'The listing binding differs from the target binding.',
 'condition_mismatch':'The listing condition differs from the target condition.',
 'unverified_edition':'Edition/binding identity is not independently verified; query confidence alone is insufficient.',
 'unverified_condition':'Condition comparability has not been established.',
}


def isbn(value):
    value = re.sub(r'[^0-9Xx]', '', str(value)).upper()
    if len(value) == 13 and is_valid_isbn13(value): return value
    if len(value) == 10 and is_valid_isbn10(value): return isbn10_to_isbn13(value)
    return ''


def number(value):
    try:
        n = Decimal(str(value))
        return n if n.is_finite() and 0 < n <= Decimal('999999999') else None
    except (InvalidOperation, ValueError): return None


def money(value): return format(value.quantize(Decimal('.01')), 'f')


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        # Naive historical dates are permitted, with ordering normalized to ISO.
        from datetime import timezone
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (ValueError, TypeError): return None


def overlap(target, listing):
    def tokens(s): return set(re.findall(r'[\w]+', s.casefold())) - {'the','a','an','and','of','in','to','by'}
    a,b=tokens(target),tokens(listing)
    return len(a & b)/len(a) if a else 0


def binding(value):
    v=str(value).lower().replace('-', '')
    if any(x in v for x in ('paperback','softcover')):return 'paperback'
    if any(x in v for x in ('hardback','hardcover')):return 'hardcover'
    return ''


def listing_key(row):
    ref = row.get('listing_url','')
    try:
        parts=urlsplit(ref)
        if parts.username or parts.password:return ''
        hostname=parts.hostname
    except ValueError:return ''
    if parts.scheme in ('http','https') and hostname:
        if any(x in parts.path.lower() for x in ('searchresults','/sch/','/search')):return ''
        host=hostname.lower().removeprefix('www.')
        path=parts.path.rstrip('/')
        if 'ebay.' in host:
            match=re.search(r'/itm/(?:[^/]+/)?(\d+)',path)
            if match:path='/itm/'+match[1]
        return urlunsplit(('https',host,path,'',''))
    # eBay stable item IDs may be available without a URL. Never use a search URL.
    if row.get('source')=='ebay_active_listings' and re.fullmatch(r'(?:v1\|)?\d+(?:\|\d+)?',row.get('raw_reference','')):
        return row['raw_reference']
    return ''


def _range(rows):
    groups=defaultdict(list)
    for r in rows:groups[r['currency']].append(Decimal(r['price']))
    result={}
    for currency,prices in sorted(groups.items()):
        prices.sort();spread=prices[-1]/prices[0]
        result[currency]=dict(count=len(prices),low=money(prices[0]),high=money(prices[-1]),
                              high_spread=spread>=Decimal(POLICY['maximum_spread_ratio']))
    return result


def review_book(book, observations, *, as_of, max_age_days=30):
    """Return decisions, per-source diagnostics and an unpublishable proposal."""
    if max_age_days < 0:raise ValueError('max_age_days must be nonnegative')
    as_of=date.fromisoformat(as_of) if isinstance(as_of,str) else as_of
    target_isbn=isbn(book.get('isbn13') or book.get('isbn10',''))
    decisions=[];groups=defaultdict(list)
    # Sort explicitly so input ordering cannot select a preferred duplicate.
    for row in sorted(observations,key=lambda r:json.dumps(dict(r),sort_keys=True)):
        row=dict(row);reasons=[];dt=timestamp(row.get('observation_date',''))
        source=row.get('source','').lower()
        if source=='ebay':source='ebay_active_listings'
        d=dict(source=source,listing=listing_key(row),observed_at=row.get('observation_date',''),
               listing_title=row.get('listing_title',''),price='',currency=row.get('currency','').upper(),
               disposition='excluded',reasons=reasons,verified=False)
        decisions.append(d)
        if source not in {'abebooks','ebay_active_listings'}:reasons.append('source');continue
        if row.get('lookup_status')!='observed':reasons.append('status_row');continue
        if dt is None:reasons.append('invalid_date');continue
        if dt.date()>as_of:reasons.append('future');continue
        if (as_of-dt.date()).days>max_age_days:reasons.append('stale');continue
        if not d['listing']:reasons.append('identity');continue
        groups[(source,d['listing'])].append((dt,row,d))
    for entries in groups.values():
        newest=max(t for t,_,_ in entries)
        latest=[x for x in entries if x[0]==newest]
        comparison_fields=('asking_price','currency','condition','listing_title','listing_author','listing_isbn13','listing_isbn10','listing_binding','listing_condition_grade')
        signatures={json.dumps({k:row.get(k,'') for k in comparison_fields},sort_keys=True) for _,row,_ in latest}
        if len(signatures)>1:
            for _,_,d in entries:d['reasons'].append('duplicate_conflict')
            continue
        winner=latest[0]
        for entry in entries:
            if entry is not winner:entry[2]['reasons'].append('duplicate')
        _,row,d=winner;reasons=d['reasons']
        n=number(row.get('asking_price',''))
        if n is None or n != n.quantize(Decimal('.01')):reasons.append('invalid_price');continue
        if d['currency'] not in POLICY['currencies']:reasons.append('currency');continue
        d['price']=money(n)
        if row.get('detail_status') in {'conflicting_isbns','conflicting_bindings'}:
            reasons.append('metadata_conflict');continue
        # Sample ISBN fields belong to the search target, never the returned listing.
        actual_isbn=isbn(row.get('listing_isbn13') or row.get('listing_isbn10',''))
        if target_isbn and actual_isbn and target_isbn!=actual_isbn:
            reasons.append('isbn_mismatch');continue
        content=' '.join(row.get(k,'') for k in ('listing_title','condition','listing_condition_description','listing_edition'))
        if re.search(r'\b(ebook|e-book|audiobook|kindle|pdf|signed|inscribed|bundle)\b|\b(?:lot|set) of \d|\b\d+[ -]volume set',content,re.I):
            reasons.append('special_copy');continue
        title_match=overlap(book.get('title',''),row.get('listing_title',''))>=.8
        author_match=overlap(book.get('author',''),row.get('listing_author',''))>=.5
        if not ((actual_isbn and actual_isbn==target_isbn) or (title_match and author_match)):
            reasons.append('weak_match');continue
        target_binding=binding(book.get('target_binding',''))
        actual_binding=binding(row.get('listing_binding','') or row.get('condition',''))
        if target_binding and actual_binding and target_binding!=actual_binding:
            reasons.append('binding_mismatch');continue
        target_condition=book.get('target_condition','').strip().lower()
        actual_condition=row.get('listing_condition_grade','').strip().lower()
        if target_condition and actual_condition and target_condition!=actual_condition:
            reasons.append('condition_mismatch');continue
        edition_verified=bool(target_isbn and actual_isbn==target_isbn and target_binding and target_binding==actual_binding)
        condition_verified=bool(target_condition and actual_condition==target_condition)
        if not edition_verified:reasons.append('unverified_edition')
        if not condition_verified:reasons.append('unverified_condition')
        d['verified']=edition_verified and condition_verified
        d['disposition']='verified_comparable' if d['verified'] else 'candidate_only'
    sources={}
    for source in sorted({d['source'] for d in decisions}):
        ds=[d for d in decisions if d['source']==source]
        candidates=[d for d in ds if d['disposition'] in {'candidate_only','verified_comparable'}]
        verified=[d for d in ds if d['disposition']=='verified_comparable']
        ranges=_range(verified)
        eligible={c:r for c,r in ranges.items() if r['count']>=POLICY['minimum_comparables'] and not r['high_spread']}
        sources[source]=dict(candidate_ranges=_range(candidates),verified_ranges=ranges,eligible_ranges=eligible,
                             reasons=dict(Counter(x for d in ds for x in d['reasons'])))
    eligible=[(s,c,r) for s,v in sources.items() for c,r in v['eligible_ranges'].items()]
    proposal=None;status='needs_research'
    if book.get('reviewed_estimate_id'):
        status='manual_review_protected'
    elif eligible:
        currencies={c for _,c,_ in eligible}
        if len(currencies)>1:status='currency_review'
        elif len(eligible)>1 and max(Decimal(r['low']) for _,_,r in eligible)>min(Decimal(r['high']) for _,_,r in eligible):
            status='source_disagreement'
        else:
            # Choose the better supported source, not a union of incompatible evidence.
            s,c,r=sorted(eligible,key=lambda x:(-x[2]['count'],x[0]))[0]
            proposal=dict(source=s,currency=c,low=r['low'],high=r['high'],per_copy=True)
            status='proposed_for_review'
    reasons_seen={reason for d in decisions for reason in d['reasons']}
    steps=[]
    if not decisions:steps.append('Collect listing-level evidence; a saved summary alone cannot verify comparable copies.')
    if 'stale' in reasons_seen:steps.append('Refresh the dated asking-price observations before proposing a current range.')
    if reasons_seen & {'weak_match','unverified_edition','isbn_mismatch','binding_mismatch'}:
        steps.append('Obtain the returned listing ISBN and binding; compare with the target edition rather than trusting the search query.')
    if reasons_seen & {'unverified_condition','condition_mismatch'}:
        steps.append('Establish the target condition and a comparable listing condition; keep uncertain copies for review.')
    if status=='source_disagreement':steps.append('Review the source disagreement before selecting a range.')
    if status=='currency_review':steps.append('Choose a comparison currency; do not combine or convert amounts implicitly.')
    if status=='manual_review_protected':steps.append('Compare with the saved manual review and obtain an explicit decision before replacement.')
    if not proposal and not steps:steps.append('Gather at least three distinct verified comparable listings in one currency with a defensible price spread.')
    return dict(catalog_item_id=book['catalog_item_id'],title=book.get('title',''),as_of=as_of.isoformat(),
                status=status,proposal=proposal,sources=sources,decisions=decisions,next_steps=steps,publishable=False)


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def replay(pilot_path, observation_paths, output_dir, *, as_of, historical_as_of):
    """Write a new private artifact directory; refuse reuse or input overlap."""
    as_of=date.fromisoformat(as_of);historical=date.fromisoformat(historical_as_of)
    if historical>as_of:raise ValueError('Historical replay date cannot exceed current date')
    pilot_path=Path(pilot_path).resolve();observation_paths=[Path(p).resolve() for p in observation_paths]
    output_dir=Path(output_dir).resolve()
    if output_dir.exists():raise ValueError('Use a new output directory; replay never overwrites prior runs')
    if 'data' in output_dir.parts:raise ValueError('Replay output cannot be a data repository')
    inputs=[pilot_path,*observation_paths]
    pilot=read_csv(pilot_path)
    ids=[r['catalog_item_id'] for r in pilot]
    if not ids or len(ids)!=len(set(ids)):raise ValueError('Pilot must have unique catalog identities')
    fingerprint=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    hashes={str(p):fingerprint(p) for p in inputs}
    observations=defaultdict(list)
    for path in observation_paths:
        for row in read_csv(path):
            cid=row.get('catalog_id') or row.get('catalog_item_id')
            if cid in ids:observations[cid].append(row)
    from valuation.market_evidence_summary import aggregate_market_evidence
    results=[]
    for book in pilot:
        rows=observations[book['catalog_item_id']]
        old=aggregate_market_evidence(rows,generated_at=as_of.isoformat()+'T00:00:00Z') if rows else []
        results.append(dict(book=book,legacy_replay=old[0] if old else None,
                            current=review_book(book,rows,as_of=as_of),
                            historical=review_book(book,rows,as_of=historical)))
    assert all(fingerprint(p)==h for p,h in ((Path(k),v) for k,v in hashes.items()))
    report=dict(model_version=VERSION,policy=POLICY,as_of=as_of.isoformat(),historical_as_of=historical.isoformat(),
                input_hashes=hashes,pilot_count=len(pilot),results=results,
                current_status_counts=dict(Counter(r['current']['status'] for r in results)),
                historical_status_counts=dict(Counter(r['historical']['status'] for r in results)),
                reason_descriptions=REASONS,publication='disabled')
    output_dir.mkdir(parents=True,mode=0o700)
    def save(name,value):
        p=output_dir/name;p.write_text(value,encoding='utf-8');p.chmod(0o600)
    save('replay.json',json.dumps(report,indent=2,sort_keys=True)+'\n')
    comparison=[]
    for r in results:
        b=r['book'];legacy=r['legacy_replay'] or {}
        comparison.append(dict(catalog_item_id=b['catalog_item_id'],title=b['title'],group=b.get('group',''),
                               saved_low=b.get('previous_low',''),saved_high=b.get('previous_high',''),saved_currency=b.get('currency',''),
                               legacy_replayed_low=legacy.get('likely_low',''),legacy_replayed_high=legacy.get('likely_high',''),
                               historical_status=r['historical']['status'],current_status=r['current']['status'],
                               historical_candidate_ranges=json.dumps({s:v['candidate_ranges'] for s,v in r['historical']['sources'].items()},sort_keys=True),
                               current_reasons=json.dumps({s:v['reasons'] for s,v in r['current']['sources'].items()},sort_keys=True)))
    p=output_dir/'comparison.csv'
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(comparison[0]));w.writeheader()
        for row in comparison:w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()})
    p.chmod(0o600)
    parts=['<!doctype html><meta charset="utf-8"><title>Offline valuation pilot</title><style>body{font:17px system-ui;max-width:1100px;margin:40px auto;padding:20px;color:#243c33}article{border-top:1px solid #ccc;padding:20px 0}pre{white-space:pre-wrap}h2{font-size:22px}p{line-height:1.5}</style><h1>Offline valuation pilot</h1><p>Preview only. No live requests or Library values changed. Candidate asking ranges below are diagnostic and cannot be published. No pilot price changes are extrapolated to the whole library.</p>']
    parts.append('<p>Current replay: '+html.escape(as_of.isoformat())+'; historical comparison: '+html.escape(historical.isoformat())+'. Maximum observation age: 30 days.</p>')
    for r in results:
        b=r['book'];parts.append('<article><h2>'+html.escape(b['title'])+'</h2><p>'+html.escape(b['catalog_item_id']+' · '+b.get('group',''))+'</p>')
        saved=' '.join(filter(None,[b.get('currency',''),b.get('previous_low',''),'to' if b.get('previous_high') else '',b.get('previous_high','')]))
        parts.append('<p>Saved range: '+html.escape(saved or 'Not recorded')+'</p>')
        for mode,label in [('current','Current evidence check'),('historical','Historical diagnostic replay')]:
            view=r[mode];parts.append('<h3>'+label+'</h3><p>'+html.escape(view['status'].replace('_',' '))+'</p>')
            for source,values in view['sources'].items():
                parts.append('<p><b>'+html.escape(source)+'</b></p>')
                for c,rr in values['candidate_ranges'].items():parts.append('<p>Candidate asking prices: '+html.escape(f"{c} {rr['low']}–{rr['high']} ({rr['count']} distinct listings; identity/condition checks may remain)")+'</p>')
                parts.append('<ul>'+''.join('<li>'+html.escape(REASONS[k])+f' ({n})</li>' for k,n in sorted(values['reasons'].items()))+'</ul>')
            if not view['sources']:parts.append('<p>No raw observations were supplied for this record. A saved summary is not a substitute for listing evidence.</p>')
        steps=list(dict.fromkeys(r['current']['next_steps']+r['historical']['next_steps']))
        parts.append('<h3>Next steps</h3><ul>'+''.join('<li>'+html.escape(step)+'</li>' for step in steps)+'</ul>')
        parts.append('</article>')
    save('review.html',''.join(parts))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot',type=Path,required=True);p.add_argument('--observations',type=Path,nargs='+',required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--as-of',required=True);p.add_argument('--historical-as-of',required=True)
    a=p.parse_args();r=replay(a.pilot,a.observations,a.output_dir,as_of=a.as_of,historical_as_of=a.historical_as_of)
    print(json.dumps(dict(pilot_count=r['pilot_count'],current_status_counts=r['current_status_counts'],historical_status_counts=r['historical_status_counts'],publication=r['publication']),indent=2))
