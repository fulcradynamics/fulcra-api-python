import json
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
@click.pass_context
@requires_auth
def create(ctx):
    """
    Create a new share to share your data with other users.
    """
    click.echo("create command - not yet implemented")


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
