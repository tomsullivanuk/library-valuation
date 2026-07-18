"""Pure adapter from eBay active-listing results to market observation rows."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from valuation.abebooks import MARKET_OBSERVATION_FIELDNAMES
from valuation.ebay_active_listings import EbayActiveListing, EbayActiveListingSearchResult


SOURCE = "ebay_active_listings"
SUPPORTED_LOOKUP_STRATEGIES = {"isbn13", "isbn10", "title_author", "title", "direct_query"}


def adapt_ebay_search_result(
    catalog: Mapping[str, str],
    search_result: EbayActiveListingSearchResult,
    *,
    observation_date: str,
    lookup_strategy: str = "direct_query",
) -> list[dict[str, str]]:
    """Convert one in-memory search result into canonical observation-shaped rows."""
    strategy = validate_lookup_strategy(lookup_strategy)
    query = clean_text(search_result.query)
    if not query:
        return [
            ebay_status_observation_row(
                catalog,
                observation_date=observation_date,
                lookup_status="no_query",
                lookup_strategy=strategy,
                search_query="",
                diagnostic_code="no_query",
                match_notes="No safe eBay query was provided.",
            )
        ]
    if not search_result.listings:
        return [
            ebay_status_observation_row(
                catalog,
                observation_date=observation_date,
                lookup_status="no_results",
                lookup_strategy=strategy,
                search_query=query,
                diagnostic_code="no_results",
                match_notes=f"eBay active-listing search returned no results for {search_result.marketplace_id}.",
            )
        ]
    return [
        ebay_listing_observation_row(
            catalog,
            listing,
            observation_date=observation_date,
            lookup_strategy=strategy,
            search_query=query,
            result_rank=rank,
        )
        for rank, listing in enumerate(search_result.listings, start=1)
    ]


def ebay_source_unavailable_row(
    catalog: Mapping[str, str],
    *,
    observation_date: str,
    lookup_strategy: str,
    search_query: str,
    safe_reason: str,
    diagnostic_code: str = "source_unavailable",
) -> dict[str, str]:
    """Build a status row from a caller-supplied, already-safe failure reason."""
    strategy = validate_lookup_strategy(lookup_strategy)
    return ebay_status_observation_row(
        catalog,
        observation_date=observation_date,
        lookup_status="source_unavailable",
        lookup_strategy=strategy,
        search_query=clean_text(search_query),
        diagnostic_code=clean_code(diagnostic_code) or "source_unavailable",
        match_notes=sanitize_failure_reason(safe_reason),
    )


def ebay_listing_observation_row(
    catalog: Mapping[str, str],
    listing: EbayActiveListing,
    *,
    observation_date: str,
    lookup_strategy: str,
    search_query: str,
    result_rank: int,
) -> dict[str, str]:
    notes = ebay_listing_notes(listing)
    row = ebay_base_observation_row(catalog, observation_date=observation_date)
    row.update(
        {
            "observation_id": ebay_observation_id(
                catalog, lookup_strategy, str(result_rank), listing.item_id or listing.item_web_url
            ),
            "lookup_status": "observed",
            "lookup_strategy": lookup_strategy,
            "search_query": search_query,
            "result_rank": str(result_rank),
            "asking_price": listing.price_value,
            "currency": listing.price_currency,
            "condition": listing.condition,
            "seller": "",
            "listing_title": listing.title,
            "listing_author": "",
            "listing_url": listing.item_web_url,
            "match_confidence": "unknown",
            "diagnostic_code": "",
            "match_notes": notes,
            "raw_reference": listing.item_id,
        }
    )
    return ordered_observation_row(row)


def ebay_status_observation_row(
    catalog: Mapping[str, str],
    *,
    observation_date: str,
    lookup_status: str,
    lookup_strategy: str,
    search_query: str,
    diagnostic_code: str,
    match_notes: str,
) -> dict[str, str]:
    row = ebay_base_observation_row(catalog, observation_date=observation_date)
    row.update(
        {
            "observation_id": ebay_observation_id(
                catalog, lookup_strategy, lookup_status, search_query
            ),
            "lookup_status": lookup_status,
            "lookup_strategy": lookup_strategy,
            "search_query": search_query,
            "match_confidence": "unknown",
            "diagnostic_code": diagnostic_code,
            "match_notes": match_notes,
        }
    )
    return ordered_observation_row(row)


def ebay_base_observation_row(
    catalog: Mapping[str, str], *, observation_date: str
) -> dict[str, str]:
    return {
        "observation_id": "",
        "catalog_id": first(catalog, "catalog_id", "catalog_item_id"),
        "title": first(catalog, "title"),
        "author": first(catalog, "author", "authors"),
        "isbn10": first(catalog, "isbn10", "isbn_10"),
        "isbn13": first(catalog, "isbn13", "isbn_13"),
        "research_score": first(catalog, "research_score"),
        "score_band": first(catalog, "score_band", "research_band"),
        "source": SOURCE,
        "lookup_status": "",
        "observation_date": observation_date,
        "lookup_strategy": "",
        "search_query": "",
        "result_rank": "",
        "asking_price": "",
        "currency": "",
        "condition": "",
        "seller": "",
        "listing_title": "",
        "listing_author": "",
        "listing_url": "",
        "match_confidence": "",
        "diagnostic_code": "",
        "match_notes": "",
        "raw_reference": "",
    }


def ebay_listing_notes(listing: EbayActiveListing) -> str:
    details = [
        f"item_id={listing.item_id}" if listing.item_id else "",
        f"buying_options={','.join(listing.buying_options)}" if listing.buying_options else "",
        f"marketplace_id={listing.marketplace_id}" if listing.marketplace_id else "",
        f"item_location_country={listing.item_location_country}" if listing.item_location_country else "",
        "item price only; shipping excluded",
    ]
    return "; ".join(detail for detail in details if detail)


def sanitize_failure_reason(reason: str) -> str:
    """Defense in depth; callers must still supply only redacted safe reasons."""
    text = clean_text(reason)[:500]
    text = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)Basic\s+[A-Za-z0-9+/=]+", "Basic [REDACTED]", text)
    text = re.sub(
        r"(?i)(access_token|refresh_token|client_secret|authorization)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )
    return text or "eBay source unavailable."


def ebay_observation_id(
    catalog: Mapping[str, str], lookup_strategy: str, rank_or_status: str, raw_reference: str
) -> str:
    payload = "\x1f".join(
        [SOURCE, first(catalog, "catalog_id", "catalog_item_id"), lookup_strategy, rank_or_status, raw_reference]
    )
    return f"MOB-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16].upper()}"


def ordered_observation_row(row: Mapping[str, str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in MARKET_OBSERVATION_FIELDNAMES}


def validate_lookup_strategy(value: str) -> str:
    strategy = clean_text(value)
    if strategy not in SUPPORTED_LOOKUP_STRATEGIES:
        raise ValueError(f"Unsupported eBay lookup strategy: {strategy or '(blank)'}")
    return strategy


def clean_code(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.casefold()).strip("_")


def clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def first(values: Mapping[str, str], *names: str) -> str:
    return next((values.get(name, "") for name in names if values.get(name, "")), "")
