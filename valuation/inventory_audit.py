"""Generated inventory audit and exception views over durable state.

This module is intentionally read-only.  It resolves explicit append-only
decision chains, joins allowlisted durable fields, and writes generated
review artifacts without importing, matching, or mutating repository state.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from valuation.collector_workbook import write_workbook
from valuation.libib_catalog import (
    ACCEPTED_CATALOG_OUTCOMES,
    UNRESOLVED_CATALOG_OUTCOMES,
    InventoryCatalogReconciliationDecisionRepository,
    StrictCatalogRepository,
    catalog_reconciliation_repository_path,
)
from valuation.libib_inventory import (
    ACCEPTED_RECONCILIATION_OUTCOMES,
    UNRESOLVED_RECONCILIATION_OUTCOMES,
    InventoryHoldingRepository,
    InventoryImportFolderRepository,
    InventoryImportRepository,
    InventoryObservationRepository,
    InventoryReconciliationDecisionRepository,
    LibibRepositoryError,
    inventory_repository_paths,
)
from valuation.repositories import ACQUISITION_FIELDNAMES


GENERATED_NOTE = (
    "Generated, non-durable review output. Workbook edits are not imported and "
    "do not change inventory, catalog, acquisition, or location state."
)

WORKBOOK_SHEETS = [
    "Summary",
    "Physical Review",
    "Catalog Review",
    "Newly Discovered",
    "Location Review",
    "Audit Coverage",
    "Reconciled Holdings",
    "Import Detail",
    "Decision Detail",
]

EMPTY_SHEET_MESSAGES = {
    "Physical Review": "No physical identity review items.",
    "Catalog Review": "No catalog identity review items.",
    "Newly Discovered": "No newly discovered books.",
    "Location Review": "No holdings require location review.",
    "Audit Coverage": "No holdings are available for audit coverage review.",
    "Reconciled Holdings": "No fully reconciled holdings yet.",
    "Import Detail": "No accepted inventory imports.",
    "Decision Detail": "No inventory reconciliation decisions.",
}

SUMMARY_FIELDS = ["section", "metric", "value", "denominator", "definition"]
PHYSICAL_REVIEW_FIELDS = [
    "reviewer_guidance", "inventory_observation_id", "candidate_holding_ids", "source_title",
    "source_creator", "normalized_isbn13", "normalized_isbn10",
    "source_collection_label", "audit_scope", "audit_completeness", "copies",
    "outcome", "confidence", "reason_codes", "explanation",
    "inventory_import_id", "observed_at",
]
CATALOG_REVIEW_FIELDS = [
    "reviewer_guidance", "holding_id", "current_catalog_item_id", "candidate_catalog_item_ids",
    "candidate_catalog_statuses", "source_title", "source_creator",
    "normalized_isbn13", "normalized_isbn10", "catalog_title", "catalog_author",
    "outcome", "review_classification", "confidence", "reason_codes",
    "explanation", "latest_inventory_observation_id",
]
AUDIT_COVERAGE_FIELDS = [
    "reviewer_guidance", "holding_id", "catalog_item_id", "title", "author", "audit_scope",
    "audit_completeness", "latest_verification_date", "source_collection_label",
    "current_physical_status", "audit_outcome", "explanation",
]
LOCATION_REVIEW_FIELDS = [
    "reviewer_guidance", "holding_id", "catalog_item_id", "title", "source_collection_label",
    "folder_path", "audit_scope", "current_location_id",
    "location_review_status", "last_verification_date",
]
NEWLY_DISCOVERED_FIELDS = [
    "reviewer_guidance", "catalog_item_id", "holding_id", "isbn13", "title", "author", "publisher",
    "source_collection_label", "catalog_reconciliation_outcome",
    "acquisition_status", "acquisition_count", "metadata_enrichment_status",
    "research_assessment_presence", "market_evidence_presence",
]
RECONCILED_FIELDS = [
    "reviewer_guidance", "holding_id", "catalog_item_id", "title", "author", "isbn13",
    "physical_outcome", "catalog_outcome", "audit_scope", "audit_completeness",
    "source_collection_label", "last_verified_at", "acquisition_status",
]
IMPORT_DETAIL_FIELDS = [
    "inventory_import_id", "source_file_name", "source_file_hash",
    "source_collection_label", "folder_id", "folder_path", "audit_scope",
    "audit_completeness", "imported_at", "parser_version", "row_count",
]
DECISION_DETAIL_FIELDS = [
    "decision_type", "decision_id", "inventory_observation_id", "holding_id",
    "catalog_item_id", "candidate_ids", "candidate_statuses", "outcome",
    "decision_basis", "confidence", "reason_codes", "explanation",
    "decision_timestamp", "model_version", "decision_origin",
    "supersedes_decision_id", "is_current",
]

WORKBOOK_COLUMNS = {
    "Summary": [
        ("section", "Area"), ("metric", "Measure"), ("value", "Current Count"),
        ("denominator", "Relevant Total"), ("definition", "What This Means"),
    ],
    "Physical Review": [
        ("reviewer_guidance", "Suggested Next Step"), ("source_title", "Book Title"),
        ("source_creator", "Author / Creator"), ("normalized_isbn13", "ISBN-13"),
        ("normalized_isbn10", "ISBN-10"), ("copies", "Reported Copies"),
        ("outcome", "Why It Needs Review"), ("explanation", "Explanation"),
        ("reason_codes", "Reason Codes"), ("confidence", "Confidence"),
        ("source_collection_label", "Libib Collection"), ("audit_scope", "Audit Area"),
        ("audit_completeness", "Audit Completeness"), ("observed_at", "Observed At"),
        ("candidate_holding_ids", "Candidate Holding IDs"),
        ("inventory_observation_id", "Observation ID"), ("inventory_import_id", "Import ID"),
    ],
    "Catalog Review": [
        ("reviewer_guidance", "Suggested Next Step"), ("source_title", "Source Title"),
        ("source_creator", "Source Author / Creator"), ("normalized_isbn13", "ISBN-13"),
        ("normalized_isbn10", "ISBN-10"), ("outcome", "Why It Needs Review"),
        ("review_classification", "Review Classification"), ("explanation", "Explanation"),
        ("reason_codes", "Reason Codes"), ("confidence", "Confidence"),
        ("catalog_title", "Current Catalog Title"), ("catalog_author", "Current Catalog Author"),
        ("candidate_catalog_item_ids", "Candidate Catalog IDs"),
        ("candidate_catalog_statuses", "Candidate Statuses"),
        ("current_catalog_item_id", "Current Catalog ID"), ("holding_id", "Holding ID"),
        ("latest_inventory_observation_id", "Observation ID"),
    ],
    "Newly Discovered": [
        ("reviewer_guidance", "Suggested Next Step"), ("title", "Book Title"),
        ("author", "Author"), ("publisher", "Publisher"), ("isbn13", "ISBN-13"),
        ("source_collection_label", "Libib Collection"), ("acquisition_status", "Acquisition Context"),
        ("metadata_enrichment_status", "Metadata Status"),
        ("research_assessment_presence", "Research Assessment"),
        ("market_evidence_presence", "Market Evidence"),
        ("catalog_reconciliation_outcome", "Catalog Outcome"),
        ("acquisition_count", "Acquisition Rows"), ("catalog_item_id", "Catalog ID"),
        ("holding_id", "Holding ID"),
    ],
    "Location Review": [
        ("reviewer_guidance", "Suggested Next Step"), ("title", "Book Title"),
        ("location_review_status", "Why It Needs Review"),
        ("source_collection_label", "Libib Collection"), ("folder_path", "Audit Folder"),
        ("audit_scope", "Audit Area"), ("last_verification_date", "Last Verified"),
        ("current_location_id", "Current Location ID"), ("catalog_item_id", "Catalog ID"),
        ("holding_id", "Holding ID"),
    ],
    "Audit Coverage": [
        ("reviewer_guidance", "Suggested Next Step"), ("title", "Book Title"),
        ("author", "Author"), ("audit_outcome", "Audit Status"),
        ("audit_scope", "Audit Area"), ("audit_completeness", "Audit Completeness"),
        ("latest_verification_date", "Last Verified"),
        ("source_collection_label", "Libib Collection"),
        ("current_physical_status", "Physical Status"), ("explanation", "Explanation"),
        ("catalog_item_id", "Catalog ID"), ("holding_id", "Holding ID"),
    ],
    "Reconciled Holdings": [
        ("reviewer_guidance", "Status"), ("title", "Book Title"), ("author", "Author"),
        ("isbn13", "ISBN-13"), ("source_collection_label", "Libib Collection"),
        ("audit_scope", "Audit Area"), ("audit_completeness", "Audit Completeness"),
        ("last_verified_at", "Last Verified"), ("acquisition_status", "Acquisition Context"),
        ("physical_outcome", "Physical Outcome"), ("catalog_outcome", "Catalog Outcome"),
        ("catalog_item_id", "Catalog ID"), ("holding_id", "Holding ID"),
    ],
    "Import Detail": [
        ("source_file_name", "Source File"), ("source_collection_label", "Libib Collection"),
        ("folder_path", "Audit Folder"), ("audit_scope", "Audit Area"),
        ("audit_completeness", "Audit Completeness"), ("imported_at", "Imported At"),
        ("row_count", "Source Rows"), ("parser_version", "Parser Version"),
        ("source_file_hash", "Source File Hash"), ("folder_id", "Folder ID"),
        ("inventory_import_id", "Import ID"),
    ],
    "Decision Detail": [
        ("decision_type", "Decision Type"), ("outcome", "Outcome"),
        ("explanation", "Explanation"), ("reason_codes", "Reason Codes"),
        ("confidence", "Confidence"), ("decision_basis", "Decision Basis"),
        ("decision_timestamp", "Decision Time"), ("decision_origin", "Decision Origin"),
        ("is_current", "Current Decision"), ("candidate_ids", "Candidate IDs"),
        ("candidate_statuses", "Candidate Statuses"), ("model_version", "Model Version"),
        ("catalog_item_id", "Catalog ID"), ("holding_id", "Holding ID"),
        ("inventory_observation_id", "Observation ID"), ("decision_id", "Decision ID"),
        ("supersedes_decision_id", "Supersedes Decision ID"),
    ],
}


@dataclass(frozen=True)
class InventoryAuditPresentation:
    summary: list[dict[str, str]]
    physical_review: list[dict[str, str]]
    catalog_review: list[dict[str, str]]
    audit_coverage: list[dict[str, str]]
    location_review: list[dict[str, str]]
    newly_discovered: list[dict[str, str]]
    reconciled_holdings: list[dict[str, str]]
    import_detail: list[dict[str, str]]
    decision_detail: list[dict[str, str]]

    def workbook_sheets(self) -> list[tuple[str, list[str], list[dict[str, str]]]]:
        rows_by_sheet = {
            "Summary": _summary_display_rows(self.summary),
            "Physical Review": self.physical_review,
            "Catalog Review": self.catalog_review,
            "Newly Discovered": self.newly_discovered,
            "Location Review": self.location_review,
            "Audit Coverage": self.audit_coverage,
            "Reconciled Holdings": self.reconciled_holdings,
            "Import Detail": self.import_detail,
            "Decision Detail": self.decision_detail,
        }
        return [
            (name, [label for _, label in WORKBOOK_COLUMNS[name]], _workbook_rows(rows_by_sheet[name], WORKBOOK_COLUMNS[name]))
            for name in WORKBOOK_SHEETS
        ]


def resolve_current_decisions(
    rows: Iterable[Mapping[str, str]], *, id_field: str, entity_field: str
) -> dict[str, dict[str, str]]:
    """Resolve one unsuperseded decision per entity, failing closed on bad chains."""

    materialized = [dict(row) for row in rows]
    by_id: dict[str, dict[str, str]] = {}
    child_counts: Counter[str] = Counter()
    for row in materialized:
        decision_id = row.get(id_field, "")
        entity_id = row.get(entity_field, "")
        if not decision_id or decision_id in by_id or not entity_id:
            raise LibibRepositoryError("Blank or duplicate decision identity")
        by_id[decision_id] = row
    for row in materialized:
        prior = row.get("supersedes_decision_id", "")
        if not prior:
            continue
        if prior not in by_id or prior == row[id_field]:
            raise LibibRepositoryError("Missing or self-referential supersession")
        if by_id[prior][entity_field] != row[entity_field]:
            raise LibibRepositoryError("Supersession crosses decision entities")
        child_counts[prior] += 1
    if any(count > 1 for count in child_counts.values()):
        raise LibibRepositoryError("Branching decision supersession")

    for start in by_id:
        seen: set[str] = set()
        current = start
        while current:
            if current in seen:
                raise LibibRepositoryError("Decision supersession cycle")
            seen.add(current)
            current = by_id[current].get("supersedes_decision_id", "")

    superseded = set(child_counts)
    current_by_entity: dict[str, dict[str, str]] = {}
    for decision_id, row in by_id.items():
        if decision_id in superseded:
            continue
        entity_id = row[entity_field]
        if entity_id in current_by_entity:
            raise LibibRepositoryError("Entity has multiple current decisions")
        current_by_entity[entity_id] = row
    return current_by_entity


def build_inventory_audit_presentation(
    *, data_dir: str | Path, research_assessments_path: str | Path | None = None,
    market_summary_path: str | Path | None = None,
) -> InventoryAuditPresentation:
    """Load, validate, and project durable inventory state without mutation."""

    data_dir = Path(data_dir)
    paths = inventory_repository_paths(data_dir)
    imports = InventoryImportRepository(paths["imports"]).load()
    folders = InventoryImportFolderRepository(paths["folders"]).load()
    observations = InventoryObservationRepository(paths["observations"]).load()
    physical = InventoryReconciliationDecisionRepository(paths["decisions"]).load()
    holdings = InventoryHoldingRepository(paths["holdings"]).load()
    catalog_decisions = InventoryCatalogReconciliationDecisionRepository(
        catalog_reconciliation_repository_path(data_dir)
    ).load()
    catalog = StrictCatalogRepository(data_dir / "catalog_items.csv").load()
    acquisitions_path = data_dir / "acquisitions.csv"
    acquisitions_available = acquisitions_path.exists()
    acquisitions = _load_exact_csv(acquisitions_path, ACQUISITION_FIELDNAMES)

    current_physical = resolve_current_decisions(
        physical,
        id_field="inventory_reconciliation_decision_id",
        entity_field="inventory_observation_id",
    )
    current_catalog = resolve_current_decisions(
        catalog_decisions,
        id_field="inventory_catalog_reconciliation_decision_id",
        entity_field="holding_id",
    )
    _validate_joins(imports, observations, physical, holdings, catalog, catalog_decisions)

    imports_by_id = {row["inventory_import_id"]: row for row in imports}
    folders_by_id = {row["folder_id"]: row for row in folders}
    observations_by_id = {row["inventory_observation_id"]: row for row in observations}
    catalog_by_id = {row["catalog_item_id"]: row for row in catalog}
    acquisitions_by_catalog: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in acquisitions:
        if row["catalog_item_id"]:
            acquisitions_by_catalog[row["catalog_item_id"]].append(row)
    research_ids = _presence_ids(research_assessments_path, "catalog_item_id")
    market_ids = _presence_ids(market_summary_path, "catalog_item_id")

    physical_review = _physical_review_rows(current_physical, observations_by_id)
    catalog_review = _catalog_review_rows(
        holdings, current_catalog, observations_by_id, catalog_by_id, current_physical
    )
    audit_coverage = _audit_rows(holdings, observations_by_id, catalog_by_id)
    location_review = _location_rows(
        holdings, observations_by_id, imports_by_id, folders_by_id, catalog_by_id
    )
    newly_discovered = _newly_discovered_rows(
        holdings, current_catalog, observations_by_id, catalog_by_id,
        acquisitions_by_catalog, acquisitions_available, research_ids, market_ids,
    )
    reconciled = _reconciled_rows(
        holdings, current_physical, current_catalog, observations_by_id,
        catalog_by_id, acquisitions_by_catalog, acquisitions_available,
    )
    summary = _summary_rows(
        imports, observations, holdings, physical_review, catalog_review,
        audit_coverage, location_review, newly_discovered, reconciled,
        current_physical, current_catalog, acquisitions_by_catalog,
        acquisitions_available,
    )
    decision_detail = _decision_detail_rows(physical, catalog_decisions)
    return InventoryAuditPresentation(
        summary=summary,
        physical_review=physical_review,
        catalog_review=catalog_review,
        audit_coverage=audit_coverage,
        location_review=location_review,
        newly_discovered=newly_discovered,
        reconciled_holdings=reconciled,
        import_detail=[{field: row[field] for field in IMPORT_DETAIL_FIELDS} for row in sorted(imports, key=lambda r: r["inventory_import_id"])],
        decision_detail=decision_detail,
    )


def write_inventory_audit_artifacts(
    *, data_dir: str | Path, output_dir: str | Path,
    research_assessments_path: str | Path | None = None,
    market_summary_path: str | Path | None = None,
) -> InventoryAuditPresentation:
    """Write deterministic summary CSV and reviewer workbook beneath output/."""

    output_dir = Path(output_dir)
    if output_dir.name != "output":
        raise ValueError("Inventory audit artifacts must be generated under an output/ directory")
    presentation = build_inventory_audit_presentation(
        data_dir=data_dir,
        research_assessments_path=research_assessments_path,
        market_summary_path=market_summary_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "inventory_audit_summary.csv", SUMMARY_FIELDS, presentation.summary)
    write_workbook(
        output_dir / "inventory_review_workbook.xlsx",
        presentation.workbook_sheets(),
        empty_messages=EMPTY_SHEET_MESSAGES,
    )
    return presentation


def _physical_review_rows(current, observations_by_id):
    rows = []
    for observation_id, decision in current.items():
        if decision["outcome"] not in UNRESOLVED_RECONCILIATION_OUTCOMES:
            continue
        observation = observations_by_id[observation_id]
        rows.append({
            "reviewer_guidance": _physical_guidance(decision["outcome"]),
            "inventory_observation_id": observation_id,
            "candidate_holding_ids": _display_json_list(decision["candidate_holding_ids_json"]),
            "source_title": observation["raw_title"],
            "source_creator": observation["raw_creators"],
            "normalized_isbn13": observation["normalized_isbn13"],
            "normalized_isbn10": observation["normalized_isbn10"],
            "source_collection_label": observation["source_collection_label"],
            "audit_scope": observation["audit_scope"],
            "audit_completeness": observation["audit_completeness"],
            "copies": observation["observed_copies"] or observation["raw_copies"],
            "outcome": decision["outcome"], "confidence": decision["confidence"],
            "reason_codes": _display_json_list(decision["reason_codes_json"]),
            "explanation": decision["explanation"],
            "inventory_import_id": observation["inventory_import_id"],
            "observed_at": observation["observed_at"],
        })
    return sorted(rows, key=lambda row: (row["outcome"], row["inventory_observation_id"]))


def _catalog_review_rows(holdings, current, observations_by_id, catalog_by_id, current_physical):
    rows = []
    for holding in holdings:
        holding_id = holding["holding_id"]
        observation = observations_by_id[holding["latest_inventory_observation_id"]]
        decision = current.get(holding_id)
        physical_decision = current_physical.get(observation["inventory_observation_id"])
        physical_resolved = bool(
            physical_decision
            and physical_decision["outcome"] in ACCEPTED_RECONCILIATION_OUTCOMES
            and physical_decision["holding_id"] == holding_id
        )
        unresolved = decision and decision["outcome"] in UNRESOLVED_CATALOG_OUTCOMES
        missing = physical_resolved and decision is None
        if not unresolved and not missing:
            continue
        catalog_item = catalog_by_id.get(holding["catalog_item_id"], {})
        rows.append({
            "reviewer_guidance": _catalog_guidance(decision["outcome"] if decision else "catalog_decision_missing"),
            "holding_id": holding_id,
            "current_catalog_item_id": holding["catalog_item_id"],
            "candidate_catalog_item_ids": _display_json_list(decision["candidate_catalog_item_ids_json"]) if decision else "",
            "candidate_catalog_statuses": _display_json_list(decision["candidate_catalog_statuses_json"]) if decision else "",
            "source_title": observation["raw_title"], "source_creator": observation["raw_creators"],
            "normalized_isbn13": observation["normalized_isbn13"], "normalized_isbn10": observation["normalized_isbn10"],
            "catalog_title": catalog_item.get("title", ""), "catalog_author": catalog_item.get("author", ""),
            "outcome": decision["outcome"] if decision else "",
            "review_classification": "" if decision else "catalog_decision_missing",
            "confidence": decision["confidence"] if decision else "unknown",
            "reason_codes": _display_json_list(decision["reason_codes_json"]) if decision else "",
            "explanation": decision["explanation"] if decision else "Accepted physical holding has no current catalog reconciliation decision.",
            "latest_inventory_observation_id": observation["inventory_observation_id"],
        })
    return sorted(rows, key=lambda row: (row["outcome"], row["holding_id"]))


def _audit_rows(holdings, observations_by_id, catalog_by_id):
    rows = []
    for holding in holdings:
        observation = observations_by_id[holding["latest_inventory_observation_id"]]
        catalog = catalog_by_id.get(holding["catalog_item_id"], {})
        outcome = holding["inventory_status"]
        rows.append({
            "reviewer_guidance": _audit_guidance(outcome),
            "holding_id": holding["holding_id"], "catalog_item_id": holding["catalog_item_id"],
            "title": catalog.get("title", observation["raw_title"]),
            "author": catalog.get("author", observation["raw_creators"]),
            "audit_scope": holding["verification_scope"] or observation["audit_scope"],
            "audit_completeness": holding["verification_completeness"] or observation["audit_completeness"],
            "latest_verification_date": holding["last_verified_at"],
            "source_collection_label": holding["source_collection_label"],
            "current_physical_status": outcome, "audit_outcome": outcome,
            "explanation": _audit_explanation(outcome),
        })
    return sorted(rows, key=lambda row: (row["audit_outcome"], row["holding_id"]))


def _location_rows(holdings, observations_by_id, imports_by_id, folders_by_id, catalog_by_id):
    rows = []
    for holding in holdings:
        observation = observations_by_id[holding["latest_inventory_observation_id"]]
        imported = imports_by_id[observation["inventory_import_id"]]
        folder = folders_by_id.get(imported["folder_id"], {})
        statuses = []
        if folder and folder["expected_collection_label"] != observation["source_collection_label"]:
            statuses.append("folder_collection_mismatch")
        if holding["current_location_id"]:
            statuses.append("location_context_available")
        elif observation["source_collection_label"]:
            statuses.append("source_label_unmapped")
        else:
            statuses.append("confirmed_location_missing")
        catalog = catalog_by_id.get(holding["catalog_item_id"], {})
        rows.append({
            "reviewer_guidance": _location_guidance(statuses),
            "holding_id": holding["holding_id"], "catalog_item_id": holding["catalog_item_id"],
            "title": catalog.get("title", observation["raw_title"]),
            "source_collection_label": observation["source_collection_label"],
            "folder_path": imported["folder_path"], "audit_scope": observation["audit_scope"],
            "current_location_id": holding["current_location_id"],
            "location_review_status": "; ".join(statuses),
            "last_verification_date": holding["last_verified_at"],
        })
    return sorted(rows, key=lambda row: (row["location_review_status"], row["holding_id"]))


def _newly_discovered_rows(holdings, current, observations_by_id, catalog_by_id, acquisitions_by_catalog, acquisitions_available, research_ids, market_ids):
    rows = []
    for holding in holdings:
        decision = current.get(holding["holding_id"])
        if not decision or decision["outcome"] != "new_catalog_item_created":
            continue
        catalog_id = decision["catalog_item_id"]
        catalog = catalog_by_id[catalog_id]
        observation = observations_by_id[decision["inventory_observation_id"]]
        acquisition_count = len(acquisitions_by_catalog.get(catalog_id, []))
        rows.append({
            "reviewer_guidance": _newly_discovered_guidance(
                _acquisition_status(acquisition_count, acquisitions_available),
                "metadata_enrichment_needed" if not catalog["publisher"] or not catalog["publication_year"] else "core_metadata_present",
            ),
            "catalog_item_id": catalog_id, "holding_id": holding["holding_id"],
            "isbn13": catalog["isbn13"], "title": catalog["title"], "author": catalog["author"],
            "publisher": catalog["publisher"], "source_collection_label": observation["source_collection_label"],
            "catalog_reconciliation_outcome": decision["outcome"],
            "acquisition_status": _acquisition_status(acquisition_count, acquisitions_available),
            "acquisition_count": str(acquisition_count),
            "metadata_enrichment_status": "metadata_enrichment_needed" if not catalog["publisher"] or not catalog["publication_year"] else "core_metadata_present",
            "research_assessment_presence": "present" if catalog_id in research_ids else "missing",
            "market_evidence_presence": "present" if catalog_id in market_ids else "missing",
        })
    return sorted(rows, key=lambda row: (row["catalog_item_id"], row["holding_id"]))


def _reconciled_rows(holdings, current_physical, current_catalog, observations_by_id, catalog_by_id, acquisitions_by_catalog, acquisitions_available):
    rows = []
    for holding in holdings:
        observation = observations_by_id[holding["latest_inventory_observation_id"]]
        physical = current_physical.get(observation["inventory_observation_id"])
        catalog_decision = current_catalog.get(holding["holding_id"])
        if not physical or physical["outcome"] not in ACCEPTED_RECONCILIATION_OUTCOMES:
            continue
        if not catalog_decision or catalog_decision["outcome"] not in ACCEPTED_CATALOG_OUTCOMES:
            continue
        if physical["holding_id"] != holding["holding_id"] or catalog_decision["catalog_item_id"] != holding["catalog_item_id"]:
            raise LibibRepositoryError("Accepted current decision disagrees with holding state")
        catalog = catalog_by_id[holding["catalog_item_id"]]
        count = len(acquisitions_by_catalog.get(holding["catalog_item_id"], []))
        rows.append({
            "reviewer_guidance": "No action — reconciled",
            "holding_id": holding["holding_id"], "catalog_item_id": holding["catalog_item_id"],
            "title": catalog["title"], "author": catalog["author"], "isbn13": catalog["isbn13"],
            "physical_outcome": physical["outcome"], "catalog_outcome": catalog_decision["outcome"],
            "audit_scope": observation["audit_scope"], "audit_completeness": observation["audit_completeness"],
            "source_collection_label": observation["source_collection_label"],
            "last_verified_at": holding["last_verified_at"], "acquisition_status": _acquisition_status(count, acquisitions_available),
        })
    return sorted(rows, key=lambda row: row["holding_id"])


def _summary_rows(imports, observations, holdings, physical_review, catalog_review, audit, locations, newly, reconciled, current_physical, current_catalog, acquisitions_by_catalog, acquisitions_available):
    eligible_holdings = sum(
        1 for holding in holdings
        if (decision := current_physical.get(holding["latest_inventory_observation_id"]))
        and decision["outcome"] in ACCEPTED_RECONCILIATION_OUTCOMES
        and decision["holding_id"] == holding["holding_id"]
    )
    linked = sum(
        1 for holding in holdings
        if holding["catalog_item_id"]
        and (decision := current_catalog.get(holding["holding_id"]))
        and decision["outcome"] in ACCEPTED_CATALOG_OUTCOMES
        and decision["catalog_item_id"] == holding["catalog_item_id"]
    )
    catalog_unresolved = max(eligible_holdings - linked, 0)
    existing_links = sum(1 for row in current_catalog.values() if row["outcome"] in {"existing_catalog_item_linked", "existing_catalog_item_confirmed", "catalog_link_unchanged"})
    no_acquisition = sum(1 for holding in holdings if acquisitions_available and holding["catalog_item_id"] and not acquisitions_by_catalog.get(holding["catalog_item_id"]))
    metrics = [
        ("State", "accepted_inventory_imports", len(imports), len(imports), "Accepted durable inventory import rows."),
        ("State", "observations", len(observations), len(observations), "Immutable durable inventory observations."),
        ("State", "current_holdings", len(holdings), len(holdings), "Current believed physical holdings."),
        ("Physical", "physically_resolved_holdings", eligible_holdings, len(holdings), "Holdings supported by a current accepted physical decision."),
        ("Physical", "physically_unresolved_observations", len(physical_review), len(observations), "Observations whose current physical decision is unresolved."),
        ("Catalog", "catalog_linked_holdings", linked, eligible_holdings, "Accepted catalog links among catalog-reconciliation-eligible holdings."),
        ("Catalog", "catalog_reconciliation_eligible_holdings", eligible_holdings, len(holdings), "Holdings whose latest observation has a current accepted physical decision."),
        ("Catalog", "catalog_unresolved_holdings", catalog_unresolved, eligible_holdings, "Eligible holdings without an accepted current catalog link; the review sheet may also retain non-eligible provenance rows."),
        ("Catalog", "existing_catalog_links", existing_links, linked, "Current accepted links to pre-existing catalog identities."),
        ("Catalog", "libib_created_catalog_items", len({row["catalog_item_id"] for row in newly}), linked, "Current Libib-created catalog identities."),
        ("Acquisition", "holdings_without_acquisition_history", no_acquisition, linked, "Linked holdings whose catalog item has no acquisition row; this does not mean not owned."),
        ("Audit", "verified_present_holdings", sum(row["audit_outcome"] == "verified_present" for row in audit), len(holdings), "Holdings durably classified verified_present."),
        ("Audit", "not_yet_audited_holdings", sum(row["audit_outcome"] == "not_yet_audited" for row in audit), len(holdings), "Holdings durably classified not_yet_audited; no negative conclusion is inferred."),
        ("Audit", "outside_audit_scope_holdings", sum(row["audit_outcome"] == "outside_audit_scope" for row in audit), len(holdings), "Holdings durably classified outside_audit_scope; no negative conclusion is inferred."),
        ("Audit", "possible_missing_holdings", sum(row["audit_outcome"] == "possible_missing" for row in audit), len(holdings), "Holdings already durably classified possible_missing; PR7 never infers this."),
        ("Location", "location_unmapped_holdings", sum("source_label_unmapped" in row["location_review_status"] for row in locations), len(holdings), "Holdings with source label evidence and no durable location_id."),
        ("Location", "folder_collection_mismatches", sum("folder_collection_mismatch" in row["location_review_status"] for row in locations), len(holdings), "Generated folder/collection evidence mismatch classification."),
        ("Review", "quantity_review_cases", sum(row["outcome"] == "quantity_requires_review" for row in physical_review), len(observations), "Current quantity_requires_review observations."),
        ("Review", "duplicate_review_cases", sum(row["outcome"] in {"indistinguishable_duplicate_rows", "possible_duplicate"} for row in physical_review), len(observations), "Current duplicate-related physical review observations."),
        ("Control", "successfully_reconciled_holdings", len(reconciled), eligible_holdings, "Accepted physical and catalog identity with no current identity-review condition."),
    ]
    return [{"section": "", "metric": "generated_output_note", "value": "Generated output; edits are not imported.", "denominator": "", "definition": GENERATED_NOTE}] + [
        {"section": section, "metric": metric, "value": str(value), "denominator": str(denominator), "definition": definition}
        for section, metric, value, denominator, definition in metrics
    ]


def _decision_detail_rows(physical, catalog):
    physical_current = resolve_current_decisions(physical, id_field="inventory_reconciliation_decision_id", entity_field="inventory_observation_id")
    catalog_current = resolve_current_decisions(catalog, id_field="inventory_catalog_reconciliation_decision_id", entity_field="holding_id")
    current_physical_ids = {row["inventory_reconciliation_decision_id"] for row in physical_current.values()}
    current_catalog_ids = {row["inventory_catalog_reconciliation_decision_id"] for row in catalog_current.values()}
    rows = []
    for row in physical:
        decision_id = row["inventory_reconciliation_decision_id"]
        rows.append({
            "decision_type": "physical", "decision_id": decision_id,
            "inventory_observation_id": row["inventory_observation_id"], "holding_id": row["holding_id"],
            "catalog_item_id": "", "candidate_ids": _display_json_list(row["candidate_holding_ids_json"]),
            "candidate_statuses": "", "outcome": row["outcome"], "decision_basis": row["decision_basis"],
            "confidence": row["confidence"], "reason_codes": _display_json_list(row["reason_codes_json"]),
            "explanation": row["explanation"], "decision_timestamp": row["decision_timestamp"],
            "model_version": row["reconciliation_model_version"], "decision_origin": row["decision_origin"],
            "supersedes_decision_id": row["supersedes_decision_id"], "is_current": "yes" if decision_id in current_physical_ids else "no",
        })
    for row in catalog:
        decision_id = row["inventory_catalog_reconciliation_decision_id"]
        rows.append({
            "decision_type": "catalog", "decision_id": decision_id,
            "inventory_observation_id": row["inventory_observation_id"], "holding_id": row["holding_id"],
            "catalog_item_id": row["catalog_item_id"], "candidate_ids": _display_json_list(row["candidate_catalog_item_ids_json"]),
            "candidate_statuses": _display_json_list(row["candidate_catalog_statuses_json"]),
            "outcome": row["outcome"], "decision_basis": row["decision_basis"], "confidence": row["confidence"],
            "reason_codes": _display_json_list(row["reason_codes_json"]), "explanation": row["explanation"],
            "decision_timestamp": row["decision_timestamp"], "model_version": row["reconciliation_model_version"],
            "decision_origin": row["decision_origin"], "supersedes_decision_id": row["supersedes_decision_id"],
            "is_current": "yes" if decision_id in current_catalog_ids else "no",
        })
    return sorted(rows, key=lambda row: (row["decision_timestamp"], row["decision_type"], row["decision_id"]))


def _validate_joins(imports, observations, physical, holdings, catalog, catalog_decisions):
    import_ids = {row["inventory_import_id"] for row in imports}
    observation_ids = {row["inventory_observation_id"] for row in observations}
    holding_ids = {row["holding_id"] for row in holdings}
    catalog_ids = {row["catalog_item_id"] for row in catalog}
    if any(row["inventory_import_id"] not in import_ids for row in observations):
        raise LibibRepositoryError("Observation references missing inventory import")
    if any(row["inventory_observation_id"] not in observation_ids for row in physical):
        raise LibibRepositoryError("Physical decision references missing observation")
    if any(row["latest_inventory_observation_id"] not in observation_ids for row in holdings):
        raise LibibRepositoryError("Holding references missing latest observation")
    if any(row["catalog_item_id"] and row["catalog_item_id"] not in catalog_ids for row in holdings):
        raise LibibRepositoryError("Holding references missing catalog item")
    if any(row["holding_id"] not in holding_ids or row["inventory_observation_id"] not in observation_ids for row in catalog_decisions):
        raise LibibRepositoryError("Catalog decision has an orphan holding or observation")
    if any(row["catalog_item_id"] and row["catalog_item_id"] not in catalog_ids for row in catalog_decisions):
        raise LibibRepositoryError("Catalog decision references missing catalog item")


def _load_exact_csv(path: Path, fieldnames: Iterable[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != tuple(fieldnames):
            raise LibibRepositoryError(f"Unsupported or malformed repository header: {path}")
        rows = [dict(row) for row in reader]
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise LibibRepositoryError(f"Malformed repository row: {path}")
    return rows


def _presence_ids(path, id_field):
    if path is None or not Path(path).exists():
        return set()
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if id_field not in (reader.fieldnames or []):
            raise LibibRepositoryError(f"Presence source lacks {id_field}: {path}")
        return {row.get(id_field, "") for row in reader if row.get(id_field, "")}


def _display_json_list(value: str) -> str:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise LibibRepositoryError("Malformed decision JSON list") from exc
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise LibibRepositoryError("Malformed decision JSON list")
    return "; ".join(parsed)


def _acquisition_status(count: int, repository_available: bool = True) -> str:
    if not repository_available:
        return "acquisition_context_unknown"
    if count == 0:
        return "no_acquisition_history"
    if count == 1:
        return "known_acquisition_history"
    return "multiple_acquisitions"


def _audit_explanation(outcome: str) -> str:
    return {
        "verified_present": "Holding is confirmed present by accepted durable evidence.",
        "not_yet_audited": "No negative conclusion; the applicable audit is incomplete or unknown.",
        "outside_audit_scope": "No negative conclusion; the holding is outside the declared audit scope.",
        "possible_missing": "Current durable state already records a completed-scope missing-review condition.",
        "verified_missing": "Current durable state already contains an explicitly approved verified-missing outcome.",
    }.get(outcome, "Current durable physical status is displayed without reinterpretation.")


def _physical_guidance(outcome: str) -> str:
    if outcome == "quantity_requires_review":
        return "Review reported quantity"
    if outcome in {"indistinguishable_duplicate_rows", "possible_duplicate", "multiple_holding_candidates"}:
        return "Check for duplicate physical copies"
    if outcome == "insufficient_identity_evidence":
        return "Add identifying evidence"
    return "Confirm physical identity"


def _catalog_guidance(outcome: str) -> str:
    if outcome == "physical_identity_unresolved":
        return "Resolve physical identity first"
    if outcome == "catalog_candidate_ineligible":
        return "Review catalog eligibility"
    if outcome == "catalog_decision_missing":
        return "Run or review catalog reconciliation"
    return "Confirm catalog match"


def _audit_guidance(outcome: str) -> str:
    return {
        "verified_present": "No action — confirmed present",
        "not_yet_audited": "Await a future applicable audit",
        "outside_audit_scope": "No action — outside this audit",
        "possible_missing": "Review possible missing book",
        "verified_missing": "Review approved missing status",
    }.get(outcome, "Review physical status")


def _location_guidance(statuses: Iterable[str]) -> str:
    statuses = set(statuses)
    if "folder_collection_mismatch" in statuses:
        return "Check folder and collection label"
    if "source_label_unmapped" in statuses:
        return "Assign a durable location later"
    if "confirmed_location_missing" in statuses:
        return "Add location evidence"
    return "No action — location recorded"


def _newly_discovered_guidance(acquisition_status: str, metadata_status: str) -> str:
    if acquisition_status == "no_acquisition_history" and metadata_status == "metadata_enrichment_needed":
        return "Review metadata; acquisition history unknown"
    if acquisition_status == "no_acquisition_history":
        return "No acquisition history — book is still owned"
    if metadata_status == "metadata_enrichment_needed":
        return "Review bibliographic metadata"
    return "Review newly discovered book"


def _workbook_rows(
    rows: Iterable[Mapping[str, str]], columns: Iterable[tuple[str, str]]
) -> list[dict[str, str]]:
    columns = list(columns)
    return [
        {label: row.get(source, "") for source, label in columns}
        for row in rows
    ]


def _summary_display_rows(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    labels = {
        "generated_output_note": "How to use this workbook",
        "accepted_inventory_imports": "Accepted Libib imports",
        "observations": "Source rows preserved",
        "current_holdings": "Books currently represented",
        "physically_resolved_holdings": "Physical identities confirmed",
        "physically_unresolved_observations": "Physical identity issues",
        "catalog_linked_holdings": "Books linked to the catalog",
        "catalog_reconciliation_eligible_holdings": "Books ready for catalog review",
        "catalog_unresolved_holdings": "Catalog identity issues",
        "existing_catalog_links": "Links to existing catalog books",
        "libib_created_catalog_items": "New books discovered through Libib",
        "holdings_without_acquisition_history": "Owned books with no acquisition history",
        "verified_present_holdings": "Books confirmed present",
        "not_yet_audited_holdings": "Books awaiting audit",
        "outside_audit_scope_holdings": "Books outside the current audit area",
        "possible_missing_holdings": "Books that may be missing",
        "location_unmapped_holdings": "Books needing a durable location",
        "folder_collection_mismatches": "Folder and collection mismatches",
        "quantity_review_cases": "Quantity issues",
        "duplicate_review_cases": "Possible duplicate-copy issues",
        "successfully_reconciled_holdings": "Fully reconciled books",
    }
    sections = {
        "State": "Inventory overview", "Physical": "Physical identity",
        "Catalog": "Catalog identity", "Acquisition": "Acquisition context",
        "Audit": "Audit coverage", "Location": "Location",
        "Review": "Needs attention", "Control": "Confirmed results", "": "About",
    }
    return [
        {
            **dict(row),
            "section": sections.get(row.get("section", ""), row.get("section", "")),
            "metric": labels.get(row.get("metric", ""), row.get("metric", "")),
        }
        for row in rows
    ]


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fieldnames} for row in rows)
