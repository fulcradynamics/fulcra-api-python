"""
Offline tests for CLI inputs that are empty (usually an unset shell variable)
or otherwise can't mean what the user wants. Each is refused up front rather
than quietly changing what the command does.
"""

import io
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

import click
import pytest
from click.testing import CliRunner

from fulcra_api.cli.commands import catalog, get_records, list_calendars
from fulcra_api.cli.data_types import (
    data_type_archive,
    data_type_create,
    restore_data_type,
)
from fulcra_api.cli.files import file_list
from fulcra_api.cli.tags import tag
from fulcra_api.cli.utils import error_message, reject_blank, valid_user_id

from .conftest import offline_client

BLANKS = ["", "   "]


def _no_network_client():
    """An offline client that fails the test if anything reaches the API."""
    client = offline_client()
    client.get_fulcra_userid = lambda: "me"

    def fail(*a, **k):
        pytest.fail("the command made a request")

    client.fulcra_api = fail
    return client


def _refused(result, message):
    assert result.exit_code == 2, result.output
    assert message in result.output


# --- reject_blank -----------------------------------------------------------


def test_reject_blank_leaves_real_and_missing_values_alone():
    ctx = click.Context(click.Command("c"))
    param = click.Option(["--x"])
    assert reject_blank(ctx, param, None) is None
    assert reject_blank(ctx, param, "abc") == "abc"
    assert reject_blank(ctx, param, ("a", "b")) == ("a", "b")
    with pytest.raises(click.BadParameter):
        reject_blank(ctx, param, ("a", ""))


# --- 1. --user-id -----------------------------------------------------------


@pytest.mark.parametrize("blank", BLANKS)
def test_blank_user_id_is_refused_rather_than_reading_your_own_data(blank):
    result = CliRunner().invoke(
        get_records,
        ["HeartRate", "1 day", "--user-id", blank],
        obj=_no_network_client(),
    )
    _refused(result, "can't be empty")


@pytest.mark.parametrize(
    "command, args",
    [(catalog, []), (file_list, ["/"])],
    ids=["catalog", "file list"],
)
def test_blank_user_id_is_refused_on_other_commands(command, args):
    result = CliRunner().invoke(
        command, [*args, "--user-id", ""], obj=_no_network_client()
    )
    _refused(result, "can't be empty")


# --- 2. time ranges ---------------------------------------------------------


def _resolving_client():
    """Resolves HeartRate, but fails the test if any records are fetched.
    (DATA_TYPE is looked up while arguments are parsed, before the range check.)"""
    client = _no_network_client()
    client.resolve_data_type = lambda *a, **k: [
        {
            "id": "HeartRate",
            "api_version": "v1",
            "record_spec": {"type": "metric"},
            "fulcra_userid": "me",
        }
    ]
    return client


def test_range_ending_before_it_starts_is_refused():
    result = CliRunner().invoke(
        get_records,
        ["HeartRate", "2026-09-25T00:00:00Z", "2026-09-24T00:00:00Z"],
        obj=_resolving_client(),
    )
    _refused(result, "TIME_RANGE ends before it starts")


def test_relative_range_in_the_future_is_refused():
    result = CliRunner().invoke(
        get_records, ["HeartRate", "in 2 days"], obj=_resolving_client()
    )
    _refused(result, "TIME_RANGE ends before it starts")


def test_valid_and_empty_windows_still_run():
    client = _resolving_client()
    client.fulcra_v1_records = lambda query, fulcra_userid=None: b""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for args in (
        [(now - timedelta(days=1)).isoformat(), now.isoformat()],
        [now.isoformat(), now.isoformat()],  # an empty window isn't an error
        ["1 day"],
        ["latest"],
    ):
        result = CliRunner().invoke(get_records, ["HeartRate", *args], obj=client)
        assert result.exit_code == 0, (args, result.output)


# --- 3. data-type create ----------------------------------------------------


@pytest.mark.parametrize("blank", BLANKS)
def test_create_refuses_a_blank_name_or_base_type(blank):
    runner = CliRunner()
    for args in (["Event", blank, "-d", "x"], [blank, "Name", "-d", "x"]):
        result = runner.invoke(data_type_create, args, obj=_no_network_client())
        _refused(result, "can't be empty")


@pytest.mark.parametrize("blank", BLANKS)
def test_create_v1_refuses_a_blank_description(blank):
    client = _no_network_client()
    client.v1_catalog = lambda **k: [
        {
            "id": "Event",
            "api_version": "v1",
            "categories": ["base_type"],
            "record_spec": {"type": "event"},
        }
    ]

    result = CliRunner().invoke(
        data_type_create, ["Event", "Name", "-d", blank], obj=client
    )

    assert result.exit_code != 0
    assert "A description is required" in result.output


# --- 4. tag create ----------------------------------------------------------


@pytest.mark.parametrize(
    "args", [[], [""], ["ok", "  "]], ids=["none", "blank", "one-blank"]
)
def test_tag_create_refuses_missing_or_blank_names(args):
    result = CliRunner().invoke(tag, ["create", *args], obj=_no_network_client())

    assert result.exit_code == 2, result.output


# --- 5. catalog -d ----------------------------------------------------------


def test_catalog_refuses_a_blank_data_type_filter():
    result = CliRunner().invoke(catalog, ["-d", ""], obj=_no_network_client())
    _refused(result, "can't be empty")



# --- 6. --user-id must be a UUID --------------------------------------------

USER_ID = "4f7e3d16-62a2-4c70-9511-0aae86a3de44"


def test_valid_user_id_accepts_uuids_and_nothing_else():
    ctx = click.Context(click.Command("c"))
    param = click.Option(["--user-id"])
    assert valid_user_id(ctx, param, None) is None
    assert valid_user_id(ctx, param, USER_ID) == USER_ID
    assert valid_user_id(ctx, param, (USER_ID,)) == (USER_ID,)
    for bad in ("not-a-uuid", (USER_ID, "nope")):
        with pytest.raises(click.BadParameter, match="must be a Fulcra user ID"):
            valid_user_id(ctx, param, bad)
    with pytest.raises(click.BadParameter, match="can't be empty"):
        valid_user_id(ctx, param, "")


def test_non_uuid_user_id_is_refused_as_itself_not_as_data_type():
    result = CliRunner().invoke(
        get_records,
        ["HeartRate", "1 day", "--user-id", "not-a-uuid"],
        obj=_no_network_client(),
    )
    _refused(result, "Invalid value for '--user-id': must be a Fulcra user ID")
    assert "Invalid value for 'DATA_TYPE'" not in result.output


# --- 7. the server's reason in error messages -------------------------------


def _http_error(code, body: bytes):
    return HTTPError("https://api/x", code, "error", {}, io.BytesIO(body))


def test_error_message_shows_the_servers_reason():
    assert error_message(_http_error(422, b'{"detail": "id must be a UUID"}')) == (
        "HTTP 422: id must be a UUID"
    )
    # no body: just the status line, not repeated
    assert error_message(_http_error(500, b"")) == "HTTP Error 500: error"
    # not an HTTP error: its own message
    assert error_message(ValueError("bad value")) == "bad value"


def test_command_errors_include_the_servers_reason():
    client = _no_network_client()

    def refuse():
        raise _http_error(403, b'{"detail": "calendars are not shared"}')

    client.calendars = refuse

    result = CliRunner().invoke(list_calendars, [], obj=client)

    assert result.exit_code == 1
    assert "HTTP 403: calendars are not shared" in result.output


# --- 8. archiving/restoring a built-in type ---------------------------------


@pytest.mark.parametrize("type_id", ["HeartRate", "Event"])
def test_archive_refuses_built_in_types_clearly(type_id):
    client = _no_network_client()
    client.resolve_data_type = lambda *a, **k: [
        {"id": type_id, "api_version": "v1", "fulcra_userid": "me"}
    ]

    result = CliRunner().invoke(data_type_archive, [type_id], obj=client)

    assert result.exit_code == 1
    message = f"{type_id} is a built-in data type, so it can't be archived"
    assert message in result.output


def test_restore_refuses_built_in_types_without_looking_them_up():
    result = CliRunner().invoke(
        restore_data_type, ["HeartRate"], obj=_no_network_client()
    )

    assert result.exit_code == 1
    assert "HeartRate is a built-in data type, so it can't be restored" in result.output
    assert "is not archived" not in result.output


# --- 9. --fields must add fields --------------------------------------------


@pytest.mark.parametrize(
    "fields",
    ['{"a": 1}', '{"properties": {}}', '{"properties": ["mood"]}'],
    ids=["no-properties", "empty-properties", "properties-not-an-object"],
)
def test_create_refuses_fields_without_properties(fields):
    client = _no_network_client()
    client.v1_catalog = lambda **k: [
        {
            "id": "Event",
            "api_version": "v1",
            "categories": ["base_type"],
            "record_spec": {"type": "event"},
        }
    ]

    result = CliRunner().invoke(
        data_type_create, ["Event", "Name", "-d", "x", "--fields", fields], obj=client
    )

    assert result.exit_code != 0
    assert 'must define the fields to add under "properties"' in result.output
