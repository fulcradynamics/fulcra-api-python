import json
from typing import List, Optional, Tuple
from urllib.error import HTTPError
from uuid import UUID

import click

from fulcra_api.core import FulcraAPI

from .utils import pass_fulcra_api, requires_auth


@click.group(name="data-type", help="Data type management sub-commands")
def data_type():
    pass


@data_type.command("create", short_help="Create a new data type")
@click.argument("base_data_type", type=str)
@click.argument("name", type=str)
@click.option(
    "-d", "--description", type=str, default=None, help="Description of the data type"
)
@click.option(
    "-t",
    "--tag",
    "tags",
    type=str,
    multiple=True,
    help="Tags to attach to the data type",
)
@click.option(
    "-k",
    "--kind",
    "metric_kind",
    type=click.Choice(
        [
            "cumulative",
            "discrete",
        ]
    ),
)
@click.option(
    "-v",
    "--value",
    "raw_value",
    type=str,
    help="Default value for recording the data type",
)
@click.option("-u", "--unit", "unit", type=str, help="Unit for recording the data type")
@click.option(
    "-s",
    "--scale-label",
    "scale_labels",
    type=str,
    multiple=True,
    help="Used for ScaleAnnotation labels",
)
@click.option(
    "--add-to-timeline", is_flag=True, help="Add created data type to timeline"
)
@pass_fulcra_api
@requires_auth
def data_type_create(
    fulcra_api: FulcraAPI,
    base_data_type: str,
    name: str,
    description: Optional[str],
    tags: List[str],
    metric_kind: Optional[str],
    raw_value: Optional[str],
    unit: Optional[str],
    scale_labels: List[str],
    add_to_timeline: bool,
):
    """Create a new data type from a base data type.

    BASE_DATA_TYPE: The base data type to create from. Use fulcra catalog --base-types-only for valid options

    NAME: The given name of the data type

    Use -d/--description to add an optional description
    """

    try:
        catalog_resp = fulcra_api.v1_catalog(
            data_type=base_data_type, fulcra_userid=fulcra_api.get_fulcra_userid()
        )
    except HTTPError as exc:
        raise click.ClickException(f"Failed to validate BASE_DATA_TYPE: {exc}")

    filtered_base_data_types = [
        c
        for c in catalog_resp
        if "base_type" in c.get("categories", [])
        and c.get("api_version", "") == "v1alpha1"
    ]

    if len(filtered_base_data_types) != 1:
        raise click.ClickException(
            f"Multiple base data types found for identifier: {base_data_type}"
        )

    fulcra_data_type = filtered_base_data_types[0]
    if fulcra_data_type.get("record_spec", {}).get("type") != "metric":
        if (
            metric_kind is not None
        ):  # TODO: DurationAnnotation actually does support metric_kind
            raise click.BadOptionUsage(
                "metric_kind",
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
            metric_kind=metric_kind,
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


@data_type.command("archive", short_help="Archive a user-defined data type")
@click.argument("data_type")
@pass_fulcra_api
@requires_auth
def data_type_archive(fulcra_api: FulcraAPI, data_type: str):
    """
    Archive a user-defined data type by ID.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types
    """

    try:
        filtered_types = fulcra_api.v1_catalog(
            data_type=data_type, fulcra_userid=fulcra_api.get_fulcra_userid()
        )
    except HTTPError:
        raise click.ClickException(f"Could not find data type matching id: {data_type}")

    if len(filtered_types) == 0:
        raise click.ClickException(f"Could not find data type matching id: {data_type}")
    elif len(filtered_types) > 1:
        raise click.ClickException(
            f"Found multiple data types matching id: {data_type}"
        )

    ann_id = None
    try:
        parts = data_type.split("/", maxsplit=2)
        ann_id = parts[1]
        ann_id = str(UUID(ann_id))
    except (ValueError, IndexError):
        raise click.ClickException("DATA_TYPE must be <Annotation Type>/<UUID>")

    try:
        fulcra_api.delete_annotation(annotation_id=ann_id)
        click.echo(f"Archived data type: {data_type}")
    except HTTPError as exc:
        raise click.ClickException(f"Failed to archive data type {data_type}: {exc}")


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
        filtered_types = fulcra_api.v1_catalog(
            data_type=data_type, fulcra_userid=fulcra_api.get_fulcra_userid()
        )
    except HTTPError:
        raise click.ClickException(f"Could not find data type matching id: {data_type}")

    if len(filtered_types) == 0:
        raise click.ClickException(f"Could not find data type matching id: {data_type}")
    elif len(filtered_types) > 1:
        raise click.ClickException(
            f"Found multiple data types matching id: {data_type}"
        )

    ann_id = None
    try:
        parts = data_type.split("/", maxsplit=2)
        ann_id = parts[1]
        ann_id = str(UUID(ann_id))
    except (ValueError, IndexError):
        raise click.ClickException("DATA_TYPE must be <Annotation Type>/<UUID>")

    try:
        ann = fulcra_api.restore_annotation(annotation_id=ann_id)
        click.echo(json.dumps(ann))
    except HTTPError as exc:
        raise click.ClickException(f"Failed to restore data type {data_type}: {exc}")


@data_type.command("schema", short_help="Get the JSON schema for a data type")
@click.argument("data_type")
@click.option(
    "--api-version",
    type=str,
    default=None,
    help="API version (required if data type has multiple versions)",
)
@click.option(
    "--user-id",
    type=str,
    default=None,
    help="User ID for the data type (defaults to authenticated user)",
)
@pass_fulcra_api
@requires_auth
def get_schema(
    fulcra_api: FulcraAPI, data_type: str, api_version: str | None, user_id: str | None
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
    try:
        dt = fulcra_api.disambiguate_data_type(
            data_type=data_type, api_version=api_version, fulcra_userid=user_id
        )
        schema = fulcra_api.v1_catalog_schema(
            data_type=dt["id"],
            api_version=dt["api_version"],
            fulcra_userid=dt["fulcra_userid"],
        )
        click.echo(json.dumps(schema, indent=2))
    except ValueError as exc:
        raise click.ClickException(str(exc))
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException(f"Schema not found for {data_type}")
        else:
            raise click.ClickException(f"Failed to fetch schema: {exc}")
