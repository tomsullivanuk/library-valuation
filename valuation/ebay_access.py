"""Bounded eBay credential and active-listing access check."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


APPLICATION_SCOPE = "https://api.ebay.com/oauth/api_scope"
ENVIRONMENT_HOSTS = {
    "production": ("https://api.ebay.com", "https://api.ebay.com/identity/v1/oauth2/token"),
    "sandbox": ("https://api.sandbox.ebay.com", "https://api.sandbox.ebay.com/identity/v1/oauth2/token"),
}
RequestJson = Callable[[urllib.request.Request, float], dict[str, Any]]


class EbayAccessError(ValueError):
    """Safe, user-facing eBay access failure."""


class EbayRequestError(EbayAccessError):
    """Sanitized request failure with safe structured retry/auth metadata."""

    def __init__(
        self,
        message: str,
        *,
        operation: str = "request",
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        failure_kind: str = "request",
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.failure_kind = failure_kind


@dataclass(frozen=True)
class EbayCredentials:
    client_id: str
    client_secret: str
    marketplace_id: str
    environment: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "EbayCredentials":
        values = os.environ if environ is None else environ
        required = ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET", "EBAY_MARKETPLACE_ID", "EBAY_ENVIRONMENT")
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            raise EbayAccessError(f"Missing required eBay environment variables: {', '.join(missing)}")
        environment = values["EBAY_ENVIRONMENT"].strip().lower()
        if environment not in ENVIRONMENT_HOSTS:
            raise EbayAccessError("EBAY_ENVIRONMENT must be 'sandbox' or 'production'")
        marketplace = values["EBAY_MARKETPLACE_ID"].strip().upper()
        if not re.fullmatch(r"EBAY_[A-Z]{2,5}", marketplace):
            raise EbayAccessError("EBAY_MARKETPLACE_ID must use an eBay marketplace value such as EBAY_US")
        return cls(
            client_id=values["EBAY_CLIENT_ID"].strip(),
            client_secret=values["EBAY_CLIENT_SECRET"].strip(),
            marketplace_id=marketplace,
            environment=environment,
        )

    def redact(self, value: object, *additional_secrets: str) -> str:
        text = str(value)
        for secret in (self.client_id, self.client_secret, *additional_secrets):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
        text = re.sub(r"(?i)Basic\s+[A-Za-z0-9+/=]+", "Basic [REDACTED]", text)
        return text


@dataclass(frozen=True)
class SafeListingSummary:
    title: str
    price: str
    currency: str


@dataclass(frozen=True)
class EbayAccessCheckResult:
    environment: str
    marketplace_id: str
    token_acquired: bool
    request_succeeded: bool
    result_count: int
    listings: tuple[SafeListingSummary, ...]


class EbayAccessClient:
    """Minimal client used only to verify authentication and one search."""

    def __init__(
        self,
        credentials: EbayCredentials,
        *,
        request_json: RequestJson | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.credentials = credentials
        self.request_json = request_json or default_request_json
        self.timeout = timeout

    def acquire_application_token(self) -> str:
        token, _expires_in = self.acquire_application_token_details()
        return token

    def acquire_application_token_details(self) -> tuple[str, float]:
        _api_host, token_url = ENVIRONMENT_HOSTS[self.credentials.environment]
        basic = base64.b64encode(
            f"{self.credentials.client_id}:{self.credentials.client_secret}".encode("utf-8")
        ).decode("ascii")
        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": APPLICATION_SCOPE}
        ).encode("ascii")
        request = urllib.request.Request(
            token_url,
            data=body,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        payload = self._safe_request(request, "token request")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise EbayAccessError("eBay token response did not include an access token")
        try:
            expires_in = float(payload.get("expires_in", 7200))
        except (TypeError, ValueError):
            expires_in = 7200.0
        if expires_in <= 0:
            raise EbayAccessError("eBay token response contained an invalid expiration")
        return token, expires_in

    def search_active_listings(self, query: str, limit: int, access_token: str) -> dict[str, Any]:
        api_host, _token_url = ENVIRONMENT_HOSTS[self.credentials.environment]
        parameters = urllib.parse.urlencode({"q": query, "limit": str(limit)})
        request = urllib.request.Request(
            f"{api_host}/buy/browse/v1/item_summary/search?{parameters}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-EBAY-C-MARKETPLACE-ID": self.credentials.marketplace_id,
                "Accept": "application/json",
            },
            method="GET",
        )
        return self._safe_request(request, "active-listing search", access_token)

    def check_access(self, query: str, limit: int) -> EbayAccessCheckResult:
        query = query.strip()
        if not query:
            raise EbayAccessError("eBay access-check query must not be blank")
        if limit < 1 or limit > 3:
            raise EbayAccessError("eBay access-check limit must be between 1 and 3")
        token = self.acquire_application_token()
        payload = self.search_active_listings(query, limit, token)
        raw_items = payload.get("itemSummaries", [])
        if not isinstance(raw_items, list):
            raise EbayAccessError("eBay search response contained an invalid item summary list")
        listings = tuple(safe_listing_summary(item) for item in raw_items[:limit] if isinstance(item, dict))
        raw_total = payload.get("total", len(raw_items))
        try:
            result_count = int(raw_total)
        except (TypeError, ValueError):
            result_count = len(raw_items)
        return EbayAccessCheckResult(
            environment=self.credentials.environment,
            marketplace_id=self.credentials.marketplace_id,
            token_acquired=True,
            request_succeeded=True,
            result_count=result_count,
            listings=listings,
        )

    def _safe_request(self, request: urllib.request.Request, operation: str, *secrets: str) -> dict[str, Any]:
        try:
            return self.request_json(request, self.timeout)
        except EbayRequestError as error:
            safe_detail = self.credentials.redact(error, *secrets)
            raise EbayRequestError(
                f"eBay {operation} failed: {safe_detail}",
                operation=operation,
                status_code=error.status_code,
                retry_after_seconds=error.retry_after_seconds,
                failure_kind=error.failure_kind,
            ) from None
        except EbayAccessError:
            raise
        except Exception as error:
            safe_detail = self.credentials.redact(error, *secrets)
            raise EbayRequestError(
                f"eBay {operation} failed: {safe_detail}", operation=operation
            ) from None


def default_request_json(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        retry_after = parse_retry_after(error.headers.get("Retry-After") if error.headers else None)
        raise EbayRequestError(
            f"HTTP {error.code}: {clean_snippet(error.reason, 120) or 'request failed'}",
            status_code=error.code,
            retry_after_seconds=retry_after,
            failure_kind="http",
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise EbayRequestError(
            clean_snippet(error.reason if isinstance(error, urllib.error.URLError) else error, 200),
            failure_kind="network",
        ) from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid JSON response: {error}") from None
    if not isinstance(payload, dict):
        raise RuntimeError("JSON response was not an object")
    return payload


def safe_listing_summary(item: Mapping[str, Any]) -> SafeListingSummary:
    price = item.get("price", {})
    if not isinstance(price, Mapping):
        price = {}
    return SafeListingSummary(
        title=clean_snippet(item.get("title", ""), 120) or "(untitled listing)",
        price=clean_snippet(price.get("value", ""), 30),
        currency=clean_snippet(price.get("currency", ""), 10),
    )


def clean_snippet(value: object, limit: int) -> str:
    return " ".join(str(value).split())[:limit]


def parse_retry_after(value: object) -> float | None:
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None
