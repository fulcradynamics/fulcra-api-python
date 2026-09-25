"""Offline tests for the `data-type` create/archive/restore CLI dispatch."""

import uuid

from click.testing import CliRunner

import json

from fulcra_api.cli.data_types import (
    data_type_archive,
    data_type_create,
    get_schema,
    restore_data_type,
)

from .conftest import offline_client


def _client():
    client = offline_client()
    client.get_fulcra_userid = lambda: "me"
    return client


def _base_type(id, api_version, record_type):
    return {
        "id": id,
        "categories": ["base_type"],
        "api_version": api_version,
        "record_spec": {"type": record_type},
    }


def _raise_value_error(*a, **k):
    # Stands in for an archived type that no longer resolves in the catalog list.
    raise ValueError("not found")


# --- create ------------------------------------------------------------------


def test_create_v1_metric_dispatches_to_module():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Metric", "v1", "metric")]
    captured = {}
    client.create_data_type = lambda base_type, body: (
        captured.update(base_type=base_type, body=body) or {"id": "Metric/uuid"}
    )

    result = CliRunner().invoke(
        data_type_create,
        ["Metric", "Resting HR", "-d", "hr", "--unit", "bpm"],
        obj=client,
    )

    assert result.exit_code == 0, result.output
    assert captured["base_type"] == "Metric"
    assert captured["body"] == {
        "name": "Resting HR",
        "description": "hr",
        "record_spec": {"unit": "bpm"},
    }


def test_create_v1_requires_description():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Metric", "v1", "metric")]
    client.create_data_type = lambda *a, **k: {"id": "x"}

    result = CliRunner().invoke(data_type_create, ["Metric", "Steps"], obj=client)

    assert result.exit_code != 0
    assert "description is required" in result.output


def test_create_v1_passes_fields_schema():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Event", "v1", "event")]
    captured = {}
    client.create_data_type = lambda base_type, body: (
        captured.update(body=body) or {"id": "Event/uuid"}
    )

    result = CliRunner().invoke(
        data_type_create,
        [
            "Event",
            "Nap",
            "-d",
            "nap",
            "--fields",
            '{"properties": {"quality": {"type": "string"}}}',
        ],
        obj=client,
    )

    assert result.exit_code == 0, result.output
    assert "schema" in captured["body"]["record_spec"]


def test_create_v1_rejects_annotation_only_flag():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Event", "v1", "event")]
    client.create_data_type = lambda *a, **k: {"id": "x"}

    result = CliRunner().invoke(
        data_type_create, ["Event", "Nap", "--tag", "sleep"], obj=client
    )

    assert result.exit_code != 0
    assert "cannot be used with v1 data type" in result.output


def test_create_v1_metric_aggregation_aliases_set_aggregation():
    for flag in ("--aggregation", "--agg", "--kind", "-k"):
        client = _client()
        client.v1_catalog = lambda **k: [_base_type("Metric", "v1", "metric")]
        captured = {}
        client.create_data_type = lambda base_type, body: (
            captured.update(body=body) or {"id": "Metric/uuid"}
        )

        result = CliRunner().invoke(
            data_type_create,
            ["Metric", "Steps", "-d", "d", flag, "cumulative"],
            obj=client,
        )

        assert result.exit_code == 0, f"{flag}: {result.output}"
        assert captured["body"]["record_spec"]["aggregation"] == "cumulative", flag


def test_create_v1_metric_builds_scale():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Metric", "v1", "metric")]
    captured = {}
    client.create_data_type = lambda base_type, body: (
        captured.update(body=body) or {"id": "Metric/uuid"}
    )

    result = CliRunner().invoke(
        data_type_create,
        ["Metric", "Mood", "-d", "d", "--scale-min", "0", "--scale-max", "10"],
        obj=client,
    )

    assert result.exit_code == 0, result.output
    assert captured["body"]["record_spec"]["scale"] == {"min": 0, "max": 10, "step": 1}


def test_create_v1_metric_scale_requires_min_and_max():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Metric", "v1", "metric")]
    client.create_data_type = lambda *a, **k: {"id": "x"}

    result = CliRunner().invoke(
        data_type_create, ["Metric", "Mood", "--scale-min", "0"], obj=client
    )

    assert result.exit_code != 0
    assert "must be provided together" in result.output


def test_create_v1_metric_builds_value_map():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Metric", "v1", "metric")]
    captured = {}
    client.create_data_type = lambda base_type, body: (
        captured.update(body=body) or {"id": "Metric/uuid"}
    )

    result = CliRunner().invoke(
        data_type_create,
        ["Metric", "Switch", "-d", "d", "--value-map", "0=off", "--value-map", "1=on"],
        obj=client,
    )

    assert result.exit_code == 0, result.output
    assert captured["body"]["record_spec"]["value_map"] == {0: "off", 1: "on"}


def test_create_v1_metric_rejects_malformed_value_map():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Metric", "v1", "metric")]
    client.create_data_type = lambda *a, **k: {"id": "x"}

    result = CliRunner().invoke(
        data_type_create, ["Metric", "Switch", "--value-map", "nope"], obj=client
    )

    assert result.exit_code != 0
    assert "INT=LABEL" in result.output


def test_create_v1_event_rejects_aggregation():
    client = _client()
    client.v1_catalog = lambda **k: [_base_type("Event", "v1", "event")]
    client.create_data_type = lambda *a, **k: {"id": "x"}

    result = CliRunner().invoke(
        data_type_create, ["Event", "Nap", "-d", "d", "--agg", "discrete"], obj=client
    )

    assert result.exit_code != 0
    assert "may only be set for the Metric" in result.output


def test_create_v1alpha1_rejects_scale_and_value_map():
    for args in (["--scale-min", "0"], ["--value-map", "0=off"]):
        client = _client()
        client.v1_catalog = lambda **k: [
            _base_type("NumericAnnotation", "v1alpha1", "metric")
        ]

        result = CliRunner().invoke(
            data_type_create, ["NumericAnnotation", "X", *args], obj=client
        )

        assert result.exit_code != 0, args
        assert "only valid for v1 Metric" in result.output, args


def test_create_v1alpha1_rejects_fields_option():
    client = _client()
    client.v1_catalog = lambda **k: [
        _base_type("MomentAnnotation", "v1alpha1", "event")
    ]

    result = CliRunner().invoke(
        data_type_create, ["MomentAnnotation", "X", "--fields", "{}"], obj=client
    )

    assert result.exit_code != 0
    assert "--fields is only valid for v1" in result.output


# --- archive -----------------------------------------------------------------


def test_archive_v1_marks_deprecated():
    client = _client()
    type_id = f"Metric/{uuid.uuid4()}"
    client.resolve_data_type = lambda *a, **k: [{"id": type_id, "api_version": "v1"}]
    captured = {}
    client.update_data_type = lambda base_type, id, body: (
        captured.update(base_type=base_type, id=id, body=body) or {}
    )

    result = CliRunner().invoke(data_type_archive, [type_id], obj=client)

    assert result.exit_code == 0, result.output
    assert captured["base_type"] == "Metric"
    assert captured["body"] == {"deprecated": True}


def test_archive_v1alpha1_deletes_annotation():
    client = _client()
    ann_uuid = str(uuid.uuid4())
    type_id = f"MomentAnnotation/{ann_uuid}"
    client.resolve_data_type = lambda *a, **k: [
        {"id": type_id, "api_version": "v1alpha1"}
    ]
    captured = {}
    client.delete_annotation = lambda annotation_id: captured.update(id=annotation_id)

    result = CliRunner().invoke(data_type_archive, [type_id], obj=client)

    assert result.exit_code == 0, result.output
    assert captured["id"] == ann_uuid


# --- restore -----------------------------------------------------------------


def test_restore_v1_clears_deprecated():
    client = _client()
    client.resolve_data_type = _raise_value_error
    type_id = f"Metric/{uuid.uuid4()}"
    captured = {}
    client.update_data_type = lambda base_type, id, body: (
        captured.update(base_type=base_type, id=id, body=body) or {"id": type_id}
    )

    result = CliRunner().invoke(restore_data_type, [type_id], obj=client)

    assert result.exit_code == 0, result.output
    assert captured["base_type"] == "Metric"
    assert captured["body"] == {"deprecated": False}


def test_restore_v1alpha1_restores_annotation():
    client = _client()
    client.resolve_data_type = _raise_value_error
    ann_uuid = str(uuid.uuid4())
    captured = {}
    client.restore_annotation = lambda annotation_id: (
        captured.update(id=annotation_id) or {"id": "x"}
    )

    result = CliRunner().invoke(
        restore_data_type, [f"MomentAnnotation/{ann_uuid}"], obj=client
    )

    assert result.exit_code == 0, result.output
    assert captured["id"] == ann_uuid


# --- schema ------------------------------------------------------------------

USER_TYPE = "Event/3982a39a-ed7b-444b-b54d-90134ac46309"


def _user_type(schema=None, fulcra_userid="me"):
    record_spec = {"type": "event"}
    if schema is not None:
        record_spec["schema"] = schema
    return {
        "id": USER_TYPE,
        "api_version": "v1",
        "record_spec": record_spec,
        "fulcra_userid": fulcra_userid,
    }


def test_schema_of_a_user_defined_type_from_its_catalog_entry():
    schema = {"properties": {"foo": {"type": "string"}}}
    client = _client()
    client.resolve_data_type = lambda *a, **k: [_user_type(schema)]

    result = CliRunner().invoke(get_schema, [USER_TYPE], obj=client)

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == schema


def test_schema_of_a_user_defined_type_is_fetched_by_its_full_id():
    client = _client()
    client.resolve_data_type = lambda *a, **k: [_user_type(fulcra_userid="sharer")]
    captured = {}

    def fake_schema(data_type, api_version, fulcra_userid=None):
        captured.update(
            data_type=data_type, api_version=api_version, fulcra_userid=fulcra_userid
        )
        return {"properties": {}}

    client.v1_catalog_schema = fake_schema

    result = CliRunner().invoke(get_schema, [USER_TYPE], obj=client)

    assert result.exit_code == 0, result.output
    assert captured == {
        "data_type": USER_TYPE,
        "api_version": "v1",
        "fulcra_userid": "sharer",
    }

