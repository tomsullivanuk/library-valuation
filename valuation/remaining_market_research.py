"""Resolve a frozen research backlog from retained records and listing receipts.

This module writes only a private review packet. It never updates saved estimates,
physical condition, catalog identities or task decisions.
"""
from collections import Counter, defaultdict
from datetime import date
import re

from valuation.market_flag_adjudication import adjudicate, page_offer, working_groups
from valuation.offline_valuation_review import isbn, volume_numbers

# Preserve seller-native labels in their own groups, never map them to eBay grades.
NATIVE_LABELS={'fair','fine','near fine','as new','good+','good-','very good+',
               'very good-','very good condition','usedgood','gut','bon'}


def reviewed_page(receipt, target, title, as_of):
    offer=page_offer(receipt,target,as_of)
    if 'native_grade_kept_separate' in offer['issues'] and offer['native_grade'].lower() in NATIVE_LABELS:
        offer['grade']='AbeBooks label: '+offer['native_grade'].lower()
        offer['issues'].remove('native_grade_kept_separate')
    if receipt.get('unavailable') or re.search(r'specific item is no longer available|item is unavailable|item has been sold',receipt.get('price_context',''),re.I):
        offer['issues'].append('listing_no_longer_available')
    wanted,actual=volume_numbers(title),volume_numbers(offer['title'])
    if wanted and actual and wanted.isdisjoint(actual):offer['issues'].append('different_volume_in_listing_title')
    if re.search(r'original typescript|manuscript|proof copy|100 page summar',offer['title'],re.I):
        offer['issues'].append('special_copy_not_ordinary_comparable')
    offer['eligible']=not offer['issues']
    return offer


def resolve(book, detailed, receipts, as_of):
    base=adjudicate(book,{},detailed,[],[],as_of)
    offers=[o for o in base['offer_decisions'] if not o.get('hold')]
    # Re-run holds against the combined set; retain initial eBay exclusions.
    pages=[reviewed_page(r,isbn(book['isbn13'] or book['isbn10']),book['title'],as_of) for r in receipts]
    offers.extend(o for o in pages if o['eligible'])
    groups,decisions=working_groups(offers)
    supported=[g for g in groups if g['supported'] and detailed['identity_supported_from_records'] and not book['reviewed_estimate_id']]
    notes=detailed.get('recorded_source_notes',[])
    if book['reviewed_estimate_id']:outcome='saved_review_protected'
    elif supported:outcome='conditional_proposal'
    elif not detailed['identity_supported_from_records']:outcome='edition_profile_research'
    elif not groups:outcome='no_eligible_used_offers'
    elif max(g['offer_count'] for g in groups)<3:outcome='too_few_comparable_offers'
    else:outcome='prices_too_widely_spread'
    steps={
        'saved_review_protected':'Keep the saved manual review; no replacement is proposed automatically.',
        'conditional_proposal':'Review the conditional ranges when relevant; no range is saved automatically. Physical condition remains unassigned.',
        'edition_profile_research':'Use the preserved publisher, translation and printing notes to find the same edition. Do not substitute a later reprint or request an ISBN already documented as absent.',
        'no_eligible_used_offers':'Find used offers for this edition; new-copy prices, unavailable listings and mismatched editions remain context only.',
        'too_few_comparable_offers':'Find additional distinct offers in the same edition, binding, seller-label group and currency; the existing group has fewer than three.',
        'prices_too_widely_spread':'Investigate the specific remaining price spread and seek additional comparable listings; do not average incompatible scenarios.'}
    return dict(catalog_item_id=book['catalog_item_id'],outcome=outcome,
        identity_supported_from_records=detailed['identity_supported_from_records'],
        source_notes=notes,supported_groups=supported,all_groups=groups,
        offer_decisions=decisions,prior_held_context=[o for o in base['offer_decisions'] if o.get('hold')],abebooks_page_review=pages,
        research_next_step=steps[outcome],actual_condition='ungraded',publishable=False)


def build(scope, books, details, plan, receipts, as_of):
    if len(scope)!=len(set(scope)) or not set(scope)<=set(books):raise ValueError('Invalid frozen scope')
    latest={r['url']:r for r in receipts}
    if {p['url'] for p in plan}-set(latest):raise ValueError('Listing review incomplete')
    selected=[latest[p['url']] for p in plan]
    if any(r.get('blocked') or r.get('error') or not r.get('details') for r in selected):
        raise ValueError('Blocked or incomplete listing metadata')
    by_book=defaultdict(list)
    for p in plan:
        for b in p['books']:
            if b['catalog_item_id'] not in scope:raise ValueError('Plan outside frozen scope')
            by_book[b['catalog_item_id']].append(latest[p['url']])
    if set(scope)!=set(details):raise ValueError('Record-review coverage incomplete')
    rows=[resolve(books[c],details[c],by_book[c],as_of) for c in scope]
    return dict(as_of=as_of.isoformat(),books=rows,summary=dict(records=len(rows),
        outcomes=dict(Counter(r['outcome'] for r in rows)),listing_pages=len(selected),
        proposals=sum(bool(r['supported_groups']) for r in rows),saved_values_changed=0),
        policy=dict(minimum_offers=3,maximum_spread_exclusive=3,
                    native_seller_labels='Separate groups; no translation into eBay grades',
                    physical_grading='Deferred until handling; no grade assigned',publication=False))
