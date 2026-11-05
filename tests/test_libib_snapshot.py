import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from valuation.libib_snapshot import refresh_snapshot
from valuation.libib_inventory import import_libib_inventory
from valuation.libib_catalog import reconcile_inventory_catalog, StrictCatalogRepository
from valuation.repositories import ACQUISITION_FIELDNAMES
from tests.test_steward_workspace import LIBIB_FIXTURE, write_csv

NOW = datetime(2026, 11, 3, 21, 30, tzinfo=timezone.utc)


def fixture_exports(tmp_path, *, copies=1):
    root = tmp_path/'input'/'libib'
    data = tmp_path/'data'
    data.mkdir()
    with LIBIB_FIXTURE.open(newline='') as f:
        rows=list(csv.DictReader(f))
    row=dict(rows[0],id='source-A',copies=str(copies))
    fields=['id',*[k for k in row if k!='id']]
    old=root/'old'/'old.csv'
    old.parent.mkdir(parents=True)
    write_csv(old,fields,[row])
    catalog=StrictCatalogRepository(data/'catalog_items.csv')
    (data/'catalog_items.csv').write_bytes(catalog.rendered_bytes([]))
    write_csv(data/'acquisitions.csv',ACQUISITION_FIELDNAMES,[])
    import_libib_inventory(old,data_dir=data,libib_input_dir=root,now=lambda:NOW)
    reconcile_inventory_catalog(data_dir=data,now=lambda:NOW)
    new=root/'new'/'new.csv'
    new.parent.mkdir()
    write_csv(new,fields,[dict(row,collection='Study and Annex')])
    def manifest(name,path,label,quantity):
        dest=tmp_path/name
        write_csv(dest,['collection','file','rows','copies','sha256'],[dict(
            collection=label,file=path.name,rows=1,copies=quantity,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())])
        return dest
    previous=manifest('previous.csv',old,'Study',copies)
    current=manifest('current.csv',new,'Study and Annex',copies)
    return root,data,previous,current,new,fields,row


def test_complete_snapshot_retains_holding_identity_and_purchase_bytes(tmp_path):
    root,data,previous,current,_,_,_=fixture_exports(tmp_path)
    before={p.name:p.read_bytes() for p in data.iterdir()}
    old=list(csv.DictReader(open(data/'inventory_holdings.csv')))[0]
    summary=refresh_snapshot(current,previous,libib_input_dir=root,data_dir=data,
        output_dir=tmp_path/'preview',imported_at=NOW)
    assert summary['active_catalog_books']==1
    assert summary['cross_export_continuities_corroborated']==1
    assert all((data/name).read_bytes()==b for name,b in before.items())
    summary=refresh_snapshot(current,previous,libib_input_dir=root,data_dir=data,
        output_dir=tmp_path/'output',imported_at=NOW,publish=True)
    holdings=list(csv.DictReader(open(data/'inventory_holdings.csv')))
    assert len(holdings)==1 and holdings[0]['holding_id']==old['holding_id']
    assert holdings[0]['catalog_item_id']==old['catalog_item_id']
    assert holdings[0]['source_collection_label']=='Study and Annex'
    assert (data/'acquisitions.csv').read_bytes()==before['acquisitions.csv']
    # All old evidence and decisions remain verbatim prefixes in their repositories.
    for name in ['inventory_imports.csv','inventory_observations.csv','inventory_reconciliation_decisions.csv']:
        assert (data/name).read_bytes().startswith(before[name])
    stable={p.name:p.read_bytes() for p in data.iterdir()}
    html=(tmp_path/'output'/'steward_workspace.html').read_bytes()
    repeated=refresh_snapshot(current,previous,libib_input_dir=root,data_dir=data,
        output_dir=tmp_path/'output',imported_at=NOW,publish=True)
    assert repeated['catalog_result']['decisions_created']==0
    assert all((data/name).read_bytes()==b for name,b in stable.items())
    assert (tmp_path/'output'/'steward_workspace.html').read_bytes()==html


def test_empty_exports_are_preserved_without_duplicate_import_hashes(tmp_path):
    root,data,previous,current,_,fields,_=fixture_exports(tmp_path)
    rows=list(csv.DictReader(open(current)))
    for label in ['Empty A','Empty B']:
        p=root/label/(label+'.csv')
        p.parent.mkdir()
        write_csv(p,fields,[])
        rows.append(dict(collection=label,file=p.name,rows=0,copies=0,
                         sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    write_csv(current,list(rows[0]),rows)
    summary=refresh_snapshot(current,previous,libib_input_dir=root,data_dir=data,
        output_dir=tmp_path/'output',publish=True,imported_at=NOW)
    assert summary['collections']==3 and summary['empty_collections']==2
    assert len(json.loads((data/'completed_inventory.json').read_text())['empty_collections'])==2
    imports=list(csv.DictReader(open(data/'inventory_imports.csv')))
    assert all(int(r['row_count'])>0 for r in imports)


def test_quantity_change_requires_review_instead_of_duplicate_holding(tmp_path):
    root,data,previous,current,new,fields,row=fixture_exports(tmp_path)
    write_csv(new,fields,[dict(row,collection='Study and Annex',copies='2')])
    m=list(csv.DictReader(open(current)))
    m[0].update(copies=2,sha256=hashlib.sha256(new.read_bytes()).hexdigest())
    write_csv(current,list(m[0]),m)
    summary=refresh_snapshot(current,previous,libib_input_dir=root,data_dir=data,
        output_dir=tmp_path/'output',publish=True,imported_at=NOW)
    assert summary['physical_identity_reviews']==1
    holds=list(csv.DictReader(open(data/'inventory_holdings.csv')))
    assert len(holds)==1 and holds[0]['copies']=='1'


def test_invalid_source_totals_leave_durable_and_artifacts_untouched(tmp_path):
    root,data,previous,current,_,_,_=fixture_exports(tmp_path)
    before={p.name:p.read_bytes() for p in data.iterdir()}
    rows=list(csv.DictReader(open(current)))
    rows[0]['copies']='99'
    write_csv(current,list(rows[0]),rows)
    with pytest.raises(ValueError,match='totals'):
        refresh_snapshot(current,previous,libib_input_dir=root,data_dir=data,
            output_dir=tmp_path/'output',publish=True,imported_at=NOW)
    assert all((data/name).read_bytes()==b for name,b in before.items())
    assert not (tmp_path/'output').exists()


def test_distinct_source_entry_with_same_isbn_keeps_exact_group_quantity(tmp_path):
    root,data,previous,current,new,fields,row=fixture_exports(tmp_path)
    write_csv(new,fields,[dict(row,collection='Study and Annex'),
                         dict(row,id='source-B',collection='Study and Annex',copies='3')])
    m=list(csv.DictReader(open(current)))
    m[0].update(rows=2,copies=4,sha256=hashlib.sha256(new.read_bytes()).hexdigest())
    write_csv(current,list(m[0]),m)
    summary=refresh_snapshot(current,previous,libib_input_dir=root,data_dir=data,
        output_dir=tmp_path/'output',publish=True,imported_at=NOW)
    assert summary['accepted_holding_entries']==2
    assert summary['accepted_copies']==4
    assert summary['active_catalog_books']==1
    holds=list(csv.DictReader(open(data/'inventory_holdings.csv')))
    assert sorted(h['copies'] for h in holds)==['1','3']
    assert sum(h['holding_state_type']=='quantity_group' for h in holds)==1
    assert list(csv.DictReader(open(data/'acquisitions.csv')))==[]
