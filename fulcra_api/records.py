"""High-level record operations: fetching and recording.

This module sits above the transport layer (the client classes in ``core``) and
below any front-end (the CLI, the MCP server). It orchestrates *which* endpoint
to call for a given resolved catalog entry and normalizes the response into a
list of record dicts, so front-ends don't each re-implement that dispatch.

Functions here take a data-access source (a ``FulcraAPI`` or
``FulcraGroupParticipant``) as their first argument, return plain data, and raise
plain ``ValueError`` -- no front-end-specific error types.
"""

import json
from datetime import datetime
from urllib.error import HTTPError
from uuid import UUID

from fulcra_api.core import FulcraGroupParticipant
from fulcra_api.record_validation import is_unknown_fields_error, unknown_fields


def build_v1_promql(
    data_type_id: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    *,
    latest: bool = False,
) -> str:
    """
    Build a PromQL query selecting a data type's records.

    A user-defined type's id (``Event/<uuid>``) can't be a PromQL metric name,
    which can't contain ``/``, so it's selected with a ``__name__`` matcher
    (``{__name__="Event/<uuid>"}``) instead.

    With ``latest=True``, emits a bare instant vector (just the selector), which
    the v1 records endpoint evaluates as the single most recent record.

    Otherwise encodes the window as a range vector anchored at the end time
    (``Type[<duration>s] @ <end_unix_ts>``), which the v1 records endpoint
    evaluates as records overlapping [start_time, end_time). Pre-epoch endpoints
    use an epoch anchor plus offset to avoid the backend's negative-time getter.
    """
    selector = f'{{__name__="{data_type_id}"}}' if "/" in data_type_id else data_type_id
    if latest:
        return selector
    duration = max(1, int((end_time - start_time).total_seconds()))
    timestamp = int(end_time.timestamp())
    if timestamp < 0:
        # The backend's timestamp getter panics on negative anchors. An epoch
        # anchor plus offset preserves the window without that conversion.
        # Split long offsets to avoid the parser's uint32 seconds-component limit.
        days, seconds = divmod(-timestamp, 86400)
        offset = (f"{days}d" if days else "") + (f"{seconds}s" if seconds else "")
        return f"{selector}[{duration}s] @ 0 offset {offset}"
    return f"{selector}[{duration}s] @ {timestamp}"


def _owner_scope(source, data_type: dict):
    """The owner id to scope a query to, or None.

    Only the direct client scopes cross-user queries; a group participant is
    already scoped to its participant and must not send a fulcra_userid.
    """
    if isinstance(source, FulcraGroupParticipant):
        return None
    if source.get_fulcra_userid() != data_type["fulcra_userid"]:
        return data_type["fulcra_userid"]
    return None


def get_records(
    source,
    data_type: dict,
    start_time: datetime | None,
    end_time: datetime | None,
    *,
    latest: bool = False,
) -> list[dict]:
    """
    Fetch records for one resolved catalog entry.

    Dispatches to the right endpoint based on the entry's api_version and record
    type, and returns a list of record dicts. With ``latest=True``, returns only
    the single most recent record (and start_time/end_time are ignored).

    Params:
        source: A FulcraAPI or FulcraGroupParticipant to query through.
        data_type: A resolved catalog entry (see FulcraAPI.resolve_data_type).
        start_time: Start of the time window (ignored when latest=True).
        end_time: End of the time window (ignored when latest=True).
        latest: Return only the most recent record instead of a window.

    Raises:
        ValueError: If the entry can't be mapped to an endpoint (unsupported
            api_version/record type, a malformed annotation shorthand, a v1
            type queried through a group participant, or latest requested for a
            non-v1 type -- only v1 has a latest-record query).
    """
    api_version = data_type["api_version"]
    record_type = data_type.get("record_spec", {}).get("type")

    # Only the v1 endpoint can return a single latest record; v0 and v1alpha1
    # require a real time window.
    if latest and api_version != "v1":
        raise ValueError(
            "Fetching the latest record is only supported for v1 data types; "
            f"provide a time range instead (data type '{data_type['id']}')."
        )

    # A custom type's shorthand, "<Base Type>/<UUID>": a user-configured
    # annotation (v1alpha1) or a user-defined type (v1).
    annotation_id = None
    parts = data_type["id"].split("/", maxsplit=2)
    base_type = parts[0]
    if len(parts) > 1:
        try:
            annotation_id = UUID(parts[1])
        except ValueError:
            raise ValueError(
                f"Custom data type '{data_type['id']}' must be written "
                "<Base Type>/<UUID>"
            )

    owner = _owner_scope(source, data_type)

    if api_version == "v0" and record_type == "metric":
        kwargs = {
            "start_time": start_time,
            "end_time": end_time,
            "metric": data_type["id"],
        }
        if owner is not None:
            kwargs["fulcra_userid"] = owner
        return _as_records(source.metric_samples(**kwargs))

    if api_version == "v1alpha1" and record_type in ("metric", "event"):
        path = f"{record_type}/{base_type}"
        if annotation_id:
            path = f"{path}/{annotation_id}"
        params = {"start_time": start_time, "end_time": end_time}
        if owner is not None:
            params["fulcra_userid"] = owner
        return _as_records(source.fulcra_v1alpha1_api_path(path, params))

    if api_version == "v1" and record_type in ("metric", "event"):
        if isinstance(source, FulcraGroupParticipant):
            raise ValueError(
                "Group participant queries are not supported for v1 data types."
            )
        # the full id: a user-defined type (Event/<uuid>) is its own data type,
        # not its base type
        query = build_v1_promql(data_type["id"], start_time, end_time, latest=latest)
        resp = source.fulcra_v1_records(query, fulcra_userid=owner)
        return _as_records(resp, jsonl=True)

    raise ValueError(
        f"Could not derive API endpoint for data type '{data_type['id']}'"
    )


def _as_records(resp, jsonl: bool = False) -> list[dict]:
    """Normalize a transport response into a list of record dicts."""
    if jsonl:
        # The v1 records endpoint streams JSONL (one record per line).
        return [json.loads(line) for line in resp.splitlines() if line.strip()]
    if isinstance(resp, bytes):
        resp = json.loads(resp)
    return resp


class SchemaNotFoundError(ValueError):
    """The data type's record schema couldn't be found, so records can't be checked."""


class RecordValidationError(ValueError):
    """A record doesn't match its data type's schema.

    ``index`` is the 0-based position of the first failing record.
    """

    def __init__(self, index: int, message: str):
        super().__init__(f"Validation error in record {index + 1}: {message}")
        self.index = index
        self.message = message


def record(
    source,
    data_type: dict,
    records: list[dict],
    *,
    tags=(),
    sources=(),
    validate: bool = True,
    delivery: str | None = None,
) -> dict:
    """
    Record records of one resolved catalog entry.

    Routes a user-configured annotation (v1alpha1 ``<Base Type>/<UUID>``) to its
    base type with an annotation source, resolves tag names to tag ids, merges
    tags and sources into every record (modifying them in place), checks the
    records against the data type's schema, and uploads them.

    Params:
        source: A FulcraAPI to record through.
        data_type: A resolved catalog entry (see FulcraAPI.resolve_data_type).
        records: The records to record.
        tags: Tag names to add to every record.
        sources: Sources to add to every record, in order, after any it has.
        validate: Check the records against the data type's schema first.
        delivery: "immediate", "batch", or None to choose: immediate for a
            single record of a v1 data type, batch otherwise.

    Returns:
        ``{"upload_id", "data_type", "record_count", "delivery", "warnings"}``,
        where ``data_type`` is the type the records were sent to and
        ``warnings`` lists fields that aren't part of the data type and will be
        dropped.

    Raises:
        ValueError: No records, or immediate delivery asked for more than one
            record or a non-v1 data type.
        RecordValidationError: A record doesn't match the schema.
        SchemaNotFoundError: The data type has no schema to validate against.
        HTTPError: Any other API failure.
    """
    if not records:
        raise ValueError("No records to record.")

    api_version = data_type["api_version"]
    if delivery is None:
        delivery = "immediate" if api_version == "v1" and len(records) == 1 else "batch"
    elif delivery == "immediate":
        if api_version != "v1":
            raise ValueError(
                "Immediate delivery is only supported for v1 data types, "
                f"not {data_type['id']} ({api_version})."
            )
        if len(records) != 1:
            raise ValueError(
                f"Immediate delivery takes exactly one record; got {len(records)}."
            )
    elif delivery != "batch":
        raise ValueError(f"delivery must be 'batch' or 'immediate', not {delivery!r}")

    # v1 types (e.g. "Event/<uuid>") go directly to that endpoint, but v1alpha1
    # annotations go to their base type, marked with an annotation source.
    target_type = data_type["id"]
    sources_to_add = list(sources)
    if "/" in data_type["id"] and api_version != "v1":
        target_type, annotation_uuid = data_type["id"].split("/", maxsplit=1)
        sources_to_add.append(f"com.fulcradynamics.annotation.{annotation_uuid.lower()}")

    tag_ids = [t["id"] for t in source.create_tags(list(tags))] if tags else []

    # Remove from each record what we're about to add, then append ours.
    for rec in records:
        if tag_ids:
            existing = [t for t in rec.get("tags", []) if t not in tag_ids]
            rec["tags"] = existing + tag_ids
        if sources_to_add:
            existing = [s for s in rec.get("sources", []) if s not in sources_to_add]
            rec["sources"] = existing + sources_to_add

    warnings = []
    if validate:
        warnings = _validate(source, data_type, records)

    # Batch is the server's default, so only immediate is spelled out.
    response = source.record_data_type(
        target_type,
        records,
        api_version,
        delivery="immediate" if delivery == "immediate" else None,
    )
    return {
        "upload_id": response.get("upload_id"),
        "data_type": target_type,
        "record_count": len(records),
        "delivery": delivery,
        "warnings": warnings,
    }


def _validate(source, data_type: dict, records: list[dict]) -> list[str]:
    """Check records against the schema; return warnings for unknown fields."""
    try:
        validation_errors = source.validate_records(
            data_type["id"], records, api_version=data_type["api_version"]
        )
    except HTTPError as exc:
        if exc.code == 404:
            raise SchemaNotFoundError(f"Schema not found for {data_type['id']}.")
        raise

    errors = [e for e in validation_errors if not is_unknown_fields_error(e[2])]
    if errors:
        index, message, _ = errors[0]
        raise RecordValidationError(index, message)

    # Unknown fields don't stop the upload: the record is kept without them.
    warnings = []
    warned = set()
    for index, _, error in validation_errors:
        for field in unknown_fields(error):
            if field in warned:
                continue
            warned.add(field)
            declared = ", ".join(sorted(error.schema.get("properties", {})))
            warnings.append(
                f"record {index + 1}: field {field!r} isn't part of "
                f"{data_type['id']} and will be dropped; its fields are: {declared}"
            )
    return warnings
