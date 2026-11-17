from copy import deepcopy
from datetime import date
import json
import pytest
from tests.test_market_flag_adjudication import receipt,ISBN
from tests.test_remaining_market_research import book
from tests.test_workspace_action_review import setup
from valuation.discrepancy_history_review import audit_book,build,history_summary,seller_family
from valuation.workspace_service import WorkspaceStore

DAY=date(2026,11,17)


def page(i,seller='World of Books Inc',stock='SKU-A',grade='Good',**changes):
    r=receipt(url=f'https://www.abebooks.com/example/{100+i}/bd',observed_at='2026-11-17T12:00:00Z')
    r['details']=r['details'].replace('Condition\nGood','Condition\n'+grade)
    r.update(seller_name=seller,seller_page='',inventory_reference=stock,unavailable=False)
    r.update(changes);return r


def baseline():return dict(rows=[dict(listing_url='retained')],summary_range_verified=True)


def test_edition_mismatch_and_provider_overlap_are_separate_findings():
    old=page(1);old['details']=old['details'].replace(ISBN,'9780715619032')
    pages=[(old,['saved_baseline']),(page(2),['conditional_comparison']),
        (page(3,seller='World of Books (was SecondSale)'),['retained_market_context'])]
    original=deepcopy(pages);r=audit_book(book(),baseline(),pages,DAY)
    assert r['baseline_different_isbn']==1 and len(r['provider_overlap_groups'])==1
    assert len(r['shared_inventory_groups'])==1 and r['identified_retailer_families']==1
    assert pages==original and not r['publishable']
    s=history_summary(book(),r,{},reviewed_on=DAY.isoformat())
    assert any('does not prove' in x for x in s['what_we_know'])
    assert s['presentation_only']
    assert 'no further search' in s['next_step']


def test_better_world_books_is_not_world_of_books_and_product_isbn_is_not_stock():
    assert seller_family('Better World Books')!=seller_family('World of Books Inc')
    rows=[(page(1,seller='Better World Books',stock=ISBN),['conditional_comparison']),
        (page(2,seller='World of Books Inc',stock=ISBN),['conditional_comparison'])]
    r=audit_book(book(),baseline(),rows,DAY)
    assert not r['provider_overlap_groups'] and not r['shared_inventory_groups']


def test_shared_stock_is_possible_overlap_and_condition_groups_stay_separate():
    rows=[(page(1,seller='Shop One'),['conditional_comparison']),
        (page(2,seller='Shop Two'),['conditional_comparison'])]
    r=audit_book(book(),baseline(),rows,DAY)
    assert not r['provider_overlap_groups'] and r['shared_inventory_groups']
    s=history_summary(book(),r,{},reviewed_on=DAY.isoformat())
    assert any('possible stock/listing overlap' in x for x in s['what_we_know'])
    rows[1]=(page(2,seller='Shop Two',grade='Very Good'),['conditional_comparison'])
    assert not audit_book(book(),baseline(),rows,DAY)['shared_inventory_groups']


def test_unavailable_context_and_missing_baseline_are_not_proof_of_mismatch():
    r=audit_book(book(),dict(rows=[],summary_range_verified=True),[(page(1,unavailable=True),['conditional_comparison'])],DAY)
    assert r['comparable_available_used_pages']==0 and not r['baseline_different_isbn']
    s=history_summary(book(),r,{},reviewed_on=DAY.isoformat())
    assert any('No edition-mismatch conclusion is inferred' in x for x in s['what_we_know'])


@pytest.mark.parametrize('bad',['missing','blocked','duplicate_scope'])
def test_incomplete_inputs_cannot_claim_full_coverage(bad):
    r=page(1);plan=[dict(url=r['url'],books=[dict(catalog_item_id='BK1',role='conditional_comparison')])]
    scope=['BK1'];rows=[r]
    if bad=='missing':rows=[]
    if bad=='blocked':r['blocked']=True
    if bad=='duplicate_scope':scope*=2
    with pytest.raises(ValueError):build(scope,{'BK1':book()},{'BK1':baseline()},plan,rows,DAY)


def test_presentation_note_preserves_completed_research_decision(tmp_path):
    model,m,path=setup(tmp_path,False);store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)
    task=next(t for t in store.actions if t['category']=='Estimate research')
    store.update(dict(kind='action',id=task['id'],fingerprint=task['fingerprint'],revision=0,status='complete',note='Prior finding'))
    m['books'][model.books[0].catalog_item_id]['history_summary']=dict(presentation_only=True,reviewed_on='2026-11-17',what_we_know=['Retained comparison checked.'],what_is_uncertain=['Seller independence not verified.'],next_step='No automatic search.',sources=[])
    path.write_text(json.dumps(m));data_before={str(p):p.read_bytes() for p in (tmp_path/'data').rglob('*') if p.is_file()}
    state=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model).snapshot();current=next(t for t in state['actions'] if t['id']==task['id'])
    assert current['fingerprint']==task['fingerprint'] and current['status']=='complete' and current['note']=='Prior finding'
    assert data_before=={str(p):p.read_bytes() for p in (tmp_path/'data').rglob('*') if p.is_file()}


def test_volume_conflicts_and_same_isbn_year_variation_are_not_conflated():
    b=book();b.update(title='Example Volume 1',publication_year='2020')
    r=page(1);r['details']=r['details'].replace('Title\nExample','Title\nExample Volume 2').replace('Publication year\n2020','Publication year\n1999')
    result=audit_book(b,baseline(),[(r,['saved_baseline'])],DAY)
    assert result['volume_conflict_pages'] and result['same_isbn_year_difference_pages']
    assert result['baseline_different_isbn']==0
    s=history_summary(b,result,{},reviewed_on=DAY.isoformat())
    assert any('different volume' in v for v in s['what_is_uncertain'])
    assert any('not automatically declared a different edition' in v for v in s['what_is_uncertain'])


def test_older_baseline_provider_repetition_is_reported_without_historical_proof():
    rows=[(page(1),['saved_baseline']),(page(2),['saved_baseline'])]
    r=audit_book(book(),baseline(),rows,DAY)
    assert r['baseline_provider_overlap_groups'] and r['baseline_shared_inventory_groups']
    assert not r['provider_overlap_groups'] and not r['shared_inventory_groups']
    s=history_summary(book(),r,{},reviewed_on=DAY.isoformat())
    assert any('does not prove who supplied' in line for line in s['what_we_know'])
