"""Read-only shared presentation model for the Steward Workspace.

This module joins strict durable repositories and explicitly supplied derived
evidence into deterministic, privacy-allowlisted in-memory records. It owns no
domain matching, reconciliation, assessment, market-summary, rendering, or
durable-write behavior.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

from valuation.inventory_audit import (
    InventoryAuditPresentation,
    build_inventory_audit_presentation,
    resolve_current_decisions,
)
from valuation.libib_catalog import (
    InventoryCatalogReconciliationDecisionRepository,
    StrictCatalogRepository,
    catalog_reconciliation_repository_path,
)
from valuation.libib_inventory import (
    InventoryHoldingRepository,
    InventoryImportFolderRepository,
    InventoryImportRepository,
    InventoryObservationRepository,
    InventoryReconciliationDecisionRepository,
    LibibRepositoryError,
    inventory_repository_paths,
)
from valuation.market_evidence_summary import MARKET_EVIDENCE_SUMMARY_FIELDNAMES
from valuation.repositories import (
    ACQUISITION_FIELDNAMES,
    COLLECTOR_REVIEW_FIELDNAMES,
    RESEARCH_ASSESSMENT_FIELDNAMES,
)
from valuation.research_candidates import RESEARCH_CANDIDATE_FIELDNAMES


PRESENTATION_MODEL_VERSION = "steward_presentation_v1"


class StewardPresentationError(ValueError):
    """Raised when required or durable source state cannot be presented safely."""


@dataclass(frozen=True)
class DerivedEvidenceInput:
    """Explicit generated evidence plus provenance supplied by its caller."""

    path: str | Path
    catalog_snapshot_sha256: str = ""
    schema_version: str = ""
    generated_at: str = ""


@dataclass(frozen=True)
class RegisteredReport:
    """Explicit report registration; no output-directory discovery is allowed."""

    report_key: str
    name: str
    purpose: str
    audience: str
    format: str
    source_path: str | Path
    public_path: str
    producing_workflow: str
    catalog_snapshot_sha256: str = ""
    generated_at: str = ""
    limitations: str = ""


@dataclass(frozen=True)
class SourceView:
    source_key: str
    authority: str
    status: str
    row_count: int
    content_sha256: str
    schema_version: str
    generated_at: str
    explanation: str


@dataclass(frozen=True)
class AcquisitionView:
    acquisition_reference: str
    acquisition_id: str
    catalog_item_id: str
    source: str
    order_date: str
    quantity: str
    currency: str


@dataclass(frozen=True)
class AssessmentView:
    assessment_id: str
    catalog_item_id: str
    priority_score: str
    priority_band: str
    signal_count: str
    signal_codes: str
    signal_summary: str
    model_version: str
    config_hash: str
    assessed_at: str
    assessment_status: str
    acquisition_snapshot_hash: str
    metadata_snapshot_hash: str


@dataclass(frozen=True)
class StewardReviewView:
    review_id: str
    catalog_item_id: str
    workflow_state: str
    disposition: str
    priority_override: str
    reviewed_at: str
    review_notes: str


@dataclass(frozen=True)
class InventoryImportView:
    inventory_import_id: str
    source_file_hash: str
    source_collection_label: str
    folder_id: str
    folder_path: str
    audit_scope: str
    audit_completeness: str
    imported_at: str
    parser_version: str
    row_count: str


@dataclass(frozen=True)
class ObservationView:
    inventory_observation_id: str
    inventory_import_id: str
    normalized_isbn10: str
    normalized_isbn13: str
    title: str
    creators: str
    publisher: str
    source_collection_label: str
    audit_scope: str
    audit_completeness: str
    observed_copies: str
    observed_at: str
    diagnostic_codes: tuple[str, ...]
    parser_version: str
    normalization_version: str


@dataclass(frozen=True)
class DecisionView:
    decision_id: str
    decision_type: str
    inventory_observation_id: str
    holding_id: str
    catalog_item_id: str
    outcome: str
    decision_basis: str
    confidence: str
    reason_codes: tuple[str, ...]
    explanation: str
    decision_timestamp: str
    model_version: str
    decision_origin: str
    supersedes_decision_id: str
    is_current: bool
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class HoldingView:
    holding_id: str
    catalog_item_id: str
    holding_state_type: str
    copies: str
    inventory_status: str
    current_location_id: str
    source_collection_label: str
    last_verified_at: str
    verification_scope: str
    verification_completeness: str
    latest_inventory_observation_id: str
    observation_ids: tuple[str, ...]
    physical_decision_ids: tuple[str, ...]
    catalog_decision_ids: tuple[str, ...]
    recommendation_ids: tuple[str, ...]


@dataclass(frozen=True)
class MarketEvidenceView:
    market_evidence_id: str
    catalog_item_id: str
    status: str
    evidence_status: str
    observed_sources: str
    listing_count: str
    market_confidence: str
    likely_low: str
    likely_mid: str
    likely_high: str
    currency: str
    review_recommendation: str
    review_reason: str
    generated_at: str
    model_version: str


@dataclass(frozen=True)
class RecommendationView:
    recommendation_id: str
    source_kind: str
    source_reference: str
    entity_type: str
    entity_id: str
    suggested_action: str
    explanation: str
    confidence: str
    reason_codes: tuple[str, ...]
    evidence_references: tuple[str, ...]
    advisory: bool = True


@dataclass(frozen=True)
class ReportView:
    report_key: str
    name: str
    purpose: str
    audience: str
    format: str
    public_path: str
    producing_workflow: str
    status: str
    generated_at: str
    limitations: str
    content_sha256: str


@dataclass(frozen=True)
class BookView:
    catalog_item_id: str
    isbn13: str
    isbn10: str
    title: str
    author: str
    publisher: str
    publication_year: str
    acquisition_status: str
    inventory_status: str
    assessment_status: str
    market_evidence_status: str
    acquisition_ids: tuple[str, ...]
    holding_ids: tuple[str, ...]
    assessment_id: str
    steward_review_id: str
    market_evidence_id: str
    recommendation_ids: tuple[str, ...]


@dataclass(frozen=True)
class CollectionView:
    catalog_item_count: int
    acquisition_count: int
    holding_count: int
    observation_count: int
    recommendation_count: int
    report_count: int
    catalog_item_ids: tuple[str, ...]
    holding_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceSnapshot:
    model_version: str
    snapshot_id: str
    generated_at: str
    sources: tuple[SourceView, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class StewardPresentation:
    snapshot: WorkspaceSnapshot
    collection: CollectionView
    books: tuple[BookView, ...]
    holdings: tuple[HoldingView, ...]
    acquisitions: tuple[AcquisitionView, ...]
    assessments: tuple[AssessmentView, ...]
    steward_reviews: tuple[StewardReviewView, ...]
    inventory_imports: tuple[InventoryImportView, ...]
    observations: tuple[ObservationView, ...]
    decisions: tuple[DecisionView, ...]
    market_evidence: tuple[MarketEvidenceView, ...]
    recommendations: tuple[RecommendationView, ...]
    reports: tuple[ReportView, ...]

    def to_json_bytes(self) -> bytes:
        """Return canonical deterministic bytes for future clients and tests."""

        return (
            json.dumps(
                asdict(self),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")


@dataclass(frozen=True)
class _LoadedDerived:
    source: SourceView
    rows: tuple[dict[str, str], ...]


def build_steward_presentation(
    *,
    data_dir: str | Path,
    market_evidence: DerivedEvidenceInput | None = None,
    research_candidates: DerivedEvidenceInput | None = None,
    reports: Sequence[RegisteredReport] = (),
    generated_at: str = "",
) -> StewardPresentation:
    """Build the deterministic shared presentation without writing any files."""

    data_dir = Path(data_dir)
    catalog_path = data_dir / "catalog_items.csv"
    if not catalog_path.is_file():
        raise StewardPresentationError(f"Required catalog repository is missing: {catalog_path}")
    try:
        catalog_rows = StrictCatalogRepository(catalog_path).load()
    except (LibibRepositoryError, ValueError) as exc:
        raise StewardPresentationError(str(exc)) from exc
    catalog_hash = _file_sha256(catalog_path)
    catalog_ids = {row["catalog_item_id"] for row in catalog_rows}
    sources: list[SourceView] = [
        _current_source("catalog", "durable", catalog_path, len(catalog_rows), "fixed_header_v1")
    ]

    acquisition_rows, acquisition_source = _load_optional_durable(
        data_dir / "acquisitions.csv", ACQUISITION_FIELDNAMES, "acquisitions"
    )
    assessment_rows, assessment_source = _load_optional_durable(
        data_dir / "research_priority_assessments.csv",
        RESEARCH_ASSESSMENT_FIELDNAMES,
        "research_assessments",
    )
    review_rows, review_source = _load_optional_durable(
        data_dir / "collector_reviews.csv",
        COLLECTOR_REVIEW_FIELDNAMES,
        "collector_reviews",
    )
    sources.extend((acquisition_source, assessment_source, review_source))
    _validate_catalog_refs(acquisition_rows, catalog_ids, "acquisitions")
    _validate_unique_and_catalog_refs(
        assessment_rows, "catalog_item_id", catalog_ids, "research assessments"
    )
    _validate_unique_and_catalog_refs(
        review_rows, "catalog_item_id", catalog_ids, "collector reviews"
    )

    inventory = _load_inventory(data_dir, catalog_ids)
    sources.append(inventory["source"])

    market = _load_derived(
        market_evidence,
        MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
        "market_evidence",
        catalog_hash,
        catalog_ids,
    )
    candidates = _load_derived(
        research_candidates,
        RESEARCH_CANDIDATE_FIELDNAMES,
        "research_candidates",
        catalog_hash,
        catalog_ids,
    )
    sources.extend((market.source, candidates.source))

    acquisition_views = _acquisition_views(acquisition_rows)
    assessment_views = tuple(
        AssessmentView(
            assessment_id=f"assessment:{row['catalog_item_id']}",
            catalog_item_id=row["catalog_item_id"],
            priority_score=row["research_priority_score"],
            priority_band=row["research_priority_band"],
            signal_count=row["research_signal_count"],
            signal_codes=row["research_signal_codes"],
            signal_summary=row["research_signal_summary"],
            model_version=row["research_model_version"],
            config_hash=row["research_config_hash"],
            assessed_at=row["assessed_at"],
            assessment_status=row["assessment_status"],
            acquisition_snapshot_hash=row["acquisition_snapshot_hash"],
            metadata_snapshot_hash=row["metadata_snapshot_hash"],
        )
        for row in sorted(assessment_rows, key=lambda item: item["catalog_item_id"])
    )
    review_views = tuple(
        StewardReviewView(
            review_id=f"review:{row['catalog_item_id']}",
            catalog_item_id=row["catalog_item_id"],
            workflow_state=row["workflow_state"],
            disposition=row["disposition"],
            priority_override=row["priority_override"],
            reviewed_at=row["reviewed_at"],
            review_notes=row["review_notes"],
        )
        for row in sorted(review_rows, key=lambda item: item["catalog_item_id"])
    )

    import_views, observation_views, decision_views, holding_rows = _inventory_views(
        inventory
    )
    market_views = _market_views(market)
    recommendations = _recommendation_views(
        inventory["audit"], market, candidates, review_views
    )
    report_views, report_sources = _report_views(reports, catalog_hash)
    sources.extend(report_sources)

    acquisitions_by_catalog = _group_ids(
        acquisition_views, "catalog_item_id", "acquisition_reference"
    )
    holdings_by_catalog: defaultdict[str, list[str]] = defaultdict(list)
    for row in holding_rows:
        if row["catalog_item_id"]:
            holdings_by_catalog[row["catalog_item_id"]].append(row["holding_id"])
    assessment_by_catalog = {row.catalog_item_id: row for row in assessment_views}
    review_by_catalog = {row.catalog_item_id: row for row in review_views}
    market_by_catalog = {row.catalog_item_id: row for row in market_views}
    recommendations_by_entity: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for row in recommendations:
        recommendations_by_entity[(row.entity_type, row.entity_id)].append(
            row.recommendation_id
        )

    holding_views = _holding_views(
        holding_rows,
        observation_views,
        decision_views,
        recommendations_by_entity,
    )
    books = tuple(
        BookView(
            catalog_item_id=row["catalog_item_id"],
            isbn13=row["isbn13"],
            isbn10=row["isbn10"],
            title=row["title"],
            author=row["author"],
            publisher=row["publisher"],
            publication_year=row["publication_year"],
            acquisition_status=_entity_evidence_status(
                acquisition_source.status, acquisitions_by_catalog[row["catalog_item_id"]]
            ),
            inventory_status=_entity_evidence_status(
                inventory["source"].status, holdings_by_catalog[row["catalog_item_id"]]
            ),
            assessment_status=(
                assessment_by_catalog[row["catalog_item_id"]].assessment_status
                if row["catalog_item_id"] in assessment_by_catalog
                else _missing_or_unavailable(assessment_source.status)
            ),
            market_evidence_status=(
                market_by_catalog[row["catalog_item_id"]].status
                if row["catalog_item_id"] in market_by_catalog
                else _missing_or_unavailable(market.source.status)
            ),
            acquisition_ids=tuple(acquisitions_by_catalog[row["catalog_item_id"]]),
            holding_ids=tuple(sorted(holdings_by_catalog[row["catalog_item_id"]])),
            assessment_id=(
                assessment_by_catalog[row["catalog_item_id"]].assessment_id
                if row["catalog_item_id"] in assessment_by_catalog
                else ""
            ),
            steward_review_id=(
                review_by_catalog[row["catalog_item_id"]].review_id
                if row["catalog_item_id"] in review_by_catalog
                else ""
            ),
            market_evidence_id=(
                market_by_catalog[row["catalog_item_id"]].market_evidence_id
                if row["catalog_item_id"] in market_by_catalog
                else ""
            ),
            recommendation_ids=tuple(
                sorted(recommendations_by_entity[("catalog_item", row["catalog_item_id"])])
            ),
        )
        for row in sorted(catalog_rows, key=lambda item: item["catalog_item_id"])
    )

    source_views = tuple(sorted(sources, key=lambda item: item.source_key))
    warnings = tuple(
        f"{source.source_key}: {source.explanation}"
        for source in source_views
        if source.status in {"stale", "incompatible"}
    )
    snapshot_id = _snapshot_id(source_views, generated_at)
    collection = CollectionView(
        catalog_item_count=len(books),
        acquisition_count=len(acquisition_views),
        holding_count=len(holding_views),
        observation_count=len(observation_views),
        recommendation_count=len(recommendations),
        report_count=len(report_views),
        catalog_item_ids=tuple(row.catalog_item_id for row in books),
        holding_ids=tuple(row.holding_id for row in holding_views),
    )
    return StewardPresentation(
        snapshot=WorkspaceSnapshot(
            model_version=PRESENTATION_MODEL_VERSION,
            snapshot_id=snapshot_id,
            generated_at=generated_at,
            sources=source_views,
            warnings=warnings,
        ),
        collection=collection,
        books=books,
        holdings=holding_views,
        acquisitions=acquisition_views,
        assessments=assessment_views,
        steward_reviews=review_views,
        inventory_imports=import_views,
        observations=observation_views,
        decisions=decision_views,
        market_evidence=market_views,
        recommendations=recommendations,
        reports=report_views,
    )


def _load_inventory(data_dir: Path, catalog_ids: set[str]) -> dict[str, object]:
    paths = inventory_repository_paths(data_dir)
    paths["catalog_decisions"] = catalog_reconciliation_repository_path(data_dir)
    present = {key for key, path in paths.items() if path.exists()}
    if not present:
        return {
            "source": _unavailable_source("inventory", "durable", "Inventory has not been supplied."),
            "imports": (),
            "folders": (),
            "observations": (),
            "physical": (),
            "holdings": (),
            "catalog_decisions": (),
            "audit": None,
        }
    if present != set(paths):
        missing = ", ".join(sorted(set(paths) - present))
        raise StewardPresentationError(f"Incomplete inventory subsystem; missing: {missing}")
    try:
        imports = InventoryImportRepository(paths["imports"]).load()
        folders = InventoryImportFolderRepository(paths["folders"]).load()
        observations = InventoryObservationRepository(paths["observations"]).load()
        physical = InventoryReconciliationDecisionRepository(paths["decisions"]).load()
        holdings = InventoryHoldingRepository(paths["holdings"]).load()
        catalog_decisions = InventoryCatalogReconciliationDecisionRepository(
            paths["catalog_decisions"]
        ).load()
        audit = build_inventory_audit_presentation(data_dir=data_dir)
    except (LibibRepositoryError, ValueError) as exc:
        raise StewardPresentationError(str(exc)) from exc
    unknown_catalog_ids = {
        row["catalog_item_id"]
        for row in holdings
        if row["catalog_item_id"] and row["catalog_item_id"] not in catalog_ids
    }
    if unknown_catalog_ids:
        raise StewardPresentationError("Inventory holding references an unknown catalog item")
    digest = hashlib.sha256()
    for key in sorted(paths):
        digest.update(key.encode("utf-8"))
        digest.update(paths[key].read_bytes())
    source = SourceView(
        source_key="inventory",
        authority="durable",
        status="current",
        row_count=len(holdings),
        content_sha256=digest.hexdigest(),
        schema_version="inventory_bundle_v1",
        generated_at="",
        explanation="Complete validated inventory repository bundle.",
    )
    return {
        "source": source,
        "imports": tuple(imports),
        "folders": tuple(folders),
        "observations": tuple(observations),
        "physical": tuple(physical),
        "holdings": tuple(holdings),
        "catalog_decisions": tuple(catalog_decisions),
        "audit": audit,
    }


def _acquisition_views(
    rows: Iterable[Mapping[str, str]],
) -> tuple[AcquisitionView, ...]:
    ordered = sorted(
        rows,
        key=lambda row: tuple(row.get(field, "") for field in ACQUISITION_FIELDNAMES),
    )
    occurrences: defaultdict[str, int] = defaultdict(int)
    views: list[AcquisitionView] = []
    for row in ordered:
        acquisition_id = row["acquisition_id"]
        occurrences[acquisition_id] += 1
        reference = f"acquisition:{acquisition_id}:{occurrences[acquisition_id]}"
        views.append(
            AcquisitionView(
                acquisition_reference=reference,
                acquisition_id=acquisition_id,
                catalog_item_id=row["catalog_item_id"],
                source=row["source"],
                order_date=row["order_date"],
                quantity=row["quantity"],
                currency=row["currency"],
            )
        )
    return tuple(views)


def _inventory_views(
    inventory: Mapping[str, object],
) -> tuple[
    tuple[InventoryImportView, ...],
    tuple[ObservationView, ...],
    tuple[DecisionView, ...],
    tuple[dict[str, str], ...],
]:
    imports = tuple(inventory["imports"])  # type: ignore[arg-type]
    observations = tuple(inventory["observations"])  # type: ignore[arg-type]
    physical = tuple(inventory["physical"])  # type: ignore[arg-type]
    catalog = tuple(inventory["catalog_decisions"])  # type: ignore[arg-type]
    holdings = tuple(inventory["holdings"])  # type: ignore[arg-type]
    current_physical = (
        resolve_current_decisions(
            physical,
            id_field="inventory_reconciliation_decision_id",
            entity_field="inventory_observation_id",
        )
        if physical
        else {}
    )
    current_catalog = (
        resolve_current_decisions(
            catalog,
            id_field="inventory_catalog_reconciliation_decision_id",
            entity_field="holding_id",
        )
        if catalog
        else {}
    )
    import_views = tuple(
        InventoryImportView(
            inventory_import_id=row["inventory_import_id"],
            source_file_hash=row["source_file_hash"],
            source_collection_label=row["source_collection_label"],
            folder_id=row["folder_id"],
            folder_path=row["folder_path"],
            audit_scope=row["audit_scope"],
            audit_completeness=row["audit_completeness"],
            imported_at=row["imported_at"],
            parser_version=row["parser_version"],
            row_count=row["row_count"],
        )
        for row in sorted(imports, key=lambda item: item["inventory_import_id"])
    )
    observation_views = tuple(
        ObservationView(
            inventory_observation_id=row["inventory_observation_id"],
            inventory_import_id=row["inventory_import_id"],
            normalized_isbn10=row["normalized_isbn10"],
            normalized_isbn13=row["normalized_isbn13"],
            title=row["raw_title"],
            creators=row["raw_creators"],
            publisher=row["raw_publisher"],
            source_collection_label=row["source_collection_label"],
            audit_scope=row["audit_scope"],
            audit_completeness=row["audit_completeness"],
            observed_copies=row["observed_copies"],
            observed_at=row["observed_at"],
            diagnostic_codes=_json_strings(row["diagnostic_codes_json"]),
            parser_version=row["parser_version"],
            normalization_version=row["normalization_version"],
        )
        for row in sorted(observations, key=lambda item: item["inventory_observation_id"])
    )
    decisions: list[DecisionView] = []
    for row in physical:
        decisions.append(
            DecisionView(
                decision_id=row["inventory_reconciliation_decision_id"],
                decision_type="physical",
                inventory_observation_id=row["inventory_observation_id"],
                holding_id=row["holding_id"],
                catalog_item_id="",
                outcome=row["outcome"],
                decision_basis=row["decision_basis"],
                confidence=row["confidence"],
                reason_codes=_json_strings(row["reason_codes_json"]),
                explanation=row["explanation"],
                decision_timestamp=row["decision_timestamp"],
                model_version=row["reconciliation_model_version"],
                decision_origin=row["decision_origin"],
                supersedes_decision_id=row["supersedes_decision_id"],
                is_current=current_physical.get(row["inventory_observation_id"]) == row,
                candidate_ids=_json_strings(row["candidate_holding_ids_json"]),
            )
        )
    for row in catalog:
        decisions.append(
            DecisionView(
                decision_id=row["inventory_catalog_reconciliation_decision_id"],
                decision_type="catalog",
                inventory_observation_id=row["inventory_observation_id"],
                holding_id=row["holding_id"],
                catalog_item_id=row["catalog_item_id"],
                outcome=row["outcome"],
                decision_basis=row["decision_basis"],
                confidence=row["confidence"],
                reason_codes=_json_strings(row["reason_codes_json"]),
                explanation=row["explanation"],
                decision_timestamp=row["decision_timestamp"],
                model_version=row["reconciliation_model_version"],
                decision_origin=row["decision_origin"],
                supersedes_decision_id=row["supersedes_decision_id"],
                is_current=current_catalog.get(row["holding_id"]) == row,
                candidate_ids=_json_strings(row["candidate_catalog_item_ids_json"]),
            )
        )
    return (
        import_views,
        observation_views,
        tuple(sorted(decisions, key=lambda item: item.decision_id)),
        holdings,
    )


def _holding_views(
    holdings: Iterable[Mapping[str, str]],
    observations: Iterable[ObservationView],
    decisions: Iterable[DecisionView],
    recommendations_by_entity: Mapping[tuple[str, str], list[str]],
) -> tuple[HoldingView, ...]:
    observations_by_holding: defaultdict[str, set[str]] = defaultdict(set)
    physical_by_holding: defaultdict[str, list[str]] = defaultdict(list)
    catalog_by_holding: defaultdict[str, list[str]] = defaultdict(list)
    for decision in decisions:
        if decision.holding_id:
            observations_by_holding[decision.holding_id].add(decision.inventory_observation_id)
            target = physical_by_holding if decision.decision_type == "physical" else catalog_by_holding
            target[decision.holding_id].append(decision.decision_id)
    known_observations = {row.inventory_observation_id for row in observations}
    return tuple(
        HoldingView(
            holding_id=row["holding_id"],
            catalog_item_id=row["catalog_item_id"],
            holding_state_type=row["holding_state_type"],
            copies=row["copies"],
            inventory_status=row["inventory_status"],
            current_location_id=row["current_location_id"],
            source_collection_label=row["source_collection_label"],
            last_verified_at=row["last_verified_at"],
            verification_scope=row["verification_scope"],
            verification_completeness=row["verification_completeness"],
            latest_inventory_observation_id=row["latest_inventory_observation_id"],
            observation_ids=tuple(
                sorted(observations_by_holding[row["holding_id"]] & known_observations)
            ),
            physical_decision_ids=tuple(sorted(physical_by_holding[row["holding_id"]])),
            catalog_decision_ids=tuple(sorted(catalog_by_holding[row["holding_id"]])),
            recommendation_ids=tuple(
                sorted(recommendations_by_entity.get(("holding", row["holding_id"]), []))
            ),
        )
        for row in sorted(holdings, key=lambda item: item["holding_id"])
    )


def _market_views(market: _LoadedDerived) -> tuple[MarketEvidenceView, ...]:
    return tuple(
        MarketEvidenceView(
            market_evidence_id=f"market:{row['catalog_item_id']}",
            catalog_item_id=row["catalog_item_id"],
            status=market.source.status,
            evidence_status=row["evidence_status"],
            observed_sources=row["observed_source_names"],
            listing_count=row["listing_count"],
            market_confidence=row["market_confidence"],
            likely_low=row["likely_low"],
            likely_mid=row["likely_mid"],
            likely_high=row["likely_high"],
            currency=row["currency"],
            review_recommendation=row["review_recommendation"],
            review_reason=row["review_reason"],
            generated_at=row["evidence_generated_at"],
            model_version=row["evidence_model_version"],
        )
        for row in market.rows
    )


def _recommendation_views(
    audit: object,
    market: _LoadedDerived,
    candidates: _LoadedDerived,
    reviews: Sequence[StewardReviewView],
) -> tuple[RecommendationView, ...]:
    pending: list[RecommendationView] = []
    seen: set[str] = set()

    def add(
        source_kind: str,
        source_reference: str,
        entity_type: str,
        entity_id: str,
        action: str,
        explanation: str,
        confidence: str = "",
        reason_codes: Iterable[str] = (),
        evidence: Iterable[str] = (),
    ) -> None:
        identity = "|".join((source_kind, source_reference, entity_type, entity_id, action))
        if identity in seen:
            return
        seen.add(identity)
        recommendation_id = "recommendation:" + hashlib.sha256(identity.encode()).hexdigest()[:20]
        pending.append(
            RecommendationView(
                recommendation_id=recommendation_id,
                source_kind=source_kind,
                source_reference=source_reference,
                entity_type=entity_type,
                entity_id=entity_id,
                suggested_action=action,
                explanation=explanation,
                confidence=confidence,
                reason_codes=tuple(sorted(set(reason_codes))),
                evidence_references=tuple(sorted(set(evidence))),
            )
        )

    if isinstance(audit, InventoryAuditPresentation):
        for row in audit.physical_review:
            add(
                "inventory_physical_review",
                row["inventory_observation_id"],
                "inventory_observation",
                row["inventory_observation_id"],
                row["reviewer_guidance"],
                row["explanation"],
                row["confidence"],
                _split_codes(row["reason_codes"]),
                (f"observation:{row['inventory_observation_id']}",),
            )
        for row in audit.catalog_review:
            add(
                "inventory_catalog_review",
                row["holding_id"],
                "holding",
                row["holding_id"],
                row["reviewer_guidance"],
                row["explanation"],
                row["confidence"],
                _split_codes(row["reason_codes"]),
                (f"holding:{row['holding_id']}",),
            )
        for row in audit.location_review:
            add(
                "inventory_location_review",
                row["holding_id"],
                "holding",
                row["holding_id"],
                row["reviewer_guidance"],
                row["location_review_status"],
                reason_codes=_split_codes(row["location_review_status"]),
                evidence=(f"holding:{row['holding_id']}",),
            )
        for row in audit.audit_coverage:
            outcome = row["audit_outcome"]
            if outcome in {"verified_present", "outside_audit_scope"}:
                continue
            add(
                "inventory_audit_coverage",
                row["holding_id"],
                "holding",
                row["holding_id"],
                row["reviewer_guidance"],
                row["explanation"],
                reason_codes=(outcome,),
                evidence=(f"holding:{row['holding_id']}",),
            )
        for row in audit.newly_discovered:
            add(
                "inventory_newly_discovered",
                row["holding_id"],
                "catalog_item",
                row["catalog_item_id"],
                row["reviewer_guidance"],
                row["acquisition_status"],
                evidence=(f"holding:{row['holding_id']}", f"catalog:{row['catalog_item_id']}"),
            )
    if market.source.status == "current":
        for row in market.rows:
            if row["review_recommendation"]:
                add(
                    "market_evidence",
                    row["catalog_item_id"],
                    "catalog_item",
                    row["catalog_item_id"],
                    row["review_recommendation"],
                    row["review_reason"],
                    row["market_confidence"],
                    evidence=(f"market:{row['catalog_item_id']}",),
                )
    if candidates.source.status == "current":
        for row in candidates.rows:
            add(
                "research_candidate",
                row["catalog_item_id"],
                "catalog_item",
                row["catalog_item_id"],
                "Review research candidate",
                row["research_signal_summary"],
                reason_codes=_split_codes(row["research_signal_codes"]),
                evidence=(f"assessment:{row['catalog_item_id']}",),
            )
    for row in reviews:
        if not row.priority_override:
            continue
        add(
            "steward_priority",
            row.review_id,
            "catalog_item",
            row.catalog_item_id,
            "Review steward-prioritized book",
            f"Steward priority is {row.priority_override}.",
            "steward_set",
            (f"priority_{row.priority_override}",),
            (row.review_id,),
        )
    return tuple(sorted(pending, key=lambda item: item.recommendation_id))


def _report_views(
    reports: Sequence[RegisteredReport], catalog_hash: str
) -> tuple[tuple[ReportView, ...], tuple[SourceView, ...]]:
    keys: set[str] = set()
    views: list[ReportView] = []
    sources: list[SourceView] = []
    for report in sorted(reports, key=lambda item: item.report_key):
        if not report.report_key or report.report_key in keys:
            raise StewardPresentationError("Report keys must be nonblank and unique")
        keys.add(report.report_key)
        public_path = PurePosixPath(report.public_path)
        if public_path.is_absolute() or ".." in public_path.parts or not report.public_path:
            raise StewardPresentationError("Report public_path must be safe and relative")
        path = Path(report.source_path)
        if not path.is_file():
            status, digest, explanation = "unavailable", "", "Registered report is unavailable."
        else:
            digest = _file_sha256(path)
            if report.catalog_snapshot_sha256 == catalog_hash:
                status, explanation = "current", "Registered report matches the catalog snapshot."
            else:
                status, explanation = "stale", "Report catalog snapshot is absent or does not match."
        views.append(
            ReportView(
                report_key=report.report_key,
                name=report.name,
                purpose=report.purpose,
                audience=report.audience,
                format=report.format,
                public_path=report.public_path,
                producing_workflow=report.producing_workflow,
                status=status,
                generated_at=report.generated_at,
                limitations=report.limitations,
                content_sha256=digest,
            )
        )
        sources.append(
            SourceView(
                source_key=f"report:{report.report_key}",
                authority="generated",
                status=status,
                row_count=1 if digest else 0,
                content_sha256=digest,
                schema_version="registered_report_v1",
                generated_at=report.generated_at,
                explanation=explanation,
            )
        )
    return tuple(views), tuple(sources)


def _load_derived(
    source: DerivedEvidenceInput | None,
    fieldnames: Sequence[str],
    source_key: str,
    catalog_hash: str,
    catalog_ids: set[str],
) -> _LoadedDerived:
    if source is None:
        return _LoadedDerived(
            _unavailable_source(source_key, "generated", "Derived evidence was not supplied."),
            (),
        )
    path = Path(source.path)
    if not path.is_file():
        return _LoadedDerived(
            _unavailable_source(source_key, "generated", "Derived evidence file is unavailable."),
            (),
        )
    try:
        rows = _read_exact_csv(path, fieldnames)
    except StewardPresentationError:
        return _LoadedDerived(
            SourceView(
                source_key=source_key,
                authority="generated",
                status="incompatible",
                row_count=0,
                content_sha256=_file_sha256(path),
                schema_version=source.schema_version,
                generated_at=source.generated_at,
                explanation="Derived evidence header or rows are incompatible.",
            ),
            (),
        )
    ids = [row["catalog_item_id"] for row in rows]
    if any(not value for value in ids) or len(ids) != len(set(ids)) or not set(ids) <= catalog_ids:
        return _LoadedDerived(
            SourceView(
                source_key=source_key,
                authority="generated",
                status="incompatible",
                row_count=0,
                content_sha256=_file_sha256(path),
                schema_version=source.schema_version,
                generated_at=source.generated_at,
                explanation="Derived evidence identities are incompatible with the catalog.",
            ),
            (),
        )
    status = "current" if source.catalog_snapshot_sha256 == catalog_hash else "stale"
    explanation = (
        "Derived evidence matches the catalog snapshot."
        if status == "current"
        else "Derived evidence catalog snapshot is absent or does not match."
    )
    return _LoadedDerived(
        SourceView(
            source_key=source_key,
            authority="generated",
            status=status,
            row_count=len(rows),
            content_sha256=_file_sha256(path),
            schema_version=source.schema_version,
            generated_at=source.generated_at,
            explanation=explanation,
        ),
        tuple(sorted(rows, key=lambda item: item["catalog_item_id"])),
    )


def _load_optional_durable(
    path: Path, fieldnames: Sequence[str], source_key: str
) -> tuple[list[dict[str, str]], SourceView]:
    if not path.exists():
        return [], _unavailable_source(source_key, "durable", "Repository is unavailable.")
    rows = _read_exact_csv(path, fieldnames)
    return rows, _current_source(source_key, "durable", path, len(rows), "fixed_header_v1")


def _read_exact_csv(path: Path, fieldnames: Sequence[str]) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != tuple(fieldnames):
                raise StewardPresentationError(f"Unsupported or malformed CSV header: {path}")
            rows = [dict(row) for row in reader]
    except UnicodeDecodeError as exc:
        raise StewardPresentationError(f"CSV must be UTF-8: {path}") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise StewardPresentationError(f"Malformed CSV row: {path}")
    return rows


def _validate_unique_and_catalog_refs(
    rows: Iterable[Mapping[str, str]],
    identity_field: str,
    catalog_ids: set[str],
    label: str,
) -> None:
    identities: set[str] = set()
    for row in rows:
        identity = row.get(identity_field, "")
        catalog_id = row.get("catalog_item_id", "")
        if not identity or identity in identities:
            raise StewardPresentationError(f"Blank or duplicate identity in {label}")
        identities.add(identity)
        if catalog_id not in catalog_ids:
            raise StewardPresentationError(f"{label} references an unknown catalog item")


def _validate_catalog_refs(
    rows: Iterable[Mapping[str, str]], catalog_ids: set[str], label: str
) -> None:
    for row in rows:
        if not row.get("acquisition_id", ""):
            raise StewardPresentationError(f"Blank acquisition identity in {label}")
        if row.get("catalog_item_id", "") not in catalog_ids:
            raise StewardPresentationError(f"{label} references an unknown catalog item")


def _current_source(
    key: str, authority: str, path: Path, count: int, schema_version: str
) -> SourceView:
    return SourceView(
        source_key=key,
        authority=authority,
        status="current",
        row_count=count,
        content_sha256=_file_sha256(path),
        schema_version=schema_version,
        generated_at="",
        explanation="Validated source is available.",
    )


def _unavailable_source(key: str, authority: str, explanation: str) -> SourceView:
    return SourceView(key, authority, "unavailable", 0, "", "", "", explanation)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_id(sources: Sequence[SourceView], generated_at: str) -> str:
    payload = {
        "model_version": PRESENTATION_MODEL_VERSION,
        "generated_at": generated_at,
        "sources": [asdict(source) for source in sources],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _json_strings(value: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise StewardPresentationError("Invalid JSON list in validated source") from exc
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise StewardPresentationError("Invalid JSON list in validated source")
    return tuple(decoded)


def _split_codes(value: str) -> tuple[str, ...]:
    return tuple(sorted(part.strip() for part in value.replace(",", ";").split(";") if part.strip()))


def _group_ids(
    rows: Iterable[object], group_field: str, identity_field: str
) -> defaultdict[str, list[str]]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[getattr(row, group_field)].append(getattr(row, identity_field))
    for values in grouped.values():
        values.sort()
    return grouped


def _entity_evidence_status(source_status: str, identities: Sequence[str]) -> str:
    if source_status != "current":
        return source_status
    return "current" if identities else "missing"


def _missing_or_unavailable(source_status: str) -> str:
    return "missing" if source_status == "current" else source_status
