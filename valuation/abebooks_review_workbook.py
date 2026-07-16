"""Reviewer-facing workbook for the full-library AbeBooks baseline."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path

from valuation.collector_workbook import write_workbook


REVIEW_WORKBOOK_SHEETS = [
    "Review Queue",
    "Possible Sale",
    "Manual Research",
    "Edition Condition Review",
    "Evidence Detail",
    "Run Summary",
    "Field Definitions",
]

REVIEW_QUEUE_FIELDNAMES = [
    "catalog_item_id",
    "title",
    "author",
    "latest_acquired_date",
    "possession_confidence",
    "review_recommendation",
    "review_reason",
    "likely_mid",
    "likely_high",
    "market_confidence",
    "outlier_sensitivity",
    "best_match_confidence",
    "listing_count",
    "isbn_13",
]

POSSIBLE_SALE_FIELDNAMES = [
    "catalog_item_id", "title", "author", "latest_acquired_date", "possession_confidence",
    "likely_low", "likely_mid", "likely_high", "market_confidence", "outlier_sensitivity",
    "listing_count", "best_match_confidence", "review_reason", "isbn_13",
]

MANUAL_RESEARCH_FIELDNAMES = [
    "catalog_item_id", "title", "author", "latest_acquired_date", "possession_confidence",
    "review_recommendation", "review_reason", "likely_mid", "likely_high", "market_confidence",
    "outlier_sensitivity", "listing_count", "best_match_confidence", "research_score",
    "research_band", "isbn_13",
]

EDITION_CONDITION_FIELDNAMES = [
    "catalog_item_id", "title", "author", "isbn_13", "review_reason", "best_match_confidence",
    "market_confidence", "likely_mid", "likely_high", "listing_count", "latest_acquired_date",
    "possession_confidence",
]

ACQUISITION_CONTEXT_FIELDNAMES = [
    "latest_acquired_date",
    "acquisition_year",
    "possession_confidence",
    "possession_note",
]

SUMMARY_FIELDNAMES = ["section", "metric", "value", "note"]
DEFINITION_FIELDNAMES = ["field", "what_it_means", "source_or_derivation", "example_values", "reviewer_guidance"]

REVIEW_PRIORITY = {
    "review_for_possible_sale": 0,
    "manual_market_research_needed": 1,
    "review_edition_or_condition": 2,
    "fallback_research_priority": 3,
    "metadata_cleanup_needed": 4,
    "market_evidence_sufficient": 5,
    "no_action_needed": 6,
}
POSSESSION_PRIORITY = {"likely_present": 0, "unknown": 1, "possibly_absent": 2}
MANUAL_RESEARCH_RECOMMENDATIONS = {
    "manual_market_research_needed",
    "fallback_research_priority",
    "metadata_cleanup_needed",
}


def write_abebooks_review_workbook(
    output_path: Path,
    *,
    summary_rows: list[dict[str, str]],
    acquisitions: Iterable[Mapping[str, str]],
) -> None:
    """Write a generated review workbook without changing canonical evidence rows."""
    enriched = add_acquisition_context(summary_rows, acquisitions)
    review_rows = sorted(enriched, key=review_sort_key)
    evidence_fieldnames = list(summary_rows[0]) if summary_rows else []
    evidence_fieldnames.extend(field for field in ACQUISITION_CONTEXT_FIELDNAMES if field not in evidence_fieldnames)
    sheets = [
        ("Review Queue", REVIEW_QUEUE_FIELDNAMES, project_review_rows(review_rows, REVIEW_QUEUE_FIELDNAMES)),
        (
            "Possible Sale",
            POSSIBLE_SALE_FIELDNAMES,
            project_review_rows(
                (row for row in review_rows if row.get("review_recommendation") == "review_for_possible_sale"),
                POSSIBLE_SALE_FIELDNAMES,
            ),
        ),
        (
            "Manual Research",
            MANUAL_RESEARCH_FIELDNAMES,
            project_review_rows(
                (row for row in review_rows if row.get("review_recommendation") in MANUAL_RESEARCH_RECOMMENDATIONS),
                MANUAL_RESEARCH_FIELDNAMES,
            ),
        ),
        (
            "Edition Condition Review",
            EDITION_CONDITION_FIELDNAMES,
            project_review_rows(
                (row for row in review_rows if row.get("review_recommendation") == "review_edition_or_condition"),
                EDITION_CONDITION_FIELDNAMES,
            ),
        ),
        ("Evidence Detail", evidence_fieldnames, enriched),
        ("Run Summary", SUMMARY_FIELDNAMES, build_run_summary_rows(review_rows)),
        ("Field Definitions", DEFINITION_FIELDNAMES, field_definition_rows(evidence_fieldnames)),
    ]
    write_workbook(output_path, sheets)


def add_acquisition_context(
    summary_rows: Iterable[Mapping[str, str]], acquisitions: Iterable[Mapping[str, str]]
) -> list[dict[str, str]]:
    acquisitions_by_id: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for acquisition in acquisitions:
        catalog_item_id = acquisition.get("catalog_item_id", "")
        if catalog_item_id:
            acquisitions_by_id[catalog_item_id].append(acquisition)

    enriched = []
    for summary in summary_rows:
        row = dict(summary)
        row.update(possession_context(acquisitions_by_id.get(row.get("catalog_item_id", ""), [])))
        enriched.append(row)
    return enriched


def possession_context(acquisitions: Iterable[Mapping[str, str]]) -> dict[str, str]:
    dated = []
    for acquisition in acquisitions:
        raw_date = acquisition.get("order_date", "").strip()
        parsed = parse_acquisition_date(raw_date)
        if parsed:
            dated.append((parsed, raw_date))
    if not dated:
        return {
            "latest_acquired_date": "",
            "acquisition_year": "",
            "possession_confidence": "unknown",
            "possession_note": "acquisition date unavailable; verify physical possession",
        }
    latest_date, latest_raw = max(dated, key=lambda value: value[0])
    if latest_date.year >= 2021:
        confidence = "likely_present"
        note = "acquired in or after 2021"
    else:
        confidence = "possibly_absent"
        note = "acquired before 2021; verify physical possession before sale/research"
    return {
        "latest_acquired_date": latest_raw,
        "acquisition_year": str(latest_date.year),
        "possession_confidence": confidence,
        "possession_note": note,
    }


def parse_acquisition_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def review_sort_key(row: Mapping[str, str]) -> tuple[int, int, float, float, str, str]:
    return (
        REVIEW_PRIORITY.get(row.get("review_recommendation", ""), 99),
        POSSESSION_PRIORITY.get(row.get("possession_confidence", ""), 99),
        -number_value(row.get("likely_mid", "")),
        -number_value(row.get("likely_high", "")),
        row.get("title", "").casefold(),
        row.get("catalog_item_id", ""),
    )


def number_value(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def project_review_rows(rows: Iterable[Mapping[str, str]], fieldnames: Iterable[str]) -> list[dict[str, str]]:
    fields = list(fieldnames)
    return [{field: row.get(field, "") for field in fields} for row in rows]


def build_run_summary_rows(rows: list[Mapping[str, str]]) -> list[dict[str, str]]:
    output = [summary_row("Run", "Total summary rows", len(rows), "One row per catalog item in the input summary.")]
    for field, section in (
        ("review_recommendation", "Review recommendation counts"),
        ("market_confidence", "Market confidence counts"),
        ("outlier_sensitivity", "Outlier sensitivity counts"),
        ("possession_confidence", "Possession confidence counts"),
        ("source_count", "Observed source-count counts"),
        ("observed_source_names", "Observed source-name counts"),
    ):
        counts = Counter(row.get(field, "") or "(blank)" for row in rows)
        output.extend(summary_row(section, value, count) for value, count in sorted(counts.items()))
    candidates = [row for row in rows if row.get("review_recommendation") == "review_for_possible_sale"][:20]
    output.extend(
        summary_row(
            "Top possible-sale candidates",
            row.get("title", "") or row.get("catalog_item_id", ""),
            row.get("likely_mid", ""),
            f"{row.get('catalog_item_id', '')}; possession: {row.get('possession_confidence', '')}; likely high: {row.get('likely_high', '')}",
        )
        for row in candidates
    )
    return output


def summary_row(section: str, metric: str, value: str | int, note: str = "") -> dict[str, str]:
    return {"section": section, "metric": metric, "value": str(value), "note": note}


def definition(meaning: str, source: str, examples: str, guidance: str) -> tuple[str, str, str, str]:
    return meaning, source, examples, guidance


ASKING_PRICE_CAVEAT = (
    "Observed AbeBooks asking-price-derived reference; not an appraisal, fair market value, realized sale price, "
    "or expected sale proceeds."
)


FIELD_DEFINITIONS = {
    "catalog_item_id": definition("Stable internal catalog identity.", "Copied from the durable catalog identity on the summary row.", "BK000001", "Use this key to reconcile a row to catalog and acquisition records."),
    "isbn_13": definition("Thirteen-digit book identifier.", "Copied from catalog/observation identity used by the evidence summary.", "9780198809647", "Confirm that it identifies the edition physically in hand."),
    "isbn_10": definition("Older ten-character book identifier.", "Copied from catalog/observation identity when available.", "0198809646", "Useful for older listings; a blank value may simply mean no ISBN-10 was available."),
    "title": definition("Catalog title for the book.", "Copied from the market evidence summary identity fields.", "History of Continua", "Verify title, volume, and edition when a price looks surprising."),
    "author": definition("Catalog author or authors.", "Copied from the market evidence summary identity fields.", "Stewart Shapiro; Geoffrey Hellman", "Missing or incorrect authors can weaken marketplace matching."),
    "latest_acquired_date": definition("Most recent known acquisition date.", "Latest valid order_date in data/acquisitions.csv joined by catalog_item_id.", "2024-07-17T20:23:21Z", "Dates before 2021 trigger a physical-possession warning."),
    "acquisition_year": definition("Year of the latest known acquisition.", "Year extracted from latest_acquired_date.", "2024", "Use the 2021 boundary only as possession context, not market evidence."),
    "possession_confidence": definition("Date-based indication that the book may still be present.", "Derived from latest acquisition: 2021+ likely_present; pre-2021 possibly_absent; missing/invalid unknown.", "likely_present; possibly_absent; unknown", "Physically verify possibly_absent and unknown items; this field never suppresses price evidence."),
    "possession_note": definition("Plain-language explanation of possession confidence.", "Generated from the same acquisition-date rule as possession_confidence.", "acquired before 2021; verify physical possession before sale/research", "Follow the verification instruction before investing time or offering a book for sale."),
    "observation_count": definition("All AbeBooks response rows summarized for the book.", "Count of listing rows plus diagnostic/status rows in the market observations input.", "3", "Compare with listing_count and status_row_count to understand what the lookup returned."),
    "listing_count": definition("Observed AbeBooks listings summarized for the book.", "Count of observation rows whose lookup status is observed.", "0; 1; 3", "More listings usually provide broader evidence; one listing is thin evidence."),
    "status_row_count": definition("Non-listing diagnostic results.", "Count of observation rows such as no_results, source_unavailable, or no_query.", "0; 1", "A nonzero value explains why usable listing evidence may be absent."),
    "source_count": definition("Number of marketplace sources with observed evidence.", "Count of distinct source names in the summarized observations.", "1", "In this AbeBooks-only baseline it is normally 1 and is retained for auditability."),
    "observed_source_names": definition("Marketplace sources contributing observed listings.", "Distinct source_name values joined from observed rows.", "abebooks", "Blank means no source produced an observed listing; this baseline otherwise normally shows abebooks."),
    "lookup_strategy": definition("Lookup method used to find listings.", "Distinct strategy values reported by the AbeBooks collector.", "isbn13; title_author", "ISBN lookup is usually more edition-specific; title/author lookup deserves closer identity review."),
    "best_match_confidence": definition("Strongest listing-identity match confidence observed.", "Highest of high, medium, low, or unknown assigned by collection matching rules.", "high; medium; low", "Low or unknown confidence increases the risk of a wrong edition or title match."),
    "high_confidence_listing_count": definition("Listings rated high match confidence.", "Count of observed listings classified high by matching rules.", "0; 3", "A larger share of high-confidence matches strengthens identity evidence."),
    "medium_confidence_listing_count": definition("Listings rated medium match confidence.", "Count of observed listings classified medium by matching rules.", "0; 2", "Review edition details before relying on price evidence dominated by medium matches."),
    "low_confidence_listing_count": definition("Listings rated low match confidence.", "Count of observed listings classified low by matching rules.", "0; 1", "Low-confidence evidence should prompt edition/identity checking."),
    "unknown_confidence_listing_count": definition("Listings without a recognized match-confidence rating.", "Count of observed listings with blank or unrecognized match confidence.", "0; 1", "Treat unknown matches cautiously and inspect the underlying listing identity."),
    "currency": definition("Currency shared by usable asking prices.", "Set only when priced listings use one currency; mixed currencies are not combined.", "USD", "Do not compare or combine amounts across currencies without conversion outside this workbook."),
    "min_asking_price": definition("Lowest usable observed asking price.", "Minimum price among same-currency observed listings.", "42.50", "A raw extreme; consult trimmed references and outlier_sensitivity."),
    "median_asking_price": definition("Middle usable observed asking price.", "Median of same-currency observed listing prices.", "55.00", "A descriptive asking-price statistic, not a sale-price estimate."),
    "max_asking_price": definition("Highest usable observed asking price.", "Maximum price among same-currency observed listings.", "120.00", "May reflect an outlier, exceptional condition, or different edition."),
    "trimmed_low_asking_price": definition("Lower asking price after the summary's conservative trimming rule.", "Derived by existing market evidence aggregation; unchanged by this workbook.", "45.00", "Compare with min_asking_price to see whether a low extreme was moderated."),
    "trimmed_high_asking_price": definition("Upper asking price after the summary's conservative trimming rule.", "Derived by existing market evidence aggregation; unchanged by this workbook.", "95.00", "Compare with max_asking_price to see whether a high extreme was moderated."),
    "evidence_status": definition("Whether usable listing evidence was observed.", "Classified from observation and price availability.", "observed_listings; no_results; source_unavailable", "Use it to distinguish no market result from a temporary source problem."),
    "outlier_sensitivity": definition("How much extreme listings affect the price range.", "Existing comparison of raw and trimmed asking-price statistics.", "low_outlier_sensitivity; high_outlier_sensitivity; not_applicable", "High sensitivity calls for manual listing, edition, and condition review."),
    "market_confidence": definition("Overall reliability class for the observed market evidence.", "Existing deterministic rules using listing coverage, match quality, price usability, and ambiguity.", "moderate_confidence_market_evidence; thin_market_evidence; source_unavailable", "Confidence describes evidence quality, not certainty of value or saleability."),
    "likely_low": definition("Conservative lower asking-price reference.", "Existing conservative-range logic over usable same-currency AbeBooks asking prices.", "50.00", ASKING_PRICE_CAVEAT),
    "likely_mid": definition("Central asking-price reference used for review prioritization.", "Existing conservative-range logic, generally anchored to the observed median.", "75.00", ASKING_PRICE_CAVEAT),
    "likely_high": definition("Conservative upper asking-price reference.", "Existing conservative-range logic over usable same-currency AbeBooks asking prices.", "100.00", ASKING_PRICE_CAVEAT),
    "market_range_basis": definition("Reason code naming the method behind likely_low/mid/high.", "Assigned by the existing conservative range logic.", "moderate_confidence_observed_asking_prices", "Use it to understand why a range exists or why it was withheld."),
    "review_recommendation": definition("Suggested next human action.", "Copied unchanged from existing review-recommendation logic.", "review_for_possible_sale; manual_market_research_needed", "Treat as a queueing aid, not an automatic sale or valuation decision."),
    "review_reason": definition("Reason code explaining the recommendation.", "Copied unchanged from existing review-recommendation logic.", "asking_price_range_meets_initial_sale_review_threshold", "Read alongside market confidence, match confidence, and possession confidence."),
    "fallback_research_priority": definition("Research priority used when market evidence is unavailable.", "Derived from the existing Research Assessment context.", "high; medium; low", "It prioritizes research effort and is not price evidence."),
    "research_score": definition("Existing Research Assessment score.", "Copied from the durable/generated Research Assessment used as fallback context.", "30", "Higher scores suggest research interest; they do not predict price."),
    "research_band": definition("Existing Research Assessment band.", "Mapped from the Research Assessment score under unchanged scoring rules.", "8-10; 6-7; 4-5; 0-3", "Use only for research prioritization, not valuation."),
    "triggered_signals": definition("Research Signal codes contributing fallback context.", "Joined from the existing Research Assessment signals.", "old_publication_year; multiple_acquisitions", "These explain research interest and are not marketplace evidence."),
    "evidence_generated_at": definition("Time the evidence summary was generated.", "UTC timestamp written by market evidence aggregation.", "2026-07-15T14:09:23Z", "Use to judge how current the marketplace snapshot is."),
    "evidence_model_version": definition("Version of the evidence-summary rules.", "Written by the market evidence aggregation implementation.", "0.5.0-pr6", "Use when comparing workbooks produced under different rule versions."),
    "evidence_notes": definition("Human-readable aggregation warnings or limitations for the row.", "Generated when listings, prices, currencies, or statuses require explanation.", "No observed listing rows.", "Read before interpreting blank ranges or unusual confidence."),
}


def field_definition_rows(fieldnames: Iterable[str]) -> list[dict[str, str]]:
    rows = []
    reviewer_fields = [
        *REVIEW_QUEUE_FIELDNAMES,
        *POSSIBLE_SALE_FIELDNAMES,
        *MANUAL_RESEARCH_FIELDNAMES,
        *EDITION_CONDITION_FIELDNAMES,
    ]
    for field in dict.fromkeys([*reviewer_fields, *fieldnames]):
        meaning, source, examples, guidance = FIELD_DEFINITIONS.get(
            field,
            definition(
                "Additional field retained from the input evidence summary.",
                "Copied unchanged from the input summary CSV.",
                "Varies by input schema.",
                "Use as supporting audit detail; it is not promoted to a reviewer-facing queue column.",
            ),
        )
        rows.append(
            {
                "field": field,
                "what_it_means": meaning,
                "source_or_derivation": source,
                "example_values": examples,
                "reviewer_guidance": guidance,
            }
        )
    return rows
