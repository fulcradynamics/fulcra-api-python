import json
from urllib.error import HTTPError

import click

from .utils import requires_auth


@click.group(help="Data sharing management sub-commands")
def share():
    pass


@share.command("list-outgoing", short_help="List datashares you've created")
@click.pass_context
@requires_auth
def list_outgoing(ctx):
    """
    List all datashares that you have created to share your data with others.
    """
    try:
        results = ctx.obj.get_datashares()
    except HTTPError as exc:
        raise click.ClickException(exc)

    for datashare in results:
        click.echo(json.dumps(datashare))


@share.command("list-incoming", short_help="List datasets shared with you")
@click.pass_context
@requires_auth
def list_incoming(ctx):
    """
    List all datasets that others have shared with you.
    """
    try:
        results = ctx.obj.get_shared_datasets()
    except HTTPError as exc:
        raise click.ClickException(exc)

    for dataset in results:
        click.echo(json.dumps(dataset))


@share.command("create", short_help="Create a new datashare")
@click.pass_context
@requires_auth
def create(ctx):
    """
    Create a new datashare to share your data with other users.
    """
    click.echo("create command - not yet implemented")


@share.command("delete", short_help="Delete a datashare you created")
@click.argument("datashare_id")
@click.pass_context
@requires_auth
def delete(ctx, datashare_id: str):
    """
    Delete a datashare that you created.

    DATASHARE_ID: UUID of the datashare to delete
    """
    try:
        ctx.obj.delete_datashare(datashare_id)
        click.echo(f"Datashare {datashare_id} deleted successfully")
    except HTTPError as exc:
        raise click.ClickException(exc)


@share.command("leave", short_help="Leave a dataset shared with you")
@click.argument("permission_id")
@click.pass_context
@requires_auth
def leave(ctx, permission_id: str):
    """
    Leave a dataset that was shared with you (revoke your access).

    PERMISSION_ID: UUID of the dataset permission to revoke
    """
    try:
        ctx.obj.delete_dataset_permission(permission_id)
        click.echo(f"Successfully left dataset (permission {permission_id} revoked)")
    except HTTPError as exc:
        raise click.ClickException(exc)
