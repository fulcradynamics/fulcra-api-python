import json
from datetime import datetime
from typing import Any, Dict
from urllib.error import HTTPError

import click

from fulcra_api.core import FulcraAPI

from .utils import (
    file_share_type,
    parse_iso_time,
    pass_fulcra_api,
    requires_auth,
    time_range,
    valid_share_types,
)


@click.group(help="Data sharing sub-commands")
def share():
    pass


@share.command("list-outgoing", short_help="List shares you've created")
@pass_fulcra_api
@requires_auth
def list_outgoing(fulcra_api: FulcraAPI):
    """
    List all data shares that you have created to share your data with others.
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
    List all data shares that are shared with you.

    Each entry is one grant.  Shares addressed to you individually have
    grant_type "user"; those made to a data group you participate in have
    grant_type "group" and name the group in group_id.  Holding both kinds of
    grant on one share produces one entry for each.
    """
    try:
        results = fulcra_api.get_shared_datasets()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(
            f"Failed to retrieve incoming shares: {exc}\n{error_body}"
        )

    # Skip the entry for the user's own data; it only reflects that they can
    # read everything of their own.
    for dataset in [r for r in results if r.get("grant_type") != "self"]:
        click.echo(json.dumps(dataset))


@share.command("create", short_help="Create a new data share")
@click.option(
    "--name",
    "datashare_name",
    default=None,
    help="Name for this share, defaults to authenticated user's name or email",
)
@click.option(
    "--data-type",
    "data_types",
    multiple=True,
    help="Data type ID to share. Can be specified multiple times.",
)
@click.option(
    "--file",
    "files",
    multiple=True,
    help="File or directory to share the latest version of.",
)
@click.option(
    "--user-id",
    "user_ids",
    multiple=True,
    help="User ID to share with",
)
@click.option(
    "--group-id",
    "group_ids",
    multiple=True,
    help="Group to share with, granting access to everyone currently "
    "participating in it (can be specified multiple times)",
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
    datashare_name: str | None,
    data_types: list[str],
    files: list[str],
    user_ids: list[str],
    group_ids: list[str],
    start_time: str | None,
    end_time: str | None,
    share_all: bool,
    no_validate: bool,
):
    """
    Create a new share to share a specific subset of your data with other users.

    Recipients can be individual users (--user-id), data groups
    (--group-id), or both; at least one is required.  Sharing with a group
    grants read-only access to everyone currently participating in it: members who join
    later gain access, and members who leave lose it.  You do not have to own a
    group to share your data into it.

    Examples:

    \b
    Share specific data types with a user:
    fulcra share create --name "Research Study" --data-type HeartRate --data-type StepCount --user-id <USER-UUID>

    \b
    Share all data types:
    fulcra share create --name "Full Access" --share-all --user-id <USER-UUID>

    \b
    Share step counts with everyone in a group:
    fulcra share create --name "Step Challenge" --data-type StepCount --group-id <GROUP-UUID>

    \b
    Share all files in the /collaboration/context/ directory:
    fulcra share create --name "Context files" --file /collaboration/context/ --user-id <USER-UUID>
    """
    if not user_ids and not group_ids:
        raise click.UsageError("Must specify at least one --user-id or --group-id")

    # Validate data types against catalog
    share_types = list(data_types)
    for file in files:
        share_types.append(file_share_type(prefix=file))

    if not no_validate:
        share_types = valid_share_types(fulcra_api=fulcra_api, share_types=share_types)

    # Parse time arguments if provided
    parsed_start_time = (
        parse_iso_time(start_time, "start time") if start_time else None
    )
    parsed_end_time = parse_iso_time(end_time, "end time") if end_time else None

    if datashare_name is None:
        datashare_name = (
            fulcra_api.get_authenticated_user_name()
            or fulcra_api.get_authenticated_user_email()
            or fulcra_api.get_fulcra_userid()
        )

    # Create the datashare
    try:
        result = fulcra_api.create_datashare(
            datashare_name=datashare_name,
            fulcra_data_types=share_types,
            allowed_user_ids=sorted(user_ids),
            allowed_group_ids=sorted(group_ids),
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
@click.argument("grant_id")
@pass_fulcra_api
@requires_auth
def leave(fulcra_api: FulcraAPI, grant_id: str):
    """
    Give up your access to a share that was shared with you.

    This works for a grant addressed to you individually (grant_type "user").
    A share that reaches you through a data group confers access on everyone
    in that group, so only the person who created it can remove that grant;
    use 'fulcra group leave' to give up your own access instead.

    GRANT_ID: the grant_id of the grant, from 'fulcra share list-incoming'
    """
    try:
        fulcra_api.delete_dataset_permission(grant_id)
        click.echo(f"Successfully left share {grant_id}")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        hint = ""
        if exc.code == 404:
            hint = (
                "\nIf this share reaches you through a data group, leave the "
                "group instead: fulcra group leave <GROUP-UUID>"
            )
        raise click.ClickException(
            f"Failed to leave share: {exc}\n{error_body}{hint}"
        )


@share.command("update", short_help="Update an existing share")
@click.argument("share_id")
@click.option("--name", type=str, help="Update the share name")
@click.option(
    "--add-data-type",
    "add_data_types",
    multiple=True,
    help="Add a data type to the share. Can be specified multiple times",
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
    help="Add a file or directory to share the latest version of. Can be specified multiple times.",
)
@click.option(
    "--remove-file",
    "remove_files",
    multiple=True,
    help="Remove a file or directory sharing the latest version. Can be specified multiple times.",
)
@click.option(
    "--set-file",
    "set_files",
    multiple=True,
    help="Replace all files or directories sharing the latest version with this list. Can be specified multiple times.",
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
    "--add-group-id",
    "add_group_ids",
    multiple=True,
    help="Add a group to share with (can be specified multiple times)",
)
@click.option(
    "--remove-group-id",
    "remove_group_ids",
    multiple=True,
    help="Remove a group from the share (can be specified multiple times)",
)
@click.option(
    "--set-group-id",
    "set_group_ids",
    multiple=True,
    help="Replace all groups with this list (can be specified multiple times)",
)
@click.option(
    "--no-group-id",
    "no_group_ids",
    is_flag=True,
    default=False,
    help="Stop sharing with every group",
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
@click.option(
    "--clear",
    "clear",
    is_flag=True,
    default=False,
    help="Remove all shared data and files from the share, then add any specified by other options",
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
    add_user_ids: list[str],
    remove_user_ids: list[str],
    set_user_ids: list[str],
    add_group_ids: list[str],
    remove_group_ids: list[str],
    set_group_ids: list[str],
    no_group_ids: bool,
    share_all_data: bool | None,
    start_time_value: str | None,
    no_start_time: bool,
    end_time_value: str | None,
    no_end_time: bool,
    no_validate: bool,
    clear: bool,
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
    Share with everyone in a group:
    fulcra share update <SHARE-UUID> --add-group-id <GROUP-UUID>

    \b
    Stop sharing with every group, leaving individual recipients alone:
    fulcra share update <SHARE-UUID> --no-group-id

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
            add_group_ids,
            remove_group_ids,
            set_group_ids,
            no_group_ids,
            share_all_data is not None,
            start_time_value,
            no_start_time,
            end_time_value,
            no_end_time,
            clear,
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

    # Validate mutual exclusivity for user IDs
    if set_user_ids and (add_user_ids or remove_user_ids):
        raise click.UsageError(
            "--set-user-id cannot be used with --add-user-id or --remove-user-id"
        )

    # Validate mutual exclusivity for group IDs
    if set_group_ids and (add_group_ids or remove_group_ids):
        raise click.UsageError(
            "--set-group-id cannot be used with --add-group-id or --remove-group-id"
        )
    if no_group_ids and (set_group_ids or add_group_ids or remove_group_ids):
        raise click.UsageError(
            "--no-group-id cannot be used with the other --*-group-id options"
        )

    # Validate mutual exclusivity for start time
    if start_time_value and no_start_time:
        raise click.UsageError("--start-time cannot be used with --no-start-time")

    # Validate mutual exclusivity for end time
    if end_time_value and no_end_time:
        raise click.UsageError("--end-time cannot be used with --no-end-time")

    # The server changes only the fields the request carries, so send just the
    # ones that were asked for.  The current share is fetched only when an
    # option modifies an existing list rather than replacing it.
    update_kwargs: Dict[str, Any] = {"datashare_id": share_id}
    current_share: Dict[str, Any] | None = None

    def load_current_share() -> Dict[str, Any]:
        nonlocal current_share
        if current_share is None:
            try:
                current_share = fulcra_api.get_datashare(share_id)
            except HTTPError as exc:
                if exc.code == 404:
                    raise click.ClickException(f"Share {share_id} not found")
                raise
        return current_share

    try:
        if name:
            update_kwargs["datashare_name"] = name

        add_types = list(add_data_types) + [
            file_share_type(prefix=f) for f in add_files
        ]
        remove_types = list(remove_data_types) + [
            file_share_type(prefix=f) for f in remove_files
        ]

        if clear or set_data_types or set_files or add_types or remove_types:
            if clear:
                updated_types = []
            elif set_data_types:
                updated_types = list(set_data_types)
            else:
                updated_types = list(load_current_share().get("fulcra_data_types", []))

            if set_files:
                updated_types = [
                    t for t in updated_types if not t.startswith("file:")
                ] + [file_share_type(prefix=f) for f in set_files]

            for add_type in add_types:
                if add_type in updated_types:
                    click.echo(
                        f"Warning: {add_type} already in share, skipping", err=True
                    )
                else:
                    updated_types.append(add_type)

            for remove_type in remove_types:
                if remove_type not in updated_types:
                    click.echo(
                        f"Warning: {remove_type} not in share, skipping", err=True
                    )
                else:
                    updated_types = [t for t in updated_types if t != remove_type]

            if not no_validate:
                updated_types = valid_share_types(
                    fulcra_api=fulcra_api, share_types=updated_types
                )

            update_kwargs["fulcra_data_types"] = updated_types

        # Handle user IDs
        if set_user_ids:
            update_kwargs["allowed_user_ids"] = sorted(set_user_ids)
        elif add_user_ids or remove_user_ids:
            current_user_ids = {
                p["allowed_fulcra_userid"]
                for p in load_current_share().get("permissions", [])
            }

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

        # Handle group IDs.  Groups and individual recipients are independent
        # lists on the server, so leaving this out keeps a share's groups as
        # they are.
        if no_group_ids:
            update_kwargs["allowed_group_ids"] = []
        elif set_group_ids:
            update_kwargs["allowed_group_ids"] = sorted(set_group_ids)
        elif add_group_ids or remove_group_ids:
            current_group_ids = {
                p["allowed_group_id"]
                for p in load_current_share().get("group_permissions", [])
            }

            for gid in add_group_ids:
                if gid in current_group_ids:
                    click.echo(f"Warning: {gid} already in share, skipping", err=True)
                else:
                    current_group_ids.add(gid)

            for gid in remove_group_ids:
                if gid not in current_group_ids:
                    click.echo(f"Warning: {gid} not in share, skipping", err=True)
                else:
                    current_group_ids.remove(gid)

            update_kwargs["allowed_group_ids"] = sorted(current_group_ids)

        # Handle share_all_data flag
        if clear:
            update_kwargs["share_all_data"] = False
        if share_all_data is not None:
            update_kwargs["share_all_data"] = share_all_data

        # Handle start time
        if start_time_value:
            update_kwargs["time_start"] = parse_iso_time(start_time_value, "start time")
        elif no_start_time:
            update_kwargs["time_start"] = None

        # Handle end time
        if end_time_value:
            update_kwargs["time_end"] = parse_iso_time(end_time_value, "end time")
        elif no_end_time:
            update_kwargs["time_end"] = None

        # Update the share
        result = fulcra_api.update_datashare(**update_kwargs)
        click.echo(json.dumps(result))

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to update share: {exc}\n{error_body}")


@share.command(
    "shared-data-types",
    short_help="Summarize what a user shares with you over a time range",
)
@click.argument("user_id")
@time_range
@pass_fulcra_api
@requires_auth
def shared_data_types(
    fulcra_api: FulcraAPI, user_id: str, start_time: datetime, end_time: datetime
):
    """Summarize the data types USER_ID shares with you across TIME_RANGE.

    Use this before querying someone else's data, instead of discovering the
    limits of your access by being denied.

    USER_ID: Fulcra user ID of the person sharing with you

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single
    interval argument relative to the current time ("1 week", "2 days", "3h", etc.)

    A share counts only if it fully covers the requested range, and the end of
    the range is compared strictly -- so ask about a window strictly inside a
    share, not its exact declared range.  Access granted through a data group
    counts the same as a direct share.

    When all_data_types is true everything is shared and fulcra_data_types is
    empty, so check that flag before reading the list.  Having nothing shared
    with you is a normal result, not an error.

    Examples:

    \b
    What can this user share with me over the past week?
    fulcra share shared-data-types <USER-UUID> "1 week"
    """
    try:
        resp = fulcra_api.list_shared_data_types(user_id, start_time, end_time)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(
            f"Failed to retrieve shared data types: {exc}\n{error_body}"
        )

    click.echo(json.dumps(resp))
