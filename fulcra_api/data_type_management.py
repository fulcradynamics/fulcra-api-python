"""High-level operations for managing v1 custom data types.

This module sits above the transport layer (the client classes in ``core``) and
below any front-end (the CLI, the MCP server). It orchestrates create / archive /
restore of v1 custom data types (Event / Metric): it builds the request bodies
the input-service expects and returns plain data, so front-ends don't each
re-implement that logic.

Functions here take a ``FulcraAPI`` as their first argument, return plain dicts,
and raise plain ``ValueError`` -- no front-end-specific error types.
"""

import json
from uuid import UUID

V1_BASE_TYPES = ("Event", "Metric")


def is_v1_base_type(name: str) -> bool:
    """Whether ``name`` is a v1 custom base type (``Event`` or ``Metric``)."""
    return name in V1_BASE_TYPES


def parse_v1_shorthand(data_type_id: str) -> tuple[str, str]:
    """Split a ``"<BaseType>/<UUID>"`` id into its base type and UUID string.

    Raises:
        ValueError: If the id isn't ``<Event|Metric>/<UUID>``.
    """
    parts = data_type_id.split("/", maxsplit=2)
    if len(parts) < 2 or not is_v1_base_type(parts[0]):
        raise ValueError("v1 data type id must be <Event|Metric>/<UUID>")
    try:
        type_uuid = str(UUID(parts[1]))
    except ValueError:
        raise ValueError("v1 data type id must be <Event|Metric>/<UUID>")
    return parts[0], type_uuid


def create_data_type(
    source,
    data_type: dict,
    name: str,
    *,
    description: str | None = None,
    unit: str | None = None,
    aggregation: str | None = None,
    scale: dict | None = None,
    value_map: dict | None = None,
    fields_schema: dict | str | None = None,
    tags: list[str] | None = None,
    raw_value: str | None = None,
    scale_labels: list[str] | None = None,
) -> dict:
    """Create a custom data type from a resolved base-type catalog entry.

    Dispatches to the right backend based on the base type's ``api_version``: v1
    custom types (Event / Metric) go to input-service, v1alpha1 annotations go to
    user-service. Options that don't apply to the resolved version are rejected
    with a ``ValueError`` rather than silently ignored.

    Params:
        source: A FulcraAPI to create through.
        data_type: A resolved base-type catalog entry (see
            FulcraAPI.resolve_data_type); its ``id`` is the base type and its
            ``api_version`` selects the backend.
        name: Human-readable name for the new type.
        description: Description of the type (required for v1; optional otherwise).
        unit: Unit of measurement (v1 Metric / v1alpha1 numeric annotations).
        aggregation: Metric aggregation, ``"cumulative"`` or ``"discrete"``
            (v1 Metric record spec / v1alpha1 metric kind).
        scale: v1 Metric scale as ``{"min": int, "max": int, "step": int}``.
        value_map: v1 Metric mapping of integer values to labels.
        fields_schema: v1 JSON Schema (dict or JSON string) of additional fields.
        tags: Tags to attach (v1alpha1 annotations only).
        raw_value: Default record value as an unparsed string (v1alpha1 numeric /
            boolean annotations only); coerced here per annotation type.
        scale_labels: Exactly five labels for a v1alpha1 ScaleAnnotation.

    Returns:
        The created data type's spec / annotation dict.

    Raises:
        ValueError: For an unsupported base type, a missing required description,
            an option that doesn't apply to the resolved API version, or an
            unparseable value / fields schema.
    """
    api_version = data_type.get("api_version")
    base_type = data_type["id"]

    if api_version == "v1":
        return _create_v1_data_type(
            source,
            base_type,
            name,
            description=description,
            unit=unit,
            aggregation=aggregation,
            scale=scale,
            value_map=value_map,
            fields_schema=fields_schema,
            tags=tags,
            raw_value=raw_value,
            scale_labels=scale_labels,
        )

    if api_version == "v1alpha1":
        return _create_v1alpha1_annotation(
            source,
            data_type,
            name,
            description=description,
            unit=unit,
            aggregation=aggregation,
            scale=scale,
            value_map=value_map,
            fields_schema=fields_schema,
            tags=tags,
            raw_value=raw_value,
            scale_labels=scale_labels,
        )

    raise ValueError(f"Cannot create a data type from base type '{base_type}'.")


def _create_v1_data_type(
    source,
    base_type: str,
    name: str,
    *,
    description: str | None,
    unit: str | None,
    aggregation: str | None,
    scale: dict | None,
    value_map: dict | None,
    fields_schema: dict | str | None,
    tags: list[str] | None,
    raw_value: str | None,
    scale_labels: list[str] | None,
) -> dict:
    """Build and POST the body for a v1 custom data type (Event or Metric)."""
    if not is_v1_base_type(base_type):
        raise ValueError(
            f"'{base_type}' is not a v1 base type; expected Event or Metric."
        )

    # These options only exist for v1alpha1 annotations; there is no v1 equivalent.
    annotation_only = {
        "tags": tags,
        "value": raw_value,
        "scale labels": scale_labels,
    }
    used = [opt for opt, val in annotation_only.items() if val]
    if used:
        raise ValueError(
            f"{', '.join(used)} cannot be used with v1 data type {base_type}."
        )

    # The server currently requires a description on v1 data types; surface a
    # clear error instead of the raw 422 the missing field would otherwise cause.
    if description is None:
        raise ValueError("A description is required (use -d/--description).")

    # unit/aggregation/scale/value_map are part of the Metric record spec and are
    # rejected by the server (422) for any other base type
    metric_only = {
        "unit": unit,
        "aggregation": aggregation,
        "scale": scale,
        "value_map": value_map,
    }
    if base_type != "Metric":
        used = [opt for opt, val in metric_only.items() if val is not None]
        if used:
            raise ValueError(
                f"{', '.join(used)} may only be set for the Metric base type."
            )

    record_spec: dict = {}
    if unit is not None:
        record_spec["unit"] = unit
    if aggregation is not None:
        record_spec["aggregation"] = aggregation
    if scale is not None:
        record_spec["scale"] = scale
    if value_map is not None:
        record_spec["value_map"] = value_map
    if fields_schema is not None:
        record_spec["schema"] = _schema_json(fields_schema)

    body: dict = {"name": name}
    if description is not None:
        body["description"] = description
    if record_spec:
        body["record_spec"] = record_spec

    return source.create_data_type(base_type, body)


def _create_v1alpha1_annotation(
    source,
    data_type: dict,
    name: str,
    *,
    description: str | None,
    unit: str | None,
    aggregation: str | None,
    scale: dict | None,
    value_map: dict | None,
    fields_schema: dict | str | None,
    tags: list[str] | None,
    raw_value: str | None,
    scale_labels: list[str] | None,
) -> dict:
    """Validate options and create a v1alpha1 annotation via user-service."""
    base_type = data_type["id"]
    scale_labels = list(scale_labels or [])
    tags = list(tags or [])

    # fields schema and the v1 Metric options have no v1alpha1 equivalent.
    if fields_schema is not None:
        raise ValueError("fields schema is only valid for v1 data types.")
    if scale is not None:
        raise ValueError("scale is only valid for v1 Metric data types.")
    if value_map is not None:
        raise ValueError("value map is only valid for v1 Metric data types.")

    # aggregation/value/unit only apply to annotations backed by a metric record.
    if data_type.get("record_spec", {}).get("type") != "metric":
        if aggregation is not None:
            # TODO: DurationAnnotation actually does support metric aggregation.
            raise ValueError(
                f"aggregation cannot be used with base data type {base_type}."
            )
        if raw_value is not None:
            raise ValueError(f"value cannot be used with base data type {base_type}.")
        if unit is not None:
            raise ValueError(f"unit cannot be used with base data type {base_type}.")

    # TODO: Possibly update type metadata to be able to determine that this is a scale
    if base_type != "ScaleAnnotation" and scale_labels:
        raise ValueError(
            f"scale labels cannot be used with base data type {base_type}."
        )

    value = None
    match base_type:
        case "MomentAnnotation":
            annotation_type = "moment"
        case "DurationAnnotation":
            annotation_type = "duration"
        case "BooleanAnnotation":
            annotation_type = "boolean"
            # user-service does not accept a unit for boolean annotations
            if unit is not None:
                raise ValueError(
                    f"unit cannot be used with base data type {base_type}."
                )
            if raw_value is not None:
                value = _parse_bool(raw_value)
        case "NumericAnnotation":
            annotation_type = "numeric"
            if raw_value is not None:
                value = _parse_float(raw_value)
        case "ScaleAnnotation":
            annotation_type = "scale"
            if len(scale_labels) != 5:
                raise ValueError(
                    "scale labels must be exactly 5 values with base data type "
                    f"{base_type}."
                )
            # user-service does not accept a unit for scale annotations
            if unit is not None:
                raise ValueError(
                    f"unit cannot be used with base data type {base_type}."
                )
        case _:
            raise ValueError(f"Unsupported base type: {base_type}")

    return source.create_annotation(
        annotation_type=annotation_type,
        name=name,
        description=description,
        tags=tags,
        metric_kind=aggregation,
        value=value,
        unit=unit,
        scale_labels=scale_labels,
    )


def archive_data_type(source, base_type: str, data_type_id: str) -> dict:
    """Archive (soft-delete) a v1 custom data type by marking it deprecated."""
    return source.update_data_type(base_type, data_type_id, {"deprecated": True})


def restore_data_type(source, base_type: str, data_type_id: str) -> dict:
    """Restore an archived v1 custom data type by clearing its deprecated flag."""
    return source.update_data_type(base_type, data_type_id, {"deprecated": False})


def _schema_json(fields_schema: dict | str) -> str:
    """Normalize a JSON Schema into the JSON *string* record_spec.schema expects.

    input-service stores the additional-fields schema as JSON text, so a dict is
    serialized and a string is validated and re-serialized.
    """
    if isinstance(fields_schema, str):
        try:
            parsed = json.loads(fields_schema)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON for fields schema: {exc}")
    else:
        parsed = fields_schema
    if not isinstance(parsed, dict):
        raise ValueError("Fields schema must be a JSON object.")
    return json.dumps(parsed)


# Truthy/falsy strings accepted for a boolean annotation value. Mirrors the set
# click's BoolParamType recognizes, so the CLI behaves the same after the coercion
# moved off click's param types and into this front-end-agnostic module.
_TRUE_STRINGS = {"1", "true", "t", "yes", "y", "on"}
_FALSE_STRINGS = {"0", "false", "f", "no", "n", "off"}


def _parse_bool(value: str) -> bool:
    """Parse a boolean annotation value string, raising ValueError if unrecognized."""
    normalized = value.strip().lower()
    if normalized in _TRUE_STRINGS:
        return True
    if normalized in _FALSE_STRINGS:
        return False
    raise ValueError(f"'{value}' is not a valid boolean value.")


def _parse_float(value: str) -> float:
    """Parse a numeric annotation value string, raising ValueError if invalid."""
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"'{value}' is not a valid numeric value.")
