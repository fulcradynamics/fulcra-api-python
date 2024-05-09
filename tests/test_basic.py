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
    cals = fulcra_client.calendars()
    assert isinstance(cals, List)
    cals = fulcra_client.calendars(fulcra_userid=fulcra_client.get_fulcra_userid())
    assert isinstance(cals, List)
    try:
        cals = fulcra_client.calendars(
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8"
        )
        assert False
    except Exception:
        assert True


def test_calendar_events(fulcra_client):
    events = fulcra_client.calendar_events(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-10 04:00:00.000Z",
    )
    assert isinstance(events, List)
    events = fulcra_client.calendar_events(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-10 04:00:00.000Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(events, List)
    try:
        events = fulcra_client.calendar_events(
            start_time="2023-07-01 04:00:00.000Z",
            end_time="2023-07-10 04:00:00.000Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_workouts(fulcra_client):
    workouts = fulcra_client.apple_workouts(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-03 04:00:00.000Z"
    )
    assert isinstance(workouts, List)
    workouts = fulcra_client.apple_workouts(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-03 04:00:00.000Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(workouts, List)
    try:
        workouts = fulcra_client.apple_workouts(
            start_time="2023-07-01 04:00:00.000Z",
            end_time="2023-07-03 04:00:00.000Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_simple_events(fulcra_client):
    events = fulcra_client.simple_events(
        start_time="2022-05-01 04:00:00.000Z", end_time="2023-08-03 04:00:00.000Z"
    )
    assert isinstance(events, List)
    events = fulcra_client.simple_events(
        start_time="2022-05-01 04:00:00.000Z",
        end_time="2023-08-03 04:00:00.000Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(events, List)
    try:
        events = fulcra_client.simple_events(
            start_time="2022-05-01 04:00:00.000Z",
            end_time="2023-08-03 04:00:00.000Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True

    filtered_events = fulcra_client.simple_events(
        start_time="2022-05-01 04:00:00.000Z",
        end_time="2023-08-03 04:00:00.000Z",
        categories=["testxyz", "nothing"],
    )
    assert isinstance(filtered_events, List)


def test_metric_samples(fulcra_client):
    samples = fulcra_client.metric_samples(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-03 04:00:00.000Z",
        metric="StepCount",
    )
    assert isinstance(samples, List)
    samples = fulcra_client.metric_samples(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-03 04:00:00.000Z",
        metric="StepCount",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(samples, List)
    try:
        samples = fulcra_client.metric_samples(
            start_time="2023-07-01 04:00:00.000Z",
            end_time="2023-07-03 04:00:00.000Z",
            metric="StepCount",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_apple_location_updates(fulcra_client):
    updates = fulcra_client.apple_location_updates(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-03 04:00:00.000Z"
    )
    assert isinstance(updates, List)
    updates = fulcra_client.apple_location_updates(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-03 04:00:00.000Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(updates, List)
    try:
        updates = fulcra_client.apple_location_updates(
            start_time="2023-07-01 04:00:00.000Z",
            end_time="2023-07-03 04:00:00.000Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_apple_location_visits(fulcra_client):
    visits = fulcra_client.apple_location_visits(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-03 04:00:00.000Z"
    )
    assert isinstance(visits, List)
    visits = fulcra_client.apple_location_visits(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-03 04:00:00.000Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(visits, List)
    try:
        visits = fulcra_client.apple_location_visits(
            start_time="2023-07-01 04:00:00.000Z",
            end_time="2023-07-03 04:00:00.000Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_metric_time_series(fulcra_client):
    df = fulcra_client.metric_time_series(
        start_time="2024-01-24 00:00:00-08:00",
        end_time="2024-01-25 00:00:00-08:00",
        sample_rate=1,
        metric="StepCount",
    )
    assert df.shape == (86400, 1)
    assert df["step_count"].sum() > -1.0
    df = fulcra_client.metric_time_series(
        start_time="2024-01-24 00:00:00-08:00",
        end_time="2024-01-25 00:00:00-08:00",
        sample_rate=1,
        metric="StepCount",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert df.shape == (86400, 1)
    assert df["step_count"].sum() > -1.0
    try:
        df = fulcra_client.metric_time_series(
            start_time="2024-01-24 00:00:00-08:00",
            end_time="2024-01-25 00:00:00-08:00",
            sample_rate=1,
            metric="StepCount",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_location_at_time(fulcra_client):
    loc = fulcra_client.location_at_time(
        time="2024-01-24 00:00:00-08:00",
    )
    assert type(loc) == list
    assert len(loc) < 2
    loc = fulcra_client.location_at_time(
        time="2024-01-24 00:00:00-08:00",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert type(loc) == list
    assert len(loc) < 2
    try:
        loc = fulcra_client.location_at_time(
            time="2024-01-24 00:00:00-08:00",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_metrics_catalog(fulcra_client):
    metrics = fulcra_client.metrics_catalog()
    assert type(metrics) == list
    assert len(metrics) > 5
