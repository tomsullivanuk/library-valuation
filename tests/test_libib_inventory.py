import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

import valuation.libib_inventory as libib_inventory
from valuation.libib_inventory import (
    AUDIT_COMPLETENESS_VALUES,
    ACCEPTED_RECONCILIATION_OUTCOMES,
    InventoryHoldingRepository,
    InventoryImportFolderRepository,
    InventoryImportRepository,
    InventoryObservationRepository,
    InventoryReconciliationDecisionRepository,
    PR3_INVENTORY_HOLDING_FIELDNAMES,
    LibibInventoryError,
    LibibRepositoryError,
    audit_absence_outcome,
    import_libib_inventory,
    inventory_repository_paths,
    resolve_libib_import_source,
    supersede_inventory_reconciliation_decision,
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


def all_repository_rows(data_dir: Path):
    paths = inventory_repository_paths(data_dir)
    return {
        "imports": InventoryImportRepository(paths["imports"]).load(),
        "folders": InventoryImportFolderRepository(paths["folders"]).load(),
        "observations": InventoryObservationRepository(paths["observations"]).load(),
        "decisions": InventoryReconciliationDecisionRepository(paths["decisions"]).load(),
        "holdings": InventoryHoldingRepository(paths["holdings"]).load(),
    }


def test_first_directory_import_registers_folder_and_creates_durable_state(tmp_path):
    libib_root, audit_area, _ = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"

    result = import_libib_inventory(
        audit_area, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW
    )
    state = all_repository_rows(data_dir)
    imports, folders, holdings = state["imports"], state["folders"], state["holdings"]

    assert result.status == "imported"
    assert result.holdings_created == 1
    assert result.observations_created == result.decisions_created == 2
    assert result.accepted_observation_count == 1
    assert result.unresolved_observation_count == 1
    assert result.rejected_observation_count == 0
    assert (
        result.accepted_observation_count
        + result.unresolved_observation_count
        + result.rejected_observation_count
        == result.observations_created
    )
    assert len(imports) == len(folders) == 1
    assert len(state["observations"]) == len(state["decisions"]) == 2
    assert len(holdings) == 1
    assert dict(result.outcome_counts) == {
        "new_holding_created": 1,
        "quantity_requires_review": 1,
    }
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
    assert len(holdings) == 1
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
    assert len(holdings) == 2
    assert len(first_ids & {row["holding_id"] for row in holdings}) == 1


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
        ("creators", "Curie, Marie", "Curie, Marie S."),
        ("ean_isbn13", "9780306406157", "9780198786221"),
    ],
)
def test_changed_identity_row_is_preserved_without_holding_mutation(
    tmp_path, field, old, new
):
    libib_root, audit_area, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    paths = inventory_repository_paths(data_dir)
    holding_before = paths["holdings"].read_bytes()
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

    assert result.status == "imported"
    assert result.holdings_created == 0
    assert any(
        diagnostic.code == "holding_identity_changed_requires_reconciliation"
        for diagnostic in result.diagnostics
    )
    assert paths["holdings"].read_bytes() == holding_before
    state = all_repository_rows(data_dir)
    assert len(state["imports"]) == 2
    assert len(state["observations"]) == 4
    assert len(state["holdings"]) == 1


def test_holdings_have_stable_project_ids_and_blank_catalog_and_location(tmp_path):
    libib_root, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    holdings = repository_rows(data_dir)[2]

    assert all(row["holding_id"].startswith("HLD-") for row in holdings)
    assert len({row["holding_id"] for row in holdings}) == 1
    assert all(row["catalog_item_id"] == "" for row in holdings)
    assert all(row["current_location_id"] == "" for row in holdings)
    assert [row["copies"] for row in holdings] == ["1"]
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
    assert len(holdings) == 1


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


def test_indistinguishable_duplicate_rows_are_observed_without_holdings(tmp_path):
    export = tmp_path / "duplicates.csv"
    lines = (FIXTURES / "study_export.csv").read_text(encoding="utf-8").splitlines()
    export.write_text("\n".join([lines[0], lines[1], lines[1]]) + "\n", encoding="utf-8")

    data_dir = tmp_path / "data"
    result = import_libib_inventory(export, data_dir=data_dir)
    state = all_repository_rows(data_dir)

    assert result.status == "imported"
    assert result.holdings_created == 0
    assert len(state["observations"]) == 2
    assert len({row["inventory_observation_id"] for row in state["observations"]}) == 2
    assert {row["outcome"] for row in state["decisions"]} == {
        "indistinguishable_duplicate_rows"
    }
    assert state["holdings"] == []


@pytest.mark.parametrize(
    ("repository_type", "filename"),
    [
        (InventoryImportRepository, "inventory_imports.csv"),
        (InventoryImportFolderRepository, "inventory_import_folders.csv"),
        (InventoryObservationRepository, "inventory_observations.csv"),
        (
            InventoryReconciliationDecisionRepository,
            "inventory_reconciliation_decisions.csv",
        ),
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


def write_single_row_export(path: Path) -> None:
    lines = (FIXTURES / "study_export.csv").read_text(encoding="utf-8").splitlines()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")


def downgrade_holdings_to_pr3_and_remove_pr5_evidence(data_dir: Path) -> list[str]:
    paths = inventory_repository_paths(data_dir)
    holdings = InventoryHoldingRepository(paths["holdings"]).load()
    holding_ids = [row["holding_id"] for row in holdings]
    with paths["holdings"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PR3_INVENTORY_HOLDING_FIELDNAMES)
        writer.writeheader()
        for row in holdings:
            legacy = {field: row.get(field, "") for field in writer.fieldnames}
            legacy["schema_version"] = "1"
            writer.writerow(legacy)
    paths["observations"].unlink()
    paths["decisions"].unlink()
    return holding_ids


def test_observations_preserve_privacy_safe_evidence_diagnostics_and_unknown_columns(tmp_path):
    export = tmp_path / "diagnostic.csv"
    rows = list(csv.DictReader((FIXTURES / "study_export.csv").open(newline="", encoding="utf-8")))
    row = dict(rows[0])
    row["ean_isbn13"] = "9.78031E+12"
    row["upc_isbn10"] = ""
    row["future_source_field"] = "not persisted raw"
    with export.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)

    import_libib_inventory(export, data_dir=tmp_path / "data", now=lambda: NOW)
    observation = all_repository_rows(tmp_path / "data")["observations"][0]

    assert observation["raw_isbn13"] == "9.78031E+12"
    assert observation["normalized_isbn13"] == ""
    assert set(json.loads(observation["diagnostic_codes_json"])) == {
        "excel_scientific_notation",
        "unknown_columns",
    }
    assert json.loads(observation["unknown_columns_json"]) == ["future_source_field"]
    assert "future_source_field" not in json.loads(observation["raw_evidence_json"])
    assert "notes" not in json.loads(observation["raw_evidence_json"])


def test_observation_ids_are_deterministic_for_the_accepted_import_and_immutable(tmp_path):
    export = tmp_path / "one.csv"
    write_single_row_export(export)
    data_dir = tmp_path / "data"
    first = import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    paths = inventory_repository_paths(data_dir)
    observation_bytes = paths["observations"].read_bytes()
    observation_id = all_repository_rows(data_dir)["observations"][0][
        "inventory_observation_id"
    ]

    repeated = import_libib_inventory(export, data_dir=data_dir)

    assert repeated.status == "duplicate"
    assert repeated.inventory_import_id == first.inventory_import_id
    assert paths["observations"].read_bytes() == observation_bytes
    assert all_repository_rows(data_dir)["observations"][0][
        "inventory_observation_id"
    ] == observation_id


def test_changed_import_appends_observations_without_rewriting_prior_evidence(tmp_path):
    libib_root, audit_area, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    before = [dict(row) for row in all_repository_rows(data_dir)["observations"]]
    changed = audit_area / "changed.csv"
    changed.write_text(
        export.read_text(encoding="utf-8").replace("Example Physics", "Corrected Physics"),
        encoding="utf-8",
    )
    export.unlink()

    import_libib_inventory(changed, data_dir=data_dir, libib_input_dir=libib_root)
    after = all_repository_rows(data_dir)["observations"]

    assert after[: len(before)] == before
    assert len(after) == len(before) * 2


def test_changed_title_with_lost_isbn_is_reviewed_without_duplicate_holding(tmp_path):
    libib_root, audit_area, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    holding_before = inventory_repository_paths(data_dir)["holdings"].read_bytes()
    rows = list(csv.DictReader(export.open(newline="", encoding="utf-8")))
    rows[0]["title"] = "Substantially Retitled Physics"
    rows[0]["ean_isbn13"] = ""
    rows[0]["upc_isbn10"] = ""
    changed = audit_area / "changed.csv"
    with changed.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    export.unlink()

    result = import_libib_inventory(
        changed, data_dir=data_dir, libib_input_dir=libib_root
    )

    assert result.holdings_created == 0
    assert "edition_or_identity_ambiguity" in dict(result.outcome_counts)
    assert inventory_repository_paths(data_dir)["holdings"].read_bytes() == holding_before


def test_repeated_exact_observation_updates_holding_only_through_accepted_decision(tmp_path):
    libib_root, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    first_holding = dict(all_repository_rows(data_dir)["holdings"][0])
    rows = export.read_text(encoding="utf-8").splitlines()
    export.write_text("\n".join([rows[0], rows[2], rows[1]]) + "\n", encoding="utf-8")

    result = import_libib_inventory(
        export,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        now=lambda: datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    state = all_repository_rows(data_dir)
    holding = state["holdings"][0]
    latest = next(
        row
        for row in state["decisions"]
        if row["inventory_reconciliation_decision_id"]
        == holding["latest_reconciliation_decision_id"]
    )

    assert dict(result.outcome_counts)["existing_holding_reobserved"] == 1
    assert holding["holding_id"] == first_holding["holding_id"]
    assert holding["latest_inventory_observation_id"] != first_holding[
        "latest_inventory_observation_id"
    ]
    assert holding["last_verified_at"] == "2026-07-21T00:00:00Z"
    assert latest["outcome"] == "existing_holding_reobserved"
    assert latest["outcome"] in ACCEPTED_RECONCILIATION_OUTCOMES


def test_manual_supersession_appends_and_preserves_prior_decision_and_observation(tmp_path):
    _, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    state = all_repository_rows(data_dir)
    prior = next(row for row in state["decisions"] if row["outcome"] == "quantity_requires_review")
    prior_copy = dict(prior)
    observation_bytes = inventory_repository_paths(data_dir)["observations"].read_bytes()

    new_id = supersede_inventory_reconciliation_decision(
        data_dir=data_dir,
        supersedes_decision_id=prior["inventory_reconciliation_decision_id"],
        outcome="manual_review_required",
        decision_basis="manual_quantity_review",
        confidence="unknown",
        reason_codes=("awaiting_copy_evidence",),
        explanation="Quantity remains unresolved.",
        now=lambda: datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    after = all_repository_rows(data_dir)

    assert len(after["decisions"]) == len(state["decisions"]) + 1
    assert next(
        row
        for row in after["decisions"]
        if row["inventory_reconciliation_decision_id"]
        == prior["inventory_reconciliation_decision_id"]
    ) == prior_copy
    appended = next(
        row
        for row in after["decisions"]
        if row["inventory_reconciliation_decision_id"] == new_id
    )
    assert appended["supersedes_decision_id"] == prior[
        "inventory_reconciliation_decision_id"
    ]
    assert appended["decision_origin"] == "manual"
    assert inventory_repository_paths(data_dir)["observations"].read_bytes() == observation_bytes


def test_invalid_or_branching_supersession_is_rejected(tmp_path):
    export = tmp_path / "one.csv"
    write_single_row_export(export)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    prior = all_repository_rows(data_dir)["decisions"][0]

    with pytest.raises(LibibRepositoryError, match="does not exist"):
        supersede_inventory_reconciliation_decision(
            data_dir=data_dir,
            supersedes_decision_id="IRD-missing",
            outcome="manual_review_required",
            decision_basis="manual",
            confidence="unknown",
        )
    supersede_inventory_reconciliation_decision(
        data_dir=data_dir,
        supersedes_decision_id=prior["inventory_reconciliation_decision_id"],
        outcome="manual_review_required",
        decision_basis="manual",
        confidence="unknown",
    )
    with pytest.raises(LibibRepositoryError, match="already been superseded"):
        supersede_inventory_reconciliation_decision(
            data_dir=data_dir,
            supersedes_decision_id=prior["inventory_reconciliation_decision_id"],
            outcome="manual_review_required",
            decision_basis="manual",
            confidence="unknown",
        )


def test_decision_supersession_cycles_fail_closed(tmp_path):
    export = tmp_path / "one.csv"
    write_single_row_export(export)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    paths = inventory_repository_paths(data_dir)
    first = all_repository_rows(data_dir)["decisions"][0]
    second = dict(
        first,
        inventory_reconciliation_decision_id="IRD-second",
        outcome="manual_review_required",
        decision_origin="manual",
        supersedes_decision_id=first["inventory_reconciliation_decision_id"],
    )
    first["supersedes_decision_id"] = "IRD-second"
    with paths["decisions"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=InventoryReconciliationDecisionRepository.fieldnames
        )
        writer.writeheader()
        writer.writerows([first, second])

    with pytest.raises(LibibRepositoryError, match="supersession cycle"):
        InventoryReconciliationDecisionRepository(paths["decisions"]).load()


def test_cross_repository_missing_observation_and_holding_references_fail_closed(tmp_path):
    export = tmp_path / "one.csv"
    write_single_row_export(export)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    paths = inventory_repository_paths(data_dir)
    decisions = all_repository_rows(data_dir)["decisions"]
    decisions[0]["inventory_observation_id"] = "IOB-missing"
    with paths["decisions"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=InventoryReconciliationDecisionRepository.fieldnames
        )
        writer.writeheader()
        writer.writerows(decisions)

    with pytest.raises(LibibRepositoryError, match="unknown observation"):
        import_libib_inventory(export, data_dir=data_dir)


def test_accepted_decision_requires_valid_holding_and_unresolved_may_be_blank(tmp_path):
    _, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    state = all_repository_rows(data_dir)
    unresolved = next(row for row in state["decisions"] if row["outcome"] == "quantity_requires_review")
    assert unresolved["holding_id"] == ""
    accepted = next(row for row in state["decisions"] if row["outcome"] == "new_holding_created")
    accepted["holding_id"] = ""
    path = inventory_repository_paths(data_dir)["decisions"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=InventoryReconciliationDecisionRepository.fieldnames
        )
        writer.writeheader()
        writer.writerows(state["decisions"])

    with pytest.raises(LibibRepositoryError, match="requires valid holding"):
        import_libib_inventory(export, data_dir=data_dir)


def test_multiple_physical_candidates_produce_one_nonmutating_review_decision(tmp_path):
    export = tmp_path / "one.csv"
    write_single_row_export(export)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    state = all_repository_rows(data_dir)
    observation = state["observations"][0]
    first = state["holdings"][0]
    second = dict(first, holding_id="HLD-second-candidate")

    decisions, created = libib_inventory._reconcile_observations(
        [observation],
        holdings=[dict(first), second],
        folder_id=first["folder_id"],
        decision_timestamp="2026-07-22T00:00:00Z",
    )

    assert created == 0
    assert decisions[0]["outcome"] == "multiple_holding_candidates"
    assert json.loads(decisions[0]["candidate_holding_ids_json"]) == sorted(
        [first["holding_id"], second["holding_id"]]
    )


def test_pr3_schema_migration_and_backfill_preserve_holding_id_and_are_idempotent(tmp_path):
    export = tmp_path / "one.csv"
    write_single_row_export(export)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    holding_ids = downgrade_holdings_to_pr3_and_remove_pr5_evidence(data_dir)

    migrated = import_libib_inventory(export, data_dir=data_dir)
    state = all_repository_rows(data_dir)

    assert migrated.status == "duplicate"
    assert [row["holding_id"] for row in state["holdings"]] == holding_ids
    assert state["holdings"][0]["schema_version"] == "2"
    assert state["observations"][0]["observation_origin"] == "pr3_backfill"
    assert state["observations"][0]["evidence_completeness"] == "legacy_derived"
    assert json.loads(state["observations"][0]["raw_evidence_json"]) == {}
    assert state["decisions"][0]["decision_origin"] == "pr3_backfill"
    assert state["decisions"][0]["outcome"] == "pr3_backfill_existing_holding"
    paths = inventory_repository_paths(data_dir)
    before = {path: path.read_bytes() for path in paths.values()}

    repeated = import_libib_inventory(export, data_dir=data_dir)

    assert repeated.status == "duplicate"
    assert before == {path: path.read_bytes() for path in paths.values()}


def test_pr3_backfill_fails_when_import_and_holding_totals_do_not_balance(tmp_path):
    _, _, export = setup_audit_area(tmp_path)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    downgrade_holdings_to_pr3_and_remove_pr5_evidence(data_dir)

    with pytest.raises(LibibRepositoryError, match="row and holding totals differ"):
        import_libib_inventory(export, data_dir=data_dir)


@pytest.mark.parametrize(
    ("repository_type", "filename"),
    [
        (InventoryObservationRepository, "inventory_observations.csv"),
        (
            InventoryReconciliationDecisionRepository,
            "inventory_reconciliation_decisions.csv",
        ),
        (InventoryHoldingRepository, "inventory_holdings.csv"),
    ],
)
def test_pr5_repositories_reject_unsupported_schema_versions(
    tmp_path, repository_type, filename
):
    path = tmp_path / filename
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=repository_type.fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                field: ("99" if field == "schema_version" else "")
                for field in writer.fieldnames
            }
        )

    with pytest.raises(LibibRepositoryError, match="Unsupported repository schema version"):
        repository_type(path).load()


@pytest.mark.parametrize(
    ("completeness", "in_scope", "expected"),
    [
        ("partial_scope", True, "not_yet_audited"),
        ("unknown", True, "not_yet_audited"),
        ("complete_scope", False, "outside_audit_scope"),
        ("partial_scope", False, "outside_audit_scope"),
        ("complete_scope", True, "possible_missing"),
    ],
)
def test_audit_absence_has_only_safe_non_destructive_outcomes(
    completeness, in_scope, expected
):
    assert audit_absence_outcome(
        audit_completeness=completeness, in_scope=in_scope
    ) == expected
    assert expected != "verified_missing"
