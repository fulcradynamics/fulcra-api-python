from fulcra_api.core import FulcraAPI
import pytest
import uuid
from typing import List


@pytest.fixture(scope="session")
def fulcra_client() -> FulcraAPI:
    fulcra = FulcraAPI()
    fulcra.authorize()
    return fulcra


def test_auth(fulcra_client):
    fuuid = uuid.UUID(fulcra_client.get_fulcra_userid())
    assert fuuid.variant == uuid.RFC_4122


def test_time_series_grouped(fulcra_client):
    df = fulcra_client.time_series_grouped(
        start_time="2023-07-04 17:00:00.000Z",
        end_time="2023-07-04 18:00:00.000Z",
        metrics=[
            "DistanceTraveledOnFoot",
        ],
        sample_rate=60,
    )
    assert df.shape[0] == 60


def test_calendars(fulcra_client):
    events = fulcra_client.calendar_events(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-10 04:00:00.000Z"
    )
    assert isinstance(events, List)
