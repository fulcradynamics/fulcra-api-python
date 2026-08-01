import json
from urllib.error import HTTPError

import click

from fulcra_api.core import FulcraAPI

from .utils import parse_iso_time, parse_json_object, pass_fulcra_api, requires_auth


@click.group(help="Data group management sub-commands")
def group():
    pass


@group.command("list", short_help="List public groups, or groups you've joined")
@click.option(
    "--joined",
    is_flag=True,
    default=False,
    help="List only groups you have joined, including participant ID",
)
@pass_fulcra_api
@requires_auth
def list_groups(fulcra_api: FulcraAPI, joined: bool):
    """
    List data groups.

    By default, lists all public groups.  With --joined, lists only the
    groups you have joined; these include your participant ID and join time.
    """
    try:
        results = fulcra_api.get_groups(subscribed_only=joined)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to retrieve groups: {exc}\n{error_body}")

    for grp in results:
        click.echo(json.dumps(grp))


@group.command("show", short_help="Show a group's description")
@click.argument("group_id")
@pass_fulcra_api
@requires_auth
def show(fulcra_api: FulcraAPI, group_id: str):
    """
    Show the description of a data group.

    GROUP_ID: UUID of the group
    """
    try:
        result = fulcra_api.get_group(group_id)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to retrieve group: {exc}\n{error_body}")

    click.echo(json.dumps(result))


@group.command("create", short_help="Create a new group")
@click.option("--title", required=True, help="Title")
@click.option(
    "--public/--private",
    "is_public",
    default=False,
    help="Whether the group is publicly listed (default: private)",
)
@click.option(
    "--responsible-entity",
    required=True,
    help="The person or organization responsible for the group",
)
@click.option("--description", required=True, help="Description of the group")
@click.option(
    "--data-type",
    "data_types",
    multiple=True,
    required=True,
    help="Data type ID that participants will share (can be specified multiple times)",
)
@click.option("--url", "group_url", required=True, help="URL of the group's webapp")
@click.option("--start-time", type=str, help="Optional start time (ISO8601 format)")
@click.option("--end-time", type=str, help="Optional end time (ISO8601 format)")
@click.option("--detail-markdown", help="Markdown shown on the group's detail view")
@click.option("--agreement-markdown", help="Markdown shown when a user joins")
@click.option("--withdraw-markdown", help="Markdown shown when a user leaves")
@click.option("--header-image-url", help="URL of the group's header image")
@click.option("--preview-image-url", help="URL of the group's preview image")
@click.option("--friendly-id", help="Human-friendly identifier for the group")
@pass_fulcra_api
@requires_auth
def create(
    fulcra_api: FulcraAPI,
    title,
    is_public,
    responsible_entity,
    description,
    data_types,
    group_url,
    start_time,
    end_time,
    detail_markdown,
    agreement_markdown,
    withdraw_markdown,
    header_image_url,
    preview_image_url,
    friendly_id,
):
    """
    Create a new data group that other Fulcra users can join.

    Participants who join share read-only access to the selected data types
    for the selected time range until they leave the group.  Most group
    parameters are immutable after creation; see 'fulcra group update' for
    the fields that can be changed later.

    Examples:

    \b
    Create a public group:
    fulcra group create --title "Step Challenge" --public \\
        --responsible-entity "Fulcra Dynamics" \\
        --description "A month-long step challenge." \\
        --data-type StepCount --url https://example.com/challenge
    """
    # Validate data types against catalog
    try:
        catalog = fulcra_api.v1_catalog()
        valid_data_type_ids = {item["id"] for item in catalog}

        # "apple_workouts" is the resource name the group data routes check for
        # workout access, but it is not a catalog ID.
        temporary_allowed_types = {"apple_workouts"}

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

    parsed_start_time = (
        parse_iso_time(start_time, "start time") if start_time else None
    )
    parsed_end_time = parse_iso_time(end_time, "end time") if end_time else None

    try:
        result = fulcra_api.create_group(
            title=title,
            is_public=is_public,
            responsible_entity=responsible_entity,
            description=description,
            fulcra_data_types=sorted(data_types),
            group_url=group_url,
            time_start=parsed_start_time,
            time_end=parsed_end_time,
            detail_markdown=detail_markdown,
            agreement_markdown=agreement_markdown,
            withdraw_markdown=withdraw_markdown,
            header_image_url=header_image_url,
            preview_image_url=preview_image_url,
            friendly_id=friendly_id,
        )
        click.echo(json.dumps(result))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to create group: {exc}\n{error_body}")


@group.command("update", short_help="Update a group you own")
@click.argument("group_id")
@click.option("--description", help="New description for the group")
@click.option("--header-image-url", help="New URL of the group's header image")
@click.option(
    "--no-header-image-url",
    is_flag=True,
    default=False,
    help="Clear the group's header image",
)
@click.option("--preview-image-url", help="New URL of the group's preview image")
@click.option(
    "--no-preview-image-url",
    is_flag=True,
    default=False,
    help="Clear the group's preview image",
)
@click.option(
    "--view-description", help="New description of the group's view (JSON object)"
)
@click.option(
    "--no-view-description",
    is_flag=True,
    default=False,
    help="Clear the group's view description",
)
@pass_fulcra_api
@requires_auth
def update(
    fulcra_api: FulcraAPI,
    group_id: str,
    description,
    header_image_url,
    no_header_image_url,
    preview_image_url,
    no_preview_image_url,
    view_description,
    no_view_description,
):
    """
    Update the editable fields of a group that you own.

    Only these fields can be changed after creation; all other group
    parameters are immutable.  Fields not specified are left unchanged.

    GROUP_ID: UUID of the group to update
    """
    if header_image_url and no_header_image_url:
        raise click.UsageError(
            "--header-image-url cannot be used with --no-header-image-url"
        )
    if preview_image_url and no_preview_image_url:
        raise click.UsageError(
            "--preview-image-url cannot be used with --no-preview-image-url"
        )
    if view_description and no_view_description:
        raise click.UsageError(
            "--view-description cannot be used with --no-view-description"
        )

    kwargs = {}
    if description:
        kwargs["description"] = description
    if header_image_url:
        kwargs["header_image_url"] = header_image_url
    elif no_header_image_url:
        kwargs["header_image_url"] = None
    if preview_image_url:
        kwargs["preview_image_url"] = preview_image_url
    elif no_preview_image_url:
        kwargs["preview_image_url"] = None
    if view_description:
        kwargs["view_description"] = parse_json_object(
            view_description, "--view-description"
        )
    elif no_view_description:
        kwargs["view_description"] = None

    if not kwargs:
        raise click.UsageError("Must specify at least one option to update")

    try:
        result = fulcra_api.update_group(group_id=group_id, **kwargs)
        click.echo(json.dumps(result))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to update group: {exc}\n{error_body}")


@group.command("delete", short_help="Delete a group you own")
@click.argument("group_id")
@pass_fulcra_api
@requires_auth
def delete(fulcra_api: FulcraAPI, group_id: str):
    """
    Delete a group that you own.

    GROUP_ID: UUID of the group to delete
    """
    try:
        fulcra_api.delete_group(group_id)
        click.echo(f"Group {group_id} deleted successfully")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to delete group: {exc}\n{error_body}")


@group.command("join", short_help="Join a group")
@click.argument("group_id")
@pass_fulcra_api
@requires_auth
def join(fulcra_api: FulcraAPI, group_id: str):
    """
    Join a data group as a participant.

    Joining shares read-only access to your data (limited to the group's
    data types and time range) with the group's owner until you leave.

    GROUP_ID: UUID of the group to join
    """
    try:
        result = fulcra_api.join_group(group_id)
        click.echo(json.dumps(result))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to join group: {exc}\n{error_body}")


@group.command("leave", short_help="Leave a group")
@click.argument("group_id")
@pass_fulcra_api
@requires_auth
def leave(fulcra_api: FulcraAPI, group_id: str):
    """
    Leave a data group, revoking the owner's access to your data.

    GROUP_ID: UUID of the group to leave
    """
    try:
        fulcra_api.leave_group(group_id)
        click.echo(f"Successfully left group {group_id}")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to leave group: {exc}\n{error_body}")


@group.command("participants", short_help="List participants of a group you own")
@click.argument("group_id")
@pass_fulcra_api
@requires_auth
def participants(fulcra_api: FulcraAPI, group_id: str):
    """
    List the participant IDs of a group that you own.

    Participant IDs are anonymized UUIDs that are only meaningful within
    this group; they do not reveal participants' Fulcra UserIDs.

    GROUP_ID: UUID of the group
    """
    try:
        results = fulcra_api.get_group_participants(group_id)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(
            f"Failed to retrieve participants: {exc}\n{error_body}"
        )

    for participant_id in results:
        click.echo(participant_id)


@group.command("get-metadata", short_help="Get a participant's metadata")
@click.argument("group_id")
@click.argument("participant_id")
@pass_fulcra_api
@requires_auth
def get_metadata(fulcra_api: FulcraAPI, group_id: str, participant_id: str):
    """
    Get the metadata object for a participant in a group you own.

    GROUP_ID: UUID of the group

    PARTICIPANT_ID: Participant ID within the group
    """
    try:
        result = fulcra_api.get_group_participant_metadata(group_id, participant_id)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to retrieve metadata: {exc}\n{error_body}")

    click.echo(json.dumps(result))


@group.command("set-metadata", short_help="Replace a participant's metadata")
@click.argument("group_id")
@click.argument("participant_id")
@click.argument("metadata")
@pass_fulcra_api
@requires_auth
def set_metadata(
    fulcra_api: FulcraAPI, group_id: str, participant_id: str, metadata: str
):
    """
    Replace the entire metadata object for a participant in a group you own.

    To modify individual values instead, use 'fulcra group update-metadata'.

    GROUP_ID: UUID of the group

    PARTICIPANT_ID: Participant ID within the group

    METADATA: The new metadata object, as JSON

    Examples:

    \b
    fulcra group set-metadata <GROUP-UUID> <PARTICIPANT-UUID> '{"nickname": "speedy"}'
    """
    parsed_metadata = parse_json_object(metadata, "METADATA")

    try:
        fulcra_api.set_group_participant_metadata(
            group_id, participant_id, parsed_metadata
        )
        click.echo(f"Metadata set for participant {participant_id}")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to set metadata: {exc}\n{error_body}")


@group.command("update-metadata", short_help="Update values on a participant's metadata")
@click.argument("group_id")
@click.argument("participant_id")
@click.argument("values")
@pass_fulcra_api
@requires_auth
def update_metadata(
    fulcra_api: FulcraAPI, group_id: str, participant_id: str, values: str
):
    """
    Update some values on a participant's metadata in a group you own.

    The given values are merged into the participant's existing metadata;
    other values are left unchanged.  To replace the entire object, use
    'fulcra group set-metadata'.

    GROUP_ID: UUID of the group

    PARTICIPANT_ID: Participant ID within the group

    VALUES: The metadata values to set, as JSON

    Examples:

    \b
    fulcra group update-metadata <GROUP-UUID> <PARTICIPANT-UUID> '{"score": 42}'
    """
    parsed_values = parse_json_object(values, "VALUES")

    try:
        fulcra_api.update_group_participant_metadata(
            group_id, participant_id, parsed_values
        )
        click.echo(f"Metadata updated for participant {participant_id}")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to update metadata: {exc}\n{error_body}")


@group.command("jwks", short_help="Get the group public keys (JWKS)")
@pass_fulcra_api
@requires_auth
def jwks(fulcra_api: FulcraAPI):
    """
    Get the group public keys as a JWKS.

    Group webapps can use these keys to validate the participant JWTs that
    Context sends when authenticating requests.
    """
    try:
        result = fulcra_api.get_group_jwks()
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to retrieve JWKS: {exc}\n{error_body}")

    click.echo(json.dumps(result))
