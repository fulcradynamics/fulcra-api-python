"""
Shared fixtures and helpers for the fulcra-api tests.

`fulcra_client` lives here rather than in each test module so that a run
covering several modules performs one device login instead of one per module.

Tests that use `fulcra_client` talk to a real backend and need someone to
finish a device login in a browser, so they're marked `live` and skipped by
default. CI runs everything else. Run them locally with:

    uv run pytest --live
"""

import datetime

import pytest

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        help="also run tests against a real Fulcra backend (needs a device login)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: talks to a real Fulcra backend; run with --live"
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "fulcra_client" in item.fixturenames:
            item.add_marker(pytest.mark.live)
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="needs a real Fulcra backend and a login; run with --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def fulcra_client() -> FulcraAPI:
    """An authorized client, for the tests that talk to a real backend."""
    fulcra = FulcraAPI()
    fulcra.authorize()
    return fulcra


def offline_client() -> FulcraAPI:
    """A client holding a fake token, for tests that never reach the network."""
    return FulcraAPI(
        credentials=FulcraCredentials(
            access_token="fake-token",
            access_token_expiration=datetime.datetime.now()
            + datetime.timedelta(hours=1),
        )
    )


def capture_request(client: FulcraAPI, response: bytes = b"{}") -> dict:
    """Point the client's transport at a dict instead of the network.

    `response` is the raw body the fake transport hands back, for callers
    that parse it.
    """
    captured: dict = {}

    def fake_fulcra_api(url_path, method="GET", data=None, **kwargs):
        captured["path"] = url_path
        captured["method"] = method
        captured["data"] = data
        captured["query"] = kwargs.get("query")
        return response

    client.fulcra_api = fake_fulcra_api
    return captured
