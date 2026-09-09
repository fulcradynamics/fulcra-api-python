"""Offline tests for `fulcra_v1_records`."""

from .conftest import capture_request, offline_client


def test_v1_records_sends_promql_query():
    client = offline_client()
    captured = capture_request(client)

    client.fulcra_v1_records("HeartRate[1h] @ 1717200000")

    assert captured["path"] == "/data/v1/records"
    assert captured["query"]["q"] == "HeartRate[1h] @ 1717200000"
    assert "fulcra_userid" not in captured["query"]


def test_v1_records_user_id_is_optional():
    """A falsy `fulcra_userid` must not leak into the query."""
    client = offline_client()
    captured = capture_request(client)

    client.fulcra_v1_records("HeartRate[1h] @ 1717200000", fulcra_userid=None)

    assert "fulcra_userid" not in captured["query"]


def test_v1_records_passes_user_id_when_given():
    client = offline_client()
    captured = capture_request(client)

    client.fulcra_v1_records(
        "HeartRate[1h] @ 1717200000", fulcra_userid="someone-else"
    )

    assert captured["query"]["fulcra_userid"] == "someone-else"
