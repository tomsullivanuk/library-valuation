import csv
import urllib.error
import urllib.request

import library_pipeline
import valuation.abebooks as abebooks
from library_pipeline import collect_abebooks_observations, collect_full_library_abebooks_observations, main
from valuation.abebooks import (
    MARKET_OBSERVATION_FIELDNAMES,
    SourceUnavailable,
    collect_abebooks_observation_rows,
    default_ssl_context,
    fetch_url,
    lookup_attempts,
    parse_abebooks_listings,
    source_error_diagnostic_code,
)


LISTING_HTML = """
<html>
  <body>
    <div class="cf result-item">
      <a class="title" href="/servlet/BookDetailsPL?bi=123">The Test Book</a>
      <script>var ignoredTitleText = "not part of the title";</script>
      <p class="author">Author: Ada Author</p>
      <p class="item-price">$12.50</p>
      <p class="condition">Condition: Very Good</p>
      <p class="seller">Seller: Example Books</p>
    </div>
  </body>
</html>
"""

CURRENT_ABEBOOKS_HTML = """
<html>
  <body>
    <ul data-test-id="srp-search-results-list">
      <li data-test-id="listing-item-32308890943" data-srp-item-role="listing">
        <meta itemprop="name" content="A Patriot&#39;s History of the United States" />
        <meta itemprop="author" content="Larry Schweikart; Michael Allen" />
        <meta itemprop="price" content="6.32" />
        <meta itemprop="priceCurrency" content="USD" />
        <meta itemprop="about" content="Paperback. Condition: Fair." />
        <a itemprop="url" href="/Patriots-History-United-States/32308890943/bd">
          A Patriot's History of the United States
        </a>
        <p data-test-id="seller-info">
          Seller:
          <a data-test-id="listing-seller-link" href="/Gulf-Coast-Books/65078731/sf">Gulf Coast Books</a>
        </p>
      </li>
    </ul>
  </body>
</html>
"""


def test_lookup_attempts_prefers_isbn13_then_isbn10_then_title_author():
    attempts = lookup_attempts(sample_row(isbn13="9780123456786", isbn10="0123456789"))

    assert [attempt["strategy"] for attempt in attempts] == ["isbn13", "isbn10", "title_author"]
    assert "isbn=9780123456786" in attempts[0]["url"]
    assert "isbn=0123456789" in attempts[1]["url"]
    assert "tn=The+Test+Book" in attempts[2]["url"]
    assert "an=Ada+Author" in attempts[2]["url"]


def test_parse_abebooks_listings_extracts_lightweight_listing_fields():
    listings = parse_abebooks_listings(LISTING_HTML)

    assert listings == [
        {
            "asking_price": "12.50",
            "currency": "USD",
            "condition": "Very Good",
            "seller": "Example Books",
            "listing_title": "The Test Book",
            "listing_author": "Ada Author",
            "listing_url": "https://www.abebooks.com/servlet/BookDetailsPL?bi=123",
        }
    ]


def test_parse_abebooks_listings_extracts_current_search_result_markup():
    listings = parse_abebooks_listings(CURRENT_ABEBOOKS_HTML)

    assert listings == [
        {
            "asking_price": "6.32",
            "currency": "USD",
            "condition": "Paperback. Condition: Fair.",
            "seller": "Gulf Coast Books",
            "listing_title": "A Patriot's History of the United States",
            "listing_author": "Larry Schweikart; Michael Allen",
            "listing_url": "https://www.abebooks.com/Patriots-History-United-States/32308890943/bd",
        }
    ]


def test_collect_abebooks_observation_rows_uses_isbn_cascade_until_results():
    requested_urls = []

    def fetch_html(url):
        requested_urls.append(url)
        if "isbn=0123456789" in url:
            return LISTING_HTML
        return "<html><body>No books found</body></html>"

    rows = collect_abebooks_observation_rows(
        [sample_row(isbn13="9780123456786", isbn10="0123456789")],
        fetch_html=fetch_html,
        observation_date="2026-07-09T00:00:00Z",
        limit=1,
        delay_seconds=0,
    )

    assert len(rows) == 1
    assert [url.split("?")[1] for url in requested_urls] == [
        "isbn=9780123456786",
        "isbn=0123456789",
    ]
    assert rows[0]["lookup_status"] == "observed"
    assert rows[0]["source"] == "abebooks"
    assert rows[0]["lookup_strategy"] == "isbn10"
    assert rows[0]["match_confidence"] == "high"
    assert rows[0]["asking_price"] == "12.50"


def test_collect_abebooks_observation_rows_writes_no_results_status_row():
    rows = collect_abebooks_observation_rows(
        [sample_row(isbn13="", isbn10="")],
        fetch_html=lambda _url: "<html><body>No results</body></html>",
        observation_date="2026-07-09T00:00:00Z",
        limit=1,
        delay_seconds=0,
    )

    assert len(rows) == 1
    assert rows[0]["lookup_status"] == "no_results"
    assert rows[0]["lookup_strategy"] == "title_author"
    assert rows[0]["match_confidence"] == "unknown"


def test_collect_abebooks_observation_rows_writes_source_unavailable_status_row():
    rows = collect_abebooks_observation_rows(
        [sample_row()],
        fetch_html=lambda _url: (_ for _ in ()).throw(SourceUnavailable("AbeBooks HTTP 403", "http_error")),
        observation_date="2026-07-09T00:00:00Z",
        limit=1,
        delay_seconds=0,
    )

    assert len(rows) == 1
    assert rows[0]["lookup_status"] == "source_unavailable"
    assert rows[0]["diagnostic_code"] == "http_error"
    assert rows[0]["match_notes"] == "AbeBooks HTTP 403"


def test_collect_abebooks_observations_writes_required_columns_without_value_fields(tmp_path):
    output_dir = tmp_path / "output"
    write_rows(output_dir / "market_validation_sample.csv", sample_fieldnames(), [sample_row()])

    count = collect_abebooks_observations(
        output_dir,
        limit=1,
        delay=0,
        fetch_html=lambda _url: LISTING_HTML,
        observation_date="2026-07-09T00:00:00Z",
        sleep=lambda _seconds: None,
    )

    observations_path = output_dir / "market_observations.csv"
    assert count == 1
    assert observations_path.exists()
    assert (output_dir / "market_observations.xlsx").exists()
    with observations_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MARKET_OBSERVATION_FIELDNAMES
        rows = list(reader)
    assert rows[0]["catalog_id"] == "BK000001"
    assert rows[0]["source"] == "abebooks"
    assert rows[0]["lookup_status"] == "observed"
    assert rows[0]["observation_date"] == "2026-07-09T00:00:00Z"
    forbidden_fields = {"estimated_value", "value_bucket", "valuation_notes", "recommendation"}
    assert forbidden_fields.isdisjoint(reader.fieldnames or [])


def test_source_error_diagnostic_code_classifies_common_access_failures():
    assert source_error_diagnostic_code(
        urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    ) == "tls_certificate_error"
    assert source_error_diagnostic_code(
        urllib.error.URLError("[Errno 8] nodename nor servname provided")
    ) == "dns_error"
    assert source_error_diagnostic_code(TimeoutError("timed out")) == "timeout"
    assert source_error_diagnostic_code(urllib.error.URLError("connection reset")) == "unknown_source_error"


def test_default_ssl_context_uses_certifi_ca_file_when_available(monkeypatch):
    calls = []

    def fake_create_default_context(*, cafile=None):
        calls.append(cafile)
        return "ssl-context"

    monkeypatch.setattr(abebooks, "certifi_ca_file", lambda: "/tmp/certifi.pem")
    monkeypatch.setattr(abebooks.ssl, "create_default_context", fake_create_default_context)

    assert default_ssl_context() == "ssl-context"
    assert calls == ["/tmp/certifi.pem"]


def test_fetch_url_uses_verified_ssl_context(monkeypatch):
    calls = []

    class Response:
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"<html>ok</html>"

    def fake_urlopen(request, *, timeout, context):
        calls.append((request, timeout, context))
        return Response()

    ssl_context = object()
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert fetch_url("https://www.abebooks.com/servlet/SearchResults?isbn=123", timeout=5, ssl_context=ssl_context) == "<html>ok</html>"
    assert calls[0][1:] == (5, ssl_context)


def test_collect_abebooks_observations_command_wiring(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_collect(output_dir, limit, delay, max_results_per_book):
        calls.append((output_dir, limit, delay, max_results_per_book))
        return 7

    monkeypatch.setattr(library_pipeline, "collect_abebooks_observations", fake_collect)

    result = main([
        "collect-abebooks-observations",
        "--output-dir",
        str(tmp_path),
        "--limit",
        "5",
        "--delay",
        "0",
        "--max-results-per-book",
        "2",
    ])

    captured = capsys.readouterr().out
    assert result == 0
    assert calls == [(tmp_path, 5, 0.0, 2)]
    assert "Wrote 7 AbeBooks market observation rows" in captured


def test_collect_full_library_abebooks_observations_uses_all_assessed_catalog_items(tmp_path):
    output_dir = tmp_path / "output"
    data_dir = tmp_path / "data"
    write_rows(
        output_dir / "library_catalog.csv",
        ["catalog_item_id", "title", "authors", "isbn10", "isbn13"],
        [
            {"catalog_item_id": "BK000001", "title": "First", "authors": "One", "isbn13": "9780123456786"},
            {"catalog_item_id": "BK000002", "title": "Second", "authors": "Two", "isbn13": "9780123456787"},
        ],
    )
    write_rows(
        data_dir / "research_priority_assessments.csv",
        ["catalog_item_id", "research_priority_score", "research_priority_band", "triggered_signals"],
        [
            {"catalog_item_id": "BK000001", "research_priority_score": "8", "research_priority_band": "high"},
            {"catalog_item_id": "BK000002", "research_priority_score": "4", "research_priority_band": "medium"},
        ],
    )

    count = collect_full_library_abebooks_observations(
        output_dir,
        data_dir=data_dir,
        delay=0,
        fetch_html=lambda _url: LISTING_HTML,
        observation_date="2026-07-14T00:00:00Z",
        sleep=lambda _seconds: None,
    )

    assert count == 2
    path = output_dir / "full_abebooks_market_observations.csv"
    assert path.exists()
    assert path.with_suffix(".xlsx").exists()
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["catalog_id"] for row in rows} == {"BK000001", "BK000002"}


def test_collect_full_library_abebooks_observations_command_wiring(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_collect(output_dir, data_dir, output_path, limit, delay, max_results_per_book):
        calls.append((output_dir, data_dir, output_path, limit, delay, max_results_per_book))
        return 9

    monkeypatch.setattr(library_pipeline, "collect_full_library_abebooks_observations", fake_collect)
    custom_output = tmp_path / "test_observations.csv"

    result = main([
        "collect-full-library-abebooks-observations",
        "--output-dir",
        str(tmp_path / "output"),
        "--data-dir",
        str(tmp_path / "data"),
        "--output",
        str(custom_output),
        "--limit",
        "5",
        "--delay",
        "2",
        "--max-results-per-book",
        "2",
    ])

    captured = capsys.readouterr().out
    assert result == 0
    assert calls == [(tmp_path / "output", tmp_path / "data", custom_output, 5, 2.0, 2)]
    assert "Wrote 9 full-library AbeBooks observation rows" in captured


def sample_row(isbn13="9780123456786", isbn10="0123456789"):
    return {
        "catalog_id": "BK000001",
        "title": "The Test Book",
        "author": "Ada Author",
        "isbn10": isbn10,
        "isbn13": isbn13,
        "research_score": "8",
        "score_band": "8-10",
    }


def sample_fieldnames():
    return [
        "catalog_id",
        "title",
        "author",
        "isbn10",
        "isbn13",
        "research_score",
        "score_band",
    ]


def write_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
