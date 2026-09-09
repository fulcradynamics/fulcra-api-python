import json
import os
import pathlib
from datetime import datetime, timezone
from functools import wraps
from urllib.error import HTTPError

import click
import dateparser

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials

# Create a pass decorator for FulcraAPI to enable type hints in subcommands
pass_fulcra_api = click.make_pass_decorator(FulcraAPI)

CONFIG_PATH = pathlib.Path.home() / ".config" / "fulcra"
CREDS_FILE = pathlib.Path(CONFIG_PATH / "credentials.json")


def ensure_config_directory():
    try:
        CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        pass


def load_creds() -> FulcraCredentials | None:
    if CREDS_FILE.is_file():
        with CREDS_FILE.open(mode="r") as f:
            creds = FulcraCredentials.from_json(f.read())
        return creds
    return None


def save_creds(creds: FulcraCredentials):
    with CREDS_FILE.open(mode="w+") as f:
        f.write(creds.to_json())


def requires_auth(f):
    @wraps(f)
    def wrapper(fulcra_api, *args, **kwargs):
        if fulcra_api.fulcra_credentials is None:
            raise click.ClickException(
                f"No credentials found, please run `fulcra auth login`"
            )
        return f(fulcra_api, *args, **kwargs)

    return wrapper


def parse_iso_time(value: str, name: str) -> datetime:
    """
    Parse a user-supplied ISO8601 time string, raising a friendly error.

    The timestamp must include a timezone offset; these values define
    access boundaries, so we refuse to guess what a naive time means.

    Params:
        value: The raw string to parse
        name: What the value is, for the error message (e.g. "start time")
    """
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise click.ClickException(
            f"Invalid {name} format: {value}. Use ISO8601 format."
        )
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise click.ClickException(
            f"The {name} must include a timezone offset "
            f"(e.g. {value}Z or {value}-07:00)."
        )
    return dt


def parse_json_object(value: str, name: str) -> dict:
    """
    Parse a user-supplied JSON object string, raising a friendly error.

    Params:
        value: The raw string to parse
        name: What the value is, for the error message (e.g. "--annotations")
    """
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON for {name}: {exc}")
    if not isinstance(parsed, dict):
        raise click.ClickException(f"{name} must be a JSON object")
    return parsed


def group_participant_options(f):
    """
    Decorator adding --group-id/--participant-id options to a data command,
    for querying data shared by a participant of a group the user owns.
    """
    f = click.option(
        "--participant-id",
        type=str,
        default=None,
        help="Participant ID within the group given by --group-id.",
    )(f)
    f = click.option(
        "--group-id",
        type=str,
        default=None,
        help="Query data shared by a participant of a group you own "
        "(requires --participant-id).",
    )(f)
    return f


def resolve_data_source(fulcra_api: FulcraAPI, group_id, participant_id):
    """
    Return the object to run a data query against: the client itself, or a
    group participant accessor when --group-id/--participant-id were given.
    """
    if (group_id is None) != (participant_id is None):
        raise click.UsageError(
            "--group-id and --participant-id must be used together"
        )
    if group_id is not None:
        return fulcra_api.group_participant(group_id, participant_id)
    return fulcra_api


def resolve_data_type(
    *,
    allow_multiple: bool = False,
    user_id_param: str | None = None,
    api_version_param: str | None = None,
    default_to_authenticated: bool = False,
    recordable_only: bool = False,
):
    """
    Build a Click argument callback that resolves a data type string to its
    catalog entry (or entries) via FulcraAPI.resolve_data_type.

    The resolved value replaces the raw string passed to the command, so command
    bodies receive a catalog dict (or a list of dicts when allow_multiple=True)
    instead of a plain string.

    Params:
        allow_multiple: Return every matching API version instead of raising when
            the type resolves to more than one entry. The command receives a list.
        user_id_param: Name of a sibling parameter holding a --user-id value. That
            parameter must be declared with is_eager=True so it is parsed before
            this callback runs.
        api_version_param: Name of a sibling parameter holding an --api-version
            value. Must also be declared with is_eager=True.
        default_to_authenticated: When no user ID is available, scope resolution to
            the authenticated user (used by commands that only operate on the
            caller's own types).
        recordable_only: Ignore matches that aren't valid write targets when
            disambiguating -- both non-recordable types and v0 types (a legacy
            read-only API). Used by write commands like `record`. Raises if the
            type resolves only to non-writable entries.
    """

    def callback(ctx: click.Context, param: click.Parameter, value):
        if value is None:
            return None

        fulcra_api = ctx.find_object(FulcraAPI)
        if fulcra_api is None:
            raise RuntimeError(
                "Invoked resolve_data_type callback without a FulcraAPI "
                "context object; the parent command group must set ctx.obj."
            )

        # This callback runs during parsing, before @requires_auth on the command
        # body, so surface the same friendly error here.
        if fulcra_api.fulcra_credentials is None:
            raise click.ClickException(
                "No credentials found, please run `fulcra auth login`"
            )

        user_id = ctx.params.get(user_id_param) if user_id_param else None
        if user_id is None and default_to_authenticated:
            user_id = fulcra_api.get_fulcra_userid()
        api_version = ctx.params.get(api_version_param) if api_version_param else None

        try:
            resolved = fulcra_api.resolve_data_type(
                value, api_version=api_version, fulcra_userid=user_id
            )
        except (ValueError, HTTPError) as exc:
            raise click.BadParameter(str(exc), ctx=ctx, param=param)

        # Write commands can only target recordable types, so read-only matches
        # are noise when disambiguating. v0 is a legacy read-only API and is never
        # a valid write target regardless of its recordable flag (most v0 types
        # inherit the default recordable=True), matching `catalog --recordable-only`.
        if recordable_only:
            writable = [
                dt
                for dt in resolved
                if dt.get("recordable", False) and dt.get("api_version") != "v0"
            ]
            if not writable:
                raise click.BadParameter(
                    f"'{value}' is not recordable; run "
                    "`fulcra catalog --recordable-only` for recordable types",
                    ctx=ctx,
                    param=param,
                )
            resolved = writable

        if not allow_multiple and len(resolved) > 1:
            versions = ", ".join(sorted(dt["api_version"] for dt in resolved))
            raise click.BadParameter(
                f"'{value}' matches multiple API versions ({versions}); "
                "specify --api-version",
                ctx=ctx,
                param=param,
            )

        return resolved if allow_multiple else resolved[0]

    return callback


def human_size(n: int) -> tuple[int, str]:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    for unit in units:
        if n < 1024:
            return n, unit
        n //= 1024
    return n, "EiB"


def make_filepath(path: str, filename: str = "") -> str:
    """Build a remote Fulcra file-store path.

    Remote paths are API paths, not local filesystem paths, so they are always
    POSIX-style regardless of the platform the CLI runs on.
    """
    filepath = pathlib.PurePosixPath("/", path, filename)
    return str(filepath)


def tolerate_unencodable_output(*streams) -> None:
    """Make text streams replace characters they can't encode instead of raising.

    The CLI decorates some messages with emoji.  On a Windows console whose
    output is redirected, stdout defaults to a legacy code page such as cp1252,
    and writing an emoji raises UnicodeEncodeError -- after the command's real
    work has already succeeded.  Swapping the error handler to "replace" turns
    those characters into "?" on such streams and is a no-op on UTF-8 ones.
    """
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass


def parse_time(ctx: click.Context, param: click.Parameter, value: str) -> datetime:
    """callback to parse a time string through dateparser and return datetime"""
    dt = dateparser.parse(
        value,
        settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True},
    )
    if dt is None:
        raise click.UsageError("Invalid time format")
    return dt


def related_cli_commands(dt: dict) -> list[str]:
    """Return a list of related CLI subcommands for a data type"""
    cmd = []
    if dt.get("api_version") == "v0":
        if dt.get("class") == "metric":
            cmd = ["metric-time-series", "get-records"]
        elif dt.get("class") == "location":
            cmd = [
                "location-at-time",
                "location-time-series",
                "google-location-updates",
                "apple-location-updates",
                "apple-location-visits",
            ]
    elif dt.get("api_version") == "v1alpha1":
        if dt.get("class") == "metric":
            cmd = ["get-records"]
        elif dt.get("class") == "event":
            cmd = ["get-records"]
    return cmd


def time_range(func):
    """
    Decorator to add flexible time domain arguments for a command.

    Accepts either:
        - A single RANGE argument that selects a range relative to the current time
        - START_TIME and END_TIME arguments that select a specific time range
    """

    @click.argument("time_range", nargs=-1, required=True)
    @wraps(func)
    def wrapper(time_range, *args, **kwargs):
        if len(time_range) == 1:
            interval = dateparser.parse(
                time_range[0],
                settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True},
            )
            if interval is None:
                raise click.UsageError("Invalid date range")
            end_time = datetime.now(timezone.utc)
            start_time = interval
        elif len(time_range) == 2:
            try:
                start_time = datetime.fromisoformat(time_range[0])
                if (
                    start_time.tzinfo is None
                    or start_time.tzinfo.utcoffset(start_time) is None
                ):
                    start_time = start_time.astimezone().astimezone(timezone.utc)
                end_time = datetime.fromisoformat(time_range[1])
                if (
                    end_time.tzinfo is None
                    or end_time.tzinfo.utcoffset(end_time) is None
                ):
                    end_time = end_time.astimezone().astimezone(timezone.utc)
            except ValueError as e:
                raise click.UsageError(f"Invalid datetime format: {e}")
        else:
            raise click.UsageError("Expected either 1 or 2 values for TIME_RANGE")

        return func(*args, start_time=start_time, end_time=end_time, **kwargs)

    return wrapper


def build_v1_promql(
    data_type_id: str, start_time: datetime, end_time: datetime
) -> str:
    """
    Build a PromQL query selecting a data type's records over [start, end).

    Encodes the window as a range vector anchored at the end time
    (`Type[<duration>s] @ <end_unix_ts>`), which the v1 records endpoint
    evaluates as records overlapping [start_time, end_time).
    """
    duration = max(1, int((end_time - start_time).total_seconds()))
    return f"{data_type_id}[{duration}s] @ {int(end_time.timestamp())}"


def file_share_type(prefix: str, history: bool = False) -> str:
    """
    Return the share type string for a file or file history path or  prefix.

    Args:
        prefix: The file or file history path or prefix.
        history: Whether to share the file history instead of only the live version (default: False).

    Returns:
        The share type string.
    """

    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    if history:
        return f"filehistory:{prefix}"
    return f"file:{prefix}"


def valid_share_types(fulcra_api: FulcraAPI, share_types: list[str]) -> list[str]:
    """
    Validate a list of data type and/or file shares.

    Args:
        fulcra_api: The FulcraAPI instance.
        share_types: A list of share types to validate.

    Raises:
        click.ClickException: If any share type is invalid.

    Returns:
        A sorted de-duplicated list of valid share types.
    """

    share_types = sorted(set(share_types))
    try:
        catalog = fulcra_api.v1_catalog(fulcra_userid=fulcra_api.get_fulcra_userid())
        valid_data_type_ids = {item["id"] for item in catalog}

        # TEMPORARY: Allow "calendars" and "calendar_events" even though they're not
        # in the v1 catalog yet. Remove this special case once they're added to the catalog.
        temporary_allowed_types = {"calendars", "calendar_events"}

        invalid_types = []
        for share_type in share_types:
            if share_type in valid_data_type_ids:
                continue
            if share_type in temporary_allowed_types:
                continue

            parts = share_type.split(":", 1)
            if len(parts) == 2:
                match parts[0]:
                    case "file" | "filehistory":
                        if parts[1].startswith("/"):
                            continue

            invalid_types.append(share_type)

        if invalid_types:
            raise click.ClickException(
                f"Invalid share type(s): {', '.join(invalid_types)}. "
                "Use 'fulcra catalog' to see valid data types."
            )
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(f"Failed to fetch catalog: {exc}\n{error_body}")

    return share_types
