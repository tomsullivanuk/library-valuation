"""Read-only edition and seller-overlap review of frozen price discrepancies.

Listing references are not assumed to be independent sellers or confirmed sales.
No range, catalog identity, physical grade or owner decision is written here.
"""
from collections import Counter, defaultdict
from datetime import date
import re
import unicodedata
from valuation.offline_valuation_review import isbn, volume_numbers
from valuation.remaining_market_research import reviewed_page
from valuation.market_flag_adjudication import fields, binding


def seller_family(name, page=''):
    normalized=re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower())
    # Public listing names explicitly identify this former-name relationship.
    # Better World Books is a different retailer and must never join this family.
    if normalized.startswith(('worldofbooks','secondsale')):return 'world-of-books-former-secondsale'
    return normalized or ('store:'+page if page else '')


def audit_book(book, baseline, pages, as_of):
    target=isbn(book['isbn13'] or book['isbn10'])
    old=[];context=[]
    for receipt,roles in pages:
        f=fields(receipt);actual=isbn(f.get('ISBN 13') or f.get('ISBN 10'))
        fact=dict(url=receipt['url'],observed_at=receipt['observed_at'],isbn=actual,
                  title=f.get('Title',''),year=f.get('Publication year',''),edition=f.get('Edition',''),binding=binding(f.get('Binding','')),isbn10=f.get('ISBN 10','').replace('-','').strip(),
                  seller_family=seller_family(receipt.get('seller_name',''),receipt.get('seller_page','')),
                  inventory_reference=receipt.get('inventory_reference','').strip(),
                  unavailable=receipt.get('unavailable',False))
        wanted,actual_volumes=volume_numbers(book['title']),volume_numbers(fact['title'])
        fact['volume_conflict']=bool(wanted and actual_volumes and wanted.isdisjoint(actual_volumes))
        fact['same_isbn_year_difference']=bool(target and actual==target and re.fullmatch(r'\d{4}',book.get('publication_year','')) and re.fullmatch(r'\d{4}',fact['year']) and book['publication_year']!=fact['year'])
        if 'saved_baseline' in roles:
            fact['match']='same_isbn' if target and actual==target else 'different_isbn' if target and actual else 'not_established'
            old.append(fact)
        if any(role!='saved_baseline' for role in roles):
            offer=reviewed_page(receipt,target,book['title'],as_of)
            context.append(dict(fact,offer=offer))
    candidates=[o for o in context if o['offer']['eligible'] and o['offer']['grade']!='new']
    providers=defaultdict(list);stock=defaultdict(list)
    for o in candidates:
        v=o['offer'];key=(v['isbn'],v['binding'],v['grade'],v['currency'])
        if o['seller_family']:providers[key+(o['seller_family'],)].append(o)
        # ISBN alone is a product identifier, not copy/stock identity evidence.
        ref=o['inventory_reference']
        if ref and ref not in {v['isbn'],book['isbn10'],book['isbn13'],'N/A','n/a','-'}:
            stock[key+(ref.casefold(),)].append(o)
    provider_overlap=[g for g in providers.values() if len(g)>1]
    shared_inventory=[g for g in stock.values() if len(g)>1]
    old_providers=defaultdict(list);old_stock=defaultdict(list)
    for o in old:
        if not o['isbn'] or not o['binding']:continue
        if o['seller_family']:old_providers[(o['isbn'],o['binding'],o['seller_family'])].append(o)
        ref=o['inventory_reference']
        if ref and ref not in {o['isbn'],o['isbn10'],'N/A','n/a','-'}:
            old_stock[(o['isbn'],o['binding'],ref.casefold())].append(o)
    baseline_provider_overlap=[g for g in old_providers.values() if len(g)>1]
    baseline_shared_inventory=[g for g in old_stock.values() if len(g)>1]
    mismatch=[o for o in old if o['match']=='different_isbn']
    unknown=[o for o in old if o['match']=='not_established']
    return dict(catalog_item_id=book['catalog_item_id'],target_isbn=target,
        baseline_summary_verified=baseline.get('summary_range_verified',False),
        baseline_links_available=bool(baseline['rows']),baseline_pages=old,
        baseline_different_isbn=len(mismatch),baseline_same_isbn=sum(o['match']=='same_isbn' for o in old),
        baseline_identity_unverified=len(unknown),market_context=context,
        volume_conflict_pages=[o for o in old+context if o['volume_conflict']],
        same_isbn_year_difference_pages=[o for o in old+context if o['same_isbn_year_difference']],
        comparable_available_used_pages=len(candidates),
        identified_retailer_families=len({o['seller_family'] for o in candidates if o['seller_family']}),
        seller_identity_missing=sum(not o['seller_family'] for o in candidates),
        provider_overlap_groups=provider_overlap,shared_inventory_groups=shared_inventory,
        baseline_provider_overlap_groups=baseline_provider_overlap,baseline_shared_inventory_groups=baseline_shared_inventory,
        ebay_seller_independence='Not established: seller identities were not retained in the earlier normalized export; this audit does not verify cross-marketplace independence.',
        completed_sales='No completed-sale evidence verified in this retained-listing audit.',
        saved_values_changed=0,publishable=False)


def history_summary(book, review, manifest_row, has_owner_check=False, reviewed_on=''):
    known=[f'The saved range is {book["estimated_value_currency"]} {book["estimated_value_precise_low"]}–{book["estimated_value_precise_high"]}. It is unchanged. A large conditional comparison difference is a review flag, not measured appreciation or a confirmed sale value.']
    if review['target_isbn']:known.append('The recorded edition identifier is ISBN '+review['target_isbn']+'. Listing matches below do not assign a physical condition grade to your copy.')
    else:known.append('No valid ISBN is established for this recorded copy; publication-profile matching remains necessary without inventing an identifier.')
    if review['baseline_summary_verified']:known.append('The saved amount is reproduced by the retained earlier market summary, including its original range/midpoint rule.')
    n=len(review['baseline_pages']);m=review['baseline_different_isbn'];u=review['baseline_identity_unverified'];same=review['baseline_same_isbn']
    if not review['baseline_links_available']:
        known.append('The earlier summary is retained, but its individual source rows were not recovered from the available observation export. No edition-mismatch conclusion is inferred from that gap.')
    elif m:
        variants=sorted({p['isbn'] for p in review['baseline_pages'] if p['match']=='different_isbn'})
        known.append(f'Of {n} retained older listing references checked, {m} now identify a different ISBN ({", ".join(variants)}), {same} match the recorded ISBN and {u} leave the identifier unverified. Current metadata does not prove what the pages displayed when the old estimate was collected.')
    else:
        known.append(f'The {n} retained older listing references yielded {same} same-ISBN matches and {u} unverified identifiers. No different-ISBN mismatch was established in these pages; this does not verify historical metadata or matching printings.')
    if review['baseline_provider_overlap_groups'] or review['baseline_shared_inventory_groups']:
        known.append('Some earlier baseline pages also currently repeat a retailer family or stock reference within the same ISBN and binding. This qualifies their apparent independence; current seller metadata does not prove who supplied the listings when the old range was collected.')
    known.append(f'The current retained AbeBooks comparison/context references include {review["comparable_available_used_pages"]} available, edition/binding/label-matched used pages across {review["identified_retailer_families"]} identified retailer families. Conditions and currencies remain separate; these totals are not a pooled value range.')
    if review['provider_overlap_groups']:
        known.append('Some comparable offers repeat the same identified retailer family within the same edition, binding, seller-label and currency group. Multiple URLs are not independent seller confirmations.')
    if review['shared_inventory_groups']:
        known.append('Some comparable offers also share a seller inventory reference. This is evidence of possible stock/listing overlap, not proof that separate physical copies do not exist.')
    if not review['provider_overlap_groups'] and not review['shared_inventory_groups']:
        known.append('No repeated-retailer or shared-inventory overlap was detected within the checked comparable AbeBooks groups. This is a limited negative finding, not proof that every marketplace offer is independent.')
    unknown=[]
    if m:unknown.append('The earlier baseline includes currently different-edition pages; do not rely on it as a verified same-edition resale valuation or interpret the difference as a proven price increase.')
    if u or not review['baseline_links_available']:unknown.append('Some baseline edition attribution remains unverified. A provenance gap is not itself an edition mismatch.')
    if review['volume_conflict_pages']:unknown.append('Some listing titles explicitly identify a different volume. Those references cannot establish a comparable value for this volume even if a listing repeats the target ISBN.')
    if review['same_isbn_year_difference_pages']:unknown.append('Some same-ISBN pages report a different publication year from the catalog. This can reflect printing differences or metadata errors; it is flagged for review, not automatically declared a different edition.')
    unknown.extend([review['ebay_seller_independence'],review['completed_sales'], 'Your copy’s condition and likely sale proceeds have not been established. New-copy context, unavailable items and excluded editions are not active used-copy comparables.'])
    if review['provider_overlap_groups'] or review['shared_inventory_groups'] or review['baseline_provider_overlap_groups'] or review['baseline_shared_inventory_groups']:
        headline='Some checked pages repeat retailer or stock information; the apparent price difference remains unverified.'
    elif m:headline='Older comparison pages identify other editions; the saved-to-proposed difference is not a verified price change.'
    elif not review['baseline_links_available']:headline='Saved-range provenance is incomplete; the newer comparison remains unapproved.'
    else:headline='The large difference remains conditional; checked metadata alone does not establish a resale value.'
    next_step='No additional physical inspection is requested by this audit. Before relying on either range for a sale, the assistant would need stronger independent, available same-edition offers or verified completed sales, then an explicitly reviewed replacement range. Existing comparisons are retained as provenance, not newly approved prices. This bounded retained-listing audit is complete; no further search is scheduled.'
    if has_owner_check:next_step+=' A separate physical check already exists in Action Items; if it is still open, answer only that recorded question when convenient. This audit creates no duplicate check.'
    sources=[];seen=set()
    for label,rows in [('Earlier baseline page',review['baseline_pages']),('Retained comparison/context page',review['market_context'])]:
        for p in rows:
            if p['url'] in seen:continue
            seen.add(p['url']);sources.append(dict(label=label+' — checked '+p['observed_at'][:10],url=p['url']))
    return dict(reviewed_on=reviewed_on,headline=headline,what_we_know=known,
        what_is_uncertain=unknown,next_step=next_step,sources=sources,presentation_only=True,
        comparison_note='Earlier conditional ranges are retained below for provenance only. The edition and seller-overlap review above qualifies their interpretation; it does not apply or endorse a new value.')


def build(scope, books, baselines, plan, receipts, as_of):
    if len(scope)!=len(set(scope)) or set(scope)!=set(books) or set(scope)!=set(baselines):raise ValueError('Scope coverage mismatch')
    by_url={r['url']:r for r in receipts}
    if {p['url'] for p in plan}-set(by_url):raise ValueError('Incomplete listing coverage')
    by_book=defaultdict(list)
    for p in plan:
        row=by_url[p['url']]
        if row.get('blocked') or row.get('error') or not row.get('details'):raise ValueError('Blocked or incomplete page metadata')
        roles=defaultdict(list)
        for b in p['books']:
            if b['catalog_item_id'] not in books:raise ValueError('Plan outside scope')
            roles[b['catalog_item_id']].append(b['role'])
        for cid,role in roles.items():by_book[cid].append((row,role))
    result=[audit_book(books[c],baselines[c],by_book[c],as_of) for c in scope]
    return dict(reviewed_on=as_of.isoformat(),books=result,summary=dict(records=len(result),
        books_with_different_isbn_baseline_pages=sum(bool(b['baseline_different_isbn']) for b in result),
        books_without_retained_baseline_links=sum(not b['baseline_links_available'] for b in result),
        books_with_provider_overlap=sum(bool(b['provider_overlap_groups']) for b in result),
        books_with_shared_inventory=sum(bool(b['shared_inventory_groups']) for b in result),
        books_with_baseline_provider_overlap=sum(bool(b['baseline_provider_overlap_groups']) for b in result),
        books_with_baseline_shared_inventory=sum(bool(b['baseline_shared_inventory_groups']) for b in result),
        books_with_any_provider_overlap=sum(bool(b['provider_overlap_groups'] or b['baseline_provider_overlap_groups']) for b in result),
        books_with_any_shared_inventory=sum(bool(b['shared_inventory_groups'] or b['baseline_shared_inventory_groups']) for b in result),
        books_with_volume_conflicts=sum(bool(b['volume_conflict_pages']) for b in result),
        books_with_same_isbn_year_differences=sum(bool(b['same_isbn_year_difference_pages']) for b in result),
        listing_pages=len(plan),saved_values_changed=0))
