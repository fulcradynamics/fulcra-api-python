import json
from datetime import datetime
from typing import Any, Dict
from urllib.error import HTTPError

import click

from fulcra_api.core import FulcraAPI

from .utils import file_share_type, pass_fulcra_api, requires_auth, valid_share_types


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
    help="Data type ID to share (can be specified multiple times)",
)
@click.option(
    "--file",
    "files",
    multiple=True,
    help='File to share (can be specified multiple times). Suffix with "/" to share a prefix. Shares the live version only.',
)
@click.option(
    "--file-history",
    "file_histories",
    multiple=True,
    help='File history to share, including live version (can be specified multiple times). Suffix with "/" to share a prefix.',
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
@click.option(
    "--no-validate",
    is_flag=True,
    default=False,
    help="Skip data type validation",
)
@pass_fulcra_api
@requires_auth
def create(
    fulcra_api: FulcraAPI,
    name: str,
    data_types: list[str],
    files: list[str],
    file_histories: list[str],
    user_ids: list[str],
    start_time: str | None,
    end_time: str | None,
    share_all: bool,
    no_validate: bool,
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
    share_types = data_types
    for file in files:
        share_types.append(file_share_type(prefix=file, history=False))
    for file_history in file_histories:
        share_types.append(file_share_type(prefix=file_history, history=True))

    if not no_validate:
        share_types = valid_share_types(fulcra_api=fulcra_api, share_types=share_types)

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
            fulcra_data_types=share_types,
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
    "--add-file",
    "add_files",
    multiple=True,
    help='Add a file to the share (can be specified multiple times). Suffix with "/" to share a prefix. Shares the live version only.',
)
@click.option(
    "--remove-file",
    "remove_files",
    multiple=True,
    help="Remove a live version file or prefix from the share (can be specified multiple times)",
)
@click.option(
    "--set-file",
    "set_files",
    multiple=True,
    help="Replace all live version file and prefix shares with this list (can be specified multiple times)",
)
@click.option(
    "--add-file-history",
    "add_file_histories",
    multiple=True,
    help='Add a file history to the share, including live version (can be specified multiple times). Suffix with "/" to share a prefix.',
)
@click.option(
    "--remove-file-history",
    "remove_file_histories",
    multiple=True,
    help="Remove a file or prefix history from the share (can be specified multiple times)",
)
@click.option(
    "--set-file-history",
    "set_file_histories",
    multiple=True,
    help="Replace all file and prefix history shares with this list (can be specified multiple times)",
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
@click.option(
    "--no-validate",
    "no_validate",
    is_flag=True,
    default=False,
    help="Skip data type validation",
)
@pass_fulcra_api
@requires_auth
def update(
    fulcra_api: FulcraAPI,
    share_id: str,
    name: str | None,
    add_data_types: list[str],
    remove_data_types: list[str],
    set_data_types: list[str],
    add_files: list[str],
    remove_files: list[str],
    set_files: list[str],
    add_file_histories: list[str],
    remove_file_histories: list[str],
    set_file_histories: list[str],
    add_user_ids: list[str],
    remove_user_ids: list[str],
    set_user_ids: list[str],
    share_all_data: bool | None,
    start_time_value: str | None,
    no_start_time: bool,
    end_time_value: str | None,
    no_end_time: bool,
    no_validate: bool,
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
            add_files,
            remove_files,
            set_files,
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

    # Validate mutual exclusivity for file prefixes
    if set_files and (add_files or remove_files):
        raise click.UsageError(
            "--set-file cannot be used with --add-file or --remove-file"
        )

    if set_file_histories and (add_file_histories or remove_file_histories):
        raise click.UsageError(
            "--set-file-history cannot be used with --add-file-history or --remove-file-history"
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
        updated_types = current_share.get("fulcra_data_types", [])
        if set_data_types:
            updated_types = set_data_types

        if set_files:
            updated_types = [t for t in updated_types if not t.startswith("file:")] + [
                file_share_type(prefix=f, history=False) for f in set_files
            ]
        if set_file_histories:
            updated_types = [
                t for t in updated_types if not t.startswith("filehistory:")
            ] + [file_share_type(prefix=f, history=True) for f in set_file_histories]

        add_types = add_data_types or []
        if add_files:
            add_types += [file_share_type(prefix=f, history=False) for f in add_files]
        if add_file_histories:
            add_types += [
                file_share_type(prefix=f, history=True) for f in add_file_histories
            ]
        remove_types = remove_data_types or []
        if remove_files:
            remove_types += [
                file_share_type(prefix=f, history=False) for f in remove_files
            ]
        if remove_file_histories:
            remove_types += [
                file_share_type(prefix=f, history=True) for f in remove_file_histories
            ]

        for add_type in add_types:
            if add_type in updated_types:
                click.echo(f"Warning: {add_type} already in share, skipping", err=True)
            else:
                updated_types.add(add_type)

        for remove_type in remove_types:
            if remove_type in updated_types:
                click.echo(f"Warning: {remove_type} not in share, skipping", err=True)
            else:
                updated_types.remove(remove_type)

        if not no_validate:
            updated_types = valid_share_types(
                fulcra_api=fulcra_api, share_types=updated_types
            )

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
