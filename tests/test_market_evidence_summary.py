import csv

from valuation.market_evidence_summary import (
    MARKET_EVIDENCE_SUMMARY_BASENAME,
    MARKET_EVIDENCE_SUMMARY_FIELDNAMES,
    MARKET_EVIDENCE_SUMMARY_SCHEMA_VERSION,
    market_evidence_summary_fieldnames,
)


def test_market_evidence_summary_fieldnames_returns_copy():
    fields = market_evidence_summary_fieldnames()

    fields.append("mutated")

    assert "mutated" not in market_evidence_summary_fieldnames()


def test_market_evidence_summary_schema_matches_pr2_contract():
    assert MARKET_EVIDENCE_SUMMARY_SCHEMA_VERSION == "0.5.0-pr2"
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
