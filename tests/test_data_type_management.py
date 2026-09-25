"""Offline tests for the v1 data-type management module."""

import json
import uuid

import pytest

from fulcra_api import data_type_management as dtm

from .conftest import capture_request, offline_client


# --- create ------------------------------------------------------------------


def test_create_metric_builds_body_and_posts():
    client = offline_client()
    captured = capture_request(client, response=b'{"id": "Metric/abc"}')

    spec = dtm.create_data_type(
        client, "Metric", "Resting HR", description="beats", unit="bpm"
    )

    assert captured["path"] == "/input/v1/data_type/Metric"
    assert captured["method"] == "POST"
    assert captured["data"] == {
        "name": "Resting HR",
        "description": "beats",
        "record_spec": {"unit": "bpm"},
    }
    assert spec == {"id": "Metric/abc"}


def test_create_event_omits_empty_record_spec():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.create_data_type(client, "Event", "Nap", description="a nap")

    assert captured["path"] == "/input/v1/data_type/Event"
    assert captured["data"] == {"name": "Nap", "description": "a nap"}


def test_create_requires_description():
    client = offline_client()

    with pytest.raises(ValueError, match="description is required"):
        dtm.create_data_type(client, "Metric", "Steps")


def test_create_event_rejects_unit():
    client = offline_client()

    with pytest.raises(ValueError, match="unit may only be set"):
        dtm.create_data_type(client, "Event", "Nap", description="d", unit="bpm")


def test_create_rejects_unknown_base_type():
    client = offline_client()

    with pytest.raises(ValueError, match="not a v1 base type"):
        dtm.create_data_type(client, "MomentAnnotation", "X", description="d")


def test_create_serializes_dict_fields_schema():
    client = offline_client()
    captured = capture_request(client, response=b"{}")
    schema = {"properties": {"quality": {"type": "string"}}}

    dtm.create_data_type(client, "Event", "Nap", description="d", fields_schema=schema)

    assert captured["data"]["record_spec"]["schema"] == json.dumps(schema)


def test_create_accepts_fields_schema_as_json_string():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    fields = {"properties": {"a": {"type": "integer"}}}

    dtm.create_data_type(
        client,
        "Metric",
        "X",
        description="d",
        unit="u",
        fields_schema=json.dumps(fields),
    )

    assert captured["data"]["record_spec"] == {
        "unit": "u",
        "schema": json.dumps(fields),
    }


def test_create_metric_sets_aggregation():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.create_data_type(
        client, "Metric", "Steps", description="d", aggregation="cumulative"
    )

    assert captured["data"]["record_spec"] == {"aggregation": "cumulative"}


def test_create_metric_sets_scale_and_value_map():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.create_data_type(
        client,
        "Metric",
        "Mood",
        description="d",
        scale={"min": 0, "max": 10, "step": 1},
        value_map={0: "off", 1: "on"},
    )

    assert captured["data"]["record_spec"]["scale"] == {"min": 0, "max": 10, "step": 1}
    assert captured["data"]["record_spec"]["value_map"] == {0: "off", 1: "on"}


def test_create_metric_combines_all_record_spec_fields():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.create_data_type(
        client,
        "Metric",
        "Everything",
        description="d",
        unit="count",
        aggregation="discrete",
        scale={"min": 0, "max": 5, "step": 1},
        value_map={0: "none"},
        fields_schema={"properties": {"note": {"type": "string"}}},
    )

    assert captured["data"]["record_spec"] == {
        "unit": "count",
        "aggregation": "discrete",
        "scale": {"min": 0, "max": 5, "step": 1},
        "value_map": {0: "none"},
        "schema": json.dumps({"properties": {"note": {"type": "string"}}}),
    }


def test_create_event_rejects_aggregation():
    client = offline_client()

    with pytest.raises(ValueError, match="may only be set for the Metric"):
        dtm.create_data_type(
            client, "Event", "Nap", description="d", aggregation="discrete"
        )


def test_create_event_rejects_scale_and_value_map():
    client = offline_client()

    with pytest.raises(ValueError, match="may only be set for the Metric"):
        dtm.create_data_type(
            client, "Event", "Nap", description="d", scale={"min": 0, "max": 1}
        )

    with pytest.raises(ValueError, match="may only be set for the Metric"):
        dtm.create_data_type(
            client, "Event", "Nap", description="d", value_map={0: "off"}
        )


def test_create_rejects_invalid_fields_json():
    client = offline_client()

    with pytest.raises(ValueError, match="Invalid JSON"):
        dtm.create_data_type(
            client, "Event", "X", description="d", fields_schema="{not json"
        )


def test_create_rejects_non_object_fields_schema():
    client = offline_client()

    with pytest.raises(ValueError, match="must be a JSON object"):
        dtm.create_data_type(
            client, "Event", "X", description="d", fields_schema="[1, 2]"
        )


# --- archive / restore -------------------------------------------------------


def test_archive_marks_deprecated():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.archive_data_type(client, "Metric", "uuid-1")

    assert captured["path"] == "/input/v1/data_type/Metric/uuid-1"
    assert captured["method"] == "PUT"
    assert captured["data"] == {"deprecated": True}


def test_restore_clears_deprecated():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.restore_data_type(client, "Event", "uuid-2")

    assert captured["path"] == "/input/v1/data_type/Event/uuid-2"
    assert captured["method"] == "PUT"
    assert captured["data"] == {"deprecated": False}


# --- helpers -----------------------------------------------------------------


def test_parse_v1_shorthand_splits_base_and_uuid():
    u = str(uuid.uuid4())
    assert dtm.parse_v1_shorthand(f"Metric/{u}") == ("Metric", u)


def test_parse_v1_shorthand_rejects_non_v1_base():
    with pytest.raises(ValueError, match="Event|Metric"):
        dtm.parse_v1_shorthand(f"MomentAnnotation/{uuid.uuid4()}")


def test_parse_v1_shorthand_rejects_bad_uuid():
    with pytest.raises(ValueError, match="Event|Metric"):
        dtm.parse_v1_shorthand("Metric/not-a-uuid")


def test_is_v1_base_type():
    assert dtm.is_v1_base_type("Event")
    assert dtm.is_v1_base_type("Metric")
    assert not dtm.is_v1_base_type("NumericAnnotation")
