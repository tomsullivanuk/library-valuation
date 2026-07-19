"""Resumable orchestration for full-library eBay active-listing collection."""

from __future__ import annotations

import csv
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from valuation.ebay_access import EbayAccessClient, EbayAccessError, EbayCredentials
from valuation.ebay_active_listings import EbayActiveListingsClient
from valuation.ebay_full_library_state import (
    LEDGER_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    OBSERVATION_PART_SCHEMA_VERSION,
    CheckpointError,
    ManifestCompatibilityError,
    catalog_ids_hash,
    create_manifest,
    fingerprint_file,
    initialize_ledger,
    is_retry_eligible,
    load_ledger,
    load_manifest,
    mark_completed,
    mark_in_progress,
    mark_retryable_failure,
    mark_terminal_failure,
    next_eligible_item,
    observation_part_relative_path,
    recover_interrupted_entries,
    run_paths,
    save_ledger_atomic,
    summarize_run_state,
    validate_checkpoint_integrity,
    validate_manifest_compatibility,
    write_json_atomic,
    write_observation_part_atomic,
)
from valuation.ebay_observations import (
    adapt_ebay_search_result,
    ebay_source_unavailable_row,
    ebay_status_observation_row,
    sanitize_failure_reason,
)
from valuation.ebay_targeted_collection import build_ebay_query


QUERY_STRATEGY_VERSION = "isbn-first-v1"
COMMAND_VERSION = "0.9.0-pr3"
DEFAULT_OUTPUT_ROOT = Path("output")
MAX_RESULTS_PER_BOOK = 10
FailureKind = str


class FullLibraryCollectionError(ValueError):
    """Safe user-facing full-library collection failure."""


def collect_full_library_ebay(
    summary_path: Path,
    output_dir: Path,
    *,
    checkpoint_dir: Path | None = None,
    data_dir: Path = Path("data"),
    resume: bool = True,
    restart: bool = False,
    delay_seconds: float = 1.0,
    max_results_per_book: int = 3,
    max_retries: int = 2,
    retry_delay_seconds: float = 5.0,
    limit: int | None = None,
    confirm_production: bool = False,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    credentials: EbayCredentials | None = None,
    client: EbayActiveListingsClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    progress: Callable[[str], None] = print,
) -> dict[str, object]:
    """Collect checkpointed per-item parts; no final CSV/XLSX is materialized."""
    del data_dir  # Reserved for the later catalog-aware command evolution.
    validate_options(
        delay_seconds=delay_seconds,
        max_results_per_book=max_results_per_book,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
        limit=limit,
    )
    if not confirm_production:
        raise FullLibraryCollectionError("Full-library eBay collection requires --confirm-production")
    try:
        active_credentials = credentials or EbayCredentials.from_environment()
    except EbayAccessError as error:
        raise FullLibraryCollectionError(str(error)) from None
    if active_credentials.environment != "production":
        raise FullLibraryCollectionError("Full-library eBay collection requires EBAY_ENVIRONMENT=production")

    output_dir = ensure_ignored_output_path(output_dir, output_root, "output directory")
    run_dir = ensure_ignored_output_path(
        checkpoint_dir or output_dir, output_root, "checkpoint directory"
    )
    if output_dir == output_root.resolve() or run_dir == output_root.resolve():
        raise FullLibraryCollectionError("Use a dedicated directory below output for full-library eBay state")
    if restart and resume:
        # Resume is the safe default; explicit restart takes precedence.
        resume = False

    candidates = select_full_library_candidates(read_summary_rows(summary_path), limit=limit)
    if not candidates:
        raise FullLibraryCollectionError("Summary input contains no full-library candidates")
    timestamp = now or utc_timestamp
    started_at = timestamp()
    manifest_expected = manifest_parameters(
        summary_path,
        candidates,
        active_credentials,
        max_results_per_book=max_results_per_book,
        delay_seconds=delay_seconds,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
        run_id=f"ebay-full-{uuid.uuid4().hex}",
        created_at=started_at,
    )

    archived_checkpoint = ""
    if restart and run_dir.exists():
        archived_checkpoint = str(archive_run_directory(run_dir, started_at))
    paths = run_paths(run_dir)
    if paths["manifest"].exists() or paths["ledger"].exists():
        if not resume:
            raise FullLibraryCollectionError(
                "Checkpoint already exists; use --resume or explicit --restart"
            )
        try:
            manifest = load_manifest(paths["manifest"])
            validate_manifest_compatibility(manifest, {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                **manifest_expected,
                "observation_schema_version": "market_observation_25_v1",
                "source_name": "ebay_active_listings",
                "seller_identity_suppressed": True,
            })
            ledger = load_ledger(paths["ledger"])
            ledger = recover_interrupted_entries(ledger, recovered_at=started_at, run_dir=run_dir)
            save_ledger_atomic(paths["ledger"], ledger)
            validate_checkpoint_integrity(run_dir)
        except (CheckpointError, OSError) as error:
            raise FullLibraryCollectionError(f"Cannot resume checkpoint: {error}") from None
        resume_count = load_resume_count(paths["run_summary"]) + 1
    else:
        if run_dir.exists() and any(run_dir.iterdir()):
            raise FullLibraryCollectionError("Run directory is nonempty but has no compatible checkpoint")
        paths["parts"].mkdir(parents=True, exist_ok=True)
        paths["final"].mkdir(parents=True, exist_ok=True)
        manifest = create_manifest(paths["manifest"], **manifest_expected)
        ledger = initialize_ledger(
            paths["ledger"], [row["catalog_item_id"] for row in candidates], created_at=started_at
        )
        resume_count = 0

    candidates_by_id = {row["catalog_item_id"]: row for row in candidates}
    active_client = client or EbayActiveListingsClient(EbayAccessClient(active_credentials))
    start_clock = monotonic()
    request_made = False
    stop_reason = ""

    while (entry := next_eligible_item(ledger, max_retries=max_retries)) is not None:
        catalog_id = str(entry["catalog_item_id"])
        candidate = candidates_by_id[catalog_id]
        strategy, query = build_ebay_query(candidate)
        attempt_at = timestamp()
        ledger = mark_in_progress(
            ledger, catalog_id, attempted_at=attempt_at, query=query, search_strategy=strategy
        )
        save_ledger_atomic(paths["ledger"], ledger)
        current = entry_by_id(ledger, catalog_id)

        if not query:
            rows = [ebay_status_observation_row(
                candidate,
                observation_date=attempt_at,
                lookup_status="no_query",
                lookup_strategy=strategy,
                search_query="",
                diagnostic_code="no_query",
                match_notes="No safe eBay query could be constructed from catalog metadata.",
            )]
            ledger = persist_completed_item(
                paths, ledger, current, rows, status="no_query", completed_at=timestamp()
            )
            progress(progress_line(ledger, current, monotonic() - start_clock))
            continue

        if request_made and delay_seconds:
            sleep(delay_seconds)
        request_made = True
        try:
            result = active_client.search(query, max_results_per_book)
            rows = adapt_ebay_search_result(
                candidate, result, observation_date=attempt_at, lookup_strategy=strategy
            )
            status = "observed" if rows[0]["lookup_status"] == "observed" else "no_results"
            ledger = persist_completed_item(
                paths, ledger, current, rows, status=status, completed_at=timestamp()
            )
        except EbayAccessError as error:
            safe_message = sanitize_failure_reason(active_credentials.redact(error))
            kind, safe_code = classify_failure(safe_message)
            if kind == "retryable" and int(current["attempt_count"]) <= max_retries:
                ledger = mark_retryable_failure(
                    ledger,
                    catalog_id,
                    updated_at=timestamp(),
                    safe_error_code=safe_code,
                    safe_error_message=safe_message,
                )
                save_ledger_atomic(paths["ledger"], ledger)
                progress(progress_line(ledger, current, monotonic() - start_clock))
                if retry_delay_seconds:
                    sleep(retry_delay_seconds)
                continue
            if kind in {"retryable", "global_terminal"}:
                rows = [ebay_source_unavailable_row(
                    candidate,
                    observation_date=attempt_at,
                    lookup_strategy=strategy,
                    search_query=query,
                    safe_reason=safe_message,
                    diagnostic_code=safe_code,
                )]
                ledger = persist_completed_item(
                    paths,
                    ledger,
                    current,
                    rows,
                    status="source_unavailable_terminal",
                    completed_at=timestamp(),
                )
                if kind == "global_terminal":
                    stop_reason = safe_code
            else:
                ledger = mark_terminal_failure(
                    ledger,
                    catalog_id,
                    completed_at=timestamp(),
                    safe_error_code=safe_code,
                    safe_error_message=safe_message,
                )
                save_ledger_atomic(paths["ledger"], ledger)
            if stop_reason:
                progress(progress_line(ledger, current, monotonic() - start_clock))
                break
        except Exception as error:
            safe_message = sanitize_failure_reason(active_credentials.redact(error))
            ledger = mark_terminal_failure(
                ledger,
                catalog_id,
                completed_at=timestamp(),
                safe_error_code="unexpected_failure",
                safe_error_message=safe_message,
            )
            save_ledger_atomic(paths["ledger"], ledger)

        progress(progress_line(ledger, current, monotonic() - start_clock))

    summary = build_run_summary(
        ledger,
        started_at=started_at,
        updated_at=timestamp(),
        elapsed_seconds=max(0.0, monotonic() - start_clock),
        resume_count=resume_count,
        output_dir=output_dir,
        checkpoint_dir=run_dir,
        archived_checkpoint=archived_checkpoint,
        stop_reason=stop_reason,
    )
    write_json_atomic(paths["run_summary"], summary)
    return summary


def select_full_library_candidates(
    summary_rows: list[Mapping[str, str]], *, limit: int | None = None
) -> list[dict[str, str]]:
    candidates = []
    seen = set()
    for source in summary_rows:
        row = dict(source)
        catalog_id = str(row.get("catalog_item_id", "")).strip()
        if not catalog_id:
            raise FullLibraryCollectionError("Summary contains a blank catalog_item_id")
        if catalog_id in seen:
            raise FullLibraryCollectionError(f"Duplicate catalog_item_id in summary: {catalog_id}")
        seen.add(catalog_id)
        row["catalog_item_id"] = catalog_id
        candidates.append(row)
    candidates.sort(key=lambda row: row["catalog_item_id"])
    return candidates[:limit] if limit is not None else candidates


def manifest_parameters(
    summary_path: Path,
    candidates: list[Mapping[str, str]],
    credentials: EbayCredentials,
    *,
    max_results_per_book: int,
    delay_seconds: float,
    max_retries: int,
    retry_delay_seconds: float,
    run_id: str,
    created_at: str,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "created_at": created_at,
        "environment": credentials.environment,
        "marketplace_id": credentials.marketplace_id,
        "summary_input_path": str(Path(summary_path)),
        "summary_input_fingerprint": fingerprint_file(summary_path),
        "candidate_count": len(candidates),
        "ordered_catalog_ids_hash": catalog_ids_hash(row["catalog_item_id"] for row in candidates),
        "query_strategy_version": QUERY_STRATEGY_VERSION,
        "max_results_per_book": max_results_per_book,
        "delay_seconds": delay_seconds,
        "max_retries": max_retries,
        "retry_delay_seconds": retry_delay_seconds,
        "command_version": COMMAND_VERSION,
        "notes": "Full-library eBay active-listing checkpoint; seller identity suppressed.",
    }


def persist_completed_item(paths, ledger, entry, rows, *, status: str, completed_at: str):
    relative = observation_part_relative_path(entry["catalog_item_id"], entry["ordinal"])
    write_observation_part_atomic(
        paths["root"] / relative,
        catalog_item_id=entry["catalog_item_id"],
        ordinal=entry["ordinal"],
        rows=rows,
        created_at=completed_at,
    )
    updated = mark_completed(
        ledger,
        entry["catalog_item_id"],
        status=status,
        completed_at=completed_at,
        observation_part_path=str(relative),
        observation_row_count=len(rows),
    )
    save_ledger_atomic(paths["ledger"], updated)
    return updated


def classify_failure(message: str) -> tuple[FailureKind, str]:
    text = message.casefold()
    if any(value in text for value in (
        "invalid_client", "invalid client", "token request", "oauth", "credential",
        "http 401", "http 403", "unauthorized", "forbidden",
    )):
        return "global_terminal", "authentication_failure"
    if any(value in text for value in (
        "http 429", "rate limit", "too many requests", "timeout", "timed out",
        "temporarily", "temporary", "connection", "http 500", "http 502", "http 503", "http 504",
    )):
        return "retryable", "temporary_source_failure"
    return "terminal", "source_failure"


def build_run_summary(
    ledger,
    *,
    started_at: str,
    updated_at: str,
    elapsed_seconds: float,
    resume_count: int,
    output_dir: Path,
    checkpoint_dir: Path,
    archived_checkpoint: str,
    stop_reason: str,
) -> dict[str, object]:
    state = summarize_run_state(ledger)
    counts = state["status_counts"]
    return {
        "schema_version": "1.0",
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "observation_part_schema_version": OBSERVATION_PART_SCHEMA_VERSION,
        "total_candidates": state["candidate_count"],
        "completed": state["terminal_count"],
        "observed": counts["observed"],
        "no_results": counts["no_results"],
        "no_query": counts["no_query"],
        "retryable_failures": counts["source_unavailable_retryable"],
        "terminal_failures": counts["source_unavailable_terminal"] + counts["failed_terminal"],
        "attempts": sum(int(entry["attempt_count"]) for entry in ledger["entries"]),
        "observation_rows": state["observation_row_count"],
        "started_at": started_at,
        "updated_at": updated_at,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "resume_count": resume_count,
        "output_dir": str(output_dir),
        "checkpoint_dir": str(checkpoint_dir),
        "archived_checkpoint": archived_checkpoint,
        "stop_reason": stop_reason,
        "seller_identity_suppressed": True,
    }


def progress_line(ledger, entry, elapsed_seconds: float) -> str:
    state = summarize_run_state(ledger)
    counts = state["status_counts"]
    current = entry_by_id(ledger, entry["catalog_item_id"])
    return (
        f"Progress {state['terminal_count']}/{state['candidate_count']} "
        f"ordinal={int(current['ordinal']) + 1} status={current['status']} "
        f"observed={counts['observed']} no_results={counts['no_results']} "
        f"retryable={counts['source_unavailable_retryable']} "
        f"terminal_failures={counts['source_unavailable_terminal'] + counts['failed_terminal']} "
        f"elapsed={max(0.0, elapsed_seconds):.1f}s"
    )


def ensure_ignored_output_path(path: Path, output_root: Path, label: str) -> Path:
    root = Path(output_root).resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root):
        raise FullLibraryCollectionError(f"Full-library eBay {label} must be under {output_root}")
    return resolved


def archive_run_directory(run_dir: Path, timestamp: str) -> Path:
    suffix = re.sub(r"[^0-9A-Za-z]+", "", timestamp) or uuid.uuid4().hex
    archive = run_dir.with_name(f"{run_dir.name}.archive-{suffix}")
    if archive.exists():
        raise FullLibraryCollectionError(f"Restart archive already exists: {archive.name}")
    run_dir.rename(archive)
    return archive


def validate_options(
    *, delay_seconds: float, max_results_per_book: int, max_retries: int,
    retry_delay_seconds: float, limit: int | None
) -> None:
    if delay_seconds < 0 or retry_delay_seconds < 0:
        raise FullLibraryCollectionError("Delay values must be zero or greater")
    if max_results_per_book < 1 or max_results_per_book > MAX_RESULTS_PER_BOOK:
        raise FullLibraryCollectionError(
            f"max-results-per-book must be between 1 and {MAX_RESULTS_PER_BOOK}"
        )
    if max_retries < 0:
        raise FullLibraryCollectionError("max-retries must be zero or greater")
    if limit is not None and limit < 1:
        raise FullLibraryCollectionError("limit must be at least 1")


def read_summary_rows(path: Path) -> list[dict[str, str]]:
    try:
        with Path(path).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError as error:
        raise FullLibraryCollectionError(f"Unable to read summary input: {Path(path).name}") from error


def load_resume_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        import json
        return int(json.loads(path.read_text(encoding="utf-8")).get("resume_count", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def entry_by_id(ledger, catalog_item_id: str):
    return next(entry for entry in ledger["entries"] if entry["catalog_item_id"] == catalog_item_id)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
