import os
import pathlib
from datetime import datetime, timezone
from urllib.error import HTTPError
from uuid import UUID

import click
import puremagic

from fulcra_api.core import FulcraAPI

from .utils import human_size, make_filepath, pass_fulcra_api, requires_auth


@click.group(help="File management sub-commands")
def file():
    pass


@file.command("list", short_help="List files")
@click.argument("path", type=str, default="/")
@click.option(
    "--user-id",
    type=str,
    default=None,
    help="Fulcra user ID of which files to fetch.",
)
@click.option(
    "--base-name",
    type=str,
    default=None,
    help="Filter files and folders by base name.",
)
@click.option(
    "--include-deleted",
    is_flag=True,
    default=False,
    help="Include deleted files.",
)
@pass_fulcra_api
@requires_auth
def file_list(
    fulcra_api: FulcraAPI,
    path: str,
    user_id: str | None,
    base_name: str | None,
    include_deleted: bool,
):
    """List uploaded files.

    PATH: Path to list files in [Default: /]
    """

    path = make_filepath(path)

    try:
        if include_deleted:
            state = "uploaded,deleted"
        else:
            state = "uploaded"
        results = fulcra_api.list_files(
            path, fulcra_userid=user_id, base_name=base_name, state=state
        )
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to list files: {exc}\n{error_body}")

    if results.get("folders") is not None:
        for d in results.get("folders", []):
            click.echo(f"{d}/")

    # Prefer the live version of each file
    files = {}
    for f in results.get("files", []):
        name = f.get("name")
        if name not in files:
            files[name] = f
            continue
        if f.get("state") == "uploaded":
            files[name] = f

    filtered_files = sorted(files.values(), key=lambda f: f.get("name"))
    for f in filtered_files:
        size, unit = human_size(f.get("size"))
        try:
            dt = datetime.fromisoformat(f.get("uploaded_at"))
        except TypeError:
            dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        status = (
            f" (deleted {f.get('deleted_at')})" if f.get("state") == "deleted" else ""
        )
        click.echo(
            f"{str(size) + unit:7} {dt.strftime('%Y-%m-%d %I:%M%p %Z')}  {f.get('name')}{status}"
        )


@file.command("stat", short_help="Get information about a file")
@click.argument("path", type=str)
@click.option(
    "--user-id",
    type=str,
    default=None,
    help="Fulcra user ID of which files to fetch.",
)
@click.option(
    "--include-deleted",
    is_flag=True,
    default=False,
    help="Include deleted versions of the file.",
)
@pass_fulcra_api
@requires_auth
def file_stat(
    fulcra_api: FulcraAPI, path: str, user_id: str | None, include_deleted: bool
):
    """Returns information about an uploaded file, including size, date uploaded, and all previously uploaded versions of the file.

    PATH: Full path of the file.
    """

    path = make_filepath(path)

    try:
        f = fulcra_api.resolve_filepath(
            path,
            all_versions=True,
            fulcra_userid=user_id,
            include_deleted=include_deleted,
        )
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to stat file: {exc}\n{error_body}")
    except Exception as exc:
        raise click.ClickException(exc)

    latest_version = f[0]

    click.echo(
        f"{make_filepath(latest_version['path'], latest_version['name'])} ({latest_version['size']} bytes)"
        + (
            f" (deleted {latest_version['deleted_at']})"
            if latest_version["state"] == "deleted"
            else ""
        )
    )
    click.echo(f"Uploaded: {latest_version['uploaded_at']}")
    click.echo(f"Version: {latest_version['id']}")
    click.echo(f"Previous Versions: {len(f[1:])}")
    for file_version in f[1:]:
        click.echo(
            f"- {file_version['id']} {file_version['uploaded_at']} ({file_version['size']} bytes)"
            + (
                f" (deleted {file_version['deleted_at']})"
                if file_version["state"] == "deleted"
                else ""
            )
        )


@file.command("download", short_help="Download a file")
@click.argument("remote_file", type=str)
@click.argument(
    "local_file", type=click.Path(allow_dash=True), required=False, default=None
)
@click.option(
    "--user-id",
    type=str,
    default=None,
    help="Fulcra user ID of which files to fetch.",
)
@click.option(
    "--version",
    type=str,
    default=None,
    help="File version to download (defaults to latest).",
)
@pass_fulcra_api
@requires_auth
def file_download(
    fulcra_api: FulcraAPI,
    remote_file: str,
    local_file: str | None,
    user_id: str | None,
    version: str | None,
):
    """Download a file.

    REMOTE_FILE: Full path of file to download.

    LOCAL_FILE: File or directory to save the downloaded file to. If a directory is given, the remote file's name is used.
    Use `-` to print file contents to STDOUT. [Default: REMOTE_FILE name in the current directory]

    """

    remote_file = make_filepath(remote_file)

    try:
        if version is not None:
            f = [
                fulcra_api.get_file_by_version(
                    version_id=version, fulcra_userid=user_id
                )
            ]
        else:
            f = fulcra_api.resolve_filepath(remote_file, fulcra_userid=user_id)
        resp = fulcra_api.download_file(f[0].get("id"), fulcra_userid=user_id)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to download file: {exc}\n{error_body}")
    except Exception as exc:
        raise click.ClickException(exc)

    remote_name = pathlib.PurePath(f[0].get("name")).name

    if local_file == "-":  # "-" → stdout
        dest = None
    elif local_file is None:
        dest = pathlib.Path(remote_name)
    else:
        dest = pathlib.Path(local_file)
        if dest.is_dir() or local_file.endswith(os.sep):
            dest = dest / remote_name

    if dest is None:
        click.open_file("-", mode="wb").write(resp.read())
        return

    try:
        dest.write_bytes(resp.read())
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise click.ClickException(f"Cannot write to {dest}: {exc.strerror}")

    click.echo(f"⬇️ fulcra:{remote_file} -> {dest}")


@file.command("upload", short_help="Upload a file")
@click.argument("local_file", type=click.File(mode="rb"))
@click.argument("remote_file", type=str, default="")
@pass_fulcra_api
@requires_auth
def file_upload(fulcra_api: FulcraAPI, local_file: click.File, remote_file: str):
    """Upload a file.

    LOCAL_FILE: File to upload.

    REMOTE_FILE: Full path to upload file to. [Default: LOCAL_FILE name]
    """
    if local_file.name == "<stdin>":
        raise click.ClickException("Cannot upload from stdin")

    if remote_file != "":
        path = make_filepath(remote_file)
    else:
        path = make_filepath(pathlib.PurePath(local_file.name).name)

    file_size = os.path.getsize(local_file.name)
    try:
        file_type = puremagic.from_file(local_file.name, mime=True)
    except puremagic.PureError:
        file_type = "application/octet-stream"

    try:
        new_file = fulcra_api.upload_file(local_file, file_type, file_size, path)
        full_path = make_filepath(new_file["file"]["path"], new_file["file"]["name"])
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to upload file: {exc}\n{error_body}")

    click.echo(f"⬆️ {local_file.name} -> fulcra:{full_path}")


@file.command("delete", short_help="Delete a file")
@click.argument("path", type=str)
@pass_fulcra_api
@requires_auth
def file_delete(fulcra_api: FulcraAPI, path):
    """Delete a file.

    PATH: Path of the file to delete.
    """
    path = make_filepath(path)

    try:
        f = fulcra_api.resolve_filepath(path)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to delete file: {exc}\n{error_body}")
    except Exception as exc:
        raise click.ClickException(exc)

    fulcra_api.delete_file(f[0].get("id"))

    click.echo(f"❌ fulcra:{path}")


@file.command("restore", short_help="Restore a file")
@click.argument("version_id", type=UUID)
@pass_fulcra_api
@requires_auth
def file_restore(fulcra_api: FulcraAPI, version_id):
    """Restore a previous version of a file.

    VERSION_ID: UUID of the file version you want to restore. Versions are returned via the `file stat` command.
    """

    try:
        file_version = fulcra_api.get_file_by_version(version_id)
    except HTTPError as exc:
        if exc.status == 404:
            raise click.ClickException(f"File version {version_id} not found")
        else:
            error_body = exc.read().decode("utf-8")
            raise click.ClickException(f"Failed to restore file: {exc}\n{error_body}")

    full_file_name = make_filepath(file_version["path"], file_version["name"])

    new_file = fulcra_api.restore_file(file_version["id"])

    click.echo(
        f"fulcra:{full_file_name}  {file_version['id']} ({file_version['uploaded_at']}) ➡️ {new_file['id']} ({new_file['uploaded_at']})"
    )
