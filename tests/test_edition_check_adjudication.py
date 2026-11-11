from copy import deepcopy
import csv
import json
import pytest
from valuation.edition_check_adjudication import adjudicate,validate_alternative


def inputs(tmp_path):
    checks=[];books={};packets={};findings={}
    for cid in ['B1','B2','B3']:
        books[cid]=dict(title='Synthetic '+cid,location='10')
        checks.append(dict(catalog_item_id=cid,kind='edition'))
        packets[cid]=dict(observations=[dict(inventory_observation_id='O'+cid,raw_title='Synthetic '+cid)],source_notes=[dict(notes='First paper-bound edition 1967. ISBN alternatives 0415314526 and 0415314534. Printed invalid identifier 0-07-004363-4.')])
    checks.extend([dict(catalog_item_id=cid,kind='inferred_copy_identity') for cid in ['B1','B2']])
    findings=dict(B1=dict(outcome='records_sufficient',finding='The recorded 1967 source profile resolves identity without assigning a later ISBN.'),B2=dict(outcome='requires_binding_check',finding='Two binding alternatives are documented.',physical_question='Hardback or paperback?',alternatives=[dict(printed='0415314534',label='paperback')]),B3=dict(outcome='requires_identifier_check',finding='Recorded identifier is invalid.',physical_question='Read the printed line when handled.',recorded_invalid_identifier='0070043634'))
    p=tmp_path/'packet.json';p.write_text(json.dumps(dict(checks=checks,books=books,packets=packets)))
    f=tmp_path/'findings.json';f.write_text(json.dumps(findings));return p,f


def test_resolutions_deduplicate_checks_without_assigning_isbn_grade_or_value(tmp_path):
    p,f=inputs(tmp_path);before=[p.read_bytes(),f.read_bytes()]
    summary=adjudicate(p,f,tmp_path/'report')
    assert summary['original_checks']==5 and summary['reviewed_books']==3
    assert summary['edition_checks_resolved']==summary['inferred_checks_resolved']==summary['inferred_checks_merged']==1
    assert summary['remaining_physical_tasks']==2 and summary['estimates_changed']==summary['source_requests']==0
    result=json.loads((tmp_path/'report/adjudications.json').read_text())
    assert all(b['actual_condition']=='ungraded' and not b['physical_copy_isbn_verified'] and not b['publishable'] and not b['canonical_updates'] for b in result['books'])
    rows=list(csv.DictReader((tmp_path/'report/physical_checks_only.csv').open()))
    assert len(rows)==2 and {r['catalog_item_id'] for r in rows}=={'B2','B3'}
    assert all(r['status']=='deferred_until_handled' for r in rows)
    assert before==[p.read_bytes(),f.read_bytes()]
    assert (tmp_path/'report/adjudications.json').stat().st_mode & 0o777==0o600
    with pytest.raises(ValueError):adjudicate(p,f,tmp_path/'report')


@pytest.mark.parametrize('change',[{'B4':dict(outcome='records_sufficient',finding='Extra')},{}])
def test_exact_authored_cohort_is_required(tmp_path,change):
    p,f=inputs(tmp_path);x=json.loads(f.read_text())
    if change:x.update(change)
    else:x.pop('B1')
    f.write_text(json.dumps(x))
    with pytest.raises(ValueError,match='exactly'):adjudicate(p,f,tmp_path/'report')


def test_nine_digit_equivalent_is_a_candidate_not_a_copy_assignment():
    a=validate_alternative(dict(printed='521091144',candidate_isbn10='0521091144',label='paper SBN'),['Printed SBN 521091144.'])
    assert a['normalized_candidate_isbn13']=='9780521091145' and not a['assigned_to_copy']
    a=validate_alternative(dict(printed='C-13-663633-0',candidate_isbn10='0136636330',label='C-coded'),['Book number C-13-663633-0.'])
    assert a['normalized_candidate_isbn13']=='9780136636335'


def test_guessed_repair_and_unrecorded_identifier_are_rejected():
    with pytest.raises(ValueError,match='repair'):validate_alternative(dict(printed='0-07-004363-4',candidate_isbn10='0070043639',label='guess'),['Printed 0-07-004363-4.'])
    with pytest.raises(ValueError,match='absent'):validate_alternative(dict(printed='0415314534',label='not present'),['No ISBN shown.'])


def test_missing_source_evidence_and_unanswered_questions_cannot_be_closed(tmp_path):
    p,f=inputs(tmp_path);packet=json.loads(p.read_text());packet['packets']['B1']['source_notes']=[];p.write_text(json.dumps(packet))
    with pytest.raises(ValueError,match='source-page'):adjudicate(p,f,tmp_path/'report')
    p,f=inputs(tmp_path);findings=json.loads(f.read_text());findings['B2'].pop('physical_question');f.write_text(json.dumps(findings))
    with pytest.raises(ValueError,match='precise physical'):adjudicate(p,f,tmp_path/'report')


def test_html_and_csv_escape_recorded_content_and_keep_frozen_scope_separate(tmp_path):
    p,f=inputs(tmp_path);packet=json.loads(p.read_text());packet['packets']['B2']['observations'][0]['raw_title']='=Synthetic <script>';p.write_text(json.dumps(packet))
    adjudicate(p,f,tmp_path/'report')
    page=(tmp_path/'report/review.html').read_text();assert '<script>' not in page and 'frozen reports retain their raw flags' in page
    rows=list(csv.DictReader((tmp_path/'report/physical_checks_only.csv').open()));assert any(r['title'].startswith("'=Synthetic") for r in rows)


def test_inferred_only_question_is_not_mislabeled_as_merged(tmp_path):
    p,f=inputs(tmp_path);packet=json.loads(p.read_text());packet['checks']=[c for c in packet['checks'] if not(c['catalog_item_id']=='B2' and c['kind']=='edition')];p.write_text(json.dumps(packet))
    summary=adjudicate(p,f,tmp_path/'report')
    assert summary['inferred_checks_remaining']==1 and summary['inferred_checks_merged']==0


def test_consistent_target_inventory_identifier_can_resolve_without_page_note(tmp_path):
    p,f=inputs(tmp_path);packet=json.loads(p.read_text());book=packet['packets']['B1'];book['source_notes']=[];book['observations'][0].update(raw_isbn13='9780198829171',raw_isbn10='0198829175',normalized_isbn13='9780198829171',normalized_isbn10='0198829175');p.write_text(json.dumps(packet))
    findings=json.loads(f.read_text());findings['B1'].update(resolution_basis='consistent_inventory_identifier',inventory_observation_ids=['OB1']);f.write_text(json.dumps(findings))
    adjudicate(p,f,tmp_path/'report')
    b=next(b for b in json.loads((tmp_path/'report/adjudications.json').read_text())['books'] if b['catalog_item_id']=='B1')
    assert b['inventory_basis'][0]['recorded_isbn13']=='9780198829171' and not b['physical_copy_isbn_verified']
    book['observations'][0]['raw_isbn13']='9780486600819';p.write_text(json.dumps(packet))
    with pytest.raises(ValueError,match='Conflicting'):adjudicate(p,f,tmp_path/'conflicting')


def test_evidence_for_one_copy_cannot_close_another_copy_question(tmp_path):
    p,f=inputs(tmp_path);packet=json.loads(p.read_text());packet['checks']=[c for c in packet['checks'] if not(c['catalog_item_id']=='B1' and c['kind']=='edition')]
    for c in packet['checks']:
        if c['catalog_item_id']=='B1':c.update(observation_ids=['unknown'],location='8')
    packet['packets']['B1']['observations']=[dict(inventory_observation_id='known',raw_title='Known copy'),dict(inventory_observation_id='unknown',raw_title='Other copy')]
    packet['packets']['B1']['source_notes']=[dict(observation_id='known',notes='Known copy has a documented edition.')];p.write_text(json.dumps(packet))
    with pytest.raises(ValueError,match='source-page'):adjudicate(p,f,tmp_path/'report')
    findings=json.loads(f.read_text());findings['B1']=dict(outcome='requires_edition_check',finding='The other copy has no recorded identifier.',physical_question='Check only the copy at 8.');f.write_text(json.dumps(findings))
    adjudicate(p,f,tmp_path/'report')
    b=next(b for b in json.loads((tmp_path/'report/adjudications.json').read_text())['books'] if b['catalog_item_id']=='B1')
    assert b['location']=='8' and b['observation_ids']==['unknown'] and not b['source_notes']


def test_source_rejected_identifier_stays_excluded_despite_valid_checksum(tmp_path):
    p,f=inputs(tmp_path);findings=json.loads(f.read_text());findings['B2']['excluded_identifiers']=[dict(printed='0415314534',reason='Source explicitly rejects it')];f.write_text(json.dumps(findings))
    with pytest.raises(ValueError,match='Source-rejected'):adjudicate(p,f,tmp_path/'report')


def test_additional_existing_image_is_copy_scoped_and_fingerprinted(tmp_path):
    import hashlib
    p,f=inputs(tmp_path);image=tmp_path/'stored-photo.jpg';image.write_bytes(b'synthetic existing image')
    findings=json.loads(f.read_text());findings['B1']['additional_record_evidence']=[dict(file=image.name,observation_id='OB1',notes='Re-read existing image: first paper-bound edition.',sha256=hashlib.sha256(image.read_bytes()).hexdigest())];f.write_text(json.dumps(findings))
    adjudicate(p,f,tmp_path/'report')
    result=json.loads((tmp_path/'report/adjudications.json').read_text());assert str(image.resolve()) in result['input_hashes']
    image.write_bytes(b'changed')
    with pytest.raises(ValueError,match='image changed'):adjudicate(p,f,tmp_path/'changed')
