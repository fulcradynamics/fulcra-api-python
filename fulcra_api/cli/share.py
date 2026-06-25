import json
from datetime import datetime
from urllib.error import HTTPError

import click

from .utils import requires_auth


@click.group(help="Data sharing management sub-commands")
def share():
    pass


@share.command("list-outgoing", short_help="List shares you've created")
@click.pass_context
@requires_auth
def list_outgoing(ctx):
    """
    List all shares that you have created to share your data with others.
    """
    try:
        results = ctx.obj.get_datashares()
    except HTTPError as exc:
        raise click.ClickException(exc)

    for datashare in results:
        click.echo(json.dumps(datashare))


@share.command("list-incoming", short_help="List shares you've received")
@click.pass_context
@requires_auth
def list_incoming(ctx):
    """
    List all shares that others have shared with you.
    """
    try:
        results = ctx.obj.get_shared_datasets()
    except HTTPError as exc:
        raise click.ClickException(exc)

    for dataset in results:
        click.echo(json.dumps(dataset))


@share.command("create", short_help="Create a new share")
@click.option("--name", required=True, help="Name for this share")
@click.option(
    "--data-type",
    "data_types",
    multiple=True,
    required=True,
    help="Data type ID to share (can be specified multiple times)",
)
@click.option(
    "--user-id",
    "user_ids",
    multiple=True,
    required=True,
    help="User ID to share with (can be specified multiple times)",
)
@click.option("--start-time", type=str, help="Optional start time (ISO8601 format)")
@click.option("--end-time", type=str, help="Optional end time (ISO8601 format)")
@click.option(
    "--share-all",
    is_flag=True,
    default=False,
    help="Share all data types (ignores --data-type)",
)
@click.pass_context
@requires_auth
def create(ctx, name, data_types, user_ids, start_time, end_time, share_all):
    """
    Create a new share to share your data with other users.

    Examples:

    \b
    Share specific data types with a user:
    fulcra share create --name "Research Study" --data-type HeartRate --data-type StepCount --user-id <user-uuid>

    \b
    Share all data types:
    fulcra share create --name "Full Access" --share-all --user-id <user-uuid>
    """
    # Validate data types against catalog
    if not share_all:
        try:
            catalog = ctx.obj.v1_catalog()
            valid_data_type_ids = {item["id"] for item in catalog}

            invalid_types = [dt for dt in data_types if dt not in valid_data_type_ids]
            if invalid_types:
                raise click.ClickException(
                    f"Invalid data type(s): {', '.join(invalid_types)}. "
                    f"Use 'fulcra catalog' to see valid data types."
                )
        except HTTPError as exc:
            raise click.ClickException(f"Failed to fetch catalog: {exc}")

    # Parse time arguments if provided
    parsed_start_time = None
    parsed_end_time = None
    if start_time:
        try:
            parsed_start_time = datetime.fromisoformat(start_time)
        except ValueError:
            raise click.ClickException(
                f"Invalid start time format: {start_time}. Use ISO8601 format."
            )

    if end_time:
        try:
            parsed_end_time = datetime.fromisoformat(end_time)
        except ValueError:
            raise click.ClickException(
                f"Invalid end time format: {end_time}. Use ISO8601 format."
            )

    # Create the datashare
    try:
        result = ctx.obj.create_datashare(
            datashare_name=name,
            fulcra_data_types=list(data_types) if not share_all else [],
            allowed_user_ids=list(user_ids),
            share_all_data=share_all,
            time_start=parsed_start_time,
            time_end=parsed_end_time,
        )
        click.echo(json.dumps(result))
    except HTTPError as exc:
        raise click.ClickException(f"Failed to create share: {exc}")


@share.command("delete", short_help="Delete a share you created")
@click.argument("share_id")
@click.pass_context
@requires_auth
def delete(ctx, share_id: str):
    """
    Delete a share that you created.

    SHARE_ID: UUID of the share to delete
    """
    try:
        ctx.obj.delete_datashare(share_id)
        click.echo(f"Share {share_id} deleted successfully")
    except HTTPError as exc:
        raise click.ClickException(exc)


@share.command("leave", short_help="Leave a share")
@click.argument("share_id")
@click.pass_context
@requires_auth
def leave(ctx, share_id: str):
    """
    Leave a share that was shared with you (revoke your access).

    SHARE_ID: UUID of the share permission to revoke
    """
    try:
        ctx.obj.delete_dataset_permission(share_id)
        click.echo(f"Successfully left share {share_id}")
    except HTTPError as exc:
        raise click.ClickException(exc)
