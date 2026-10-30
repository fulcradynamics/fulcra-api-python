"""Metadata updates through Click and the existing SDK transport boundary."""

import json

import pytest
from click.testing import CliRunner

from fulcra_api.cli.data_types import data_type
from .conftest import offline_client

TYPE_ID = "Event/3982a39a-ed7b-444b-b54d-90134ac46309"


@pytest.mark.parametrize("expected", ["stale", ""])
def test_guard_mismatch_never_writes(expected):
    client, _, calls = client_with_type()
    result = CliRunner().invoke(
        data_type,
        ["update", TYPE_ID, "--name", "New", "--expected-description", expected],
        obj=client,
    )
    assert result.exit_code == 1
    assert "Description changed" in result.output
    assert [c[1] for c in calls] == ["GET"]


@pytest.mark.parametrize(
    "description, expected",
    [
        ("Original\ntext", " Original text "),
        ("", ""),
        (None, ""),
    ],
)
def test_guard_matches_catalog_description(description, expected):
    client, entry, calls = client_with_type()
    entry["description"] = description
    result = CliRunner().invoke(
        data_type,
        ["update", TYPE_ID, "--name", "New", "--expected-description", expected],
        obj=client,
    )
    assert result.exit_code == 0, result.output
    assert [c[1] for c in calls] == ["GET", "PUT", "GET"]


@pytest.mark.parametrize(
    "args",
    [
        [TYPE_ID],
        [TYPE_ID, "--name", "  "],
        ["Event", "--name", "New"],
        [TYPE_ID.replace("-", ""), "--name", "New"],
        [TYPE_ID.replace("Event", "MomentAnnotation"), "--name", "New"],
    ],
)
def test_invalid_input_before_auth(args):
    client, _, calls = client_with_type()
    client.fulcra_credentials = None
    client.get_fulcra_userid = lambda: pytest.fail("must not authenticate")
    result = CliRunner().invoke(data_type, ["update", *args], obj=client)
    assert result.exit_code == 2, result.output
    assert "No credentials" not in result.output
    assert calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"fulcra_userid": "other"},
        {"recordable": False},
        {"deprecated": True},
        {"deleted_at": "2026-01-01"},
        {"api_version": "v1alpha1"},
        {"id": "Event"},
    ],
)
def test_invalid_target_never_writes(change):
    client, entry, calls = client_with_type()
    entry.update(change)
    result = CliRunner().invoke(
        data_type, ["update", TYPE_ID, "--name", "New"], obj=client
    )
    assert result.exit_code == 1
    assert "active owned" in result.output
    assert [c[1] for c in calls] == ["GET"]


@pytest.mark.parametrize("rows", [[], [{}, {}]])
def test_missing_or_ambiguous_target(rows):
    client, _, calls = client_with_type()
    client.v1_catalog = lambda **kwargs: rows
    result = CliRunner().invoke(
        data_type, ["update", TYPE_ID, "--name", "New"], obj=client
    )
    assert result.exit_code == 1
    assert "Missing or ambiguous" in result.output
    assert calls == []


@pytest.mark.parametrize(
    "failure",
    [
        "write",
        "readback",
        "name",
        "description",
        "record_spec",
    ],
)
def test_uncertain_result_does_not_repeat_sdk_write(failure):
    client, entry, calls = client_with_type()
    transport = client.fulcra_api

    def failing_transport(path, method="GET", **kwargs):
        if method == "GET" and len(calls) == 2:
            if failure == "readback":
                calls.append((path, method, None, kwargs))
                raise OSError("read failed")
            if failure != "write":
                entry[failure] = "unexpected"
        response = transport(path, method=method, **kwargs)
        if method == "PUT" and failure == "write":
            raise OSError("response lost after write")
        return response

    client.fulcra_api = failing_transport
    result = CliRunner().invoke(
        data_type, ["update", TYPE_ID, "--name", "New"], obj=client
    )
    assert result.exit_code == 1, result.output
    output = json.loads(result.stdout)
    assert output["status"] == "uncertain"
    assert output["verified"] is False
    assert "reconcile" in output["reason"]
    assert sum(c[1] == "PUT" for c in calls) == 1
    assert len(calls) == (2 if failure == "write" else 3)


def client_with_type(type_id=TYPE_ID):
    client = offline_client()
    client.get_fulcra_userid = lambda: "me"
    entry = dict(
        id=type_id,
        fulcra_userid="me",
        api_version="v1",
        recordable=True,
        name="Old",
        description="Original\ntext",
        deprecated=False,
        tags=["keep"],
        record_spec={"schema": {"properties": {"x": {"type": "string"}}}},
    )
    calls = []

    def transport(path, method="GET", data=None, **kwargs):
        calls.append((path, method, data, kwargs))
        if method == "PUT":
            assert path == f"/input/v1/data_type/{type_id}"
            entry.update(data)
            return json.dumps(entry).encode()
        assert path == "/data/v1/catalog"
        assert kwargs == {"query": {"data_type": type_id, "fulcra_userid": "me"}}
        return json.dumps([entry]).encode()

    client.fulcra_api = transport
    return client, entry, calls


@pytest.mark.parametrize(
    "base, changes",
    [
        ("Event", {"name": "New"}),
        ("Metric", {"description": "New text"}),
        ("Event", {"description": ""}),
        ("Metric", {"name": "New", "description": "Both"}),
    ],
)
def test_update_metadata_and_read_back(base, changes):
    type_id = TYPE_ID.replace("Event", base)
    client, entry, calls = client_with_type(type_id)
    args = ["update", type_id]
    for key, value in changes.items():
        args.extend([f"--{key}", value])
    result = CliRunner().invoke(data_type, args, obj=client)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == dict(
        status="updated", verified=True, data_type=type_id, **changes
    )
    assert [c[1] for c in calls] == ["GET", "PUT", "GET"]
    assert calls[1][2] == changes
    assert entry["name"] == changes.get("name", "Old")
    assert entry["description"] == changes.get("description", "Original\ntext")
