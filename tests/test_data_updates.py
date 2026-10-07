"""Offline tests for `data_updates` and the `data-updates` command."""

import json
from urllib.error import HTTPError, URLError

import pytest
from click.testing import CliRunner

from fulcra_api.cli.commands import data_updates as data_updates_command

from .conftest import capture_request, offline_client

ME = "4f7e3d16-62a2-4c70-9511-0aae86a3de44"
BOB = "5ce6549b-91ff-4413-b326-93722f3cbbaf"
CAROL = "9e1c0d3a-2222-4c70-9511-0aae86a3de44"
QUIET = "9e1c0d3a-3333-4c70-9511-0aae86a3de44"

START, END = "2026-02-01 00:00:00Z", "2026-02-03 00:00:00Z"


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


def _grant(uid, grant_type="user", name=None):
    return {
        "grant_type": grant_type,
        "sharing_fulcra_userid": uid,
        "sharing_fulcra_user_name": name or f"name of {uid[:4]}",
    }


def _sharing_client(grants, updates_by_user, own=ME):
    """A client whose /data/v1/updates answers from `updates_by_user`, keyed by
    the `fulcra_userid` query (None for the caller's own updates).  A value
    that is an exception is raised instead.  Records every updates request."""
    client = offline_client()
    client.get_fulcra_userid = lambda: own
    client.get_shared_datasets = lambda: grants
    requests = []

    def fake_fulcra_api(url_path, method="GET", query=None, **kwargs):
        assert url_path == "/data/v1/updates"
        uid = (query or {}).get("fulcra_userid")
        requests.append(uid)
        answer = updates_by_user.get(uid, {"data_types": {}, "file_changes": []})
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer).encode()

    client.fulcra_api = fake_fulcra_api
    return client, requests


def test_include_shared_checks_each_person_once():
    grants = [
        {"grant_type": "self", "sharing_fulcra_userid": ME},
        _grant(BOB, name="Bob"),
        _grant(BOB, grant_type="group", name="Bob"),  # same person via a group
        _grant(CAROL, name="Carol"),
        _grant(QUIET),
        _grant(ME, grant_type="group"),  # the caller's own share to a group
    ]
    updates = {
        None: {"data_types": {"StepCount": 3}, "file_changes": []},
        BOB: {"data_types": {"Event/aaa": 2}, "file_changes": []},
        CAROL: {"data_types": {}, "file_changes": [{"name": "notes.md"}]},
    }
    client, requests = _sharing_client(grants, updates)

    result = client.data_updates(START, END, include_shared=True)

    assert requests == [None, BOB, CAROL, QUIET]
    assert result["data_types"] == {"StepCount": 3}
    assert result["shared"] == {
        BOB: {"name": "Bob", "data_types": {"Event/aaa": 2}, "file_changes": []},
        CAROL: {
            "name": "Carol",
            "data_types": {},
            "file_changes": [{"name": "notes.md"}],
        },
    }
    assert result["peers_checked"] == 3
    assert "peers_skipped" not in result


def test_include_shared_reports_failures_per_person():
    grants = [_grant(BOB, name="Bob"), _grant(CAROL, name="Carol")]
    updates = {
        BOB: HTTPError("url", 403, "Forbidden", None, None),
        CAROL: URLError("timed out"),
    }
    client, _ = _sharing_client(grants, updates)

    shared = client.data_updates(START, END, include_shared=True)["shared"]

    assert shared == {
        BOB: {"name": "Bob", "error": "HTTP 403"},
        CAROL: {"name": "Carol", "error": "timeout"},
    }


PEERS = [f"00000000-0000-4000-8000-{i:012d}" for i in range(25)]


def test_include_shared_checks_everyone_by_default():
    client, requests = _sharing_client([_grant(p) for p in PEERS], {})

    result = client.data_updates(START, END, include_shared=True)

    assert requests == [None] + PEERS
    assert result["peers_checked"] == len(PEERS)
    assert "peers_skipped" not in result


def test_max_peers_caps_the_people_checked():
    client, requests = _sharing_client([_grant(p) for p in PEERS], {})

    result = client.data_updates(START, END, include_shared=True, max_peers=20)

    assert requests == [None] + PEERS[:20]
    assert result["peers_checked"] == 20
    assert result["peers_skipped"] == PEERS[20:]
    assert result["shared"] == {}


def test_max_peers_zero_checks_nobody_but_lists_them():
    client, requests = _sharing_client([_grant(BOB), _grant(CAROL)], {})

    result = client.data_updates(START, END, include_shared=True, max_peers=0)

    assert requests == [None]
    assert result["peers_checked"] == 0
    assert result["peers_skipped"] == [BOB, CAROL]


def test_negative_max_peers_is_refused():
    client, requests = _sharing_client([], {})

    with pytest.raises(ValueError):
        client.data_updates(START, END, include_shared=True, max_peers=-1)
    assert requests == []


def test_include_shared_without_shares_still_returns_own_updates():
    client, requests = _sharing_client(
        [{"grant_type": "self", "sharing_fulcra_userid": ME}],
        {None: {"data_types": {"HeartRate": 5}, "file_changes": []}},
    )

    result = client.data_updates(START, END, include_shared=True)

    assert requests == [None]
    assert result == {
        "data_types": {"HeartRate": 5},
        "file_changes": [],
        "shared": {},
        "peers_checked": 0,
    }


def test_include_shared_and_user_id_are_exclusive():
    client, requests = _sharing_client([], {})

    with pytest.raises(ValueError):
        client.data_updates(START, END, fulcra_userid=BOB, include_shared=True)
    assert requests == []


def test_cli_include_shared():
    client, requests = _sharing_client(
        [_grant(BOB, name="Bob")],
        {BOB: {"data_types": {"Event/aaa": 1}, "file_changes": []}},
    )

    result = CliRunner().invoke(
        data_updates_command, ["1 hour", "--include-shared"], obj=client
    )

    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert {"start_time", "end_time", "data_types", "file_changes"} <= set(out)
    assert out["shared"][BOB]["data_types"] == {"Event/aaa": 1}
    assert out["peers_checked"] == 1
    assert requests == [None, BOB]


def test_cli_without_include_shared_is_unchanged():
    client, requests = _sharing_client([_grant(BOB)], {})

    result = CliRunner().invoke(data_updates_command, ["1 hour"], obj=client)

    assert result.exit_code == 0, result.output
    assert "shared" not in json.loads(result.output)
    assert requests == [None]


def test_cli_rejects_user_id_with_include_shared():
    client, requests = _sharing_client([], {})

    result = CliRunner().invoke(
        data_updates_command,
        ["1 hour", "--include-shared", "--user-id", BOB],
        obj=client,
    )

    assert result.exit_code == 2
    assert "not both" in result.output
    assert requests == []
