import pytest
from fulcra_api.core import (
    FulcraAPI,
    FULCRA_OIDC_DOMAIN,
    FULCRA_OIDC_CLIENT_ID,
    FULCRA_OIDC_AUDIENCE,
    FULCRA_OIDC_SCOPE,
)
import urllib.parse
import datetime
from unittest.mock import patch


@pytest.fixture
def client() -> FulcraAPI:
    """Provides a fresh FulcraAPI client for each test."""
    return FulcraAPI()


def test_get_authorization_code_url_basic(client: FulcraAPI):
    redirect_uri = "https://testing.fulcradynamics.com/callback"
    url_str = client.get_authorization_code_url(redirect_uri=redirect_uri)

    assert url_str.startswith(f"https://{client.oidc_domain}/authorize?")

    parsed_url = urllib.parse.urlparse(url_str)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    assert query_params["client_id"] == [client.oidc_client_id]
    assert query_params["audience"] == [client.oidc_audience]
    assert query_params["scope"] == [client.oidc_scope]
    assert query_params["response_type"] == ["code"]
    assert query_params["redirect_uri"] == [redirect_uri]
    assert "state" not in query_params


def test_get_authorization_code_url_with_state(client: FulcraAPI):
    redirect_uri = "https://testing.fulcradynamics.com/callback"
    state = "randomstate123"
    url_str = client.get_authorization_code_url(redirect_uri=redirect_uri, state=state)

    parsed_url = urllib.parse.urlparse(url_str)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    assert query_params["state"] == [state]
    assert query_params["redirect_uri"] == [redirect_uri]


@patch("fulcra_api.core.FulcraAPI._fetch_token_from_auth_server")
def test_authorize_with_authorization_code_success(mock_fetch_token, client: FulcraAPI):
    code = "auth_code_123"
    redirect_uri = "https://testing.fulcradynamics.com/callback"

    mock_access_token = "mock_access_token_val"
    mock_refresh_token = "mock_refresh_token_val"
    mock_expiration = datetime.datetime.now() + datetime.timedelta(hours=1)

    mock_fetch_token.return_value = (
        mock_access_token,
        mock_expiration,
        mock_refresh_token,
    )

    client.authorize_with_authorization_code(code=code, redirect_uri=redirect_uri)

    mock_fetch_token.assert_called_once_with(
        {
            "grant_type": "authorization_code",
            "client_id": client.oidc_client_id,  # Uses instance client_id
            "code": code,
            "redirect_uri": redirect_uri,
        }
    )

    assert client.fulcra_cached_access_token == mock_access_token
    assert client.fulcra_cached_access_token_expiration == mock_expiration
    assert client.fulcra_cached_refresh_token == mock_refresh_token


@patch("fulcra_api.core.FulcraAPI._fetch_token_from_auth_server")
def test_authorize_with_authorization_code_failure(mock_fetch_token, client: FulcraAPI):
    code = "auth_code_123"
    redirect_uri = "https://testing.fulcradynamics.com/callback"

    mock_fetch_token.return_value = (None, None, None)

    with pytest.raises(
        Exception, match="Failed to exchange authorization code for token."
    ):
        client.authorize_with_authorization_code(code=code, redirect_uri=redirect_uri)

    assert client.fulcra_cached_access_token is None
    assert client.fulcra_cached_access_token_expiration is None
    assert client.fulcra_cached_refresh_token is None


def test_refresh_access_token_no_initial_refresh_token(client: FulcraAPI):
    client.fulcra_cached_refresh_token = None
    with pytest.raises(
        Exception, match="No refresh token available to refresh the access token."
    ):
        client.refresh_access_token()


@patch("fulcra_api.core.FulcraAPI._fetch_token_from_auth_server")
def test_refresh_access_token_success_with_new_refresh_token(
    mock_fetch_token, client: FulcraAPI
):
    initial_refresh_token = "initial_refresh_token"
    client.fulcra_cached_refresh_token = initial_refresh_token

    new_access_token = "new_access_token_val"
    new_refresh_token = "new_refresh_token_val"  # Simulating refresh token rotation
    new_expiration = datetime.datetime.now() + datetime.timedelta(hours=1)

    mock_fetch_token.return_value = (
        new_access_token,
        new_expiration,
        new_refresh_token,
    )

    result = client.refresh_access_token()

    assert result is True
    mock_fetch_token.assert_called_once_with(
        {
            "grant_type": "refresh_token",
            "client_id": client.oidc_client_id,  # Uses instance client_id
            "refresh_token": initial_refresh_token,
            "scope": client.oidc_scope,  # Uses instance scope
        }
    )

    assert client.fulcra_cached_access_token == new_access_token
    assert client.fulcra_cached_access_token_expiration == new_expiration
    assert client.fulcra_cached_refresh_token == new_refresh_token


@patch("fulcra_api.core.FulcraAPI._fetch_token_from_auth_server")
def test_refresh_access_token_success_no_new_refresh_token(
    mock_fetch_token, client: FulcraAPI
):
    initial_refresh_token = "initial_refresh_token_no_rotate"
    client.fulcra_cached_refresh_token = initial_refresh_token

    new_access_token = "new_access_token_val_no_rotate"
    # Server does not return a new refresh token
    new_expiration = datetime.datetime.now() + datetime.timedelta(hours=1)

    mock_fetch_token.return_value = (new_access_token, new_expiration, None)

    result = client.refresh_access_token()

    assert result is True
    assert client.fulcra_cached_access_token == new_access_token
    assert client.fulcra_cached_access_token_expiration == new_expiration
    # Refresh token should remain the old one
    assert client.fulcra_cached_refresh_token == initial_refresh_token


@patch("fulcra_api.core.FulcraAPI._fetch_token_from_auth_server")
def test_refresh_access_token_failure(mock_fetch_token, client: FulcraAPI):
    initial_refresh_token = "initial_refresh_token_fail"
    client.fulcra_cached_refresh_token = initial_refresh_token

    # Store original token values to check they are not cleared on simple failure
    original_access_token = "original_access_token"
    original_expiration = datetime.datetime.now() - datetime.timedelta(
        hours=1
    )  # Expired
    client.fulcra_cached_access_token = original_access_token
    client.fulcra_cached_access_token_expiration = original_expiration

    mock_fetch_token.return_value = (None, None, None)

    result = client.refresh_access_token()

    assert result is False
    # Current implementation does not clear tokens on refresh failure, it just returns False.
    assert client.fulcra_cached_access_token == original_access_token
    assert client.fulcra_cached_access_token_expiration == original_expiration
    assert client.fulcra_cached_refresh_token == initial_refresh_token
