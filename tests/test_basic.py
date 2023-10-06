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

def test_workouts(fulcra_client):
    workouts = fulcra_client.apple_workouts(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-03 04:00:00.000Z"
    )
    assert isinstance(workouts, List)

def test_simple_events(fulcra_client):
    events = fulcra_client.simple_events(
        start_time="2022-05-01 04:00:00.000Z", end_time="2023-08-03 04:00:00.000Z"
    )
    assert isinstance(events, List)

    filtered_events = fulcra_client.simple_events(
        start_time="2022-05-01 04:00:00.000Z", end_time="2023-08-03 04:00:00.000Z",
        categories=["testxyz", "nothing"]
    )
    assert isinstance(filtered_events, List)

def test_metric_samples(fulcra_client):
    samples = fulcra_client.metric_samples(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-03 04:00:00.000Z",
        metric="StepCount"
    )
    assert isinstance(samples, List)

def test_apple_location_updates(fulcra_client):
    updates = fulcra_client.apple_location_updates(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-03 04:00:00.000Z"
    )
    assert isinstance(updates, List)

def test_apple_location_visits(fulcra_client):
    visits = fulcra_client.apple_location_visits(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-03 04:00:00.000Z"
    )
    assert isinstance(visits, List)


