import json
import pytest
from valuation import family_requests as s

@pytest.fixture
def db(tmp_path):
 d=s.connect(tmp_path/'requests.sqlite');yield d;d.close()

C={'ref':dict(reference='ref',title='Book',author='Author')}

def test_isolation_persistence_and_immutable_revision(db):
 d=s.save(db,'a',0,['ref'],'message',C)
 assert s.draft(db,'b')['books']==[]
 r=s.submit(db,'a',1,'key',C,'hash')
 assert s.submit(db,'a',1,'key',C,'hash')==r
 assert s.submit(db,'a',1,'different-key-after-reload',C,'hash')==r
 s.save(db,'a',1,[],'changed',C)
 assert s.submissions(db,'a')[0]['payload']['books'][0]['title']=='Book'
 assert s.submissions(db,'b')==[]
 assert s.draft(db,'a')['message']=='changed'

def test_stale_missing_duplicate_and_empty(db):
 with pytest.raises(ValueError):s.save(db,'a',0,['ref','ref'],'',C)
 with pytest.raises(ValueError):s.save(db,'a',0,['missing'],'',C)
 with pytest.raises(ValueError):s.submit(db,'a',0,'k',C,'hash')
 s.save(db,'a',0,['ref'],'',C)
 with pytest.raises(s.Conflict):s.save(db,'a',0,[],'',C)
 with pytest.raises(s.Conflict):s.submit(db,'a',0,'k',C,'hash')
 with pytest.raises(ValueError):s.submit(db,'a',1,'k',{},'hash')

def test_reopen_and_sqlite_backup(tmp_path):
 path=tmp_path/'live.sqlite';db=s.connect(path);s.save(db,'a',0,['ref'],'',C);s.submit(db,'a',1,'k',C,'hash')
 backup=s.connect(tmp_path/'backup.sqlite');db.backup(backup);db.close()
 assert s.draft(backup,'a')['books']==['ref'] and len(s.submissions(backup,'a'))==1
 backup.close();again=s.connect(path);assert len(s.submissions(again))==1;again.close()
