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

# The v1 custom base types. Their names don't overlap the v1alpha1 annotation
# base types, so the prefix of a "<base>/<uuid>" id unambiguously identifies the
# API version -- which matters for restore, where an archived type is absent from
# the catalog list and can't be resolved to its version there.
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
    base_type: str,
    name: str,
    *,
    description: str | None = None,
    unit: str | None = None,
    aggregation: str | None = None,
    scale: dict | None = None,
    value_map: dict | None = None,
    fields_schema: dict | str | None = None,
) -> dict:
    """Create a v1 custom data type (Event or Metric).

    Params:
        source: A FulcraAPI to create through.
        base_type: ``"Event"`` or ``"Metric"``.
        name: Human-readable name for the new type.
        description: Description of the type (currently required by the server).
        unit: Unit of measurement (Metric only).
        aggregation: Metric aggregation, ``"cumulative"`` or ``"discrete"``
            (Metric only).
        scale: Metric scale as ``{"min": int, "max": int, "step": int}``
            (Metric only).
        value_map: Mapping of integer metric values to labels (Metric only).
        fields_schema: A JSON Schema (dict or JSON string) of additional fields
            to merge onto the base type's schema.

    Returns:
        The created data type's spec (including its ``"<BaseType>/<UUID>"`` id).

    Raises:
        ValueError: For an unknown base type, a missing description, a Metric-only
            option on a non-Metric type, or an unparseable fields_schema.
    """
    if not is_v1_base_type(base_type):
        raise ValueError(
            f"'{base_type}' is not a v1 base type; expected Event or Metric."
        )

    # The server currently requires a description on v1 data types; surface a
    # clear error instead of the raw 422 the missing field would otherwise cause.
    if description is None:
        raise ValueError("A description is required (use -d/--description).")

    # unit/aggregation/scale/value_map are part of the Metric record spec and are
    # rejected by the server (422) for any other base type; surface that up front.
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
