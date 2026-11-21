from contextlib import closing
import json,sqlite3
import pytest
from valuation import family_requests as r,family_owner as o,request_maintenance as m

def setup(tmp_path):
 c=dict(database=str(tmp_path/'db.sqlite'));db=r.connect(c['database']);o.schema(db)
 catalog={'ref':dict(reference='ref',title='Book',author='Author')}
 r.save(db,'test@example.org',0,['ref'],'test',catalog)
 s=r.submit(db,'test@example.org',1,'key',catalog,'snap')
 o.update(db,'owner@example.org',dict(submission=s['id'],reference='ref',state='declined',version=0),{})
 return c,db,s,catalog

def test_archive_restores_and_keeps_recipient_history(tmp_path):
 c,db,s,_=setup(tmp_path)
 m.archive(db,'owner@example.org',s['id'],True)
 assert not r.submissions(db)
 assert len(r.submissions(db,'test@example.org'))==1
 assert len(r.submissions(db,include_archived=True))==1
 m.archive(db,'owner@example.org',s['id'],False)
 assert len(r.submissions(db))==1
 db.close()

def test_purge_exact_tests_preserves_new_requests_and_drafts(tmp_path):
 c,db,s,catalog=setup(tmp_path)
 plan=m.preview(c,[s['id']],['test@example.org'])
 r.save(db,'real@example.org',0,['ref'],'real',catalog);real=r.submit(db,'real@example.org',1,'new',catalog,'snap')
 result=m.purge(c,plan,tmp_path/'backup')
 assert result['removed_submissions']==1 and len(r.submissions(db))==1
 assert r.submissions(db)[0]['id']==real['id']
 with sqlite3.connect(tmp_path/'backup/requests.sqlite') as backup:assert backup.execute('SELECT count(*) FROM submissions').fetchone()[0]==2
 assert r.draft(db,'real@example.org')['version']==2
 assert db.execute('SELECT count(*) FROM request_events WHERE submission=?',(s['id'],)).fetchone()[0]==0
 db.close()

def test_changed_history_blocks_cleanup_and_non_tests_rejected(tmp_path):
 c,db,s,_=setup(tmp_path);plan=m.preview(c,[s['id']],['test@example.org'])
 with pytest.raises(ValueError):m.preview(c,[s['id']],['other@example.org'])
 o.update(db,'owner@example.org',dict(submission=s['id'],reference='ref',state='pending',version=1),{})
 with pytest.raises(r.Conflict):m.purge(c,plan,tmp_path/'backup')
 with pytest.raises(ValueError):m.preview(c,[s['id']],['test@example.org'])
 assert len(r.submissions(db))==1 and not (tmp_path/'backup').exists()
 db.close()
