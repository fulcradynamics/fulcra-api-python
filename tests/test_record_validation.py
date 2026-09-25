"""
Offline tests for the record checks that run before an upload: timestamps the
ETL couldn't parse and fields it would drop, both of which would otherwise be
lost silently after the upload succeeded.
"""

import pytest

from fulcra_api.record_validation import (
    check_date_time,
    is_unknown_fields_error,
    strict_schema,
)

from .conftest import offline_client

# --- the date-time grammar, per API version ---------------------------------

# Accepted by both ETLs (v1-etl-task and annotation-transform-task).
BOTH_ACCEPT = [
    "2026-09-25T12:34:56Z",
    "2026-09-25T12:34:56+00:00",
    "2026-09-25T12:34:56-07:00",
    "2026-09-25T12:34:56+0530",
    "2026-09-25t12:34:56z",
    "2026-09-25 12:34:56Z",
    "2026-09-25T12:34Z",
    "2026-09-25T12:34:56.1Z",
    "2026-09-25T12:34:56.123456Z",
    "2026-09-25T12:34:56.123456789Z",  # nanoseconds
    "2026-09-25T12:34:56.999999999Z",  # rounds past the second
    "2026-09-25T12:34:56",  # no offset: read as UTC
    "2026-09-25",
    "2024-02-29T00:00:00Z",
]

# Refused by both.
BOTH_REJECT = [
    "",
    "not a time",
    "1790000000",  # epoch seconds
    "2026-13-01T00:00:00Z",
    "2026-02-30T00:00:00Z",
    "2025-02-29T00:00:00Z",
    "2026-09-25T24:00:00Z",
    "2026-09-25T12:60:00Z",
    "2026-09-25T12:34:60Z",
    "2026-09-25T12:34:56+24:00",
    "2026-09-25T12:34:56.Z",
    "2026-09-25T12Z",
    "2026-9-25T12:34:56Z",
    " 2026-09-25T12:34:56Z",
    "2026-09-25T12:34:56Z ",
    "2026-09-25T12:34:56 UTC",
]

# An hours-only offset, as Postgres writes it: v1 only.
V1_ONLY = ["2026-09-25T12:34:56-07", "2026-09-25T12:34:56+00", "2026-09-25 12:34:56.5+05"]


@pytest.mark.parametrize("api_version", ["v1", "v1alpha1"])
@pytest.mark.parametrize("value", BOTH_ACCEPT)
def test_date_times_both_etls_parse_are_accepted(value, api_version):
    check_date_time(value, api_version)


@pytest.mark.parametrize("api_version", ["v1", "v1alpha1"])
@pytest.mark.parametrize("value", BOTH_REJECT)
def test_date_times_neither_etl_parses_are_refused(value, api_version):
    with pytest.raises(ValueError):
        check_date_time(value, api_version)


@pytest.mark.parametrize("value", V1_ONLY)
def test_hour_only_offsets_are_v1_only(value):
    check_date_time(value, "v1")
    with pytest.raises(ValueError, match="needs minutes for v1alpha1"):
        check_date_time(value, "v1alpha1")


# --- strict_schema ----------------------------------------------------------

PROPS = {"properties": {"a": {"type": "string"}}}


def test_strict_schema_refuses_undeclared_fields_on_a_copy():
    schema = {"type": "object", **PROPS}
    strict = strict_schema(schema)
    assert strict["additionalProperties"] is False
    assert "additionalProperties" not in schema


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object"},
        {"properties": ["a"]},
        {**PROPS, "additionalProperties": True},
        {**PROPS, "additionalProperties": {"type": "string"}},
        {**PROPS, "allOf": [{"properties": {"b": {}}}]},
        {**PROPS, "anyOf": [{}]},
        {**PROPS, "oneOf": [{}]},
        {**PROPS, "$ref": "#/$defs/x"},
        {**PROPS, "patternProperties": {"^x-": {}}},
    ],
    ids=[
        "no-properties",
        "properties-not-an-object",
        "already-open",
        "already-typed",
        "allOf",
        "anyOf",
        "oneOf",
        "$ref",
        "patternProperties",
    ],
)
def test_strict_schema_leaves_schemas_it_cant_safely_close(schema):
    assert strict_schema(schema) is schema


# --- validate_records -------------------------------------------------------

EVENT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["start_time"],
    "properties": {
        "id": {"type": "string", "format": "uuid"},
        "start_time": {"type": "string", "format": "date-time"},
        # nullable, as Pydantic writes every optional field
        "end_time": {
            "anyOf": [{"type": "string", "format": "date-time"}, {"type": "null"}]
        },
        "mood": {"type": "string"},
        "details": {"type": "object", "properties": {"x": {"type": "number"}}},
        "sources": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}

START = "2026-09-25T12:00:00Z"


def _client(schema=EVENT_SCHEMA):
    client = offline_client()
    seen = {}

    def fake_schema(data_type, api_version):
        seen.update(data_type=data_type, api_version=api_version)
        return schema

    client.v1_catalog_schema = fake_schema
    return client, seen


def test_valid_records_have_no_errors():
    client, seen = _client()
    records = [{"start_time": START, "mood": "calm", "details": {"x": 1}}]

    assert client.validate_records("Event/abc", records, "v1") == []
    assert seen == {"data_type": "Event/abc", "api_version": "v1"}


def test_undeclared_fields_are_refused_by_default():
    client, _ = _client()

    errors = client.validate_records(
        "Event/abc", [{"start_time": START}, {"start_time": START, "mod": "x"}], "v1"
    )

    assert len(errors) == 1
    idx, message, error = errors[0]
    assert idx == 1
    assert is_unknown_fields_error(error)
    assert message == (
        "field 'mod' is not part of this data type and would be dropped; its fields "
        "are: details, end_time, id, mood, sources, start_time, tags"
    )


def test_several_undeclared_fields_are_named_together():
    client, _ = _client()

    [(_, message, _)] = client.validate_records(
        "Event/abc", [{"start_time": START, "b": 1, "a": 2}], "v1"
    )

    assert message.startswith("fields 'a', 'b' are not part of this data type")


def test_undeclared_fields_can_be_allowed():
    client, _ = _client()
    records = [{"start_time": START, "mod": "x"}]

    assert client.validate_records("Event/abc", records, "v1", allow_unknown_fields=True) == []


def test_nested_objects_are_not_made_strict():
    client, _ = _client()
    records = [{"start_time": START, "details": {"x": 1, "extra": True}}]

    assert client.validate_records("Event/abc", records, "v1") == []


def test_schemas_that_cant_be_closed_still_validate_the_rest():
    schema = {**EVENT_SCHEMA, "allOf": [{"required": ["mood"]}]}
    client, _ = _client(schema)

    errors = client.validate_records("Event/abc", [{"start_time": START, "mod": "x"}], "v1")

    # the missing mood is reported; the undeclared field can't be judged
    assert [e[2].validator for e in errors] == ["required"]


def test_invalid_timestamps_are_refused_with_a_reason():
    client, _ = _client()

    [(idx, message, error)] = client.validate_records(
        "Event/abc", [{"start_time": "2026-02-30T00:00:00Z"}], "v1"
    )

    assert idx == 0
    assert error.validator == "format"
    assert message.startswith("'2026-02-30T00:00:00Z' is not a 'date-time': not a real date-time")
    assert message.endswith("(path: start_time)")


def test_timestamps_are_checked_for_the_data_types_api_version():
    client, _ = _client()
    records = [{"start_time": "2026-09-25T12:00:00+00"}]

    assert client.validate_records("Event/abc", records, "v1") == []
    [(_, message, _)] = client.validate_records("Event/abc", records, "v1alpha1")
    assert "needs minutes for v1alpha1" in message


def test_other_formats_are_still_checked():
    client, _ = _client()

    [(_, message, error)] = client.validate_records(
        "Event/abc", [{"start_time": START, "id": "not-a-uuid"}], "v1"
    )

    assert error.validator == "format"
    assert "is not a 'uuid'" in message


def test_every_error_is_reported_with_undeclared_fields_last():
    client, _ = _client()
    records = [
        {"start_time": "garbage", "mod": "x", "mood": 3},
        {"start_time": START},
        {"mood": "calm"},
    ]

    errors = client.validate_records("Event/abc", records, "v1")

    found = [(idx, e.validator) for idx, _, e in errors]
    # all of them, per record in order, with the dropped field after the real problems
    assert sorted(found[:2]) == [(0, "format"), (0, "type")]
    assert found[2:] == [(0, "additionalProperties"), (2, "required")]


def test_errors_inside_nullable_fields_explain_the_real_problem():
    client, _ = _client()

    [(_, message, error)] = client.validate_records(
        "Event/abc", [{"start_time": START, "end_time": "not a time"}], "v1"
    )

    assert error.validator == "anyOf"
    assert message.startswith("'not a time' is not a 'date-time': expected an ISO 8601")
    assert message.endswith("(path: end_time)")
    assert client.validate_records(
        "Event/abc", [{"start_time": START, "end_time": None}], "v1"
    ) == []
