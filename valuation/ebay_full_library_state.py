"""Crash-safe, network-free state for resumable full-library eBay collection."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

from valuation.abebooks import MARKET_OBSERVATION_FIELDNAMES
from valuation.ebay_observations import sanitize_failure_reason


MANIFEST_SCHEMA_VERSION = "1.0"
LEDGER_SCHEMA_VERSION = "1.0"
OBSERVATION_PART_SCHEMA_VERSION = "1.0"
OBSERVATION_SCHEMA_VERSION = "market_observation_25_v1"
SOURCE_NAME = "ebay_active_listings"

STATUSES = {
    "pending",
    "in_progress",
    "observed",
    "no_results",
    "no_query",
    "source_unavailable_retryable",
    "source_unavailable_terminal",
    "failed_terminal",
}
TERMINAL_STATUSES = {
    "observed", "no_results", "no_query", "source_unavailable_terminal", "failed_terminal"
}
RETRYABLE_STATUSES = {"pending", "source_unavailable_retryable"}
PART_REQUIRED_STATUSES = {"observed", "no_results", "no_query", "source_unavailable_terminal"}
COMPATIBILITY_CRITICAL_MANIFEST_FIELDS = (
    "schema_version",
    "environment",
    "marketplace_id",
    "summary_input_fingerprint",
    "candidate_count",
    "ordered_catalog_ids_hash",
    "query_strategy_version",
    "observation_schema_version",
    "max_results_per_book",
    "source_name",
    "seller_identity_suppressed",
)
MANIFEST_FIELDS = {
    "schema_version", "run_id", "created_at", "environment", "marketplace_id",
    "summary_input_path", "summary_input_fingerprint", "candidate_count",
    "ordered_catalog_ids_hash", "query_strategy_version", "observation_schema_version",
    "max_results_per_book", "delay_seconds", "max_retries", "retry_delay_seconds",
    "source_name", "seller_identity_suppressed", "command_version", "notes",
}
LEDGER_ENTRY_FIELDS = {
    "catalog_item_id", "ordinal", "status", "attempt_count", "last_attempt_at",
    "completed_at", "query", "search_strategy", "observation_part_path",
    "observation_row_count", "safe_error_code", "safe_error_message",
    "retry_eligible", "retry_after", "updated_at",
}

ALLOWED_TRANSITIONS = {
    "pending": {"in_progress"},
    "in_progress": TERMINAL_STATUSES | {"source_unavailable_retryable"},
    "source_unavailable_retryable": {"pending", "in_progress", "source_unavailable_terminal", "failed_terminal"},
    "observed": set(),
    "no_results": set(),
    "no_query": set(),
    "source_unavailable_terminal": set(),
    "failed_terminal": set(),
}


class CheckpointError(ValueError):
    """Base exception for invalid or incompatible checkpoint state."""


class ManifestCompatibilityError(CheckpointError):
    """Raised when existing run state cannot be resumed safely."""


class CheckpointIntegrityError(CheckpointError):
    """Raised when ledger and observation parts disagree."""


def run_paths(run_dir: Path) -> dict[str, Path]:
    root = Path(run_dir)
    return {
        "root": root,
        "manifest": root / "manifest.json",
        "ledger": root / "ledger.json",
        "parts": root / "parts",
        "run_summary": root / "run_summary.json",
        "final": root / "final",
    }


def fingerprint_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def catalog_ids_hash(catalog_item_ids: Iterable[str]) -> str:
    payload = "\n".join(str(value) for value in catalog_item_ids)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def create_manifest(
    path: Path,
    *,
    run_id: str,
    created_at: str,
    environment: str,
    marketplace_id: str,
    summary_input_path: str,
    summary_input_fingerprint: str,
    candidate_count: int,
    ordered_catalog_ids_hash: str,
    query_strategy_version: str,
    max_results_per_book: int,
    delay_seconds: float,
    max_retries: int,
    retry_delay_seconds: float,
    command_version: str,
    notes: str = "",
) -> dict[str, object]:
    """Create one immutable manifest; an existing destination is never replaced."""
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": required_text(run_id, "run_id"),
        "created_at": required_text(created_at, "created_at"),
        "environment": required_text(environment, "environment"),
        "marketplace_id": required_text(marketplace_id, "marketplace_id"),
        "summary_input_path": required_text(summary_input_path, "summary_input_path"),
        "summary_input_fingerprint": required_text(
            summary_input_fingerprint, "summary_input_fingerprint"
        ),
        "candidate_count": nonnegative_int(candidate_count, "candidate_count"),
        "ordered_catalog_ids_hash": required_text(
            ordered_catalog_ids_hash, "ordered_catalog_ids_hash"
        ),
        "query_strategy_version": required_text(query_strategy_version, "query_strategy_version"),
        "observation_schema_version": OBSERVATION_SCHEMA_VERSION,
        "max_results_per_book": positive_int(max_results_per_book, "max_results_per_book"),
        "delay_seconds": nonnegative_float(delay_seconds, "delay_seconds"),
        "max_retries": nonnegative_int(max_retries, "max_retries"),
        "retry_delay_seconds": nonnegative_float(retry_delay_seconds, "retry_delay_seconds"),
        "source_name": SOURCE_NAME,
        "seller_identity_suppressed": True,
        "command_version": required_text(command_version, "command_version"),
        "notes": sanitize_checkpoint_text(notes) if notes else "",
    }
    write_json_atomic(path, manifest, replace=False)
    return manifest


def load_manifest(path: Path) -> dict[str, object]:
    manifest = load_json(path)
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise CheckpointError(f"Unsupported manifest schema version: {manifest.get('schema_version')!r}")
    if set(manifest) != MANIFEST_FIELDS:
        raise CheckpointError("Manifest fields do not match the supported schema")
    return manifest


def validate_manifest_compatibility(
    existing: Mapping[str, object], expected: Mapping[str, object]
) -> None:
    differences = [
        field for field in COMPATIBILITY_CRITICAL_MANIFEST_FIELDS
        if existing.get(field) != expected.get(field)
    ]
    if differences:
        raise ManifestCompatibilityError(
            "Incompatible resume manifest fields: " + ", ".join(differences)
        )


def initialize_ledger(
    path: Path, catalog_item_ids: Iterable[str], *, created_at: str
) -> dict[str, object]:
    ids = [required_text(value, "catalog_item_id") for value in catalog_item_ids]
    if len(ids) != len(set(ids)):
        raise CheckpointError("Duplicate catalog_item_id values are not allowed")
    if Path(path).exists():
        ledger = load_ledger(path)
        if [entry["catalog_item_id"] for entry in ledger["entries"]] != ids:
            raise ManifestCompatibilityError("Existing ledger candidate order is incompatible")
        return ledger
    ledger = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "created_at": required_text(created_at, "created_at"),
        "updated_at": required_text(created_at, "created_at"),
        "entries": [new_ledger_entry(value, ordinal, created_at) for ordinal, value in enumerate(ids)],
    }
    save_ledger_atomic(path, ledger, replace=False)
    return ledger


def new_ledger_entry(catalog_item_id: str, ordinal: int, updated_at: str) -> dict[str, object]:
    return {
        "catalog_item_id": catalog_item_id,
        "ordinal": ordinal,
        "status": "pending",
        "attempt_count": 0,
        "last_attempt_at": "",
        "completed_at": "",
        "query": "",
        "search_strategy": "",
        "observation_part_path": "",
        "observation_row_count": 0,
        "safe_error_code": "",
        "safe_error_message": "",
        "retry_eligible": True,
        "retry_after": "",
        "updated_at": updated_at,
    }


def load_ledger(path: Path) -> dict[str, object]:
    ledger = load_json(path)
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise CheckpointError(f"Unsupported ledger schema version: {ledger.get('schema_version')!r}")
    validate_ledger_shape(ledger)
    return ledger


def save_ledger_atomic(path: Path, ledger: Mapping[str, object], *, replace: bool = True) -> None:
    validate_ledger_shape(ledger)
    write_json_atomic(path, ledger, replace=replace)


def recover_interrupted_entries(
    ledger: Mapping[str, object], *, recovered_at: str, run_dir: Path | None = None
) -> dict[str, object]:
    recovered = copy.deepcopy(dict(ledger))
    for entry in recovered["entries"]:
        if entry["status"] == "in_progress":
            relative = observation_part_relative_path(entry["catalog_item_id"], entry["ordinal"])
            part_path = Path(run_dir) / relative if run_dir is not None else None
            if part_path is not None and part_path.is_file():
                part = load_observation_part(part_path)
                if part["catalog_item_id"] != entry["catalog_item_id"] or part["ordinal"] != entry["ordinal"]:
                    raise CheckpointIntegrityError(
                        f"Interrupted observation part identity mismatch for {entry['catalog_item_id']}"
                    )
                entry.update({
                    "status": part["outcome_status"],
                    "completed_at": part["created_at"],
                    "observation_part_path": str(relative),
                    "observation_row_count": len(part["rows"]),
                    "retry_eligible": False,
                    "safe_error_code": "",
                    "safe_error_message": "",
                    "updated_at": recovered_at,
                })
            else:
                entry.update({
                    "status": "pending",
                    "retry_eligible": True,
                    "safe_error_code": "interrupted",
                    "safe_error_message": "Previous attempt was interrupted before completion.",
                    "updated_at": recovered_at,
                })
    recovered["updated_at"] = recovered_at
    validate_ledger_shape(recovered)
    return recovered


def is_terminal_status(status: str) -> bool:
    validate_status(status)
    return status in TERMINAL_STATUSES


def should_skip_on_resume(entry: Mapping[str, object]) -> bool:
    return is_terminal_status(str(entry.get("status", "")))


def is_retry_eligible(entry: Mapping[str, object], *, max_retries: int) -> bool:
    status = str(entry.get("status", ""))
    validate_status(status)
    return (
        status in RETRYABLE_STATUSES
        and bool(entry.get("retry_eligible"))
        and int(entry.get("attempt_count", 0)) <= max_retries
    )


def can_transition(from_status: str, to_status: str) -> bool:
    validate_status(from_status)
    validate_status(to_status)
    return to_status in ALLOWED_TRANSITIONS[from_status]


def next_eligible_item(ledger: Mapping[str, object], *, max_retries: int) -> dict[str, object] | None:
    validate_ledger_shape(ledger)
    return next(
        (copy.deepcopy(entry) for entry in ledger["entries"] if is_retry_eligible(entry, max_retries=max_retries)),
        None,
    )


def mark_in_progress(
    ledger: Mapping[str, object], catalog_item_id: str, *, attempted_at: str, query: str, search_strategy: str
) -> dict[str, object]:
    return update_entry(
        ledger,
        catalog_item_id,
        "in_progress",
        attempted_at,
        attempt_count_delta=1,
        last_attempt_at=attempted_at,
        query=str(query or ""),
        search_strategy=str(search_strategy or ""),
        completed_at="",
        retry_eligible=False,
        retry_after="",
        safe_error_code="",
        safe_error_message="",
    )


def mark_completed(
    ledger: Mapping[str, object], catalog_item_id: str, *, status: str, completed_at: str,
    observation_part_path: str, observation_row_count: int
) -> dict[str, object]:
    if status not in PART_REQUIRED_STATUSES:
        raise CheckpointError(f"Completion status requires an observation part: {status!r}")
    return update_entry(
        ledger,
        catalog_item_id,
        status,
        completed_at,
        completed_at=completed_at,
        observation_part_path=required_text(observation_part_path, "observation_part_path"),
        observation_row_count=positive_int(observation_row_count, "observation_row_count"),
        retry_eligible=False,
        retry_after="",
        safe_error_code="",
        safe_error_message="",
    )


def mark_retryable_failure(
    ledger: Mapping[str, object], catalog_item_id: str, *, updated_at: str,
    safe_error_code: str, safe_error_message: str, retry_after: str = ""
) -> dict[str, object]:
    return update_entry(
        ledger,
        catalog_item_id,
        "source_unavailable_retryable",
        updated_at,
        retry_eligible=True,
        retry_after=str(retry_after or ""),
        safe_error_code=safe_code(safe_error_code),
        safe_error_message=sanitize_checkpoint_text(safe_error_message),
    )


def mark_terminal_failure(
    ledger: Mapping[str, object], catalog_item_id: str, *, completed_at: str,
    safe_error_code: str, safe_error_message: str
) -> dict[str, object]:
    return update_entry(
        ledger,
        catalog_item_id,
        "failed_terminal",
        completed_at,
        completed_at=completed_at,
        retry_eligible=False,
        safe_error_code=safe_code(safe_error_code),
        safe_error_message=sanitize_checkpoint_text(safe_error_message),
    )


def observation_part_relative_path(catalog_item_id: str, ordinal: int) -> Path:
    digest = hashlib.sha256(required_text(catalog_item_id, "catalog_item_id").encode("utf-8")).hexdigest()[:16]
    return Path("parts") / f"{nonnegative_int(ordinal, 'ordinal'):06d}-{digest}.json"


def write_observation_part_atomic(
    path: Path, *, catalog_item_id: str, ordinal: int, rows: Iterable[Mapping[str, str]],
    created_at: str, replace: bool = False
) -> dict[str, object]:
    normalized = [validate_observation_row(row) for row in rows]
    if not normalized:
        raise CheckpointError("Observation part must contain at least one row")
    envelope = {
        "schema_version": OBSERVATION_PART_SCHEMA_VERSION,
        "catalog_item_id": required_text(catalog_item_id, "catalog_item_id"),
        "ordinal": nonnegative_int(ordinal, "ordinal"),
        "created_at": required_text(created_at, "created_at"),
        "outcome_status": observation_part_outcome(normalized),
        "rows": normalized,
    }
    write_json_atomic(path, envelope, replace=replace)
    return envelope


def load_observation_part(path: Path) -> dict[str, object]:
    part = load_json(path)
    if part.get("schema_version") != OBSERVATION_PART_SCHEMA_VERSION:
        raise CheckpointError(f"Unsupported observation-part schema version: {part.get('schema_version')!r}")
    if not isinstance(part.get("rows"), list) or not part["rows"]:
        raise CheckpointError("Observation part rows must be a non-empty list")
    part["rows"] = [validate_observation_row(row) for row in part["rows"]]
    expected_outcome = observation_part_outcome(part["rows"])
    if part.get("outcome_status") != expected_outcome:
        raise CheckpointError("Observation-part outcome does not match its rows")
    return part


def validate_checkpoint_integrity(run_dir: Path) -> list[str]:
    paths = run_paths(run_dir)
    manifest = load_manifest(paths["manifest"])
    ledger = load_ledger(paths["ledger"])
    if manifest["candidate_count"] != len(ledger["entries"]):
        raise CheckpointIntegrityError("Manifest candidate count does not match ledger")
    if manifest["ordered_catalog_ids_hash"] != catalog_ids_hash(
        entry["catalog_item_id"] for entry in ledger["entries"]
    ):
        raise CheckpointIntegrityError("Manifest candidate ordering does not match ledger")
    checked = []
    referenced_parts = set()
    for entry in ledger["entries"]:
        relative = str(entry["observation_part_path"] or "")
        if entry["status"] in PART_REQUIRED_STATUSES:
            if not relative:
                raise CheckpointIntegrityError(f"Completed item {entry['catalog_item_id']} has no part path")
            part_path = safe_run_relative_path(paths["root"], relative)
            referenced_parts.add(part_path.resolve())
            if not part_path.is_file():
                raise CheckpointIntegrityError(f"Missing observation part for {entry['catalog_item_id']}")
            part = load_observation_part(part_path)
            if part["catalog_item_id"] != entry["catalog_item_id"] or part["ordinal"] != entry["ordinal"]:
                raise CheckpointIntegrityError(f"Observation part identity mismatch for {entry['catalog_item_id']}")
            if len(part["rows"]) != entry["observation_row_count"]:
                raise CheckpointIntegrityError(f"Observation row count mismatch for {entry['catalog_item_id']}")
            checked.append(entry["catalog_item_id"])
        elif relative:
            raise CheckpointIntegrityError(f"Non-completed item {entry['catalog_item_id']} references a part")
    actual_parts = {path.resolve() for path in paths["parts"].glob("*.json")} if paths["parts"].exists() else set()
    unexpected = actual_parts - referenced_parts
    if unexpected:
        raise CheckpointIntegrityError("Unreferenced observation part detected")
    return checked


def summarize_run_state(ledger: Mapping[str, object]) -> dict[str, object]:
    validate_ledger_shape(ledger)
    counts = Counter(entry["status"] for entry in ledger["entries"])
    return {
        "candidate_count": len(ledger["entries"]),
        "status_counts": {status: counts.get(status, 0) for status in sorted(STATUSES)},
        "terminal_count": sum(counts[status] for status in TERMINAL_STATUSES),
        "retry_eligible_count": sum(bool(entry["retry_eligible"]) for entry in ledger["entries"]),
        "observation_row_count": sum(int(entry["observation_row_count"]) for entry in ledger["entries"]),
    }


def update_entry(
    ledger: Mapping[str, object], catalog_item_id: str, new_status: str, updated_at: str,
    *, attempt_count_delta: int = 0, **updates: object
) -> dict[str, object]:
    validate_ledger_shape(ledger)
    updated = copy.deepcopy(dict(ledger))
    matches = [entry for entry in updated["entries"] if entry["catalog_item_id"] == catalog_item_id]
    if len(matches) != 1:
        raise CheckpointError(f"Unknown or duplicate catalog_item_id: {catalog_item_id!r}")
    entry = matches[0]
    if not can_transition(str(entry["status"]), new_status):
        raise CheckpointError(f"Invalid status transition: {entry['status']} -> {new_status}")
    entry.update(updates)
    entry["status"] = new_status
    entry["attempt_count"] = int(entry["attempt_count"]) + attempt_count_delta
    entry["updated_at"] = required_text(updated_at, "updated_at")
    updated["updated_at"] = updated_at
    validate_ledger_shape(updated)
    return updated


def validate_ledger_shape(ledger: Mapping[str, object]) -> None:
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise CheckpointError(f"Unsupported ledger schema version: {ledger.get('schema_version')!r}")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise CheckpointError("Ledger entries must be a list")
    ids = []
    for expected_ordinal, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise CheckpointError("Ledger entry must be an object")
        if set(entry) != LEDGER_ENTRY_FIELDS:
            raise CheckpointError("Ledger entry fields do not match the supported schema")
        ids.append(required_text(entry.get("catalog_item_id"), "catalog_item_id"))
        if entry.get("ordinal") != expected_ordinal:
            raise CheckpointError("Ledger ordinals must be contiguous and deterministic")
        validate_status(str(entry.get("status", "")))
        nonnegative_int(entry.get("attempt_count"), "attempt_count")
        nonnegative_int(entry.get("observation_row_count"), "observation_row_count")
    if len(ids) != len(set(ids)):
        raise CheckpointError("Ledger contains duplicate catalog_item_id values")


def validate_observation_row(row: Mapping[str, str]) -> dict[str, str]:
    if set(row) != set(MARKET_OBSERVATION_FIELDNAMES):
        raise CheckpointError("Observation row must contain exactly the canonical 25 fields")
    normalized = {field: str(row.get(field, "") or "") for field in MARKET_OBSERVATION_FIELDNAMES}
    if normalized["source"] != SOURCE_NAME:
        raise CheckpointError("Observation part source must be ebay_active_listings")
    if normalized["seller"]:
        raise CheckpointError("Seller identity must remain suppressed in eBay observations")
    return normalized


def observation_part_outcome(rows: list[Mapping[str, str]]) -> str:
    statuses = {row.get("lookup_status", "") for row in rows}
    if statuses == {"observed"}:
        return "observed"
    if statuses == {"no_results"}:
        return "no_results"
    if statuses == {"no_query"}:
        return "no_query"
    if statuses == {"source_unavailable"}:
        return "source_unavailable_terminal"
    raise CheckpointError("Observation part rows must have one supported outcome")


def write_json_atomic(path: Path, value: Mapping[str, object], *, replace: bool = True) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not replace:
        raise FileExistsError(destination)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if destination.exists() and not replace:
            raise FileExistsError(destination)
        os.replace(temp_path, destination)
        temp_path = None
        fsync_directory(destination.parent)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise CheckpointError(f"Unable to load checkpoint JSON: {Path(path).name}") from exc
    if not isinstance(value, dict):
        raise CheckpointError("Checkpoint JSON root must be an object")
    return value


def safe_run_relative_path(run_dir: Path, relative: str) -> Path:
    root = Path(run_dir).resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise CheckpointIntegrityError("Checkpoint path escapes the run directory")
    return candidate


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def validate_status(status: str) -> None:
    if status not in STATUSES:
        raise CheckpointError(f"Unknown ledger status: {status!r}")


def required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CheckpointError(f"{field} is required")
    return text


def safe_code(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in text):
        raise CheckpointError("safe_error_code must use lowercase letters, digits, underscore, or hyphen")
    return text[:100]


def sanitize_checkpoint_text(value: object) -> str:
    text = sanitize_failure_reason(str(value or ""))
    return re.sub(
        r"(?i)\b(access_token|refresh_token|client_secret|authorization)\b",
        "[REDACTED_FIELD]",
        text,
    )


def nonnegative_int(value: object, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CheckpointError(f"{field} must be an integer") from exc
    if number < 0:
        raise CheckpointError(f"{field} must be nonnegative")
    return number


def positive_int(value: object, field: str) -> int:
    number = nonnegative_int(value, field)
    if number == 0:
        raise CheckpointError(f"{field} must be positive")
    return number


def nonnegative_float(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CheckpointError(f"{field} must be numeric") from exc
    if number < 0:
        raise CheckpointError(f"{field} must be nonnegative")
    return number
