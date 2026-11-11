import pytest
from valuation.family_search import Search,fingerprint
from valuation.family_catalog import FIELDS

def book(ref,title,author='',description='',isbn=''):
 r=dict.fromkeys(FIELDS,'');r.update(reference=ref,title=title,author=author,description=description,isbn=isbn);return r

@pytest.fixture
def records():return [book('a','Medieval Philosophy','José Smith','Scholastic thought and faith', '9780198829171'),book('b','Modern Faith','Other','Medieval philosophy is mentioned here'),book('c','Painting Landscapes','Artist','Art and outdoor painting')]

def refs(result):return [r['reference'] for r in result['results']]

def test_exact_titles_isbns_and_description_ranking(records):
 s=Search(records)
 assert refs(s.search('medieval philosophy'))[0]=='a'
 assert refs(s.search('978-0-19-882917-1'))==['a']
 assert refs(s.search('9780000000000'))==[]
 assert refs(Search([book('short','The Book')]).search('The Book'))==['short']
 assert refs(s.search('scholastic'))==['a']
 assert refs(s.search('jose smith'))[0]=='a'
 assert refs(s.search('philosphy'))[0]=='a'

def test_sql_input_and_no_results(records):
 s=Search(records)
 assert refs(s.search('zzxxyy qqqvvv'))==[]
 s.search('" OR books; DROP TABLE books; --')
 assert refs(s.search('Medieval Philosophy'))[0]=='a'
 with pytest.raises(ValueError):s.search('a'*501)

def test_semantic_boundary_fallback_and_live_availability(records):
 s=Search(records,lambda q,allowed:[('c',.7),('PRIVATE',1),('b',.1)])
 out=s.search('artistic scenery',allowed={'a','c'})
 assert refs(out)==['c'] and out['engine']=='hybrid'
 assert refs(s.search('artistic scenery',allowed={'a'}))==[]
 def broken(*args):raise RuntimeError('PRIVATE DETAILS')
 out=Search(records,broken).search('scholastic')
 assert refs(out)==['a'] and out['engine']=='keyword' and 'PRIVATE' not in str(out)

def test_allowlist_and_fingerprint(records):
 assert fingerprint(records)==fingerprint(list(reversed(records)))
 with pytest.raises(ValueError):Search([dict(records[0],notes='PRIVATE')])
 with pytest.raises(ValueError):Search([records[0],records[0]])
 assert 'Scholastic' in Search(records).search('scholastic')['results'][0]['excerpt']

def test_embedding_index_detects_source_changes_and_corruption(records,tmp_path,monkeypatch):
 import numpy as np
 from valuation import family_search_embeddings as e
 class FakeEncoder:
  def encode(self,texts,**kwargs):return np.array([[1.,0.] for _ in texts])
 monkeypatch.setattr(e,'encoder',lambda p:FakeEncoder())
 e.build(records,'pinned-model',tmp_path)
 semantic=e.Embeddings(records,'pinned-model',tmp_path)
 assert len(semantic('topic',{'a'}))==1
 with pytest.raises(ValueError):e.Embeddings([dict(records[0],description='Changed')]+records[1:],'pinned-model',tmp_path)
 (tmp_path/'vectors.npz').write_bytes(b'damaged')
 with pytest.raises(ValueError):e.Embeddings(records,'pinned-model',tmp_path)

def test_chunked_descriptions_are_bounded_and_private_fields_rejected(records):
 from valuation.family_search_embeddings import documents
 long=dict(records[0],description='scholastic '*5000)
 chunks=list(documents([long]))
 assert 1<len(chunks)<=16 and all(ref=='a' for ref,_ in chunks)
 assert len(list(documents([dict(records[0],description='')])))==1
 with pytest.raises(ValueError):list(documents([dict(records[0],private_note='no')]))

def test_incidental_single_word_does_not_satisfy_unrelated_long_query(records):
 s=Search(records)
 assert refs(s.search('scholastic hoverboard neutron warranty'))==[]

def test_preview_falls_back_without_exposing_private_fields(records,tmp_path):
 import json
 from valuation.family_service import App
 snap=tmp_path/'catalog.json';snap.write_text(json.dumps(records))
 app=App(dict(snapshot=str(snap),database=str(tmp_path/'requests.sqlite'),search_pilot_dir=str(tmp_path/'missing')),identity=lambda t:'owner')
 out=app.search_preview('scholastic')
 assert out['hybrid']['engine']=='keyword'
 assert out['hybrid']['results'][0]['title']=='Medieval Philosophy'
 assert 'unavailable' in out['hybrid']['notice']
 assert not any('location' in r or 'value' in r for r in out['hybrid']['results'])

def test_owner_search_includes_reserved_holdings_and_maps_only_active_ids(tmp_path,monkeypatch):
 import json,hashlib
 from types import SimpleNamespace
 from valuation.family_service import App
 ref=hashlib.sha256(b'family-v1:BOOK').hexdigest()[:20]
 record=book(ref,'Medieval Philosophy')
 path=tmp_path/'catalog.json';path.write_text(json.dumps([record]))
 app=App(dict(snapshot=str(path),database=str(tmp_path/'db'),owner_data_dir=str(tmp_path),owner_output_dir=str(tmp_path)),identity=lambda t:'owner')
 # Family availability excludes a reserved title, while owner active inventory retains it.
 app.catalog=lambda:({},'hash')
 monkeypatch.setattr('valuation.workspace_service.load_model',lambda *a:SimpleNamespace(completed_inventory=SimpleNamespace(catalog_item_ids=('BOOK',))))
 assert app.search_preview('medieval')['hybrid']['results']==[]
 result=app.search_preview('medieval',owner_scope=True)['hybrid']['results']
 assert result[0]['catalog_item_id']=='BOOK'
 assert app.search_preview('medieval',owner_scope=True,catalog_ids=['OTHER'])['hybrid']['results']==[]
 with pytest.raises(ValueError):app.search_preview('medieval',owner_scope=True,catalog_ids='BOOK')
 monkeypatch.setattr('valuation.workspace_service.load_model',lambda *a:SimpleNamespace(completed_inventory=SimpleNamespace(catalog_item_ids=())))
 assert app.search_preview('medieval',owner_scope=True)['hybrid']['results']==[]
