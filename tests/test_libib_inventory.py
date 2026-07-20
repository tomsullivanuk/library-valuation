import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

import valuation.libib_inventory as libib_inventory
from valuation.libib_inventory import (
    AUDIT_COMPLETENESS_VALUES,
    InventoryHoldingRepository,
    InventoryImportFolderRepository,
    InventoryImportRepository,
    LibibInventoryError,
    LibibRepositoryError,
    import_libib_inventory,
    inventory_repository_paths,
    resolve_libib_import_source,
)


FIXTURES = Path(__file__).parent / "fixtures" / "libib"
NOW = datetime(2026, 7, 20, 12, 30, tzinfo=timezone.utc)


def setup_audit_area(tmp_path: Path, name: str = "study") -> tuple[Path, Path, Path]:
    libib_root = tmp_path / "input" / "libib"
    audit_area = libib_root / name
    audit_area.mkdir(parents=True)
    export = audit_area / "library_20260720_013144.csv"
    shutil.copyfile(FIXTURES / "study_export.csv", export)
    return libib_root, audit_area, export


def repository_rows(data_dir: Path):
    paths = inventory_repository_paths(data_dir)
    return (
        InventoryImportRepository(paths["imports"]).load(),
        InventoryImportFolderRepository(paths["folders"]).load(),
        InventoryHoldingRepository(paths["holdings"]).load(),
    )


def test_first_directory_import_registers_folder_and_creates_durable_state(tmp_path):
    libib_root, audit_area, _ = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"

    result = import_libib_inventory(
        audit_area, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW
    )
    imports, folders, holdings = repository_rows(data_dir)

    assert result.status == "imported"
    assert result.holdings_created == 2
    assert len(imports) == len(folders) == 1
    assert len(holdings) == 2
    assert folders[0]["folder_path"] == "study"
    assert folders[0]["expected_collection_label"] == "Study"
    assert folders[0]["first_imported_at"] == folders[0]["last_imported_at"] == "2026-07-20T12:30:00Z"
    assert imports[0]["source_file_name"] == "library_20260720_013144.csv"
    assert imports[0]["source_collection_label"] == "Study"
    assert imports[0]["row_count"] == "2"


def test_repeat_import_uses_hash_and_does_not_duplicate_or_mutate_state(tmp_path):
    libib_root, audit_area, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    first = import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    renamed = audit_area / "renamed.csv"
    export.rename(renamed)

    repeated = import_libib_inventory(
        renamed,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        now=lambda: datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    imports, folders, holdings = repository_rows(data_dir)

    assert repeated.status == "duplicate"
    assert repeated.inventory_import_id == first.inventory_import_id
    assert repeated.holdings_created == 0
    assert len(imports) == len(folders) == 1
    assert len(holdings) == 2
    assert folders[0]["last_imported_at"] == "2026-07-20T12:30:00Z"


def test_new_file_in_registered_folder_reuses_registration_and_holding_ids(tmp_path):
    libib_root, audit_area, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    first = import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    first_ids = {row["holding_id"] for row in repository_rows(data_dir)[2]}
    changed = audit_area / "library_20260721_013144.csv"
    rows = list(csv.DictReader(export.open(newline="", encoding="utf-8")))
    added = dict(rows[0])
    added.update(
        title="New Study Arrival",
        creators="Hopper, Grace",
        first_name="Grace",
        last_name="Hopper",
        ean_isbn13="",
        upc_isbn10="",
        description="A distinct synthetic book.",
        publisher="Another Press",
        publish_date="1999-01-01",
    )
    with changed.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows([*rows, added])
    export.unlink()

    second = import_libib_inventory(
        changed,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        audit_scope="Study shelves",
        audit_completeness="partial_scope",
        now=lambda: datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    imports, folders, holdings = repository_rows(data_dir)

    assert first.folder_id == second.folder_id
    assert len(imports) == 2
    assert len(folders) == 1
    assert folders[0]["last_imported_at"] == "2026-07-21T00:00:00Z"
    assert len(holdings) == 3
    assert len(first_ids & {row["holding_id"] for row in holdings}) == 2


def test_collection_mismatch_returns_review_without_mutation(tmp_path):
    libib_root, audit_area, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    before = {path: path.read_bytes() for path in inventory_repository_paths(data_dir).values()}
    changed = audit_area / "changed.csv"
    changed.write_text(export.read_text(encoding="utf-8").replace(",Study,", ",Wrong Room,"), encoding="utf-8")
    export.unlink()

    result = import_libib_inventory(changed, data_dir=data_dir, libib_input_dir=libib_root)

    assert result.status == "review_required"
    assert result.diagnostics[0].code == "collection_label_changed_or_misfiled"
    assert result.diagnostics[0].registered_collection == "Study"
    assert result.diagnostics[0].observed_collection == "Wrong Room"
    assert result.diagnostics[0].folder_path == "study"
    assert "Confirm whether" in result.diagnostics[0].recommendation
    assert before == {path: path.read_bytes() for path in inventory_repository_paths(data_dir).values()}


@pytest.mark.parametrize(
    ("audit_scope", "audit_completeness"),
    [
        ("Living Room Bookshelf near office", "complete_scope"),
        ("Basement storage", "partial_scope"),
    ],
)
def test_descriptive_audit_scope_is_distinct_from_completeness(
    tmp_path, audit_scope, audit_completeness
):
    libib_root, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"

    import_libib_inventory(
        export,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        audit_scope=audit_scope,
        audit_completeness=audit_completeness,
        now=lambda: NOW,
    )

    row = repository_rows(data_dir)[0][0]
    assert row["audit_scope"] == audit_scope
    assert row["audit_completeness"] == audit_completeness


def test_audit_metadata_defaults_to_unknown(tmp_path):
    libib_root, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"

    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)

    row = repository_rows(data_dir)[0][0]
    assert row["audit_scope"] == "unknown"
    assert row["audit_completeness"] == "unknown"


def test_invalid_audit_completeness_is_rejected(tmp_path):
    _, _, export = setup_audit_area(tmp_path)
    with pytest.raises(LibibInventoryError, match="audit_completeness must be one of"):
        import_libib_inventory(
            export,
            data_dir=tmp_path / "data",
            audit_scope="Study",
            audit_completeness="complete",
        )


def test_folder_collection_and_audit_scope_remain_distinct(tmp_path):
    libib_root, _, export = setup_audit_area(tmp_path, name="study-workflow-folder")
    data_dir = tmp_path / "data"

    import_libib_inventory(
        export,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        audit_scope="  Upstairs reading areas  ",
        audit_completeness="partial_scope",
        now=lambda: NOW,
    )
    import_row, folder_row = repository_rows(data_dir)[0][0], repository_rows(data_dir)[1][0]

    assert folder_row["folder_path"] == "study-workflow-folder"
    assert import_row["source_collection_label"] == "Study"
    assert import_row["audit_scope"] == "Upstairs reading areas"
    assert len({folder_row["folder_path"], import_row["source_collection_label"], import_row["audit_scope"]}) == 3


def test_blank_descriptive_audit_scope_is_rejected(tmp_path):
    _, _, export = setup_audit_area(tmp_path)
    with pytest.raises(LibibInventoryError, match="nonblank descriptive value"):
        import_libib_inventory(export, data_dir=tmp_path / "data", audit_scope="  ")


@pytest.mark.parametrize(
    ("field", "old", "new"),
    [
        ("title", "Example Physics", "Example Physics, corrected title"),
        ("ean_isbn13", "9780306406157", "9780198786221"),
    ],
)
def test_changed_identity_row_requires_reconciliation_without_mutation(
    tmp_path, field, old, new
):
    libib_root, audit_area, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    paths = inventory_repository_paths(data_dir)
    before = {path: path.read_bytes() for path in paths.values()}
    changed = audit_area / "changed.csv"
    rows = list(csv.DictReader(export.open(newline="", encoding="utf-8")))
    assert rows[0][field] == old
    rows[0][field] = new
    if field == "ean_isbn13":
        rows[0]["upc_isbn10"] = "0198786220"
    with changed.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    export.unlink()

    result = import_libib_inventory(changed, data_dir=data_dir, libib_input_dir=libib_root)

    assert result.status == "review_required"
    assert result.holdings_created == 0
    assert any(
        diagnostic.code == "holding_identity_changed_requires_reconciliation"
        for diagnostic in result.diagnostics
    )
    assert before == {path: path.read_bytes() for path in paths.values()}
    assert len(repository_rows(data_dir)[2]) == 2


def test_holdings_have_stable_project_ids_and_blank_catalog_and_location(tmp_path):
    libib_root, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    holdings = repository_rows(data_dir)[2]

    assert all(row["holding_id"].startswith("HLD-") for row in holdings)
    assert len({row["holding_id"] for row in holdings}) == 2
    assert all(row["catalog_item_id"] == "" for row in holdings)
    assert all(row["current_location_id"] == "" for row in holdings)
    assert [row["copies"] for row in holdings] == ["1", "2"]
    assert all(row["inventory_status"] == "verified_present" for row in holdings)
    assert all(row["raw_source_reference"].startswith("sha256:") for row in holdings)


def test_row_order_does_not_change_holding_id_set(tmp_path):
    libib_root, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    first_ids = {row["holding_id"] for row in repository_rows(data_dir)[2]}
    rows = export.read_text(encoding="utf-8").splitlines()
    export.write_text("\n".join([rows[0], rows[2], rows[1]]) + "\n", encoding="utf-8")

    reordered = import_libib_inventory(
        export,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        now=lambda: datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    assert reordered.status == "imported"
    assert reordered.holdings_created == 0
    assert {row["holding_id"] for row in repository_rows(data_dir)[2]} == first_ids


def test_explicit_file_outside_operational_root_creates_no_folder_registration(tmp_path):
    export = tmp_path / "explicit.csv"
    shutil.copyfile(FIXTURES / "study_export.csv", export)
    data_dir = tmp_path / "data"

    result = import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    imports, folders, holdings = repository_rows(data_dir)

    assert result.folder_id is None
    assert imports[0]["folder_id"] == imports[0]["folder_path"] == ""
    assert folders == []
    assert len(holdings) == 2


def test_directory_selection_is_direct_and_non_recursive(tmp_path):
    area = tmp_path / "study"
    nested = area / "nested"
    nested.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "study_export.csv", nested / "export.csv")

    with pytest.raises(LibibInventoryError, match="exactly one direct CSV; found 0"):
        resolve_libib_import_source(area)
    shutil.copyfile(FIXTURES / "study_export.csv", area / "one.csv")
    assert resolve_libib_import_source(area) == area / "one.csv"
    shutil.copyfile(FIXTURES / "study_export.csv", area / "two.csv")
    with pytest.raises(LibibInventoryError, match="exactly one direct CSV; found 2"):
        resolve_libib_import_source(area)


def test_multiple_collection_labels_and_unknown_copies_fail_before_writes(tmp_path):
    data_dir = tmp_path / "data"
    with pytest.raises(LibibInventoryError, match="exactly one non-empty"):
        import_libib_inventory(FIXTURES / "untouched_export.csv", data_dir=data_dir)
    assert not data_dir.exists()


def test_indistinguishable_duplicate_rows_require_review(tmp_path):
    export = tmp_path / "duplicates.csv"
    lines = (FIXTURES / "study_export.csv").read_text(encoding="utf-8").splitlines()
    export.write_text("\n".join([lines[0], lines[1], lines[1]]) + "\n", encoding="utf-8")

    with pytest.raises(LibibInventoryError, match="indistinguishable duplicate rows"):
        import_libib_inventory(export, data_dir=tmp_path / "data")


@pytest.mark.parametrize(
    ("repository_type", "filename"),
    [
        (InventoryImportRepository, "inventory_imports.csv"),
        (InventoryImportFolderRepository, "inventory_import_folders.csv"),
        (InventoryHoldingRepository, "inventory_holdings.csv"),
    ],
)
def test_malformed_or_unknown_repository_schema_fails_safely(tmp_path, repository_type, filename):
    path = tmp_path / filename
    path.write_text("schema_version,wrong\n99,value\n", encoding="utf-8")
    with pytest.raises(LibibRepositoryError, match="Unsupported or malformed repository header"):
        repository_type(path).load()


def test_repository_schema_version_rejects_unsupported_rows(tmp_path):
    path = tmp_path / "inventory_imports.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=InventoryImportRepository.fieldnames)
        writer.writeheader()
        writer.writerow({field: ("99" if field == "schema_version" else "") for field in writer.fieldnames})
    with pytest.raises(LibibRepositoryError, match="Unsupported repository schema version"):
        InventoryImportRepository(path).load()


def test_publication_failure_restores_previous_repository_bytes(tmp_path, monkeypatch):
    libib_root, audit_area, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    paths = inventory_repository_paths(data_dir)
    before = {path: path.read_bytes() for path in paths.values()}
    changed = audit_area / "changed.csv"
    rows = list(csv.DictReader(export.open(newline="", encoding="utf-8")))
    added = dict(rows[0])
    added.update(
        title="Atomic Publication Example",
        creators="Turing, Alan",
        first_name="Alan",
        last_name="Turing",
        ean_isbn13="",
        upc_isbn10="",
        description="A distinct synthetic book.",
    )
    with changed.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows([*rows, added])
    export.unlink()
    real_replace = libib_inventory.os.replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(libib_inventory.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="injected publication failure"):
        import_libib_inventory(changed, data_dir=data_dir, libib_input_dir=libib_root)

    assert before == {path: path.read_bytes() for path in paths.values()}
