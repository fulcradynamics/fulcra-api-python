"""Offline tests for the v1 data-type management module."""

import json
import uuid

import pytest

from fulcra_api import data_type_management as dtm

from .conftest import capture_request, offline_client


# --- create: catalog-entry helpers -------------------------------------------


def _v1(base_type: str, record_type: str) -> dict:
    """A resolved v1 base-type catalog entry."""
    return {"id": base_type, "api_version": "v1", "record_spec": {"type": record_type}}


def _v1alpha1(base_type: str, record_type: str) -> dict:
    """A resolved v1alpha1 annotation base-type catalog entry."""
    return {
        "id": base_type,
        "api_version": "v1alpha1",
        "record_spec": {"type": record_type},
    }


# --- create: v1 --------------------------------------------------------------


def test_create_metric_builds_body_and_posts():
    client = offline_client()
    captured = capture_request(client, response=b'{"id": "Metric/abc"}')

    spec = dtm.create_data_type(
        client, _v1("Metric", "metric"), "Resting HR", description="beats", unit="bpm"
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

    dtm.create_data_type(client, _v1("Event", "event"), "Nap", description="a nap")

    assert captured["path"] == "/input/v1/data_type/Event"
    assert captured["data"] == {"name": "Nap", "description": "a nap"}


def test_create_requires_description():
    client = offline_client()

    with pytest.raises(ValueError, match="description is required"):
        dtm.create_data_type(client, _v1("Metric", "metric"), "Steps")


def test_create_event_rejects_unit():
    client = offline_client()

    with pytest.raises(ValueError, match="unit may only be set"):
        dtm.create_data_type(
            client, _v1("Event", "event"), "Nap", description="d", unit="bpm"
        )


def test_create_rejects_unknown_base_type():
    client = offline_client()

    with pytest.raises(ValueError, match="not a v1 base type"):
        dtm.create_data_type(
            client, _v1("MomentAnnotation", "event"), "X", description="d"
        )


def test_create_rejects_unsupported_api_version():
    client = offline_client()

    with pytest.raises(ValueError, match="Cannot create a data type"):
        dtm.create_data_type(
            client,
            {"id": "StepCount", "api_version": "v0", "record_spec": {"type": "metric"}},
            "X",
            description="d",
        )


def test_create_v1_rejects_annotation_only_options():
    client = offline_client()

    with pytest.raises(ValueError, match="cannot be used with v1 data type"):
        dtm.create_data_type(
            client, _v1("Metric", "metric"), "X", description="d", tags=["a"]
        )
    with pytest.raises(ValueError, match="cannot be used with v1 data type"):
        dtm.create_data_type(
            client, _v1("Metric", "metric"), "X", description="d", raw_value="1"
        )
    with pytest.raises(ValueError, match="cannot be used with v1 data type"):
        dtm.create_data_type(
            client,
            _v1("Metric", "metric"),
            "X",
            description="d",
            scale_labels=["a"],
        )


def test_create_serializes_dict_fields_schema():
    client = offline_client()
    captured = capture_request(client, response=b"{}")
    schema = {"properties": {"quality": {"type": "string"}}}

    dtm.create_data_type(
        client, _v1("Event", "event"), "Nap", description="d", fields_schema=schema
    )

    assert captured["data"]["record_spec"]["schema"] == json.dumps(schema)


def test_create_accepts_fields_schema_as_json_string():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.create_data_type(
        client,
        _v1("Metric", "metric"),
        "X",
        description="d",
        unit="u",
        fields_schema='{"a": 1}',
    )

    assert captured["data"]["record_spec"] == {
        "unit": "u",
        "schema": json.dumps({"a": 1}),
    }


def test_create_metric_sets_aggregation():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.create_data_type(
        client,
        _v1("Metric", "metric"),
        "Steps",
        description="d",
        aggregation="cumulative",
    )

    assert captured["data"]["record_spec"] == {"aggregation": "cumulative"}


def test_create_metric_sets_scale_and_value_map():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.create_data_type(
        client,
        _v1("Metric", "metric"),
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
        _v1("Metric", "metric"),
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
            client,
            _v1("Event", "event"),
            "Nap",
            description="d",
            aggregation="discrete",
        )


def test_create_event_rejects_scale_and_value_map():
    client = offline_client()

    with pytest.raises(ValueError, match="may only be set for the Metric"):
        dtm.create_data_type(
            client,
            _v1("Event", "event"),
            "Nap",
            description="d",
            scale={"min": 0, "max": 1},
        )

    with pytest.raises(ValueError, match="may only be set for the Metric"):
        dtm.create_data_type(
            client, _v1("Event", "event"), "Nap", description="d", value_map={0: "off"}
        )


def test_create_rejects_invalid_fields_json():
    client = offline_client()

    with pytest.raises(ValueError, match="Invalid JSON"):
        dtm.create_data_type(
            client,
            _v1("Event", "event"),
            "X",
            description="d",
            fields_schema="{not json",
        )


def test_create_rejects_non_object_fields_schema():
    client = offline_client()

    with pytest.raises(ValueError, match="must be a JSON object"):
        dtm.create_data_type(
            client, _v1("Event", "event"), "X", description="d", fields_schema="[1, 2]"
        )


# --- create: v1alpha1 annotations --------------------------------------------


def test_create_annotation_maps_base_type_to_annotation_type():
    cases = {
        "MomentAnnotation": ("event", "moment"),
        "DurationAnnotation": ("event", "duration"),
        "BooleanAnnotation": ("event", "boolean"),
        "NumericAnnotation": ("metric", "numeric"),
    }
    for base_type, (record_type, annotation_type) in cases.items():
        client = offline_client()
        captured = capture_request(client, response=b"{}")

        dtm.create_data_type(
            client, _v1alpha1(base_type, record_type), "X", description="d"
        )

        assert captured["path"] == "/user/v1alpha1/annotation"
        assert captured["data"]["annotation_type"] == annotation_type, base_type


def test_create_numeric_annotation_coerces_float_value():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    dtm.create_data_type(
        client,
        _v1alpha1("NumericAnnotation", "metric"),
        "X",
        description="d",
        raw_value="1.5",
    )

    assert captured["data"]["measurement_spec"]["custom"]["value"] == 1.5


def test_create_numeric_annotation_rejects_bad_float():
    client = offline_client()
    capture_request(client)

    with pytest.raises(ValueError, match="not a valid numeric value"):
        dtm.create_data_type(
            client,
            _v1alpha1("NumericAnnotation", "metric"),
            "X",
            description="d",
            raw_value="nope",
        )


def test_create_boolean_annotation_coerces_bool_value():
    for text, expected in (("true", True), ("no", False), ("1", True), ("off", False)):
        client = offline_client()
        captured = capture_request(client, response=b"{}")

        dtm.create_data_type(
            client,
            _v1alpha1("BooleanAnnotation", "metric"),
            "X",
            description="d",
            raw_value=text,
        )

        assert captured["data"]["measurement_spec"]["boolean"]["value"] is expected


def test_create_boolean_annotation_rejects_bad_bool():
    client = offline_client()
    capture_request(client)

    with pytest.raises(ValueError, match="not a valid boolean value"):
        dtm.create_data_type(
            client,
            _v1alpha1("BooleanAnnotation", "metric"),
            "X",
            description="d",
            raw_value="maybe",
        )


def test_create_scale_annotation_requires_five_labels():
    client = offline_client()
    capture_request(client)

    with pytest.raises(ValueError, match="exactly 5"):
        dtm.create_data_type(
            client,
            _v1alpha1("ScaleAnnotation", "event"),
            "X",
            description="d",
            scale_labels=["a", "b", "c"],
        )


def test_create_scale_labels_rejected_for_non_scale():
    client = offline_client()
    capture_request(client)

    with pytest.raises(ValueError, match="scale labels cannot be used"):
        dtm.create_data_type(
            client,
            _v1alpha1("MomentAnnotation", "event"),
            "X",
            description="d",
            scale_labels=["a", "b", "c", "d", "e"],
        )


def test_create_non_metric_annotation_rejects_metric_options():
    for kwargs, match in (
        ({"aggregation": "cumulative"}, "aggregation cannot be used"),
        ({"raw_value": "1"}, "value cannot be used"),
        ({"unit": "mg"}, "unit cannot be used"),
    ):
        client = offline_client()
        capture_request(client)

        with pytest.raises(ValueError, match=match):
            dtm.create_data_type(
                client,
                _v1alpha1("MomentAnnotation", "event"),
                "X",
                description="d",
                **kwargs,
            )


def test_create_annotation_rejects_v1_only_options():
    for kwargs, match in (
        ({"fields_schema": "{}"}, "fields schema is only valid for v1"),
        ({"scale": {"min": 0, "max": 1}}, "scale is only valid for v1 Metric"),
        ({"value_map": {0: "off"}}, "value map is only valid for v1 Metric"),
    ):
        client = offline_client()
        capture_request(client)

        with pytest.raises(ValueError, match=match):
            dtm.create_data_type(
                client,
                _v1alpha1("NumericAnnotation", "metric"),
                "X",
                description="d",
                **kwargs,
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
