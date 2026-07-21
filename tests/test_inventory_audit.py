import csv
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

from valuation.inventory_audit import (
    CATALOG_REVIEW_FIELDS,
    DECISION_DETAIL_FIELDS,
    EMPTY_SHEET_MESSAGES,
    GENERATED_NOTE,
    PHYSICAL_REVIEW_FIELDS,
    SUMMARY_FIELDS,
    WORKBOOK_COLUMNS,
    WORKBOOK_SHEETS,
    build_inventory_audit_presentation,
    resolve_current_decisions,
    write_inventory_audit_artifacts,
)
from valuation.collector_workbook import write_workbook
from valuation.libib_catalog import StrictCatalogRepository, reconcile_inventory_catalog
from valuation.libib_inventory import (
    InventoryHoldingRepository,
    InventoryImportFolderRepository,
    LibibRepositoryError,
    import_libib_inventory,
    inventory_repository_paths,
)
from valuation.repositories import ACQUISITION_FIELDNAMES


FIXTURE = Path(__file__).parent / "fixtures" / "libib" / "study_export.csv"
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)


def setup_state(tmp_path: Path):
    libib_root = tmp_path / "input" / "libib"
    audit_area = libib_root / "study"
    audit_area.mkdir(parents=True)
    export = audit_area / "library_20260720_013144.csv"
    shutil.copyfile(FIXTURE, export)
    data_dir = tmp_path / "data"
    import_libib_inventory(
        export,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        audit_scope="Study",
        audit_completeness="partial_scope",
        now=lambda: NOW,
    )
    (data_dir / "catalog_items.csv").write_bytes(
        StrictCatalogRepository(data_dir / "catalog_items.csv").rendered_bytes([])
    )
    with (data_dir / "acquisitions.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=ACQUISITION_FIELDNAMES).writeheader()
    reconcile_inventory_catalog(data_dir=data_dir, now=lambda: NOW)
    return data_dir


def decision(identifier, entity="OBS-1", supersedes=""):
    return {
        "decision_id": identifier,
        "entity_id": entity,
        "supersedes_decision_id": supersedes,
    }


def test_current_decision_resolution_handles_no_one_and_multi_step_supersession():
    assert resolve_current_decisions(
        [decision("D1")], id_field="decision_id", entity_field="entity_id"
    )["OBS-1"]["decision_id"] == "D1"
    assert resolve_current_decisions(
        [decision("D1"), decision("D2", supersedes="D1")],
        id_field="decision_id", entity_field="entity_id",
    )["OBS-1"]["decision_id"] == "D2"
    assert resolve_current_decisions(
        [decision("D1"), decision("D2", supersedes="D1"), decision("D3", supersedes="D2")],
        id_field="decision_id", entity_field="entity_id",
    )["OBS-1"]["decision_id"] == "D3"


@pytest.mark.parametrize(
    "rows, message",
    [
        ([decision("D1"), decision("D2", supersedes="D1"), decision("D3", supersedes="D1")], "Branching"),
        ([decision("D2", supersedes="missing")], "Missing"),
        ([decision("D1", supersedes="D2"), decision("D2", supersedes="D1")], "cycle"),
        ([decision("D1"), decision("D2")], "multiple current"),
    ],
)
def test_current_decision_resolution_fails_closed(rows, message):
    with pytest.raises(LibibRepositoryError, match=message):
        resolve_current_decisions(rows, id_field="decision_id", entity_field="entity_id")


def test_queues_preserve_current_durable_outcomes_and_allowlisted_fields(tmp_path):
    data_dir = setup_state(tmp_path)
    presentation = build_inventory_audit_presentation(data_dir=data_dir)

    assert len(presentation.physical_review) == 1
    assert presentation.physical_review[0]["outcome"] == "quantity_requires_review"
    assert presentation.physical_review[0]["reviewer_guidance"] == "Review reported quantity"
    assert presentation.physical_review[0]["reason_codes"] == "copies_not_one"
    assert len(presentation.newly_discovered) == 1
    assert presentation.newly_discovered[0]["acquisition_status"] == "no_acquisition_history"
    assert presentation.newly_discovered[0]["acquisition_count"] == "0"
    assert "acquisition history" in presentation.newly_discovered[0]["reviewer_guidance"]
    assert len(presentation.reconciled_holdings) == 1
    assert presentation.catalog_review == []
    assert all("raw_evidence_json" not in row for rows in presentation.__dict__.values() for row in rows)
    assert all(set(row) == set(PHYSICAL_REVIEW_FIELDS) for row in presentation.physical_review)
    assert all(set(row) == set(DECISION_DETAIL_FIELDS) for row in presentation.decision_detail)


@pytest.mark.parametrize(
    "outcome",
    [
        "holding_identity_changed_requires_reconciliation",
        "multiple_holding_candidates",
        "indistinguishable_duplicate_rows",
        "quantity_requires_review",
        "edition_or_identity_ambiguity",
        "insufficient_identity_evidence",
        "manual_review_required",
        "possible_duplicate",
    ],
)
def test_each_current_physical_unresolved_outcome_enters_physical_review(tmp_path, outcome):
    data_dir = setup_state(tmp_path)
    path = inventory_repository_paths(data_dir)["decisions"]
    from valuation.libib_inventory import InventoryReconciliationDecisionRepository

    repository = InventoryReconciliationDecisionRepository(path)
    rows = repository.load()
    unresolved = next(row for row in rows if row["outcome"] == "quantity_requires_review")
    unresolved["outcome"] = outcome
    path.write_bytes(repository.rendered_bytes(rows))
    assert [row["outcome"] for row in build_inventory_audit_presentation(data_dir=data_dir).physical_review] == [outcome]


@pytest.mark.parametrize(
    "outcome",
    [
        "catalog_relink_requires_review",
        "multiple_catalog_candidates",
        "edition_or_catalog_identity_ambiguity",
        "conflicting_isbn_evidence",
        "insufficient_catalog_evidence",
        "catalog_candidate_requires_review",
        "manual_catalog_review_required",
        "catalog_candidate_ineligible",
        "physical_identity_unresolved",
    ],
)
def test_each_current_catalog_unresolved_outcome_enters_catalog_review(tmp_path, outcome):
    data_dir = setup_state(tmp_path)
    from valuation.libib_catalog import (
        InventoryCatalogReconciliationDecisionRepository,
        catalog_reconciliation_repository_path,
    )

    holding_path = inventory_repository_paths(data_dir)["holdings"]
    holding_repository = InventoryHoldingRepository(holding_path)
    holdings = holding_repository.load()
    holdings[0]["catalog_item_id"] = ""
    holding_path.write_bytes(holding_repository.rendered_bytes(holdings))
    decision_path = catalog_reconciliation_repository_path(data_dir)
    repository = InventoryCatalogReconciliationDecisionRepository(decision_path)
    decisions = repository.load()
    decisions[0].update(outcome=outcome, catalog_item_id="")
    decision_path.write_bytes(repository.rendered_bytes(decisions))

    rows = build_inventory_audit_presentation(data_dir=data_dir).catalog_review
    assert len(rows) == 1
    assert rows[0]["outcome"] == outcome


def test_superseded_physical_decision_is_history_not_current_queue_membership(tmp_path):
    data_dir = setup_state(tmp_path)
    path = inventory_repository_paths(data_dir)["decisions"]
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    unresolved = next(row for row in rows if row["outcome"] == "quantity_requires_review")
    replacement = dict(unresolved)
    replacement.update(
        inventory_reconciliation_decision_id="IRD-manual-current",
        outcome="manual_review_required",
        supersedes_decision_id=unresolved["inventory_reconciliation_decision_id"],
        decision_origin="manual",
        reason_codes_json='["reviewed_quantity"]',
    )
    rows.append(replacement)
    from valuation.libib_inventory import InventoryReconciliationDecisionRepository

    path.write_bytes(InventoryReconciliationDecisionRepository(path).rendered_bytes(rows))
    presentation = build_inventory_audit_presentation(data_dir=data_dir)

    assert [row["outcome"] for row in presentation.physical_review] == ["manual_review_required"]
    history = [row for row in presentation.decision_detail if row["decision_type"] == "physical"]
    assert {row["is_current"] for row in history} == {"yes", "no"}


@pytest.mark.parametrize(
    "status, completeness",
    [
        ("verified_present", "partial_scope"),
        ("not_yet_audited", "partial_scope"),
        ("outside_audit_scope", "complete_scope"),
        ("possible_missing", "complete_scope"),
    ],
)
def test_audit_coverage_displays_durable_state_without_generating_verified_missing(
    tmp_path, status, completeness
):
    data_dir = setup_state(tmp_path)
    path = inventory_repository_paths(data_dir)["holdings"]
    repository = InventoryHoldingRepository(path)
    holdings = repository.load()
    holdings[0]["inventory_status"] = status
    holdings[0]["verification_completeness"] = completeness
    path.write_bytes(repository.rendered_bytes(holdings))

    presentation = build_inventory_audit_presentation(data_dir=data_dir)
    row = presentation.audit_coverage[0]
    assert row["audit_outcome"] == status
    assert row["audit_completeness"] == completeness
    assert all(item["audit_outcome"] != "verified_missing" for item in presentation.audit_coverage)


def test_location_review_retains_labels_and_exposes_mismatch_without_location_creation(tmp_path):
    data_dir = setup_state(tmp_path)
    paths = inventory_repository_paths(data_dir)
    folder_repo = InventoryImportFolderRepository(paths["folders"])
    folders = folder_repo.load()
    folders[0]["expected_collection_label"] = "Renamed logical catalog"
    paths["folders"].write_bytes(folder_repo.rendered_bytes(folders))
    before_holdings = paths["holdings"].read_bytes()

    presentation = build_inventory_audit_presentation(data_dir=data_dir)
    row = presentation.location_review[0]
    assert row["source_collection_label"] == "Study"
    assert row["folder_path"] == "study"
    assert row["audit_scope"] == "Study"
    assert row["current_location_id"] == ""
    assert row["location_review_status"] == "folder_collection_mismatch; source_label_unmapped"
    assert paths["holdings"].read_bytes() == before_holdings
    assert not (data_dir / "inventory_locations.csv").exists()


def test_acquisition_context_distinguishes_zero_one_and_multiple(tmp_path):
    data_dir = setup_state(tmp_path)
    initial = build_inventory_audit_presentation(data_dir=data_dir)
    catalog_id = initial.newly_discovered[0]["catalog_item_id"]
    fieldnames = [
        "acquisition_id", "catalog_item_id", "source", "source_order_id",
        "source_item_id", "order_date", "quantity", "item_price", "item_subtotal",
        "currency", "source_title", "source_asin", "isbn13", "isbn10",
    ]
    base = {field: "" for field in fieldnames}
    base.update(acquisition_id="A1", catalog_item_id=catalog_id, source="manual")
    with (data_dir / "acquisitions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(base)
    assert build_inventory_audit_presentation(data_dir=data_dir).newly_discovered[0]["acquisition_status"] == "known_acquisition_history"
    base["acquisition_id"] = "A2"
    with (data_dir / "acquisitions.csv").open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames).writerow(base)
    assert build_inventory_audit_presentation(data_dir=data_dir).newly_discovered[0]["acquisition_status"] == "multiple_acquisitions"


def test_missing_acquisition_repository_is_unknown_not_zero_history(tmp_path):
    data_dir = setup_state(tmp_path)
    (data_dir / "acquisitions.csv").unlink()
    presentation = build_inventory_audit_presentation(data_dir=data_dir)
    assert presentation.newly_discovered[0]["acquisition_status"] == "acquisition_context_unknown"
    metrics = {row["metric"]: row for row in presentation.summary}
    assert metrics["holdings_without_acquisition_history"]["value"] == "0"


def test_summary_metrics_reconcile_and_use_catalog_eligible_denominator(tmp_path):
    presentation = build_inventory_audit_presentation(data_dir=setup_state(tmp_path))
    metrics = {row["metric"]: row for row in presentation.summary}
    assert metrics["accepted_inventory_imports"]["value"] == "1"
    assert metrics["observations"]["value"] == "2"
    assert metrics["current_holdings"]["value"] == "1"
    assert metrics["physically_unresolved_observations"]["value"] == "1"
    assert metrics["catalog_linked_holdings"]["value"] == "1"
    assert metrics["catalog_linked_holdings"]["denominator"] == "1"
    assert metrics["catalog_reconciliation_eligible_holdings"]["value"] == "1"
    assert metrics["not_yet_audited_holdings"]["value"] == "0"
    assert metrics["outside_audit_scope_holdings"]["value"] == "0"
    assert metrics["libib_created_catalog_items"]["value"] == "1"
    assert metrics["quantity_review_cases"]["value"] == "1"
    assert metrics["successfully_reconciled_holdings"]["value"] == "1"


def test_zero_row_state_is_supported(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "catalog_items.csv").write_bytes(
        StrictCatalogRepository(data_dir / "catalog_items.csv").rendered_bytes([])
    )
    with (data_dir / "acquisitions.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=ACQUISITION_FIELDNAMES).writeheader()
    presentation = build_inventory_audit_presentation(data_dir=data_dir)
    metrics = {row["metric"]: row for row in presentation.summary}
    assert metrics["observations"]["value"] == "0"
    assert metrics["catalog_linked_holdings"]["denominator"] == "0"
    assert presentation.physical_review == presentation.catalog_review == []


def test_artifacts_are_deterministic_structured_and_do_not_mutate_repositories(tmp_path):
    data_dir = setup_state(tmp_path)
    before = {path: path.read_bytes() for path in sorted(data_dir.iterdir()) if path.is_file()}
    output_dir = tmp_path / "output"
    first = write_inventory_audit_artifacts(data_dir=data_dir, output_dir=output_dir)
    first_csv = (output_dir / "inventory_audit_summary.csv").read_bytes()
    first_xlsx = (output_dir / "inventory_review_workbook.xlsx").read_bytes()
    second = write_inventory_audit_artifacts(data_dir=data_dir, output_dir=output_dir)

    assert first == second
    assert (output_dir / "inventory_audit_summary.csv").read_bytes() == first_csv
    assert (output_dir / "inventory_review_workbook.xlsx").read_bytes() == first_xlsx
    assert {path: path.read_bytes() for path in sorted(data_dir.iterdir()) if path.is_file()} == before
    note = list(csv.DictReader((output_dir / "inventory_audit_summary.csv").open()))[0]
    assert note["value"] == "Generated output; edits are not imported."
    assert note["definition"] == GENERATED_NOTE

    with zipfile.ZipFile(output_dir / "inventory_review_workbook.xlsx") as workbook:
        assert workbook_sheet_names(workbook) == WORKBOOK_SHEETS
        for index in range(1, len(WORKBOOK_SHEETS) + 1):
            xml = workbook.read(f"xl/worksheets/sheet{index}.xml").decode("utf-8")
            assert 'state="frozen"' in xml
            assert "<autoFilter" in xml
            assert "raw_evidence_json" not in xml
        assert xml_header_values(workbook.read("xl/worksheets/sheet1.xml")) == [label for _, label in WORKBOOK_COLUMNS["Summary"]]
        assert xml_header_values(workbook.read("xl/worksheets/sheet2.xml")) == [label for _, label in WORKBOOK_COLUMNS["Physical Review"]]
        assert xml_header_values(workbook.read("xl/worksheets/sheet3.xml")) == [label for _, label in WORKBOOK_COLUMNS["Catalog Review"]]
        assert all("<f" not in workbook.read(f"xl/worksheets/sheet{index}.xml").decode("utf-8") for index in range(1, 10))


def test_artifacts_reject_non_output_directory(tmp_path):
    with pytest.raises(ValueError, match="output/"):
        write_inventory_audit_artifacts(data_dir=setup_state(tmp_path), output_dir=tmp_path / "reports")


def test_shared_workbook_writer_text_formats_only_isbn_named_columns(tmp_path):
    output = tmp_path / "isbn-format.xlsx"
    write_workbook(
        output,
        [("Values", ["isbn10", "normalized_isbn13", "count", "price", "observed_at"], [{
            "isbn10": "0306406152",
            "normalized_isbn13": "9780306406157",
            "count": "12",
            "price": "19.95",
            "observed_at": "2026-07-20T15:00:00Z",
        }])],
    )
    with zipfile.ZipFile(output) as workbook:
        xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert '<c r="A2" t="inlineStr" s="8"><is><t>0306406152</t>' in xml
    assert '<c r="B2" t="inlineStr" s="8"><is><t>9780306406157</t>' in xml
    for cell in ("C2", "D2", "E2"):
        assert f'<c r="{cell}" t="inlineStr" s="8">' not in xml
        assert f'<c r="{cell}" t="inlineStr" s="5">' in xml


def test_empty_workbook_has_professional_messages_visible_sheets_and_no_formulas(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "catalog_items.csv").write_bytes(
        StrictCatalogRepository(data_dir / "catalog_items.csv").rendered_bytes([])
    )
    with (data_dir / "acquisitions.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=ACQUISITION_FIELDNAMES).writeheader()
    output_dir = tmp_path / "output"
    write_inventory_audit_artifacts(data_dir=data_dir, output_dir=output_dir)

    with zipfile.ZipFile(output_dir / "inventory_review_workbook.xlsx") as workbook:
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
        assert workbook_sheet_names(workbook) == WORKBOOK_SHEETS
        assert 'state="hidden"' not in workbook_xml
        assert 'state="veryHidden"' not in workbook_xml
        for index, sheet_name in enumerate(WORKBOOK_SHEETS[1:], start=2):
            xml = workbook.read(f"xl/worksheets/sheet{index}.xml").decode("utf-8")
            assert EMPTY_SHEET_MESSAGES[sheet_name] in xml
            assert '<mergeCell ref="A2:' in xml
            assert "<f" not in xml


def test_workbook_places_reviewer_columns_before_technical_ids(tmp_path):
    output_dir = tmp_path / "output"
    write_inventory_audit_artifacts(data_dir=setup_state(tmp_path), output_dir=output_dir)
    with zipfile.ZipFile(output_dir / "inventory_review_workbook.xlsx") as workbook:
        physical = xml_header_values(workbook.read("xl/worksheets/sheet2.xml"))
        newly = xml_header_values(workbook.read("xl/worksheets/sheet4.xml"))
    assert physical[:3] == ["Suggested Next Step", "Book Title", "Author / Creator"]
    assert physical[-3:] == ["Candidate Holding IDs", "Observation ID", "Import ID"]
    assert newly[:3] == ["Suggested Next Step", "Book Title", "Author"]
    assert newly[-2:] == ["Catalog ID", "Holding ID"]


def test_summary_workbook_uses_collector_facing_metric_names(tmp_path):
    output_dir = tmp_path / "output"
    write_inventory_audit_artifacts(data_dir=setup_state(tmp_path), output_dir=output_dir)
    with zipfile.ZipFile(output_dir / "inventory_review_workbook.xlsx") as workbook:
        xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Physical identity issues" in xml
    assert "Catalog identity issues" in xml
    assert "New books discovered through Libib" in xml
    assert "physically_unresolved_observations" not in xml


def test_zip_metadata_is_fixed_for_deterministic_workbooks(tmp_path):
    output_dir = tmp_path / "output"
    write_inventory_audit_artifacts(data_dir=setup_state(tmp_path), output_dir=output_dir)
    with zipfile.ZipFile(output_dir / "inventory_review_workbook.xlsx") as workbook:
        assert {item.date_time for item in workbook.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def test_malformed_or_orphan_state_fails_before_artifact_generation(tmp_path):
    data_dir = setup_state(tmp_path)
    path = inventory_repository_paths(data_dir)["holdings"]
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows[0]["latest_inventory_observation_id"] = "IOB-missing"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(LibibRepositoryError, match="missing latest observation"):
        write_inventory_audit_artifacts(data_dir=data_dir, output_dir=tmp_path / "output")
    assert not (tmp_path / "output").exists()


def workbook_sheet_names(workbook):
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    return [sheet.attrib["name"] for sheet in root.findall("m:sheets/m:sheet", namespace)]


def xml_header_values(sheet_xml):
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(sheet_xml)
    first_row = root.find("m:sheetData/m:row", namespace)
    return ["".join(cell.itertext()) for cell in first_row]
