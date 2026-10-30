"""Offline coverage for metadata updates through Click and the SDK."""

import io
import json
from email.message import Message
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
from click.testing import CliRunner

from fulcra_api.cli.data_types import data_type
from .conftest import offline_client

TYPE_ID = "Event/3982a39a-ed7b-444b-b54d-90134ac46309"


@pytest.fixture
def client():
    client = offline_client()
    client.get_fulcra_userid = lambda: "me"
    client.resolve_data_type = Mock(return_value=[{"id": TYPE_ID, "api_version": "v1"}])
    client.fulcra_api = Mock(
        return_value=b'{"id": "returned-id", "name": "Server name"}'
    )
    return client


@pytest.mark.parametrize(
    "base, changes",
    [
        ("Event", {"name": "New"}),
        ("Metric", {"description": "New text"}),
        ("Event", {"description": ""}),
        ("Metric", {"name": "New", "description": "Both"}),
    ],
)
def test_update_returns_sdk_result_with_only_supplied_fields(client, base, changes):
    type_id = TYPE_ID.replace("Event", base)
    client.resolve_data_type.return_value = [{"id": type_id, "api_version": "v1"}]
    args = ["update", type_id]
    for key, value in changes.items():
        args.extend([f"--{key}", value])
    result = CliRunner().invoke(data_type, args, obj=client)

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"id": "returned-id", "name": "Server name"}
    assert result.stderr == ""
    client.resolve_data_type.assert_called_once_with(
        type_id, api_version=None, fulcra_userid="me"
    )
    client.fulcra_api.assert_called_once_with(
        f"/input/v1/data_type/{type_id}", data=changes, method="PUT"
    )


def test_update_options(client):
    result = CliRunner().invoke(data_type, ["update", "--help"], obj=client)
    assert result.exit_code == 0
    assert "--name" in result.output and "--description" in result.output
    assert "--expected-description" not in result.output
    result = CliRunner().invoke(
        data_type,
        ["update", TYPE_ID, "--expected-description", "old", "--name", "New"],
        obj=client,
    )
    assert result.exit_code == 2
    assert "No such option" in result.output
    client.fulcra_api.assert_not_called()


@pytest.mark.parametrize(
    "args, message",
    [([], "Provide --name and/or --description"), (["--name", "  "], "can't be empty")],
)
def test_invalid_options_do_not_write(client, args, message):
    result = CliRunner().invoke(data_type, ["update", TYPE_ID, *args], obj=client)
    assert result.exit_code == 2
    assert message in result.output
    client.fulcra_api.assert_not_called()


@pytest.mark.parametrize(
    "type_id, version",
    [
        ("Event", "v1"),
        (TYPE_ID.replace("Event", "MomentAnnotation"), "v1alpha1"),
        ("Event/not-a-uuid", "v1"),
    ],
)
def test_invalid_target_does_not_write(client, type_id, version):
    client.resolve_data_type.return_value = [{"id": type_id, "api_version": version}]
    result = CliRunner().invoke(
        data_type, ["update", type_id, "--name", "New"], obj=client
    )
    assert result.exit_code == 1
    assert "<Event|Metric>/<UUID>" in result.output
    client.fulcra_api.assert_not_called()


def test_resolution_error_does_not_write(client):
    client.resolve_data_type.side_effect = ValueError("No data type found")
    result = CliRunner().invoke(
        data_type, ["update", TYPE_ID, "--name", "New"], obj=client
    )
    assert result.exit_code == 2
    assert "No data type found" in result.output
    client.fulcra_api.assert_not_called()


def test_requires_auth(client):
    client.fulcra_credentials = None
    result = CliRunner().invoke(
        data_type, ["update", TYPE_ID, "--name", "New"], obj=client
    )
    assert result.exit_code == 1
    assert "fulcra auth login" in result.output
    client.fulcra_api.assert_not_called()


def test_api_error_uses_normal_cli_error(client):
    client.fulcra_api.side_effect = HTTPError(
        "https://example.invalid",
        403,
        "Forbidden",
        Message(),
        io.BytesIO(b'{"detail":"Not your data type"}'),
    )
    result = CliRunner().invoke(
        data_type, ["update", TYPE_ID, "--name", "New"], obj=client
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert (
        f"Failed to update data type {TYPE_ID}: HTTP 403: Not your data type"
        in result.stderr
    )
    assert client.fulcra_api.call_count == 1
