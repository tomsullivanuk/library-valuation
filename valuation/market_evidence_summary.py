"""Source-neutral Market Evidence Summary schema."""

from __future__ import annotations


MARKET_EVIDENCE_SUMMARY_SCHEMA_VERSION = "0.5.0-pr2"

MARKET_EVIDENCE_SUMMARY_BASENAME = "market_evidence_summary"

MARKET_EVIDENCE_SUMMARY_FIELDNAMES = [
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


def market_evidence_summary_fieldnames() -> list[str]:
    """Return the generated Market Evidence Summary column order."""
    return list(MARKET_EVIDENCE_SUMMARY_FIELDNAMES)
