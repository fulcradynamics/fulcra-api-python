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
@click.option(
    "--tag",
    "tags",
    multiple=True,
    default=(),
    help="Tag to add to record(s). Can be used multiple times.",
)
@click.option(
    "--source",
    "sources",
    multiple=True,
    default=(),
    help="Source to add to record(s). Can be used multiple times. Includes 'com.fulcradynamics.cli'.",
)
@click.pass_context
@pass_fulcra_api
@requires_auth
def record(
    fulcra_api: FulcraAPI,
    ctx: click.Context,
    data_type: str,
    value: str | None,
    file: click.File | None,
    api_version: str | None,
    no_validate: bool,
    tags: tuple,
    sources: tuple,
):
    """
    Record data for a Fulcra data type.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog --recordable-only` for a list of
    recordable Fulcra Data Types.

    VALUE: Optional metric value for quick recording (e.g., "75.5" for NumericAnnotation)

    Reads JSON or JSONL (newline-delimited JSON) records from stdin or a file, unless VALUE or
    --field-* options are provided. Each record should conform to the schema for the specified data type.

    Field options (--<NAME>=<VALUE>) allow setting arbitrary record fields. Values are parsed
    as JSON first (numbers, booleans, objects), falling back to strings if not valid JSON.

    To see available fields for a data type, use:
    fulcra data-type schema <DATA_TYPE> --api-version <VERSION>

    Examples:

    \b
    Quick record a metric value:
    fulcra record NumericAnnotation/<UUID> 75.5

    \b
    Quick record with field options:
    fulcra record NumericAnnotation/<UUID> --value=75.5 --note="Resting heart rate"

    \b
    Record an event with a note:
    fulcra record MomentAnnotation/<UUID> --note="Felt energized"

    \b
    Record with boolean and numeric fields:
    fulcra record BooleanAnnotation/<UUID> --value=true --note="Test"

    \b
    Record from stdin (single JSON object):
    echo '{"value": 75.5, "unit": "bpm"}' | fulcra record NumericAnnotation/<UUID>

    \b
    Record from stdin (JSONL - multiple records):
    echo '{"value": 75.5}
    {"value": 80.2}' | fulcra record NumericAnnotation/<UUID>

    \b
    Record from a file:
    fulcra record NumericAnnotation/<UUID> -f records.jsonl
    """
    try:
        # VALUE argument is incompatible with --file
        if value is not None and file is not None:
            raise click.ClickException("Cannot specify both VALUE and --file")

        # Copy extra args and prepend VALUE if it's a field option
        args_to_parse = list(ctx.args)
        if value is not None and value.startswith("--"):
            args_to_parse.insert(0, value)
            value = None

        # Parse field options from args (any --option not handled by Click)
        fields = {}

        # If VALUE provided, treat it as setting the "value" field first
        # Parse as JSON (--value can still override)
        if value is not None:
            try:
                parsed_value = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                parsed_value = value
            fields["value"] = parsed_value

        args_iter = iter(args_to_parse)
        for arg in args_iter:
            if arg.startswith("--"):
                field_spec = arg[2:]  # Remove "--" prefix
                if "=" in field_spec:
                    # Handle --name=value format
                    field_name, field_value = field_spec.split("=", 1)
                else:
                    # Handle --name value format
                    field_name = field_spec
                    try:
                        next_arg = next(args_iter)
                        if next_arg.startswith("--"):
                            raise click.ClickException(
                                f"--{field_name} requires a value"
                            )
                        field_value = next_arg
                    except StopIteration:
                        raise click.ClickException(f"--{field_name} requires a value")

                # Parse value as JSON first, fall back to string
                try:
                    parsed_value = json.loads(field_value)
                except (json.JSONDecodeError, ValueError):
                    parsed_value = field_value

                fields[field_name] = parsed_value

        # Handle quick recording with VALUE and/or --field-* options
        if value is not None or fields:
            records = [fields]
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

            # Apply --field-* options to all records from file/stdin
            if fields:
                for record in records:
                    record.update(fields)

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

        # Resolve tag names to UUIDs
        tag_ids = []
        if tags:
            resolved_tags = fulcra_api.create_tags(list(tags))
            tag_ids = [t["id"] for t in resolved_tags]

        # Build sources list: CLI source, --source options, then annotation source
        sources_to_add = ["com.fulcradynamics.cli"] + list(sources)
        if annotation_source:
            sources_to_add.append(annotation_source)

        # Apply --tag and --source options to all records
        for record in records:
            # Add tags (append to existing, but avoid duplicates)
            if tag_ids:
                record_tags = record.get("tags", [])
                for tag_id in tag_ids:
                    if tag_id not in record_tags:
                        record_tags.append(tag_id)
                record["tags"] = record_tags

            # Add sources: filter duplicates from record, then append our sources
            if sources_to_add:
                record_sources = record.get("sources", [])
                # Remove any sources from record that we're about to add
                record_sources = [s for s in record_sources if s not in sources_to_add]
                # Append CLI source, options, and annotation source
                record_sources.extend(sources_to_add)
                record["sources"] = record_sources

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
@click.argument("record_id", required=False)
@click.option("-f", "--file", type=click.File("r"), default=None)
@click.option(
    "--api-version",
    type=str,
    default="v1alpha1",
    help="API version to use (default: v1alpha1)",
)
@click.option(
    "--no-validate",
    is_flag=True,
    default=False,
    help="Skip schema validation before deleting",
)
@pass_fulcra_api
@requires_auth
def delete_records(
    fulcra_api: FulcraAPI,
    data_type: str,
    record_id: str | None,
    file: click.File | None,
    api_version: str | None,
    no_validate: bool,
):
    """
    Delete records for a Fulcra data type.

    Deletion works by posting DeletedRecord tombstones. Only recordable data types support
    deletion. Run `fulcra catalog --recordable-only` for a list of data types that can be deleted.

    DATA_TYPE: The Fulcra data type of the records being deleted

    RECORD_ID: (Optional) A single record UUID to delete

    Reads JSON or JSONL (newline-delimited JSON) deletion records from stdin or a file, unless
    RECORD_ID is provided. Each record should have the form {"record_id": "<UUID>"}.

    Examples:

    \b
    Quick delete a single record:
    fulcra delete NumericAnnotation/<UUID> <RECORD-ID>

    \b
    Delete from stdin (JSONL - multiple records):
    echo '{"record_id": "id1"}
    {"record_id": "id2"}' | fulcra delete NumericAnnotation/<UUID>

    \b
    Delete from a file:
    fulcra delete NumericAnnotation/<UUID> -f deletions.jsonl
    """
    try:
        # RECORD_ID argument is incompatible with --file
        if record_id is not None and file is not None:
            raise click.ClickException("Cannot specify both RECORD_ID and --file")

        # Extract base type (strip UUID if present)
        base_type = data_type.split("/")[0] if "/" in data_type else data_type

        # Build deletion records
        records = []

        if record_id is not None:
            # Quick form: single record ID
            records = [{"record_id": record_id}]
        else:
            # Read from file or stdin
            input_source = file if file else click.get_text_stream("stdin")
            input_data = input_source.read().strip()

            if not input_data:
                raise click.ClickException(
                    "No RECORD_ID provided and no data in stdin/file"
                )

            # Parse JSONL or JSON
            lines = input_data.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as e:
                    raise click.ClickException(f"Invalid JSON in input: {e}")

        if not records:
            raise click.ClickException("No records to delete")

        # Add data_type field to each record
        for record in records:
            record["data_type"] = base_type

        # Validate records unless --no-validate
        if not no_validate:
            try:
                errors = fulcra_api.validate_records(
                    "DeletedRecord", records, api_version=api_version
                )
                if errors:
                    error_msg = "Validation failed:\n"
                    for idx, msg, _ in errors:
                        error_msg += f"  Record {idx + 1}: {msg}\n"
                    raise click.ClickException(error_msg)
            except HTTPError as exc:
                if exc.code == 404:
                    raise click.ClickException(
                        f"Schema not found for DeletedRecord/{api_version}. "
                        "Use --no-validate to skip validation"
                    )
                else:
                    raise click.ClickException(f"Failed to fetch schema: {exc}")

        # Record the tombstones
        kwargs = {"data_type": "DeletedRecord", "records": records}
        if api_version is not None:
            kwargs["api_version"] = api_version

        response = fulcra_api.record_data_type(**kwargs)

        # Print upload ID
        click.echo(response["upload_id"])

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to delete records: {exc}\n{error_body}")
