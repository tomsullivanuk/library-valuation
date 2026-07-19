import base64
import urllib.parse

import pytest

from library_pipeline import build_parser, main
from valuation.ebay_access import (
    APPLICATION_SCOPE,
    EbayAccessClient,
    EbayAccessError,
    EbayCredentials,
    EbayRequestError,
    parse_retry_after,
)


ENVIRONMENT = {
    "EBAY_CLIENT_ID": "test-client-id",
    "EBAY_CLIENT_SECRET": "test-client-secret",
    "EBAY_MARKETPLACE_ID": "EBAY_US",
    "EBAY_ENVIRONMENT": "sandbox",
}


def headers(request):
    return {key.lower(): value for key, value in request.header_items()}


def test_missing_credentials_fail_clearly_without_exposing_values():
    with pytest.raises(EbayAccessError) as caught:
        EbayCredentials.from_environment({"EBAY_CLIENT_ID": "present"})

    message = str(caught.value)
    assert "EBAY_CLIENT_SECRET" in message
    assert "EBAY_MARKETPLACE_ID" in message
    assert "EBAY_ENVIRONMENT" in message
    assert "present" not in message


def test_credentials_load_from_environment_and_require_explicit_valid_environment():
    credentials = EbayCredentials.from_environment(ENVIRONMENT)
    assert credentials.client_id == "test-client-id"
    assert credentials.client_secret == "test-client-secret"
    assert credentials.marketplace_id == "EBAY_US"
    assert credentials.environment == "sandbox"

    with pytest.raises(EbayAccessError, match="sandbox.*production"):
        EbayCredentials.from_environment({**ENVIRONMENT, "EBAY_ENVIRONMENT": "automatic"})


def test_token_request_uses_client_credentials_application_scope_and_handles_success():
    seen = []

    def request_json(request, timeout):
        seen.append((request, timeout))
        return {"access_token": "short-lived-token", "expires_in": 7200}

    client = EbayAccessClient(
        EbayCredentials.from_environment(ENVIRONMENT), request_json=request_json, timeout=7
    )
    assert client.acquire_application_token() == "short-lived-token"

    request, timeout = seen[0]
    assert request.full_url == "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
    assert request.method == "POST"
    assert timeout == 7
    assert urllib.parse.parse_qs(request.data.decode()) == {
        "grant_type": ["client_credentials"],
        "scope": [APPLICATION_SCOPE],
    }
    expected_basic = base64.b64encode(b"test-client-id:test-client-secret").decode()
    assert headers(request)["authorization"] == f"Basic {expected_basic}"
    assert headers(request)["content-type"] == "application/x-www-form-urlencoded"


def test_search_request_and_safe_summary_are_bounded():
    seen = []

    def request_json(request, _timeout):
        seen.append(request)
        if request.method == "POST":
            return {"access_token": "short-lived-token"}
        return {
            "total": 12,
            "itemSummaries": [
                {"title": "  Springer\nHandbook of Spacetime  ", "price": {"value": "42.50", "currency": "USD"}},
                {"title": "Second result", "price": {"value": "55", "currency": "USD"}},
                {"title": "Result beyond requested limit", "price": {"value": "70", "currency": "USD"}},
            ],
        }

    client = EbayAccessClient(EbayCredentials.from_environment(ENVIRONMENT), request_json=request_json)
    result = client.check_access("Springer Handbook of Spacetime", 2)

    search = seen[1]
    parsed = urllib.parse.urlparse(search.full_url)
    assert parsed.path == "/buy/browse/v1/item_summary/search"
    assert urllib.parse.parse_qs(parsed.query) == {
        "q": ["Springer Handbook of Spacetime"],
        "limit": ["2"],
    }
    assert headers(search)["authorization"] == "Bearer short-lived-token"
    assert headers(search)["x-ebay-c-marketplace-id"] == "EBAY_US"
    assert result.environment == "sandbox"
    assert result.marketplace_id == "EBAY_US"
    assert result.token_acquired and result.request_succeeded
    assert result.result_count == 12
    assert len(result.listings) == 2
    assert result.listings[0].title == "Springer Handbook of Spacetime"
    assert result.listings[0].price == "42.50"
    assert result.listings[0].currency == "USD"


def test_api_errors_redact_credentials_headers_and_tokens():
    calls = 0

    def request_json(request, _timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"access_token": "live-access-token"}
        raise RuntimeError(
            "request failed for test-client-id test-client-secret "
            f"{headers(request)['authorization']} Basic dGVzdC1jbGllbnQtaWQ6dGVzdC1jbGllbnQtc2VjcmV0"
        )

    client = EbayAccessClient(EbayCredentials.from_environment(ENVIRONMENT), request_json=request_json)
    with pytest.raises(EbayAccessError) as caught:
        client.check_access("book", 1)

    message = str(caught.value)
    for secret in ("test-client-id", "test-client-secret", "live-access-token", "dGVzdC1jbGllbnQ"):
        assert secret not in message
    assert "Bearer [REDACTED]" in message
    assert "Basic [REDACTED]" in message


def test_invalid_token_and_search_responses_fail_safely():
    credentials = EbayCredentials.from_environment(ENVIRONMENT)
    client = EbayAccessClient(credentials, request_json=lambda _request, _timeout: {})
    with pytest.raises(EbayAccessError, match="did not include an access token"):
        client.acquire_application_token()

    responses = iter([{"access_token": "token"}, {"itemSummaries": "not-a-list"}])
    client = EbayAccessClient(credentials, request_json=lambda _request, _timeout: next(responses))
    with pytest.raises(EbayAccessError, match="invalid item summary list"):
        client.check_access("book", 1)


def test_cli_command_is_exposed_and_missing_credentials_are_user_facing(monkeypatch, capsys):
    args = build_parser().parse_args(["ebay-access-check", "--query", "book", "--limit", "1"])
    assert args.command == "ebay-access-check"
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)

    assert main(["ebay-access-check", "--query", "book", "--limit", "1"]) == 1
    captured = capsys.readouterr()
    assert "Missing required eBay environment variables" in captured.err
    assert captured.out == ""


def test_structured_request_metadata_is_preserved_without_secret_detail():
    credentials = EbayCredentials.from_environment(ENVIRONMENT)

    def request_json(_request, _timeout):
        raise EbayRequestError(
            "HTTP 429", status_code=429, retry_after_seconds=12,
            failure_kind="http",
        )

    client = EbayAccessClient(credentials, request_json=request_json)
    with pytest.raises(EbayRequestError) as caught:
        client.search_active_listings("book", 1, "private-token")
    error = caught.value
    assert error.operation == "active-listing search"
    assert error.status_code == 429
    assert error.retry_after_seconds == 12
    assert "private-token" not in str(error)
    assert parse_retry_after("15") == 15
    assert parse_retry_after("not-a-number") is None
