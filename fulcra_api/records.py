"""High-level record-fetching operations.

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
from uuid import UUID

from fulcra_api.core import FulcraGroupParticipant


def build_v1_promql(
    data_type_id: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    *,
    latest: bool = False,
) -> str:
    """
    Build a PromQL query selecting a data type's records.

    With ``latest=True``, emits a bare instant vector (just the type id), which
    the v1 records endpoint evaluates as the single most recent record.

    Otherwise encodes the window as a range vector anchored at the end time
    (``Type[<duration>s] @ <end_unix_ts>``), which the v1 records endpoint
    evaluates as records overlapping [start_time, end_time).
    """
    if latest:
        return data_type_id
    duration = max(1, int((end_time - start_time).total_seconds()))
    return f"{data_type_id}[{duration}s] @ {int(end_time.timestamp())}"


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

    # User-configured annotation shorthand: "<AnnotationType>/<UUID>".
    annotation_id = None
    parts = data_type["id"].split("/", maxsplit=2)
    base_type = parts[0]
    if len(parts) > 1:
        try:
            annotation_id = UUID(parts[1])
        except ValueError:
            raise ValueError(
                "User configured annotation shorthand must be "
                "<Annotation Type>/<UUID>"
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
        query = build_v1_promql(base_type, start_time, end_time, latest=latest)
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
