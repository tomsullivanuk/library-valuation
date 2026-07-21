import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

import valuation.inventory_workflow as workflow
from library_pipeline import main
from valuation.inventory_workflow import DURABLE_REPOSITORY_NAMES, InventoryWorkflowError, update_inventory
from valuation.libib_catalog import StrictCatalogRepository
from valuation.repositories import ACQUISITION_FIELDNAMES, CATALOG_ITEMS_FIELDNAMES


FIXTURE = Path(__file__).parent / "fixtures" / "libib" / "study_export.csv"
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)


def catalog_row():
    row = {field: "" for field in CATALOG_ITEMS_FIELDNAMES}
    row.update(
        catalog_item_id="BK000001",
        isbn13="9780306406157",
        isbn10="0306406152",
        title="Example Physics",
        author="Marie Curie",
        publisher="Example Press",
        publication_year="1980",
        match_confidence="high",
    )
    return row


def setup_workflow(tmp_path: Path):
    libib_root = tmp_path / "input" / "libib"
    audit_dir = libib_root / "study"
    audit_dir.mkdir(parents=True)
    source = audit_dir / "library_20260720_013144.csv"
    shutil.copyfile(FIXTURE, source)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    catalog = StrictCatalogRepository(data_dir / "catalog_items.csv")
    catalog.path.write_bytes(catalog.rendered_bytes([catalog_row()]))
    with (data_dir / "acquisitions.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=ACQUISITION_FIELDNAMES).writeheader()
    return source, libib_root, data_dir, tmp_path / "output"


def state_bytes(data_dir: Path):
    return {
        path.name: path.read_bytes()
        for path in data_dir.iterdir()
        if path.is_file()
    }


def run(source, libib_root, data_dir, output_dir, *, publish=False):
    return update_inventory(
        source,
        libib_input_dir=libib_root,
        data_dir=data_dir,
        output_dir=output_dir,
        audit_scope="Study",
        audit_completeness="partial_scope",
        publish=publish,
        now=lambda: NOW,
    )


def test_preview_is_default_complete_and_does_not_mutate_durable_state(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    before = state_bytes(data_dir)

    result = run(source, libib_root, data_dir, output_dir)

    assert result.mode == "preview"
    assert result.source_rows == 2
    assert result.observations_created == 2
    assert result.holdings_created == 1
    assert result.physical_unresolved == 1
    assert result.catalog_existing_links == 1
    assert result.catalog_items_created == 0
    assert result.acquisitions_created == 0
    assert result.proposed_durable_changes is True
    assert result.durable_state_changed is False
    assert state_bytes(data_dir) == before
    assert (output_dir / "inventory_audit_summary.csv").exists()
    assert (output_dir / "inventory_review_workbook.xlsx").exists()


def test_single_audit_area_directory_is_an_explicit_supported_input(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    result = run(source.parent, libib_root, data_dir, output_dir)
    assert result.source_file == str(source.resolve())
    assert result.mode == "preview"


def test_explicit_publication_changes_all_expected_state_and_no_acquisition(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    acquisition_before = (data_dir / "acquisitions.csv").read_bytes()

    result = run(source, libib_root, data_dir, output_dir, publish=True)

    assert result.mode == "publish"
    assert result.durable_state_changed is True
    assert result.repeat is False
    assert all((data_dir / name).exists() for name in DURABLE_REPOSITORY_NAMES)
    assert (data_dir / "acquisitions.csv").read_bytes() == acquisition_before


def test_identical_repeat_reuses_import_and_creates_no_durable_duplicates(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    first = run(source, libib_root, data_dir, output_dir, publish=True)
    before = state_bytes(data_dir)
    workbook_before = (output_dir / "inventory_review_workbook.xlsx").read_bytes()

    repeated = run(source, libib_root, data_dir, output_dir, publish=True)

    assert repeated.import_status == "duplicate"
    assert repeated.repeat is True
    assert repeated.inventory_import_id == first.inventory_import_id
    assert repeated.observations_created == 0
    assert repeated.observations_reused == 2
    assert repeated.durable_state_changed is False
    assert state_bytes(data_dir) == before
    assert (output_dir / "inventory_review_workbook.xlsx").read_bytes() == workbook_before


def test_repeat_completion_summary_and_artifacts_are_deterministic(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    run(source, libib_root, data_dir, output_dir, publish=True)
    first = run(source, libib_root, data_dir, output_dir)
    workbook = (output_dir / "inventory_review_workbook.xlsx").read_bytes()
    second = run(source, libib_root, data_dir, output_dir)
    assert first.as_dict() == second.as_dict()
    assert (output_dir / "inventory_review_workbook.xlsx").read_bytes() == workbook


def test_changed_source_uses_existing_conservative_reconciliation_without_real_mutation(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    run(source, libib_root, data_dir, output_dir, publish=True)
    before = state_bytes(data_dir)
    rows = list(csv.DictReader(source.open(newline="", encoding="utf-8")))
    rows[0]["title"] = "Example Physics Corrected"
    changed = source.parent / "library_changed.csv"
    with changed.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    result = run(changed, libib_root, data_dir, output_dir)

    assert result.import_status == "imported"
    assert result.repeat is False
    assert result.physical_unresolved >= 1
    assert state_bytes(data_dir) == before


@pytest.mark.parametrize("failure_stage", ["inventory", "catalog", "artifacts"])
def test_failure_after_each_workflow_stage_restores_every_repository(tmp_path, monkeypatch, failure_stage):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    before = state_bytes(data_dir)
    target_name = {
        "inventory": "import_libib_inventory",
        "catalog": "reconcile_inventory_catalog",
        "artifacts": "write_inventory_audit_artifacts",
    }[failure_stage]
    original = getattr(workflow, target_name)

    def fail_after(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError(f"injected {failure_stage} failure")

    monkeypatch.setattr(workflow, target_name, fail_after)
    with pytest.raises(RuntimeError, match="injected"):
        run(source, libib_root, data_dir, output_dir, publish=True)

    assert state_bytes(data_dir) == before
    assert not output_dir.exists()


def test_artifact_publication_failure_restores_durable_and_prior_artifacts(tmp_path, monkeypatch):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    output_dir.mkdir()
    prior = {name: f"prior-{name}".encode() for name in workflow.ARTIFACT_NAMES}
    for name, content in prior.items():
        (output_dir / name).write_bytes(content)
    before = state_bytes(data_dir)

    monkeypatch.setattr(workflow, "_publish_artifacts", lambda *args: (_ for _ in ()).throw(RuntimeError("publish failed")))
    with pytest.raises(RuntimeError, match="publish failed"):
        run(source, libib_root, data_dir, output_dir, publish=True)

    assert state_bytes(data_dir) == before
    assert {name: (output_dir / name).read_bytes() for name in prior} == prior


def test_collection_mismatch_fails_without_writes(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    run(source, libib_root, data_dir, output_dir, publish=True)
    before = state_bytes(data_dir)
    text = source.read_text(encoding="utf-8").replace(",Study,", ",Elsewhere,")
    changed = source.parent / "misfiled.csv"
    changed.write_text(text, encoding="utf-8")

    with pytest.raises(InventoryWorkflowError, match="requires review"):
        run(changed, libib_root, data_dir, output_dir)
    assert state_bytes(data_dir) == before


def test_source_outside_registered_root_and_invalid_repository_fail_before_writes(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    outside = tmp_path / "outside.csv"
    shutil.copyfile(source, outside)
    with pytest.raises(InventoryWorkflowError, match="inside the declared"):
        run(outside, libib_root, data_dir, output_dir)

    (data_dir / "inventory_holdings.csv").write_text("wrong,header\n", encoding="utf-8")
    before = state_bytes(data_dir)
    with pytest.raises(Exception, match="Unsupported|malformed"):
        run(source, libib_root, data_dir, output_dir)
    assert state_bytes(data_dir) == before


def test_malformed_source_fails_before_any_repository_or_artifact_write(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    source.write_text("title,collection\nBroken,Study\n", encoding="utf-8")
    before = state_bytes(data_dir)
    with pytest.raises(Exception, match="missing required columns"):
        run(source, libib_root, data_dir, output_dir, publish=True)
    assert state_bytes(data_dir) == before
    assert not output_dir.exists()


def test_malformed_current_decision_chain_fails_closed(tmp_path):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    run(source, libib_root, data_dir, output_dir, publish=True)
    path = data_dir / "inventory_reconciliation_decisions.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    duplicate = dict(rows[0])
    duplicate["inventory_reconciliation_decision_id"] = "IRD-malformed-current"
    rows.append(duplicate)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    before = state_bytes(data_dir)

    with pytest.raises(Exception, match="current|supersed"):
        run(source, libib_root, data_dir, output_dir)
    assert state_bytes(data_dir) == before


def test_cli_defaults_to_preview_and_prints_machine_readable_summary(tmp_path, capsys):
    source, libib_root, data_dir, output_dir = setup_workflow(tmp_path)
    before = state_bytes(data_dir)
    exit_code = main([
        "update-inventory", "--source", str(source), "--libib-input-dir", str(libib_root),
        "--data-dir", str(data_dir), "--output-dir", str(output_dir),
        "--audit-scope", "Study", "--audit-completeness", "partial_scope",
    ])
    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert summary["mode"] == "preview"
    assert summary["durable_state_changed"] is False
    assert state_bytes(data_dir) == before
