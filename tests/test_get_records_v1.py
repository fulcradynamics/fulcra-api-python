"""Offline tests for `get-records` v1 data-type support."""

import io
from urllib.error import HTTPError

from click.testing import CliRunner

from fulcra_api.cli.commands import get_records
from fulcra_api.cli.utils import http_error_detail

from .conftest import offline_client

# 2024-06-01 -> 2024-06-02 UTC: 86400s window anchored at the end unix time.
DAY_RANGE = ["2024-06-01T00:00:00Z", "2024-06-02T00:00:00Z"]
EXPECTED_PROMQL = "HeartRate[86400s] @ 1717286400"


def _v1_client(entries, *, userid="me"):
    """An offline client whose catalog resolution and identity are stubbed."""
    client = offline_client()
    client.resolve_data_type = lambda *a, **k: entries
    client.get_fulcra_userid = lambda: userid
    return client


def _entry(id="HeartRate", record_type="metric", fulcra_userid="me"):
    return {
        "id": id,
        "api_version": "v1",
        "record_spec": {"type": record_type},
        "fulcra_userid": fulcra_userid,
    }


def test_v1_builds_promql_and_parses_jsonl():
    client = _v1_client([_entry()])
    captured = {}

    def fake_records(query, fulcra_userid=None):
        captured["query"] = query
        captured["fulcra_userid"] = fulcra_userid
        return b'{"a": 1}\n{"a": 2}\n'

    client.fulcra_v1_records = fake_records

    result = CliRunner().invoke(get_records, ["HeartRate", *DAY_RANGE], obj=client)

    assert result.exit_code == 0, result.output
    assert captured["query"] == EXPECTED_PROMQL
    # Same user, so no cross-user scoping is applied.
    assert captured["fulcra_userid"] is None
    # JSONL is re-emitted as one JSON object per line.
    assert result.output.splitlines() == ['{"a": 1}', '{"a": 2}']


def test_v1_passes_fulcra_userid_for_other_users_data():
    client = _v1_client([_entry(fulcra_userid="someone-else")], userid="me")
    captured = {}
    client.fulcra_v1_records = lambda query, fulcra_userid=None: (
        captured.update(fulcra_userid=fulcra_userid) or b""
    )

    result = CliRunner().invoke(get_records, ["HeartRate", *DAY_RANGE], obj=client)

    assert result.exit_code == 0, result.output
    assert captured["fulcra_userid"] == "someone-else"


def test_v1_latest_builds_bare_instant_vector():
    client = _v1_client([_entry()])
    captured = {}
    client.fulcra_v1_records = lambda query, fulcra_userid=None: (
        captured.update(query=query) or b'{"a": 1}\n'
    )

    result = CliRunner().invoke(get_records, ["HeartRate", "latest"], obj=client)

    assert result.exit_code == 0, result.output
    assert captured["query"] == "HeartRate"
    assert result.output.splitlines() == ['{"a": 1}']


def test_v1_rejects_group_participant_source():
    client = _v1_client([_entry()])
    client.fulcra_v1_records = lambda *a, **k: b""

    result = CliRunner().invoke(
        get_records,
        ["HeartRate", "1 day", "--group-id", "g", "--participant-id", "p"],
        obj=client,
    )

    assert result.exit_code != 0
    assert "Group participant queries are not supported" in result.output


USER_TYPE = "Event/3982a39a-ed7b-444b-b54d-90134ac46309"


def test_v1_user_defined_type_is_queried_by_name_matcher():
    client = _v1_client([_entry(id=USER_TYPE, record_type="event")])
    captured = {}
    client.fulcra_v1_records = lambda query, fulcra_userid=None: (
        captured.update(query=query) or b'{"foo": "bar"}\n'
    )

    result = CliRunner().invoke(get_records, [USER_TYPE, *DAY_RANGE], obj=client)

    assert result.exit_code == 0, result.output
    assert captured["query"] == f'{{__name__="{USER_TYPE}"}}[86400s] @ 1717286400'
    assert result.output.splitlines() == ['{"foo": "bar"}']


def test_v1_keeps_field_types_in_output():
    """numbers, booleans and nested values are echoed as JSON, not strings"""
    client = _v1_client([_entry(id=USER_TYPE, record_type="event")])
    client.fulcra_v1_records = lambda query, fulcra_userid=None: (
        b'{"score": 7, "ratio": 0.5, "done": true, "tags": ["a"], "meta": {"k": 1}}\n'
    )

    result = CliRunner().invoke(get_records, [USER_TYPE, "latest"], obj=client)

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        '{"score": 7, "ratio": 0.5, "done": true, "tags": ["a"], "meta": {"k": 1}}'
    ]


def _http_error(code, body: bytes):
    return HTTPError("https://api/data/v1/records", code, "error", {}, io.BytesIO(body))


def test_v1_query_error_shows_the_servers_reason():
    client = _v1_client([_entry()])

    def refuse(query, fulcra_userid=None):
        raise _http_error(422, b'{"detail": "function \'rate\' is not supported"}')

    client.fulcra_v1_records = refuse

    result = CliRunner().invoke(get_records, ["HeartRate", "1 day"], obj=client)

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert (
        "Failed to fetch HeartRate records (422): function 'rate' is not supported"
        in result.output
    )


def test_http_error_detail_formats():
    # FastAPI's usual error body
    assert http_error_detail(_http_error(401, b'{"detail": "access denied"}')) == (
        "access denied"
    )
    # request validation errors: one message per field
    body = b'{"detail": [{"msg": "Field required"}, {"msg": "Input should be a UUID"}]}'
    assert http_error_detail(_http_error(422, body)) == (
        "Field required; Input should be a UUID"
    )
    # not JSON: the body itself
    assert http_error_detail(_http_error(502, b"Bad Gateway")) == "Bad Gateway"
    # no body: the status line
    assert "500" in http_error_detail(_http_error(500, b""))

