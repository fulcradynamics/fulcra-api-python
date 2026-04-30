import datetime
import urllib.parse
from unittest.mock import patch

import pytest

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials


@pytest.fixture
def client() -> FulcraAPI:
    """Provides a fresh FulcraAPI client for each test."""
    return FulcraAPI()


def test_get_authorization_code_url_basic(client: FulcraAPI):
    redirect_uri = "https://testing.fulcradynamics.com/callback"
    url_str = client.get_authorization_code_url(redirect_uri=redirect_uri)

    assert url_str.startswith(f"https://{client.oidc.domain}/authorize?")

    parsed_url = urllib.parse.urlparse(url_str)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    assert query_params["client_id"] == [client.oidc.client_id]
    assert query_params["audience"] == [client.oidc.audience]
    assert query_params["scope"] == [client.oidc.scope]
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


@patch("fulcra_api.oidc.FulcraOIDCProvider.get_token")
def test_authorize_with_authorization_code_success(mock_fetch_token, client: FulcraAPI):
    code = "auth_code_123"
    redirect_uri = "https://testing.fulcradynamics.com/callback"

    mock_access_token = "mock_access_token_val"
    mock_refresh_token = "mock_refresh_token_val"
    mock_expiration = datetime.datetime.now() + datetime.timedelta(hours=1)

    mock_fetch_token.return_value = FulcraCredentials(
        access_token=mock_access_token,
        access_token_expiration=mock_expiration,
        refresh_token=mock_refresh_token,
    )

    client.authorize_with_authorization_code(code=code, redirect_uri=redirect_uri)

    mock_fetch_token.assert_called_once_with(
        "authorization_code",
        {
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )

    assert client.get_cached_access_token() == mock_access_token
    assert client.get_cached_access_token_expiration() == mock_expiration
    assert client.get_cached_refresh_token() == mock_refresh_token


@patch("fulcra_api.oidc.FulcraOIDCProvider.get_token")
def test_authorize_with_authorization_code_failure(mock_fetch_token, client: FulcraAPI):
    code = "auth_code_123"
    redirect_uri = "https://testing.fulcradynamics.com/callback"

    # this should raise an exception
    mock_fetch_token.side_effect = Exception()

    with pytest.raises(
        Exception, match="Failed to exchange authorization code for token."
    ):
        client.authorize_with_authorization_code(code=code, redirect_uri=redirect_uri)

    assert client.get_cached_access_token() is None
    assert client.get_cached_access_token_expiration() is None
    assert client.get_cached_refresh_token() is None


def test_refresh_access_token_no_initial_refresh_token(client: FulcraAPI):
    client.fulcra_cached_refresh_token = None
    with pytest.raises(
        Exception, match="No refresh token available to refresh the access token."
    ):
        client.refresh_access_token()


@patch("fulcra_api.oidc.FulcraOIDCProvider.get_token")
def test_refresh_access_token_success_with_new_refresh_token(
    mock_get_token, client: FulcraAPI
):
    initial_refresh_token = "initial_refresh_token"

    client.fulcra_credentials = FulcraCredentials(
        access_token="initial_access_token",
        access_token_expiration=datetime.datetime.now() - datetime.timedelta(hours=1),
        refresh_token=initial_refresh_token,
    )

    new_access_token = "new_access_token_val"
    new_refresh_token = "new_refresh_token_val"  # Simulating refresh token rotation
    new_expiration = datetime.datetime.now() + datetime.timedelta(hours=1)

    mock_get_token.return_value = FulcraCredentials(
        access_token=new_access_token,
        access_token_expiration=new_expiration,
        refresh_token=new_refresh_token,
    )

    result = client.refresh_access_token()

    assert result is True
    mock_get_token.assert_called_once_with(
        "refresh_token",
        {"refresh_token": initial_refresh_token, "scope": client.oidc.scope},
    )

    assert client.get_cached_access_token() == new_access_token
    assert client.get_cached_access_token_expiration() == new_expiration
    assert client.get_cached_refresh_token() == new_refresh_token


@patch("fulcra_api.oidc.FulcraOIDCProvider.get_token")
def test_refresh_access_token_success_no_new_refresh_token(
    mock_get_token, client: FulcraAPI
):
    initial_refresh_token = "initial_refresh_token_no_rotate"

    client.fulcra_credentials = FulcraCredentials(
        access_token="initial_access_token",
        access_token_expiration=datetime.datetime.now() - datetime.timedelta(hours=1),
        refresh_token=initial_refresh_token,
    )

    new_access_token = "new_access_token_val_no_rotate"
    # Server does not return a new refresh token
    new_expiration = datetime.datetime.now() + datetime.timedelta(hours=1)

    mock_get_token.return_value = FulcraCredentials(
        access_token=new_access_token,
        access_token_expiration=new_expiration,
        refresh_token=None,
    )

    result = client.refresh_access_token()

    assert result is True
    assert client.get_cached_access_token() == new_access_token
    assert client.get_cached_access_token_expiration() == new_expiration
    # Refresh token should remain the old one
    assert client.get_cached_refresh_token() == initial_refresh_token


@patch("fulcra_api.oidc.FulcraOIDCProvider.get_token")
def test_refresh_access_token_failure(mock_get_token, client: FulcraAPI):
    initial_refresh_token = "initial_refresh_token_fail"

    client.fulcra_credentials = FulcraCredentials(
        access_token="initial_access_token",
        access_token_expiration=datetime.datetime.now() - datetime.timedelta(hours=1),
        refresh_token=initial_refresh_token,
    )

    # Store original token values to check they are not cleared on simple failure
    original_access_token = "original_access_token"
    original_expiration = datetime.datetime.now() - datetime.timedelta(
        hours=1
    )  # Expired
    client.set_cached_access_token(original_access_token)
    client.set_cached_access_token_expiration(original_expiration)

    mock_get_token.side_effect = Exception("Token refresh failed")

    result = client.refresh_access_token()

    assert result is False
    # Current implementation does not clear tokens on refresh failure, it just returns False.
    assert client.get_cached_access_token() == original_access_token
    assert client.get_cached_access_token_expiration() == original_expiration
    assert client.get_cached_refresh_token() == initial_refresh_token
