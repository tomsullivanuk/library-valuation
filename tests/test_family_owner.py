from dataclasses import dataclass
from types import SimpleNamespace
import pytest
from valuation import family_owner as o,family_requests as r

@pytest.fixture
def setup(tmp_path):
 db=r.connect(tmp_path/'requests.sqlite');o.schema(db)
 catalog={'ref':dict(reference='ref',title='Book',author='Author')}
 facts={'ref':dict(catalog_item_id='book',title='Book',author='Author',value='$20',location='1',copies=[dict(id='hold:1',holding_id='hold',unit=1,location='1',label='1 · copy 1 of 2'),dict(id='hold:2',holding_id='hold',unit=2,location='1',label='1 · copy 2 of 2')])}
 ids=[]
 for email in ('one','two','three'):
  r.save(db,email,0,['ref'],'',catalog);ids.append(r.submit(db,email,1,'k',catalog,'hash')['id'])
 yield db,catalog,facts,ids
 db.close()

def action(id,state,version=0,slot=None):return dict(submission=id,reference='ref',state=state,version=version,slot=slot)

def test_correct_test_transfer_restores_copy_and_retains_audit(setup):
 import json
 db,c,f,ids=setup
 o.update(db,'owner',action(ids[0],'approved',slot='hold:1'),f)
 o.update(db,'owner',dict(action(ids[0],'transferred',1),transfer_kind='sale',sale_amount='35'),f)
 body=dict(action(ids[0],'pending',2),correct_transfer=True,correction_reason='Test only; copy still present')
 with pytest.raises(ValueError):o.update(db,'owner',dict(body,correction_reason=' '),f)
 with pytest.raises(r.Conflict):o.update(db,'owner',dict(body,version=1),f)
 d=o.update(db,'owner',body,f)
 assert d['state']=='pending' and d['slot'] is None and d['transfer'] is None
 event=json.loads(db.execute('SELECT payload FROM request_events ORDER BY id DESC').fetchone()[0])
 assert event['before']['transfer']['amount']=='35.00'
 assert event['before']['slot']=='hold:1' and event['correction_reason']==body['correction_reason']
 assert next(row for row in o.inbox(db,f) if row['id']==ids[0])['items'][0]['history'][-1]['correction_reason']==body['correction_reason']
 o.update(db,'owner',action(ids[1],'approved',slot='hold:1'),f)
 # The original request can later be genuinely transferred without a stale-row conflict.
 o.update(db,'owner',action(ids[0],'approved',3,slot='hold:2'),f)
 o.update(db,'owner',dict(action(ids[0],'transferred',4),transfer_kind='gift'),f)
 assert o.decision(db,ids[0],'ref')['transfer']['kind']=='gift'

def test_correction_requires_a_recorded_transfer_and_original_copy(setup):
 db,c,f,ids=setup
 body=dict(action(ids[0],'pending'),correct_transfer=True,correction_reason='Test')
 with pytest.raises(ValueError):o.update(db,'owner',body,f)
 o.update(db,'owner',action(ids[0],'approved',slot='hold:1'),f)
 o.update(db,'owner',action(ids[0],'collected',1),f)
 with pytest.raises(r.Conflict):o.update(db,'owner',dict(body,version=2),{})
 assert o.decision(db,ids[0],'ref')['state']=='collected'

def test_reservation_overlap_release_and_collection(setup):
 db,c,f,ids=setup
 assert len(o.inbox(db,f)[0]['items'][0]['other_requesters'])==2
 o.update(db,'owner',action(ids[0],'approved',slot='hold:1'),f)
 with pytest.raises(r.Conflict):o.update(db,'owner',action(ids[1],'approved',slot='hold:1'),f)
 o.update(db,'owner',action(ids[1],'approved',slot='hold:2'),f)
 assert o.available(db,c,f)=={}
 o.update(db,'owner',action(ids[1],'pending',1),f)
 assert 'ref' in o.available(db,c,f)
 o.update(db,'owner',action(ids[0],'collected',1),f)
 with pytest.raises(r.Conflict):o.update(db,'owner',action(ids[0],'declined',2),f)
 assert db.execute('SELECT count(*) FROM request_events').fetchone()[0]==4

def test_invalid_stale_or_unrelated_mutations(setup):
 db,c,f,ids=setup
 with pytest.raises(ValueError):o.update(db,'owner',action(ids[0],'collected'),f)
 with pytest.raises(r.Conflict):o.update(db,'owner',action(ids[0],'approved',slot='invented'),f)
 with pytest.raises(ValueError):o.update(db,'owner',action('missing','pending'),f)
 o.update(db,'owner',action(ids[0],'declined'),f)
 with pytest.raises(r.Conflict):o.update(db,'owner',action(ids[0],'pending'),f)
 assert len(r.submissions(db))==3

@pytest.mark.parametrize('terminal',['collected','transferred'])
def test_collected_overlay_preserves_source_and_updates_current_counts(setup,terminal):
 from dataclasses import dataclass
 from valuation.completed_inventory import CompletedInventoryScope
 db,c,f,ids=setup
 for id,slot in zip(ids,['hold:1','hold:2']):
  o.update(db,'owner',action(id,'approved',slot=slot),f)
  o.update(db,'owner',dict(action(id,terminal,1),transfer_kind='gift'),f)
 @dataclass(frozen=True)
 class H:holding_id:str='hold';catalog_item_id:str='book';copies:str='2'
 @dataclass(frozen=True)
 class B:catalog_item_id:str='book';copy_count:int=2
 @dataclass(frozen=True)
 class M:holdings:tuple;books:tuple;completed_inventory:object
 model=M((H(),),(B(),),CompletedInventoryScope(completed=True,source_copies=2,catalog_item_ids=('book',),holding_ids=('hold',)))
 path=db.execute('PRAGMA database_list').fetchone()['file']
 result=o.collected_overlay(model,dict(database=path))
 assert model.holdings[0].copies=='2' and model.completed_inventory.source_copies==2
 assert result.books[0].copy_count==0 and result.completed_inventory.source_copies==0
 assert result.completed_inventory.catalog_item_ids==() and result.completed_inventory.holding_ids==()

def test_backup_preserves_allocations_and_history(setup,tmp_path):
 db,c,f,ids=setup
 o.update(db,'owner',action(ids[0],'approved',slot='hold:1'),f)
 backup=r.connect(tmp_path/'restored.sqlite');db.backup(backup)
 assert o.decision(backup,ids[0],'ref')['state']=='approved'
 assert backup.execute('SELECT count(*) FROM request_events').fetchone()[0]==1
 with pytest.raises(r.Conflict):o.update(backup,'owner',action(ids[1],'approved',slot='hold:1'),f)
 backup.close()

def test_inbox_history_is_ordered_and_scoped_to_requested_book(setup):
 db,c,f,ids=setup
 o.update(db,'owner',action(ids[0],'approved',slot='hold:1'),f)
 o.update(db,'owner',action(ids[0],'pending',1),f)
 rows={row['id']:row for row in o.inbox(db,f)}
 events=rows[ids[0]]['items'][0]['history']
 assert [e['state'] for e in events]==['approved','pending']
 assert all(e['actor']=='owner' and e['created'] for e in events)
 assert rows[ids[1]]['items'][0]['history']==[]

@pytest.mark.parametrize('kind,amount,expected',[('gift','',None),('sale','35','35.00'),('sale','',None),('sale','0','0.00')])
def test_transfer_preserves_history_and_removes_only_assigned_copy(setup,kind,amount,expected):
 db,c,f,ids=setup
 o.update(db,'owner',action(ids[0],'approved',slot='hold:1'),f)
 d=o.update(db,'owner',dict(action(ids[0],'transferred',1),transfer_kind=kind,sale_amount=amount),f)
 assert d['state']=='transferred' and d['slot']=='hold:1'
 assert d['transfer']['kind']==kind and d['transfer']['amount']==expected
 assert 'ref' in o.available(db,c,f)  # second physical copy remains available
 assert len(r.submissions(db))==3
 history=next(x for x in o.inbox(db,f) if x['id']==ids[0])['items'][0]['history']
 assert [e['state'] for e in history]==['approved','transferred']
 assert history[-1]['transfer']['currency']=='USD'
 with pytest.raises(r.Conflict):o.update(db,'owner',action(ids[0],'pending',2),f)
 with pytest.raises(r.Conflict):o.update(db,'owner',action(ids[1],'approved',slot='hold:1'),f)

@pytest.mark.parametrize('kind,amount',[('',None),('loan',None),('gift','1'),('sale','-1'),('sale','NaN'),('sale','Infinity'),('sale','1.234'),('sale','1000000000')])
def test_invalid_transfer_does_not_change_reservation(setup,kind,amount):
 db,c,f,ids=setup
 o.update(db,'owner',action(ids[0],'approved',slot='hold:1'),f)
 with pytest.raises(ValueError):o.update(db,'owner',dict(action(ids[0],'transferred',1),transfer_kind=kind,sale_amount=amount),f)
 assert o.decision(db,ids[0],'ref')['state']=='approved'
 assert db.execute('SELECT count(*) FROM request_transfers').fetchone()[0]==0
 assert db.execute('SELECT count(*) FROM request_events').fetchone()[0]==1

def test_transfer_requires_approval_and_survives_backup(setup,tmp_path):
 db,c,f,ids=setup
 with pytest.raises(ValueError):o.update(db,'owner',dict(action(ids[0],'transferred'),transfer_kind='gift'),f)
 o.update(db,'owner',action(ids[0],'approved',slot='hold:1'),f)
 o.update(db,'owner',dict(action(ids[0],'transferred',1),transfer_kind='sale',sale_amount='35'),f)
 restored=r.connect(tmp_path/'transfer-backup.sqlite');db.backup(restored)
 assert o.decision(restored,ids[0],'ref')['transfer']['amount']=='35.00'
 assert restored.execute('SELECT count(*) FROM request_events').fetchone()[0]==2
 restored.close()
