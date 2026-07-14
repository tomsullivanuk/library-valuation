import csv

from library_pipeline import summarize_market_evidence

from valuation.market_evidence_summary import (
    MARKET_EVIDENCE_SUMMARY_BASENAME,
    MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
    MARKET_EVIDENCE_SUMMARY_SCHEMA_VERSION,
    aggregate_market_evidence,
    build_conservative_market_range,
    build_review_recommendation,
    market_evidence_summary_fieldnames,
)


def test_market_evidence_summary_fieldnames_returns_copy():
    fields = market_evidence_summary_fieldnames()

    fields.append("mutated")

    assert "mutated" not in market_evidence_summary_fieldnames()


def test_market_evidence_summary_schema_matches_pr6_contract():
    assert MARKET_EVIDENCE_SUMMARY_SCHEMA_VERSION == "0.5.0-pr6"
    assert MARKET_EVIDENCE_SUMMARY_BASENAME == "market_evidence_summary"
    assert MARKET_EVIDENCE_SUMMARY_FIELDNAMES == [
        "catalog_item_id",
        "isbn_13",
        "isbn_10",
        "title",
        "author",
        "observation_count",
        "listing_count",
        "status_row_count",
        "source_count",
        "observed_source_names",
        "lookup_strategy",
        "best_match_confidence",
        "high_confidence_listing_count",
        "medium_confidence_listing_count",
        "low_confidence_listing_count",
        "unknown_confidence_listing_count",
        "currency",
        "min_asking_price",
        "median_asking_price",
        "max_asking_price",
        "trimmed_low_asking_price",
        "trimmed_high_asking_price",
        "evidence_status",
        "outlier_sensitivity",
        "market_confidence",
        "likely_low",
        "likely_mid",
        "likely_high",
        "market_range_basis",
        "review_recommendation",
        "review_reason",
        "fallback_research_priority",
        "research_score",
        "research_band",
        "triggered_signals",
        "evidence_generated_at",
        "evidence_model_version",
        "evidence_notes",
    ]


def test_market_evidence_summary_schema_uses_non_appraisal_terminology():
    joined_fieldnames = ",".join(MARKET_EVIDENCE_SUMMARY_FIELDNAMES)

    assert "appraisal" not in joined_fieldnames
    assert "fair_market_value" not in joined_fieldnames
    assert "sold_price" not in joined_fieldnames
    assert "sale_price" not in joined_fieldnames
    assert "valuation" not in joined_fieldnames


def test_market_evidence_summary_csv_header_matches_schema(tmp_path):
    path = tmp_path / "market_evidence_summary.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARKET_EVIDENCE_SUMMARY_FIELDNAMES)
        writer.writeheader()

    assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(MARKET_EVIDENCE_SUMMARY_FIELDNAMES)


def observation(**overrides):
    row = {
        "observation_id": "OBS1",
        "catalog_id": "BK000001",
        "isbn13": "9780000000001",
        "isbn10": "0000000001",
        "title": "Example Book",
        "author": "Example Author",
        "research_score": "7",
        "score_band": "high",
        "source": "abebooks",
        "lookup_status": "observed",
        "lookup_strategy": "isbn13",
        "asking_price": "10.00",
        "currency": "USD",
        "match_confidence": "high",
    }
    row.update(overrides)
    return row


def test_multiple_listings_aggregate_counts_prices_and_context():
    rows = [
        observation(asking_price="10.00", match_confidence="medium"),
        observation(observation_id="OBS2", asking_price="20.00", lookup_strategy="title_author"),
        observation(observation_id="OBS3", asking_price="30.00", match_confidence="low"),
    ]

    summary = aggregate_market_evidence(rows, generated_at="2026-07-14T00:00:00Z")[0]

    assert list(summary) == MARKET_EVIDENCE_SUMMARY_FIELDNAMES
    assert summary["catalog_item_id"] == "BK000001"
    assert summary["isbn_13"] == "9780000000001"
    assert summary["observation_count"] == "3"
    assert summary["listing_count"] == "3"
    assert summary["status_row_count"] == "0"
    assert summary["source_count"] == "1"
    assert summary["observed_source_names"] == "abebooks"
    assert summary["lookup_strategy"] == "isbn13 | title_author"
    assert summary["currency"] == "USD"
    assert summary["min_asking_price"] == "10.00"
    assert summary["median_asking_price"] == "20.00"
    assert summary["max_asking_price"] == "30.00"
    assert summary["trimmed_low_asking_price"] == "10.00"
    assert summary["trimmed_high_asking_price"] == "30.00"
    assert summary["research_score"] == "7"
    assert summary["research_band"] == "high"
    assert summary["evidence_model_version"] == "0.5.0-pr6"


def test_status_rows_count_as_coverage_but_not_prices():
    rows = [
        observation(asking_price="12.50"),
        observation(
            observation_id="STATUS1",
            lookup_status="no_results",
            asking_price="999.00",
            currency="USD",
            match_confidence="unknown",
        ),
    ]

    summary = aggregate_market_evidence(rows, generated_at="2026-07-14T00:00:00Z")[0]

    assert summary["observation_count"] == "2"
    assert summary["listing_count"] == "1"
    assert summary["status_row_count"] == "1"
    assert summary["median_asking_price"] == "12.50"
    assert summary["evidence_status"] == "observed_listings"
    assert summary["market_confidence"] == "thin_market_evidence"
    assert summary["outlier_sensitivity"] == "high_outlier_sensitivity"
    assert summary["likely_low"] == "12.50"
    assert summary["likely_mid"] == "12.50"
    assert summary["likely_high"] == ""
    assert summary["market_range_basis"] == "thin_evidence_high_outlier_sensitivity_observed_asking_prices"
    assert summary["review_recommendation"] == "manual_market_research_needed"
    assert "fragile_asking_price_evidence" in summary["review_reason"]
    assert summary["fallback_research_priority"] == ""
    assert "excluded from asking-price calculations" in summary["evidence_notes"]


def test_match_confidence_counts_and_best_are_deterministic():
    rows = [
        observation(match_confidence="unknown"),
        observation(observation_id="OBS2", match_confidence="low"),
        observation(observation_id="OBS3", match_confidence="medium"),
        observation(observation_id="OBS4", match_confidence="high"),
        observation(observation_id="OBS5", match_confidence="unexpected"),
    ]

    summary = aggregate_market_evidence(reversed(rows), generated_at="2026-07-14T00:00:00Z")[0]

    assert summary["best_match_confidence"] == "high"
    assert summary["high_confidence_listing_count"] == "1"
    assert summary["medium_confidence_listing_count"] == "1"
    assert summary["low_confidence_listing_count"] == "1"
    assert summary["unknown_confidence_listing_count"] == "2"


def test_mixed_currencies_are_not_combined():
    rows = [
        observation(asking_price="10.00", currency="USD"),
        observation(observation_id="OBS2", asking_price="15.00", currency="GBP"),
    ]

    summary = aggregate_market_evidence(rows, generated_at="2026-07-14T00:00:00Z")[0]

    for field in (
        "currency",
        "min_asking_price",
        "median_asking_price",
        "max_asking_price",
        "trimmed_low_asking_price",
        "trimmed_high_asking_price",
    ):
        assert summary[field] == ""
    assert "Mixed currencies" in summary["evidence_notes"]
    assert summary["market_confidence"] == "mixed_currency_evidence"
    assert summary["outlier_sensitivity"] == "unknown_outlier_sensitivity"
    assert summary["likely_low"] == summary["likely_mid"] == summary["likely_high"] == ""
    assert summary["market_range_basis"] == "range_not_available_mixed_currency"
    assert summary["review_recommendation"] == "manual_market_research_needed"
    assert summary["review_reason"] == "mixed_currency_evidence_requires_manual_research"


def test_status_only_row_leaves_reserved_fields_blank():
    summary = aggregate_market_evidence(
        [observation(lookup_status="source_unavailable", asking_price="", currency="")],
        generated_at="2026-07-14T00:00:00Z",
    )[0]

    assert summary["evidence_status"] == "source_unavailable"
    assert summary["market_confidence"] == "source_unavailable"
    assert summary["outlier_sensitivity"] == "not_applicable"
    assert summary["best_match_confidence"] == ""
    assert summary["likely_low"] == summary["likely_mid"] == summary["likely_high"] == ""
    assert summary["market_range_basis"] == "range_not_available_source_unavailable"
    assert summary["review_recommendation"] == "fallback_research_priority"
    assert summary["review_reason"] == "market_evidence_unavailable_high_research_priority"
    assert summary["fallback_research_priority"] == "high"


def listing_rows(prices, *, match_confidence="high", currency="USD"):
    return [
        observation(
            observation_id=f"OBS{index}",
            asking_price=str(price),
            currency=currency,
            match_confidence=match_confidence,
        )
        for index, price in enumerate(prices, start=1)
    ]


def test_high_confidence_market_evidence_has_low_outlier_sensitivity():
    summary = aggregate_market_evidence(
        listing_rows([10, 11, 12, 13, 14]), generated_at="2026-07-14T00:00:00Z"
    )[0]

    assert summary["market_confidence"] == "high_confidence_market_evidence"
    assert summary["outlier_sensitivity"] == "low_outlier_sensitivity"
    assert summary["likely_low"] == "10.00"
    assert summary["likely_mid"] == "12.00"
    assert summary["likely_high"] == "14.00"
    assert summary["market_range_basis"] == "high_confidence_observed_asking_prices"
    assert summary["review_recommendation"] == "market_evidence_sufficient"
    assert summary["review_reason"] == "usable_market_evidence_below_sale_review_threshold"


def test_high_confidence_range_uses_distinct_trimmed_bounds():
    result = build_conservative_market_range(
        {
            "market_confidence": "high_confidence_market_evidence",
            "outlier_sensitivity": "moderate_outlier_sensitivity",
            "min_asking_price": "5.00",
            "median_asking_price": "20.00",
            "max_asking_price": "100.00",
            "trimmed_low_asking_price": "10.00",
            "trimmed_high_asking_price": "40.00",
        }
    )

    assert result == {
        "likely_low": "10.00",
        "likely_mid": "20.00",
        "likely_high": "40.00",
        "market_range_basis": "high_confidence_observed_asking_prices",
    }


def test_moderate_confidence_market_evidence():
    summary = aggregate_market_evidence(
        listing_rows([10, 15, 20], match_confidence="medium"), generated_at="2026-07-14T00:00:00Z"
    )[0]

    assert summary["market_confidence"] == "moderate_confidence_market_evidence"
    assert summary["outlier_sensitivity"] == "low_outlier_sensitivity"
    assert summary["likely_low"] == "10.00"
    assert summary["likely_mid"] == "15.00"
    assert summary["likely_high"] == "20.00"
    assert summary["market_range_basis"] == "moderate_confidence_observed_asking_prices"
    assert summary["review_recommendation"] == "market_evidence_sufficient"


def test_ambiguous_edition_match_outranks_listing_volume():
    summary = aggregate_market_evidence(
        listing_rows([10, 11, 12, 13, 14], match_confidence="low"), generated_at="2026-07-14T00:00:00Z"
    )[0]

    assert summary["market_confidence"] == "ambiguous_edition_match"
    assert summary["likely_low"] == "10.00"
    assert summary["likely_mid"] == "12.00"
    assert summary["likely_high"] == ""
    assert summary["market_range_basis"] == "ambiguous_match_observed_asking_prices"
    assert summary["review_recommendation"] == "review_edition_or_condition"
    assert summary["review_reason"] == "ambiguous_edition_or_condition_match"


def test_price_unavailable_evidence():
    summary = aggregate_market_evidence(
        listing_rows(["", "", ""]), generated_at="2026-07-14T00:00:00Z"
    )[0]

    assert summary["market_confidence"] == "price_unavailable_evidence"
    assert summary["outlier_sensitivity"] == "unknown_outlier_sensitivity"
    assert summary["likely_low"] == summary["likely_mid"] == summary["likely_high"] == ""
    assert summary["market_range_basis"] == "range_not_available_price_unavailable"
    assert summary["review_recommendation"] == "manual_market_research_needed"
    assert summary["review_reason"] == "asking_price_unavailable_requires_manual_research"


def test_no_market_evidence_and_no_query_categories():
    no_evidence = aggregate_market_evidence(
        [observation(lookup_status="no_results", asking_price="", currency="")],
        generated_at="2026-07-14T00:00:00Z",
    )[0]
    no_query = aggregate_market_evidence(
        [observation(lookup_status="no_query", asking_price="", currency="")],
        generated_at="2026-07-14T00:00:00Z",
    )[0]

    assert no_evidence["market_confidence"] == "no_market_evidence"
    assert no_evidence["outlier_sensitivity"] == "not_applicable"
    assert no_evidence["market_range_basis"] == "range_not_available_no_market_evidence"
    assert no_evidence["review_recommendation"] == "fallback_research_priority"
    assert no_evidence["fallback_research_priority"] == "high"
    assert no_query["market_confidence"] == "no_query"
    assert no_query["outlier_sensitivity"] == "not_applicable"
    assert no_query["market_range_basis"] == "range_not_available_no_query"
    assert no_query["review_recommendation"] == "metadata_cleanup_needed"
    assert no_query["review_reason"] == "insufficient_metadata_for_market_lookup"
    assert no_query["fallback_research_priority"] == "high"


def test_outlier_sensitivity_moderate_and_high_spread():
    moderate = aggregate_market_evidence(
        listing_rows([10, 20, 30]), generated_at="2026-07-14T00:00:00Z"
    )[0]
    high = aggregate_market_evidence(
        listing_rows([10, 20, 50]), generated_at="2026-07-14T00:00:00Z"
    )[0]

    assert moderate["outlier_sensitivity"] == "moderate_outlier_sensitivity"
    assert high["outlier_sensitivity"] == "high_outlier_sensitivity"
    assert high["market_confidence"] == "unknown_market_confidence"
    assert high["likely_high"] == ""
    assert high["market_range_basis"] == "range_not_available_unknown_confidence"
    assert high["review_recommendation"] == "manual_market_research_needed"
    assert "fragile_asking_price_evidence" in high["review_reason"]


def test_meaningful_asking_price_range_recommends_possible_sale_review():
    summary = aggregate_market_evidence(
        listing_rows([50, 55, 60, 65, 70]), generated_at="2026-07-14T00:00:00Z"
    )[0]

    assert summary["market_confidence"] == "high_confidence_market_evidence"
    assert summary["likely_mid"] == "60.00"
    assert summary["review_recommendation"] == "review_for_possible_sale"
    assert summary["review_reason"] == "asking_price_range_meets_initial_sale_review_threshold"
    assert summary["fallback_research_priority"] == ""


def test_high_side_threshold_can_trigger_possible_sale_review():
    result = build_review_recommendation(
        {
            "market_confidence": "moderate_confidence_market_evidence",
            "likely_mid": "45.00",
            "likely_high": "75.00",
            "research_band": "high",
        }
    )

    assert result == {
        "review_recommendation": "review_for_possible_sale",
        "review_reason": "asking_price_range_meets_initial_sale_review_threshold",
        "fallback_research_priority": "",
    }


def test_low_research_priority_without_market_evidence_needs_no_action():
    summary = aggregate_market_evidence(
        [
            observation(
                lookup_status="no_results",
                asking_price="",
                currency="",
                research_score="4",
                score_band="low",
            )
        ],
        generated_at="2026-07-14T00:00:00Z",
    )[0]

    assert summary["review_recommendation"] == "no_action_needed"
    assert summary["review_reason"] == "market_evidence_unavailable_low_research_priority"
    assert summary["fallback_research_priority"] == "low"


def test_pipeline_entry_point_writes_csv_and_xlsx(tmp_path):
    observations = tmp_path / "market_observations.csv"
    output_csv = tmp_path / "market_evidence_summary.csv"
    output_xlsx = tmp_path / "market_evidence_summary.xlsx"
    with observations.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(observation()))
        writer.writeheader()
        writer.writerow(observation())

    count = summarize_market_evidence(observations, output_csv, output_xlsx)

    assert count == 1
    assert output_xlsx.exists()
    with output_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MARKET_EVIDENCE_SUMMARY_FIELDNAMES
        assert list(reader)[0]["catalog_item_id"] == "BK000001"
