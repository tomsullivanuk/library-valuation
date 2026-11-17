from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import pytest
from valuation.research_history import project,summary
from tests.test_workspace_action_review import setup
from valuation.workspace_service import WorkspaceStore


def book(**changes):
    fields=dict(usable_market_estimate=True,resale_market_summary='USD 10–20',estimated_value_precise_low='10',
        estimated_value_precise_high='20',estimated_value_currency='USD',reviewed_estimate_id='',
        reviewed_estimate_date='',reviewed_estimate_note='',reviewed_estimate_sources=[])
    fields.update(changes);return SimpleNamespace(**fields)


def task(category,**changes):
    fields=dict(id='research:1',catalog_item_id='BK1',category=category,action='Recorded finding',
        reason='Two comparable used offers remain.',next_step='Find another matching used offer.',fingerprint='original',status='open')
    fields.update(changes);return fields


@pytest.mark.parametrize('category',['Proposed estimates','Estimate research','Retain current estimate','Resolved from records','Awaiting physical check','Optional research'])
def test_each_research_class_has_clear_structure_without_writes(category):
    t=task(category);b=book();before=deepcopy(t)
    result=project([t],{'BK1':b},'2026-11-16')[0]
    s=result['history_summary']
    assert s['what_we_know'] and s['what_is_uncertain'] and s['next_step'] and s['reviewed_on']=='2026-11-16'
    assert result['fingerprint']=='original' and t==before and b.estimated_value_precise_low=='10'


def test_containment_does_not_mix_currencies_or_hide_outside_scenarios():
    p=dict(low='12',high='18',currency='USD',binding='paperback',grade='good',source_urls=['https://example.test/offer'])
    t=task('Proposed estimates',proposals=[p])
    assert 'fit inside' in summary(t,book())['headline']
    assert 'fit inside' not in summary(t,book(estimated_value_currency='GBP'))['headline']
    assert 'fit inside' not in summary(dict(t,proposals=[p,dict(p,high='25')]),book())['headline']
    assert 'No immediate action' in summary(t,book())['next_step']


def test_physical_dependencies_reference_existing_question_only():
    check=task('Book checks',id='check:1',action='Read only the cover identifier.')
    s=summary(task('Awaiting physical check'),book(),[check])
    assert any(check['action'] in line for line in s['what_we_know'])
    assert 'existing linked question' in s['next_step'] and 'automatically' in s['next_step']
    result=project([check],{'BK1':book()})
    assert result==[check] and 'history_summary' not in result[0]


def test_manual_reviews_and_authored_findings_are_preserved():
    b=book(reviewed_estimate_id='EST-1',reviewed_estimate_date='2026-11-10',reviewed_estimate_note='My explicit basis',reviewed_estimate_sources=['https://example.test/saved'])
    s=summary(task('Proposed estimates'),b,reviewed_on='2026-11-16')
    assert s['reviewed_on']=='2026-11-10' and 'explicitly reviewed' in s['headline']
    authored=dict(reviewed_on='2026-11-01',what_we_know=['Specific retained fact'],what_is_uncertain=['Specific gap'],next_step='No action now',sources=[])
    t=task('Estimate research',history_summary=authored)
    assert project([t],{'BK1':book()},'2026-11-16')[0]['history_summary']==authored


def test_projection_preserves_answer_status_identity_and_all_data_files(tmp_path):
    model,m,path=setup(tmp_path,False);store=WorkspaceStore(tmp_path/'data',tmp_path/'output',model=model)
    research=next(t for t in store.actions if t['category']=='Estimate research')
    store.update(dict(kind='action',id=research['id'],fingerprint=research['fingerprint'],revision=0,status='complete',note='Preserved research finding'))
    before={str(p):p.read_bytes() for p in (tmp_path/'data').rglob('*') if p.is_file()}
    state=store.snapshot();current=next(t for t in state['actions'] if t['id']==research['id'])
    assert current['status']=='complete' and current['note']=='Preserved research finding'
    assert current['fingerprint']==research['fingerprint'] and current['history_summary']['what_we_know']
    assert before=={str(p):p.read_bytes() for p in (tmp_path/'data').rglob('*') if p.is_file()}
