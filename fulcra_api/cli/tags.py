import json
from typing import Optional, Tuple
from urllib.error import HTTPError

import click

from fulcra_api.core import FulcraAPI

from .utils import pass_fulcra_api, requires_auth


@click.group(help="Tag management sub-commands")
def tag():
    pass


@tag.command("list", short_help="Return a list of user-defined tags")
@click.option("-n", "--name", type=str, help="Filter results by partial name.")
@click.option("--tag-name", type=str, help="Filter results by full tag name.")
@click.option("--tag-id", type=str, help="Filter results by tag ID.")
@pass_fulcra_api
@requires_auth
def tag_list(
    fulcra_api: FulcraAPI,
    name: Optional[str],
    tag_name: Optional[str],
    tag_id: Optional[str],
):
    """
    Return a list of user-defined tags that can be used when creating and recording custom data types.
    """

    try:
        response = fulcra_api.tags()

        if name:
            response = [
                t for t in response if name.lower() in t.get("name", "").lower()
            ]

        if tag_name is not None:
            response = [
                t for t in response if tag_name.lower() == t.get("name", "").lower()
            ]

        if tag_id is not None:
            response = [
                t for t in response if tag_id.lower() == t.get("id", "").lower()
            ]

        click.echo(json.dumps(response))
    except HTTPError as exc:
        raise click.ClickException(f"Failed to get tags: {exc}")


@tag.command("get", short_help="Get a user-defined tag")
@click.argument("name_or_id", type=str)
@pass_fulcra_api
@requires_auth
def get_tag(fulcra_api: FulcraAPI, name_or_id: str):
    """Get a user-defined tag by name or ID.

    NAME_OR_ID: Tag name or ID
    """
    from uuid import UUID

    tag_name = name_or_id
    tag_id = None
    try:
        tag_id = str(UUID(name_or_id))
    except ValueError:
        pass

    try:
        if tag_id:
            resp = fulcra_api.get_tag_by_id(tag_id=tag_id)
            click.echo(json.dumps(resp))
        else:
            resp = fulcra_api.get_tag_by_name(name=tag_name)
            click.echo(json.dumps(resp))

    except HTTPError as exc:
        if exc.status == 404:
            raise click.ClickException(f"No tag found: {tag_name or id}")
        else:
            raise click.ClickException(f"Failed to get tag: {exc}")


@tag.command("create", short_help="Create user-defined tags")
@click.argument("names", nargs=-1)
@pass_fulcra_api
@requires_auth
def tag_create(fulcra_api: FulcraAPI, names: Tuple[str, ...]):
    """
    Create case-insensitive user-defined tags by name that can be used when creating and recording custom data types.
    """

    created_tags = fulcra_api.create_tags(list(names))
    click.echo(json.dumps(created_tags))


@tag.command("delete", short_help="Delete user-defined tag")
@click.argument("tag_id")
@pass_fulcra_api
@requires_auth
def tag_delete(fulcra_api: FulcraAPI, tag_id: str):
    """
    Delete a user-defined tag by tag ID.
    """

    try:
        fulcra_api.delete_tag(tag_id)
    except HTTPError as exc:
        raise click.ClickException(f"Failed to delete tag {tag_id}: {exc}")

    click.echo(f"Tag deleted: {tag_id}")
