"""Reusable, source-specific eBay active-listing search client."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from valuation.ebay_access import EbayAccessClient, EbayAccessError


RAW_SOURCE = "ebay_active_listing"
MAX_SEARCH_LIMIT = 50


@dataclass(frozen=True)
class EbayActiveListing:
    """Provisional normalized result from one eBay Browse item summary."""

    item_id: str
    title: str
    price_value: str
    price_currency: str
    item_web_url: str
    condition: str
    seller_username: str
    buying_options: tuple[str, ...]
    item_location_country: str
    raw_source: str
    query: str
    marketplace_id: str


@dataclass(frozen=True)
class EbayActiveListingSearchResult:
    """Safe in-memory result for one bounded direct-query search."""

    query: str
    marketplace_id: str
    total: int
    listings: tuple[EbayActiveListing, ...]


class EbayActiveListingsClient:
    """Acquire an application token and normalize one bounded Browse search."""

    def __init__(self, access_client: EbayAccessClient) -> None:
        self.access_client = access_client

    def search(self, query: str, limit: int = 10) -> EbayActiveListingSearchResult:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise EbayAccessError("eBay active-listings query must not be blank")
        if limit < 1 or limit > MAX_SEARCH_LIMIT:
            raise EbayAccessError(f"eBay active-listings limit must be between 1 and {MAX_SEARCH_LIMIT}")

        token = self.access_client.acquire_application_token()
        payload = self.access_client.search_active_listings(normalized_query, limit, token)
        raw_items = payload.get("itemSummaries", [])
        if not isinstance(raw_items, list):
            raise EbayAccessError("eBay search response contained an invalid item summary list")
        listings = tuple(
            normalize_active_listing(item, normalized_query, self.access_client.credentials.marketplace_id)
            for item in raw_items[:limit]
            if isinstance(item, Mapping)
        )
        return EbayActiveListingSearchResult(
            query=normalized_query,
            marketplace_id=self.access_client.credentials.marketplace_id,
            total=safe_integer(payload.get("total"), len(raw_items)),
            listings=listings,
        )


def normalize_active_listing(
    item: Mapping[str, Any], query: str, marketplace_id: str
) -> EbayActiveListing:
    """Normalize permitted item-summary fields without retaining a raw payload."""
    price = item.get("price")
    if not isinstance(price, Mapping):
        price = {}
    seller = item.get("seller")
    if not isinstance(seller, Mapping):
        seller = {}
    location = item.get("itemLocation")
    if not isinstance(location, Mapping):
        location = {}
    raw_options = item.get("buyingOptions")
    if not isinstance(raw_options, list):
        raw_options = []
    return EbayActiveListing(
        item_id=safe_text(item.get("itemId")),
        title=safe_text(item.get("title")),
        price_value=safe_text(price.get("value")),
        price_currency=safe_text(price.get("currency")),
        item_web_url=safe_text(item.get("itemWebUrl")),
        condition=safe_text(item.get("condition")),
        seller_username=safe_text(seller.get("username")),
        buying_options=tuple(safe_text(option) for option in raw_options if safe_text(option)),
        item_location_country=safe_text(location.get("country")),
        raw_source=RAW_SOURCE,
        query=query,
        marketplace_id=marketplace_id,
    )


def safe_text(value: object) -> str:
    if value is None or isinstance(value, (dict, list, tuple)):
        return ""
    return " ".join(str(value).split())


def safe_integer(value: object, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
