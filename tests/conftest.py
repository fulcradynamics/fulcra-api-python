"""
Shared fixtures and helpers for the fulcra-api tests.

`fulcra_client` lives here rather than in each test module so that a run
covering several modules performs one device login instead of one per module.
"""

import datetime

import pytest

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials


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
