"""Durable Libib imports, immutable observations, and physical reconciliation.

This module owns the PR5 evidence-to-belief boundary. It deliberately does not
match or create catalog items, create locations or acquisitions, generate
reports, discover inputs recursively, or expose a CLI workflow.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

from valuation.libib import (
    LibibDiagnostic,
    LibibSourceRecord,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    parse_libib_csv,
)


PARSER_VERSION = "libib_csv_v1"
NORMALIZATION_VERSION = "libib_normalization_v1"
RECONCILIATION_MODEL_VERSION = "physical_reconciliation_v1"
IMPORT_REPOSITORY_SCHEMA_VERSION = "1"
FOLDER_REPOSITORY_SCHEMA_VERSION = "1"
OBSERVATION_REPOSITORY_SCHEMA_VERSION = "1"
DECISION_REPOSITORY_SCHEMA_VERSION = "1"
HOLDING_REPOSITORY_SCHEMA_VERSION = "2"
REPOSITORY_SCHEMA_VERSION = IMPORT_REPOSITORY_SCHEMA_VERSION

AUDIT_COMPLETENESS_VALUES = frozenset({"complete_scope", "partial_scope", "unknown"})
CONFIDENCE_VALUES = frozenset({"high", "medium", "low", "unknown"})
DECISION_ORIGINS = frozenset({"automatic", "manual", "pr3_backfill"})
OBSERVATION_ORIGINS = frozenset({"direct", "pr3_backfill"})
EVIDENCE_COMPLETENESS_VALUES = frozenset({"full", "legacy_derived"})

ACCEPTED_RECONCILIATION_OUTCOMES = frozenset(
    {
        "new_holding_created",
        "existing_holding_confirmed",
        "existing_holding_reobserved",
        "holding_evidence_updated",
        "quantity_group_confirmed",
        "pr3_backfill_existing_holding",
    }
)
UNRESOLVED_RECONCILIATION_OUTCOMES = frozenset(
    {
        "holding_identity_changed_requires_reconciliation",
        "multiple_holding_candidates",
        "indistinguishable_duplicate_rows",
        "quantity_requires_review",
        "edition_or_identity_ambiguity",
        "insufficient_identity_evidence",
        "manual_review_required",
        "possible_duplicate",
    }
)
RECONCILIATION_OUTCOMES = (
    ACCEPTED_RECONCILIATION_OUTCOMES | UNRESOLVED_RECONCILIATION_OUTCOMES
)
AUDIT_COVERAGE_OUTCOMES = frozenset(
    {
        "verified_present",
        "not_yet_audited",
        "outside_audit_scope",
        "possible_missing",
        "verified_missing",
    }
)

INVENTORY_IMPORT_FIELDNAMES = (
    "schema_version",
    "inventory_import_id",
    "source_file_name",
    "source_file_hash",
    "source_collection_label",
    "folder_id",
    "folder_path",
    "audit_scope",
    "audit_completeness",
    "imported_at",
    "parser_version",
    "row_count",
)

INVENTORY_IMPORT_FOLDER_FIELDNAMES = (
    "schema_version",
    "folder_id",
    "folder_path",
    "expected_collection_label",
    "first_imported_at",
    "last_imported_at",
    "notes",
)

INVENTORY_OBSERVATION_FIELDNAMES = (
    "schema_version",
    "inventory_observation_id",
    "inventory_import_id",
    "source_row_number",
    "source_row_discriminator",
    "parser_version",
    "normalization_version",
    "source_row_fingerprint",
    "raw_evidence_json",
    "raw_isbn10",
    "raw_isbn13",
    "normalized_isbn10",
    "normalized_isbn13",
    "raw_title",
    "normalized_title",
    "raw_creators",
    "normalized_creators",
    "raw_publisher",
    "source_collection_label",
    "audit_scope",
    "audit_completeness",
    "raw_copies",
    "observed_copies",
    "raw_source_added_date",
    "normalized_source_added_date",
    "observed_at",
    "source_reference",
    "diagnostic_codes_json",
    "unknown_columns_json",
    "observation_origin",
    "evidence_completeness",
)

INVENTORY_RECONCILIATION_DECISION_FIELDNAMES = (
    "schema_version",
    "inventory_reconciliation_decision_id",
    "inventory_observation_id",
    "holding_id",
    "candidate_holding_ids_json",
    "outcome",
    "decision_basis",
    "confidence",
    "decision_timestamp",
    "reconciliation_model_version",
    "supersedes_decision_id",
    "decision_origin",
    "reason_codes_json",
    "explanation",
)

PR3_INVENTORY_HOLDING_FIELDNAMES = (
    "schema_version",
    "holding_id",
    "catalog_item_id",
    "inventory_import_id",
    "source_collection_label",
    "source_row_fingerprint",
    "source_title_key",
    "source_creator_key",
    "source_isbn_key",
    "current_location_id",
    "copies",
    "inventory_status",
    "last_verified_at",
    "raw_source_reference",
)

INVENTORY_HOLDING_FIELDNAMES = (
    "schema_version",
    "holding_id",
    "catalog_item_id",
    "inventory_import_id",
    "folder_id",
    "source_collection_label",
    "source_row_fingerprint",
    "source_title_key",
    "source_creator_key",
    "source_isbn_key",
    "current_location_id",
    "copies",
    "holding_state_type",
    "inventory_status",
    "last_verified_at",
    "latest_inventory_observation_id",
    "latest_reconciliation_decision_id",
    "verification_scope",
    "verification_completeness",
    "raw_source_reference",
)

_HOLDING_NAMESPACE = uuid.UUID("5c29019d-3d20-42f4-bdad-a48842783d79")
_OBSERVATION_NAMESPACE = uuid.UUID("f7cf0412-b9c2-48bd-8aaa-6246522e552b")
_DECISION_NAMESPACE = uuid.UUID("87abf8df-a99e-4ff7-a91e-41ac86c70663")

_HOLDING_IDENTITY_FIELDS = (
    "item_type",
    "title",
    "creators",
    "first_name",
    "last_name",
    "ean_isbn13",
    "upc_isbn10",
    "description",
    "publisher",
    "publish_date",
)

_PRIVACY_SAFE_OBSERVATION_FIELDS = (
    "item_type",
    "title",
    "creators",
    "first_name",
    "last_name",
    "collection",
    "ean_isbn13",
    "upc_isbn10",
    "description",
    "publisher",
    "publish_date",
    "added",
    "copies",
)


class LibibInventoryError(ValueError):
    """Raised when an import or reconciliation cannot be accepted safely."""


class LibibRepositoryError(LibibInventoryError):
    """Raised when durable inventory CSV state is malformed or incompatible."""


@dataclass(frozen=True)
class InventoryDiagnostic:
    code: str
    message: str
    registered_collection: str = ""
    observed_collection: str = ""
    folder_path: str = ""
    recommendation: str = ""
    holding_id: str = ""
    source_row_fingerprint: str = ""
    inventory_observation_id: str = ""


@dataclass(frozen=True)
class LibibInventoryImportResult:
    status: str
    inventory_import_id: str | None
    source_file_hash: str
    folder_id: str | None
    holdings_created: int
    observations_created: int = 0
    decisions_created: int = 0
    accepted_observation_count: int = 0
    unresolved_observation_count: int = 0
    rejected_observation_count: int = 0
    outcome_counts: tuple[tuple[str, int], ...] = ()
    diagnostics: tuple[InventoryDiagnostic, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status in {"imported", "duplicate"}


class VersionedCsvRepository:
    """Strict versioned CSV repository rendered only through atomic publication."""

    fieldnames: tuple[str, ...] = ()
    schema_version = ""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        header, rows = _read_csv(self.path)
        if header != self.fieldnames:
            raise LibibRepositoryError(
                f"Unsupported or malformed repository header: {self.path}"
            )
        self._validate_schema_versions(rows)
        self.validate(rows)
        return rows

    def _validate_schema_versions(self, rows: list[dict[str, str]]) -> None:
        for row in rows:
            if row["schema_version"] != self.schema_version:
                raise LibibRepositoryError(
                    f"Unsupported repository schema version {row['schema_version']!r}: "
                    f"{self.path}"
                )

    def validate(self, rows: list[dict[str, str]]) -> None:
        """Validate repository-specific invariants."""

    def rendered_bytes(self, rows: list[dict[str, str]]) -> bytes:
        self._validate_schema_versions(rows)
        self.validate(rows)
        with tempfile.SpooledTemporaryFile(
            mode="w+", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(
                handle, fieldnames=self.fieldnames, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(
                {field: row.get(field, "") for field in self.fieldnames}
                for row in rows
            )
            handle.seek(0)
            return handle.read().encode("utf-8")


class InventoryImportRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_IMPORT_FIELDNAMES
    schema_version = IMPORT_REPOSITORY_SCHEMA_VERSION

    def validate(self, rows: list[dict[str, str]]) -> None:
        _require_unique(rows, "inventory_import_id", self.path)
        _require_unique(rows, "source_file_hash", self.path)
        for row in rows:
            if not row["inventory_import_id"] or not _is_sha256(row["source_file_hash"]):
                raise LibibRepositoryError(f"Invalid import identity in {self.path}")
            if not row["audit_scope"].strip():
                raise LibibRepositoryError(f"Blank audit_scope in {self.path}")
            if row["audit_completeness"] not in AUDIT_COMPLETENESS_VALUES:
                raise LibibRepositoryError(f"Invalid audit_completeness in {self.path}")
            if _positive_or_zero_integer(row["row_count"]) is None:
                raise LibibRepositoryError(f"Invalid row_count in {self.path}")


class InventoryImportFolderRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_IMPORT_FOLDER_FIELDNAMES
    schema_version = FOLDER_REPOSITORY_SCHEMA_VERSION

    def validate(self, rows: list[dict[str, str]]) -> None:
        _require_unique(rows, "folder_id", self.path)
        _require_unique(rows, "folder_path", self.path)
        for row in rows:
            if not row["folder_id"] or not row["folder_path"]:
                raise LibibRepositoryError(f"Incomplete folder registration in {self.path}")
            if not row["expected_collection_label"]:
                raise LibibRepositoryError(f"Incomplete folder registration in {self.path}")


class InventoryObservationRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_OBSERVATION_FIELDNAMES
    schema_version = OBSERVATION_REPOSITORY_SCHEMA_VERSION

    def validate(self, rows: list[dict[str, str]]) -> None:
        _require_unique(rows, "inventory_observation_id", self.path)
        _require_unique_pairs(
            rows,
            "inventory_import_id",
            "source_row_discriminator",
            self.path,
        )
        for row in rows:
            if not row["inventory_observation_id"] or not row["inventory_import_id"]:
                raise LibibRepositoryError(f"Invalid observation identity in {self.path}")
            if not _is_sha256(row["source_row_fingerprint"]):
                raise LibibRepositoryError(f"Invalid observation fingerprint in {self.path}")
            if row["audit_completeness"] not in AUDIT_COMPLETENESS_VALUES:
                raise LibibRepositoryError(f"Invalid observation completeness in {self.path}")
            if row["observation_origin"] not in OBSERVATION_ORIGINS:
                raise LibibRepositoryError(f"Invalid observation origin in {self.path}")
            if row["evidence_completeness"] not in EVIDENCE_COMPLETENESS_VALUES:
                raise LibibRepositoryError(
                    f"Invalid observation evidence completeness in {self.path}"
                )
            _require_json_object(row["raw_evidence_json"], self.path)
            _require_json_list(row["diagnostic_codes_json"], self.path)
            _require_json_list(row["unknown_columns_json"], self.path)
            if row["observed_copies"] and _positive_integer(row["observed_copies"]) is None:
                raise LibibRepositoryError(f"Invalid observed copies in {self.path}")


class InventoryReconciliationDecisionRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_RECONCILIATION_DECISION_FIELDNAMES
    schema_version = DECISION_REPOSITORY_SCHEMA_VERSION

    def validate(self, rows: list[dict[str, str]]) -> None:
        _require_unique(rows, "inventory_reconciliation_decision_id", self.path)
        ids = {row["inventory_reconciliation_decision_id"] for row in rows}
        by_id = {row["inventory_reconciliation_decision_id"]: row for row in rows}
        for row in rows:
            if not row["inventory_observation_id"]:
                raise LibibRepositoryError(f"Decision lacks observation in {self.path}")
            if row["outcome"] not in RECONCILIATION_OUTCOMES:
                raise LibibRepositoryError(f"Invalid reconciliation outcome in {self.path}")
            if row["confidence"] not in CONFIDENCE_VALUES:
                raise LibibRepositoryError(f"Invalid reconciliation confidence in {self.path}")
            if row["decision_origin"] not in DECISION_ORIGINS:
                raise LibibRepositoryError(f"Invalid decision origin in {self.path}")
            if not row["decision_basis"] or not row["reconciliation_model_version"]:
                raise LibibRepositoryError(f"Incomplete reconciliation decision in {self.path}")
            _require_json_list(row["candidate_holding_ids_json"], self.path)
            _require_json_list(row["reason_codes_json"], self.path)
            supersedes = row["supersedes_decision_id"]
            if supersedes:
                if supersedes not in ids or supersedes == row["inventory_reconciliation_decision_id"]:
                    raise LibibRepositoryError(f"Invalid decision supersession in {self.path}")
                if by_id[supersedes]["inventory_observation_id"] != row["inventory_observation_id"]:
                    raise LibibRepositoryError(
                        f"Superseded decision belongs to another observation in {self.path}"
                    )
        _validate_supersession_acyclic(rows, self.path)


class InventoryHoldingRepository(VersionedCsvRepository):
    fieldnames = INVENTORY_HOLDING_FIELDNAMES
    schema_version = HOLDING_REPOSITORY_SCHEMA_VERSION

    def load_with_migration(self) -> tuple[list[dict[str, str]], bool]:
        if not self.path.exists():
            return [], False
        header, rows = _read_csv(self.path)
        if header == self.fieldnames:
            self._validate_schema_versions(rows)
            self.validate(rows)
            return rows, False
        if header != PR3_INVENTORY_HOLDING_FIELDNAMES:
            raise LibibRepositoryError(
                f"Unsupported or malformed repository header: {self.path}"
            )
        for row in rows:
            if row["schema_version"] != "1":
                raise LibibRepositoryError(
                    f"Unsupported repository schema version {row['schema_version']!r}: "
                    f"{self.path}"
                )
        migrated = [_migrate_pr3_holding(row) for row in rows]
        self.validate(migrated)
        return migrated, True

    def load(self) -> list[dict[str, str]]:
        return self.load_with_migration()[0]

    def validate(self, rows: list[dict[str, str]]) -> None:
        _require_unique(rows, "holding_id", self.path)
        for row in rows:
            if not row["holding_id"] or not _is_sha256(row["source_row_fingerprint"]):
                raise LibibRepositoryError(f"Invalid holding identity in {self.path}")
            if _positive_integer(row["copies"]) is None:
                raise LibibRepositoryError(f"Invalid copies in {self.path}")
            if row["holding_state_type"] not in {"physical_copy", "quantity_group"}:
                raise LibibRepositoryError(f"Invalid holding state type in {self.path}")
            if row["verification_completeness"] not in AUDIT_COMPLETENESS_VALUES:
                raise LibibRepositoryError(
                    f"Invalid holding verification completeness in {self.path}"
                )


def import_libib_inventory(
    source: str | Path,
    *,
    data_dir: str | Path,
    libib_input_dir: str | Path | None = None,
    audit_scope: str = "unknown",
    audit_completeness: str = "unknown",
    now: Callable[[], datetime] | None = None,
) -> LibibInventoryImportResult:
    """Import, observe, and reconcile one file or one selected audit directory."""

    audit_scope = _normalize_audit_scope(audit_scope)
    _validate_audit_completeness(audit_completeness)
    source_file = resolve_libib_import_source(source)
    source_hash = _file_sha256(source_file)
    paths = inventory_repository_paths(data_dir)
    repositories = _repositories(paths)

    imports = repositories["imports"].load()
    folders = repositories["folders"].load()
    observations = repositories["observations"].load()
    decisions = repositories["decisions"].load()
    holdings, holdings_migrated = repositories["holdings"].load_with_migration()

    backfilled = _backfill_pr3_state(
        imports=imports,
        observations=observations,
        decisions=decisions,
        holdings=holdings,
    )
    migration_changed = holdings_migrated or backfilled
    _validate_repository_set(imports, folders, observations, decisions, holdings)
    _validate_source_totals(imports, observations)
    _validate_current_terminal_decisions(observations, decisions)

    duplicate = next(
        (row for row in imports if row["source_file_hash"] == source_hash), None
    )
    if duplicate is not None:
        if migration_changed:
            _publish_all(repositories, imports, folders, observations, decisions, holdings)
        return LibibInventoryImportResult(
            status="duplicate",
            inventory_import_id=duplicate["inventory_import_id"],
            source_file_hash=source_hash,
            folder_id=duplicate["folder_id"] or None,
            holdings_created=0,
        )

    parsed = parse_libib_csv(source_file)
    collection_label = _single_collection_label(parsed.records)
    folder_path = _operational_folder_path(source_file.parent, libib_input_dir)
    folder = next((row for row in folders if row["folder_path"] == folder_path), None)
    if folder is not None and folder["expected_collection_label"] != collection_label:
        if migration_changed:
            _publish_all(repositories, imports, folders, observations, decisions, holdings)
        return _collection_mismatch_result(
            source_hash, folder, folder_path, collection_label
        )

    imported_at = _iso_timestamp((now or _utc_now)())
    if folder_path and folder is None:
        folder = {
            "schema_version": FOLDER_REPOSITORY_SCHEMA_VERSION,
            "folder_id": f"LBF-{uuid.uuid4()}",
            "folder_path": folder_path,
            "expected_collection_label": collection_label,
            "first_imported_at": imported_at,
            "last_imported_at": imported_at,
            "notes": "",
        }
        folders.append(folder)
    elif folder is not None:
        folder = dict(folder)
        folder["last_imported_at"] = imported_at
        folders = [
            folder if row["folder_id"] == folder["folder_id"] else row
            for row in folders
        ]

    inventory_import_id = f"LBI-{uuid.uuid4()}"
    folder_id = folder["folder_id"] if folder else ""
    import_row = {
        "schema_version": IMPORT_REPOSITORY_SCHEMA_VERSION,
        "inventory_import_id": inventory_import_id,
        "source_file_name": source_file.name,
        "source_file_hash": source_hash,
        "source_collection_label": collection_label,
        "folder_id": folder_id,
        "folder_path": folder_path,
        "audit_scope": audit_scope,
        "audit_completeness": audit_completeness,
        "imported_at": imported_at,
        "parser_version": PARSER_VERSION,
        "row_count": str(len(parsed.records)),
    }
    imports.append(import_row)

    new_observations = _build_observations(
        parsed.records,
        diagnostics=parsed.diagnostics,
        unknown_columns=parsed.unknown_columns,
        inventory_import_id=inventory_import_id,
        source_file_hash=source_hash,
        audit_scope=audit_scope,
        audit_completeness=audit_completeness,
        observed_at=imported_at,
    )
    observations.extend(new_observations)

    new_decisions, holdings_created = _reconcile_observations(
        new_observations,
        holdings=holdings,
        folder_id=folder_id,
        decision_timestamp=imported_at,
    )
    decisions.extend(new_decisions)
    _validate_repository_set(imports, folders, observations, decisions, holdings)
    _validate_source_totals(imports, observations)
    _validate_current_terminal_decisions(observations, decisions)
    _publish_all(repositories, imports, folders, observations, decisions, holdings)

    counts = Counter(row["outcome"] for row in new_decisions)
    accepted_count = sum(
        count for outcome, count in counts.items() if outcome in ACCEPTED_RECONCILIATION_OUTCOMES
    )
    unresolved_count = sum(
        count
        for outcome, count in counts.items()
        if outcome in UNRESOLVED_RECONCILIATION_OUTCOMES
    )
    if accepted_count + unresolved_count != len(new_observations):
        raise LibibRepositoryError("Reconciliation result counts do not balance observations")
    unresolved_diagnostics = tuple(
        InventoryDiagnostic(
            code=row["outcome"],
            message=row["explanation"],
            folder_path=folder_path,
            holding_id=row["holding_id"],
            inventory_observation_id=row["inventory_observation_id"],
        )
        for row in new_decisions
        if row["outcome"] in UNRESOLVED_RECONCILIATION_OUTCOMES
    )
    return LibibInventoryImportResult(
        status="imported",
        inventory_import_id=inventory_import_id,
        source_file_hash=source_hash,
        folder_id=folder_id or None,
        holdings_created=holdings_created,
        observations_created=len(new_observations),
        decisions_created=len(new_decisions),
        accepted_observation_count=accepted_count,
        unresolved_observation_count=unresolved_count,
        rejected_observation_count=0,
        outcome_counts=tuple(sorted(counts.items())),
        diagnostics=unresolved_diagnostics,
    )


def supersede_inventory_reconciliation_decision(
    *,
    data_dir: str | Path,
    supersedes_decision_id: str,
    outcome: str,
    decision_basis: str,
    confidence: str,
    holding_id: str = "",
    candidate_holding_ids: Iterable[str] = (),
    reason_codes: Iterable[str] = (),
    explanation: str = "",
    now: Callable[[], datetime] | None = None,
) -> str:
    """Append one explicit manual supersession; never edit the prior decision."""

    paths = inventory_repository_paths(data_dir)
    repositories = _repositories(paths)
    imports = repositories["imports"].load()
    folders = repositories["folders"].load()
    observations = repositories["observations"].load()
    decisions = repositories["decisions"].load()
    holdings, migrated = repositories["holdings"].load_with_migration()
    if migrated:
        raise LibibRepositoryError(
            "PR3 holdings require import/backfill before manual decision supersession"
        )
    prior = next(
        (
            row
            for row in decisions
            if row["inventory_reconciliation_decision_id"] == supersedes_decision_id
        ),
        None,
    )
    if prior is None:
        raise LibibRepositoryError("Superseded reconciliation decision does not exist")
    if any(row["supersedes_decision_id"] == supersedes_decision_id for row in decisions):
        raise LibibRepositoryError("Reconciliation decision has already been superseded")
    _validate_new_decision_values(outcome, confidence, holding_id, holdings)

    timestamp = _iso_timestamp((now or _utc_now)())
    decision_id = f"IRD-{uuid.uuid4()}"
    row = {
        "schema_version": DECISION_REPOSITORY_SCHEMA_VERSION,
        "inventory_reconciliation_decision_id": decision_id,
        "inventory_observation_id": prior["inventory_observation_id"],
        "holding_id": holding_id,
        "candidate_holding_ids_json": _json_list(sorted(set(candidate_holding_ids))),
        "outcome": outcome,
        "decision_basis": decision_basis,
        "confidence": confidence,
        "decision_timestamp": timestamp,
        "reconciliation_model_version": RECONCILIATION_MODEL_VERSION,
        "supersedes_decision_id": supersedes_decision_id,
        "decision_origin": "manual",
        "reason_codes_json": _json_list(sorted(set(reason_codes))),
        "explanation": explanation,
    }
    decisions.append(row)

    if outcome in ACCEPTED_RECONCILIATION_OUTCOMES:
        observation = next(
            obs
            for obs in observations
            if obs["inventory_observation_id"] == prior["inventory_observation_id"]
        )
        holdings[:] = [
            _apply_observation_to_holding(
                existing,
                observation,
                decision_id=decision_id,
                decision_timestamp=timestamp,
            )
            if existing["holding_id"] == holding_id
            else existing
            for existing in holdings
        ]

    _validate_repository_set(imports, folders, observations, decisions, holdings)
    _validate_current_terminal_decisions(observations, decisions)
    _publish_repository_set(
        (
            (repositories["decisions"], decisions),
            (repositories["holdings"], holdings),
        )
    )
    return decision_id


def audit_absence_outcome(*, audit_completeness: str, in_scope: bool) -> str:
    """Return the only safe PR5 absence interpretation; mutate no repositories."""

    _validate_audit_completeness(audit_completeness)
    if not in_scope:
        return "outside_audit_scope"
    if audit_completeness == "complete_scope":
        return "possible_missing"
    return "not_yet_audited"


def resolve_libib_import_source(source: str | Path) -> Path:
    """Resolve one file or the single direct CSV in an audit-area directory."""

    path = Path(source)
    if path.is_file():
        return path
    if not path.is_dir():
        raise LibibInventoryError(f"Libib input does not exist: {path}")
    candidates = sorted(
        candidate
        for candidate in path.iterdir()
        if candidate.is_file() and candidate.suffix.lower() == ".csv"
    )
    if len(candidates) != 1:
        raise LibibInventoryError(
            f"Audit-area directory must contain exactly one direct CSV; "
            f"found {len(candidates)}: {path}"
        )
    return candidates[0]


def inventory_repository_paths(data_dir: str | Path) -> dict[str, Path]:
    root = Path(data_dir)
    return {
        "imports": root / "inventory_imports.csv",
        "folders": root / "inventory_import_folders.csv",
        "observations": root / "inventory_observations.csv",
        "decisions": root / "inventory_reconciliation_decisions.csv",
        "holdings": root / "inventory_holdings.csv",
    }


def source_row_fingerprint(record: LibibSourceRecord) -> str:
    """Hash identity-bearing row evidence without operational or quantity fields."""

    evidence = {key: record.raw_values.get(key, "") for key in _HOLDING_IDENTITY_FIELDS}
    canonical = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _repositories(paths: Mapping[str, Path]) -> dict[str, VersionedCsvRepository]:
    return {
        "imports": InventoryImportRepository(paths["imports"]),
        "folders": InventoryImportFolderRepository(paths["folders"]),
        "observations": InventoryObservationRepository(paths["observations"]),
        "decisions": InventoryReconciliationDecisionRepository(paths["decisions"]),
        "holdings": InventoryHoldingRepository(paths["holdings"]),
    }


def _build_observations(
    records: Iterable[LibibSourceRecord],
    *,
    diagnostics: Iterable[LibibDiagnostic],
    unknown_columns: Iterable[str],
    inventory_import_id: str,
    source_file_hash: str,
    audit_scope: str,
    audit_completeness: str,
    observed_at: str,
) -> list[dict[str, str]]:
    records = list(records)
    fingerprints = [source_row_fingerprint(record) for record in records]
    occurrences: defaultdict[str, int] = defaultdict(int)
    rows = []
    for record, fingerprint in zip(records, fingerprints, strict=True):
        occurrences[fingerprint] += 1
        occurrence = occurrences[fingerprint]
        discriminator = f"{fingerprint}:{occurrence}"
        observation_uuid = uuid.uuid5(
            _OBSERVATION_NAMESPACE,
            f"{inventory_import_id}:{discriminator}",
        )
        diagnostic_codes = sorted(
            {
                diagnostic.code
                for diagnostic in diagnostics
                if diagnostic.row_number in {None, record.source_row_number}
            }
        )
        raw_evidence = {
            field: record.raw_values.get(field, "")
            for field in _PRIVACY_SAFE_OBSERVATION_FIELDS
        }
        rows.append(
            {
                "schema_version": OBSERVATION_REPOSITORY_SCHEMA_VERSION,
                "inventory_observation_id": f"IOB-{observation_uuid}",
                "inventory_import_id": inventory_import_id,
                "source_row_number": str(record.source_row_number),
                "source_row_discriminator": discriminator,
                "parser_version": PARSER_VERSION,
                "normalization_version": NORMALIZATION_VERSION,
                "source_row_fingerprint": fingerprint,
                "raw_evidence_json": _json_object(raw_evidence),
                "raw_isbn10": record.raw_isbn10,
                "raw_isbn13": record.raw_isbn13,
                "normalized_isbn10": record.normalized_isbn10 or "",
                "normalized_isbn13": record.normalized_isbn13 or "",
                "raw_title": record.raw_values.get("title", ""),
                "normalized_title": _title_key(record),
                "raw_creators": record.raw_creators,
                "normalized_creators": _creator_key(record),
                "raw_publisher": record.raw_publisher,
                "source_collection_label": record.raw_collection,
                "audit_scope": audit_scope,
                "audit_completeness": audit_completeness,
                "raw_copies": record.raw_copies,
                "observed_copies": (
                    str(record.normalized_copies)
                    if record.normalized_copies is not None
                    else ""
                ),
                "raw_source_added_date": record.raw_added_date,
                "normalized_source_added_date": record.normalized_added_date or "",
                "observed_at": observed_at,
                "source_reference": (
                    f"sha256:{source_file_hash}#row:{record.source_row_number}"
                ),
                "diagnostic_codes_json": _json_list(diagnostic_codes),
                "unknown_columns_json": _json_list(sorted(unknown_columns)),
                "observation_origin": "direct",
                "evidence_completeness": "full",
            }
        )
    return rows


def _reconcile_observations(
    observations: list[dict[str, str]],
    *,
    holdings: list[dict[str, str]],
    folder_id: str,
    decision_timestamp: str,
) -> tuple[list[dict[str, str]], int]:
    fingerprint_counts = Counter(
        observation["source_row_fingerprint"] for observation in observations
    )
    decisions = []
    holdings_created = 0
    for observation in observations:
        fingerprint = observation["source_row_fingerprint"]
        if fingerprint_counts[fingerprint] > 1:
            decision = _decision_row(
                observation,
                outcome="indistinguishable_duplicate_rows",
                basis="duplicate_source_fingerprint_within_import",
                confidence="high",
                timestamp=decision_timestamp,
                reason_codes=("duplicate_fingerprint", "copy_identity_unavailable"),
                explanation=(
                    "Byte-identical identity evidence occurs more than once in the import; "
                    "no copy ordinal or holding identity was invented."
                ),
            )
            decisions.append(decision)
            continue

        copies = _positive_integer(observation["observed_copies"])
        if copies != 1:
            decision = _decision_row(
                observation,
                outcome="quantity_requires_review",
                basis="unsupported_source_quantity",
                confidence="high",
                timestamp=decision_timestamp,
                reason_codes=("copies_not_one",),
                explanation=(
                    "Observed copies is not exactly one; quantity is preserved as evidence "
                    "and no holding expansion was attempted."
                ),
            )
            decisions.append(decision)
            continue

        if _has_identity_conflict(observation):
            decisions.append(
                _decision_row(
                    observation,
                    outcome="edition_or_identity_ambiguity",
                    basis="conflicting_source_identifiers",
                    confidence="low",
                    timestamp=decision_timestamp,
                    reason_codes=("isbn_conflict",),
                    explanation="Conflicting identifier evidence prevents holding creation.",
                )
            )
            continue

        candidates = _holding_candidates(observation, holdings)
        candidate_ids = tuple(candidate["holding_id"] for candidate in candidates)
        exact = [
            candidate
            for candidate in candidates
            if candidate["source_row_fingerprint"] == fingerprint
        ]
        same_folder_exact = [
            candidate
            for candidate in exact
            if folder_id and candidate["folder_id"] == folder_id
        ]

        if len(same_folder_exact) == 1 and len(candidates) == 1:
            holding = same_folder_exact[0]
            decision = _decision_row(
                observation,
                outcome="existing_holding_reobserved",
                basis="exact_fingerprint_same_registered_folder",
                confidence="high",
                timestamp=decision_timestamp,
                holding_id=holding["holding_id"],
                candidates=candidate_ids,
                reason_codes=("exact_fingerprint", "same_folder_registration"),
                explanation="Exact prior evidence in the same registered folder confirms the holding.",
            )
            decisions.append(decision)
            holdings[:] = [
                _apply_observation_to_holding(
                    row,
                    observation,
                    decision_id=decision["inventory_reconciliation_decision_id"],
                    decision_timestamp=decision_timestamp,
                )
                if row["holding_id"] == holding["holding_id"]
                else row
                for row in holdings
            ]
            continue

        if len(candidates) > 1:
            decisions.append(
                _decision_row(
                    observation,
                    outcome="multiple_holding_candidates",
                    basis="multiple_physical_candidates",
                    confidence="low",
                    timestamp=decision_timestamp,
                    candidates=candidate_ids,
                    reason_codes=("multiple_candidates",),
                    explanation="More than one existing physical holding is plausible.",
                )
            )
            continue

        if len(candidates) == 1:
            candidate = candidates[0]
            outcome = (
                "possible_duplicate"
                if candidate["source_row_fingerprint"] == fingerprint
                else "holding_identity_changed_requires_reconciliation"
            )
            decisions.append(
                _decision_row(
                    observation,
                    outcome=outcome,
                    basis="single_nonautomatic_physical_candidate",
                    confidence="medium",
                    timestamp=decision_timestamp,
                    candidates=candidate_ids,
                    reason_codes=("identity_continuity_not_proven",),
                    explanation=(
                        "One holding is plausible, but changed evidence or folder context "
                        "prevents automatic physical-identity acceptance."
                    ),
                )
            )
            continue

        weak_candidates = _weak_holding_candidates(observation, holdings, folder_id)
        if weak_candidates:
            decisions.append(
                _decision_row(
                    observation,
                    outcome="edition_or_identity_ambiguity",
                    basis="partial_title_or_creator_continuity",
                    confidence="low",
                    timestamp=decision_timestamp,
                    candidates=(row["holding_id"] for row in weak_candidates),
                    reason_codes=("partial_bibliographic_overlap",),
                    explanation=(
                        "Partial title or creator continuity may represent edited evidence; "
                        "no new holding was created."
                    ),
                )
            )
            continue

        if not _sufficient_new_holding_evidence(observation):
            decisions.append(
                _decision_row(
                    observation,
                    outcome="insufficient_identity_evidence",
                    basis="weak_physical_identity_evidence",
                    confidence="low",
                    timestamp=decision_timestamp,
                    reason_codes=("isbn_or_title_creator_required",),
                    explanation="Evidence is too weak to create a distinct physical holding.",
                )
            )
            continue

        holding_id = _new_holding_id(observation, folder_id)
        if any(row["holding_id"] == holding_id for row in holdings):
            raise LibibRepositoryError("Deterministic holding identity collision")
        decision = _decision_row(
            observation,
            outcome="new_holding_created",
            basis=(
                "new_valid_isbn_no_candidate"
                if _observation_isbn_key(observation)
                else "new_title_creator_no_candidate"
            ),
            confidence="high" if _observation_isbn_key(observation) else "medium",
            timestamp=decision_timestamp,
            holding_id=holding_id,
            reason_codes=("no_existing_candidate", "copies_exactly_one"),
            explanation=(
                "Evidence supports one distinct physical holding and no existing holding "
                "is a credible candidate."
            ),
        )
        decisions.append(decision)
        holdings.append(
            _new_holding_row(
                observation,
                holding_id=holding_id,
                folder_id=folder_id,
                decision_id=decision["inventory_reconciliation_decision_id"],
                decision_timestamp=decision_timestamp,
            )
        )
        holdings_created += 1
    return decisions, holdings_created


def _holding_candidates(
    observation: Mapping[str, str], holdings: Iterable[dict[str, str]]
) -> list[dict[str, str]]:
    fingerprint = observation["source_row_fingerprint"]
    isbn_key = _observation_isbn_key(observation)
    title_key = observation["normalized_title"]
    creator_key = observation["normalized_creators"]
    candidates = []
    for holding in holdings:
        if holding["inventory_status"] not in {"verified_present", "unknown"}:
            continue
        exact = holding["source_row_fingerprint"] == fingerprint
        isbn_match = bool(isbn_key and holding["source_isbn_key"] == isbn_key)
        title_creator_match = bool(
            title_key
            and creator_key
            and holding["source_title_key"] == title_key
            and holding["source_creator_key"] == creator_key
            and not _has_distinct_valid_isbn_evidence(observation, holding)
        )
        if exact or isbn_match or title_creator_match:
            candidates.append(holding)
    return sorted(candidates, key=lambda row: row["holding_id"])


def _weak_holding_candidates(
    observation: Mapping[str, str],
    holdings: Iterable[dict[str, str]],
    folder_id: str,
) -> list[dict[str, str]]:
    """Return review-only partial overlaps; never automatic identity matches."""

    title_key = observation["normalized_title"]
    creator_key = observation["normalized_creators"]
    candidates = []
    for holding in holdings:
        if holding["inventory_status"] not in {"verified_present", "unknown"}:
            continue
        if folder_id and holding["folder_id"] != folder_id:
            continue
        title_overlap = bool(title_key and holding["source_title_key"] == title_key)
        creator_overlap = bool(
            creator_key and holding["source_creator_key"] == creator_key
        )
        if (
            (title_overlap or creator_overlap)
            and not _has_distinct_valid_isbn_evidence(observation, holding)
        ):
            candidates.append(holding)
    return sorted(candidates, key=lambda row: row["holding_id"])


def _decision_row(
    observation: Mapping[str, str],
    *,
    outcome: str,
    basis: str,
    confidence: str,
    timestamp: str,
    holding_id: str = "",
    candidates: Iterable[str] = (),
    reason_codes: Iterable[str] = (),
    explanation: str,
    origin: str = "automatic",
    supersedes: str = "",
) -> dict[str, str]:
    deterministic_key = (
        f"{observation['inventory_observation_id']}:{RECONCILIATION_MODEL_VERSION}:"
        f"{outcome}:{holding_id}:{supersedes}"
    )
    decision_uuid = uuid.uuid5(_DECISION_NAMESPACE, deterministic_key)
    return {
        "schema_version": DECISION_REPOSITORY_SCHEMA_VERSION,
        "inventory_reconciliation_decision_id": f"IRD-{decision_uuid}",
        "inventory_observation_id": observation["inventory_observation_id"],
        "holding_id": holding_id,
        "candidate_holding_ids_json": _json_list(sorted(set(candidates))),
        "outcome": outcome,
        "decision_basis": basis,
        "confidence": confidence,
        "decision_timestamp": timestamp,
        "reconciliation_model_version": RECONCILIATION_MODEL_VERSION,
        "supersedes_decision_id": supersedes,
        "decision_origin": origin,
        "reason_codes_json": _json_list(sorted(set(reason_codes))),
        "explanation": explanation,
    }


def _new_holding_row(
    observation: Mapping[str, str],
    *,
    holding_id: str,
    folder_id: str,
    decision_id: str,
    decision_timestamp: str,
) -> dict[str, str]:
    return {
        "schema_version": HOLDING_REPOSITORY_SCHEMA_VERSION,
        "holding_id": holding_id,
        "catalog_item_id": "",
        "inventory_import_id": observation["inventory_import_id"],
        "folder_id": folder_id,
        "source_collection_label": observation["source_collection_label"],
        "source_row_fingerprint": observation["source_row_fingerprint"],
        "source_title_key": observation["normalized_title"],
        "source_creator_key": observation["normalized_creators"],
        "source_isbn_key": _observation_isbn_key(observation),
        "current_location_id": "",
        "copies": "1",
        "holding_state_type": "physical_copy",
        "inventory_status": "verified_present",
        "last_verified_at": decision_timestamp,
        "latest_inventory_observation_id": observation["inventory_observation_id"],
        "latest_reconciliation_decision_id": decision_id,
        "verification_scope": observation["audit_scope"],
        "verification_completeness": observation["audit_completeness"],
        "raw_source_reference": observation["source_reference"],
    }


def _apply_observation_to_holding(
    holding: Mapping[str, str],
    observation: Mapping[str, str],
    *,
    decision_id: str,
    decision_timestamp: str,
) -> dict[str, str]:
    updated = dict(holding)
    updated.update(
        {
            "source_collection_label": observation["source_collection_label"],
            "source_row_fingerprint": observation["source_row_fingerprint"],
            "source_title_key": observation["normalized_title"],
            "source_creator_key": observation["normalized_creators"],
            "source_isbn_key": _observation_isbn_key(observation),
            "inventory_status": "verified_present",
            "last_verified_at": decision_timestamp,
            "latest_inventory_observation_id": observation["inventory_observation_id"],
            "latest_reconciliation_decision_id": decision_id,
            "verification_scope": observation["audit_scope"],
            "verification_completeness": observation["audit_completeness"],
            "raw_source_reference": observation["source_reference"],
        }
    )
    return updated


def _new_holding_id(observation: Mapping[str, str], folder_id: str) -> str:
    identity_scope = folder_id or observation["inventory_import_id"]
    value = f"{identity_scope}:{observation['source_row_fingerprint']}"
    return f"HLD-{uuid.uuid5(_HOLDING_NAMESPACE, value)}"


def _backfill_pr3_state(
    *,
    imports: list[dict[str, str]],
    observations: list[dict[str, str]],
    decisions: list[dict[str, str]],
    holdings: list[dict[str, str]],
) -> bool:
    changed = False
    observations_by_import: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for observation in observations:
        observations_by_import[observation["inventory_import_id"]].append(observation)
    holdings_by_import: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for holding in holdings:
        holdings_by_import[holding["inventory_import_id"]].append(holding)
    import_by_id = {row["inventory_import_id"]: row for row in imports}

    for import_row in imports:
        import_id = import_row["inventory_import_id"]
        expected = int(import_row["row_count"])
        existing = observations_by_import[import_id]
        if existing:
            if len(existing) != expected:
                raise LibibRepositoryError(
                    f"Observation total does not balance PR3 import {import_id}"
                )
            continue
        legacy_holdings = holdings_by_import[import_id]
        if len(legacy_holdings) != expected:
            raise LibibRepositoryError(
                f"Cannot backfill PR3 import {import_id}: row and holding totals differ"
            )
        for holding in sorted(legacy_holdings, key=lambda row: row["holding_id"]):
            observation = _legacy_observation(import_row, holding)
            decision = _decision_row(
                observation,
                outcome="pr3_backfill_existing_holding",
                basis="pr3_legacy_holding_backfill",
                confidence="unknown",
                timestamp=import_row["imported_at"],
                holding_id=holding["holding_id"],
                candidates=(holding["holding_id"],),
                reason_codes=("legacy_derived_evidence",),
                explanation=(
                    "PR3 holding evidence was backfilled without fabricating unavailable raw row data."
                ),
                origin="pr3_backfill",
            )
            observations.append(observation)
            decisions.append(decision)
            holding.update(
                {
                    "folder_id": import_row["folder_id"],
                    "latest_inventory_observation_id": observation[
                        "inventory_observation_id"
                    ],
                    "latest_reconciliation_decision_id": decision[
                        "inventory_reconciliation_decision_id"
                    ],
                    "verification_scope": import_row["audit_scope"],
                    "verification_completeness": import_row["audit_completeness"],
                }
            )
            changed = True

    unknown_imports = sorted(set(holdings_by_import) - set(import_by_id))
    if unknown_imports:
        raise LibibRepositoryError("Holding references unknown PR3 import")
    return changed


def _legacy_observation(
    import_row: Mapping[str, str], holding: Mapping[str, str]
) -> dict[str, str]:
    discriminator = f"legacy:{holding['holding_id']}"
    observation_uuid = uuid.uuid5(
        _OBSERVATION_NAMESPACE,
        f"{import_row['inventory_import_id']}:{discriminator}",
    )
    isbn_key = holding["source_isbn_key"]
    return {
        "schema_version": OBSERVATION_REPOSITORY_SCHEMA_VERSION,
        "inventory_observation_id": f"IOB-{observation_uuid}",
        "inventory_import_id": import_row["inventory_import_id"],
        "source_row_number": "",
        "source_row_discriminator": discriminator,
        "parser_version": import_row["parser_version"],
        "normalization_version": "pr3_persisted_keys_v1",
        "source_row_fingerprint": holding["source_row_fingerprint"],
        "raw_evidence_json": "{}",
        "raw_isbn10": "",
        "raw_isbn13": "",
        "normalized_isbn10": isbn_key if len(isbn_key) == 10 else "",
        "normalized_isbn13": isbn_key if len(isbn_key) == 13 else "",
        "raw_title": "",
        "normalized_title": holding["source_title_key"],
        "raw_creators": "",
        "normalized_creators": holding["source_creator_key"],
        "raw_publisher": "",
        "source_collection_label": holding["source_collection_label"],
        "audit_scope": import_row["audit_scope"],
        "audit_completeness": import_row["audit_completeness"],
        "raw_copies": holding["copies"],
        "observed_copies": holding["copies"],
        "raw_source_added_date": "",
        "normalized_source_added_date": "",
        "observed_at": import_row["imported_at"],
        "source_reference": holding["raw_source_reference"],
        "diagnostic_codes_json": _json_list(("pr3_legacy_derived_evidence",)),
        "unknown_columns_json": "[]",
        "observation_origin": "pr3_backfill",
        "evidence_completeness": "legacy_derived",
    }


def _migrate_pr3_holding(row: Mapping[str, str]) -> dict[str, str]:
    copies = row["copies"]
    return {
        "schema_version": HOLDING_REPOSITORY_SCHEMA_VERSION,
        "holding_id": row["holding_id"],
        "catalog_item_id": row["catalog_item_id"],
        "inventory_import_id": row["inventory_import_id"],
        "folder_id": "",
        "source_collection_label": row["source_collection_label"],
        "source_row_fingerprint": row["source_row_fingerprint"],
        "source_title_key": row["source_title_key"],
        "source_creator_key": row["source_creator_key"],
        "source_isbn_key": row["source_isbn_key"],
        "current_location_id": row["current_location_id"],
        "copies": copies,
        "holding_state_type": "physical_copy" if copies == "1" else "quantity_group",
        "inventory_status": row["inventory_status"],
        "last_verified_at": row["last_verified_at"],
        "latest_inventory_observation_id": "",
        "latest_reconciliation_decision_id": "",
        "verification_scope": "unknown",
        "verification_completeness": "unknown",
        "raw_source_reference": row["raw_source_reference"],
    }


def _validate_repository_set(
    imports: list[dict[str, str]],
    folders: list[dict[str, str]],
    observations: list[dict[str, str]],
    decisions: list[dict[str, str]],
    holdings: list[dict[str, str]],
) -> None:
    import_ids = {row["inventory_import_id"] for row in imports}
    folder_ids = {row["folder_id"] for row in folders}
    observation_ids = {row["inventory_observation_id"] for row in observations}
    holding_ids = {row["holding_id"] for row in holdings}
    decision_ids = {row["inventory_reconciliation_decision_id"] for row in decisions}
    decision_by_id = {
        row["inventory_reconciliation_decision_id"]: row for row in decisions
    }

    for row in imports:
        if row["folder_id"] and row["folder_id"] not in folder_ids:
            raise LibibRepositoryError("Inventory import references unknown folder_id")
    for row in observations:
        if row["inventory_import_id"] not in import_ids:
            raise LibibRepositoryError("Inventory observation references unknown import")
    for row in decisions:
        if row["inventory_observation_id"] not in observation_ids:
            raise LibibRepositoryError("Reconciliation decision references unknown observation")
        candidates = _parse_json_list(row["candidate_holding_ids_json"])
        if any(candidate not in holding_ids for candidate in candidates):
            raise LibibRepositoryError("Reconciliation decision references unknown candidate")
        if row["outcome"] in ACCEPTED_RECONCILIATION_OUTCOMES:
            if not row["holding_id"] or row["holding_id"] not in holding_ids:
                raise LibibRepositoryError("Accepted decision requires valid holding")
        elif row["holding_id"] and row["holding_id"] not in holding_ids:
            raise LibibRepositoryError("Decision references unknown holding")
    for row in holdings:
        if row["inventory_import_id"] not in import_ids:
            raise LibibRepositoryError("Inventory holding references unknown import")
        if row["folder_id"] and row["folder_id"] not in folder_ids:
            raise LibibRepositoryError("Inventory holding references unknown folder")
        if row["latest_inventory_observation_id"]:
            if row["latest_inventory_observation_id"] not in observation_ids:
                raise LibibRepositoryError("Holding references unknown latest observation")
        if row["latest_reconciliation_decision_id"]:
            if row["latest_reconciliation_decision_id"] not in decision_ids:
                raise LibibRepositoryError("Holding references unknown latest decision")
            latest = decision_by_id[row["latest_reconciliation_decision_id"]]
            if latest["holding_id"] != row["holding_id"]:
                raise LibibRepositoryError("Holding latest decision references another holding")
            if latest["inventory_observation_id"] != row["latest_inventory_observation_id"]:
                raise LibibRepositoryError("Holding latest provenance is inconsistent")
            if latest["outcome"] not in ACCEPTED_RECONCILIATION_OUTCOMES:
                raise LibibRepositoryError("Holding latest decision is not accepted")


def _validate_source_totals(
    imports: Iterable[dict[str, str]], observations: Iterable[dict[str, str]]
) -> None:
    counts = Counter(row["inventory_import_id"] for row in observations)
    for row in imports:
        if counts[row["inventory_import_id"]] != int(row["row_count"]):
            raise LibibRepositoryError(
                f"Observation source total does not balance import {row['inventory_import_id']}"
            )


def _validate_current_terminal_decisions(
    observations: Iterable[dict[str, str]], decisions: Iterable[dict[str, str]]
) -> None:
    decisions = list(decisions)
    superseded = {row["supersedes_decision_id"] for row in decisions if row["supersedes_decision_id"]}
    current_counts = Counter(
        row["inventory_observation_id"]
        for row in decisions
        if row["inventory_reconciliation_decision_id"] not in superseded
    )
    for observation in observations:
        if current_counts[observation["inventory_observation_id"]] != 1:
            raise LibibRepositoryError(
                "Each observation must have exactly one current terminal reconciliation decision"
            )


def _validate_supersession_acyclic(
    rows: list[dict[str, str]], path: Path
) -> None:
    parent = {
        row["inventory_reconciliation_decision_id"]: row["supersedes_decision_id"]
        for row in rows
        if row["supersedes_decision_id"]
    }
    for start in parent:
        seen = set()
        current = start
        while current in parent:
            if current in seen:
                raise LibibRepositoryError(f"Decision supersession cycle in {path}")
            seen.add(current)
            current = parent[current]


def _validate_new_decision_values(
    outcome: str,
    confidence: str,
    holding_id: str,
    holdings: Iterable[dict[str, str]],
) -> None:
    if outcome not in RECONCILIATION_OUTCOMES:
        raise LibibRepositoryError("Invalid reconciliation outcome")
    if confidence not in CONFIDENCE_VALUES:
        raise LibibRepositoryError("Invalid reconciliation confidence")
    holding_ids = {row["holding_id"] for row in holdings}
    if outcome in ACCEPTED_RECONCILIATION_OUTCOMES:
        if not holding_id or holding_id not in holding_ids:
            raise LibibRepositoryError("Accepted decision requires valid holding")
    elif holding_id and holding_id not in holding_ids:
        raise LibibRepositoryError("Decision references unknown holding")


def _publish_all(
    repositories: Mapping[str, VersionedCsvRepository],
    imports: list[dict[str, str]],
    folders: list[dict[str, str]],
    observations: list[dict[str, str]],
    decisions: list[dict[str, str]],
    holdings: list[dict[str, str]],
) -> None:
    _publish_repository_set(
        (
            (repositories["imports"], imports),
            (repositories["folders"], folders),
            (repositories["observations"], observations),
            (repositories["decisions"], decisions),
            (repositories["holdings"], holdings),
        )
    )


def _publish_repository_set(
    repository_rows: Iterable[tuple[VersionedCsvRepository, list[dict[str, str]]]],
) -> None:
    """Stage all CSVs, then replace with byte-for-byte rollback on failure."""

    prepared = [
        (repository, repository.rendered_bytes(rows))
        for repository, rows in repository_rows
    ]
    originals = {
        repository.path: (
            repository.path.read_bytes() if repository.path.exists() else None
        )
        for repository, _ in prepared
    }
    temp_paths: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for repository, content in prepared:
            repository.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=repository.path.parent, delete=False
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temp_paths[repository.path] = Path(handle.name)
        for repository, _ in prepared:
            os.replace(temp_paths.pop(repository.path), repository.path)
            replaced.append(repository.path)
    except Exception:
        for path in reversed(replaced):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    finally:
        for path in temp_paths.values():
            path.unlink(missing_ok=True)


def _collection_mismatch_result(
    source_hash: str,
    folder: Mapping[str, str],
    folder_path: str,
    collection_label: str,
) -> LibibInventoryImportResult:
    return LibibInventoryImportResult(
        status="review_required",
        inventory_import_id=None,
        source_file_hash=source_hash,
        folder_id=folder["folder_id"],
        holdings_created=0,
        diagnostics=(
            InventoryDiagnostic(
                code="collection_label_changed_or_misfiled",
                message=(
                    "Observed Libib collection differs from the registered audit-area label"
                ),
                registered_collection=folder["expected_collection_label"],
                observed_collection=collection_label,
                folder_path=folder_path,
                recommendation=(
                    "Confirm whether the collection was renamed or the export was "
                    "misfiled; do not create a location automatically."
                ),
            ),
        ),
    )


def _single_collection_label(records: Iterable[LibibSourceRecord]) -> str:
    labels = {record.raw_collection for record in records if record.raw_collection.strip()}
    if len(labels) != 1:
        raise LibibInventoryError(
            "A durable audit-area import requires exactly one non-empty Libib collection label"
        )
    return next(iter(labels))


def _operational_folder_path(parent: Path, libib_input_dir: str | Path | None) -> str:
    if libib_input_dir is None:
        return ""
    root = Path(libib_input_dir).resolve()
    try:
        relative = parent.resolve().relative_to(root)
    except ValueError:
        return ""
    if relative == Path("."):
        return ""
    return relative.as_posix()


def _sufficient_new_holding_evidence(observation: Mapping[str, str]) -> bool:
    return bool(
        _observation_isbn_key(observation)
        or (observation["normalized_title"] and observation["normalized_creators"])
    )


def _has_identity_conflict(observation: Mapping[str, str]) -> bool:
    return "isbn_conflict" in _parse_json_list(observation["diagnostic_codes_json"])


def _has_distinct_valid_isbn_evidence(
    observation: Mapping[str, str], holding: Mapping[str, str]
) -> bool:
    """Return true only when both sides carry valid, different ISBN identity."""

    if _has_identity_conflict(observation):
        return False
    observation_isbn13 = _normalized_isbn13(
        observation["normalized_isbn13"] or observation["normalized_isbn10"]
    )
    holding_isbn13 = _normalized_isbn13(holding["source_isbn_key"])
    return bool(
        observation_isbn13
        and holding_isbn13
        and observation_isbn13 != holding_isbn13
    )


def _normalized_isbn13(value: str) -> str:
    if len(value) == 13 and is_valid_isbn13(value):
        return value
    if len(value) == 10 and is_valid_isbn10(value):
        return isbn10_to_isbn13(value)
    return ""


def _observation_isbn_key(observation: Mapping[str, str]) -> str:
    return observation["normalized_isbn13"] or observation["normalized_isbn10"]


def _title_key(record: LibibSourceRecord) -> str:
    return _normalized_key(record.raw_values.get("title", ""))


def _creator_key(record: LibibSourceRecord) -> str:
    return _normalized_key(
        record.normalized_creators or record.primary_author_display or ""
    )


def _normalized_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            header = tuple(reader.fieldnames or ())
            rows = [dict(row) for row in reader]
    except UnicodeDecodeError as exc:
        raise LibibRepositoryError(f"Repository must be UTF-8: {path}") from exc
    except csv.Error as exc:
        raise LibibRepositoryError(f"Malformed CSV repository: {path}") from exc
    for row_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise LibibRepositoryError(f"Malformed repository row {row_number}: {path}")
    return header, rows


def _require_unique(rows: list[dict[str, str]], field: str, path: Path) -> None:
    values = [row[field] for row in rows]
    if len(values) != len(set(values)):
        raise LibibRepositoryError(f"Duplicate {field} in {path}")


def _require_unique_pairs(
    rows: list[dict[str, str]], first: str, second: str, path: Path
) -> None:
    values = [(row[first], row[second]) for row in rows]
    if len(values) != len(set(values)):
        raise LibibRepositoryError(f"Duplicate {first}/{second} in {path}")


def _require_json_list(value: str, path: Path) -> None:
    if not isinstance(_parse_json(value, path), list):
        raise LibibRepositoryError(f"Expected JSON list in {path}")


def _require_json_object(value: str, path: Path) -> None:
    if not isinstance(_parse_json(value, path), dict):
        raise LibibRepositoryError(f"Expected JSON object in {path}")


def _parse_json(value: str, path: Path) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise LibibRepositoryError(f"Malformed JSON field in {path}") from exc


def _parse_json_list(value: str) -> list[str]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise LibibRepositoryError("Expected JSON string list")
    return parsed


def _json_list(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _json_object(value: Mapping[str, str]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _positive_integer(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _positive_or_zero_integer(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalize_audit_scope(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise LibibInventoryError("audit_scope must be a nonblank descriptive value")
    return normalized


def _validate_audit_completeness(value: str) -> None:
    if value not in AUDIT_COMPLETENESS_VALUES:
        raise LibibInventoryError(
            "audit_completeness must be one of: "
            + ", ".join(sorted(AUDIT_COMPLETENESS_VALUES))
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise LibibInventoryError("Import timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
