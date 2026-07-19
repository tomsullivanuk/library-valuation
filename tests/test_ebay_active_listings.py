import urllib.parse

import pytest

from valuation.ebay_access import EbayAccessClient, EbayAccessError, EbayCredentials, EbayRequestError
from valuation.ebay_active_listings import EbayActiveListingsClient, EbayBrowseSession, RAW_SOURCE


ENVIRONMENT = {
    "EBAY_CLIENT_ID": "test-client-id",
    "EBAY_CLIENT_SECRET": "test-client-secret",
    "EBAY_MARKETPLACE_ID": "EBAY_US",
    "EBAY_ENVIRONMENT": "sandbox",
}


def client_with_responses(*responses):
    remaining = iter(responses)
    access = EbayAccessClient(
        EbayCredentials.from_environment(ENVIRONMENT),
        request_json=lambda _request, _timeout: next(remaining),
    )
    return EbayActiveListingsClient(access)


def test_successful_search_maps_source_specific_normalized_results():
    client = client_with_responses(
        {"access_token": "token"},
        {
            "total": 1,
            "itemSummaries": [{
                "itemId": "v1|123|0",
                "title": " Springer\nHandbook of Spacetime ",
                "price": {"value": "49.95", "currency": "EUR"},
                "itemWebUrl": "https://www.ebay.com/itm/123",
                "condition": "Very Good",
                "seller": {"username": "bookseller"},
                "buyingOptions": ["FIXED_PRICE", "BEST_OFFER"],
                "itemLocation": {"country": "DE"},
                "unretained": {"raw": "payload"},
            }],
        },
    )

    result = client.search("  Springer  Handbook of Spacetime ", limit=3)
    assert result.query == "Springer Handbook of Spacetime"
    assert result.marketplace_id == "EBAY_US"
    assert result.total == 1
    assert len(result.listings) == 1
    listing = result.listings[0]
    assert listing.item_id == "v1|123|0"
    assert listing.title == "Springer Handbook of Spacetime"
    assert listing.price_value == "49.95"
    assert listing.price_currency == "EUR"
    assert listing.item_web_url == "https://www.ebay.com/itm/123"
    assert listing.condition == "Very Good"
    assert not hasattr(listing, "seller_username")
    assert "bookseller" not in repr(listing)
    assert listing.buying_options == ("FIXED_PRICE", "BEST_OFFER")
    assert listing.item_location_country == "DE"
    assert listing.raw_source == RAW_SOURCE
    assert listing.query == result.query


def test_zero_results_return_empty_list_without_error():
    result = client_with_responses(
        {"access_token": "token"}, {"total": 0, "itemSummaries": []}
    ).search("book", 3)
    assert result.total == 0
    assert result.listings == ()


def test_missing_price_and_optional_fields_are_safe_blanks():
    result = client_with_responses(
        {"access_token": "token"}, {"itemSummaries": [{"itemId": "123"}]}
    ).search("book", 1)
    listing = result.listings[0]
    assert listing.item_id == "123"
    assert listing.title == ""
    assert listing.price_value == ""
    assert listing.price_currency == ""
    assert listing.item_web_url == ""
    assert listing.condition == ""
    assert listing.buying_options == ()
    assert listing.item_location_country == ""


def test_limit_is_respected_and_marketplace_header_is_passed():
    requests = []

    def request_json(request, _timeout):
        requests.append(request)
        if request.method == "POST":
            return {"access_token": "token"}
        return {"total": 4, "itemSummaries": [{"itemId": str(i)} for i in range(4)]}

    access = EbayAccessClient(EbayCredentials.from_environment(ENVIRONMENT), request_json=request_json)
    result = EbayActiveListingsClient(access).search("book query", 2)
    search = requests[1]
    assert urllib.parse.parse_qs(urllib.parse.urlparse(search.full_url).query)["limit"] == ["2"]
    assert {key.lower(): value for key, value in search.header_items()}[
        "x-ebay-c-marketplace-id"
    ] == "EBAY_US"
    assert [listing.item_id for listing in result.listings] == ["0", "1"]


def test_token_and_browse_errors_remain_redacted():
    credentials = EbayCredentials.from_environment(ENVIRONMENT)

    def token_error(_request, _timeout):
        raise RuntimeError("test-client-secret Basic c2VjcmV0")

    with pytest.raises(EbayAccessError) as token_caught:
        EbayActiveListingsClient(
            EbayAccessClient(credentials, request_json=token_error)
        ).search("book", 1)
    assert "test-client-secret" not in str(token_caught.value)
    assert "Basic [REDACTED]" in str(token_caught.value)

    calls = 0

    def browse_error(request, _timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"access_token": "private-access-token"}
        raise RuntimeError(f"failed with {dict(request.header_items())['Authorization']}")

    with pytest.raises(EbayAccessError) as browse_caught:
        EbayActiveListingsClient(
            EbayAccessClient(credentials, request_json=browse_error)
        ).search("book", 1)
    assert "private-access-token" not in str(browse_caught.value)
    assert "Bearer [REDACTED]" in str(browse_caught.value)


def test_query_and_limit_validation_do_not_call_network():
    access = EbayAccessClient(
        EbayCredentials.from_environment(ENVIRONMENT),
        request_json=lambda _request, _timeout: pytest.fail("network should not be called"),
    )
    client = EbayActiveListingsClient(access)
    with pytest.raises(EbayAccessError, match="must not be blank"):
        client.search(" ", 1)
    with pytest.raises(EbayAccessError, match="between 1 and 50"):
        client.search("book", 51)


def test_browse_session_reuses_one_token_across_searches():
    requests = []

    def request_json(request, _timeout):
        requests.append(request)
        if request.method == "POST":
            return {"access_token": "memory-only-token", "expires_in": 7200}
        return {"total": 0, "itemSummaries": []}

    access = EbayAccessClient(EbayCredentials.from_environment(ENVIRONMENT), request_json=request_json)
    session = EbayBrowseSession(access, monotonic=lambda: 100.0)
    client = EbayActiveListingsClient(access, session=session)
    client.search("first", 1)
    client.search("second", 1)
    assert [request.method for request in requests].count("POST") == 1
    assert session.token_acquisition_count == 1
    assert session.token_refresh_count == 0
    assert session.browse_request_count == 2
    assert "memory-only-token" not in repr(session.token)


def test_browse_session_refreshes_before_expiration():
    clock = iter([0.0, 95.0])
    tokens = iter(["token-one", "token-two"])

    def request_json(request, _timeout):
        if request.method == "POST":
            return {"access_token": next(tokens), "expires_in": 100}
        return {"total": 0, "itemSummaries": []}

    access = EbayAccessClient(EbayCredentials.from_environment(ENVIRONMENT), request_json=request_json)
    session = EbayBrowseSession(access, monotonic=lambda: next(clock), refresh_margin_seconds=10)
    client = EbayActiveListingsClient(access, session=session)
    client.search("first", 1)
    client.search("second", 1)
    assert session.token_acquisition_count == 2
    assert session.token_refresh_count == 1
    assert session.token.generation == 2


def test_browse_session_refreshes_once_after_bearer_rejection():
    token_count = 0
    browse_count = 0

    def request_json(request, _timeout):
        nonlocal token_count, browse_count
        if request.method == "POST":
            token_count += 1
            return {"access_token": f"token-{token_count}", "expires_in": 7200}
        browse_count += 1
        if browse_count == 1:
            raise EbayRequestError("HTTP 401", status_code=401, failure_kind="http")
        return {"total": 0, "itemSummaries": []}

    access = EbayAccessClient(EbayCredentials.from_environment(ENVIRONMENT), request_json=request_json)
    session = EbayBrowseSession(access, monotonic=lambda: 0.0)
    EbayActiveListingsClient(access, session=session).search("book", 1)
    assert token_count == 2
    assert browse_count == 2
    assert session.token_refresh_count == 1


def test_repeated_bearer_rejection_stops_after_one_refresh():
    def request_json(request, _timeout):
        if request.method == "POST":
            return {"access_token": "token", "expires_in": 7200}
        raise EbayRequestError("HTTP 401", status_code=401, failure_kind="http")

    access = EbayAccessClient(EbayCredentials.from_environment(ENVIRONMENT), request_json=request_json)
    session = EbayBrowseSession(access, monotonic=lambda: 0.0)
    with pytest.raises(EbayRequestError) as caught:
        EbayActiveListingsClient(access, session=session).search("book", 1)
    assert caught.value.failure_kind == "bearer_rejected_after_refresh"
    assert session.token_acquisition_count == 2
    assert session.browse_request_count == 2
