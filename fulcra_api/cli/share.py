import json
from datetime import datetime
from typing import Any, Dict
from urllib.error import HTTPError

import click

from fulcra_api.core import FulcraAPI

from .utils import pass_fulcra_api, requires_auth


@click.group(help="Data sharing management sub-commands")
def share():
    pass


@share.command("list-outgoing", short_help="List shares you've created")
@pass_fulcra_api
@requires_auth
def list_outgoing(fulcra_api: FulcraAPI):
    """
    List all shares that you have created to share your data with others.
    """
    try:
        results = fulcra_api.get_datashares()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(
            f"Failed to retrieve outgoing shares: {exc}\n{error_body}"
        )

    for datashare in results:
        click.echo(json.dumps(datashare))


@share.command("list-incoming", short_help="List shares you've received")
@pass_fulcra_api
@requires_auth
def list_incoming(fulcra_api: FulcraAPI):
    """
    List all shares that others have shared with you.
    """
    try:
        results = fulcra_api.get_shared_datasets()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(
            f"Failed to retrieve incoming shares: {exc}\n{error_body}"
        )

    authenticated_userid = fulcra_api.get_fulcra_userid()
    # filter out dataset that is automatically generated for each user; it reflects that
    # they share all data with themselves
    for dataset in [
        r for r in results if r.get("permission_id") != authenticated_userid
    ]:
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
    help="Share all data types",
)
@pass_fulcra_api
@requires_auth
def create(
    fulcra_api: FulcraAPI, name, data_types, user_ids, start_time, end_time, share_all
):
    """
    Create a new share to share your data with other users.

    Examples:

    \b
    Share specific data types with a user:
    fulcra share create --name "Research Study" --data-type HeartRate --data-type StepCount --user-id <USER-UUID>

    \b
    Share all data types:
    fulcra share create --name "Full Access" --share-all --user-id <USER-UUID>
    """
    # Validate data types against catalog
    try:
        catalog = fulcra_api.v1_catalog()
        valid_data_type_ids = {item["id"] for item in catalog}

        # TEMPORARY: Allow "calendars" and "calendar_events" even though they're not
        # in the v1 catalog yet. Remove this special case once they're added to the catalog.
        temporary_allowed_types = {"calendars", "calendar_events"}

        invalid_types = [
            dt
            for dt in data_types
            if dt not in valid_data_type_ids and dt not in temporary_allowed_types
        ]
        if invalid_types:
            raise click.ClickException(
                f"Invalid data type(s): {', '.join(invalid_types)}. "
                f"Use 'fulcra catalog' to see valid data types."
            )
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to fetch catalog: {exc}\n{error_body}")

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
        result = fulcra_api.create_datashare(
            datashare_name=name,
            fulcra_data_types=sorted(data_types),
            allowed_user_ids=sorted(user_ids),
            share_all_data=share_all,
            time_start=parsed_start_time,
            time_end=parsed_end_time,
        )
        click.echo(json.dumps(result))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to create share: {exc}\n{error_body}")


@share.command("delete", short_help="Delete a share you created")
@click.argument("share_id")
@pass_fulcra_api
@requires_auth
def delete(fulcra_api: FulcraAPI, share_id: str):
    """
    Delete a share that you created.

    SHARE_ID: UUID of the share to delete
    """
    try:
        fulcra_api.delete_datashare(share_id)
        click.echo(f"Share {share_id} deleted successfully")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to delete share: {exc}\n{error_body}")


@share.command("leave", short_help="Leave a share")
@click.argument("share_id")
@pass_fulcra_api
@requires_auth
def leave(fulcra_api: FulcraAPI, share_id: str):
    """
    Leave a share that was shared with you (revoke your access).

    SHARE_ID: UUID of the share permission to revoke
    """
    try:
        fulcra_api.delete_dataset_permission(share_id)
        click.echo(f"Successfully left share {share_id}")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to leave share: {exc}\n{error_body}")


@share.command("update", short_help="Update an existing share")
@click.argument("share_id")
@click.option("--name", type=str, help="Update the share name")
@click.option(
    "--add-data-type",
    "add_data_types",
    multiple=True,
    help="Add a data type to the share (can be specified multiple times)",
)
@click.option(
    "--remove-data-type",
    "remove_data_types",
    multiple=True,
    help="Remove a data type from the share (can be specified multiple times)",
)
@click.option(
    "--set-data-type",
    "set_data_types",
    multiple=True,
    help="Replace all data types with this list (can be specified multiple times)",
)
@click.option(
    "--add-user-id",
    "add_user_ids",
    multiple=True,
    help="Add a user to share with (can be specified multiple times)",
)
@click.option(
    "--remove-user-id",
    "remove_user_ids",
    multiple=True,
    help="Remove a user from the share (can be specified multiple times)",
)
@click.option(
    "--set-user-id",
    "set_user_ids",
    multiple=True,
    help="Replace all users with this list (can be specified multiple times)",
)
@click.option(
    "--share-all-data",
    "share_all_data",
    is_flag=True,
    flag_value=True,
    default=None,
    help="Enable sharing all data types",
)
@click.option(
    "--no-share-all-data",
    "share_all_data",
    is_flag=True,
    flag_value=False,
    default=None,
    help="Disable sharing all data types",
)
@click.option(
    "--start-time",
    "start_time_value",
    type=str,
    help="Set start time for data range (ISO8601 format)",
)
@click.option(
    "--no-start-time",
    "no_start_time",
    is_flag=True,
    default=False,
    help="Remove start time (make share open-ended at start)",
)
@click.option(
    "--end-time",
    "end_time_value",
    type=str,
    help="Set end time for data range (ISO8601 format)",
)
@click.option(
    "--no-end-time",
    "no_end_time",
    is_flag=True,
    default=False,
    help="Remove end time (make share open-ended at end)",
)
@pass_fulcra_api
@requires_auth
def update(
    fulcra_api: FulcraAPI,
    share_id: str,
    name,
    add_data_types,
    remove_data_types,
    set_data_types,
    add_user_ids,
    remove_user_ids,
    set_user_ids,
    share_all_data,
    start_time_value,
    no_start_time,
    end_time_value,
    no_end_time,
):
    """
    Update an existing share by modifying data types, users, or settings.

    Data type IDs should match those returned by the 'fulcra catalog' command.

    SHARE_ID: UUID of the share to update

    Examples:

    \b
    Update share name:
    fulcra share update <SHARE-UUID> --name "New Share Name"

    \b
    Add data types to a share:
    fulcra share update <SHARE-UUID> --add-data-type HeartRate --add-data-type StepCount

    \b
    Remove data types from a share:
    fulcra share update <SHARE-UUID> --remove-data-type HeartRate

    \b
    Replace all data types:
    fulcra share update <SHARE-UUID> --set-data-type SleepAnalysis --set-data-type HeartRate

    \b
    Add users and remove data types in one command:
    fulcra share update <SHARE-UUID> --add-user-id <USER-UUID> --remove-data-type StepCount

    \b
    Disable share-all-data mode:
    fulcra share update <SHARE-UUID> --no-share-all-data

    \b
    Set time range:
    fulcra share update <SHARE-UUID> --start-time 2026-01-01T00:00:00 --end-time 2026-12-31T23:59:59

    \b
    Make share open-ended:
    fulcra share update <SHARE-UUID> --no-start-time --no-end-time
    """
    # Validate that at least one option is specified
    has_any_option = any(
        [
            name,
            add_data_types,
            remove_data_types,
            set_data_types,
            add_user_ids,
            remove_user_ids,
            set_user_ids,
            share_all_data is not None,
            start_time_value,
            no_start_time,
            end_time_value,
            no_end_time,
        ]
    )

    if not has_any_option:
        raise click.UsageError("Must specify at least one option to update")

    # Validate mutual exclusivity for data types
    if set_data_types and (add_data_types or remove_data_types):
        raise click.UsageError(
            "--set-data-type cannot be used with --add-data-type or --remove-data-type"
        )

    # Validate mutual exclusivity for user IDs
    if set_user_ids and (add_user_ids or remove_user_ids):
        raise click.UsageError(
            "--set-user-id cannot be used with --add-user-id or --remove-user-id"
        )

    # Validate mutual exclusivity for start time
    if start_time_value and no_start_time:
        raise click.UsageError("--start-time cannot be used with --no-start-time")

    # Validate mutual exclusivity for end time
    if end_time_value and no_end_time:
        raise click.UsageError("--end-time cannot be used with --no-end-time")

    try:
        # Fetch current share
        shares = fulcra_api.get_datashares()
        current_share = next(
            (s for s in shares if s.get("datashare_id") == share_id), None
        )
        if not current_share:
            raise click.ClickException(f"Share {share_id} not found")

        # Initialize update arguments with all current values
        update_kwargs: Dict[str, Any] = {
            "datashare_id": share_id,
            "datashare_name": current_share.get("datashare_name"),
            "fulcra_data_types": current_share.get("fulcra_data_types"),
            "allowed_user_ids": [
                p["allowed_fulcra_userid"] for p in current_share.get("permissions", [])
            ],
            "share_all_data": current_share.get("share_all_data"),
            "time_start": datetime.fromisoformat(current_share["time_start"])
            if current_share.get("time_start")
            else None,
            "time_end": datetime.fromisoformat(current_share["time_end"])
            if current_share.get("time_end")
            else None,
        }

        # Override with provided values

        # Handle name
        if name:
            update_kwargs["datashare_name"] = name

        # Handle data types
        if set_data_types:
            update_kwargs["fulcra_data_types"] = sorted(set_data_types)
        elif add_data_types or remove_data_types:
            current_data_types = set(update_kwargs["fulcra_data_types"] or [])

            for dt in add_data_types:
                if dt in current_data_types:
                    click.echo(f"Warning: {dt} already in share, skipping", err=True)
                else:
                    current_data_types.add(dt)

            for dt in remove_data_types:
                if dt not in current_data_types:
                    click.echo(f"Warning: {dt} not in share, skipping", err=True)
                else:
                    current_data_types.remove(dt)

            update_kwargs["fulcra_data_types"] = sorted(current_data_types)

        # Handle user IDs
        if set_user_ids:
            update_kwargs["allowed_user_ids"] = sorted(set_user_ids)
        elif add_user_ids or remove_user_ids:
            current_user_ids = set(update_kwargs["allowed_user_ids"] or [])

            for uid in add_user_ids:
                if uid in current_user_ids:
                    click.echo(f"Warning: {uid} already in share, skipping", err=True)
                else:
                    current_user_ids.add(uid)

            for uid in remove_user_ids:
                if uid not in current_user_ids:
                    click.echo(f"Warning: {uid} not in share, skipping", err=True)
                else:
                    current_user_ids.remove(uid)

            update_kwargs["allowed_user_ids"] = sorted(current_user_ids)

        # Handle share_all_data flag
        if share_all_data is not None:
            update_kwargs["share_all_data"] = share_all_data

        # Handle start time
        if start_time_value:
            try:
                update_kwargs["time_start"] = datetime.fromisoformat(start_time_value)
            except ValueError:
                raise click.ClickException(
                    f"Invalid start time format: {start_time_value}. Use ISO8601 format."
                )
        elif no_start_time:
            update_kwargs["time_start"] = None

        # Handle end time
        if end_time_value:
            try:
                update_kwargs["time_end"] = datetime.fromisoformat(end_time_value)
            except ValueError:
                raise click.ClickException(
                    f"Invalid end time format: {end_time_value}. Use ISO8601 format."
                )
        elif no_end_time:
            update_kwargs["time_end"] = None

        # Update the share
        result = fulcra_api.update_datashare(**update_kwargs)
        click.echo(json.dumps(result))

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to update share: {exc}\n{error_body}")
