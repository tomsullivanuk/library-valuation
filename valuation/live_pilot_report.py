"""Private review report for bounded live observations; no publishing capability."""
from collections import Counter, defaultdict
from datetime import datetime,timezone
import argparse
import csv
import hashlib
import html
import json
from decimal import Decimal
from pathlib import Path
from valuation.offline_valuation_review import review_book, read_csv, listing_key, REASONS


def text(value):return html.escape(str(value))

def price(currency,low,high=None):
    if not low:return 'Not recorded'
    symbol={'USD':'$','GBP':'£','EUR':'€'}.get(currency,currency+' ')
    return symbol+low+('–'+symbol+high if high and high!=low else '')


def report(pilot,observations,checkpoint,output_dir,*,as_of):
    pilot,observations,checkpoint=map(Path,(pilot,observations,checkpoint))
    out=Path(output_dir)
    if out.exists():raise ValueError('Choose a new report directory; prior reviews are retained')
    if 'data' in out.resolve().parts:raise ValueError('Reports cannot be written into a data repository')
    books=read_csv(pilot);rows=read_csv(observations);state=json.loads(checkpoint.read_text())
    if hashlib.sha256(pilot.read_bytes()).hexdigest()!=state['manifest']['pilot_sha256']:
        raise ValueError('Pilot differs from the collected cohort')
    if [b['catalog_item_id'] for b in books]!=state['manifest']['catalog_ids']:
        raise ValueError('Cohort ordering differs')
    byid=defaultdict(list)
    for row in rows:byid[row['catalog_id']].append(row)
    views=[];flat=[]
    for b in books:
        rs=byid[b['catalog_item_id']];v=review_book(b,rs,as_of=as_of)
        views.append(dict(book=b,review=v))
        observed=[r for r in rs if r['lookup_status']=='observed']
        flat.append(dict(catalog_item_id=b['catalog_item_id'],title=b['title'],saved_low=b.get('previous_low',''),saved_high=b.get('previous_high',''),saved_currency=b.get('currency',''),returned_listings=len(observed),returned_isbn=sum(bool(r.get('listing_isbn13')) for r in observed),returned_binding=sum(bool(r.get('listing_binding')) for r in observed),returned_condition=sum(bool(r.get('listing_condition_grade')) for r in observed),review_status=v['status'],candidate_ranges=json.dumps({s:vv['candidate_ranges'] for s,vv in v['sources'].items()},sort_keys=True)))
    listings=[r for r in rows if r['lookup_status']=='observed']
    summary=dict(pilot_books=len(books),collection_status=state['status'],completed_books=sum(bool(b.get('completed')) for b in state['books'].values()),api_requests=state['request_count'],observations=len(rows),listing_details=len(listings),isbn_present=sum(bool(r.get('listing_isbn13')) for r in listings),binding_present=sum(bool(r.get('listing_binding')) for r in listings),condition_grade_present=sum(bool(r.get('listing_condition_grade')) for r in listings),books_with_results=sum(bool(byid[b['catalog_item_id']]) and any(r['lookup_status']=='observed' for r in byid[b['catalog_item_id']]) for b in books),books_with_candidates=sum(any(s['candidate_ranges'] for s in v['review']['sources'].values()) for v in views),verified_proposals=sum(v['review']['proposal'] is not None for v in views),as_of=as_of,publication='disabled',input_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (pilot,observations,checkpoint)})
    out.mkdir(parents=True,mode=0o700)
    def save(name,value):
        p=out/name;p.write_text(value,encoding='utf-8');p.chmod(0o600)
    save('summary.json',json.dumps(summary,indent=2)+'\n')
    save('review.json',json.dumps(dict(summary=summary,books=views),indent=2,sort_keys=True)+'\n')
    with (out/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader()
        for r in flat:w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in r.items()})
    (out/'comparison.csv').chmod(0o600)
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Live valuation pilot review</title><style>body{font:17px system-ui;color:#243c33;max-width:1200px;margin:32px auto;padding:20px}h1,h2{color:#215a45}p,li{line-height:1.5}details{border:1px solid #ccd6d0;padding:16px;border-radius:8px;margin:16px 0}summary{cursor:pointer;font-weight:bold}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #ddd}a{color:#215a45}.scroll{overflow-x:auto}.notice{background:#fff4d7;padding:16px}small{color:#506258}</style><h1>Live valuation pilot review</h1>']
    parts.append('<p class="notice">Review only. Existing Library estimates have not been replaced. Candidate asking-price ranges require review of edition, binding and condition; they are not appraisals or expected sale proceeds. Shipping is excluded.</p>')
    parts.append('<p>'+text(f"Collection: {summary['collection_status']}. {summary['completed_books']}/{len(books)} books completed; {len(listings)} listing details. Source: eBay US active fixed-price listings. Review date: {as_of}.")+'</p>')
    parts.append('<p>'+text(f"Returned listing ISBN: {summary['isbn_present']}/{len(listings)}; binding: {summary['binding_present']}/{len(listings)}; condition grade: {summary['condition_grade_present']}/{len(listings)}. Missing facts remain unknown.")+'</p>')
    parts.append('<p>Expand a book to compare its saved range with fresh candidate asking prices and inspect the listing facts. Target binding and physical condition have not been assumed from the sale listings.</p>')
    for view in views:
        b,v=view['book'],view['review'];rs=byid[b['catalog_item_id']]
        parts.append('<details><summary>'+text(b['title'])+'</summary><p>'+text(b.get('author',''))+'</p><p>Saved range: '+text(price(b.get('currency',''),b.get('previous_low',''),b.get('previous_high','')))+'</p>')
        parts.append('<p>Target ISBN: '+text(b.get('isbn13') or b.get('isbn10') or 'Not recorded')+'. Target binding and condition: '+text((b.get('target_binding') or 'unknown')+' / '+(b.get('target_condition') or 'unknown'))+'.</p>')
        for source,sv in v['sources'].items():
            for c,rr in sv['candidate_ranges'].items():
                parts.append('<p>Candidate asking prices: <b>'+text(price(c,rr['low'],rr['high']))+'</b> · '+text(str(rr['count'])+' distinct listings')+(' · Wide spread: review unusual prices.' if rr['high_spread'] else '')+'</p>')
            if not sv['candidate_ranges']:parts.append('<p>No sufficiently matched candidate prices from this source.</p>')
        accepted_keys={d['listing'] for d in v['decisions'] if d['disposition'] in {'candidate_only','verified_comparable'}}
        groups=defaultdict(list)
        for r in rs:
            if listing_key(r) in accepted_keys and r.get('asking_price'):
                groups[(r.get('listing_binding') or 'unknown format',r.get('listing_condition_grade') or 'unknown condition',r.get('currency',''))].append(Decimal(r['asking_price']))
        if groups:
            parts.append('<p>Candidate prices grouped by the seller-reported format and condition:</p><ul>')
            for (fmt,grade,currency),prices in sorted(groups.items()):
                label=fmt+' / '+grade.replace('_',' ')+': '+price(currency,format(min(prices),'.2f'),format(max(prices),'.2f'))+f' ({len(prices)} listings)'
                parts.append('<li>'+text(label)+'</li>')
            parts.append('</ul>')
        if not rs:parts.append('<p>This book has no recorded results yet.</p>')
        parts.append('<ul>'+''.join('<li>'+text(s)+'</li>' for s in v['next_steps'])+'</ul>')
        parts.append('<div class="scroll"><table><thead><tr><th>Listing</th><th>Asking price</th><th>Returned ISBN / binding</th><th>Condition</th><th>Review</th></tr></thead><tbody>')
        ds={d['listing']:d for d in v['decisions'] if d['listing']}
        for r in rs:
            if r['lookup_status']!='observed':
                parts.append('<tr><td colspan="5">'+text('Lookup/detail outcome: '+r.get('detail_status',r['lookup_status']))+'</td></tr>');continue
            d=ds.get(listing_key(r),{})
            label=text(r.get('listing_title',''))
            # Normalized URLs must remain eBay HTTPS links; never render arbitrary CSV URLs as links.
            from urllib.parse import urlsplit
            try:u=urlsplit(r.get('listing_url',''));valid=u.scheme=='https' and bool(u.hostname) and (u.hostname=='ebay.com' or u.hostname.endswith('.ebay.com')) and not u.username
            except ValueError:valid=False
            if valid:label='<a target="_blank" rel="noreferrer" href="'+text(r['listing_url'])+'">'+label+'</a>'
            notes='; '.join(REASONS.get(reason,reason) for reason in d.get('reasons',[])) or d.get('disposition','Needs review')
            parts.append('<tr><td>'+label+'<br><small>'+text(' / '.join(filter(None,[r.get('listing_author',''),r.get('listing_publisher',''),r.get('listing_year','')])))+'</small></td><td>'+text(price(r.get('currency',''),r.get('asking_price','')))+'</td><td>'+text((r.get('listing_isbns') or 'Unknown')+' / '+(r.get('listing_format_raw') or r.get('listing_binding') or 'Unknown'))+'</td><td>'+text(r.get('condition') or 'Unknown')+'<br><small>'+text(r.get('listing_condition_description',''))+'</small></td><td>'+text(notes)+'</td></tr>')
        parts.append('</tbody></table></div></details>')
    save('review.html',''.join(parts)+'</html>')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('pilot','observations','checkpoint','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--as-of',default=datetime.now(timezone.utc).date().isoformat())
    a=p.parse_args();print(json.dumps(report(a.pilot,a.observations,a.checkpoint,a.output_dir,as_of=a.as_of),indent=2))
