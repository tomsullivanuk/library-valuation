"""Conservative catalog reconciliation for accepted inventory holdings.

This PR6 boundary links current physical-copy belief to durable bibliographic
identity.  It deliberately does not create acquisitions, locations, reports,
or user-facing workflow orchestration, and it never reads arbitrary observation
``raw_evidence_json`` keys.
"""

from __future__ import annotations

import csv
import json
import re
import tempfile
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Iterable, Mapping

from valuation.libib import is_valid_isbn10, is_valid_isbn13, isbn10_to_isbn13
from valuation.libib_inventory import (
    ACCEPTED_RECONCILIATION_OUTCOMES,
    CONFIDENCE_VALUES,
    InventoryHoldingRepository,
    InventoryObservationRepository,
    InventoryReconciliationDecisionRepository,
    LibibRepositoryError,
    VersionedCsvRepository,
    _json_list,
    _parse_json_list,
    _publish_repository_set,
)
from valuation.repositories import CATALOG_ITEMS_FIELDNAMES


CATALOG_RECONCILIATION_SCHEMA_VERSION = "1"
CATALOG_RECONCILIATION_MODEL_VERSION = "inventory_catalog_reconciliation_v1"

CATALOG_DECISION_ORIGINS = frozenset({"automatic", "manual", "migration", "backfill"})
ELIGIBLE_CATALOG_STATUSES = frozenset({"", "active"})
INELIGIBLE_CATALOG_STATUSES = frozenset({"excluded", "merged", "invalid"})

ACCEPTED_CATALOG_OUTCOMES = frozenset(
    {
        "existing_catalog_item_linked",
        "existing_catalog_item_confirmed",
        "catalog_link_unchanged",
        "new_catalog_item_created",
    }
)
UNRESOLVED_CATALOG_OUTCOMES = frozenset(
    {
        "catalog_relink_requires_review",
        "multiple_catalog_candidates",
        "edition_or_catalog_identity_ambiguity",
        "conflicting_isbn_evidence",
        "insufficient_catalog_evidence",
        "catalog_candidate_requires_review",
        "manual_catalog_review_required",
        "catalog_candidate_ineligible",
        "physical_identity_unresolved",
    }
)
CATALOG_RECONCILIATION_OUTCOMES = ACCEPTED_CATALOG_OUTCOMES | UNRESOLVED_CATALOG_OUTCOMES

INVENTORY_CATALOG_RECONCILIATION_DECISION_FIELDNAMES = (
    "schema_version",
    "inventory_catalog_reconciliation_decision_id",
    "holding_id",
    "inventory_observation_id",
    "catalog_item_id",
    "candidate_catalog_item_ids_json",
    "candidate_catalog_statuses_json",
    "outcome",
    "decision_basis",
    "confidence",
    "reason_codes_json",
    "explanation",
    "decision_timestamp",
    "reconciliation_model_version",
    "decision_origin",
    "supersedes_decision_id",
)


class LibibCatalogReconciliationError(LibibRepositoryError):
    """Raised when catalog reconciliation cannot proceed without guessing."""


@dataclass(frozen=True)
class CatalogReconciliationResult:
    processed_holdings: int
    decisions_created: int
    catalog_items_created: int
    holdings_linked: int
    accepted_count: int
    unresolved_count: int
    unchanged_count: int
    outcome_counts: tuple[tuple[str, int], ...]


class InventoryCatalogReconciliationDecisionRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_CATALOG_RECONCILIATION_DECISION_FIELDNAMES
    schema_version = CATALOG_RECONCILIATION_SCHEMA_VERSION

    def validate(self, rows: list[dict[str, str]]) -> None:
        ids: set[str] = set()
        by_id: dict[str, dict[str, str]] = {}
        for row in rows:
            decision_id = row["inventory_catalog_reconciliation_decision_id"]
            if not decision_id or decision_id in ids:
                raise LibibCatalogReconciliationError(
                    f"Duplicate or blank catalog reconciliation decision ID in {self.path}"
                )
            ids.add(decision_id)
            by_id[decision_id] = row
            if not row["holding_id"] or not row["inventory_observation_id"]:
                raise LibibCatalogReconciliationError(
                    f"Catalog decision lacks holding or observation in {self.path}"
                )
            if row["outcome"] not in CATALOG_RECONCILIATION_OUTCOMES:
                raise LibibCatalogReconciliationError(
                    f"Invalid catalog reconciliation outcome in {self.path}"
                )
            if row["confidence"] not in CONFIDENCE_VALUES:
                raise LibibCatalogReconciliationError(
                    f"Invalid catalog reconciliation confidence in {self.path}"
                )
            if row["decision_origin"] not in CATALOG_DECISION_ORIGINS:
                raise LibibCatalogReconciliationError(
                    f"Invalid catalog decision origin in {self.path}"
                )
            if not row["decision_basis"] or not row["reconciliation_model_version"]:
                raise LibibCatalogReconciliationError(
                    f"Incomplete catalog reconciliation decision in {self.path}"
                )
            _json_string_list(row["candidate_catalog_item_ids_json"], self.path)
            _json_string_list(row["candidate_catalog_statuses_json"], self.path)
            _json_string_list(row["reason_codes_json"], self.path)
            if row["outcome"] in ACCEPTED_CATALOG_OUTCOMES and not row["catalog_item_id"]:
                raise LibibCatalogReconciliationError(
                    f"Accepted catalog decision lacks catalog item in {self.path}"
                )
        for row in rows:
            prior = row["supersedes_decision_id"]
            if not prior:
                continue
            if prior == row["inventory_catalog_reconciliation_decision_id"] or prior not in by_id:
                raise LibibCatalogReconciliationError(
                    f"Invalid catalog decision supersession in {self.path}"
                )
            if by_id[prior]["holding_id"] != row["holding_id"]:
                raise LibibCatalogReconciliationError(
                    f"Catalog decision supersedes a decision for another holding in {self.path}"
                )
        _validate_no_branches_or_cycles(rows, self.path)


class StrictCatalogRepository:
    """Strict adapter for the existing fixed-header catalog repository."""

    fieldnames = tuple(CATALOG_ITEMS_FIELDNAMES)

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        try:
            with self.path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != self.fieldnames:
                    raise LibibCatalogReconciliationError(
                        f"Unsupported or malformed catalog header: {self.path}"
                    )
                rows = [dict(row) for row in reader]
        except UnicodeDecodeError as exc:
            raise LibibCatalogReconciliationError(
                f"Catalog repository must be UTF-8: {self.path}"
            ) from exc
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                raise LibibCatalogReconciliationError(
                    f"Malformed catalog repository row: {self.path}"
                )
        self.validate(rows)
        return rows

    def validate(self, rows: list[dict[str, str]]) -> None:
        ids = [row["catalog_item_id"] for row in rows]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            raise LibibCatalogReconciliationError(
                f"Blank or duplicate catalog_item_id in {self.path}"
            )

    def rendered_bytes(self, rows: list[dict[str, str]]) -> bytes:
        self.validate(rows)
        with tempfile.SpooledTemporaryFile(mode="w+", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows({field: row.get(field, "") for field in self.fieldnames} for row in rows)
            handle.seek(0)
            return handle.read().encode("utf-8")


def catalog_reconciliation_repository_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "inventory_catalog_reconciliation_decisions.csv"


def reconcile_inventory_catalog(
    *,
    data_dir: str | Path,
    catalog_path: str | Path | None = None,
    holding_ids: Iterable[str] | None = None,
    catalog_status_by_id: Mapping[str, str] | None = None,
    now: Callable[[], datetime] | None = None,
) -> CatalogReconciliationResult:
    """Reconcile eligible current holdings to catalog identity atomically."""

    data_dir = Path(data_dir)
    holdings_repo = InventoryHoldingRepository(data_dir / "inventory_holdings.csv")
    observations_repo = InventoryObservationRepository(data_dir / "inventory_observations.csv")
    physical_decisions_repo = InventoryReconciliationDecisionRepository(
        data_dir / "inventory_reconciliation_decisions.csv"
    )
    catalog_repo = StrictCatalogRepository(catalog_path or data_dir / "catalog_items.csv")
    decisions_repo = InventoryCatalogReconciliationDecisionRepository(
        catalog_reconciliation_repository_path(data_dir)
    )

    holdings = holdings_repo.load()
    observations = observations_repo.load()
    physical_decisions = physical_decisions_repo.load()
    catalog = catalog_repo.load()
    decisions = decisions_repo.load()
    status_by_id = _validate_statuses(catalog, catalog_status_by_id or {})
    _validate_cross_repository_state(
        holdings, observations, physical_decisions, catalog, decisions
    )

    selected = set(holding_ids) if holding_ids is not None else None
    known_holding_ids = {row["holding_id"] for row in holdings}
    if selected is not None and not selected <= known_holding_ids:
        raise LibibCatalogReconciliationError("Unknown selected holding_id")

    observations_by_id = {row["inventory_observation_id"]: row for row in observations}
    current_catalog_decisions = _current_decisions(decisions)
    timestamp = _timestamp((now or _utc_now)())
    created_decisions: list[dict[str, str]] = []
    catalog_items_created = 0
    holdings_linked = 0
    unchanged_count = 0

    for holding in sorted(holdings, key=lambda row: row["holding_id"]):
        if selected is not None and holding["holding_id"] not in selected:
            continue
        prior_catalog_decision = current_catalog_decisions.get(holding["holding_id"])
        if (
            prior_catalog_decision is not None
            and prior_catalog_decision["inventory_observation_id"]
            == holding["latest_inventory_observation_id"]
        ):
            unchanged_count += 1
            continue
        observation = observations_by_id.get(holding["latest_inventory_observation_id"])
        physical_accepted = _holding_has_accepted_physical_identity(
            holding, physical_decisions
        )
        if observation is None or not physical_accepted:
            # Holdings without accepted current physical provenance are not processed
            # automatically and receive no durable catalog decision.
            unchanged_count += 1
            continue

        decision, new_item = _reconcile_one(
            holding,
            observation,
            catalog,
            status_by_id,
            timestamp,
        )
        if prior_catalog_decision is not None:
            decision["supersedes_decision_id"] = prior_catalog_decision[
                "inventory_catalog_reconciliation_decision_id"
            ]
        if new_item is not None:
            catalog.append(new_item)
            status_by_id[new_item["catalog_item_id"]] = "active"
            catalog_items_created += 1
        created_decisions.append(decision)
        if decision["outcome"] in ACCEPTED_CATALOG_OUTCOMES:
            accepted_id = decision["catalog_item_id"]
            if holding["catalog_item_id"] != accepted_id:
                holding["catalog_item_id"] = accepted_id
                holdings_linked += 1

    if not created_decisions:
        return CatalogReconciliationResult(
            processed_holdings=0,
            decisions_created=0,
            catalog_items_created=0,
            holdings_linked=0,
            accepted_count=0,
            unresolved_count=0,
            unchanged_count=unchanged_count,
            outcome_counts=(),
        )

    decisions.extend(created_decisions)
    _validate_cross_repository_state(
        holdings, observations, physical_decisions, catalog, decisions
    )
    _publish_repository_set(
        (
            (catalog_repo, catalog),
            (decisions_repo, decisions),
            (holdings_repo, holdings),
        )
    )
    counts = Counter(row["outcome"] for row in created_decisions)
    accepted = sum(count for outcome, count in counts.items() if outcome in ACCEPTED_CATALOG_OUTCOMES)
    unresolved = sum(count for outcome, count in counts.items() if outcome in UNRESOLVED_CATALOG_OUTCOMES)
    if accepted + unresolved != len(created_decisions):
        raise LibibCatalogReconciliationError("Catalog reconciliation results do not balance")
    return CatalogReconciliationResult(
        processed_holdings=len(created_decisions),
        decisions_created=len(created_decisions),
        catalog_items_created=catalog_items_created,
        holdings_linked=holdings_linked,
        accepted_count=accepted,
        unresolved_count=unresolved,
        unchanged_count=unchanged_count,
        outcome_counts=tuple(sorted(counts.items())),
    )


def supersede_inventory_catalog_reconciliation_decision(
    *,
    data_dir: str | Path,
    supersedes_decision_id: str,
    outcome: str,
    decision_basis: str,
    confidence: str,
    catalog_item_id: str = "",
    candidate_catalog_item_ids: Iterable[str] = (),
    reason_codes: Iterable[str] = (),
    explanation: str = "",
    now: Callable[[], datetime] | None = None,
) -> str:
    """Append one explicit manual decision and update a holding only if accepted."""

    data_dir = Path(data_dir)
    decisions_repo = InventoryCatalogReconciliationDecisionRepository(
        catalog_reconciliation_repository_path(data_dir)
    )
    holdings_repo = InventoryHoldingRepository(data_dir / "inventory_holdings.csv")
    catalog_repo = StrictCatalogRepository(data_dir / "catalog_items.csv")
    decisions = decisions_repo.load()
    holdings = holdings_repo.load()
    catalog = catalog_repo.load()
    prior = next(
        (row for row in decisions if row["inventory_catalog_reconciliation_decision_id"] == supersedes_decision_id),
        None,
    )
    if prior is None:
        raise LibibCatalogReconciliationError("Superseded catalog decision does not exist")
    if any(row["supersedes_decision_id"] == supersedes_decision_id for row in decisions):
        raise LibibCatalogReconciliationError("Catalog decision has already been superseded")
    _validate_manual_values(outcome, confidence, catalog_item_id, catalog)
    decision_id = f"ICD-{uuid.uuid4()}"
    row = _decision_row(
        holding_id=prior["holding_id"],
        observation_id=prior["inventory_observation_id"],
        catalog_item_id=catalog_item_id,
        candidates=tuple(candidate_catalog_item_ids),
        statuses=(),
        outcome=outcome,
        basis=decision_basis,
        confidence=confidence,
        reason_codes=tuple(reason_codes),
        explanation=explanation,
        timestamp=_timestamp((now or _utc_now)()),
        origin="manual",
        supersedes=prior["inventory_catalog_reconciliation_decision_id"],
        decision_id=decision_id,
    )
    decisions.append(row)
    if outcome in ACCEPTED_CATALOG_OUTCOMES:
        holding = next((item for item in holdings if item["holding_id"] == prior["holding_id"]), None)
        if holding is None:
            raise LibibCatalogReconciliationError("Catalog decision references missing holding")
        holding["catalog_item_id"] = catalog_item_id
    decisions_repo.validate(decisions)
    _validate_catalog_references(holdings, catalog, decisions)
    _publish_repository_set(((decisions_repo, decisions), (holdings_repo, holdings)))
    return decision_id


def _reconcile_one(
    holding: dict[str, str],
    observation: Mapping[str, str],
    catalog: list[dict[str, str]],
    statuses: Mapping[str, str],
    timestamp: str,
) -> tuple[dict[str, str], dict[str, str] | None]:
    isbn10 = observation["normalized_isbn10"]
    isbn13 = observation["normalized_isbn13"]
    diagnostics = set(_parse_json_list(observation["diagnostic_codes_json"]))
    if "isbn_conflict" in diagnostics or (
        isbn10 and isbn13 and isbn10_to_isbn13(isbn10) != isbn13
    ):
        return _automatic_decision(
            holding, observation, (), statuses, "conflicting_isbn_evidence",
            "conflicting_normalized_isbn", "low", ("isbn_conflict",),
            "Valid ISBN evidence conflicts; catalog identity requires review.", timestamp,
        ), None

    candidates, method = _catalog_candidates(observation, catalog)
    eligible = [row for row in candidates if statuses[row["catalog_item_id"]] in ELIGIBLE_CATALOG_STATUSES]
    ineligible = [row for row in candidates if row not in eligible]
    all_ids = tuple(row["catalog_item_id"] for row in candidates)

    if len(eligible) > 1:
        return _automatic_decision(
            holding, observation, all_ids, statuses, "multiple_catalog_candidates",
            method, "low", ("multiple_catalog_candidates",),
            "Multiple active catalog records are plausible; no catalog link was selected.", timestamp,
        ), None
    if not eligible and ineligible:
        return _automatic_decision(
            holding, observation, all_ids, statuses, "catalog_candidate_ineligible",
            method, "low", ("excluded_merged_or_invalid_candidate",),
            "Only ineligible catalog candidates were found; no link was changed.", timestamp,
        ), None
    if len(eligible) == 1:
        candidate = eligible[0]
        candidate_id = candidate["catalog_item_id"]
        if _catalog_isbn_conflict(candidate):
            return _automatic_decision(
                holding, observation, all_ids, statuses,
                "conflicting_isbn_evidence", method, "low",
                ("catalog_candidate_isbn_conflict",),
                "The candidate catalog row contains conflicting valid ISBN values; no link was changed.",
                timestamp,
            ), None
        evidence_conflict = _catalog_metadata_conflict(observation, candidate)
        strong_isbn = method in {"exact_isbn13", "isbn10_derived_isbn13"}
        corroborated_title_creator = method == "title_creator_publisher"
        if evidence_conflict:
            outcome = "edition_or_catalog_identity_ambiguity"
            if holding["catalog_item_id"] and holding["catalog_item_id"] != candidate_id:
                outcome = "catalog_relink_requires_review"
            return _automatic_decision(
                holding, observation, all_ids, statuses, outcome, method, "low",
                ("conflicting_title_creator_evidence",),
                "Strong catalog evidence conflicts with title or creator evidence; the current link is unchanged.",
                timestamp,
            ), None
        if not (strong_isbn or corroborated_title_creator):
            return _automatic_decision(
                holding, observation, all_ids, statuses, "catalog_candidate_requires_review",
                method, "medium", ("insufficient_automatic_corroboration",),
                "A catalog candidate exists but does not meet the automatic-link threshold.", timestamp,
            ), None
        if holding["catalog_item_id"] and holding["catalog_item_id"] != candidate_id:
            return _automatic_decision(
                holding, observation, all_ids, statuses, "catalog_relink_requires_review",
                method, "medium", ("existing_catalog_link_differs",),
                "Evidence points to another catalog item; explicit supersession is required.", timestamp,
            ), None
        outcome = "existing_catalog_item_linked" if not holding["catalog_item_id"] else "existing_catalog_item_confirmed"
        return _automatic_decision(
            holding, observation, all_ids, statuses, outcome, method, "high" if strong_isbn else "medium",
            (method,), "A unique eligible catalog item met the automatic-link threshold.", timestamp,
            accepted_catalog_item_id=candidate_id,
        ), None

    if holding["catalog_item_id"]:
        return _automatic_decision(
            holding, observation, (), statuses, "catalog_link_unchanged",
            "prior_accepted_catalog_link", "high", ("no_conflicting_candidate",),
            "No conflicting candidate was found; the existing catalog link remains unchanged.", timestamp,
            accepted_catalog_item_id=holding["catalog_item_id"],
        ), None

    if _grouped_or_multivolume(observation):
        return _automatic_decision(
            holding, observation, (), statuses, "edition_or_catalog_identity_ambiguity",
            "grouped_or_multivolume_title_evidence", "low",
            ("grouped_or_multivolume_evidence",),
            "The title may represent a set or multiple volumes; one catalog identity was not created automatically.",
            timestamp,
        ), None

    if _strong_new_catalog_evidence(observation):
        catalog_item_id = _next_catalog_item_id(catalog)
        new_item = _new_catalog_item(catalog_item_id, observation)
        decision = _automatic_decision(
            holding, observation, (catalog_item_id,), {**statuses, catalog_item_id: "active"},
            "new_catalog_item_created", "unique_valid_isbn_no_candidate", "high",
            ("libib_discovered_catalog_identity", "no_acquisition_created"),
            "Strong unambiguous Libib evidence initialized a new catalog identity; no acquisition was inferred.",
            timestamp, accepted_catalog_item_id=catalog_item_id,
        )
        return decision, new_item

    title = observation["normalized_title"]
    creator = _creator_key(observation["normalized_creators"])
    reason = "missing_valid_isbn"
    if not title or not creator:
        reason = "insufficient_title_creator_evidence"
    return _automatic_decision(
        holding, observation, (), statuses, "insufficient_catalog_evidence",
        "no_automatic_candidate", "low", (reason,),
        "Evidence does not support an automatic catalog link or new catalog identity.", timestamp,
    ), None


def _catalog_candidates(
    observation: Mapping[str, str], catalog: Iterable[dict[str, str]]
) -> tuple[list[dict[str, str]], str]:
    rows = list(catalog)
    isbn13 = observation["normalized_isbn13"]
    isbn10 = observation["normalized_isbn10"]
    target13 = isbn13 or (isbn10_to_isbn13(isbn10) if isbn10 and is_valid_isbn10(isbn10) else "")
    if target13 and is_valid_isbn13(target13):
        matches = [row for row in rows if _catalog_isbn13(row) == target13]
        if matches:
            method = "exact_isbn13"
            if isbn10 and not observation["raw_isbn13"]:
                method = "isbn10_derived_isbn13"
            return matches, method
    title = observation["normalized_title"]
    creator = _creator_key(observation["normalized_creators"])
    if title and creator:
        matches = [
            row for row in rows
            if _key(row.get("title", "")) == _key(title)
            and _creator_key(row.get("author", "")) == creator
        ]
        if matches:
            publisher = _key(observation["raw_publisher"])
            corroborated = [row for row in matches if publisher and _key(row.get("publisher", "")) == publisher]
            if corroborated:
                return corroborated, "title_creator_publisher"
            return matches, "title_creator"
    if title:
        matches = [row for row in rows if _key(row.get("title", "")) == _key(title)]
        if matches:
            return matches, "title_only"
    if creator:
        matches = [row for row in rows if _creator_key(row.get("author", "")) == creator]
        if matches:
            return matches, "creator_only"
    return [], "no_candidate"


def _catalog_metadata_conflict(observation: Mapping[str, str], candidate: Mapping[str, str]) -> bool:
    title = _key(observation["normalized_title"])
    creator = _creator_key(observation["normalized_creators"])
    candidate_title = _key(candidate.get("title", ""))
    candidate_creator = _creator_key(candidate.get("author", ""))
    if creator in {"author unknown", "unknown author"}:
        creator = ""
    title_conflict = bool(
        title and candidate_title
        and SequenceMatcher(None, title, candidate_title).ratio() < 0.50
    )
    creator_conflict = bool(
        creator and candidate_creator
        and SequenceMatcher(None, creator, candidate_creator).ratio() < 0.50
    )
    # A unique exact ISBN commonly joins a source subtitle or contributor list
    # to a shorter canonical record. Treat metadata as strong contradictory
    # evidence only when both independently available dimensions disagree.
    return title_conflict and creator_conflict


def _strong_new_catalog_evidence(observation: Mapping[str, str]) -> bool:
    isbn13 = observation["normalized_isbn13"]
    isbn10 = observation["normalized_isbn10"]
    valid13 = bool(isbn13 and is_valid_isbn13(isbn13))
    derived13 = bool(isbn10 and is_valid_isbn10(isbn10) and is_valid_isbn13(isbn10_to_isbn13(isbn10)))
    return bool(
        (valid13 or derived13)
        and observation["normalized_title"]
        and observation["normalized_creators"]
        and observation["observed_copies"] == "1"
        and "isbn_conflict" not in _parse_json_list(observation["diagnostic_codes_json"])
    )


def _grouped_or_multivolume(observation: Mapping[str, str]) -> bool:
    title = _key(observation["normalized_title"])
    tokens = set(title.split())
    return bool(
        {"set", "volumes"} & tokens
        or "box set" in title
        or "boxed set" in title
        or "multi volume" in title
    )


def _new_catalog_item(catalog_item_id: str, observation: Mapping[str, str]) -> dict[str, str]:
    return {
        "catalog_item_id": catalog_item_id,
        "isbn13": observation["normalized_isbn13"] or isbn10_to_isbn13(observation["normalized_isbn10"]),
        "isbn10": observation["normalized_isbn10"],
        "title": observation["raw_title"] or observation["normalized_title"],
        "author": observation["raw_creators"] or observation["normalized_creators"],
        "publisher": observation["raw_publisher"],
        # PR5 observations do not expose publication date as an explicit field.
        # PR6 therefore leaves this blank instead of parsing raw_evidence_json.
        "publication_year": "",
        "source_fingerprint": observation["source_row_fingerprint"],
        "match_confidence": "high",
    }


def _automatic_decision(
    holding: Mapping[str, str], observation: Mapping[str, str], candidates: Iterable[str],
    statuses: Mapping[str, str], outcome: str, basis: str, confidence: str,
    reason_codes: Iterable[str], explanation: str, timestamp: str,
    accepted_catalog_item_id: str = "",
) -> dict[str, str]:
    candidate_ids = tuple(sorted(set(candidates)))
    return _decision_row(
        holding_id=holding["holding_id"], observation_id=observation["inventory_observation_id"],
        catalog_item_id=accepted_catalog_item_id, candidates=candidate_ids,
        statuses=tuple(f"{item}:{statuses.get(item, 'active') or 'active'}" for item in candidate_ids),
        outcome=outcome, basis=basis, confidence=confidence, reason_codes=tuple(reason_codes),
        explanation=explanation, timestamp=timestamp, origin="automatic",
    )


def _decision_row(
    *, holding_id: str, observation_id: str, catalog_item_id: str,
    candidates: Iterable[str], statuses: Iterable[str], outcome: str, basis: str,
    confidence: str, reason_codes: Iterable[str], explanation: str, timestamp: str,
    origin: str, supersedes: str = "", decision_id: str | None = None,
) -> dict[str, str]:
    return {
        "schema_version": CATALOG_RECONCILIATION_SCHEMA_VERSION,
        "inventory_catalog_reconciliation_decision_id": decision_id or f"ICD-{uuid.uuid4()}",
        "holding_id": holding_id,
        "inventory_observation_id": observation_id,
        "catalog_item_id": catalog_item_id,
        "candidate_catalog_item_ids_json": _json_list(candidates),
        "candidate_catalog_statuses_json": _json_list(statuses),
        "outcome": outcome,
        "decision_basis": basis,
        "confidence": confidence,
        "reason_codes_json": _json_list(reason_codes),
        "explanation": explanation,
        "decision_timestamp": timestamp,
        "reconciliation_model_version": CATALOG_RECONCILIATION_MODEL_VERSION,
        "decision_origin": origin,
        "supersedes_decision_id": supersedes,
    }


def _holding_has_accepted_physical_identity(
    holding: Mapping[str, str], decisions: Iterable[Mapping[str, str]]
) -> bool:
    decision_id = holding["latest_reconciliation_decision_id"]
    return any(
        row["inventory_reconciliation_decision_id"] == decision_id
        and row["holding_id"] == holding["holding_id"]
        and row["inventory_observation_id"] == holding["latest_inventory_observation_id"]
        and row["outcome"] in ACCEPTED_RECONCILIATION_OUTCOMES
        for row in decisions
    )


def _validate_cross_repository_state(
    holdings: list[dict[str, str]], observations: list[dict[str, str]],
    physical_decisions: list[dict[str, str]], catalog: list[dict[str, str]],
    catalog_decisions: list[dict[str, str]],
) -> None:
    InventoryCatalogReconciliationDecisionRepository(Path("<memory>")).validate(catalog_decisions)
    holding_ids = {row["holding_id"] for row in holdings}
    observation_ids = {row["inventory_observation_id"] for row in observations}
    catalog_ids = {row["catalog_item_id"] for row in catalog}
    for row in catalog_decisions:
        if row["holding_id"] not in holding_ids:
            raise LibibCatalogReconciliationError("Catalog decision references unknown holding")
        if row["inventory_observation_id"] not in observation_ids:
            raise LibibCatalogReconciliationError("Catalog decision references unknown observation")
        candidates = _parse_json_list(row["candidate_catalog_item_ids_json"])
        if any(value not in catalog_ids for value in candidates):
            raise LibibCatalogReconciliationError("Catalog decision references unknown candidate")
        if row["catalog_item_id"] and row["catalog_item_id"] not in catalog_ids:
            raise LibibCatalogReconciliationError("Catalog decision references unknown catalog item")
    _validate_catalog_references(holdings, catalog, catalog_decisions)
    # Loading the physical repositories plus this check prevents catalog work
    # from bypassing the accepted physical-identity boundary.
    for holding in holdings:
        if holding["catalog_item_id"] and holding["catalog_item_id"] not in catalog_ids:
            raise LibibCatalogReconciliationError("Holding references unknown catalog item")


def _validate_catalog_references(
    holdings: list[dict[str, str]], catalog: list[dict[str, str]],
    decisions: list[dict[str, str]],
) -> None:
    catalog_ids = {row["catalog_item_id"] for row in catalog}
    current = _current_decisions(decisions)
    for holding in holdings:
        catalog_id = holding["catalog_item_id"]
        if catalog_id and catalog_id not in catalog_ids:
            raise LibibCatalogReconciliationError("Holding references unknown catalog item")
        decision = current.get(holding["holding_id"])
        if decision and decision["outcome"] in ACCEPTED_CATALOG_OUTCOMES:
            if decision["catalog_item_id"] != catalog_id:
                raise LibibCatalogReconciliationError("Holding catalog link disagrees with current accepted decision")


def _current_decisions(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    rows = list(rows)
    superseded = {row["supersedes_decision_id"] for row in rows if row["supersedes_decision_id"]}
    current: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["inventory_catalog_reconciliation_decision_id"] in superseded:
            continue
        holding_id = row["holding_id"]
        if holding_id in current:
            raise LibibCatalogReconciliationError("Holding has multiple current catalog decisions")
        current[holding_id] = row
    return current


def _validate_no_branches_or_cycles(rows: list[dict[str, str]], path: Path) -> None:
    children = Counter(row["supersedes_decision_id"] for row in rows if row["supersedes_decision_id"])
    if any(count > 1 for count in children.values()):
        raise LibibCatalogReconciliationError(f"Branching catalog supersession in {path}")
    parent = {
        row["inventory_catalog_reconciliation_decision_id"]: row["supersedes_decision_id"]
        for row in rows if row["supersedes_decision_id"]
    }
    for start in parent:
        seen: set[str] = set()
        current = start
        while current in parent:
            if current in seen:
                raise LibibCatalogReconciliationError(f"Catalog supersession cycle in {path}")
            seen.add(current)
            current = parent[current]


def _validate_statuses(
    catalog: Iterable[dict[str, str]], supplied: Mapping[str, str]
) -> dict[str, str]:
    catalog_ids = {row["catalog_item_id"] for row in catalog}
    if not set(supplied) <= catalog_ids:
        raise LibibCatalogReconciliationError("Catalog status supplied for unknown catalog item")
    result = {catalog_id: supplied.get(catalog_id, "active") for catalog_id in catalog_ids}
    allowed = ELIGIBLE_CATALOG_STATUSES | INELIGIBLE_CATALOG_STATUSES
    if any(status not in allowed for status in result.values()):
        raise LibibCatalogReconciliationError("Unsupported catalog status")
    return result


def _validate_manual_values(
    outcome: str, confidence: str, catalog_item_id: str,
    catalog: Iterable[dict[str, str]],
) -> None:
    if outcome not in CATALOG_RECONCILIATION_OUTCOMES:
        raise LibibCatalogReconciliationError("Invalid catalog reconciliation outcome")
    if confidence not in CONFIDENCE_VALUES:
        raise LibibCatalogReconciliationError("Invalid catalog reconciliation confidence")
    catalog_ids = {row["catalog_item_id"] for row in catalog}
    if outcome in ACCEPTED_CATALOG_OUTCOMES and catalog_item_id not in catalog_ids:
        raise LibibCatalogReconciliationError("Accepted catalog decision requires valid catalog item")
    if catalog_item_id and catalog_item_id not in catalog_ids:
        raise LibibCatalogReconciliationError("Catalog decision references unknown catalog item")


def _catalog_isbn13(row: Mapping[str, str]) -> str:
    isbn13 = row.get("isbn13", "")
    if isbn13 and is_valid_isbn13(isbn13):
        return isbn13
    isbn10 = row.get("isbn10", "")
    if isbn10 and is_valid_isbn10(isbn10):
        return isbn10_to_isbn13(isbn10)
    return ""


def _catalog_isbn_conflict(row: Mapping[str, str]) -> bool:
    isbn13 = row.get("isbn13", "")
    isbn10 = row.get("isbn10", "")
    return bool(
        isbn13 and isbn10
        and is_valid_isbn13(isbn13)
        and is_valid_isbn10(isbn10)
        and isbn10_to_isbn13(isbn10) != isbn13
    )


def _next_catalog_item_id(catalog: Iterable[Mapping[str, str]]) -> str:
    highest = 0
    for row in catalog:
        match = re.fullmatch(r"BK(\d{6})", row["catalog_item_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"BK{highest + 1:06d}"


def _key(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _creator_key(value: str) -> str:
    return " ".join(sorted(re.findall(r"[a-z0-9]+", (value or "").casefold())))


def _json_string_list(value: str, path: Path) -> None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise LibibCatalogReconciliationError(f"Malformed JSON field in {path}") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise LibibCatalogReconciliationError(f"Expected JSON string list in {path}")


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
