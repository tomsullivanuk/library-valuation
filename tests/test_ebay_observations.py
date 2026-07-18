from valuation.abebooks import MARKET_OBSERVATION_FIELDNAMES
from valuation.ebay_active_listings import EbayActiveListing, EbayActiveListingSearchResult
from valuation.ebay_observations import (
    SOURCE,
    adapt_ebay_search_result,
    ebay_source_unavailable_row,
)


OBSERVED_AT = "2026-07-18T12:00:00Z"


def catalog_row():
    return {
        "catalog_item_id": "BK000001",
        "title": "Springer Handbook of Spacetime",
        "authors": "Abhay Ashtekar; Vesselin Petkov",
        "isbn_10": "3642419917",
        "isbn_13": "9783642419911",
        "research_score": "8",
        "research_band": "8-10",
    }


def listing(**overrides):
    values = {
        "item_id": "v1|123|0",
        "title": "Springer Handbook of Spacetime",
        "price_value": "89.50",
        "price_currency": "EUR",
        "item_web_url": "https://www.ebay.com/itm/123",
        "condition": "Very Good",
        "buying_options": ("FIXED_PRICE", "BEST_OFFER"),
        "item_location_country": "DE",
        "raw_source": "ebay_active_listing",
        "query": "Springer Handbook of Spacetime",
        "marketplace_id": "EBAY_US",
    }
    values.update(overrides)
    return EbayActiveListing(**values)


def search_result(*listings, query="Springer Handbook of Spacetime", total=None):
    return EbayActiveListingSearchResult(
        query=query,
        marketplace_id="EBAY_US",
        total=len(listings) if total is None else total,
        listings=tuple(listings),
    )


def test_observed_listing_maps_to_existing_observation_shape():
    rows = adapt_ebay_search_result(
        catalog_row(), search_result(listing()), observation_date=OBSERVED_AT
    )
    row = rows[0]
    assert list(row) == MARKET_OBSERVATION_FIELDNAMES
    assert row["catalog_id"] == "BK000001"
    assert row["title"] == "Springer Handbook of Spacetime"
    assert row["author"] == "Abhay Ashtekar; Vesselin Petkov"
    assert row["isbn10"] == "3642419917"
    assert row["isbn13"] == "9783642419911"
    assert row["source"] == SOURCE
    assert row["lookup_status"] == "observed"
    assert row["lookup_strategy"] == "direct_query"
    assert row["search_query"] == "Springer Handbook of Spacetime"
    assert row["result_rank"] == "1"
    assert row["observation_date"] == OBSERVED_AT
    assert row["match_confidence"] == "unknown"
    assert row["observation_id"].startswith("MOB-")


def test_price_currency_condition_and_url_are_preserved_without_seller_or_shipping():
    row = adapt_ebay_search_result(
        catalog_row(), search_result(listing()), observation_date=OBSERVED_AT
    )[0]
    assert row["asking_price"] == "89.50"
    assert row["currency"] == "EUR"
    assert row["condition"] == "Very Good"
    assert row["seller"] == ""
    assert row["listing_title"] == "Springer Handbook of Spacetime"
    assert row["listing_author"] == ""
    assert row["listing_url"] == "https://www.ebay.com/itm/123"
    assert "item price only; shipping excluded" in row["match_notes"]


def test_source_specific_values_are_limited_to_notes_and_raw_reference():
    row = adapt_ebay_search_result(
        catalog_row(), search_result(listing()), observation_date=OBSERVED_AT
    )[0]
    assert row["raw_reference"] == "v1|123|0"
    assert "item_id=v1|123|0" in row["match_notes"]
    assert "buying_options=FIXED_PRICE,BEST_OFFER" in row["match_notes"]
    assert "marketplace_id=EBAY_US" in row["match_notes"]
    assert "item_location_country=DE" in row["match_notes"]
    assert "seller" not in row["match_notes"].casefold()
    assert all(field in MARKET_OBSERVATION_FIELDNAMES for field in row)


def test_missing_price_is_preserved_as_blank_without_changing_observed_status():
    row = adapt_ebay_search_result(
        catalog_row(),
        search_result(listing(price_value="", price_currency="")),
        observation_date=OBSERVED_AT,
    )[0]
    assert row["lookup_status"] == "observed"
    assert row["asking_price"] == ""
    assert row["currency"] == ""


def test_zero_results_create_one_no_results_status_row():
    rows = adapt_ebay_search_result(
        catalog_row(), search_result(total=0), observation_date=OBSERVED_AT
    )
    assert len(rows) == 1
    row = rows[0]
    assert list(row) == MARKET_OBSERVATION_FIELDNAMES
    assert row["lookup_status"] == "no_results"
    assert row["diagnostic_code"] == "no_results"
    assert row["match_confidence"] == "unknown"
    assert row["asking_price"] == ""
    assert "EBAY_US" in row["match_notes"]


def test_missing_query_creates_one_no_query_status_row():
    row = adapt_ebay_search_result(
        catalog_row(), search_result(query="", total=0), observation_date=OBSERVED_AT
    )[0]
    assert row["lookup_status"] == "no_query"
    assert row["lookup_strategy"] == "direct_query"
    assert row["search_query"] == ""
    assert row["diagnostic_code"] == "no_query"


def test_source_failure_creates_safe_redacted_status_row():
    row = ebay_source_unavailable_row(
        catalog_row(),
        observation_date=OBSERVED_AT,
        lookup_strategy="title_author",
        search_query="Springer Handbook of Spacetime",
        diagnostic_code="HTTP 503 / upstream unavailable",
        safe_reason=(
            "HTTP 503; Bearer private-token; Basic cHJpdmF0ZQ==; "
            "access_token=secret-token client_secret=secret-value"
        ),
    )
    assert list(row) == MARKET_OBSERVATION_FIELDNAMES
    assert row["lookup_status"] == "source_unavailable"
    assert row["diagnostic_code"] == "http_503_upstream_unavailable"
    assert row["match_confidence"] == "unknown"
    assert "private-token" not in row["match_notes"]
    assert "cHJpdmF0ZQ" not in row["match_notes"]
    assert "secret-token" not in row["match_notes"]
    assert "secret-value" not in row["match_notes"]
    assert row["match_notes"].count("[REDACTED]") == 4


def test_adapter_is_deterministic_and_does_not_mutate_inputs():
    catalog = catalog_row()
    result = search_result(listing())
    first = adapt_ebay_search_result(catalog, result, observation_date=OBSERVED_AT)
    second = adapt_ebay_search_result(catalog, result, observation_date=OBSERVED_AT)
    assert first == second
    assert catalog == catalog_row()
    assert result == search_result(listing())
