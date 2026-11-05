import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.test_steward_workspace import LIBIB_FIXTURE, write_csv
from valuation.completed_inventory import declaration_from_manifest, resolve_completed_inventory
from valuation.inventory_review import apply_reviewed_plan
from valuation.libib_catalog import StrictCatalogRepository, reconcile_inventory_catalog, _current_decisions
from valuation.libib_inventory import import_libib_inventory
from valuation.repositories import ACQUISITION_FIELDNAMES

NOW=datetime(2026,11,3,22,tzinfo=timezone.utc)


def reviewed_fixture(tmp_path, *, conflict=False):
    root=tmp_path/'input'/'libib'
    source=root/'study'/'source.csv'
    source.parent.mkdir(parents=True)
    with LIBIB_FIXTURE.open() as f:row=next(csv.DictReader(f))
    row.update(id='source-review',title='Reviewed historical book',creators='Ada Example',publisher='Example Press',
        ean_isbn13='9780306406157' if conflict else '',upc_isbn10='0198786220' if conflict else '',copies='1')
    write_csv(source,list(row),[row])
    data=tmp_path/'data'
    data.mkdir()
    repo=StrictCatalogRepository(data/'catalog_items.csv')
    repo.path.write_bytes(repo.rendered_bytes([]))
    write_csv(data/'acquisitions.csv',ACQUISITION_FIELDNAMES,[])
    import_libib_inventory(source,data_dir=data,libib_input_dir=root,now=lambda:NOW)
    reconcile_inventory_catalog(data_dir=data,now=lambda:NOW)
    manifest=tmp_path/'manifest.csv'
    write_csv(manifest,['collection','file','rows','copies','sha256'],[dict(collection='Study',file=source.name,
        rows=1,copies=1,sha256=hashlib.sha256(source.read_bytes()).hexdigest())])
    (data/'completed_inventory.json').write_text(json.dumps(declaration_from_manifest(manifest,root)))
    obs=next(csv.DictReader(open(data/'inventory_observations.csv')))
    holdings=list(csv.DictReader(open(data/'inventory_holdings.csv')))
    decision_path=data/'inventory_catalog_reconciliation_decisions.csv'
    if not decision_path.exists():
        from valuation.libib_catalog import InventoryCatalogReconciliationDecisionRepository
        repo_decisions=InventoryCatalogReconciliationDecisionRepository(decision_path)
        decision_path.write_bytes(repo_decisions.rendered_bytes([]))
    decisions=list(csv.DictReader(open(decision_path)))
    holding=holdings[0] if holdings else None
    plan={'schema_version':1,'catalog_sha256':hashlib.sha256(repo.path.read_bytes()).hexdigest(),
        'holdings_sha256':hashlib.sha256((data/'inventory_holdings.csv').read_bytes()).hexdigest(),
        'catalog_decisions_sha256':hashlib.sha256((data/'inventory_catalog_reconciliation_decisions.csv').read_bytes()).hexdigest(),
        'repositories_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in data.iterdir() if p.is_file()},
        'reviewed_entries':[dict(observation_id=obs['inventory_observation_id'],holding_id=holding['holding_id'] if holding else '',
            source_fingerprint=obs['source_row_fingerprint'],source_reference=obs['source_reference'],
            supersedes_catalog_decision_id=decisions[-1]['inventory_catalog_reconciliation_decision_id'] if decisions else '',
            action='create_source_only',basis='reviewed_source_metadata',reason='Reviewed title, creator and publisher; ISBN unknown.',
            title=obs['raw_title'],collection='Study')]}
    path=tmp_path/'plan.json'
    path.write_text(json.dumps(plan))
    return data,path,plan


def test_review_creates_source_backed_identity_without_invented_isbn(tmp_path):
    data,path,plan=reviewed_fixture(tmp_path)
    before={p.name:p.read_bytes() for p in data.iterdir() if p.is_file()}
    preview=apply_reviewed_plan(path,data_dir=data,output_dir=tmp_path/'preview',reviewed_at=NOW)
    assert preview['resolved']==1 and preview['remaining']==0
    assert all((data/n).read_bytes()==b for n,b in before.items())
    summary=apply_reviewed_plan(path,data_dir=data,output_dir=tmp_path/'output',publish=True,reviewed_at=NOW)
    book=StrictCatalogRepository(data/'catalog_items.csv').load()[0]
    assert book['title']=='Reviewed historical book'
    assert book['author']=='Ada Example'
    assert book['publisher']=='Example Press'
    assert book['isbn10']==book['isbn13']==book['publication_year']==''
    assert book['match_confidence']=='medium'
    assert (data/'acquisitions.csv').read_bytes()==before['acquisitions.csv']
    assert (data/'inventory_observations.csv').read_bytes()==before['inventory_observations.csv']
    assert (data/'inventory_catalog_reconciliation_decisions.csv').read_bytes().startswith(before['inventory_catalog_reconciliation_decisions.csv'])
    assert not resolve_completed_inventory(data).unresolved_observation_ids
    assert summary['source_only_identifiers_unknown']==1
    assert (tmp_path/'output'/'steward_workspace.html').read_bytes()==(tmp_path/'preview'/'steward_workspace.html').read_bytes()
    with pytest.raises(ValueError,match='stale'):
        apply_reviewed_plan(path,data_dir=data,output_dir=tmp_path/'output',publish=True)


def test_review_keeps_a_specific_user_question_durably(tmp_path):
    data,path,plan=reviewed_fixture(tmp_path)
    plan['reviewed_entries'][0].update(action='needs_input',question='Which ISBN appears on the copyright page?')
    path.write_text(json.dumps(plan))
    result=apply_reviewed_plan(path,data_dir=data,output_dir=tmp_path/'output',publish=True,reviewed_at=NOW)
    assert result['remaining']==1 and result['resolved']==0
    decisions=_current_decisions(list(csv.DictReader(open(data/'inventory_catalog_reconciliation_decisions.csv'))))
    decision=next(iter(decisions.values()))
    assert decision['decision_origin']=='manual'
    assert 'Which ISBN appears' in decision['explanation']
    assert 'steward_input_needed' in decision['reason_codes_json']
    assert 'Which ISBN appears' in (tmp_path/'output'/'inventory_review_needs_input.csv').read_text()


def test_review_rejects_stale_sources_before_writing(tmp_path):
    data,path,plan=reviewed_fixture(tmp_path)
    p=data/'inventory_observations.csv'
    p.write_bytes(p.read_bytes()+b'\n')
    before={p.name:p.read_bytes() for p in data.iterdir() if p.is_file()}
    with pytest.raises(ValueError,match='stale'):
        apply_reviewed_plan(path,data_dir=data,output_dir=tmp_path/'output',publish=True)
    assert all((data/n).read_bytes()==b for n,b in before.items())
    assert not (tmp_path/'output').exists()


def test_review_preserves_conflicting_observation_when_applying_cited_correction(tmp_path):
    data,path,plan=reviewed_fixture(tmp_path,conflict=True)
    item=plan['reviewed_entries'][0]
    item.update(action='physical_link',catalog_item_id='',source_urls=['https://example.test/publisher-record'],
        corrected_identifiers={'isbn13':'9780306406157','isbn10':'0306406152'},basis='reviewed_identifier_conflict')
    path.write_text(json.dumps(plan))
    before=(data/'inventory_observations.csv').read_bytes()
    result=apply_reviewed_plan(path,data_dir=data,output_dir=tmp_path/'output',publish=True,reviewed_at=NOW)
    assert result['resolved']==1
    book=StrictCatalogRepository(data/'catalog_items.csv').load()[0]
    assert book['isbn13']=='9780306406157' and book['isbn10']=='0306406152'
    assert (data/'inventory_observations.csv').read_bytes()==before
    assert len(list(csv.DictReader(open(data/'inventory_holdings.csv'))))==1


def test_review_requires_original_note_evidence_for_source_only_physical_override(tmp_path):
    data,path,plan=reviewed_fixture(tmp_path,conflict=True)
    source=tmp_path/'input'/'libib'/'study'/'source.csv'
    with source.open() as handle:
        raw=next(csv.DictReader(handle))
    item=plan['reviewed_entries'][0]
    item.update(action='physical_create_source_only',
        source_evidence=dict(file=source.name,source_id=raw['id'],
            notes_sha256=hashlib.sha256(raw.get('notes','').encode()).hexdigest()))
    path.write_text(json.dumps(plan))
    before=(data/'inventory_observations.csv').read_bytes()
    result=apply_reviewed_plan(path,data_dir=data,output_dir=tmp_path/'output',publish=True,
        reviewed_at=NOW,libib_input_dir=tmp_path/'input'/'libib')
    assert result['resolved']==1 and result['source_only_identifiers_unknown']==1
    book=StrictCatalogRepository(data/'catalog_items.csv').load()[0]
    assert book['isbn13']==book['isbn10']==''
    assert book['match_confidence']=='medium'
    assert (data/'inventory_observations.csv').read_bytes()==before


def test_review_rejects_changed_original_note_evidence(tmp_path):
    data,path,plan=reviewed_fixture(tmp_path)
    plan['reviewed_entries'][0]['source_evidence']=dict(file='source.csv',source_id='source-review',notes_sha256='wrong')
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError,match='note evidence does not match'):
        apply_reviewed_plan(path,data_dir=data,output_dir=tmp_path/'output',publish=True,
            libib_input_dir=tmp_path/'input'/'libib')
    assert not (tmp_path/'output').exists()
