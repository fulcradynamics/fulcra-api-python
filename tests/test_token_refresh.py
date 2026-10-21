"""Offline tests for access token expiry and refresh (PLAT-829).

Agents call the CLI on a loop from several processes, sometimes running in
different timezones, sharing one credentials file. Expiry has to be judged
the same way in all of them, a failed refresh has to say whether logging in
again is needed, and concurrent refreshes mustn't spend the refresh token
twice.
"""

import base64
import datetime
import importlib
import io
import json
import os
import stat
import sys
import time
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import click
import pytest
from click.testing import CliRunner

from fulcra_api.cli import (
    EXIT_AUTH_UNAVAILABLE,
    EXIT_REAUTH_REQUIRED,
    FulcraGroup,
)
from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials, jwt_expiration
from fulcra_api.credentials_store import CredentialsFile
from fulcra_api.oidc import (
    FulcraAuthUnavailable,
    FulcraOIDCProvider,
    FulcraReauthRequired,
)

auth_module = importlib.import_module("fulcra_api.cli.auth")

UTC = datetime.timezone.utc


def make_jwt(expires_in: float) -> str:
    """An unsigned JWT whose `exp` is `expires_in` seconds from now."""

    def part(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    exp = int(time.time() + expires_in)
    return f"{part({'alg': 'none'})}.{part({'exp': exp, 'sub': 'u'})}.sig"


def http_error(code: int, body: dict | None = None) -> HTTPError:
    return HTTPError(
        "https://example/oauth/token",
        code,
        "error",
        {},  # type: ignore[arg-type]
        io.BytesIO(json.dumps(body or {}).encode()),
    )


@pytest.fixture
def provider() -> FulcraOIDCProvider:
    return FulcraOIDCProvider(
        domain="auth.example", client_id="cid", scope="openid", audience="aud"
    )


@pytest.fixture
def local_tz():
    """Switch this process's local timezone, as a different TZ= would."""
    if not hasattr(time, "tzset"):
        pytest.skip("needs time.tzset")
    original = os.environ.get("TZ")

    def set_tz(name: str):
        os.environ["TZ"] = name
        time.tzset()

    yield set_tz
    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


# --- expiry ---------------------------------------------------------------


def test_jwt_expiration_reads_exp_claim():
    exp = jwt_expiration(make_jwt(3600))
    assert exp is not None and exp.tzinfo is not None
    assert abs((exp - datetime.datetime.now(UTC)).total_seconds() - 3600) < 5


@pytest.mark.parametrize("token", [None, "", "opaque-token", "a.b.c", "a.!!!.c"])
def test_jwt_expiration_is_none_for_non_jwts(token):
    assert jwt_expiration(token) is None


def test_jwt_exp_wins_over_stored_expiration():
    # The stored expiration claims hours left, but the token itself expired.
    creds = FulcraCredentials(
        access_token=make_jwt(-60),
        access_token_expiration=datetime.datetime.now() + datetime.timedelta(hours=7),
    )
    assert creds.is_expired()


def test_file_written_in_utc_read_in_pacific(local_tz):
    """The incident: a UTC process wrote the file, a Pacific one read it."""
    local_tz("UTC")
    written = FulcraCredentials(
        access_token=make_jwt(-60),
        access_token_expiration=datetime.datetime.now() - datetime.timedelta(minutes=1),
        refresh_token="rt",
    ).to_json()

    local_tz("America/Los_Angeles")
    read = FulcraCredentials.from_json(written)
    assert read.is_expired()


def test_naive_expiration_falls_back_to_local_time():
    # Opaque tokens (no exp claim) keep the old local-time behavior.
    soon = datetime.datetime.now() + datetime.timedelta(seconds=30)
    creds = FulcraCredentials(access_token="opaque", access_token_expiration=soon)
    assert not creds.is_expired()
    assert creds.is_expired(leeway=datetime.timedelta(seconds=60))


def test_aware_expiration_compares_without_error():
    creds = FulcraCredentials(
        access_token="opaque",
        access_token_expiration=datetime.datetime.now(UTC)
        + datetime.timedelta(hours=1),
    )
    assert not creds.is_expired()


def test_stored_expiration_stays_readable_by_older_releases():
    # Older releases compare this field with a naive datetime.now(), so it
    # must not carry an offset.
    expiration = datetime.datetime.now(UTC) + datetime.timedelta(hours=1)
    data = json.loads(
        FulcraCredentials(
            access_token="t", access_token_expiration=expiration
        ).to_json()
    )
    stored = datetime.datetime.fromisoformat(data["access_token_expiration"])
    assert stored.tzinfo is None
    assert stored.astimezone() == expiration


def test_from_json_returns_aware_datetimes():
    creds = FulcraCredentials.from_json(
        json.dumps(
            {
                "access_token": "t",
                "access_token_expiration": "2026-10-21T16:50:58.470000",
                "refresh_token": "rt",
                "refresh_token_expiration": None,
            }
        )
    )
    assert creds.access_token_expiration.tzinfo is not None


def test_get_token_stamps_an_aware_expiry_with_a_timeout(provider):
    token = make_jwt(86400)
    response = MagicMock()
    response.read.return_value = json.dumps(
        {"access_token": token, "expires_in": 86400, "refresh_token": "rt2"}
    ).encode()
    with patch(
        "fulcra_api.oidc.urllib.request.urlopen", return_value=response
    ) as urlopen:
        creds = provider.get_token("refresh_token", {"refresh_token": "rt"})

    assert urlopen.call_args.kwargs["timeout"] > 0
    assert creds.access_token_expiration == jwt_expiration(token)


# --- refresh failures -----------------------------------------------------


def test_rejected_refresh_token_needs_reauth_without_retrying(provider):
    with patch.object(
        provider,
        "get_token",
        side_effect=http_error(
            403,
            {
                "error": "invalid_grant",
                "error_description": "Unknown or invalid refresh token.",
            },
        ),
    ) as get_token:
        with pytest.raises(FulcraReauthRequired, match="invalid_grant"):
            provider.refresh_credentials(FulcraCredentials(refresh_token="rt"))
    assert get_token.call_count == 1


@pytest.mark.parametrize(
    "error",
    [
        URLError("no route to host"),
        TimeoutError("timed out"),
        http_error(503),
        http_error(429),
    ],
)
def test_temporary_failures_are_retried_then_reported(provider, error):
    with patch("fulcra_api.oidc.time.sleep"), patch.object(
        provider, "get_token", side_effect=error
    ) as get_token:
        with pytest.raises(FulcraAuthUnavailable):
            provider.refresh_credentials(FulcraCredentials(refresh_token="rt"))
    assert get_token.call_count == 3


def test_temporary_failure_then_success(provider):
    fresh = FulcraCredentials(access_token=make_jwt(3600))
    with patch("fulcra_api.oidc.time.sleep"), patch.object(
        provider, "get_token", side_effect=[http_error(502), fresh]
    ):
        assert (
            provider.refresh_credentials(FulcraCredentials(refresh_token="rt")) is fresh
        )


def expired_client(**kwargs) -> FulcraAPI:
    return FulcraAPI(
        credentials=FulcraCredentials(access_token=make_jwt(-60), refresh_token="rt"),
        **kwargs,
    )


def test_failed_refresh_raises_instead_of_sending_an_expired_token():
    client = expired_client()
    with patch.object(
        client.oidc,
        "refresh_credentials",
        side_effect=FulcraReauthRequired("invalid_grant"),
    ), patch("fulcra_api.core.urllib.request.urlopen") as urlopen:
        with pytest.raises(FulcraReauthRequired):
            client.fulcra_api("/user/v1alpha1/info")
    urlopen.assert_not_called()


def test_token_about_to_expire_is_refreshed_before_the_request():
    client = FulcraAPI(
        credentials=FulcraCredentials(access_token=make_jwt(20), refresh_token="rt")
    )
    fresh = make_jwt(3600)
    with patch.object(
        client.oidc,
        "refresh_credentials",
        return_value=FulcraCredentials(access_token=fresh),
    ), patch("fulcra_api.core.urllib.request.urlopen") as urlopen:
        urlopen.return_value.read.return_value = b"{}"
        client.fulcra_api("/user/v1alpha1/info")
    assert urlopen.call_args.args[0].get_header("Authorization") == f"Bearer {fresh}"


def test_failed_refresh_of_a_still_valid_token_still_sends_it():
    held = make_jwt(20)
    client = FulcraAPI(
        credentials=FulcraCredentials(access_token=held, refresh_token="rt")
    )
    with patch.object(
        client.oidc, "refresh_credentials", side_effect=FulcraAuthUnavailable("down")
    ), patch("fulcra_api.core.urllib.request.urlopen") as urlopen:
        urlopen.return_value.read.return_value = b"{}"
        client.fulcra_api("/user/v1alpha1/info")
    assert urlopen.call_args.args[0].get_header("Authorization") == f"Bearer {held}"


def test_401_refreshes_and_retries_once():
    # e.g. a wrong local clock made an expired token look valid
    client = FulcraAPI(
        credentials=FulcraCredentials(access_token=make_jwt(3600), refresh_token="rt")
    )
    fresh = make_jwt(3600) + "x"
    ok = MagicMock()
    ok.read.return_value = b"{}"
    with patch.object(
        client.oidc,
        "refresh_credentials",
        return_value=FulcraCredentials(access_token=fresh),
    ), patch(
        "fulcra_api.core.urllib.request.urlopen", side_effect=[http_error(401), ok]
    ) as urlopen:
        assert client.fulcra_api("/user/v1alpha1/info") == b"{}"
    assert urlopen.call_count == 2
    assert urlopen.call_args.args[0].get_header("Authorization") == f"Bearer {fresh}"


def test_refresh_access_token_keeps_returning_false_on_failure():
    client = expired_client()
    with patch.object(
        client.oidc, "refresh_credentials", side_effect=FulcraAuthUnavailable("down")
    ):
        assert client.refresh_access_token() is False


# --- shared credentials file ----------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_credentials_file_is_private(tmp_path):
    store = CredentialsFile(tmp_path / "credentials.json")
    store.save(FulcraCredentials(access_token="t", refresh_token="rt"))
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    assert store.load().refresh_token == "rt"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_load_missing_file_is_none(tmp_path):
    assert CredentialsFile(tmp_path / "nope.json").load() is None


def test_second_process_reuses_a_refresh_another_already_did(tmp_path):
    """Two processes load the same expired token; only one may spend the
    refresh token, since Auth0 revokes a rotated refresh token used twice."""
    store = CredentialsFile(tmp_path / "credentials.json")
    store.save(FulcraCredentials(access_token=make_jwt(-60), refresh_token="rt1"))

    a = FulcraAPI(credentials=store.load(), credentials_store=store)
    b = FulcraAPI(credentials=store.load(), credentials_store=store)

    fresh = FulcraCredentials(access_token=make_jwt(3600), refresh_token="rt2")
    with patch.object(a.oidc, "refresh_credentials", return_value=fresh) as a_refresh:
        a.refresh_credentials()
    with patch.object(b.oidc, "refresh_credentials") as b_refresh:
        b.refresh_credentials()

    a_refresh.assert_called_once()
    b_refresh.assert_not_called()
    assert b.fulcra_credentials.access_token == fresh.access_token
    assert store.load().refresh_token == "rt2"


def test_refresh_uses_the_stored_refresh_token(tmp_path):
    # This client was loaded before another process rotated the refresh token.
    store = CredentialsFile(tmp_path / "credentials.json")
    client = FulcraAPI(
        credentials=FulcraCredentials(access_token=make_jwt(-60), refresh_token="rt1"),
        credentials_store=store,
    )
    store.save(FulcraCredentials(access_token=make_jwt(-30), refresh_token="rt2"))

    with patch.object(
        client.oidc,
        "refresh_credentials",
        return_value=FulcraCredentials(access_token=make_jwt(3600)),
    ) as refresh:
        client.refresh_credentials()

    assert refresh.call_args.args[0].refresh_token == "rt2"
    assert store.load().refresh_token == "rt2"


# --- CLI ------------------------------------------------------------------


def run_failing_command(exc: Exception, wrap: bool):
    @click.group(cls=FulcraGroup)
    def group():
        pass

    @group.command()
    def cmd():
        if not wrap:
            raise exc
        try:
            raise exc
        except Exception as inner:
            raise click.ClickException(str(inner))

    return CliRunner().invoke(group, ["cmd"])


@pytest.mark.parametrize("wrap", [False, True])
def test_cli_reports_reauth_with_its_own_exit_code(wrap):
    result = run_failing_command(FulcraReauthRequired("invalid_grant"), wrap)
    assert result.exit_code == EXIT_REAUTH_REQUIRED
    assert "fulcra auth login" in result.output


@pytest.mark.parametrize("wrap", [False, True])
def test_cli_reports_temporary_failure_without_suggesting_login(wrap):
    result = run_failing_command(FulcraAuthUnavailable("could not reach"), wrap)
    assert result.exit_code == EXIT_AUTH_UNAVAILABLE
    assert "try again" in result.output
    assert "fulcra auth login" not in result.output


def test_cli_leaves_other_errors_alone():
    result = run_failing_command(ValueError("boom"), wrap=True)
    assert result.exit_code == 1
    assert "boom" in result.output


def test_print_access_token_reuses_a_valid_token():
    held = make_jwt(3600)
    client = FulcraAPI(
        credentials=FulcraCredentials(access_token=held, refresh_token="rt")
    )
    with patch.object(client.oidc, "refresh_credentials") as refresh:
        result = CliRunner().invoke(auth_module.get_access_token, [], obj=client)
    assert result.exit_code == 0, result.output
    refresh.assert_not_called()
    assert result.output.strip() == held


def test_lock_excludes_other_holders(tmp_path):
    import threading

    store = CredentialsFile(tmp_path / "credentials.json")
    held = threading.Event()
    waited = []

    def hold():
        with store.lock():
            held.set()
            time.sleep(0.3)

    t = threading.Thread(target=hold)
    t.start()
    held.wait()
    start = time.monotonic()
    with store.lock():
        waited.append(time.monotonic() - start)
    t.join()
    assert waited[0] >= 0.2
