"""Reusable, source-specific eBay active-listing search client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import time
from typing import Any

from valuation.ebay_access import EbayAccessClient, EbayAccessError, EbayRequestError


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


@dataclass(frozen=True)
class EbayApplicationToken:
    value: str = field(repr=False)
    acquired_at: float
    expires_in: float
    refresh_at: float
    generation: int


class EbayBrowseSession:
    """Reuse one in-memory application token and refresh it safely."""

    def __init__(
        self,
        access_client: EbayAccessClient,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        refresh_margin_seconds: float = 300.0,
    ) -> None:
        if refresh_margin_seconds < 0:
            raise ValueError("refresh_margin_seconds must be nonnegative")
        self.access_client = access_client
        self.monotonic = monotonic
        self.refresh_margin_seconds = refresh_margin_seconds
        self.token: EbayApplicationToken | None = None
        self.token_acquisition_count = 0
        self.token_refresh_count = 0
        self.browse_request_count = 0

    def search_active_listings(self, query: str, limit: int) -> dict[str, Any]:
        token = self.current_token()
        self.browse_request_count += 1
        try:
            return self.access_client.search_active_listings(query, limit, token.value)
        except EbayRequestError as error:
            if error.operation == "active-listing search" and error.status_code == 401:
                token = self.refresh_token()
                self.browse_request_count += 1
                try:
                    return self.access_client.search_active_listings(query, limit, token.value)
                except EbayRequestError as repeated:
                    if repeated.status_code in {401, 403}:
                        raise EbayRequestError(
                            "eBay active-listing authentication failed after one token refresh",
                            operation="active-listing search",
                            status_code=repeated.status_code,
                            failure_kind="bearer_rejected_after_refresh",
                        ) from None
                    raise
            raise

    def current_token(self) -> EbayApplicationToken:
        now = self.monotonic()
        if self.token is None:
            return self._acquire(now, refresh=False)
        if now >= self.token.refresh_at:
            return self._acquire(now, refresh=True)
        return self.token

    def refresh_token(self) -> EbayApplicationToken:
        return self._acquire(self.monotonic(), refresh=self.token is not None)

    def _acquire(self, now: float, *, refresh: bool) -> EbayApplicationToken:
        value, expires_in = self.access_client.acquire_application_token_details()
        self.token_acquisition_count += 1
        if refresh:
            self.token_refresh_count += 1
        generation = 1 if self.token is None else self.token.generation + 1
        refresh_at = now + max(0.0, expires_in - self.refresh_margin_seconds)
        self.token = EbayApplicationToken(value, now, expires_in, refresh_at, generation)
        return self.token


class EbayActiveListingsClient:
    """Acquire an application token and normalize one bounded Browse search."""

    def __init__(
        self, access_client: EbayAccessClient, *, session: EbayBrowseSession | None = None
    ) -> None:
        self.access_client = access_client
        self.session = session

    def search(self, query: str, limit: int = 10) -> EbayActiveListingSearchResult:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise EbayAccessError("eBay active-listings query must not be blank")
        if limit < 1 or limit > MAX_SEARCH_LIMIT:
            raise EbayAccessError(f"eBay active-listings limit must be between 1 and {MAX_SEARCH_LIMIT}")

        if self.session is None:
            token = self.access_client.acquire_application_token()
            payload = self.access_client.search_active_listings(normalized_query, limit, token)
        else:
            payload = self.session.search_active_listings(normalized_query, limit)
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
