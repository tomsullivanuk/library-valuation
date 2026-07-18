"""Bounded candidate selection and collection for eBay active listings."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Mapping

from valuation.ebay_access import EbayAccessError
from valuation.ebay_active_listings import EbayActiveListingsClient
from valuation.ebay_observations import (
    adapt_ebay_search_result,
    ebay_source_unavailable_row,
    ebay_status_observation_row,
)


DEFAULT_REVIEW_RECOMMENDATIONS = ("review_for_possible_sale",)
SUPPORTED_REVIEW_RECOMMENDATIONS = (
    "review_for_possible_sale",
    "manual_market_research_needed",
    "review_edition_or_condition",
)
REVIEW_PRIORITY = {value: index for index, value in enumerate(SUPPORTED_REVIEW_RECOMMENDATIONS)}
MAX_TARGETED_BOOKS = 50
MAX_RESULTS_PER_BOOK = 10


def select_targeted_candidates(
    summary_rows: Iterable[Mapping[str, str]],
    *,
    review_recommendations: Iterable[str] = DEFAULT_REVIEW_RECOMMENDATIONS,
    limit_books: int,
) -> list[dict[str, str]]:
    """Select a deterministic, explicitly bounded reviewer-priority cohort."""
    validate_collection_limits(limit_books, 1, 0)
    selected_recommendations = tuple(dict.fromkeys(review_recommendations))
    unsupported = set(selected_recommendations) - set(SUPPORTED_REVIEW_RECOMMENDATIONS)
    if unsupported:
        raise ValueError(f"Unsupported review recommendation: {sorted(unsupported)[0]}")
    candidates = [
        dict(row)
        for row in summary_rows
        if row.get("review_recommendation", "") in selected_recommendations
    ]
    return sorted(candidates, key=candidate_sort_key)[:limit_books]


def build_ebay_query(catalog: Mapping[str, str]) -> tuple[str, str]:
    """Build one conservative catalog-derived query and its strategy."""
    isbn13 = normalized_isbn(catalog.get("isbn_13") or catalog.get("isbn13"), 13)
    if isbn13:
        return "isbn13", isbn13
    isbn10 = normalized_isbn(catalog.get("isbn_10") or catalog.get("isbn10"), 10)
    if isbn10:
        return "isbn10", isbn10
    title = clean_query_part(catalog.get("title", ""))
    author = clean_query_part(catalog.get("author") or catalog.get("authors", ""))
    if usable_title(title) and author:
        return "title_author", f"{title} {author}"
    if usable_title(title):
        return "title", title
    return "title", ""


def collect_targeted_ebay_observation_rows(
    summary_rows: Iterable[Mapping[str, str]],
    client: EbayActiveListingsClient,
    *,
    observation_date: str,
    limit_books: int,
    max_results_per_book: int = 3,
    delay_seconds: float = 1.0,
    review_recommendations: Iterable[str] = DEFAULT_REVIEW_RECOMMENDATIONS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, str]]:
    """Collect one bounded cohort; stop after the first safe client failure."""
    validate_collection_limits(limit_books, max_results_per_book, delay_seconds)
    candidates = select_targeted_candidates(
        summary_rows,
        review_recommendations=review_recommendations,
        limit_books=limit_books,
    )
    rows: list[dict[str, str]] = []
    request_count = 0
    for candidate in candidates:
        strategy, query = build_ebay_query(candidate)
        if not query:
            rows.append(
                ebay_status_observation_row(
                    candidate,
                    observation_date=observation_date,
                    lookup_status="no_query",
                    lookup_strategy=strategy,
                    search_query="",
                    diagnostic_code="no_query",
                    match_notes="No safe eBay query could be constructed from catalog metadata.",
                )
            )
            continue
        if request_count and delay_seconds:
            sleep(delay_seconds)
        request_count += 1
        try:
            result = client.search(query, max_results_per_book)
        except EbayAccessError as error:
            rows.append(
                ebay_source_unavailable_row(
                    candidate,
                    observation_date=observation_date,
                    lookup_strategy=strategy,
                    search_query=query,
                    safe_reason=str(error),
                )
            )
            break
        rows.extend(
            adapt_ebay_search_result(
                candidate,
                result,
                observation_date=observation_date,
                lookup_strategy=strategy,
            )
        )
    return rows


def validate_collection_limits(limit_books: int, max_results_per_book: int, delay_seconds: float) -> None:
    if limit_books < 1 or limit_books > MAX_TARGETED_BOOKS:
        raise ValueError(f"limit-books must be between 1 and {MAX_TARGETED_BOOKS}")
    if max_results_per_book < 1 or max_results_per_book > MAX_RESULTS_PER_BOOK:
        raise ValueError(f"max-results-per-book must be between 1 and {MAX_RESULTS_PER_BOOK}")
    if delay_seconds < 0:
        raise ValueError("delay must be zero or greater")


def candidate_sort_key(row: Mapping[str, str]) -> tuple[int, float, float, float, str, str]:
    return (
        REVIEW_PRIORITY.get(row.get("review_recommendation", ""), 99),
        -number_value(row.get("likely_mid", "")),
        -number_value(row.get("likely_high", "")),
        -number_value(row.get("research_score", "")),
        row.get("title", "").casefold(),
        row.get("catalog_item_id", ""),
    )


def normalized_isbn(value: object, length: int) -> str:
    cleaned = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return cleaned if len(cleaned) == length and (length != 13 or cleaned.isdigit()) else ""


def clean_query_part(value: object) -> str:
    return " ".join(str(value or "").split())[:240]


def usable_title(value: str) -> bool:
    return len(value) >= 3 and bool(re.search(r"[A-Za-z0-9]", value))


def number_value(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return float("-inf")
