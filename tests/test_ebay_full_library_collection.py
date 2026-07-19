import csv
import json
import itertools
from pathlib import Path

import pytest

from library_pipeline import build_parser, main
from valuation.ebay_access import EbayAccessClient, EbayAccessError, EbayCredentials, EbayRequestError
from valuation.ebay_active_listings import (
    EbayActiveListing, EbayActiveListingSearchResult, EbayActiveListingsClient, EbayBrowseSession,
)
from valuation.ebay_full_library_collection import (
    FullLibraryCollectionError,
    collect_full_library_ebay,
    select_full_library_candidates,
)
from valuation.ebay_full_library_state import load_ledger, load_manifest, run_paths


NOW_COUNTER = itertools.count()


def now():
    return f"2026-07-19T12:{next(NOW_COUNTER):04d}:00Z"


def credentials(environment="production"):
    return EbayCredentials("client-id", "client-secret", "EBAY_US", environment)


def summary_row(catalog_id, **values):
    row = {
        "catalog_item_id": catalog_id,
        "isbn_13": "9781234567890",
        "isbn_10": "123456789X",
        "title": f"Book {catalog_id}",
        "author": "A. Author",
    }
    row.update(values)
    return row


def listing_result(query="9781234567890"):
    listing = EbayActiveListing(
        item_id="item-1", title="Listed Book", price_value="42.00", price_currency="USD",
        item_web_url="https://example.test/item-1", condition="Good",
        buying_options=("FIXED_PRICE",), item_location_country="US",
        raw_source="ebay_active_listing", query=query, marketplace_id="EBAY_US",
    )
    return EbayActiveListingSearchResult(query, "EBAY_US", 1, (listing,))


def empty_result(query="9781234567890"):
    return EbayActiveListingSearchResult(query, "EBAY_US", 0, ())


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def search(self, query, limit):
        self.calls.append((query, limit))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


def write_summary(path, rows):
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(tmp_path, rows, responses, **options):
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, rows)
    messages = []
    result = collect_full_library_ebay(
        summary,
        output_root / "full_library_ebay",
        output_root=output_root,
        credentials=credentials(),
        client=FakeClient(responses),
        confirm_production=True,
        delay_seconds=0,
        retry_delay_seconds=0,
        now=options.pop("now", now),
        monotonic=lambda: 10.0,
        progress=messages.append,
        **options,
    )
    return result, output_root / "full_library_ebay", messages


def test_production_confirmation_environment_and_credential_guards(tmp_path, monkeypatch):
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1")])
    output = tmp_path / "output" / "run"
    with pytest.raises(FullLibraryCollectionError, match="confirm-production"):
        collect_full_library_ebay(summary, output, output_root=tmp_path / "output")
    with pytest.raises(FullLibraryCollectionError, match="requires EBAY_ENVIRONMENT=production"):
        collect_full_library_ebay(
            summary, output, output_root=tmp_path / "output", confirm_production=True,
            credentials=credentials("sandbox"), client=FakeClient([])
        )
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("EBAY_MARKETPLACE_ID", raising=False)
    monkeypatch.delenv("EBAY_ENVIRONMENT", raising=False)
    with pytest.raises(FullLibraryCollectionError, match="Missing required"):
        collect_full_library_ebay(
            summary, output, output_root=tmp_path / "output", confirm_production=True
        )


def test_output_and_checkpoint_paths_must_be_below_output_root(tmp_path):
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1")])
    with pytest.raises(FullLibraryCollectionError, match="output directory"):
        collect_full_library_ebay(
            summary, tmp_path / "unsafe", output_root=tmp_path / "output",
            confirm_production=True, credentials=credentials(), client=FakeClient([])
        )
    with pytest.raises(FullLibraryCollectionError, match="checkpoint directory"):
        collect_full_library_ebay(
            summary, tmp_path / "output" / "run", checkpoint_dir=tmp_path / "unsafe",
            output_root=tmp_path / "output", confirm_production=True,
            credentials=credentials(), client=FakeClient([])
        )


def test_candidates_are_deterministic_limited_and_duplicate_safe():
    rows = [summary_row("BK2"), summary_row("BK1")]
    assert [row["catalog_item_id"] for row in select_full_library_candidates(rows)] == ["BK1", "BK2"]
    assert [row["catalog_item_id"] for row in select_full_library_candidates(rows, limit=1)] == ["BK1"]
    with pytest.raises(FullLibraryCollectionError, match="Duplicate"):
        select_full_library_candidates([summary_row("BK1"), summary_row("BK1")])


def test_book_level_pacing_is_mockable(tmp_path):
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1"), summary_row("BK2")])
    sleeps = []
    collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=FakeClient([empty_result(), empty_result()]), confirm_production=True,
        delay_seconds=1.5, retry_delay_seconds=0, sleep=sleeps.append, now=now,
        monotonic=lambda: 1.0, progress=lambda _value: None,
    )
    assert sleeps == [1.5]


def test_new_run_initializes_manifest_ledger_parts_and_observed_flow(tmp_path):
    result, run_dir, messages = run(tmp_path, [summary_row("BK1")], [listing_result()])
    paths = run_paths(run_dir)
    manifest = load_manifest(paths["manifest"])
    ledger = load_ledger(paths["ledger"])
    assert manifest["environment"] == "production"
    assert manifest["candidate_count"] == 1
    assert ledger["entries"][0]["status"] == "observed"
    assert ledger["entries"][0]["attempt_count"] == 1
    assert paths["parts"].is_dir() and len(list(paths["parts"].glob("*.json"))) == 1
    assert paths["run_summary"].is_file()
    assert result["observed"] == 1 and result["observation_rows"] == 1
    assert messages and "status=observed" in messages[-1]


def test_zero_results_and_no_query_are_terminal_parts(tmp_path):
    rows = [summary_row("BK1"), summary_row("BK2", isbn_13="", isbn_10="", title="--", author="")]
    result, run_dir, _messages = run(tmp_path, rows, [empty_result()])
    ledger = load_ledger(run_paths(run_dir)["ledger"])
    assert [entry["status"] for entry in ledger["entries"]] == ["no_results", "no_query"]
    assert result["no_results"] == 1 and result["no_query"] == 1
    assert len(list(run_paths(run_dir)["parts"].glob("*.json"))) == 2


def test_retryable_failure_retries_with_persisted_attempt_count(tmp_path):
    sleeps = []
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1")])
    client = FakeClient([EbayAccessError("HTTP 429 too many requests"), listing_result()])
    result = collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=client, confirm_production=True, delay_seconds=0, retry_delay_seconds=2,
        max_retries=1, sleep=sleeps.append, now=now, monotonic=lambda: 1.0, progress=lambda _value: None
    )
    entry = load_ledger(run_paths(output_root / "run")["ledger"])["entries"][0]
    assert entry["status"] == "observed" and entry["attempt_count"] == 2
    assert sleeps == [2]
    assert result["attempts"] == 2


def test_exhausted_retry_remains_eligible_for_later_resume(tmp_path):
    result, run_dir, _messages = run(
        tmp_path, [summary_row("BK1")], [EbayAccessError("HTTP 503 temporary")], max_retries=0
    )
    entry = load_ledger(run_paths(run_dir)["ledger"])["entries"][0]
    assert entry["status"] == "source_unavailable_retryable"
    assert entry["attempt_count"] == 1
    assert result["retryable_failures"] == 1
    summary = tmp_path / "summary.csv"
    resumed = collect_full_library_ebay(
        summary, run_dir, output_root=tmp_path / "output", credentials=credentials(),
        client=FakeClient([empty_result()]), confirm_production=True, max_retries=0,
        delay_seconds=0, retry_delay_seconds=0, now=now, monotonic=lambda: 1.0,
        progress=lambda _value: None,
    )
    entry = load_ledger(run_paths(run_dir)["ledger"])["entries"][0]
    assert entry["status"] == "no_results" and entry["attempt_count"] == 2
    assert resumed["resume_count"] == 1


def test_global_auth_failure_terminalizes_current_item_and_stops(tmp_path):
    result, run_dir, _messages = run(
        tmp_path,
        [summary_row("BK1"), summary_row("BK2")],
        [EbayAccessError("token request failed: invalid_client")],
    )
    ledger = load_ledger(run_paths(run_dir)["ledger"])
    assert [entry["status"] for entry in ledger["entries"]] == [
        "source_unavailable_terminal", "pending"
    ]
    assert result["stop_reason"] == "authentication_failure"
    assert result["attempts"] == 1
    assert result["global_stop_count"] == 1


def test_unexpected_failure_is_sanitized_terminal_and_next_item_continues(tmp_path):
    result, run_dir, _messages = run(
        tmp_path,
        [summary_row("BK1"), summary_row("BK2")],
        [RuntimeError("Bearer private-token client_secret=private-secret"), empty_result()],
    )
    ledger = load_ledger(run_paths(run_dir)["ledger"])
    assert [entry["status"] for entry in ledger["entries"]] == ["failed_terminal", "no_results"]
    persisted = (run_paths(run_dir)["ledger"].read_text() + run_paths(run_dir)["run_summary"].read_text())
    assert "private-token" not in persisted and "private-secret" not in persisted
    assert result["terminal_failures"] == 1


def test_resume_skips_completed_and_retries_interrupted_retryable_item(tmp_path):
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1"), summary_row("BK2")])
    first_client = FakeClient([listing_result(), EbayAccessError("HTTP 429 rate limit")])

    def interrupt(_seconds):
        raise KeyboardInterrupt

    with pytest.raises(FullLibraryCollectionError, match="interrupted safely"):
        collect_full_library_ebay(
            summary, output_root / "run", output_root=output_root, credentials=credentials(),
            client=first_client, confirm_production=True, delay_seconds=0, retry_delay_seconds=1,
            max_retries=1, sleep=interrupt, now=now, monotonic=lambda: 1.0,
            progress=lambda _value: None,
        )
    interrupted_summary = json.loads(
        run_paths(output_root / "run")["run_summary"].read_text(encoding="utf-8")
    )
    assert interrupted_summary["stop_reason"] == "interrupted"
    second_client = FakeClient([empty_result()])
    result = collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=second_client, confirm_production=True, delay_seconds=0, retry_delay_seconds=0,
        max_retries=1, now=now, monotonic=lambda: 1.0, progress=lambda _value: None,
    )
    assert len(second_client.calls) == 1
    ledger = load_ledger(run_paths(output_root / "run")["ledger"])
    assert [entry["status"] for entry in ledger["entries"]] == ["observed", "no_results"]
    assert [entry["attempt_count"] for entry in ledger["entries"]] == [1, 2]
    assert result["resume_count"] == 1


def test_structured_rate_limit_honors_capped_retry_after_and_records_metrics(tmp_path):
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1")])
    sleeps = []
    error = EbayRequestError(
        "HTTP 429", operation="active-listing search", status_code=429,
        retry_after_seconds=120, failure_kind="http",
    )
    result = collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=FakeClient([error, empty_result()]), confirm_production=True,
        max_retries=1, retry_delay_seconds=2, max_retry_delay_seconds=30,
        delay_seconds=0, sleep=sleeps.append, now=now, monotonic=lambda: 1.0,
        progress=lambda _value: None,
    )
    assert sleeps == [30]
    assert result["retry_event_count"] == 1
    assert result["rate_limit_event_count"] == 1
    assert result["temporary_failure_count"] == 1


def test_real_browse_session_metrics_are_safe_aggregates(tmp_path):
    calls = []

    def request_json(request, _timeout):
        calls.append(request.method)
        if request.method == "POST":
            return {"access_token": "never-persist-this-token", "expires_in": 7200}
        return {"total": 0, "itemSummaries": []}

    access = EbayAccessClient(credentials(), request_json=request_json)
    session = EbayBrowseSession(access, monotonic=lambda: 1.0)
    client = EbayActiveListingsClient(access, session=session)
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1"), summary_row("BK2")])
    result = collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=client, confirm_production=True, delay_seconds=0, retry_delay_seconds=0,
        now=now, monotonic=lambda: 1.0, progress=lambda _value: None,
    )
    assert calls.count("POST") == 1
    assert result["token_acquisition_count"] == 1
    assert result["token_refresh_count"] == 0
    assert result["browse_request_count"] == 2
    persisted = "".join(path.read_text() for path in (output_root / "run").rglob("*.json"))
    assert "never-persist-this-token" not in persisted


def test_token_refresh_metrics_are_included_in_run_summary(tmp_path):
    token_calls = 0
    browse_calls = 0

    def request_json(request, _timeout):
        nonlocal token_calls, browse_calls
        if request.method == "POST":
            token_calls += 1
            return {"access_token": f"memory-token-{token_calls}", "expires_in": 7200}
        browse_calls += 1
        if browse_calls == 1:
            raise EbayRequestError("HTTP 401", status_code=401, failure_kind="http")
        return {"total": 0, "itemSummaries": []}

    access = EbayAccessClient(credentials(), request_json=request_json)
    session = EbayBrowseSession(access, monotonic=lambda: 1.0)
    client = EbayActiveListingsClient(access, session=session)
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1")])
    result = collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=client, confirm_production=True, delay_seconds=0, retry_delay_seconds=0,
        now=now, monotonic=lambda: 1.0, progress=lambda _value: None,
    )
    assert result["token_acquisition_count"] == 2
    assert result["token_refresh_count"] == 1
    assert result["browse_request_count"] == 2


@pytest.mark.parametrize("stage", ["after_part_write", "after_part_validation"])
def test_interruption_after_part_creation_adopts_part_without_duplicate_request(tmp_path, stage):
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1")])

    def interrupt(current_stage, _path):
        if current_stage == stage:
            raise KeyboardInterrupt

    with pytest.raises(FullLibraryCollectionError, match="interrupted safely"):
        collect_full_library_ebay(
            summary, output_root / "run", output_root=output_root, credentials=credentials(),
            client=FakeClient([listing_result()]), confirm_production=True, delay_seconds=0,
            retry_delay_seconds=0, now=now, monotonic=lambda: 1.0,
            progress=lambda _value: None, transition_hook=interrupt,
        )
    resumed_client = FakeClient([])
    result = collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=resumed_client, confirm_production=True, delay_seconds=0,
        retry_delay_seconds=0, now=now, monotonic=lambda: 1.0,
        progress=lambda _value: None,
    )
    assert resumed_client.calls == []
    assert result["observed"] == 1
    assert result["recovered_parts_count"] == 1
    assert len(list(run_paths(output_root / "run")["parts"].glob("*.json"))) == 1


def test_interruption_before_part_write_recovers_item_to_pending(tmp_path):
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1")])
    with pytest.raises(FullLibraryCollectionError, match="interrupted safely"):
        collect_full_library_ebay(
            summary, output_root / "run", output_root=output_root, credentials=credentials(),
            client=FakeClient([KeyboardInterrupt()]), confirm_production=True, delay_seconds=0,
            retry_delay_seconds=0, now=now, monotonic=lambda: 1.0,
            progress=lambda _value: None,
        )
    resumed_client = FakeClient([empty_result()])
    result = collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=resumed_client, confirm_production=True, delay_seconds=0,
        retry_delay_seconds=0, now=now, monotonic=lambda: 1.0,
        progress=lambda _value: None,
    )
    assert len(resumed_client.calls) == 1
    assert result["no_results"] == 1


def test_interruption_after_ledger_completion_does_not_duplicate_item(tmp_path):
    output_root = tmp_path / "output"
    summary = tmp_path / "summary.csv"
    write_summary(summary, [summary_row("BK1")])

    def interrupt(stage, _path):
        if stage == "after_ledger_completion":
            raise KeyboardInterrupt

    with pytest.raises(FullLibraryCollectionError, match="interrupted safely"):
        collect_full_library_ebay(
            summary, output_root / "run", output_root=output_root, credentials=credentials(),
            client=FakeClient([listing_result()]), confirm_production=True, delay_seconds=0,
            retry_delay_seconds=0, now=now, monotonic=lambda: 1.0,
            progress=lambda _value: None, transition_hook=interrupt,
        )
    resumed_client = FakeClient([])
    result = collect_full_library_ebay(
        summary, output_root / "run", output_root=output_root, credentials=credentials(),
        client=resumed_client, confirm_production=True, delay_seconds=0,
        retry_delay_seconds=0, now=now, monotonic=lambda: 1.0,
        progress=lambda _value: None,
    )
    assert resumed_client.calls == []
    assert result["observed"] == 1


def test_incompatible_resume_is_rejected(tmp_path):
    _result, run_dir, _messages = run(tmp_path, [summary_row("BK1")], [empty_result()])
    summary = tmp_path / "summary.csv"
    with pytest.raises(FullLibraryCollectionError, match="Cannot resume checkpoint"):
        collect_full_library_ebay(
            summary, run_dir, output_root=tmp_path / "output", credentials=credentials(),
            client=FakeClient([]), confirm_production=True, max_results_per_book=2,
            delay_seconds=0, retry_delay_seconds=0, now=now, progress=lambda _value: None
        )


def test_restart_archives_existing_checkpoint_without_deleting_it(tmp_path):
    _result, run_dir, _messages = run(tmp_path, [summary_row("BK1")], [empty_result()])
    summary = tmp_path / "summary.csv"
    result = collect_full_library_ebay(
        summary, run_dir, output_root=tmp_path / "output", credentials=credentials(),
        client=FakeClient([empty_result()]), confirm_production=True, restart=True,
        delay_seconds=0, retry_delay_seconds=0, now=now, monotonic=lambda: 1.0,
        progress=lambda _value: None
    )
    archive = Path(result["archived_checkpoint"])
    assert archive.is_dir() and (archive / "manifest.json").is_file()
    assert (run_dir / "manifest.json").is_file()


def test_cli_help_and_confirmation_error_are_safe(tmp_path, capsys):
    parser = build_parser()
    args = parser.parse_args([
        "collect-full-library-ebay-observations", "--summary", "summary.csv",
        "--output-dir", "output/run",
    ])
    assert args.resume is True and args.confirm_production is False
    assert args.max_retry_delay == 60.0
    assert main([
        "collect-full-library-ebay-observations", "--summary", str(tmp_path / "summary.csv"),
        "--output-dir", str(tmp_path / "output" / "run"),
    ]) == 1
    error = capsys.readouterr().err
    assert "--confirm-production" in error
    assert "client-secret" not in error
