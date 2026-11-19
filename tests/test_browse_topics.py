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


def test_history_subtopics_from_catalog_subjects_and_lc():
    assert 'american' in classify({'title':'A life'},{'lcc':'E457.2'})
    assert 'european-history' in classify({'title':'A kingdom'},{'lcc':'DA30'})
    assert 'ancient-history' in classify({'title':'The Roman Empire'})
    assert 'political-thought' in classify({'title':'A treatise'},{'lcc':'JC71'})
    assert 'war-history' in classify({'title':'World War II'})
    assert 'medieval-history' in classify({'title':'The Middle Ages'})


def test_each_broad_topic_has_narrower_subjects():
    result=build({'a':{'title':'Uninformative'}})
    assert all(t['subtopics'] for t in result['topics'] if t['id']!='more')
    assert 'fiction' in classify({'title':'A novel'})
    assert 'drawing-painting' in classify({'title':'Drawing and painting'})
