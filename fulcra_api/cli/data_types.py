import json
from typing import List, Optional, Tuple
from urllib.error import HTTPError
from uuid import UUID

import click
import jsonschema

from .utils import requires_auth


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
@click.pass_context
@requires_auth
def data_type_create(
    ctx,
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
        catalog_resp = ctx.obj.v1_catalog(base_data_type)
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
    if fulcra_data_type.get("klass", "") != "metric":
        if (
            metric_kind is not None
        ):  # TODO: DurationAnnotation actually does support metric_kind
            raise click.BadOptionUsage(
                "metric_kind",
                f"-k / --kind cannot be used with base data type {base_data_type}",
                ctx,
            )

        if raw_value is not None:
            raise click.BadOptionUsage(
                "raw_value",
                f"-v / --value cannot be used with base data type {base_data_type}",
                ctx,
            )

        if unit is not None:
            raise click.BadOptionUsage(
                "unit",
                f"-u / --unit cannot be used with base data type {base_data_type}",
                ctx,
            )

    # TODO: Possibly update type metadata to be able to determine that this is a scale
    if fulcra_data_type["id"] == "ScaleAnnotation" and len(scale_labels) > 0:
        raise click.BadOptionUsage(
            "scale_labels",
            f"-s / --scale-labels cannot be used with base data type {base_data_type}",
            ctx,
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
                    ctx,
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
                    f"-s / --scale-labels must be used with exactly 5 values with base data type {base_data_type}",
                    ctx,
                )
            # user-service does not accept a unit for scale annotations
            if unit is not None:
                raise click.BadOptionUsage(
                    "unit",
                    f"-u / --unit cannot be used with base data type {base_data_type}",
                    ctx,
                )
        case _:
            raise click.ClickException(f"Unsupported base type: {base_data_type}")

    try:
        ann = ctx.obj.create_annotation(
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
                info = ctx.obj.get_user_info()
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

                ctx.obj.update_user_preferences(prefs_payload)
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
@click.pass_context
@requires_auth
def data_type_archive(ctx, data_type: str):
    """
    Archive a user-defined data type by ID.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types
    """

    try:
        filtered_types = ctx.obj.v1_catalog(data_type=data_type)
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
        ctx.obj.delete_annotation(annotation_id=ann_id)
        click.echo(f"Archived data type: {data_type}")
    except HTTPError as exc:
        raise click.ClickException(f"Failed to archive data type {data_type}: {exc}")


@data_type.command("restore", short_help="Restore an archived user-defined data type")
@click.argument("data_type")
@click.pass_context
@requires_auth
def restore_data_type(ctx, data_type: str):
    """
    Restore an archived user-defined data type by ID.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types
    """

    try:
        filtered_types = ctx.obj.v1_catalog(data_type=data_type)
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
        ann = ctx.obj.restore_annotation(annotation_id=ann_id)
        click.echo(json.dumps(ann))
    except HTTPError as exc:
        raise click.ClickException(f"Failed to restore data type {data_type}: {exc}")


@data_type.command("record", short_help="Record data for a data type")
@click.argument("data_type")
@click.option(
    "-f",
    "--file",
    type=click.File("r"),
    default="-",
    help="File containing JSON or JSONL records (default: stdin)",
)
@click.option(
    "--api-version",
    type=str,
    default=None,
    help="API version to use (optional)",
)
@click.option(
    "--no-validate",
    is_flag=True,
    default=False,
    help="Skip schema validation",
)
@click.pass_context
@requires_auth
def record_data_type_cmd(
    ctx, data_type: str, file, api_version: str | None, no_validate: bool
):
    """
    Record data for a Fulcra data type.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types

    Reads JSON or JSONL (newline-delimited JSON) records from stdin or a file.
    Each record should conform to the schema for the specified data type.

    Examples:

    \b
    Record from stdin (single JSON object):
    echo '{"value": 75.5, "unit": "bpm"}' | fulcra data-type record NumericAnnotation/<uuid>

    \b
    Record from stdin (JSONL - multiple records):
    echo '{"value": 75.5}
    {"value": 80.2}' | fulcra data-type record NumericAnnotation/<uuid>

    \b
    Record from a file:
    fulcra data-type record NumericAnnotation/<uuid> -f records.jsonl
    """
    try:
        # Read input
        content = file.read().strip()
        if not content:
            raise click.ClickException("No input provided")

        # Parse as JSONL or JSON
        records = []
        lines = content.split("\n")

        # Try parsing as JSONL first (one JSON object per line)
        if len(lines) > 1 or (len(lines) == 1 and not content.startswith("[")):
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as e:
                    raise click.ClickException(f"Invalid JSON on line {line_num}: {e}")
        else:
            # Try parsing as JSON array
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    records = parsed
                elif isinstance(parsed, dict):
                    records = [parsed]
                else:
                    raise click.ClickException(
                        "Input must be a JSON object, array, or JSONL"
                    )
            except json.JSONDecodeError as e:
                raise click.ClickException(f"Invalid JSON: {e}")

        if not records:
            raise click.ClickException("No valid records found in input")

        # Handle user-created annotation types (BaseType/UUID format)
        annotation_source = None
        base_type = data_type
        if "/" in data_type:
            parts = data_type.split("/", maxsplit=1)
            base_type = parts[0]
            annotation_uuid = parts[1].lower()
            annotation_source = f"com.fulcradynamics.annotation.{annotation_uuid}"

        # Determine API version for schema validation
        schema_api_version = api_version
        if schema_api_version is None and not no_validate:
            # Query catalog to find the data type and its API version
            try:
                catalog_results = ctx.obj.v1_catalog(data_type=base_type)
                if len(catalog_results) == 0:
                    raise click.ClickException(
                        f"Data type '{base_type}' not found in catalog"
                    )
                elif len(catalog_results) > 1:
                    raise click.ClickException(
                        f"Multiple data types found for '{base_type}'. "
                        "Please specify --api-version"
                    )
                schema_api_version = catalog_results[0]["api_version"]
            except HTTPError as exc:
                raise click.ClickException(
                    f"Failed to query catalog for {base_type}: {exc}"
                )

        # Validate records against schema if requested
        if not no_validate:
            try:
                # Fetch schema for the data type
                schema_resp = ctx.obj.fulcra_api(
                    f"/data/v1/catalog/{base_type}/{schema_api_version}/schema"
                )
                schema = json.loads(schema_resp)

                # Validate each record
                for idx, record in enumerate(records):
                    try:
                        jsonschema.validate(instance=record, schema=schema)
                    except jsonschema.ValidationError as e:
                        error_msg = f"Validation error in record {idx + 1}: {e.message}"
                        if e.path:
                            error_msg += f"\nPath: {'.'.join(str(p) for p in e.path)}"
                        raise click.ClickException(error_msg)
            except HTTPError as exc:
                if exc.code == 404:
                    raise click.ClickException(
                        f"Schema not found for {base_type}/{schema_api_version}. "
                        "Use --no-validate to skip validation"
                    )
                else:
                    raise click.ClickException(f"Failed to fetch schema: {exc}")

        # Add annotation source to records if needed
        if annotation_source:
            for record in records:
                sources = record.get("sources", [])
                if annotation_source not in sources:
                    sources.append(annotation_source)
                    record["sources"] = sources

        # Record data using base type
        kwargs = {"data_type": base_type, "records": records}
        if api_version is not None:
            kwargs["api_version"] = api_version

        response = ctx.obj.record_data_type(**kwargs)

        # Print upload ID
        click.echo(response["upload_id"])

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to record data: {exc}\n{error_body}")


@data_type.command("delete-records", short_help="Delete records by posting tombstones")
@click.argument("data_type")
@click.argument("record_ids", nargs=-1, required=True)
@click.option(
    "--api-version",
    type=str,
    default=None,
    help="API version to use (optional)",
)
@click.pass_context
@requires_auth
def delete_records_cmd(ctx, data_type: str, record_ids: tuple, api_version: str | None):
    """
    Delete records by posting DeletedRecord tombstones.

    DATA_TYPE: The Fulcra data type of the records to delete

    RECORD_IDS: One or more record UUIDs to delete

    Examples:

    \b
    Delete a single record:
    fulcra data-type delete-records NumericAnnotation/<uuid> <record-id>

    \b
    Delete multiple records:
    fulcra data-type delete-records NumericAnnotation/<uuid> <id1> <id2> <id3>
    """
    try:
        # Extract base type (strip UUID if present)
        base_type = data_type.split("/")[0] if "/" in data_type else data_type

        # Create DeletedRecord tombstones for each record
        tombstones = [
            {"record_id": record_id, "data_type": base_type} for record_id in record_ids
        ]

        # Record the tombstones
        kwargs = {"data_type": "DeletedRecord", "records": tombstones}
        if api_version is not None:
            kwargs["api_version"] = api_version

        response = ctx.obj.record_data_type(**kwargs)

        # Print upload ID
        click.echo(response["upload_id"])

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to delete records: {exc}\n{error_body}")
