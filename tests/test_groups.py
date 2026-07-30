import datetime
import urllib.request
from typing import List
from urllib.error import HTTPError

import pytest

from fulcra_api.core import FulcraAPI, FulcraGroupParticipant
from fulcra_api.credentials import FulcraCredentials


@pytest.fixture(scope="session")
def fulcra_client() -> FulcraAPI:
    fulcra = FulcraAPI()
    fulcra.authorize()
    return fulcra


#
# Offline tests (no authorization required)
#


def offline_client() -> FulcraAPI:
    return FulcraAPI(
        credentials=FulcraCredentials(
            access_token="fake-token",
            access_token_expiration=datetime.datetime.now()
            + datetime.timedelta(hours=1),
        )
    )


def test_group_participant_paths():
    client = offline_client()
    participant = client.group_participant("gid-123", "pid-456")
    assert isinstance(participant, FulcraGroupParticipant)
    assert (
        participant._v0_data_path("metric_samples")
        == "/data/v0/pool/gid-123/participant/pid-456/metric_samples"
    )
    with pytest.raises(ValueError):
        participant._v0_data_path("metric_samples", "some-user")
    assert (
        client._v0_data_path("sleep_agg", "user-789") == "/data/v0/user-789/sleep_agg"
    )


def test_group_participant_method_surface():
    participant = offline_client().group_participant("gid", "pid")
    for name in [
        "metric_time_series",
        "metric_samples",
        "apple_workouts",
        "location_at_time",
        "location_time_series",
        "gmaps_location_updates",
        "apple_location_updates",
        "apple_location_visits",
        "sleep_stages",
        "sleep_cycles",
        "sleep_agg",
        "get_metadata",
        "set_metadata",
        "update_metadata",
    ]:
        assert callable(getattr(participant, name))
    # Operations without pool data routes must not exist on the accessor
    for name in ["calendars", "calendar_events", "create_group", "authorize"]:
        assert not hasattr(participant, name)


def test_empty_body_is_sent(monkeypatch):
    """Regression test: data={} must send an empty JSON body, not no body."""
    client = offline_client()
    captured = {}

    def fake_urlopen(req):
        captured["data"] = req.data
        captured["content_type"] = req.headers.get("Content-type")

        class Resp:
            def read(self):
                return b"{}"

        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client.set_group_participant_metadata("gid", "pid", {})
    assert captured["data"] == b"{}"
    assert captured["content_type"] == "application/json"

    client.fulcra_api("/user/v1alpha1/pool")
    assert captured["data"] is None
    assert captured["content_type"] is None


#
# Live integration tests
#


def test_group_lifecycle(fulcra_client):
    group = fulcra_client.create_group(
        title="fulcra-api-python integration test",
        is_public=False,
        responsible_entity="Fulcra Dynamics",
        description="Temporary group created by the test suite; safe to delete.",
        fulcra_data_types=["StepCount"],
        group_url="https://fulcradynamics.com/",
    )
    group_id = group["id"]
    assert group["is_public"] is False

    try:
        fetched = fulcra_client.get_group(group_id)
        assert fetched["title"] == "fulcra-api-python integration test"

        updated = fulcra_client.update_group(
            group_id, description="Updated by the test suite."
        )
        assert updated["description"] == "Updated by the test suite."
        assert updated["title"] == "fulcra-api-python integration test"

        updated = fulcra_client.update_group(
            group_id, header_image_url="https://fulcradynamics.com/header.png"
        )
        assert updated["header_image_url"] == "https://fulcradynamics.com/header.png"
        # Fields that are not passed stay untouched; an explicit None clears.
        updated = fulcra_client.update_group(group_id, header_image_url=None)
        assert updated["header_image_url"] is None
        assert updated["description"] == "Updated by the test suite."

        # The owner joins their own group, acting as a participant.
        membership = fulcra_client.join_group(group_id)
        participant_id = membership["participant_id"]

        joined = fulcra_client.get_groups(subscribed_only=True)
        ours = next(g for g in joined if g["id"] == group_id)
        assert ours["participant_id"] == participant_id

        participant_ids = fulcra_client.get_group_participants(group_id)
        assert participant_id in participant_ids

        # Participant metadata round trip, including clearing it (regression
        # test for empty-body requests).
        participant = fulcra_client.group_participant(group_id, participant_id)
        participant.set_metadata({"nickname": "tester"})
        assert participant.get_metadata() == {"nickname": "tester"}
        participant.update_metadata({"score": 42})
        assert participant.get_metadata() == {"nickname": "tester", "score": 42}
        participant.set_metadata({})
        assert participant.get_metadata() == {}

        # Data access through the accessor; the participant's data is the
        # owner's own since the owner joined the group.
        samples = participant.metric_samples(
            start_time="2024-01-24 00:00:00-08:00",
            end_time="2024-01-25 00:00:00-08:00",
            metric="StepCount",
        )
        assert isinstance(samples, List)
        df = participant.metric_time_series(
            start_time="2024-01-24 00:00:00-08:00",
            end_time="2024-01-25 00:00:00-08:00",
            sample_rate=60,
            metric="StepCount",
        )
        assert df.shape == (1440, 1)

        # Metrics outside the group's shared data types must be denied.
        try:
            participant.metric_samples(
                start_time="2024-01-24 00:00:00-08:00",
                end_time="2024-01-25 00:00:00-08:00",
                metric="HeartRate",
            )
            assert False
        except Exception:
            assert True

        fulcra_client.leave_group(group_id)
        joined = fulcra_client.get_groups(subscribed_only=True)
        assert not any(g["id"] == group_id for g in joined)
    finally:
        fulcra_client.delete_group(group_id)

    try:
        fulcra_client.get_group(group_id)
        assert False
    except Exception:
        assert True


def test_group_data_access_boundaries(fulcra_client):
    """
    A group only grants access to its own data types, within its own time
    range, for its own participant IDs; everything else must be denied.
    """
    time_start = datetime.datetime.fromisoformat("2024-01-24 00:00:00-08:00")
    time_end = datetime.datetime.fromisoformat("2024-01-26 00:00:00-08:00")
    group = fulcra_client.create_group(
        title="fulcra-api-python boundary test",
        is_public=False,
        responsible_entity="Fulcra Dynamics",
        description="Temporary group created by the test suite; safe to delete.",
        fulcra_data_types=["StepCount"],
        group_url="https://fulcradynamics.com/",
        time_start=time_start,
        time_end=time_end,
    )
    group_id = group["id"]

    try:
        membership = fulcra_client.join_group(group_id)
        participant_id = membership["participant_id"]

        participant_ids = fulcra_client.get_group_participants(group_id)
        assert participant_ids == [participant_id]

        participant = fulcra_client.group_participant(group_id, participant_id)

        # Valid requests: shared metric, range inside the group's time range.
        samples = participant.metric_samples(
            start_time="2024-01-24 00:00:00-08:00",
            end_time="2024-01-25 00:00:00-08:00",
            metric="StepCount",
        )
        assert isinstance(samples, List)
        df = participant.metric_time_series(
            start_time="2024-01-24 06:00:00-08:00",
            end_time="2024-01-24 18:00:00-08:00",
            sample_rate=60,
            metric="StepCount",
        )
        assert df.shape == (720, 1)

        # Invalid requests must all be denied.
        denied_requests = [
            # entirely before the group's time range
            {"start_time": "2024-01-22 00:00:00-08:00",
             "end_time": "2024-01-23 00:00:00-08:00",
             "metric": "StepCount"},
            # entirely after the group's time range
            {"start_time": "2024-01-27 00:00:00-08:00",
             "end_time": "2024-01-28 00:00:00-08:00",
             "metric": "StepCount"},
            # straddling the start of the range
            {"start_time": "2024-01-23 00:00:00-08:00",
             "end_time": "2024-01-25 00:00:00-08:00",
             "metric": "StepCount"},
            # straddling the end of the range
            {"start_time": "2024-01-25 00:00:00-08:00",
             "end_time": "2024-01-27 00:00:00-08:00",
             "metric": "StepCount"},
            # inverted range
            {"start_time": "2024-01-25 00:00:00-08:00",
             "end_time": "2024-01-24 00:00:00-08:00",
             "metric": "StepCount"},
            # metric that is not part of the group
            {"start_time": "2024-01-24 00:00:00-08:00",
             "end_time": "2024-01-25 00:00:00-08:00",
             "metric": "HeartRate"},
        ]
        for request in denied_requests:
            with pytest.raises(HTTPError):
                participant.metric_samples(**request)
            with pytest.raises(HTTPError):
                participant.metric_time_series(sample_rate=60, **request)

        # A participant ID that does not exist in the group must be denied,
        # even for an otherwise-valid request.
        bogus = fulcra_client.group_participant(
            group_id, "13371337-1337-1337-81e7-a102ab7d3ff8"
        )
        with pytest.raises(HTTPError):
            bogus.metric_samples(
                start_time="2024-01-24 00:00:00-08:00",
                end_time="2024-01-25 00:00:00-08:00",
                metric="StepCount",
            )
    finally:
        fulcra_client.delete_group(group_id)


def test_get_groups_public(fulcra_client):
    groups = fulcra_client.get_groups()
    assert isinstance(groups, List)
    for group in groups:
        assert group["is_public"] is True


def test_group_jwks(fulcra_client):
    jwks = fulcra_client.get_group_jwks()
    assert isinstance(jwks, dict)
    assert "keys" in jwks
