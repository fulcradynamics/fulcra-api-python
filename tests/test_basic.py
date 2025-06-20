import uuid
from datetime import datetime
from typing import List

import pytest

from fulcra_api.core import FulcraAPI


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

    df = fulcra_client.time_series_grouped(
        start_time=datetime.fromisoformat("2023-07-04 17:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-04 18:00:00.000+00:00"),
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

    events = fulcra_client.calendar_events(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-10 04:00:00.000+00:00"),
    )
    assert isinstance(events, List)
    events = fulcra_client.calendar_events(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-10 04:00:00.000+00:00"),
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(events, List)
    try:
        events = fulcra_client.calendar_events(
            start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
            end_time=datetime.fromisoformat("2023-07-10 04:00:00.000+00:00"),
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

    workouts = fulcra_client.apple_workouts(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
    )
    assert isinstance(workouts, List)
    workouts = fulcra_client.apple_workouts(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(workouts, List)
    try:
        workouts = fulcra_client.apple_workouts(
            start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
            end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


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

    samples = fulcra_client.metric_samples(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
        metric="StepCount",
    )
    assert isinstance(samples, List)
    samples = fulcra_client.metric_samples(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
        metric="StepCount",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(samples, List)
    try:
        samples = fulcra_client.metric_samples(
            start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
            end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
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

    updates = fulcra_client.apple_location_updates(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
    )
    assert isinstance(updates, List)
    updates = fulcra_client.apple_location_updates(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(updates, List)
    try:
        updates = fulcra_client.apple_location_updates(
            start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
            end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
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

    visits = fulcra_client.apple_location_visits(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
    )
    assert isinstance(visits, List)
    visits = fulcra_client.apple_location_visits(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(visits, List)
    try:
        visits = fulcra_client.apple_location_visits(
            start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
            end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_metric_time_series_calculations(fulcra_client):
    df = fulcra_client.metric_time_series(
        start_time="2024-01-24 00:00:00-08:00",
        end_time="2024-01-25 00:00:00-08:00",
        sample_rate=1,
        metric="HeartRate",
        calculations=["max"],
    )
    assert "max_heart_rate" in df

    df = fulcra_client.metric_time_series(
        start_time=datetime.fromisoformat("2024-01-24 00:00:00-08:00"),
        end_time=datetime.fromisoformat("2024-01-25 00:00:00-08:00"),
        sample_rate=1,
        metric="HeartRate",
        calculations=["max"],
    )
    assert "max_heart_rate" in df


def test_metric_time_series_with_calculations(fulcra_client):
    df = fulcra_client.metric_time_series(
        start_time="2024-01-24 00:00:00-08:00",
        end_time="2024-01-25 00:00:00-08:00",
        sample_rate=3600,
        metric="HeartRate",
        calculations=[
            "min",
            "max",
            "mean",
            "delta",
            "uniques",
            "allpoints",
            "rollingmean",
        ],
    )
    print(df.columns)
    assert "min_heart_rate" in df
    assert "max_heart_rate" in df
    assert "mean_heart_rate" in df
    assert "delta_heart_rate" in df
    assert "uniq_heart_rate" in df
    assert "all_heart_rate" in df
    assert "rollingmean_heart_rate" in df

    df = fulcra_client.metric_time_series(
        start_time=datetime.fromisoformat("2024-01-24 00:00:00-08:00"),
        end_time=datetime.fromisoformat("2024-01-25 00:00:00-08:00"),
        sample_rate=3600,
        metric="HeartRate",
        calculations=["min", "max"],
    )
    assert "min_heart_rate" in df
    assert "max_heart_rate" in df
    assert "mean_heart_rate" not in df


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

    df = fulcra_client.metric_time_series(
        start_time=datetime.fromisoformat("2024-01-24 00:00:00-08:00"),
        end_time=datetime.fromisoformat("2024-01-25 00:00:00-08:00"),
        sample_rate=1,
        metric="StepCount",
    )
    assert df.shape == (86400, 1)
    assert df["step_count"].sum() > -1.0
    df = fulcra_client.metric_time_series(
        start_time=datetime.fromisoformat("2024-01-24 00:00:00-08:00"),
        end_time=datetime.fromisoformat("2024-01-25 00:00:00-08:00"),
        sample_rate=1,
        metric="StepCount",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert df.shape == (86400, 1)
    assert df["step_count"].sum() > -1.0
    try:
        df = fulcra_client.metric_time_series(
            start_time=datetime.fromisoformat("2024-01-24 00:00:00-08:00"),
            end_time=datetime.fromisoformat("2024-01-25 00:00:00-08:00"),
            sample_rate=1,
            metric="StepCount",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_location_time_series(fulcra_client):
    locations = fulcra_client.location_time_series(
        start_time="2024-06-06T19:00:00-07:00",
        end_time="2024-06-06T20:00:00-07:00",
        reverse_geocode=True,
    )
    assert (type(locations)) is list
    assert len(locations) == 4
    try:
        locations = fulcra_client.location_time_series(
            start_time="2024-06-06T19:00:00-07:00",
            end_time="2024-06-06T20:00:00-07:00",
            reverse_geocode=True,
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True

    locations = fulcra_client.location_time_series(
        start_time=datetime.fromisoformat("2024-06-06T19:00:00-07:00"),
        end_time=datetime.fromisoformat("2024-06-06T20:00:00-07:00"),
        reverse_geocode=True,
    )
    assert (type(locations)) is list
    assert len(locations) == 4
    try:
        locations = fulcra_client.location_time_series(
            start_time=datetime.fromisoformat("2024-06-06T19:00:00-07:00"),
            end_time=datetime.fromisoformat("2024-06-06T20:00:00-07:00"),
            reverse_geocode=True,
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_location_at_time(fulcra_client):
    loc = fulcra_client.location_at_time(
        time="2024-01-24 00:00:00-08:00",
    )
    assert type(loc) is list
    assert len(loc) < 2
    loc = fulcra_client.location_at_time(
        time="2024-01-24 00:00:00-08:00",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert type(loc) is list
    assert len(loc) < 2
    try:
        loc = fulcra_client.location_at_time(
            time="2024-01-24 00:00:00-08:00",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True

    loc = fulcra_client.location_at_time(
        time=datetime.fromisoformat("2024-01-24 00:00:00-08:00"),
    )
    assert type(loc) is list
    assert len(loc) < 2
    loc = fulcra_client.location_at_time(
        time=datetime.fromisoformat("2024-01-24 00:00:00-08:00"),
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert type(loc) is list
    assert len(loc) < 2
    try:
        loc = fulcra_client.location_at_time(
            time=datetime.fromisoformat("2024-01-24 00:00:00-08:00"),
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_moment_annotations(fulcra_client):
    loc = fulcra_client.moment_annotations("2024-06-01T00:00Z", "2024-06-10T00:00Z")
    assert type(loc) is list

    loc = fulcra_client.moment_annotations(
        datetime.fromisoformat("2024-06-01T00:00+00:00"),
        datetime.fromisoformat("2024-06-10T00:00+00:00"),
    )
    assert type(loc) is list


def test_duration_annotations(fulcra_client):
    loc = fulcra_client.duration_annotations("2024-06-01T00:00Z", "2024-06-10T00:00Z")
    assert type(loc) is list

    loc = fulcra_client.duration_annotations(
        datetime.fromisoformat("2024-06-01T00:00+00:00"),
        datetime.fromisoformat("2024-06-10T00:00+00:00"),
    )
    assert type(loc) is list


def test_boolean_annotations(fulcra_client):
    loc = fulcra_client.boolean_annotations("2024-06-01T00:00Z", "2024-06-10T00:00Z")
    assert type(loc) is list

    loc = fulcra_client.boolean_annotations(
        datetime.fromisoformat("2024-06-01T00:00+00:00"),
        datetime.fromisoformat("2024-06-10T00:00+00:00"),
    )
    assert type(loc) is list


def test_numeric_annotations(fulcra_client):
    loc = fulcra_client.numeric_annotations("2024-06-01T00:00Z", "2024-06-10T00:00Z")
    assert type(loc) is list

    loc = fulcra_client.numeric_annotations(
        datetime.fromisoformat("2024-06-01T00:00+00:00"),
        datetime.fromisoformat("2024-06-10T00:00+00:00"),
    )
    assert type(loc) is list


def test_scale_annotations(fulcra_client):
    loc = fulcra_client.scale_annotations("2024-06-01T00:00Z", "2024-06-10T00:00Z")
    assert type(loc) is list

    loc = fulcra_client.scale_annotations(
        datetime.fromisoformat("2024-06-01T00:00+00:00"),
        datetime.fromisoformat("2024-06-10T00:00+00:00"),
    )
    assert type(loc) is list


def test_metrics_catalog(fulcra_client):
    metrics = fulcra_client.metrics_catalog()
    assert type(metrics) is list
    assert len(metrics) > 5


def test_get_shared_datasets(fulcra_client):
    shared_datasets = fulcra_client.get_shared_datasets()
    assert type(shared_datasets) is list


def test_get_user_info(fulcra_client):
    user_info = fulcra_client.get_user_info()
    assert isinstance(user_info, dict)
    assert "userid" in user_info
    assert "created" in user_info
    assert "preferences" in user_info
    assert user_info["userid"] == fulcra_client.get_fulcra_userid()


def test_sleep_cycles(fulcra_client):
    df = fulcra_client.sleep_cycles(
        start_time="2023-07-01 00:00:00Z",
        end_time="2023-07-02 00:00:00Z",
    )
    assert df.shape[0] >= 0  # Check if DataFrame is returned, can be empty

    df = fulcra_client.sleep_cycles(
        start_time=datetime.fromisoformat("2023-07-01 00:00:00+00:00"),
        end_time=datetime.fromisoformat("2023-07-02 00:00:00+00:00"),
    )
    assert df.shape[0] >= 0

    df = fulcra_client.sleep_cycles(
        start_time="2023-07-01 00:00:00Z",
        end_time="2023-07-02 00:00:00Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert df.shape[0] >= 0


def test_sleep_agg(fulcra_client):
    df = fulcra_client.sleep_agg(
        start_time="2023-07-01 00:00:00Z",
        end_time="2023-07-02 00:00:00Z",
    )
    assert df.shape[0] >= 0  # Check if DataFrame is returned, can be empty

    df = fulcra_client.sleep_agg(
        start_time=datetime.fromisoformat("2023-07-01 00:00:00+00:00"),
        end_time=datetime.fromisoformat("2023-07-02 00:00:00+00:00"),
    )
    assert df.shape[0] >= 0

    df = fulcra_client.sleep_agg(
        start_time="2023-07-01 00:00:00Z",
        end_time="2023-07-02 00:00:00Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert df.shape[0] >= 0

    try:
        df = fulcra_client.sleep_agg(
            start_time="2023-07-01 00:00:00Z",
            end_time="2023-07-02 00:00:00Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False  # Should not reach here
    except Exception:
        assert True

    df = fulcra_client.sleep_agg(
        start_time=datetime.fromisoformat("2023-07-01 00:00:00+00:00"),
        end_time=datetime.fromisoformat("2023-07-02 00:00:00+00:00"),
        cycle_gap="PT1H",
        stages=[1, 2, 3, 4, 5],
        gap_stages=[0],
        clip_to_range=False,
        mode="start",
        period="12h",
        agg_functions=["avg", "max"],
        tz="America/New_York",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert df.shape[0] >= 0


def test_gmaps_location_updates(fulcra_client):
    updates = fulcra_client.gmaps_location_updates(
        start_time="2023-07-01 04:00:00.000Z", end_time="2023-07-03 04:00:00.000Z"
    )
    assert isinstance(updates, List)
    updates = fulcra_client.gmaps_location_updates(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-03 04:00:00.000Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(updates, List)
    updates = fulcra_client.gmaps_location_updates(
        start_time="2023-07-01 04:00:00.000Z",
        end_time="2023-07-03 04:00:00.000Z",
        fulcra_source_id="AABD9EB1-8CF7-49C7-8456-A073F85FAE27",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(updates, List)
    try:
        updates = fulcra_client.gmaps_location_updates(
            start_time="2023-07-01 04:00:00.000Z",
            end_time="2023-07-03 04:00:00.000Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True

    updates = fulcra_client.gmaps_location_updates(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
    )
    assert isinstance(updates, List)
    updates = fulcra_client.gmaps_location_updates(
        start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
        end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert isinstance(updates, List)
    try:
        updates = fulcra_client.gmaps_location_updates(
            start_time=datetime.fromisoformat("2023-07-01 04:00:00.000+00:00"),
            end_time=datetime.fromisoformat("2023-07-03 04:00:00.000+00:00"),
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False
    except Exception:
        assert True


def test_sleep_stages(fulcra_client):
    df = fulcra_client.sleep_stages(
        start_time="2023-07-01 00:00:00Z",
        end_time="2023-07-02 00:00:00Z",
    )
    assert df.shape[0] >= 0  # Check if DataFrame is returned, can be empty

    df = fulcra_client.sleep_stages(
        start_time=datetime.fromisoformat("2023-07-01 00:00:00+00:00"),
        end_time=datetime.fromisoformat("2023-07-02 00:00:00+00:00"),
    )
    assert df.shape[0] >= 0

    df = fulcra_client.sleep_stages(
        start_time="2023-07-01 00:00:00Z",
        end_time="2023-07-02 00:00:00Z",
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert df.shape[0] >= 0

    try:
        df = fulcra_client.sleep_stages(
            start_time="2023-07-01 00:00:00Z",
            end_time="2023-07-02 00:00:00Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False  # Should not reach here
    except Exception:
        assert True

    df = fulcra_client.sleep_stages(
        start_time=datetime.fromisoformat("2023-07-01 00:00:00+00:00"),
        end_time=datetime.fromisoformat("2023-07-02 00:00:00+00:00"),
        cycle_gap="PT1H",
        stages=[1, 2, 3, 4, 5],
        gap_stages=[0],
        merge_overlapping=False,
        merge_contiguous=False,
        clip_to_range=False,
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert df.shape[0] >= 0

    try:
        df = fulcra_client.sleep_cycles(
            start_time="2023-07-01 00:00:00Z",
            end_time="2023-07-02 00:00:00Z",
            fulcra_userid="13371337-1337-1337-81e7-a102ab7d3ff8",
        )
        assert False  # Should not reach here
    except Exception:
        assert True

    df = fulcra_client.sleep_cycles(
        start_time=datetime.fromisoformat("2023-07-01 00:00:00+00:00"),
        end_time=datetime.fromisoformat("2023-07-02 00:00:00+00:00"),
        cycle_gap="PT1H",
        stages=[1, 2, 3],
        gap_stages=[0],
        clip_to_range=False,
        fulcra_userid=fulcra_client.get_fulcra_userid(),
    )
    assert df.shape[0] >= 0
