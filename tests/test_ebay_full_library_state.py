import json
from pathlib import Path

import pytest

from valuation.abebooks import MARKET_OBSERVATION_FIELDNAMES
from valuation.ebay_full_library_state import (
    COMPATIBILITY_CRITICAL_MANIFEST_FIELDS,
    LEDGER_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    OBSERVATION_PART_SCHEMA_VERSION,
    CheckpointError,
    CheckpointIntegrityError,
    ManifestCompatibilityError,
    can_transition,
    catalog_ids_hash,
    create_manifest,
    initialize_ledger,
    is_retry_eligible,
    is_terminal_status,
    load_ledger,
    load_manifest,
    load_observation_part,
    materialize_observation_rows,
    mark_completed,
    mark_in_progress,
    mark_retryable_failure,
    mark_terminal_failure,
    next_eligible_item,
    observation_part_relative_path,
    recover_interrupted_entries,
    run_paths,
    save_ledger_atomic,
    should_skip_on_resume,
    summarize_run_state,
    validate_checkpoint_integrity,
    validate_manifest_compatibility,
    write_observation_part_atomic,
)


NOW = "2026-07-19T12:00:00Z"


def manifest_values(**overrides):
    values = {
        "run_id": "run-001",
        "created_at": NOW,
        "environment": "production",
        "marketplace_id": "EBAY_US",
        "summary_input_path": "output/full_summary.csv",
        "summary_input_fingerprint": "sha256:abc",
        "candidate_count": 2,
        "ordered_catalog_ids_hash": catalog_ids_hash(["BK1", "BK2"]),
        "query_strategy_version": "isbn-first-v1",
        "max_results_per_book": 3,
        "delay_seconds": 1,
        "max_retries": 2,
        "retry_delay_seconds": 5,
        "command_version": "0.9.0-pr2",
        "notes": "fixture",
    }
    values.update(overrides)
    return values


def observation(catalog_id="BK1", status="observed"):
    row = {field: "" for field in MARKET_OBSERVATION_FIELDNAMES}
    row.update({
        "observation_id": f"MOB-{catalog_id}",
        "catalog_id": catalog_id,
        "source": "ebay_active_listings",
        "lookup_status": status,
        "listing_url": f"https://example.test/{catalog_id}" if status == "observed" else "",
        "seller": "",
        "match_confidence": "unknown",
    })
    return row


def test_manifest_round_trip_is_stable_and_immutable(tmp_path):
    path = tmp_path / "run" / "manifest.json"
    created = create_manifest(path, **manifest_values())
    assert created == load_manifest(path)
    assert created["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert created["seller_identity_suppressed"] is True
    assert path.read_text(encoding="utf-8").endswith("\n")
    with pytest.raises(FileExistsError):
        create_manifest(path, **manifest_values())


def test_manifest_compatibility_accepts_operational_changes_but_rejects_critical_changes(tmp_path):
    path = tmp_path / "manifest.json"
    existing = create_manifest(path, **manifest_values())
    expected = dict(existing, delay_seconds=2, max_retries=4, retry_delay_seconds=10, notes="resume")
    validate_manifest_compatibility(existing, expected)
    assert "delay_seconds" not in COMPATIBILITY_CRITICAL_MANIFEST_FIELDS

    for field, value in (
        ("summary_input_fingerprint", "sha256:different"),
        ("environment", "sandbox"),
        ("marketplace_id", "EBAY_GB"),
        ("max_results_per_book", 2),
        ("schema_version", "2.0"),
        ("seller_identity_suppressed", False),
    ):
        with pytest.raises(ManifestCompatibilityError, match=field):
            validate_manifest_compatibility(existing, dict(existing, **{field: value}))


def test_unknown_manifest_schema_version_fails_safely(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version":"99"}', encoding="utf-8")
    with pytest.raises(CheckpointError, match="Unsupported manifest"):
        load_manifest(path)


def test_ledger_initialization_is_deterministic_idempotent_and_rejects_duplicates(tmp_path):
    path = tmp_path / "ledger.json"
    first = initialize_ledger(path, ["BK2", "BK1"], created_at=NOW)
    second = initialize_ledger(path, ["BK2", "BK1"], created_at="later")
    assert first == second
    assert [(entry["ordinal"], entry["catalog_item_id"]) for entry in first["entries"]] == [
        (0, "BK2"), (1, "BK1")
    ]
    with pytest.raises(ManifestCompatibilityError):
        initialize_ledger(path, ["BK1", "BK2"], created_at=NOW)
    with pytest.raises(CheckpointError, match="Duplicate"):
        initialize_ledger(tmp_path / "duplicate.json", ["BK1", "BK1"], created_at=NOW)


def test_atomic_ledger_save_load_and_unknown_schema_rejection(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = initialize_ledger(path, ["BK1"], created_at=NOW)
    updated = mark_in_progress(
        ledger, "BK1", attempted_at="2026-07-19T12:01:00Z", query="9781", search_strategy="isbn13"
    )
    save_ledger_atomic(path, updated)
    assert load_ledger(path) == updated
    broken = dict(updated, schema_version="2.0")
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(CheckpointError, match="Unsupported ledger"):
        load_ledger(path)


def test_interrupted_in_progress_recovers_to_pending_without_losing_attempt_metadata(tmp_path):
    ledger = initialize_ledger(tmp_path / "ledger.json", ["BK1"], created_at=NOW)
    active = mark_in_progress(
        ledger, "BK1", attempted_at="attempted", query="9781", search_strategy="isbn13"
    )
    recovered = recover_interrupted_entries(active, recovered_at="recovered")
    entry = recovered["entries"][0]
    assert entry["status"] == "pending"
    assert entry["attempt_count"] == 1
    assert entry["query"] == "9781"
    assert entry["safe_error_code"] == "interrupted"
    assert is_retry_eligible(entry, max_retries=2)


def test_interrupted_entry_adopts_completed_atomic_part(tmp_path):
    run_dir = tmp_path / "run"
    ledger = initialize_ledger(run_dir / "ledger.json", ["BK1"], created_at=NOW)
    active = mark_in_progress(
        ledger, "BK1", attempted_at="attempted", query="9781", search_strategy="isbn13"
    )
    relative = observation_part_relative_path("BK1", 0)
    write_observation_part_atomic(
        run_dir / relative, catalog_item_id="BK1", ordinal=0,
        rows=[observation()], created_at="completed"
    )
    recovered = recover_interrupted_entries(active, recovered_at="recovered", run_dir=run_dir)
    entry = recovered["entries"][0]
    assert entry["status"] == "observed"
    assert entry["completed_at"] == "completed"
    assert entry["observation_part_path"] == str(relative)
    assert entry["observation_row_count"] == 1
    assert should_skip_on_resume(entry)


def test_interrupted_entry_does_not_adopt_invalid_part(tmp_path):
    run_dir = tmp_path / "run"
    ledger = initialize_ledger(run_dir / "ledger.json", ["BK1"], created_at=NOW)
    active = mark_in_progress(
        ledger, "BK1", attempted_at="attempted", query="9781", search_strategy="isbn13"
    )
    part_path = run_dir / observation_part_relative_path("BK1", 0)
    part_path.parent.mkdir(parents=True)
    part_path.write_text('{"schema_version":"broken"}', encoding="utf-8")
    with pytest.raises(CheckpointError, match="Unsupported observation-part"):
        recover_interrupted_entries(active, recovered_at="recovered", run_dir=run_dir)


def test_materialization_is_deterministic_network_free_and_includes_status_rows(
    tmp_path, monkeypatch
):
    run_dir = completed_run(
        tmp_path,
        [("BK2", [observation("BK2", "no_results")]), ("BK1", [observation("BK1")])],
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: pytest.fail("materialization must not use the network"),
    )
    first = materialize_observation_rows(run_dir)
    second = materialize_observation_rows(run_dir)
    assert first == second
    assert [(row["catalog_id"], row["lookup_status"]) for row in first] == [
        ("BK2", "no_results"), ("BK1", "observed")
    ]
    assert all(row["seller"] == "" for row in first)


def test_materialization_rejects_missing_malformed_and_incomplete_parts(tmp_path):
    run_dir = completed_run(tmp_path, [("BK1", [observation("BK1")])])
    part_path = next((run_dir / "parts").glob("*.json"))
    part_path.unlink()
    with pytest.raises(CheckpointIntegrityError, match="Missing observation part"):
        materialize_observation_rows(run_dir)

    run_dir = completed_run(tmp_path / "malformed", [("BK1", [observation("BK1")])])
    next((run_dir / "parts").glob("*.json")).write_text("not json", encoding="utf-8")
    with pytest.raises(CheckpointError, match="Unable to load checkpoint JSON"):
        materialize_observation_rows(run_dir)

    run_dir = tmp_path / "incomplete"
    create_manifest(run_dir / "manifest.json", **manifest_values(candidate_count=1, ordered_catalog_ids_hash=catalog_ids_hash(["BK1"])))
    initialize_ledger(run_dir / "ledger.json", ["BK1"], created_at=NOW)
    with pytest.raises(CheckpointIntegrityError, match="fully materializable"):
        materialize_observation_rows(run_dir)


def test_materialization_rejects_duplicate_observations_and_listing_urls(tmp_path):
    duplicate_id = observation("BK2")
    duplicate_id["observation_id"] = "MOB-BK1"
    run_dir = completed_run(
        tmp_path / "ids", [("BK1", [observation("BK1")]), ("BK2", [duplicate_id])]
    )
    with pytest.raises(CheckpointIntegrityError, match="observation ID"):
        materialize_observation_rows(run_dir)

    first = observation("BK1")
    second = observation("BK2")
    first["listing_url"] = second["listing_url"] = "https://example.test/shared"
    run_dir = completed_run(tmp_path / "urls", [("BK1", [first]), ("BK2", [second])])
    with pytest.raises(CheckpointIntegrityError, match="listing URL"):
        materialize_observation_rows(run_dir)


def completed_run(tmp_path, item_rows):
    run_dir = tmp_path / "run"
    catalog_ids = [catalog_id for catalog_id, _rows in item_rows]
    create_manifest(
        run_dir / "manifest.json",
        **manifest_values(
            candidate_count=len(catalog_ids),
            ordered_catalog_ids_hash=catalog_ids_hash(catalog_ids),
        ),
    )
    ledger = initialize_ledger(run_dir / "ledger.json", catalog_ids, created_at=NOW)
    for ordinal, (catalog_id, rows) in enumerate(item_rows):
        ledger = mark_in_progress(
            ledger, catalog_id, attempted_at="attempt", query="query", search_strategy="isbn13"
        )
        relative = observation_part_relative_path(catalog_id, ordinal)
        write_observation_part_atomic(
            run_dir / relative,
            catalog_item_id=catalog_id,
            ordinal=ordinal,
            rows=rows,
            created_at="completed",
        )
        ledger = mark_completed(
            ledger,
            catalog_id,
            status=rows[0]["lookup_status"],
            completed_at="completed",
            observation_part_path=str(relative),
            observation_row_count=len(rows),
        )
    save_ledger_atomic(run_dir / "ledger.json", ledger)
    return run_dir


@pytest.mark.parametrize("status", ["observed", "no_results", "no_query", "source_unavailable_terminal", "failed_terminal"])
def test_terminal_statuses_are_skipped(status):
    assert is_terminal_status(status)
    assert should_skip_on_resume({"status": status})


def test_retryable_failure_is_eligible_and_terminal_failure_is_skipped(tmp_path):
    ledger = initialize_ledger(tmp_path / "ledger.json", ["BK1", "BK2"], created_at=NOW)
    for item in ("BK1", "BK2"):
        ledger = mark_in_progress(ledger, item, attempted_at="attempt", query="q", search_strategy="title")
    ledger = mark_retryable_failure(
        ledger, "BK1", updated_at="failed", safe_error_code="http_429",
        safe_error_message="Bearer secret client_secret=hidden", retry_after="later"
    )
    ledger = mark_terminal_failure(
        ledger, "BK2", completed_at="failed", safe_error_code="invalid_request",
        safe_error_message="not retryable"
    )
    retryable, terminal = ledger["entries"]
    assert is_retry_eligible(retryable, max_retries=2)
    assert next_eligible_item(ledger, max_retries=2)["catalog_item_id"] == "BK1"
    assert "Bearer secret" not in retryable["safe_error_message"]
    assert "hidden" not in retryable["safe_error_message"]
    assert not is_retry_eligible(terminal, max_retries=2)
    assert should_skip_on_resume(terminal)


def test_valid_and_invalid_status_transitions_are_enforced(tmp_path):
    assert can_transition("pending", "in_progress")
    assert can_transition("in_progress", "observed")
    assert can_transition("source_unavailable_retryable", "in_progress")
    assert not can_transition("observed", "in_progress")
    ledger = initialize_ledger(tmp_path / "ledger.json", ["BK1"], created_at=NOW)
    with pytest.raises(CheckpointError, match="Invalid status transition"):
        mark_completed(
            ledger, "BK1", status="observed", completed_at=NOW,
            observation_part_path="parts/a.json", observation_row_count=1
        )


def test_observation_part_round_trip_path_and_duplicate_protection(tmp_path):
    relative = observation_part_relative_path("BK/unsafe", 3)
    assert relative.parent == Path("parts")
    assert "/unsafe" not in str(relative)
    path = tmp_path / relative
    created = write_observation_part_atomic(
        path, catalog_item_id="BK/unsafe", ordinal=3, rows=[observation("BK/unsafe")], created_at=NOW
    )
    assert load_observation_part(path) == created
    assert created["schema_version"] == OBSERVATION_PART_SCHEMA_VERSION
    with pytest.raises(FileExistsError):
        write_observation_part_atomic(
            path, catalog_item_id="BK/unsafe", ordinal=3, rows=[observation("BK/unsafe")], created_at=NOW
        )


def test_observation_parts_enforce_schema_source_and_seller_suppression(tmp_path):
    path = tmp_path / "part.json"
    bad_seller = observation()
    bad_seller["seller"] = "private-account"
    with pytest.raises(CheckpointError, match="Seller identity"):
        write_observation_part_atomic(path, catalog_item_id="BK1", ordinal=0, rows=[bad_seller], created_at=NOW)
    bad_source = observation()
    bad_source["source"] = "other"
    with pytest.raises(CheckpointError, match="source"):
        write_observation_part_atomic(path, catalog_item_id="BK1", ordinal=0, rows=[bad_source], created_at=NOW)
    missing = observation()
    missing.pop("seller")
    with pytest.raises(CheckpointError, match="25 fields"):
        write_observation_part_atomic(path, catalog_item_id="BK1", ordinal=0, rows=[missing], created_at=NOW)


def test_checkpoint_integrity_accepts_valid_parts_and_detects_missing_part(tmp_path):
    paths = run_paths(tmp_path / "output" / "full_library_ebay")
    create_manifest(paths["manifest"], **manifest_values(candidate_count=1, ordered_catalog_ids_hash=catalog_ids_hash(["BK1"])))
    ledger = initialize_ledger(paths["ledger"], ["BK1"], created_at=NOW)
    ledger = mark_in_progress(ledger, "BK1", attempted_at="attempt", query="q", search_strategy="title")
    relative = observation_part_relative_path("BK1", 0)
    write_observation_part_atomic(
        paths["root"] / relative, catalog_item_id="BK1", ordinal=0,
        rows=[observation()], created_at=NOW
    )
    ledger = mark_completed(
        ledger, "BK1", status="observed", completed_at="done",
        observation_part_path=str(relative), observation_row_count=1
    )
    save_ledger_atomic(paths["ledger"], ledger)
    assert validate_checkpoint_integrity(paths["root"]) == ["BK1"]
    (paths["root"] / relative).unlink()
    with pytest.raises(CheckpointIntegrityError, match="Missing observation part"):
        validate_checkpoint_integrity(paths["root"])


def test_summary_counts_are_deterministic(tmp_path):
    ledger = initialize_ledger(tmp_path / "ledger.json", ["BK1", "BK2"], created_at=NOW)
    ledger = mark_in_progress(ledger, "BK1", attempted_at="attempt", query="q", search_strategy="title")
    ledger = mark_completed(
        ledger, "BK1", status="no_results", completed_at="done",
        observation_part_path="parts/one.json", observation_row_count=1
    )
    summary = summarize_run_state(ledger)
    assert summary["candidate_count"] == 2
    assert summary["status_counts"]["no_results"] == 1
    assert summary["status_counts"]["pending"] == 1
    assert summary["terminal_count"] == 1
    assert summary["retry_eligible_count"] == 1
    assert summary["observation_row_count"] == 1


def test_persisted_state_has_no_credential_token_or_header_fields(tmp_path):
    paths = run_paths(tmp_path / "output" / "full_library_ebay")
    create_manifest(
        paths["manifest"],
        **manifest_values(notes="Bearer private-token client_secret=private-secret"),
    )
    initialize_ledger(paths["ledger"], ["BK1", "BK2"], created_at=NOW)
    persisted = (paths["manifest"].read_text() + paths["ledger"].read_text()).lower()
    for forbidden in ("access_token", "refresh_token", "authorization", "client_secret", "raw_response"):
        assert forbidden not in persisted
    assert "private-token" not in persisted
    assert "private-secret" not in persisted
    assert paths["root"].is_relative_to(tmp_path / "output")


def test_unknown_observation_part_schema_version_is_rejected(tmp_path):
    path = tmp_path / "part.json"
    path.write_text('{"schema_version":"99","rows":[{}]}', encoding="utf-8")
    with pytest.raises(CheckpointError, match="Unsupported observation-part"):
        load_observation_part(path)


def test_schema_versions_are_explicit():
    assert MANIFEST_SCHEMA_VERSION == "1.0"
    assert LEDGER_SCHEMA_VERSION == "1.0"
    assert OBSERVATION_PART_SCHEMA_VERSION == "1.0"
