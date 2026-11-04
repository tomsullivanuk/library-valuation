import csv
import hashlib
import json
from dataclasses import asdict

import pytest

from valuation.completed_inventory import (
    declaration_from_manifest, publish_files, resolve_completed_inventory,
)
from tests.test_steward_workspace import model_with_inventory


def declared_model(tmp_path):
    model = model_with_inventory(tmp_path)
    imported = model.inventory_imports[0]
    observations = [o for o in model.observations if o.inventory_import_id == imported.inventory_import_id]
    declaration = {'schema_version': 1, 'assertion': 'completed_physical_inventory', 'sources': [
        {'sha256': imported.source_file_hash, 'collection': imported.source_collection_label,
         'rows': len(observations), 'copies': sum(int(o.observed_copies) for o in observations)}]}
    return model, declaration


def test_scope_uses_immutable_imports_and_preserves_unlinked_entries(tmp_path):
    model, declaration = declared_model(tmp_path)
    scope = resolve_completed_inventory(tmp_path / 'data', declaration)
    assert scope.completed
    assert scope.source_entries == len(model.observations)
    assert scope.source_copies == sum(int(o.observed_copies) for o in model.observations)
    assert set(scope.catalog_item_ids) == {h.catalog_item_id for h in model.holdings if h.catalog_item_id}
    assert set(scope.unresolved_observation_ids) == {
        o.inventory_observation_id for o in model.observations
        if not any(h.latest_inventory_observation_id == o.inventory_observation_id and h.catalog_item_id for h in model.holdings)}
    before = {p: p.read_bytes() for p in (tmp_path / 'data').iterdir()}
    assert resolve_completed_inventory(tmp_path / 'data', declaration) == scope
    assert all(p.read_bytes() == b for p, b in before.items())


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'count', 'collection'])
def test_bad_declaration_fails_closed(tmp_path, change):
    _, declaration = declared_model(tmp_path)
    source = declaration['sources'][0]
    if change == 'missing': source['sha256'] = '0' * 64
    if change == 'duplicate': declaration['sources'].append(dict(source))
    if change == 'count': source['copies'] += 1
    if change == 'collection': source['collection'] = 'Wrong collection'
    with pytest.raises(ValueError):
        resolve_completed_inventory(tmp_path / 'data', declaration)


def test_saved_scope_survives_rebuild_and_changes_snapshot_id(tmp_path):
    from valuation.steward_presentation import build_steward_presentation
    model, declaration = declared_model(tmp_path)
    preview = build_steward_presentation(data_dir=tmp_path / 'data', completed_inventory_declaration=declaration)
    (tmp_path / 'data' / 'completed_inventory.json').write_text(json.dumps(declaration))
    rebuilt = build_steward_presentation(data_dir=tmp_path / 'data')
    assert preview.to_json_bytes() == rebuilt.to_json_bytes()
    assert rebuilt.snapshot.snapshot_id != model.snapshot.snapshot_id
    assert rebuilt.acquisitions == model.acquisitions
    assert rebuilt.books == model.books


def test_manifest_rejects_modified_export(tmp_path):
    root = tmp_path / 'input'
    folder = root / 'study'
    folder.mkdir(parents=True)
    source = folder / 'library.csv'
    source.write_text('original')
    manifest = tmp_path / 'manifest.csv'
    with manifest.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['collection', 'file', 'rows', 'copies', 'sha256'])
        writer.writeheader()
        writer.writerow(dict(collection='Study', file=source.name, rows=1, copies=1,
                             sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    assert len(declaration_from_manifest(manifest, root)['sources']) == 1
    source.write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        declaration_from_manifest(manifest, root)


def test_publication_failure_restores_previous_files(tmp_path, monkeypatch):
    import valuation.completed_inventory as module
    old = tmp_path / 'old'
    new = tmp_path / 'new'
    old.write_bytes(b'preserved')
    replace = module.os.replace
    calls = 0
    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('Injected publication failure')
        replace(source, destination)
    monkeypatch.setattr(module.os, 'replace', fail_second)
    with pytest.raises(OSError):
        publish_files([(old, b'changed'), (new, b'new')])
    assert old.read_bytes() == b'preserved'
    assert not new.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['old']
