"""Offline tests for `data_updates`."""

from .conftest import capture_request, offline_client


def test_data_updates_user_id_is_optional():
    """Regression: `fulcra_userid` briefly became a required positional argument."""
    client = offline_client()
    captured = capture_request(client)

    client.data_updates(
        start_time="2026-02-01 00:00:00Z", end_time="2026-02-03 00:00:00Z"
    )

    assert captured["path"] == "/data/v1/updates"
    assert "fulcra_userid" not in captured["query"]


def test_data_updates_passes_user_id_when_given():
    client = offline_client()
    captured = capture_request(client)

    client.data_updates(
        start_time="2026-02-01 00:00:00Z",
        end_time="2026-02-03 00:00:00Z",
        fulcra_userid="someone-else",
    )

    assert captured["query"]["fulcra_userid"] == "someone-else"
