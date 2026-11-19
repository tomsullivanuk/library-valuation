import csv,hashlib
from valuation.browse_topics import build,classify

def test_lc_and_subjects_create_cross_listed_friendly_topics():
    labels=classify({'title':'Gorgias'},{'lcc':'B371.A5','subjects':'Philosophy, ancient; Ethics'})
    assert {'philosophy','ancient','ethics'}<=set(labels)
    assert 'logic-mathematics' in classify({'title':'Reasoning'},{'lcc':'QA9'})
    assert 'bible' in classify({'title':'A guide'},{'lcc':'BS123'})

def test_coverage_counts_are_unique_per_record_and_missing_metadata_visible():
    result=build({'a':{'title':'Gorgias'},'b':{'title':'Uninformative title'}})
    assert result['books']['b']==['more']
    assert next(t['count'] for t in result['topics'] if t['id']=='philosophy')==1
    assert result['total']==2

def test_stale_isbn_metadata_is_not_applied(tmp_path):
    with (tmp_path/'book_metadata.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['catalog_item_id','isbn13','subjects']);w.writeheader();w.writerow(dict(catalog_item_id='B',isbn13='9780000000001',subjects='Physics'))
    ref=hashlib.sha256(b'family-v1:B').hexdigest()[:20]
    result=build({ref:{'title':'Uninformative title','isbn':'9780000000002'}},tmp_path)
    assert result['books'][ref]==['more']
    assert result['metadata_matched']==0

def test_review_override_supports_subtopics_and_rejects_unknown_labels():
    assert classify({'title':'Physics'},override=['ancient','made-up'])==['ancient','philosophy']
