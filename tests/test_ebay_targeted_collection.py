import csv
from pathlib import Path

import pytest

from library_pipeline import build_parser, collect_targeted_ebay_observations
from valuation.abebooks import MARKET_OBSERVATION_FIELDNAMES
from valuation.ebay_access import EbayAccessError
from valuation.ebay_active_listings import EbayActiveListing, EbayActiveListingSearchResult
from valuation.ebay_targeted_collection import (
    build_ebay_query,
    collect_targeted_ebay_observation_rows,
    select_targeted_candidates,
)


def summary_row(catalog_id: str, recommendation: str = "review_for_possible_sale", **values):
    row = {
        "catalog_item_id": catalog_id,
        "isbn_13": "9781234567890",
        "isbn_10": "123456789X",
        "title": f"Book {catalog_id}",
        "author": "A. Author",
        "review_recommendation": recommendation,
        "likely_mid": "50",
        "likely_high": "75",
        "research_score": "40",
        "research_band": "medium",
    }
    row.update(values)
    return row


def search_result(query: str, listings=()):
    return EbayActiveListingSearchResult(
        query=query,
        marketplace_id="EBAY_US",
        total=len(listings),
        listings=tuple(listings),
    )


def listing(query: str):
    return EbayActiveListing(
        item_id="v1|123|0",
        title="Listed Book",
        price_value="42.00",
        price_currency="EUR",
        item_web_url="https://example.test/item/123",
        condition="Good",
        buying_options=("FIXED_PRICE",),
        item_location_country="DE",
        raw_source="ebay_active_listing",
        query=query,
        marketplace_id="EBAY_US",
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def search(self, query, limit):
        self.calls.append((query, limit))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_cli_requires_summary_output_and_bounded_limit():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["collect-targeted-ebay-observations", "--summary", "input.csv", "--output", "output/x.csv"])
    args = parser.parse_args(
        [
            "collect-targeted-ebay-observations",
            "--summary",
            "input.csv",
            "--output",
            "output/x.csv",
            "--limit-books",
            "5",
        ]
    )
    assert args.limit_books == 5
    assert args.max_results_per_book == 3


def test_candidate_filtering_and_deterministic_reviewer_priority_order():
    rows = [
        summary_row("low", likely_mid="10"),
        summary_row("other", "no_action_needed", likely_mid="999"),
        summary_row("high", likely_mid="100"),
        summary_row("manual", "manual_market_research_needed", likely_mid="200"),
    ]
    selected = select_targeted_candidates(
        rows,
        review_recommendations=("manual_market_research_needed", "review_for_possible_sale"),
        limit_books=3,
    )
    assert [row["catalog_item_id"] for row in selected] == ["high", "low", "manual"]


def test_candidate_limit_allows_representative_cohort_but_remains_bounded():
    rows = [summary_row(f"book-{index:03d}") for index in range(100)]
    assert len(select_targeted_candidates(rows, limit_books=100)) == 100
    with pytest.raises(ValueError, match="between 1 and 100"):
        select_targeted_candidates(rows, limit_books=101)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"isbn_13": "978-1-234-56789-0"}, ("isbn13", "9781234567890")),
        ({"isbn_13": "", "isbn_10": "1-234567-89-X"}, ("isbn10", "123456789X")),
        ({"isbn_13": "", "isbn_10": "", "title": "Useful Title", "author": "Jane Doe"}, ("title_author", "Useful Title Jane Doe")),
        ({"isbn_13": "", "isbn_10": "", "title": "Useful Title", "author": ""}, ("title", "Useful Title")),
        ({"isbn_13": "", "isbn_10": "", "title": "--", "author": ""}, ("title", "")),
    ],
)
def test_query_strategy_order(values, expected):
    assert build_ebay_query(values) == expected


def test_collection_maps_observed_and_zero_result_rows_and_passes_limit():
    candidates = [summary_row("observed", likely_mid="100"), summary_row("empty", likely_mid="50")]
    first_query = "9781234567890"
    client = FakeClient([search_result(first_query, (listing(first_query),)), search_result(first_query)])
    sleeps = []
    rows = collect_targeted_ebay_observation_rows(
        candidates,
        client,
        observation_date="2026-07-18T00:00:00Z",
        limit_books=2,
        max_results_per_book=2,
        delay_seconds=0.25,
        sleep=sleeps.append,
    )
    assert [row["lookup_status"] for row in rows] == ["observed", "no_results"]
    assert client.calls == [(first_query, 2), (first_query, 2)]
    assert sleeps == [0.25]
    assert rows[0]["asking_price"] == "42.00"
    assert rows[0]["currency"] == "EUR"
    assert rows[0]["seller"] == ""
    assert list(rows[0]) == MARKET_OBSERVATION_FIELDNAMES


def test_no_query_does_not_call_client():
    client = FakeClient([])
    row = summary_row("no-query", isbn_13="", isbn_10="", title="--", author="")
    rows = collect_targeted_ebay_observation_rows(
        [row], client, observation_date="2026-07-18", limit_books=1, delay_seconds=0
    )
    assert rows[0]["lookup_status"] == "no_query"
    assert client.calls == []


def test_safe_client_failure_emits_sanitized_status_and_stops():
    client = FakeClient([EbayAccessError("Bearer private-token client_secret=private-secret")])
    rows = collect_targeted_ebay_observation_rows(
        [summary_row("one"), summary_row("two")],
        client,
        observation_date="2026-07-18",
        limit_books=2,
        delay_seconds=0,
    )
    assert len(rows) == 1
    assert rows[0]["lookup_status"] == "source_unavailable"
    assert "private-token" not in rows[0]["match_notes"]
    assert "private-secret" not in rows[0]["match_notes"]
    assert client.calls == [("9781234567890", 3)]


def test_writer_outputs_existing_schema_csv_and_xlsx_under_output(tmp_path):
    output_root = tmp_path / "output"
    summary_path = tmp_path / "summary.csv"
    write_summary(summary_path, [summary_row("one")])
    query = "9781234567890"
    client = FakeClient([search_result(query, (listing(query),))])
    output_path = output_root / "targeted_ebay_observations.csv"
    count = collect_targeted_ebay_observations(
        summary_path,
        output_path,
        limit_books=1,
        delay=0,
        client=client,
        observation_date="2026-07-18",
        output_root=output_root,
    )
    assert count == 1
    with output_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MARKET_OBSERVATION_FIELDNAMES
        written = list(reader)
    assert written[0]["raw_reference"] == "v1|123|0"
    assert "FIXED_PRICE" in written[0]["match_notes"]
    assert (output_root / "targeted_ebay_observations.xlsx").exists()
    assert "private-token" not in output_path.read_text(encoding="utf-8")


def test_writer_refuses_output_outside_generated_boundary(tmp_path):
    summary_path = tmp_path / "summary.csv"
    write_summary(summary_path, [summary_row("one")])
    with pytest.raises(ValueError, match="must be under"):
        collect_targeted_ebay_observations(
            summary_path,
            tmp_path / "not-output" / "rows.csv",
            limit_books=1,
            client=FakeClient([]),
            output_root=tmp_path / "output",
        )


def write_summary(path: Path, rows):
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
