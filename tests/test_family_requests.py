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
 assert s.draft(db,'a')==dict(version=2,books=[],message='')
 s.save(db,'a',2,[],'changed',C)
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
 assert s.draft(backup,'a')['books']==[] and len(s.submissions(backup,'a'))==1
 backup.close();again=s.connect(path);assert len(s.submissions(again))==1;again.close()


def test_retry_does_not_clear_new_choices_and_stale_tab_cannot_resubmit(db):
 s.save(db,'a',0,['ref'],'first message',C)
 first=s.submit(db,'a',1,'first-key',C,'hash')
 assert s.draft(db,'a')['message']==''
 with pytest.raises(s.Conflict):s.save(db,'a',1,['ref'],'old tab',C)
 s.save(db,'a',2,['ref'],'second message',C)
 assert s.submit(db,'a',1,'first-key',C,'hash')==first
 assert s.draft(db,'a')==dict(version=3,books=['ref'],message='second message')
 second=s.submit(db,'a',3,'second-key',C,'hash')
 assert second['id']!=first['id']
 assert len(s.submissions(db,'a'))==2
 assert s.draft(db,'a')==dict(version=4,books=[],message='')

def test_failed_submission_keeps_draft(db):
 s.save(db,'a',0,['ref'],'keep this',C)
 with pytest.raises(ValueError):s.submit(db,'a',1,'key',{},'hash')
 assert s.draft(db,'a')==dict(version=1,books=['ref'],message='keep this')
 assert s.submissions(db,'a')==[]


def test_remove_unavailable_books_incrementally_without_losing_other_choices(db):
 catalog={r:dict(reference=r,title=r,author='Author') for r in ['reserved-one','reserved-two','available']}
 s.save(db,'nate',0,list(catalog),'Keep these notes',catalog)
 current={'available':catalog['available']}
 # A draft may retain old unavailable choices while its owner removes them one at a time.
 d=s.save(db,'nate',1,['reserved-two','available'],'Keep these notes',current)
 assert d['books']==['reserved-two','available']
 with pytest.raises(ValueError):s.submit(db,'nate',2,'blocked',current,'snapshot')
 assert s.draft(db,'nate')['books']==['reserved-two','available']
 with pytest.raises(ValueError):s.save(db,'nate',2,['reserved-two','available','invented'],'',current)
 d=s.save(db,'nate',2,['available'],'Keep these notes',current)
 result=s.submit(db,'nate',d['version'],'remaining',current,'snapshot')
 assert result['payload']['message']=='Keep these notes'
 assert [b['reference'] for b in result['payload']['books']]==['available']
 assert s.draft(db,'nate')['books']==[]
