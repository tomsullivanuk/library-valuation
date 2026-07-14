"""Source-neutral aggregation for generated Market Evidence Summaries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from statistics import median


MARKET_EVIDENCE_SUMMARY_SCHEMA_VERSION = "0.5.0-pr5"

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


CONFIDENCE_STRENGTH = {"unknown": 0, "low": 1, "medium": 2, "high": 3}


def aggregate_market_evidence(
    observation_rows: Iterable[Mapping[str, str]], *, generated_at: str | None = None
) -> list[dict[str, str]]:
    """Aggregate source-neutral observation rows into one summary per book."""
    groups: dict[tuple[str, ...], list[Mapping[str, str]]] = defaultdict(list)
    for index, row in enumerate(observation_rows):
        key = _identity_key(row)
        groups[key or ("unidentified", str(index))].append(row)

    timestamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    summaries = [_summarize_group(rows, timestamp) for _, rows in sorted(groups.items())]
    return summaries


def _identity_key(row: Mapping[str, str]) -> tuple[str, ...] | None:
    catalog_id = _first(row, "catalog_item_id", "catalog_id", "sample_id")
    if catalog_id:
        return ("catalog", catalog_id)
    isbn13 = _first(row, "isbn_13", "isbn13")
    if isbn13:
        return ("isbn13", isbn13)
    isbn10 = _first(row, "isbn_10", "isbn10")
    if isbn10:
        return ("isbn10", isbn10)
    title = _first(row, "title").casefold()
    author = _first(row, "author", "authors").casefold()
    if title or author:
        return ("title_author", title, author)
    observation_id = _first(row, "observation_id")
    return ("observation", observation_id) if observation_id else None


def _summarize_group(rows: list[Mapping[str, str]], generated_at: str) -> dict[str, str]:
    listings = [row for row in rows if _first(row, "lookup_status").casefold() == "observed"]
    status_rows = [row for row in rows if row not in listings]
    sources = _stable_values(rows, "source_name", "source")
    strategies = _stable_values(rows, "lookup_strategy")
    confidence_counts = {name: 0 for name in CONFIDENCE_STRENGTH}
    for row in listings:
        confidence = _first(row, "match_confidence").casefold()
        confidence_counts[confidence if confidence in confidence_counts else "unknown"] += 1
    observed_confidences = [name for name, count in confidence_counts.items() if count]
    best_confidence = max(observed_confidences, key=CONFIDENCE_STRENGTH.get) if observed_confidences else ""

    priced = []
    missing_price_count = 0
    for row in listings:
        price = _decimal(_first(row, "asking_price", "price"))
        currency = _first(row, "currency").upper()
        if price is None or not currency:
            missing_price_count += 1
        else:
            priced.append((price, currency))
    currencies = sorted({currency for _, currency in priced})
    mixed_currencies = len(currencies) > 1
    prices = sorted(price for price, _ in priced) if len(currencies) == 1 else []

    notes = []
    if not listings:
        notes.append("No observed listing rows.")
    if missing_price_count:
        notes.append(f"{missing_price_count} listing row(s) lacked a usable asking price or currency.")
    if mixed_currencies:
        notes.append("Mixed currencies were observed; asking-price summaries were left blank because no conversion was applied.")
    if status_rows:
        notes.append(f"{len(status_rows)} source status row(s) were excluded from asking-price calculations.")

    values = {
        "catalog_item_id": _first_across(rows, "catalog_item_id", "catalog_id", "sample_id"),
        "isbn_13": _first_across(rows, "isbn_13", "isbn13"),
        "isbn_10": _first_across(rows, "isbn_10", "isbn10"),
        "title": _first_across(rows, "title"),
        "author": _first_across(rows, "author", "authors"),
        "observation_count": str(len(rows)),
        "listing_count": str(len(listings)),
        "status_row_count": str(len(status_rows)),
        "source_count": str(len(sources)),
        "observed_source_names": " | ".join(sources),
        "lookup_strategy": " | ".join(strategies),
        "best_match_confidence": best_confidence,
        "high_confidence_listing_count": str(confidence_counts["high"]),
        "medium_confidence_listing_count": str(confidence_counts["medium"]),
        "low_confidence_listing_count": str(confidence_counts["low"]),
        "unknown_confidence_listing_count": str(confidence_counts["unknown"]),
        "currency": currencies[0] if len(currencies) == 1 else "",
        "min_asking_price": _format_decimal(prices[0]) if prices else "",
        "median_asking_price": _format_decimal(median(prices)) if prices else "",
        "max_asking_price": _format_decimal(prices[-1]) if prices else "",
        "trimmed_low_asking_price": _format_decimal(prices[0]) if prices else "",
        "trimmed_high_asking_price": _format_decimal(prices[-1]) if prices else "",
        "evidence_status": _evidence_status(listings, status_rows),
        "research_score": _first_across(rows, "research_score"),
        "research_band": _first_across(rows, "research_band", "score_band"),
        "triggered_signals": _first_across(rows, "triggered_signals"),
        "evidence_generated_at": generated_at,
        "evidence_model_version": MARKET_EVIDENCE_SUMMARY_SCHEMA_VERSION,
        "evidence_notes": " ".join(notes),
    }
    values["outlier_sensitivity"] = classify_outlier_sensitivity(values)
    values["market_confidence"] = classify_market_confidence(values)
    values.update(build_conservative_market_range(values))
    return {field: values.get(field, "") for field in MARKET_EVIDENCE_SUMMARY_FIELDNAMES}


def classify_outlier_sensitivity(summary_row: Mapping[str, str]) -> str:
    """Classify sensitivity to sample size and observed asking-price spread."""
    listing_count = _integer(_first(summary_row, "listing_count"))
    if listing_count == 0:
        return "not_applicable"
    low = _decimal(_first(summary_row, "min_asking_price"))
    high = _decimal(_first(summary_row, "max_asking_price"))
    if low is None or high is None:
        return "unknown_outlier_sensitivity"
    if listing_count < 3 or low == 0 < high:
        return "high_outlier_sensitivity"
    if low == 0:
        return "low_outlier_sensitivity"
    spread_ratio = high / low
    if spread_ratio >= Decimal("5"):
        return "high_outlier_sensitivity"
    if spread_ratio >= Decimal("3"):
        return "moderate_outlier_sensitivity"
    return "low_outlier_sensitivity"


def classify_market_confidence(summary_row: Mapping[str, str]) -> str:
    """Classify evidence usability without asserting or estimating book value."""
    evidence_status = _first(summary_row, "evidence_status")
    listing_count = _integer(_first(summary_row, "listing_count"))
    if evidence_status == "source_unavailable":
        return "source_unavailable"
    if evidence_status == "no_query":
        return "no_query"
    if listing_count == 0:
        return "no_market_evidence"
    if "mixed currencies" in _first(summary_row, "evidence_notes").casefold():
        return "mixed_currency_evidence"
    if _decimal(_first(summary_row, "median_asking_price")) is None:
        return "price_unavailable_evidence"
    best_match = _first(summary_row, "best_match_confidence").casefold()
    if best_match not in {"high", "medium"}:
        return "ambiguous_edition_match"
    if listing_count < 3:
        return "thin_market_evidence"
    outlier_sensitivity = _first(summary_row, "outlier_sensitivity")
    high_confidence_count = _integer(_first(summary_row, "high_confidence_listing_count"))
    if listing_count >= 5 and high_confidence_count >= 3 and outlier_sensitivity != "high_outlier_sensitivity":
        return "high_confidence_market_evidence"
    if outlier_sensitivity != "high_outlier_sensitivity":
        return "moderate_confidence_market_evidence"
    return "unknown_market_confidence"


RANGE_UNAVAILABLE_BASIS = {
    "source_unavailable": "range_not_available_source_unavailable",
    "no_query": "range_not_available_no_query",
    "no_market_evidence": "range_not_available_no_market_evidence",
    "mixed_currency_evidence": "range_not_available_mixed_currency",
    "price_unavailable_evidence": "range_not_available_price_unavailable",
    "unknown_market_confidence": "range_not_available_unknown_confidence",
}


def build_conservative_market_range(summary_row: Mapping[str, str]) -> dict[str, str]:
    """Build a cautious asking-price-derived range without estimating sale value."""
    confidence = _first(summary_row, "market_confidence")
    if confidence in RANGE_UNAVAILABLE_BASIS:
        return _range_values(basis=RANGE_UNAVAILABLE_BASIS[confidence])

    low = _first(summary_row, "min_asking_price")
    mid = _first(summary_row, "median_asking_price")
    high = _first(summary_row, "max_asking_price")
    trimmed_low = _first(summary_row, "trimmed_low_asking_price") or low
    trimmed_high = _first(summary_row, "trimmed_high_asking_price") or high
    if not low or not mid:
        return _range_values(basis="range_not_available_price_unavailable")

    sensitivity = _first(summary_row, "outlier_sensitivity")
    if confidence == "ambiguous_edition_match":
        basis = "ambiguous_match_observed_asking_prices"
        if sensitivity == "high_outlier_sensitivity":
            basis = "ambiguous_match_high_outlier_sensitivity_observed_asking_prices"
        return _range_values(low=low, mid=mid, basis=basis)
    if confidence == "thin_market_evidence":
        if sensitivity == "high_outlier_sensitivity":
            return _range_values(
                low=low,
                mid=mid,
                basis="thin_evidence_high_outlier_sensitivity_observed_asking_prices",
            )
        return _range_values(low=low, mid=mid, high=high, basis="thin_evidence_observed_asking_prices")
    if confidence == "moderate_confidence_market_evidence":
        return _range_values(
            low=trimmed_low,
            mid=mid,
            high=trimmed_high,
            basis="moderate_confidence_observed_asking_prices",
        )
    if confidence == "high_confidence_market_evidence":
        if not trimmed_low or not trimmed_high:
            return _range_values(basis="range_not_available_price_unavailable")
        return _range_values(
            low=trimmed_low,
            mid=mid,
            high=trimmed_high,
            basis="high_confidence_observed_asking_prices",
        )
    return _range_values(basis="range_not_available_unknown_confidence")


def _range_values(*, low: str = "", mid: str = "", high: str = "", basis: str) -> dict[str, str]:
    return {
        "likely_low": low,
        "likely_mid": mid,
        "likely_high": high,
        "market_range_basis": basis,
    }


def _evidence_status(listings: list[Mapping[str, str]], status_rows: list[Mapping[str, str]]) -> str:
    if listings:
        return "observed_listings"
    statuses = {_first(row, "lookup_status").casefold() for row in status_rows}
    if "source_unavailable" in statuses:
        return "source_unavailable"
    if "no_query" in statuses:
        return "no_query"
    return "no_market_evidence"


def _first(row: Mapping[str, str], *names: str) -> str:
    return next((str(row.get(name, "")).strip() for name in names if str(row.get(name, "")).strip()), "")


def _first_across(rows: list[Mapping[str, str]], *names: str) -> str:
    return next((value for row in rows if (value := _first(row, *names))), "")


def _stable_values(rows: list[Mapping[str, str]], *names: str) -> list[str]:
    return sorted({_first(row, *names) for row in rows if _first(row, *names)}, key=str.casefold)


def _decimal(value: str) -> Decimal | None:
    try:
        number = Decimal(value.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None
    return number if number.is_finite() and number >= 0 else None


def _integer(value: str) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _format_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
