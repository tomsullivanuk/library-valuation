import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import valuation.libib_inventory as libib_inventory
from valuation.libib_catalog import (
    ACCEPTED_CATALOG_OUTCOMES,
    CATALOG_RECONCILIATION_OUTCOMES,
    INVENTORY_CATALOG_RECONCILIATION_DECISION_FIELDNAMES,
    InventoryCatalogReconciliationDecisionRepository,
    LibibCatalogReconciliationError,
    StrictCatalogRepository,
    catalog_reconciliation_repository_path,
    reconcile_inventory_catalog,
    supersede_inventory_catalog_reconciliation_decision,
)
from valuation.libib_inventory import (
    InventoryHoldingRepository,
    InventoryObservationRepository,
    InventoryReconciliationDecisionRepository,
    LibibRepositoryError,
    import_libib_inventory,
    inventory_repository_paths,
)
from valuation.repositories import CATALOG_ITEMS_FIELDNAMES


FIXTURE = Path(__file__).parent / "fixtures" / "libib" / "study_export.csv"
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)


def setup_state(tmp_path: Path, *, transform=None):
    export = tmp_path / "input" / "one.csv"
    export.parent.mkdir(parents=True)
    rows = list(csv.DictReader(FIXTURE.open(newline="", encoding="utf-8")))
    row = dict(rows[0])
    if transform:
        transform(row)
    with export.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, now=lambda: NOW)
    return data_dir


def catalog_row(catalog_id="BK000001", **values):
    row = {field: "" for field in CATALOG_ITEMS_FIELDNAMES}
    row.update(
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


def write_catalog(data_dir: Path, rows):
    repository = StrictCatalogRepository(data_dir / "catalog_items.csv")
    (data_dir / "catalog_items.csv").write_bytes(repository.rendered_bytes(list(rows)))


def load_state(data_dir: Path):
    paths = inventory_repository_paths(data_dir)
    return {
        "holdings": InventoryHoldingRepository(paths["holdings"]).load(),
        "observations": InventoryObservationRepository(paths["observations"]).load(),
        "physical_decisions": InventoryReconciliationDecisionRepository(paths["decisions"]).load(),
        "catalog": StrictCatalogRepository(data_dir / "catalog_items.csv").load(),
        "catalog_decisions": InventoryCatalogReconciliationDecisionRepository(
            catalog_reconciliation_repository_path(data_dir)
        ).load(),
    }


def test_unique_isbn13_links_existing_catalog_without_metadata_or_acquisition_mutation(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row()])
    canonical_before = StrictCatalogRepository(data_dir / "catalog_items.csv").load()

    result = reconcile_inventory_catalog(data_dir=data_dir, now=lambda: NOW)
    state = load_state(data_dir)

    assert result.holdings_linked == result.accepted_count == 1
    assert dict(result.outcome_counts) == {"existing_catalog_item_linked": 1}
    assert state["holdings"][0]["catalog_item_id"] == "BK000001"
    assert state["catalog"] == canonical_before
    assert state["catalog_decisions"][0]["decision_basis"] == "exact_isbn13"
    assert not (data_dir / "acquisitions.csv").exists()


def test_isbn10_derived_match_is_explicit_and_dual_isbn_is_consistent(tmp_path):
    def only_isbn10(row):
        row["ean_isbn13"] = ""

    data_dir = setup_state(tmp_path, transform=only_isbn10)
    write_catalog(data_dir, [catalog_row(isbn13="", isbn10="0306406152")])

    reconcile_inventory_catalog(data_dir=data_dir, now=lambda: NOW)
    decision = load_state(data_dir)["catalog_decisions"][0]

    assert decision["outcome"] == "existing_catalog_item_linked"
    assert decision["decision_basis"] == "isbn10_derived_isbn13"


def test_conflicting_valid_isbns_are_unresolved_and_nonmutating(tmp_path):
    data_dir = setup_state(tmp_path)
    observation_path = inventory_repository_paths(data_dir)["observations"]
    observations = InventoryObservationRepository(observation_path).load()
    observations[0]["normalized_isbn10"] = "0198786220"
    observations[0]["diagnostic_codes_json"] = '["isbn_conflict"]'
    observation_path.write_bytes(InventoryObservationRepository(observation_path).rendered_bytes(observations))
    write_catalog(data_dir, [catalog_row()])

    result = reconcile_inventory_catalog(data_dir=data_dir)

    assert dict(result.outcome_counts) == {"conflicting_isbn_evidence": 1}
    assert load_state(data_dir)["holdings"][0]["catalog_item_id"] == ""


def test_conflicting_valid_isbns_on_catalog_candidate_are_unresolved(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row(isbn10="0198786220")])

    result = reconcile_inventory_catalog(data_dir=data_dir)

    assert dict(result.outcome_counts) == {"conflicting_isbn_evidence": 1}
    assert load_state(data_dir)["holdings"][0]["catalog_item_id"] == ""


def test_duplicate_isbn_catalog_candidates_require_review(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row("BK000001"), catalog_row("BK000002")])

    result = reconcile_inventory_catalog(data_dir=data_dir)
    decision = load_state(data_dir)["catalog_decisions"][0]

    assert dict(result.outcome_counts) == {"multiple_catalog_candidates": 1}
    assert json.loads(decision["candidate_catalog_item_ids_json"]) == ["BK000001", "BK000002"]
    assert load_state(data_dir)["holdings"][0]["catalog_item_id"] == ""


def test_title_creator_publisher_can_link_but_title_or_creator_only_cannot(tmp_path):
    def no_isbn(row):
        row["ean_isbn13"] = row["upc_isbn10"] = ""

    data_dir = setup_state(tmp_path, transform=no_isbn)
    write_catalog(data_dir, [catalog_row(isbn13="", isbn10="")])
    linked = reconcile_inventory_catalog(data_dir=data_dir)
    assert dict(linked.outcome_counts) == {"existing_catalog_item_linked": 1}
    assert load_state(data_dir)["catalog_decisions"][0]["decision_basis"] == "title_creator_publisher"

    data_dir = setup_state(tmp_path / "title")
    observation_path = inventory_repository_paths(data_dir)["observations"]
    observations = InventoryObservationRepository(observation_path).load()
    observations[0].update(normalized_isbn13="", normalized_isbn10="", normalized_creators="")
    observation_path.write_bytes(InventoryObservationRepository(observation_path).rendered_bytes(observations))
    write_catalog(data_dir, [catalog_row(isbn13="", isbn10="")])
    unresolved = reconcile_inventory_catalog(data_dir=data_dir)
    assert dict(unresolved.outcome_counts) == {"catalog_candidate_requires_review": 1}

    data_dir = setup_state(tmp_path / "creator")
    observation_path = inventory_repository_paths(data_dir)["observations"]
    observations = InventoryObservationRepository(observation_path).load()
    observations[0].update(normalized_isbn13="", normalized_isbn10="", normalized_title="")
    observation_path.write_bytes(InventoryObservationRepository(observation_path).rendered_bytes(observations))
    write_catalog(data_dir, [catalog_row(isbn13="", isbn10="")])
    unresolved = reconcile_inventory_catalog(data_dir=data_dir)
    assert dict(unresolved.outcome_counts) == {"catalog_candidate_requires_review": 1}


def test_title_creator_multiple_candidates_require_review(tmp_path):
    def no_isbn(row):
        row["ean_isbn13"] = row["upc_isbn10"] = ""

    data_dir = setup_state(tmp_path, transform=no_isbn)
    write_catalog(
        data_dir,
        [
            catalog_row("BK000001", isbn13="", isbn10="", publisher="Other Press"),
            catalog_row("BK000002", isbn13="", isbn10="", publisher="Second Press"),
        ],
    )
    result = reconcile_inventory_catalog(data_dir=data_dir)
    assert dict(result.outcome_counts) == {"multiple_catalog_candidates": 1}


@pytest.mark.parametrize("status", ["excluded", "merged", "invalid"])
def test_ineligible_catalog_candidate_is_not_linked(tmp_path, status):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row()])

    result = reconcile_inventory_catalog(
        data_dir=data_dir, catalog_status_by_id={"BK000001": status}
    )

    assert dict(result.outcome_counts) == {"catalog_candidate_ineligible": 1}
    assert load_state(data_dir)["holdings"][0]["catalog_item_id"] == ""


def test_strong_libib_only_evidence_creates_catalog_and_link_without_acquisition(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [])

    result = reconcile_inventory_catalog(data_dir=data_dir, now=lambda: NOW)
    state = load_state(data_dir)

    assert result.catalog_items_created == result.holdings_linked == 1
    assert dict(result.outcome_counts) == {"new_catalog_item_created": 1}
    assert state["catalog"][0]["catalog_item_id"] == "BK000001"
    assert state["catalog"][0]["source_fingerprint"] == state["observations"][0]["source_row_fingerprint"]
    assert state["catalog"][0]["publication_year"] == ""
    assert state["holdings"][0]["catalog_item_id"] == "BK000001"
    assert "no_acquisition_created" in json.loads(state["catalog_decisions"][0]["reason_codes_json"])
    assert not (data_dir / "acquisitions.csv").exists()


def test_weak_no_isbn_evidence_does_not_create_catalog(tmp_path):
    def no_isbn(row):
        row["ean_isbn13"] = row["upc_isbn10"] = ""

    data_dir = setup_state(tmp_path, transform=no_isbn)
    write_catalog(data_dir, [])

    result = reconcile_inventory_catalog(data_dir=data_dir)

    assert dict(result.outcome_counts) == {"insufficient_catalog_evidence": 1}
    assert load_state(data_dir)["catalog"] == []


def test_grouped_or_multivolume_title_does_not_create_catalog(tmp_path):
    data_dir = setup_state(tmp_path, transform=lambda row: row.update(title="Synthetic Physics Box Set"))
    write_catalog(data_dir, [])

    result = reconcile_inventory_catalog(data_dir=data_dir)

    assert dict(result.outcome_counts) == {"edition_or_catalog_identity_ambiguity": 1}
    assert load_state(data_dir)["catalog"] == []


def test_exact_isbn_with_conflicting_title_requires_review(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row(title="Mediterranean Cooking Handbook", author="Unrelated Writer")])

    result = reconcile_inventory_catalog(data_dir=data_dir)

    assert dict(result.outcome_counts) == {"edition_or_catalog_identity_ambiguity": 1}
    assert load_state(data_dir)["holdings"][0]["catalog_item_id"] == ""


def test_exact_isbn_allows_subtitle_and_contributor_variants(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(
        data_dir,
        [catalog_row(title="Example Physics: An Extended Subtitle", author="Marie Curie; Another Contributor")],
    )

    result = reconcile_inventory_catalog(data_dir=data_dir)

    assert dict(result.outcome_counts) == {"existing_catalog_item_linked": 1}
    assert load_state(data_dir)["holdings"][0]["catalog_item_id"] == "BK000001"


def test_arbitrary_raw_evidence_keys_cannot_create_or_match_catalog(tmp_path):
    data_dir = setup_state(tmp_path)
    observation_path = inventory_repository_paths(data_dir)["observations"]
    observations = InventoryObservationRepository(observation_path).load()
    observations[0].update(
        normalized_isbn13="", normalized_isbn10="", normalized_title="", normalized_creators="",
        raw_evidence_json='{"isbn13":"9780306406157","title":"Example Physics","creators":"Marie Curie"}',
    )
    observation_path.write_bytes(InventoryObservationRepository(observation_path).rendered_bytes(observations))
    write_catalog(data_dir, [catalog_row()])

    result = reconcile_inventory_catalog(data_dir=data_dir)

    assert dict(result.outcome_counts) == {"insufficient_catalog_evidence": 1}
    assert load_state(data_dir)["holdings"][0]["catalog_item_id"] == ""


def test_repeat_reconciliation_is_idempotent_and_order_independent(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row("BK000002"), catalog_row("BK000001", isbn13="9780198786221", isbn10="0198786220")])
    first = reconcile_inventory_catalog(data_dir=data_dir)
    before = {path: path.read_bytes() for path in [
        data_dir / "catalog_items.csv",
        data_dir / "inventory_holdings.csv",
        catalog_reconciliation_repository_path(data_dir),
    ]}

    second = reconcile_inventory_catalog(data_dir=data_dir)

    assert first.decisions_created == 1
    assert second.decisions_created == 0
    assert before == {path: path.read_bytes() for path in before}


def test_new_accepted_physical_observation_creates_superseding_catalog_confirmation(tmp_path):
    libib_root = tmp_path / "input" / "libib"
    area = libib_root / "study"
    export = area / "one.csv"
    export.parent.mkdir(parents=True)
    rows = list(csv.DictReader(FIXTURE.open(newline="", encoding="utf-8")))
    with export.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerow(rows[0])
    data_dir = tmp_path / "data"
    import_libib_inventory(export, data_dir=data_dir, libib_input_dir=libib_root, now=lambda: NOW)
    write_catalog(data_dir, [catalog_row()])
    reconcile_inventory_catalog(data_dir=data_dir, now=lambda: NOW)
    first = load_state(data_dir)["catalog_decisions"][0]
    lines = export.read_text(encoding="utf-8").splitlines()
    export.write_text("\n".join([lines[0], lines[1]]) + "\n", encoding="utf-8")
    # Change file bytes without changing identity-bearing row evidence.
    export.write_text(export.read_text(encoding="utf-8").replace("2026-07-19", "2026-07-20"), encoding="utf-8")
    import_libib_inventory(
        export, data_dir=data_dir, libib_input_dir=libib_root,
        now=lambda: datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    result = reconcile_inventory_catalog(data_dir=data_dir, now=lambda: datetime(2026, 7, 21, tzinfo=timezone.utc))
    decisions = load_state(data_dir)["catalog_decisions"]

    assert dict(result.outcome_counts) == {"existing_catalog_item_confirmed": 1}
    assert len(decisions) == 2
    assert decisions[1]["supersedes_decision_id"] == first["inventory_catalog_reconciliation_decision_id"]
    assert decisions[1]["inventory_observation_id"] != first["inventory_observation_id"]


def test_existing_link_confirmation_and_no_silent_relink(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row("BK000001"), catalog_row("BK000002", isbn13="9780198786221", isbn10="0198786220")])
    holdings_path = inventory_repository_paths(data_dir)["holdings"]
    holdings = InventoryHoldingRepository(holdings_path).load()
    holdings[0]["catalog_item_id"] = "BK000001"
    holdings_path.write_bytes(InventoryHoldingRepository(holdings_path).rendered_bytes(holdings))

    confirmed = reconcile_inventory_catalog(data_dir=data_dir)
    assert dict(confirmed.outcome_counts) == {"existing_catalog_item_confirmed": 1}

    data_dir = setup_state(tmp_path / "relink")
    write_catalog(data_dir, [catalog_row("BK000001", isbn13="9780198786221", isbn10="0198786220"), catalog_row("BK000002")])
    holdings_path = inventory_repository_paths(data_dir)["holdings"]
    holdings = InventoryHoldingRepository(holdings_path).load()
    holdings[0]["catalog_item_id"] = "BK000001"
    holdings_path.write_bytes(InventoryHoldingRepository(holdings_path).rendered_bytes(holdings))
    proposed = reconcile_inventory_catalog(data_dir=data_dir)
    assert dict(proposed.outcome_counts) == {"catalog_relink_requires_review": 1}
    assert load_state(data_dir)["holdings"][0]["catalog_item_id"] == "BK000001"


def test_physical_unresolved_state_blocks_catalog_reconciliation(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row()])
    physical_path = inventory_repository_paths(data_dir)["decisions"]
    decisions = InventoryReconciliationDecisionRepository(physical_path).load()
    decisions[0]["outcome"] = "manual_review_required"
    decisions[0]["holding_id"] = ""
    physical_path.write_bytes(InventoryReconciliationDecisionRepository(physical_path).rendered_bytes(decisions))

    result = reconcile_inventory_catalog(data_dir=data_dir)

    assert result.decisions_created == 0
    assert not catalog_reconciliation_repository_path(data_dir).exists()


def test_manual_supersession_appends_without_deleting_prior_and_updates_link(tmp_path):
    def no_isbn(row):
        row["ean_isbn13"] = row["upc_isbn10"] = ""

    data_dir = setup_state(tmp_path, transform=no_isbn)
    write_catalog(data_dir, [catalog_row(isbn13="", isbn10="", publisher="")])
    reconcile_inventory_catalog(data_dir=data_dir)
    prior = load_state(data_dir)["catalog_decisions"][0]

    new_id = supersede_inventory_catalog_reconciliation_decision(
        data_dir=data_dir,
        supersedes_decision_id=prior["inventory_catalog_reconciliation_decision_id"],
        outcome="existing_catalog_item_linked",
        decision_basis="manual_bibliographic_review",
        confidence="high",
        catalog_item_id="BK000001",
        reason_codes=("manual_confirmation",),
        now=lambda: NOW,
    )
    state = load_state(data_dir)

    assert len(state["catalog_decisions"]) == 2
    assert state["catalog_decisions"][0] == prior
    assert state["catalog_decisions"][1]["supersedes_decision_id"] == prior["inventory_catalog_reconciliation_decision_id"]
    assert state["catalog_decisions"][1]["inventory_catalog_reconciliation_decision_id"] == new_id
    assert state["holdings"][0]["catalog_item_id"] == "BK000001"


def test_invalid_cross_holding_branch_and_cycle_supersession_fail_closed(tmp_path):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [catalog_row()])
    reconcile_inventory_catalog(data_dir=data_dir)
    path = catalog_reconciliation_repository_path(data_dir)
    rows = InventoryCatalogReconciliationDecisionRepository(path).load()
    first = rows[0]
    second = dict(first, inventory_catalog_reconciliation_decision_id="ICD-second", supersedes_decision_id=first["inventory_catalog_reconciliation_decision_id"])
    third = dict(second, inventory_catalog_reconciliation_decision_id="ICD-third")
    with pytest.raises(LibibCatalogReconciliationError, match="Branching"):
        InventoryCatalogReconciliationDecisionRepository(path).rendered_bytes([first, second, third])
    second["holding_id"] = "HLD-other"
    with pytest.raises(LibibCatalogReconciliationError, match="another holding"):
        InventoryCatalogReconciliationDecisionRepository(path).rendered_bytes([first, second])
    second["holding_id"] = first["holding_id"]
    first["supersedes_decision_id"] = "ICD-second"
    with pytest.raises(LibibCatalogReconciliationError, match="cycle"):
        InventoryCatalogReconciliationDecisionRepository(path).rendered_bytes([first, second])


def test_malformed_decision_and_catalog_repositories_fail_closed(tmp_path):
    decision_path = tmp_path / "bad-decisions.csv"
    decision_path.write_text("schema_version,wrong\n99,value\n", encoding="utf-8")
    with pytest.raises(LibibRepositoryError, match="Unsupported or malformed"):
        InventoryCatalogReconciliationDecisionRepository(decision_path).load()
    catalog_path = tmp_path / "bad-catalog.csv"
    catalog_path.write_text("catalog_item_id,wrong\nBK000001,value\n", encoding="utf-8")
    with pytest.raises(LibibCatalogReconciliationError, match="Unsupported or malformed"):
        StrictCatalogRepository(catalog_path).load()


def test_accepted_decision_requires_catalog_and_unresolved_may_be_blank(tmp_path):
    row = {field: "" for field in INVENTORY_CATALOG_RECONCILIATION_DECISION_FIELDNAMES}
    row.update(
        schema_version="1", inventory_catalog_reconciliation_decision_id="ICD-one",
        holding_id="HLD-one", inventory_observation_id="IOB-one",
        candidate_catalog_item_ids_json="[]", candidate_catalog_statuses_json="[]",
        outcome="existing_catalog_item_linked", decision_basis="manual", confidence="high",
        reason_codes_json="[]", decision_timestamp="2026-07-20T00:00:00Z",
        reconciliation_model_version="v1", decision_origin="manual",
    )
    repository = InventoryCatalogReconciliationDecisionRepository(tmp_path / "decisions.csv")
    with pytest.raises(LibibCatalogReconciliationError, match="lacks catalog item"):
        repository.rendered_bytes([row])
    row["outcome"] = "manual_catalog_review_required"
    repository.rendered_bytes([row])
    assert row["outcome"] in CATALOG_RECONCILIATION_OUTCOMES
    assert row["outcome"] not in ACCEPTED_CATALOG_OUTCOMES


def test_atomic_failure_restores_catalog_decision_and_holding_bytes(tmp_path, monkeypatch):
    data_dir = setup_state(tmp_path)
    write_catalog(data_dir, [])
    paths = [data_dir / "catalog_items.csv", inventory_repository_paths(data_dir)["holdings"]]
    before = {path: path.read_bytes() for path in paths}
    real_replace = libib_inventory.os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected catalog publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(libib_inventory.os, "replace", fail_second)
    with pytest.raises(OSError, match="injected catalog publication failure"):
        reconcile_inventory_catalog(data_dir=data_dir)

    assert before == {path: path.read_bytes() for path in paths}
    assert not catalog_reconciliation_repository_path(data_dir).exists()


def test_repository_schema_version_and_closed_outcomes_are_enforced(tmp_path):
    path = tmp_path / "decisions.csv"
    row = {field: "" for field in INVENTORY_CATALOG_RECONCILIATION_DECISION_FIELDNAMES}
    row["schema_version"] = "99"
    row["candidate_catalog_item_ids_json"] = row["candidate_catalog_statuses_json"] = row["reason_codes_json"] = "[]"
    with pytest.raises(LibibRepositoryError, match="Unsupported repository schema version"):
        InventoryCatalogReconciliationDecisionRepository(path).rendered_bytes([row])
    assert CATALOG_RECONCILIATION_OUTCOMES == ACCEPTED_CATALOG_OUTCOMES | {
        "catalog_relink_requires_review", "multiple_catalog_candidates",
        "edition_or_catalog_identity_ambiguity", "conflicting_isbn_evidence",
        "insufficient_catalog_evidence", "catalog_candidate_requires_review",
        "manual_catalog_review_required", "catalog_candidate_ineligible",
        "physical_identity_unresolved",
    }
