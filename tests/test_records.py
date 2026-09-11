"""Offline tests for the high-level record-fetching module."""

from datetime import datetime, timedelta, timezone

import pytest

from fulcra_api.records import build_v1_promql, get_records

from .conftest import capture_request, offline_client

DAY_START = datetime(2024, 6, 1, tzinfo=timezone.utc)
DAY_END = datetime(2024, 6, 2, tzinfo=timezone.utc)
EXPECTED_PROMQL = "HeartRate[86400s] @ 1717286400"


def _entry(*, api_version, record_type="metric", id="HeartRate", fulcra_userid="me"):
    return {
        "id": id,
        "api_version": api_version,
        "record_spec": {"type": record_type},
        "fulcra_userid": fulcra_userid,
    }


def _owned_client():
    client = offline_client()
    client.get_fulcra_userid = lambda: "me"
    return client


# --- build_v1_promql ---------------------------------------------------------


def test_promql_builds_anchored_range_vector():
    assert build_v1_promql("HeartRate", DAY_START, DAY_END) == EXPECTED_PROMQL


def test_promql_anchors_at_end_time_regardless_of_timezone():
    end_other = DAY_END.astimezone(timezone(timedelta(hours=-7)))
    assert build_v1_promql("HeartRate", DAY_START, end_other) == EXPECTED_PROMQL


def test_promql_zero_length_window_clamps_to_one_second():
    assert build_v1_promql("StepCount", DAY_START, DAY_START) == (
        "StepCount[1s] @ 1717200000"
    )


def test_promql_latest_is_a_bare_instant_vector():
    assert build_v1_promql("HeartRate", latest=True) == "HeartRate"


# --- get_records dispatch ----------------------------------------------------


def test_v1alpha1_dispatch_hits_path_endpoint():
    client = _owned_client()
    captured = capture_request(client, response=b'[{"x": 1}]')

    result = get_records(
        client, _entry(api_version="v1alpha1"), DAY_START, DAY_END
    )

    assert captured["path"] == "/data/v1alpha1/metric/HeartRate"
    assert "fulcra_userid" not in captured["query"]
    assert result == [{"x": 1}]


def test_v1alpha1_dispatch_scopes_other_users_data():
    client = _owned_client()
    captured = capture_request(client, response=b"[]")

    get_records(
        client,
        _entry(api_version="v1alpha1", fulcra_userid="someone-else"),
        DAY_START,
        DAY_END,
    )

    assert captured["query"]["fulcra_userid"] == "someone-else"


def test_v1_dispatch_builds_promql_and_parses_jsonl():
    client = _owned_client()
    captured = capture_request(client, response=b'{"x": 1}\n{"x": 2}\n')

    result = get_records(
        client, _entry(api_version="v1"), DAY_START, DAY_END
    )

    assert captured["path"] == "/data/v1/records"
    assert captured["query"]["q"] == EXPECTED_PROMQL
    assert result == [{"x": 1}, {"x": 2}]


def test_unsupported_combination_raises_value_error():
    client = _owned_client()

    with pytest.raises(ValueError, match="Could not derive API endpoint"):
        get_records(
            client, _entry(api_version="v0", record_type="event"), DAY_START, DAY_END
        )


def test_v1_rejects_group_participant_source():
    source = offline_client().group_participant("group", "participant")

    with pytest.raises(ValueError, match="Group participant"):
        get_records(source, _entry(api_version="v1"), DAY_START, DAY_END)


# --- get_records latest ------------------------------------------------------


def test_latest_v1_uses_bare_instant_vector():
    client = _owned_client()
    captured = capture_request(client, response=b'{"x": 9}\n')

    result = get_records(
        client, _entry(api_version="v1"), None, None, latest=True
    )

    assert captured["path"] == "/data/v1/records"
    assert captured["query"]["q"] == "HeartRate"
    assert result == [{"x": 9}]


def test_latest_v1alpha1_event_hits_latest_route():
    client = _owned_client()
    captured = capture_request(client, response=b"[]")

    get_records(
        client,
        _entry(api_version="v1alpha1", record_type="event"),
        None,
        None,
        latest=True,
    )

    assert captured["path"] == "/data/v1alpha1/event/HeartRate/latest"
    assert captured["query"]["total"] == 1


def test_latest_v1alpha1_metric_raises_value_error():
    client = _owned_client()

    with pytest.raises(ValueError, match="not supported"):
        get_records(
            client, _entry(api_version="v1alpha1"), None, None, latest=True
        )


def test_latest_v0_metric_raises_value_error():
    client = _owned_client()

    with pytest.raises(ValueError, match="not supported"):
        get_records(client, _entry(api_version="v0"), None, None, latest=True)
