import csv

from library_pipeline import build_parser, summarize_market_evidence
from valuation.market_evidence_summary import (
    MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
    aggregate_market_evidence,
)


def observed(source="abebooks", **overrides):
    row = {
        "observation_id": "OBS1",
        "catalog_id": "BK1",
        "isbn13": "9780000000001",
        "isbn10": "0000000001",
        "title": "Example Book",
        "author": "Example Author",
        "research_score": "30",
        "score_band": "high",
        "source": source,
        "lookup_status": "observed",
        "lookup_strategy": "isbn13",
        "asking_price": "20.00",
        "currency": "USD",
        "match_confidence": "high" if source == "abebooks" else "unknown",
    }
    row.update(overrides)
    return row


def status(source, lookup_status="no_results", **overrides):
    return observed(
        source,
        lookup_status=lookup_status,
        asking_price="",
        currency="",
        match_confidence="unknown",
        **overrides,
    )


def summarize(rows):
    return aggregate_market_evidence(rows, generated_at="2026-07-18T00:00:00Z")[0]


def test_abebooks_only_core_behavior_and_source_projection():
    rows = [
        observed(observation_id=f"A{index}", asking_price=str(price))
        for index, price in enumerate((10, 20, 30), start=1)
    ]
    summary = summarize(rows)
    assert summary["listing_count"] == "3"
    assert summary["median_asking_price"] == "20.00"
    assert summary["market_confidence"] == "moderate_confidence_market_evidence"
    assert summary["review_recommendation"] == "market_evidence_sufficient"
    assert summary["evidence_source_mix"] == "abebooks_only"
    assert summary["market_range_source"] == "abebooks"
    assert summary["abebooks_listing_count"] == "3"
    assert summary["ebay_active_listing_count"] == "0"


def test_ebay_only_observed_rows_have_separate_counts_and_prices():
    rows = [
        observed("ebay_active_listings", observation_id="E1", asking_price="15.00", currency="EUR"),
        observed("ebay_active_listings", observation_id="E2", asking_price="25.00", currency="EUR"),
    ]
    summary = summarize(rows)
    assert summary["source_count"] == "1"
    assert summary["observed_source_names"] == "ebay_active_listings"
    assert summary["evidence_source_mix"] == "ebay_active_listings_only"
    assert summary["market_range_source"] == "ebay_active_listings"
    assert summary["ebay_active_listing_count"] == "2"
    assert summary["ebay_status_count"] == "0"
    assert summary["ebay_active_currency"] == "EUR"
    assert summary["ebay_active_min_asking_price"] == "15.00"
    assert summary["ebay_active_median_asking_price"] == "20.00"
    assert summary["ebay_active_max_asking_price"] == "25.00"
    assert summary["market_confidence"] == "ambiguous_edition_match"


def test_mixed_sources_keep_abebooks_range_confidence_and_recommendation():
    abebooks = [
        observed(observation_id=f"A{index}", asking_price=str(price))
        for index, price in enumerate((50, 60, 70), start=1)
    ]
    baseline = summarize(abebooks)
    mixed = summarize(
        abebooks
        + [
            observed(
                "ebay_active_listings",
                observation_id="E1",
                asking_price="500.00",
                currency="USD",
            )
        ]
    )
    for field in (
        "listing_count",
        "currency",
        "min_asking_price",
        "median_asking_price",
        "max_asking_price",
        "market_confidence",
        "likely_low",
        "likely_mid",
        "likely_high",
        "review_recommendation",
        "review_reason",
    ):
        assert mixed[field] == baseline[field]
    assert mixed["source_count"] == "2"
    assert mixed["observed_source_names"] == "abebooks | ebay_active_listings"
    assert mixed["evidence_source_mix"] == "abebooks_and_ebay_active_listings"
    assert mixed["abebooks_listing_count"] == "3"
    assert mixed["ebay_active_listing_count"] == "1"


def test_ebay_no_results_does_not_erase_abebooks_observed_evidence():
    abebooks = [
        observed(observation_id=f"A{index}", asking_price=str(price))
        for index, price in enumerate((10, 20, 30), start=1)
    ]
    baseline = summarize(abebooks)
    mixed = summarize(abebooks + [status("ebay_active_listings", observation_id="ES")])
    assert mixed["evidence_status"] == baseline["evidence_status"] == "observed_listings"
    assert mixed["market_confidence"] == baseline["market_confidence"]
    assert mixed["review_recommendation"] == baseline["review_recommendation"]
    assert mixed["ebay_active_listing_count"] == "0"
    assert mixed["ebay_status_count"] == "1"


def test_ebay_no_results_alone_is_source_specific_market_absence():
    summary = summarize([status("ebay_active_listings")])
    assert summary["evidence_status"] == "no_market_evidence"
    assert summary["market_confidence"] == "no_market_evidence"
    assert summary["evidence_source_mix"] == "ebay_active_listings_only"
    assert summary["ebay_status_count"] == "1"
    assert summary["abebooks_status_count"] == "0"


def test_cross_source_currency_mismatch_is_not_combined():
    summary = summarize(
        [
            observed(asking_price="20.00", currency="USD"),
            observed("ebay_active_listings", observation_id="E1", asking_price="30.00", currency="GBP"),
        ]
    )
    assert summary["source_price_comparability"] == "cross_source_currency_mismatch"
    assert summary["abebooks_currency"] == "USD"
    assert summary["ebay_active_currency"] == "GBP"
    assert summary["median_asking_price"] == "20.00"
    assert summary["currency"] == "USD"


def test_mixed_currency_within_ebay_leaves_ebay_price_summary_blank():
    summary = summarize(
        [
            observed("ebay_active_listings", observation_id="E1", asking_price="10", currency="USD"),
            observed("ebay_active_listings", observation_id="E2", asking_price="20", currency="EUR"),
        ]
    )
    assert summary["source_price_comparability"] == "mixed_currency_within_source"
    assert summary["ebay_active_currency"] == "mixed"
    assert summary["ebay_active_min_asking_price"] == ""
    assert summary["ebay_active_median_asking_price"] == ""
    assert summary["ebay_active_max_asking_price"] == ""
    assert summary["market_confidence"] == "mixed_currency_evidence"


def test_sources_are_deterministic_and_cli_accepts_repeated_inputs():
    parser = build_parser()
    args = parser.parse_args(
        [
            "summarize-market-evidence",
            "--observations",
            "a.csv",
            "--observations",
            "b.csv",
        ]
    )
    assert [str(path) for path in args.observations] == ["a.csv", "b.csv"]
    summary = summarize(
        [status("ebay_active_listings"), status("abebooks", observation_id="A1")]
    )
    assert summary["observed_source_names"] == "abebooks | ebay_active_listings"


def test_multiple_input_files_write_stable_csv_and_xlsx(tmp_path):
    abebooks_path = tmp_path / "abebooks.csv"
    ebay_path = tmp_path / "ebay.csv"
    write_rows(abebooks_path, [observed()])
    write_rows(ebay_path, [status("ebay_active_listings")])
    output_csv = tmp_path / "summary.csv"
    output_xlsx = tmp_path / "summary.xlsx"
    count = summarize_market_evidence([abebooks_path, ebay_path], output_csv, output_xlsx)
    assert count == 1
    assert output_xlsx.exists()
    with output_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MARKET_EVIDENCE_SUMMARY_FIELDNAMES
        assert list(reader)[0]["source_count"] == "2"


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
