import json
from typing import List, Optional, Tuple
from urllib.error import HTTPError

import click

from fulcra_api.core import FulcraAPI

from .utils import pass_fulcra_api, requires_auth


@click.command(
    "record",
    short_help="Record data for a data type",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    ),
)
@click.argument("data_type")
@click.argument("value", required=False)
@click.option(
    "-f",
    "--file",
    type=click.File("r"),
    default=None,
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
@pass_fulcra_api
@requires_auth
def record(
    fulcra_api: FulcraAPI,
    ctx: click.Context,
    data_type: str,
    value: str | None,
    file,
    api_version: str | None,
    no_validate: bool,
):
    """
    Record data for a Fulcra data type.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog --recordable-only` for a list of
    recordable Fulcra Data Types.

    VALUE: Optional metric value for quick recording (e.g., "75.5" for NumericAnnotation)

    Reads JSON or JSONL (newline-delimited JSON) records from stdin or a file, unless VALUE or
    --field-* options are provided. Each record should conform to the schema for the specified data type.

    Field options (--field-<name>=<value>) allow setting arbitrary record fields. Values are parsed
    as JSON first (numbers, booleans, objects), falling back to strings if not valid JSON.

    Examples:

    \b
    Quick record a metric value:
    fulcra record NumericAnnotation/<uuid> 75.5

    \b
    Quick record with field options:
    fulcra record NumericAnnotation/<uuid> --field-value=75.5 --field-note="Resting heart rate"

    \b
    Record an event with a note:
    fulcra record MomentAnnotation/<uuid> --field-note="Felt energized"

    \b
    Record with boolean and numeric fields:
    fulcra record BooleanAnnotation/<uuid> --field-value=true --field-note="Test"

    \b
    Record from stdin (single JSON object):
    echo '{"value": 75.5, "unit": "bpm"}' | fulcra record NumericAnnotation/<uuid>

    \b
    Record from stdin (JSONL - multiple records):
    echo '{"value": 75.5}
    {"value": 80.2}' | fulcra record NumericAnnotation/<uuid>

    \b
    Record from a file:
    fulcra record NumericAnnotation/<uuid> -f records.jsonl
    """
    try:
        # Copy extra args and prepend VALUE if it's a --field-* option
        args_to_parse = list(ctx.args)
        if value is not None and value.startswith("--field-"):
            args_to_parse.insert(0, value)
            value = None

        # Parse --field-* options from args
        fields = {}
        i = 0
        while i < len(args_to_parse):
            arg = args_to_parse[i]
            if arg.startswith("--field-"):
                field_spec = arg[8:]  # Remove "--field-" prefix
                if "=" in field_spec:
                    # Handle --field-name=value format
                    field_name, field_value = field_spec.split("=", 1)
                else:
                    # Handle --field-name value format
                    field_name = field_spec
                    if i + 1 < len(args_to_parse) and not args_to_parse[
                        i + 1
                    ].startswith("--"):
                        i += 1
                        field_value = args_to_parse[i]
                    else:
                        raise click.ClickException(
                            f"--field-{field_name} requires a value"
                        )

                # Parse value as JSON first, fall back to string
                try:
                    parsed_value = json.loads(field_value)
                except (json.JSONDecodeError, ValueError):
                    parsed_value = field_value

                fields[field_name] = parsed_value
            i += 1

        # Handle quick recording with VALUE and/or --field-* options
        if value is not None or fields:
            if file is not None:
                raise click.ClickException(
                    "Cannot specify both VALUE/--field-* and --file"
                )

            if value is not None and "value" in fields:
                raise click.ClickException(
                    "Cannot specify both VALUE and --field-value"
                )

            record = dict(fields)
            if value is not None:
                # Parse value as number
                try:
                    numeric_value = float(value)
                except ValueError:
                    raise click.ClickException(f"VALUE must be a number, got: {value}")
                record["value"] = numeric_value

            records = [record]
        else:
            # Read input from file or stdin
            if file is None:
                file = click.get_text_stream("stdin")

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
                        raise click.ClickException(
                            f"Invalid JSON on line {line_num}: {e}"
                        )
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
                catalog_results = fulcra_api.v1_catalog(data_type=base_type)
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
                validation_errors = fulcra_api.validate_records(
                    base_type, records, schema_api_version
                )

                # Check for validation errors (only invalid records are returned)
                if validation_errors:
                    idx, error_msg, error_obj = validation_errors[0]
                    raise click.ClickException(
                        f"Validation error in record {idx + 1}: {error_msg}"
                    )
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

        response = fulcra_api.record_data_type(**kwargs)

        # Print upload ID
        click.echo(response["upload_id"])

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to record data: {exc}\n{error_body}")


@click.command("delete", short_help="Delete records for a data type")
@click.argument("data_type")
@click.argument("record_ids", nargs=-1, required=True)
@click.option(
    "--api-version",
    type=str,
    default=None,
    help="API version to use (optional)",
)
@pass_fulcra_api
@requires_auth
def delete_records(
    fulcra_api: FulcraAPI, data_type: str, record_ids: tuple, api_version: str | None
):
    """
    Delete records for a Fulcra data type.

    Deletion works by posting DeletedRecord tombstones. Only recordable data types support
    deletion. Run `fulcra catalog --recordable-only` for a list of data types that can be deleted.

    DATA_TYPE: The Fulcra data type of the records to delete

    RECORD_IDS: One or more record UUIDs to delete

    Examples:

    \b
    Delete a single record:
    fulcra delete NumericAnnotation/<uuid> <record-id>

    \b
    Delete multiple records:
    fulcra delete NumericAnnotation/<uuid> <id1> <id2> <id3>
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

        response = fulcra_api.record_data_type(**kwargs)

        # Print upload ID
        click.echo(response["upload_id"])

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to delete records: {exc}\n{error_body}")
