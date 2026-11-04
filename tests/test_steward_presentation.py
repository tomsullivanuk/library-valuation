import csv
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from valuation.libib_catalog import StrictCatalogRepository, reconcile_inventory_catalog
from valuation.libib_inventory import (
    InventoryObservationRepository,
    import_libib_inventory,
    inventory_repository_paths,
)
from valuation.market_evidence_summary import MARKET_EVIDENCE_SUMMARY_FIELDNAMES
from valuation.repositories import (
    ACQUISITION_FIELDNAMES,
    CATALOG_ITEMS_FIELDNAMES,
    COLLECTOR_REVIEW_FIELDNAMES,
    RESEARCH_ASSESSMENT_FIELDNAMES,
)
from valuation.research_candidates import RESEARCH_CANDIDATE_FIELDNAMES
from valuation.steward_presentation import (
    DerivedEvidenceInput,
    RegisteredReport,
    StewardPresentationError,
    _presentation_currency_value,
    build_steward_presentation,
)


FIXTURE = Path(__file__).parent / "fixtures" / "libib" / "study_export.csv"
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


def blank_row(fieldnames, **values):
    row = {field: "" for field in fieldnames}
    row.update(values)
    return row


def catalog_row(catalog_id="BK000001", **values):
    row = blank_row(
        CATALOG_ITEMS_FIELDNAMES,
        catalog_item_id=catalog_id,
        isbn13="9780306406157",
        isbn10="0306406152",
        title="Example Physics",
        author="Marie Curie",
        publisher="Example Press",
        publication_year="1980",
        match_confidence="high",
    )
    row.update(values)
    return row


def write_csv(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_catalog(data_dir: Path, rows):
    path = data_dir / "catalog_items.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(StrictCatalogRepository(path).rendered_bytes(list(rows)))
    return path


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def setup_inventory(tmp_path: Path):
    libib_root = tmp_path / "input" / "libib"
    source = libib_root / "study" / "library.csv"
    source.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURE, source)
    data_dir = tmp_path / "data"
    import_libib_inventory(
        source,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        audit_scope="Study",
        audit_completeness="partial_scope",
        now=lambda: NOW,
    )
    write_catalog(data_dir, [])
    write_csv(data_dir / "acquisitions.csv", ACQUISITION_FIELDNAMES, [])
    reconcile_inventory_catalog(data_dir=data_dir, now=lambda: NOW)
    return data_dir


def source_status(model, key):
    return next(source.status for source in model.snapshot.sources if source.source_key == key)


def test_minimum_catalog_only_state_is_useful_and_optional_sources_are_unavailable(tmp_path):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])

    model = build_steward_presentation(data_dir=data_dir)

    assert model.collection.catalog_item_count == 1
    assert model.books[0].catalog_item_id == "BK000001"
    assert model.books[0].acquisition_status == "unavailable"
    assert model.books[0].inventory_status == "unavailable"
    assert model.books[0].assessment_status == "unavailable"
    assert model.books[0].market_evidence_status == "unavailable"
    assert model.books[0].location_summary == "Location information not included"
    assert model.books[0].purchase_summary == "Acquisition history not included"
    assert model.books[0].resale_market_summary == ""
    assert model.books[0].disposition == "information_not_included"
    assert {source.status for source in model.snapshot.sources if source.source_key != "catalog"} == {
        "unavailable"
    }


def test_catalog_plus_inventory_preserves_entity_boundaries_and_cross_references(tmp_path):
    data_dir = setup_inventory(tmp_path)

    model = build_steward_presentation(data_dir=data_dir)

    assert source_status(model, "inventory") == "current"
    assert model.observations
    assert model.decisions
    assert model.holdings
    assert model.inventory_imports
    assert all(observation.inventory_observation_id for observation in model.observations)
    assert {
        observation.inventory_import_id for observation in model.observations
    } <= {row.inventory_import_id for row in model.inventory_imports}
    assert all(decision.inventory_observation_id for decision in model.decisions)
    assert any(
        observation.description == "A synthetic fixture, not a real library record."
        for observation in model.observations
    )
    for holding in model.holdings:
        assert set(holding.observation_ids) <= {
            observation.inventory_observation_id for observation in model.observations
        }
        if holding.catalog_item_id:
            book = next(
                row for row in model.books if row.catalog_item_id == holding.catalog_item_id
            )
            assert holding.holding_id in book.holding_ids
            if book.title == "Example Physics":
                assert book.description == "A synthetic fixture, not a real library record."
                assert book.copy_count == 1
                assert book.location_values == ("Study",)
                assert book.location_summary == "Study"


def test_catalog_plus_current_market_evidence_is_allowlisted_and_linked(tmp_path):
    data_dir = tmp_path / "data"
    catalog_path = write_catalog(data_dir, [catalog_row()])
    market_path = tmp_path / "derived" / "market.csv"
    write_csv(
        market_path,
        MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
        [
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000001",
                observed_source_names="AbeBooks",
                listing_count="3",
                evidence_status="available",
                market_confidence="medium",
                likely_low="20",
                likely_mid="30",
                likely_high="40",
                currency="USD",
                review_recommendation="Review comparable listings",
                review_reason="Limited comparable evidence",
                evidence_generated_at="2026-07-23T12:00:00Z",
                evidence_model_version="market_v1",
                evidence_notes="PRIVATE-NOT-PROJECTED",
            )
        ],
    )

    model = build_steward_presentation(
        data_dir=data_dir,
        market_evidence=DerivedEvidenceInput(
            market_path,
            catalog_snapshot_sha256=sha256(catalog_path),
            schema_version="market_v1",
            generated_at="2026-07-23T12:00:00Z",
        ),
    )

    assert source_status(model, "market_evidence") == "current"
    assert model.books[0].market_evidence_id == "market:BK000001"
    assert model.books[0].market_evidence_status == "current"
    assert model.books[0].resale_market_status == "estimate_available"
    assert model.books[0].resale_market_summary == "$20–40"
    assert model.books[0].estimated_value == "30"
    assert model.market_evidence[0].likely_mid == "30"
    assert model.recommendations[0].source_kind == "market_evidence"


def test_market_conclusions_distinguish_estimate_unreliable_and_not_researched(tmp_path):
    data_dir = tmp_path / "data"
    catalog_path = write_catalog(
        data_dir,
        [
            catalog_row("BK000001"),
            catalog_row("BK000002", isbn13="9780198786221", isbn10="0198786220"),
            catalog_row("BK000003", isbn13="9781402894626", isbn10="1402894627"),
        ],
    )
    market_path = tmp_path / "derived" / "market.csv"
    write_csv(
        market_path,
        MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
        [
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000001",
                evidence_status="observed_listings",
                likely_mid="30",
                currency="USD",
            ),
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000002",
                evidence_status="source_unavailable",
            ),
        ],
    )
    model = build_steward_presentation(
        data_dir=data_dir,
        market_evidence=DerivedEvidenceInput(
            market_path,
            catalog_snapshot_sha256=sha256(catalog_path),
            schema_version="market_v1",
        ),
    )

    assert {
        row.catalog_item_id: row.resale_market_status for row in model.books
    } == {
        "BK000001": "estimate_available",
        "BK000002": "no_reliable_estimate",
        "BK000003": "not_researched",
    }


@pytest.mark.parametrize(
    ("value", "presented"),
    [
        ("0.25", "0"),
        ("0.49", "0"),
        ("0.50", "1"),
        ("0.75", "1"),
        ("1.49", "1"),
        ("1.50", "2"),
        ("1.92", "2"),
        ("1.94", "2"),
        ("12.49", "12"),
        ("12.50", "13"),
        ("15.99", "16"),
        ("70.73", "71"),
        ("81.56", "82"),
    ],
)
def test_market_card_values_use_nearest_unit_half_up(value, presented):
    assert _presentation_currency_value(value) == presented


def test_market_cards_round_all_values_without_changing_underlying_precision(tmp_path):
    data_dir = tmp_path / "data"
    catalog_path = write_catalog(
        data_dir,
        [
            catalog_row("BK000001"),
            catalog_row("BK000002", isbn13="9780198786221", isbn10="0198786220"),
            catalog_row("BK000003", isbn13="", isbn10=""),
            catalog_row("BK000004", isbn13="", isbn10=""),
            catalog_row("BK000005", isbn13="", isbn10=""),
            catalog_row("BK000006", isbn13="", isbn10=""),
            catalog_row("BK000007", isbn13="", isbn10=""),
            catalog_row("BK000008", isbn13="", isbn10=""),
        ],
    )
    market_path = tmp_path / "derived" / "market.csv"
    write_csv(
        market_path,
        MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
        [
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000001",
                evidence_status="observed_listings",
                likely_low="187.09",
                likely_mid="370.01",
                likely_high="552.93",
                currency="USD",
            ),
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000002",
                evidence_status="observed_listings",
                likely_low="0.25",
                likely_mid="0.50",
                likely_high="0.75",
                currency="USD",
            ),
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000003",
                evidence_status="observed_listings",
                likely_low="1.92",
                likely_mid="1.92",
                likely_high="9.42",
                currency="USD",
            ),
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000004",
                evidence_status="observed_listings",
                likely_low="1.94",
                likely_mid="1.94",
                currency="USD",
            ),
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000005",
                evidence_status="observed_listings",
                likely_low="70.73",
                likely_mid="76.14",
                likely_high="81.56",
                currency="GBP",
            ),
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000006",
                evidence_status="observed_listings",
                likely_low="12.49",
                likely_mid="14.24",
                likely_high="15.99",
                currency="CHF",
            ),
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000007",
                evidence_status="observed_listings",
                likely_mid="1995.96",
                currency="USD",
            ),
        ],
    )
    model = build_steward_presentation(
        data_dir=data_dir,
        market_evidence=DerivedEvidenceInput(
            market_path,
            catalog_snapshot_sha256=sha256(catalog_path),
            schema_version="market_v1",
        ),
    )
    books = {row.catalog_item_id: row for row in model.books}

    assert books["BK000001"].estimated_value == "370.01"
    assert (
        books["BK000001"].estimated_value_precise_low,
        books["BK000001"].estimated_value_precise_high,
        books["BK000001"].estimated_value_currency,
    ) == ("187.09", "552.93", "USD")
    assert (
        books["BK000001"].estimated_value_sort_low,
        books["BK000001"].estimated_value_sort_high,
    ) == ("187", "553")
    assert books["BK000001"].resale_market_summary == "$187.09–552.93"
    assert books["BK000001"].resale_market_card_summary == "$187–$553"
    assert (
        books["BK000002"].estimated_value_sort_low,
        books["BK000002"].estimated_value_sort_high,
    ) == ("0", "1")
    assert books["BK000002"].resale_market_summary == "$0.25–0.75"
    assert books["BK000002"].resale_market_card_summary == "$0–$1"
    assert (
        books["BK000003"].estimated_value_sort_low,
        books["BK000003"].estimated_value_sort_high,
        books["BK000003"].resale_market_card_summary,
    ) == ("2", "9", "$2–$9")
    assert (
        books["BK000004"].estimated_value_sort_low,
        books["BK000004"].estimated_value_sort_high,
        books["BK000004"].resale_market_card_summary,
    ) == ("2", "2", "$2")
    assert (
        books["BK000004"].estimated_value_precise_low,
        books["BK000004"].estimated_value_precise_high,
    ) == ("1.94", "1.94")
    assert (
        books["BK000005"].estimated_value_sort_low,
        books["BK000005"].estimated_value_sort_high,
        books["BK000005"].resale_market_card_summary,
    ) == ("71", "82", "£71–£82")
    assert books["BK000006"].resale_market_card_summary == "CHF 12–CHF 16"
    assert (
        books["BK000007"].estimated_value_precise_low,
        books["BK000007"].estimated_value_precise_high,
        books["BK000007"].estimated_value_currency,
        books["BK000007"].resale_market_card_summary,
    ) == ("1995.96", "1995.96", "USD", "$1,996")
    assert (
        books["BK000008"].estimated_value_precise_low,
        books["BK000008"].estimated_value_precise_high,
        books["BK000008"].estimated_value_currency,
        books["BK000008"].estimated_value_display,
        books["BK000008"].resale_market_card_summary,
    ) == ("", "", "", "", "Not researched")
    assert books["BK000003"].resale_market_summary == "$1.92–9.42"
    assert books["BK000005"].resale_market_summary == "£70.73–81.56"
    assert books["BK000006"].resale_market_summary == "CHF 12.49–15.99"
    assert b"PRIVATE-NOT-PROJECTED" not in model.to_json_bytes()


def test_complete_available_state_includes_all_concepts_and_registered_report(tmp_path):
    data_dir = setup_inventory(tmp_path)
    catalog_path = data_dir / "catalog_items.csv"
    catalog = StrictCatalogRepository(catalog_path).load()
    catalog_id = catalog[0]["catalog_item_id"]
    write_csv(
        data_dir / "acquisitions.csv",
        ACQUISITION_FIELDNAMES,
        [
            blank_row(
                ACQUISITION_FIELDNAMES,
                acquisition_id="ACQ-1",
                catalog_item_id=catalog_id,
                source="amazon",
                order_date="2020-01-02",
                quantity="1",
                currency="USD",
                source_order_id="PRIVATE-ORDER",
            )
        ],
    )
    write_csv(
        data_dir / "research_priority_assessments.csv",
        RESEARCH_ASSESSMENT_FIELDNAMES,
        [
            blank_row(
                RESEARCH_ASSESSMENT_FIELDNAMES,
                catalog_item_id=catalog_id,
                research_priority_score="8",
                research_priority_band="high",
                research_signal_count="2",
                research_signal_codes="older;university_press",
                research_signal_summary="Research priority evidence",
                research_model_version="research_v1",
                research_config_hash="config-hash",
                assessed_at="2026-07-01",
                assessment_status="current",
                acquisition_snapshot_hash="acquisition-hash",
                metadata_snapshot_hash="metadata-hash",
            )
        ],
    )
    write_csv(
        data_dir / "collector_reviews.csv",
        COLLECTOR_REVIEW_FIELDNAMES,
        [
            blank_row(
                COLLECTOR_REVIEW_FIELDNAMES,
                catalog_item_id=catalog_id,
                workflow_state="review",
                disposition="keep",
                priority_override="high",
                reviewed_at="2026-07-02",
                review_notes="Steward note",
                reviewed_by="PRIVATE-NAME",
            )
        ],
    )
    market_path = tmp_path / "derived" / "market.csv"
    write_csv(
        market_path,
        MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
        [
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id=catalog_id,
                evidence_status="available",
                market_confidence="high",
                review_recommendation="Review for sale research",
                review_reason="Evidence is available",
            )
        ],
    )
    candidates_path = tmp_path / "derived" / "candidates.csv"
    write_csv(
        candidates_path,
        RESEARCH_CANDIDATE_FIELDNAMES,
        [
            blank_row(
                RESEARCH_CANDIDATE_FIELDNAMES,
                catalog_item_id=catalog_id,
                research_priority_band="high",
                research_signal_codes="older",
                research_signal_summary="Review this candidate",
                reviewed_by="PRIVATE-CANDIDATE-NAME",
            )
        ],
    )
    report_path = tmp_path / "output" / "inventory.xlsx"
    report_path.parent.mkdir()
    report_path.write_bytes(b"synthetic report")
    catalog_hash = sha256(catalog_path)

    model = build_steward_presentation(
        data_dir=data_dir,
        market_evidence=DerivedEvidenceInput(
            market_path, catalog_snapshot_sha256=catalog_hash, schema_version="market_v1"
        ),
        research_candidates=DerivedEvidenceInput(
            candidates_path,
            catalog_snapshot_sha256=catalog_hash,
            schema_version="candidate_v1",
        ),
        reports=(
            RegisteredReport(
                report_key="inventory_review",
                name="Inventory Review",
                purpose="Review inventory questions",
                audience="Steward",
                format="xlsx",
                source_path=report_path,
                public_path="inventory.xlsx",
                producing_workflow="update-inventory",
                catalog_snapshot_sha256=catalog_hash,
            ),
        ),
        generated_at="2026-07-23T12:00:00Z",
    )

    book = next(row for row in model.books if row.catalog_item_id == catalog_id)
    assert book.acquisition_status == "current"
    assert book.assessment_id == f"assessment:{catalog_id}"
    assert book.steward_review_id == f"review:{catalog_id}"
    assert book.market_evidence_id == f"market:{catalog_id}"
    assert book.purchase_summary == "Amazon • Jan 2020"
    assert book.purchase_date == "2020-01-02"
    assert book.acquisition_source == "Amazon"
    assert book.acquisition_month == "2020-01"
    assert book.acquisition_count == 1
    assert book.disposition == "keep"
    assert model.reports[0].status == "current"
    assert model.assessments[0].config_hash == "config-hash"
    assert model.assessments[0].acquisition_snapshot_hash == "acquisition-hash"
    assert model.collection.report_count == 1
    assert any(
        row.source_kind == "steward_priority"
        and row.entity_id == catalog_id
        and row.advisory
        for row in model.recommendations
    )
    serialized = model.to_json_bytes()
    assert b"PRIVATE-ORDER" not in serialized
    assert b"PRIVATE-NAME" not in serialized
    assert b"PRIVATE-CANDIDATE-NAME" not in serialized


@pytest.mark.parametrize("missing_name", ["inventory_imports.csv", "inventory_holdings.csv"])
def test_partial_inventory_subsystem_fails_closed(tmp_path, missing_name):
    data_dir = setup_inventory(tmp_path)
    (data_dir / missing_name).unlink()

    with pytest.raises(StewardPresentationError, match="Incomplete inventory subsystem"):
        build_steward_presentation(data_dir=data_dir)


def test_missing_or_malformed_required_catalog_fails_closed(tmp_path):
    with pytest.raises(StewardPresentationError, match="missing"):
        build_steward_presentation(data_dir=tmp_path / "data")

    data_dir = tmp_path / "malformed"
    write_csv(data_dir / "catalog_items.csv", ["wrong"], [{"wrong": "value"}])
    with pytest.raises(StewardPresentationError, match="header"):
        build_steward_presentation(data_dir=data_dir)


def test_stale_and_incompatible_derived_evidence_are_explicit_and_non_authoritative(tmp_path):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])
    stale_path = tmp_path / "stale.csv"
    write_csv(
        stale_path,
        MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
        [
            blank_row(
                MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
                catalog_item_id="BK000001",
                review_recommendation="Do not use stale guidance",
            )
        ],
    )
    stale = build_steward_presentation(
        data_dir=data_dir,
        market_evidence=DerivedEvidenceInput(
            stale_path, catalog_snapshot_sha256="0" * 64
        ),
    )
    assert source_status(stale, "market_evidence") == "stale"
    assert stale.market_evidence[0].status == "stale"
    assert not stale.recommendations
    assert stale.snapshot.warnings

    incompatible_path = tmp_path / "incompatible.csv"
    write_csv(incompatible_path, ["catalog_item_id", "unexpected"], [])
    incompatible = build_steward_presentation(
        data_dir=data_dir,
        market_evidence=DerivedEvidenceInput(incompatible_path),
    )
    assert source_status(incompatible, "market_evidence") == "incompatible"
    assert incompatible.market_evidence == ()


def test_stable_deterministic_output_and_changed_source_changes_snapshot(tmp_path):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])

    first = build_steward_presentation(data_dir=data_dir)
    second = build_steward_presentation(data_dir=data_dir)
    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
    assert first.to_json_bytes() == second.to_json_bytes()

    write_catalog(data_dir, [catalog_row(title="Changed title")])
    changed = build_steward_presentation(data_dir=data_dir)
    assert changed.snapshot.snapshot_id != first.snapshot.snapshot_id
    assert changed.to_json_bytes() != first.to_json_bytes()


def test_duplicate_historical_acquisition_ids_get_stable_presentation_references(tmp_path):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])
    duplicate = blank_row(
        ACQUISITION_FIELDNAMES,
        acquisition_id="AMZ-COLLISION",
        catalog_item_id="BK000001",
        source="amazon",
        quantity="1",
    )
    write_csv(data_dir / "acquisitions.csv", ACQUISITION_FIELDNAMES, [duplicate, duplicate])

    model = build_steward_presentation(data_dir=data_dir)

    assert [row.acquisition_id for row in model.acquisitions] == [
        "AMZ-COLLISION",
        "AMZ-COLLISION",
    ]
    assert [row.acquisition_reference for row in model.acquisitions] == [
        "acquisition:AMZ-COLLISION:1",
        "acquisition:AMZ-COLLISION:2",
    ]
    assert model.books[0].acquisition_ids == (
        "acquisition:AMZ-COLLISION:1",
        "acquisition:AMZ-COLLISION:2",
    )
    assert model.books[0].purchase_summary == "2 records"
    assert model.books[0].acquisition_count == 2
    assert model.books[0].acquisition_source == "Amazon"
    assert model.books[0].acquisition_month == ""


def test_acquisition_export_summary_uses_latest_parsed_record_and_stable_ties(tmp_path):
    data_dir = tmp_path / "data"
    write_catalog(
        data_dir,
        [
            catalog_row("BK000001"),
            catalog_row("BK000002", isbn13="", isbn10=""),
            catalog_row("BK000003", isbn13="", isbn10=""),
            catalog_row("BK000004", isbn13="", isbn10=""),
            catalog_row("BK000005", isbn13="", isbn10=""),
        ],
    )
    write_csv(
        data_dir / "acquisitions.csv",
        ACQUISITION_FIELDNAMES,
        [
            blank_row(
                ACQUISITION_FIELDNAMES,
                acquisition_id="ACQ-1",
                catalog_item_id="BK000001",
                source="amazon",
                order_date="2021-02-17T14:37:22Z",
            ),
            blank_row(
                ACQUISITION_FIELDNAMES,
                acquisition_id="ACQ-2A",
                catalog_item_id="BK000002",
                source="amazon",
                order_date="2021-02-17T14:37:22Z",
            ),
            blank_row(
                ACQUISITION_FIELDNAMES,
                acquisition_id="ACQ-2B",
                catalog_item_id="BK000002",
                source="gift",
                order_date="2026-05-04T09:15:00Z",
            ),
            blank_row(
                ACQUISITION_FIELDNAMES,
                acquisition_id="ACQ-3",
                catalog_item_id="BK000003",
                source="estate",
                order_date="",
            ),
            blank_row(
                ACQUISITION_FIELDNAMES,
                acquisition_id="ACQ-5A",
                catalog_item_id="BK000005",
                source="amazon",
                order_date="2026-05-04T09:15:00Z",
            ),
            blank_row(
                ACQUISITION_FIELDNAMES,
                acquisition_id="ACQ-5B",
                catalog_item_id="BK000005",
                source="gift",
                order_date="2026-05-04T09:15:00Z",
            ),
        ],
    )

    first = build_steward_presentation(data_dir=data_dir)
    second = build_steward_presentation(data_dir=data_dir)
    books = {book.catalog_item_id: book for book in first.books}

    assert (
        books["BK000001"].acquisition_source,
        books["BK000001"].acquisition_month,
        books["BK000001"].acquisition_count,
    ) == ("Amazon", "2021-02", 1)
    assert (
        books["BK000002"].acquisition_source,
        books["BK000002"].acquisition_month,
        books["BK000002"].acquisition_count,
        books["BK000002"].purchase_summary,
    ) == ("Gift", "2026-05", 2, "2 records • latest May 2026")
    assert (
        books["BK000003"].acquisition_source,
        books["BK000003"].acquisition_month,
        books["BK000003"].acquisition_count,
    ) == ("Estate", "", 1)
    assert (
        books["BK000004"].acquisition_source,
        books["BK000004"].acquisition_month,
        books["BK000004"].acquisition_count,
    ) == ("", "", 0)
    assert (
        books["BK000005"].acquisition_source,
        books["BK000005"].acquisition_month,
        books["BK000005"].acquisition_count,
    ) == ("Gift", "2026-05", 2)
    assert first.to_json_bytes() == second.to_json_bytes()


def test_observation_raw_evidence_and_local_paths_are_not_projected(tmp_path):
    data_dir = setup_inventory(tmp_path)
    path = inventory_repository_paths(data_dir)["observations"]
    repository = InventoryObservationRepository(path)
    rows = repository.load()
    rows[0]["raw_evidence_json"] = '{"private_secret":"DO-NOT-EXPOSE"}'
    rows[0]["source_reference"] = "/Users/private/library.csv:2"
    path.write_bytes(repository.rendered_bytes(rows))

    model = build_steward_presentation(data_dir=data_dir)
    payload = model.to_json_bytes()

    assert b"raw_evidence_json" not in payload
    assert b"DO-NOT-EXPOSE" not in payload
    assert b"/Users/private" not in payload


def test_model_build_is_read_only(tmp_path):
    data_dir = setup_inventory(tmp_path)
    before = {path: path.read_bytes() for path in data_dir.iterdir() if path.is_file()}

    build_steward_presentation(data_dir=data_dir)

    after = {path: path.read_bytes() for path in data_dir.iterdir() if path.is_file()}
    assert after == before


def test_synthetic_real_catalog_scale_is_supported(tmp_path):
    data_dir = tmp_path / "data"
    rows = [
        catalog_row(
            f"BK{index:06d}",
            isbn13=f"978000{index:07d}"[-13:],
            isbn10="",
            title=f"Synthetic Book {index}",
        )
        for index in range(1, 3015)
    ]
    write_catalog(data_dir, rows)

    model = build_steward_presentation(data_dir=data_dir)

    assert model.collection.catalog_item_count == 3014
    assert len(model.books) == 3014
    assert model.books[0].catalog_item_id == "BK000001"
    assert model.books[-1].catalog_item_id == "BK003014"


def test_research_reasons_explain_recorded_points_without_rescoring():
    from valuation.steward_presentation import _plain_research_reasons
    text=_plain_research_reasons('missing_oclc:+5; scholarly_lc_subject:+10; university_press:+15')
    assert text==('A library catalog identifier is missing, making edition matching harder (+5 points); '
                  'Its library subject classification suggests scholarly interest (+10 points); '
                  'Published by a university press (+15 points)')
    assert _plain_research_reasons('university_press:+7')=='Published by a university press (+7 points)'
    assert _plain_research_reasons('', 'Existing explanation')=='Existing explanation'
    assert _plain_research_reasons('future_signal:+4')=='Future signal (+4 points)'
