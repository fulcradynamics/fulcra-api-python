import json
from typing import List, Optional, Tuple
from urllib.error import HTTPError
from uuid import UUID

import click
from click_option_group import optgroup

from fulcra_api import data_type_management
from fulcra_api.core import FulcraAPI

from .utils import pass_fulcra_api, requires_auth, resolve_data_type


@click.group(name="data-type", help="Data type management sub-commands")
def data_type():
    pass


@data_type.command("create", short_help="Create a new data type")
@click.argument("base_data_type", type=str)
@click.argument("name", type=str)
@click.option(
    "-d",
    "--description",
    type=str,
    default=None,
    help="Description of the data type (required for v1; optional for v1alpha1)",
)
@click.option(
    "-t",
    "--tag",
    "tags",
    type=str,
    multiple=True,
    help="Tags to attach to the data type (v1alpha1 annotations only)",
)
@optgroup.group(
    "Metric options",
    help="For metric record types (v1 Metric and v1alpha1 metric annotations)",
)
@optgroup.option(
    "-k",
    "--kind",
    "--metric-aggregation",
    "--aggregation",
    "--agg",
    "metric_agg",
    type=click.Choice(
        [
            "cumulative",
            "discrete",
        ]
    ),
    help="Metric aggregation (v1 Metric record spec; v1alpha1 metric kind)",
)
@optgroup.option(
    "-u",
    "--unit",
    "--metric-unit",
    "unit",
    type=str,
    help="Unit of measurement (v1 Metric; v1alpha1 numeric annotations)",
)
@optgroup.option(
    "-v",
    "--value",
    "--metric-value",
    "raw_value",
    type=str,
    help="Default value for recording the data type (v1alpha1 annotations only)",
)
@optgroup.group(
    "v1 Metric options",
    help="Only applicable when BASE_DATA_TYPE is the v1 Metric base type",
)
@optgroup.option(
    "--scale-min",
    "scale_min",
    type=int,
    default=None,
    help="Minimum value of the metric scale (requires --scale-max)",
)
@optgroup.option(
    "--scale-max",
    "scale_max",
    type=int,
    default=None,
    help="Maximum value of the metric scale (requires --scale-min)",
)
@optgroup.option(
    "--scale-step",
    "scale_step",
    type=int,
    default=None,
    help="Step of the metric scale (default 1 when a scale is set)",
)
@optgroup.option(
    "--value-map",
    "value_map",
    type=str,
    multiple=True,
    help="Map an integer value to a label, e.g. 0=off (repeatable)",
)
@optgroup.group(
    "Scale annotation options",
    help="Only applicable when BASE_DATA_TYPE is ScaleAnnotation (v1alpha1)",
)
@optgroup.option(
    "-s",
    "--scale-label",
    "scale_labels",
    type=str,
    multiple=True,
    help="ScaleAnnotation labels, exactly 5 (v1alpha1 only)",
)
@click.option(
    "--add-to-timeline",
    is_flag=True,
    help="Add created data type to timeline (v1alpha1 annotations only)",
)
@click.option(
    "--fields",
    "fields_schema",
    type=str,
    default=None,
    help="JSON Schema of additional fields to merge onto the base type "
    "(v1 Event/Metric only)",
)
@pass_fulcra_api
@requires_auth
def data_type_create(
    fulcra_api: FulcraAPI,
    base_data_type: str,
    name: str,
    description: Optional[str],
    tags: List[str],
    metric_agg: Optional[str],
    unit: Optional[str],
    raw_value: Optional[str],
    scale_min: Optional[int],
    scale_max: Optional[int],
    scale_step: Optional[int],
    value_map: Tuple[str, ...],
    scale_labels: List[str],
    add_to_timeline: bool,
    fields_schema: Optional[str],
):
    """Create a new data type from a base data type.

    BASE_DATA_TYPE: The base data type to create from. List valid base types with fulcra catalog --base-types --recordable

    NAME: The name of the data type to create

    Use -d/--description to add an optional description
    """

    try:
        catalog_resp = fulcra_api.v1_catalog(
            data_type=base_data_type, fulcra_userid=fulcra_api.get_fulcra_userid()
        )
    except HTTPError as exc:
        raise click.ClickException(f"Failed to validate BASE_DATA_TYPE: {exc}")

    filtered_base_data_types = [
        c for c in catalog_resp if "base_type" in c.get("categories", [])
    ]

    if len(filtered_base_data_types) != 1:
        raise click.ClickException(
            f"Could not resolve a single base data type for identifier: {base_data_type}"
        )

    fulcra_data_type = filtered_base_data_types[0]

    if fulcra_data_type.get("api_version") == "v1":
        _create_v1_data_type(
            fulcra_api,
            fulcra_data_type,
            base_data_type=base_data_type,
            name=name,
            description=description,
            unit=unit,
            metric_agg=metric_agg,
            scale_min=scale_min,
            scale_max=scale_max,
            scale_step=scale_step,
            value_map=value_map,
            fields_schema=fields_schema,
            tags=tags,
            raw_value=raw_value,
            scale_labels=scale_labels,
            add_to_timeline=add_to_timeline,
        )
        return

    # v1alpha1 annotation path. --fields and the v1 Metric options are v1-only.
    if fields_schema is not None:
        raise click.BadOptionUsage(
            "fields_schema", "--fields is only valid for v1 data types"
        )

    if scale_min is not None or scale_max is not None or scale_step is not None:
        raise click.BadOptionUsage(
            "scale_min",
            "--scale-min/--scale-max/--scale-step are only valid for v1 Metric "
            "data types",
        )

    if value_map:
        raise click.BadOptionUsage(
            "value_map", "--value-map is only valid for v1 Metric data types"
        )

    if fulcra_data_type.get("record_spec", {}).get("type") != "metric":
        if (
            metric_agg is not None
        ):  # TODO: DurationAnnotation actually does support metric_agg
            raise click.BadOptionUsage(
                "metric_agg",
                f"-k / --kind cannot be used with base data type {base_data_type}",
            )

        if raw_value is not None:
            raise click.BadOptionUsage(
                "raw_value",
                f"-v / --value cannot be used with base data type {base_data_type}",
            )

        if unit is not None:
            raise click.BadOptionUsage(
                "unit",
                f"-u / --unit cannot be used with base data type {base_data_type}",
            )

    # TODO: Possibly update type metadata to be able to determine that this is a scale
    if fulcra_data_type["id"] != "ScaleAnnotation" and len(scale_labels) > 0:
        raise click.BadOptionUsage(
            "scale_labels",
            f"-s / --scale-label cannot be used with base data type {base_data_type}",
        )

    value = None
    match fulcra_data_type["id"]:
        case "MomentAnnotation":
            annotation_type = "moment"
        case "DurationAnnotation":
            annotation_type = "duration"
        case "BooleanAnnotation":
            annotation_type = "boolean"
            # user-service does not accept a unit for boolean annotations
            if unit is not None:
                raise click.BadOptionUsage(
                    "unit",
                    f"-u / --unit cannot be used with base data type {base_data_type}",
                )
            if raw_value is not None:
                value = click.types.BoolParamType().convert(raw_value, None, None)
        case "NumericAnnotation":
            annotation_type = "numeric"
            if raw_value is not None:
                value = click.types.FloatParamType().convert(raw_value, None, None)
        case "ScaleAnnotation":
            annotation_type = "scale"
            if len(scale_labels) != 5:
                raise click.BadOptionUsage(
                    "scale_labels",
                    f"-s / --scale-label must be used with exactly 5 values with base data type {base_data_type}",
                )
            # user-service does not accept a unit for scale annotations
            if unit is not None:
                raise click.BadOptionUsage(
                    "unit",
                    f"-u / --unit cannot be used with base data type {base_data_type}",
                )
        case _:
            raise click.ClickException(f"Unsupported base type: {base_data_type}")

    try:
        ann = fulcra_api.create_annotation(
            annotation_type=annotation_type,
            name=name,
            description=description,
            tags=tags,
            metric_kind=metric_agg,
            value=value,
            unit=unit,
            scale_labels=scale_labels,
        )

        if add_to_timeline:
            try:
                info = fulcra_api.get_user_info()
                current_prefs = info.get("preferences", {})
                existing_metrics_map = current_prefs.get("selected_metrics_map", {})

                current_selection = existing_metrics_map.get(info["userid"], [])
                ann_id = ann["id"]

                # TODO: this is a legacy naming convention for timeline data tracks
                updated_selection = [
                    f"fulcra_custom_event.{ann_id}"
                ] + current_selection

                prefs_payload = {
                    "selected_metrics_map": {
                        **existing_metrics_map,
                        info["userid"]: updated_selection,
                    }
                }

                fulcra_api.update_user_preferences(prefs_payload)
            except HTTPError as exc:
                click.echo(f"Failed to add annotation to timeline: {exc}", err=True)

        click.echo(json.dumps(ann))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(
            f"Failed to create event data type: {exc}\n{error_body}"
        )


def _create_v1_data_type(
    fulcra_api: FulcraAPI,
    fulcra_data_type: dict,
    *,
    base_data_type: str,
    name: str,
    description: Optional[str],
    unit: Optional[str],
    metric_agg: Optional[str],
    scale_min: Optional[int],
    scale_max: Optional[int],
    scale_step: Optional[int],
    value_map: Tuple[str, ...],
    fields_schema: Optional[str],
    tags: List[str],
    raw_value: Optional[str],
    scale_labels: List[str],
    add_to_timeline: bool,
):
    """Create a v1 custom data type (Event or Metric).

    The annotation-only options have no v1 equivalent, so they're rejected here
    rather than silently ignored. Metric-only options (unit/aggregation/scale/
    value_map) are passed through and validated against the base type downstream.
    """
    rejected = []
    if tags:
        rejected.append("-t / --tag")
    if raw_value is not None:
        rejected.append("-v / --value")
    if scale_labels:
        rejected.append("-s / --scale-label")
    if add_to_timeline:
        rejected.append("--add-to-timeline")
    if rejected:
        raise click.BadOptionUsage(
            "",
            f"{', '.join(rejected)} cannot be used with v1 data type {base_data_type}",
        )

    scale = _build_scale(scale_min, scale_max, scale_step)
    parsed_value_map = _parse_value_map(value_map)

    try:
        spec = data_type_management.create_data_type(
            fulcra_api,
            fulcra_data_type["id"],
            name,
            description=description,
            unit=unit,
            aggregation=metric_agg,
            scale=scale,
            value_map=parsed_value_map,
            fields_schema=fields_schema,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to create data type: {exc}\n{error_body}")

    click.echo(json.dumps(spec))


def _build_scale(
    scale_min: Optional[int], scale_max: Optional[int], scale_step: Optional[int]
) -> Optional[dict]:
    """Assemble the Metric ``record_spec.scale`` object from the CLI options.

    Returns None when no scale option was given. ``step`` defaults to 1 when a
    scale is set (the server does not apply that default itself).
    """
    if scale_min is None and scale_max is None and scale_step is None:
        return None
    if scale_min is None or scale_max is None:
        raise click.BadOptionUsage(
            "scale_min", "--scale-min and --scale-max must be provided together"
        )
    return {
        "min": scale_min,
        "max": scale_max,
        "step": scale_step if scale_step is not None else 1,
    }


def _parse_value_map(value_map: Tuple[str, ...]) -> Optional[dict]:
    """Parse repeated ``INT=LABEL`` options into a ``{int: str}`` mapping."""
    if not value_map:
        return None
    parsed: dict = {}
    for item in value_map:
        key, sep, label = item.partition("=")
        if not sep:
            raise click.BadOptionUsage(
                "value_map", f"--value-map entry '{item}' must be in INT=LABEL form"
            )
        try:
            int_key = int(key)
        except ValueError:
            raise click.BadOptionUsage(
                "value_map", f"--value-map key '{key}' must be an integer"
            )
        parsed[int_key] = label
    return parsed


@data_type.command("archive", short_help="Archive a user-defined data type")
@click.argument(
    "data_type",
    callback=resolve_data_type(default_to_authenticated=True),
)
@pass_fulcra_api
@requires_auth
def data_type_archive(fulcra_api: FulcraAPI, data_type: dict):
    """
    Archive a user-defined data type by ID.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types
    """

    # data_type is the resolved catalog entry (see resolve_data_type)
    type_id = data_type["id"]

    if data_type.get("api_version") == "v1":
        try:
            base_type, type_uuid = data_type_management.parse_v1_shorthand(type_id)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        try:
            data_type_management.archive_data_type(fulcra_api, base_type, type_uuid)
            click.echo(f"Archived data type: {type_id}")
        except HTTPError as exc:
            raise click.ClickException(
                f"Failed to archive data type {type_id}: {exc}"
            )
        return

    try:
        parts = type_id.split("/", maxsplit=2)
        ann_id = str(UUID(parts[1]))
    except (ValueError, IndexError):
        raise click.ClickException("DATA_TYPE must be <Annotation Type>/<UUID>")

    try:
        fulcra_api.delete_annotation(annotation_id=ann_id)
        click.echo(f"Archived data type: {type_id}")
    except HTTPError as exc:
        raise click.ClickException(f"Failed to archive data type {type_id}: {exc}")


@data_type.command("restore", short_help="Restore an archived user-defined data type")
@click.argument("data_type")
@pass_fulcra_api
@requires_auth
def restore_data_type(fulcra_api: FulcraAPI, data_type: str):
    """
    Restore an archived user-defined data type by ID.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types
    """

    try:
        fulcra_api.resolve_data_type(
            data_type=data_type,
            fulcra_userid=fulcra_api.get_fulcra_userid(),
        )
        raise click.ClickException(f"Data type {data_type} is not archived")
    except ValueError:
        # If we did not find this data type, then it may be archived
        pass
    except HTTPError as exc:
        raise click.ClickException(str(exc))

    parts = data_type.split("/", maxsplit=2)
    base_type = parts[0]

    # An archived type is absent from the catalog list, so its API version can't
    # be resolved there; infer it from the "<BaseType>/<UUID>" prefix instead.
    if data_type_management.is_v1_base_type(base_type):
        try:
            base_type, type_uuid = data_type_management.parse_v1_shorthand(data_type)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        try:
            spec = data_type_management.restore_data_type(
                fulcra_api, base_type, type_uuid
            )
            click.echo(json.dumps(spec))
        except HTTPError as exc:
            raise click.ClickException(
                f"Failed to restore data type {data_type}: {exc}"
            )
        return

    try:
        ann_id = str(UUID(parts[1]))
    except (ValueError, IndexError):
        raise click.ClickException("DATA_TYPE must be <Annotation Type>/<UUID>")

    try:
        ann = fulcra_api.restore_annotation(annotation_id=ann_id)
        click.echo(json.dumps(ann))
    except HTTPError as exc:
        raise click.ClickException(f"Failed to restore data type {data_type}: {exc}")


@data_type.command("schema", short_help="Get the JSON schema for a data type")
@click.option(
    "--api-version",
    type=str,
    default=None,
    is_eager=True,
    help="API version (required if data type has multiple versions)",
)
@click.option(
    "--user-id",
    type=str,
    default=None,
    is_eager=True,
    help="User ID for the data type (defaults to authenticated user)",
)
@click.argument(
    "data_type",
    callback=resolve_data_type(
        user_id_param="user_id", api_version_param="api_version"
    ),
)
@pass_fulcra_api
@requires_auth
def get_schema(
    fulcra_api: FulcraAPI, data_type: dict, api_version: str | None, user_id: str | None
):
    """
    Get the JSON schema for a Fulcra data type.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types.

    Examples:

    \b
    Get schema for a data type:
    fulcra data-type schema NumericAnnotation --api-version v1alpha1

    \b
    Get schema with auto-detected version (if only one exists):
    fulcra data-type schema DeletedRecord
    """
    # data_type is the resolved catalog entry (see resolve_data_type)
    try:
        # Just pull the schema from the type if populated
        schema = data_type.get("record_spec", {}).get("schema")
        if schema is None:
            schema = fulcra_api.v1_catalog_schema(
                data_type=data_type["id"],
                api_version=data_type["api_version"],
                fulcra_userid=data_type["fulcra_userid"],
            )
        click.echo(json.dumps(schema, indent=2))
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException(f"Schema not found for {data_type['id']}")
        else:
            raise click.ClickException(f"Failed to fetch schema: {exc}")
