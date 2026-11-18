import pytest
from valuation import family_requests, family_owner, owner_picks

@pytest.fixture
def setup(tmp_path):
    db=family_requests.connect(tmp_path/'requests.sqlite')
    facts={'r':dict(catalog_item_id='B',title='Example',author='Author',copies=[dict(id='H:1',label='1 · copy 1',location='1')])}
    yield db,facts
    db.close()

def body(purpose='self',key='k'):
    return dict(purpose=purpose,email='guest@example.test',items=[dict(catalog_item_id='B',slot='H:1')],message='Pickup note',key=key)

def test_self_pick_reserves_and_idempotent_retry(setup):
    db,facts=setup
    first=owner_picks.create(db,'owner@example.test',body(),facts,{'owner@example.test'})
    assert owner_picks.create(db,'owner@example.test',body(),facts,{'owner@example.test'})==first
    row=family_owner.inbox(db,facts)[0]
    assert row['email']=='owner@example.test'
    assert row['items'][0]['decision']['state']=='approved'
    assert row['items'][0]['decision']['slot']=='H:1'
    assert row['items'][0]['history'][0]['message']=='Pickup note'

def test_review_is_not_reserved_and_does_not_modify_guest_draft(setup):
    db,facts=setup
    owner_picks.create(db,'owner@example.test',body('review'),facts,{'owner@example.test'})
    assert family_owner.inbox(db,facts)[0]['items'][0]['decision']['slot'] is None
    assert family_requests.draft(db,'guest@example.test')['version']==0
    owner_picks.create(db,'owner@example.test',body('other','another'),facts,{'owner@example.test','guest@example.test'})
    assert len(family_requests.submissions(db))==2

def test_conflicts_and_inactive_recipient_leave_no_partial_submission(setup):
    db,facts=setup
    with pytest.raises(ValueError):owner_picks.create(db,'owner@example.test',body('other'),facts,{'owner@example.test'})
    owner_picks.create(db,'owner@example.test',body(),facts,{'owner@example.test'})
    with pytest.raises(family_requests.Conflict):owner_picks.create(db,'owner@example.test',body('review','second'),facts,{'owner@example.test'})
    assert len(family_requests.submissions(db))==1


def test_batch_conflict_is_atomic_and_changed_retry_rejected(setup):
    db,facts=setup
    facts['r2']=dict(catalog_item_id='B2',title='Second',author='Author',copies=[dict(id='H:2',label='2 · copy 1',location='2')])
    owner_picks.create(db,'owner@example.test',body(),facts,{'owner@example.test'})
    batch=body(key='batch')
    batch['items']=[dict(catalog_item_id='B2',slot='H:2'),dict(catalog_item_id='B',slot='H:1')]
    with pytest.raises(family_requests.Conflict):owner_picks.create(db,'owner@example.test',batch,facts,{'owner@example.test'})
    assert len(family_requests.submissions(db))==1
    assert db.execute("SELECT count(*) FROM request_decisions WHERE slot='H:2'").fetchone()[0]==0
    changed=body();changed['message']='Changed'
    with pytest.raises(family_requests.Conflict):owner_picks.create(db,'owner@example.test',changed,facts,{'owner@example.test'})


def test_multiple_copies_of_one_title_are_atomic_and_retry_safe(setup):
    db,facts=setup
    facts['r']['copies'].append(dict(id='H:2',label='2 · copy 1',location='2'))
    b=body();b['items'].append(dict(catalog_item_id='B',slot='H:2'))
    saved=owner_picks.create(db,'owner@example.test',b,facts,{'owner@example.test'})
    assert saved['count']==2
    assert owner_picks.create(db,'owner@example.test',b,facts,{'owner@example.test'})==saved
    decisions=[r['items'][0]['decision'] for r in family_owner.inbox(db,facts)]
    assert {d['slot'] for d in decisions}=={'H:1','H:2'}
    assert all(d['state']=='approved' for d in decisions)
    duplicate=body(key='duplicate');duplicate['items']*=2
    with pytest.raises(ValueError):owner_picks.create(db,'owner@example.test',duplicate,facts,{'owner@example.test'})
