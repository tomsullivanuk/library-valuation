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

def test_collected_overlay_preserves_source_and_updates_current_counts(setup):
 from dataclasses import dataclass
 from valuation.completed_inventory import CompletedInventoryScope
 db,c,f,ids=setup
 for id,slot in zip(ids,['hold:1','hold:2']):
  o.update(db,'owner',action(id,'approved',slot=slot),f)
  o.update(db,'owner',action(id,'collected',1),f)
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
