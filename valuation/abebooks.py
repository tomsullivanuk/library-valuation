"""Experimental AbeBooks market observation collection."""

from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from html.parser import HTMLParser


SOURCE = "abebooks"
ABBOOKS_SEARCH_URL = "https://www.abebooks.com/servlet/SearchResults"

MARKET_OBSERVATION_FIELDNAMES = [
    "observation_id",
    "catalog_id",
    "title",
    "author",
    "isbn10",
    "isbn13",
    "research_score",
    "score_band",
    "source",
    "lookup_status",
    "observation_date",
    "lookup_strategy",
    "search_query",
    "result_rank",
    "asking_price",
    "currency",
    "condition",
    "seller",
    "listing_title",
    "listing_author",
    "listing_url",
    "match_confidence",
    "match_notes",
    "raw_reference",
]

FetchHtml = Callable[[str], str]


class SourceUnavailable(RuntimeError):
    """Raised when a market source cannot be reached or parsed usefully."""


def collect_abebooks_observation_rows(
    sample_rows: Iterable[Mapping[str, str]],
    *,
    fetch_html: FetchHtml,
    observation_date: str,
    limit: int = 30,
    max_results_per_book: int = 3,
    delay_seconds: float = 1.0,
    sleep: Callable[[float], None] | None = None,
) -> list[dict[str, str]]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if max_results_per_book < 1:
        raise ValueError("max_results_per_book must be at least 1")

    selected_samples = list(sample_rows)[:limit]
    rows = []
    sleeper = sleep or (lambda _seconds: None)
    for index, sample in enumerate(selected_samples):
        rows.extend(
            collect_observations_for_sample(
                sample,
                fetch_html=fetch_html,
                observation_date=observation_date,
                max_results_per_book=max_results_per_book,
            )
        )
        if delay_seconds > 0 and index < len(selected_samples) - 1:
            sleeper(delay_seconds)
    return rows


def collect_observations_for_sample(
    sample: Mapping[str, str],
    *,
    fetch_html: FetchHtml,
    observation_date: str,
    max_results_per_book: int,
) -> list[dict[str, str]]:
    attempts = lookup_attempts(sample)
    if not attempts:
        return [
            status_observation_row(
                sample,
                observation_date=observation_date,
                lookup_status="no_query",
                lookup_strategy="none",
                search_query="",
                match_notes="No ISBN, title, or author available for lookup.",
            )
        ]

    last_attempt = attempts[-1]
    last_error = ""
    for attempt in attempts:
        try:
            document = fetch_html(attempt["url"])
        except SourceUnavailable as error:
            return [
                status_observation_row(
                    sample,
                    observation_date=observation_date,
                    lookup_status="source_unavailable",
                    lookup_strategy=attempt["strategy"],
                    search_query=attempt["query"],
                    match_notes=str(error),
                    raw_reference=attempt["url"],
                )
            ]
        try:
            listings = parse_abebooks_listings(document)
        except SourceUnavailable as error:
            return [
                status_observation_row(
                    sample,
                    observation_date=observation_date,
                    lookup_status="source_unavailable",
                    lookup_strategy=attempt["strategy"],
                    search_query=attempt["query"],
                    match_notes=str(error),
                    raw_reference=attempt["url"],
                )
            ]
        if listings:
            return [
                listing_observation_row(
                    sample,
                    listing,
                    observation_date=observation_date,
                    lookup_strategy=attempt["strategy"],
                    search_query=attempt["query"],
                    result_rank=rank,
                )
                for rank, listing in enumerate(listings[:max_results_per_book], start=1)
            ]
        last_error = "No parsed listing results."

    return [
        status_observation_row(
            sample,
            observation_date=observation_date,
            lookup_status="no_results",
            lookup_strategy=last_attempt["strategy"],
            search_query=last_attempt["query"],
            match_notes=last_error,
            raw_reference=last_attempt["url"],
        )
    ]


def lookup_attempts(sample: Mapping[str, str]) -> list[dict[str, str]]:
    attempts = []
    isbn13 = sample.get("isbn13", "").strip()
    isbn10 = sample.get("isbn10", "").strip()
    title = sample.get("title", "").strip()
    author = sample.get("author", "").strip()
    if isbn13:
        attempts.append(lookup_attempt("isbn13", isbn13))
    if isbn10 and isbn10 != isbn13:
        attempts.append(lookup_attempt("isbn10", isbn10))
    if title or author:
        query = " ".join(part for part in (title, author) if part)
        attempts.append(lookup_attempt("title_author", query, title=title, author=author))
    return attempts


def lookup_attempt(strategy: str, query: str, title: str = "", author: str = "") -> dict[str, str]:
    if strategy in {"isbn13", "isbn10"}:
        params = {"isbn": query}
    else:
        params = {"tn": title, "an": author}
    return {
        "strategy": strategy,
        "query": query,
        "url": f"{ABBOOKS_SEARCH_URL}?{urllib.parse.urlencode(params)}",
    }


def fetch_url(url: str, timeout: float = 20.0) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LibraryValuation/0.4.0 market-observation-spike",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                raise SourceUnavailable(f"Unexpected content type from AbeBooks: {content_type}")
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        raise SourceUnavailable(f"AbeBooks HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SourceUnavailable(f"AbeBooks request failed: {error}") from error


def parse_abebooks_listings(document: str) -> list[dict[str, str]]:
    parser = AbeBooksSearchParser()
    parser.feed(document)
    listings = parser.listings
    if listings:
        return listings
    if looks_blocked_or_unavailable(document):
        raise SourceUnavailable("AbeBooks returned a blocked or unavailable page.")
    return []


def looks_blocked_or_unavailable(document: str) -> bool:
    lowered = document.lower()
    blocked_markers = (
        "access denied",
        "captcha",
        "robot check",
        "temporarily unavailable",
        "unusual traffic",
    )
    return any(marker in lowered for marker in blocked_markers)


class AbeBooksSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.listings: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._field = ""
        self._link_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): value or "" for name, value in attrs}
        classes = attributes.get("class", "").lower()
        itemtype = attributes.get("itemtype", "").lower()
        if tag in {"div", "li", "article"} and (
            "result-item" in classes
            or "cf result" in classes
            or "search-result" in classes
            or "listresult" in classes
            or "book" in itemtype
        ):
            self._finish_current()
            self._current = {}
            self._field = ""
            return
        if self._current is None:
            return
        if tag == "a" and ("title" in classes or "BookDetails" in attributes.get("href", "")):
            self._field = "listing_title"
            self._link_href = attributes.get("href", "")
            if self._link_href:
                self._current["listing_url"] = absolute_abebooks_url(self._link_href)
            return
        if "author" in classes:
            self._field = "listing_author"
        elif "price" in classes:
            self._field = "asking_price"
        elif "condition" in classes:
            self._field = "condition"
        elif "seller" in classes or "bookseller" in classes:
            self._field = "seller"

    def handle_endtag(self, tag: str) -> None:
        if tag in {"div", "li", "article"}:
            self._finish_current()
        self._field = ""

    def handle_data(self, data: str) -> None:
        if self._current is None or not self._field:
            return
        value = clean_text(data)
        if not value:
            return
        existing = self._current.get(self._field, "")
        self._current[self._field] = clean_text(f"{existing} {value}" if existing else value)

    def _finish_current(self) -> None:
        if self._current and (self._current.get("listing_title") or self._current.get("listing_url")):
            self.listings.append(normalize_listing(self._current))
        self._current = None
        self._field = ""


def normalize_listing(listing: Mapping[str, str]) -> dict[str, str]:
    price, currency = parse_price(listing.get("asking_price", ""))
    return {
        "asking_price": price,
        "currency": currency,
        "condition": strip_label(listing.get("condition", ""), "condition"),
        "seller": strip_label(listing.get("seller", ""), "seller"),
        "listing_title": listing.get("listing_title", ""),
        "listing_author": strip_label(listing.get("listing_author", ""), "author"),
        "listing_url": listing.get("listing_url", ""),
    }


def listing_observation_row(
    sample: Mapping[str, str],
    listing: Mapping[str, str],
    *,
    observation_date: str,
    lookup_strategy: str,
    search_query: str,
    result_rank: int,
) -> dict[str, str]:
    confidence, notes = match_confidence(sample, listing, lookup_strategy)
    raw_reference = listing.get("listing_url", "")
    return base_observation_row(sample, observation_date=observation_date) | {
        "observation_id": observation_id(sample, lookup_strategy, str(result_rank), raw_reference),
        "lookup_status": "observed",
        "lookup_strategy": lookup_strategy,
        "search_query": search_query,
        "result_rank": str(result_rank),
        "asking_price": listing.get("asking_price", ""),
        "currency": listing.get("currency", ""),
        "condition": listing.get("condition", ""),
        "seller": listing.get("seller", ""),
        "listing_title": listing.get("listing_title", ""),
        "listing_author": listing.get("listing_author", ""),
        "listing_url": listing.get("listing_url", ""),
        "match_confidence": confidence,
        "match_notes": notes,
        "raw_reference": raw_reference,
    }


def status_observation_row(
    sample: Mapping[str, str],
    *,
    observation_date: str,
    lookup_status: str,
    lookup_strategy: str,
    search_query: str,
    match_notes: str,
    raw_reference: str = "",
) -> dict[str, str]:
    return base_observation_row(sample, observation_date=observation_date) | {
        "observation_id": observation_id(sample, lookup_strategy, lookup_status, raw_reference),
        "lookup_status": lookup_status,
        "lookup_strategy": lookup_strategy,
        "search_query": search_query,
        "result_rank": "",
        "asking_price": "",
        "currency": "",
        "condition": "",
        "seller": "",
        "listing_title": "",
        "listing_author": "",
        "listing_url": "",
        "match_confidence": "unknown",
        "match_notes": match_notes,
        "raw_reference": raw_reference,
    }


def base_observation_row(sample: Mapping[str, str], *, observation_date: str) -> dict[str, str]:
    return {
        "observation_id": "",
        "catalog_id": sample.get("catalog_id", "") or sample.get("catalog_item_id", ""),
        "title": sample.get("title", ""),
        "author": sample.get("author", "") or sample.get("authors", ""),
        "isbn10": sample.get("isbn10", ""),
        "isbn13": sample.get("isbn13", ""),
        "research_score": sample.get("research_score", ""),
        "score_band": sample.get("score_band", ""),
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
        "match_notes": "",
        "raw_reference": "",
    }


def match_confidence(sample: Mapping[str, str], listing: Mapping[str, str], lookup_strategy: str) -> tuple[str, str]:
    if lookup_strategy in {"isbn13", "isbn10"}:
        return "high", f"Matched by {lookup_strategy} lookup."
    title_score = token_overlap(sample.get("title", ""), listing.get("listing_title", ""))
    author_score = token_overlap(sample.get("author", ""), listing.get("listing_author", ""))
    if title_score >= 0.75 and author_score >= 0.5:
        return "medium", "Title and author are similar."
    if title_score >= 0.5:
        return "low", "Title is partially similar; title/author fallback requires review."
    return "unknown", "Unable to establish a lightweight title/author match."


def token_overlap(left: str, right: str) -> float:
    left_tokens = meaningful_tokens(left)
    right_tokens = meaningful_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2 and token not in {"the", "and", "for", "with"}
    }


def parse_price(value: str) -> tuple[str, str]:
    value = clean_text(value)
    match = re.search(r"(?P<symbol>[$£€])\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{2})?)", value)
    if not match:
        return "", ""
    currency = {"$": "USD", "£": "GBP", "€": "EUR"}.get(match.group("symbol"), "")
    return match.group("amount").replace(",", ""), currency


def strip_label(value: str, label: str) -> str:
    return re.sub(rf"^{re.escape(label)}\s*:\s*", "", clean_text(value), flags=re.IGNORECASE)


def clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


def absolute_abebooks_url(url: str) -> str:
    return urllib.parse.urljoin("https://www.abebooks.com", url)


def observation_id(sample: Mapping[str, str], lookup_strategy: str, rank_or_status: str, raw_reference: str) -> str:
    catalog_id = sample.get("catalog_id", "") or sample.get("catalog_item_id", "")
    payload = "\x1f".join([SOURCE, catalog_id, lookup_strategy, rank_or_status, raw_reference])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()
    return f"MOB-{digest}"
