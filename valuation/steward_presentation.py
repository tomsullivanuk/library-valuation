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
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

from valuation.completed_inventory import CompletedInventoryScope, resolve_completed_inventory

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
    identity_validated: bool = False


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
    item_price: str = ""
    item_subtotal: str = ""


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
    signal_explanation: str = ""


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
    description: str
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
    confidence_display: str = ""
    evidence_status_display: str = ""
    review_reason_display: str = ""


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
    description: str
    copy_count: int
    location_values: tuple[str, ...]
    location_status: str
    location_summary: str
    purchase_summary: str
    purchase_date: str
    acquisition_source: str
    acquisition_month: str
    acquisition_count: int
    resale_market_status: str
    resale_market_summary: str
    resale_market_card_summary: str
    estimated_value_display: str
    estimated_value: str
    estimated_value_precise_low: str
    estimated_value_precise_high: str
    estimated_value_sort_low: str
    estimated_value_sort_high: str
    estimated_value_currency: str
    disposition: str
    usable_market_estimate: bool = False


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
    completed_inventory: CompletedInventoryScope = CompletedInventoryScope()

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



def _plain_research_reasons(summary: str, fallback: str = "") -> str:
    """Explain recorded signal points without rescoring the assessment."""
    labels = {
        "old_publication_year": "An older publication date warrants a closer look",
        "university_press": "Published by a university press",
        "specialist_publisher": "Published by a specialist or scholarly publisher",
        "missing_lcc": "A library subject classification is missing",
        "missing_oclc": "A library catalog identifier is missing, making edition matching harder",
        "scholarly_lc_subject": "Its library subject classification suggests scholarly interest",
        "multiple_acquisitions": "Multiple purchase records warrant checking for duplicates or replacements",
        "low_metadata_confidence": "Some bibliographic details are incomplete or uncertain",
    }
    reasons = []
    for part in summary.split(";"):
        match = re.fullmatch(r"\s*([a-z_]+):([+-]?\d+)\s*", part)
        if not match:
            continue
        code, points = match.groups()
        label = labels.get(code, code.replace("_", " ").capitalize())
        reasons.append(f"{label} ({int(points):+d} points)")
    return "; ".join(reasons) or fallback or "No research reasons were recorded."


def _book_steward_summaries(
    *,
    acquisition_source_status: str,
    acquisitions: Sequence[AcquisitionView],
    inventory_source_status: str,
    holdings: Sequence[Mapping[str, str]],
    market_source_status: str,
    market: MarketEvidenceView | None,
    review_source_status: str,
    review: StewardReviewView | None,
) -> dict[str, object]:
    """Derive privacy-safe conclusions for the book-first Library view."""

    locations: list[str] = []
    if inventory_source_status != "current":
        location_status = inventory_source_status
        location_summary = {
            "stale": "Location information may be out of date",
            "incompatible": "Location information cannot be used",
        }.get(inventory_source_status, "Location information not included")
    elif not holdings:
        location_status = "no_physical_copy"
        location_summary = "Not Located"
    else:
        locations = sorted({
            (
                row.get("source_collection_label", "").strip()
                or row.get("current_location_id", "").strip()
            )
            for row in holdings
        } - {""})
        locations = sorted({re.sub(r"^Box\s+", "", value, flags=re.I) for value in locations},
                           key=lambda value: tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in re.split(r"(\d+)", value)))
        if not locations:
            location_status = "not_recorded"
            location_summary = "Not Located"
        elif len(locations) == 1:
            location_status = "confirmed"
            location_summary = locations[0]
        else:
            location_status = "multiple"
            location_summary = ", ".join(locations)

    latest_acquisition = _latest_acquisition(acquisitions)
    purchase_date = latest_acquisition.order_date if latest_acquisition else ""
    acquisition_source = (
        latest_acquisition.source.strip().title() if latest_acquisition else ""
    )
    acquisition_month = _acquisition_month(purchase_date)
    acquisition_count = len(acquisitions)
    if acquisition_source_status != "current":
        purchase_summary = {
            "stale": "Acquisition history may be out of date",
            "incompatible": "Acquisition history cannot be used",
        }.get(acquisition_source_status, "Acquisition history not included")
    elif not acquisitions:
        purchase_summary = "No acquisition record"
    elif len(acquisitions) == 1:
        source = acquisition_source
        when = _month_year(purchase_date)
        purchase_summary = " • ".join(value for value in (source, when) if value)
        if not purchase_summary:
            purchase_summary = "Acquisition recorded"
    else:
        purchase_summary = f"{len(acquisitions)} records"
        if purchase_date:
            purchase_summary += f" • latest {_month_year(purchase_date)}"

    if latest_acquisition and acquisition_source_status == "current":
        try:
            amount = Decimal(latest_acquisition.item_price)
            if amount.is_finite() and amount >= 0:
                rounded = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                currency = latest_acquisition.currency.strip()
                prefix = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency, (currency + " ") if currency else "")
                purchase_summary += f" • {prefix}{rounded:,.0f}"
        except (InvalidOperation, ValueError):
            pass

    estimated_value = ""
    estimated_value_precise_low = ""
    estimated_value_precise_high = ""
    estimated_value_sort_low = ""
    estimated_value_sort_high = ""
    estimated_currency = ""
    resale_card_summary = ""
    estimated_value_display = ""
    if market_source_status != "current":
        resale_status = market_source_status
        resale_summary = ""
    elif market is None:
        resale_status = "not_researched"
        resale_summary = "Not researched"
    elif market.evidence_status == "no_market_evidence":
        resale_status = "not_researched"
        resale_summary = "Not researched"
    else:
        estimated_value = market.likely_mid or market.likely_low or market.likely_high
        if estimated_value:
            estimated_currency = market.currency
            resale_status = "estimate_available"
            if market.likely_low and market.likely_high:
                estimated_value_precise_low = market.likely_low
                estimated_value_precise_high = market.likely_high
                (
                    estimated_value_sort_low,
                    estimated_value_sort_high,
                ) = _presentation_currency_range_values(
                    market.likely_low, market.likely_high
                )
                resale_summary = (
                    f"{_currency_prefix(market.currency)}"
                    f"{market.likely_low}–{market.likely_high}"
                )
                resale_card_summary = _rounded_currency_range(
                    market.likely_low, market.likely_high, market.currency
                )
            else:
                estimated_value_precise_low = estimated_value
                estimated_value_precise_high = estimated_value
                presented_value = _presentation_currency_value(estimated_value)
                estimated_value_sort_low = presented_value
                estimated_value_sort_high = presented_value
                resale_summary = f"{_currency_prefix(market.currency)}{estimated_value}"
                resale_card_summary = (
                    f"{_currency_prefix(market.currency)}"
                    f"{_format_presentation_currency_value(presented_value)}"
                )
            estimated_value_display = resale_card_summary
        else:
            resale_status = "no_reliable_estimate"
            resale_summary = "No reliable estimate"
    if not resale_card_summary:
        resale_card_summary = resale_summary

    return {
        "location_status": location_status,
        "location_summary": location_summary,
        "location_values": tuple(locations),
        "purchase_summary": purchase_summary,
        "purchase_date": purchase_date,
        "acquisition_source": acquisition_source,
        "acquisition_month": acquisition_month,
        "acquisition_count": acquisition_count,
        "usable_market_estimate": (
            resale_status == "estimate_available" and bool(estimated_currency)
            and market is not None and market.market_confidence in {
                "high_confidence_market_evidence", "moderate_confidence_market_evidence"}
        ),
        "resale_market_status": resale_status,
        "resale_market_summary": resale_summary,
        "resale_market_card_summary": resale_card_summary,
        "estimated_value_display": estimated_value_display,
        "estimated_value": estimated_value,
        "estimated_value_precise_low": estimated_value_precise_low,
        "estimated_value_precise_high": estimated_value_precise_high,
        "estimated_value_sort_low": estimated_value_sort_low,
        "estimated_value_sort_high": estimated_value_sort_high,
        "estimated_value_currency": estimated_currency,
        "disposition": (
            review.disposition
            if review and review.disposition
            else (
                ""
                if review_source_status == "current"
                else "information_not_included"
            )
        ),
    }


def _month_year(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%b %Y")
    except ValueError:
        return value


def _parsed_acquisition_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_acquisition(
    acquisitions: Sequence[AcquisitionView],
) -> AcquisitionView | None:
    if not acquisitions:
        return None
    dated = [
        (parsed, row.acquisition_id, row.acquisition_reference, row)
        for row in acquisitions
        if (parsed := _parsed_acquisition_datetime(row.order_date)) is not None
    ]
    if dated:
        return max(dated, key=lambda item: item[:3])[3]
    return max(
        acquisitions,
        key=lambda row: (row.acquisition_id, row.acquisition_reference),
    )


def _acquisition_month(value: str) -> str:
    parsed = _parsed_acquisition_datetime(value)
    return parsed.strftime("%Y-%m") if parsed else ""


def _currency_prefix(currency: str) -> str:
    return {
        "USD": "$",
        "GBP": "£",
        "EUR": "€",
        "CAD": "CA$",
        "AUD": "A$",
    }.get(currency.upper(), f"{currency} " if currency else "")


def _presentation_currency_value(value: str) -> str:
    try:
        numeric_value = Decimal(value)
    except InvalidOperation:
        return value
    rounded = numeric_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return format(rounded, "f")


def _presentation_currency_range_values(low: str, high: str) -> tuple[str, str]:
    return _presentation_currency_value(low), _presentation_currency_value(high)


def _format_presentation_currency_value(value: str) -> str:
    try:
        numeric_value = Decimal(value)
    except InvalidOperation:
        return value
    return format(numeric_value, ",f")


def _rounded_currency_range(low: str, high: str, currency: str) -> str:
    presented_low, presented_high = _presentation_currency_range_values(low, high)
    prefix = _currency_prefix(currency)
    return (
        f"{prefix}{_format_presentation_currency_value(presented_low)}–"
        f"{prefix}{_format_presentation_currency_value(presented_high)}"
    )


def build_steward_presentation(
    *,
    data_dir: str | Path,
    market_evidence: DerivedEvidenceInput | None = None,
    research_candidates: DerivedEvidenceInput | None = None,
    reports: Sequence[RegisteredReport] = (),
    generated_at: str = "",
    completed_inventory_declaration: Mapping | None = None,
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
            signal_explanation=_plain_research_reasons(row["research_signal_summary"], row["research_signal_explanations"]),
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
    acquisition_rows_by_catalog: defaultdict[str, list[AcquisitionView]] = defaultdict(list)
    for acquisition in acquisition_views:
        acquisition_rows_by_catalog[acquisition.catalog_item_id].append(acquisition)
    holdings_by_catalog: defaultdict[str, list[str]] = defaultdict(list)
    holding_rows_by_catalog: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in holding_rows:
        if row["catalog_item_id"]:
            holdings_by_catalog[row["catalog_item_id"]].append(row["holding_id"])
            holding_rows_by_catalog[row["catalog_item_id"]].append(row)
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
    observations_by_id = {
        observation.inventory_observation_id: observation
        for observation in observation_views
    }
    descriptions_by_catalog: defaultdict[str, list[str]] = defaultdict(list)
    for holding in holding_rows:
        catalog_item_id = holding["catalog_item_id"]
        observation = observations_by_id.get(holding["latest_inventory_observation_id"])
        if catalog_item_id and observation and observation.description:
            descriptions_by_catalog[catalog_item_id].append(observation.description)
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
            description=(
                sorted(
                    set(descriptions_by_catalog[row["catalog_item_id"]]),
                    key=lambda value: (-len(value), value),
                )[0]
                if descriptions_by_catalog[row["catalog_item_id"]]
                else ""
            ),
            copy_count=sum(
                int(holding.get("copies", "") or "1")
                for holding in holding_rows_by_catalog[row["catalog_item_id"]]
            ),
            **_book_steward_summaries(
                acquisition_source_status=acquisition_source.status,
                acquisitions=acquisition_rows_by_catalog[row["catalog_item_id"]],
                inventory_source_status=inventory["source"].status,
                holdings=holding_rows_by_catalog[row["catalog_item_id"]],
                market_source_status=market.source.status,
                market=market_by_catalog.get(row["catalog_item_id"]),
                review_source_status=review_source.status,
                review=review_by_catalog.get(row["catalog_item_id"]),
            ),
        )
        for row in sorted(catalog_rows, key=lambda item: item["catalog_item_id"])
    )

    completed_inventory = resolve_completed_inventory(data_dir, completed_inventory_declaration)
    if completed_inventory.completed:
        sources.append(SourceView(
            source_key="completed_inventory", authority="steward_declaration", status="current",
            row_count=completed_inventory.source_entries,
            content_sha256=hashlib.sha256(json.dumps(asdict(completed_inventory), sort_keys=True).encode()).hexdigest(),
            schema_version="completed_inventory_v1", generated_at="",
            explanation="Steward declared these explicit source imports a completed physical inventory."))
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
        completed_inventory=completed_inventory,
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
                item_price=row["item_price"],
                item_subtotal=row["item_subtotal"],
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
            description=_json_object_string(row["raw_evidence_json"], "description"),
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



def _plain_market_text(value: str) -> str:
    """Translate recorded market labels without changing evidence or estimates."""
    labels = {
        "high_confidence_market_evidence": "High — several well-matched listings support the estimate.",
        "moderate_confidence_market_evidence": "Moderate — reasonably matched listings support an estimate, with some uncertainty.",
        "thin_market_evidence": "Limited — fewer than three usable listings were recorded.",
        "ambiguous_edition_match": "Uncertain — the listings may describe a different edition or condition.",
        "mixed_currency_evidence": "Uncertain — the listings use different currencies.",
        "price_unavailable_evidence": "Uncertain — usable asking prices were not recorded.",
        "unknown_market_confidence": "Uncertain — the listings do not support a dependable confidence rating.",
        "observed_listings": "Seller asking-price listings were recorded.",
        "no_market_evidence": "No usable market listings were recorded.",
        "source_unavailable": "The market source was unavailable when researched.",
        "no_query": "No market search was recorded.",
        "usable_market_evidence_below_sale_review_threshold": "Comparable asking prices are available, but the estimated range is below the threshold used to suggest a sale review.",
        "asking_price_range_meets_initial_sale_review_threshold": "The asking-price range is high enough to consider reviewing this book for sale.",
        "uncertain_market_evidence_requires_manual_research": "The market evidence is uncertain and needs further research.",
        "thin_market_evidence_requires_manual_research": "Too few usable listings were found; further research is needed.",
        "asking_price_unavailable_requires_manual_research": "Usable asking prices are missing; further research is needed.",
        "mixed_currency_evidence_requires_manual_research": "The listings use different currencies and need manual comparison.",
        "fragile_asking_price_evidence": "Unusually high or low asking prices can substantially affect the estimate.",
        "ambiguous_edition_or_condition_match": "Check whether the listings match this book's edition and condition.",
        "market_evidence_unavailable_low_research_priority": "No usable market evidence is available; the existing research assessment gives this book low priority.",
        "market_evidence_unavailable_medium_research_priority": "No usable market evidence is available; the existing research assessment gives this book medium priority for further research.",
        "market_evidence_unavailable_high_research_priority": "No usable market evidence is available; the existing research assessment gives this book high priority for further research.",
        "insufficient_metadata_for_market_lookup": "The title or author details need checking before a useful market search can be made.",
        "no_review_rule_triggered": "The recorded evidence does not suggest an additional review task.",
    }
    parts = [part.strip() for part in value.split(";") if part.strip()]
    return " ".join(labels.get(part, part.replace("_", " ").capitalize()) for part in parts) or "Not recorded."


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
            confidence_display=_plain_market_text(row["market_confidence"]),
            evidence_status_display=_plain_market_text(row["evidence_status"]),
            review_reason_display=_plain_market_text(row["review_reason"]),
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
        if (
            public_path.is_absolute()
            or ".." in public_path.parts
            or not report.public_path
            or not public_path.parts
            or report.public_path != report.public_path.strip()
            or "\\" in report.public_path
            or "%" in report.public_path
            or "?" in report.public_path
            or "#" in report.public_path
            or ":" in public_path.parts[0]
            or any(ord(character) < 32 for character in report.public_path)
        ):
            raise StewardPresentationError("Report public_path must be safe and relative")
        path = Path(report.source_path)
        if not path.is_file():
            status, digest, explanation = "missing", "", "Registered report file is missing."
        else:
            digest = _file_sha256(path)
            format_name = report.format.casefold().lstrip(".")
            source_suffix = path.suffix.casefold().lstrip(".")
            public_suffix = public_path.suffix.casefold().lstrip(".")
            if (
                not format_name
                or source_suffix != format_name
                or public_suffix != format_name
            ):
                status, explanation = (
                    "incompatible",
                    "Registered report format and file extension do not agree.",
                )
            elif report.catalog_snapshot_sha256 == catalog_hash:
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
    if source.catalog_snapshot_sha256 == catalog_hash:
        status = "current"
        explanation = "Derived evidence matches the catalog snapshot."
    elif source.identity_validated:
        status = "current"
        explanation = "Explicit evidence identities were validated against the current catalog."
    else:
        status = "stale"
        explanation = "Derived evidence catalog snapshot is absent or does not match."
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


def _json_object_string(value: str, field: str) -> str:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise StewardPresentationError("Invalid JSON object in validated source") from exc
    if not isinstance(decoded, dict):
        raise StewardPresentationError("Invalid JSON object in validated source")
    result = decoded.get(field, "")
    return result if isinstance(result, str) else ""


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
