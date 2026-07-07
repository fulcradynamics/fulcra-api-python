import os
import pathlib
from datetime import datetime, timezone
from functools import wraps

import click
import dateparser

from ..core import FulcraAPI
from ..credentials import FulcraCredentials

# Create a pass decorator for FulcraAPI to enable type hints in subcommands
pass_fulcra_api = click.make_pass_decorator(FulcraAPI)

CONFIG_PATH = pathlib.Path.home() / ".config" / "fulcra"
CREDS_FILE = pathlib.Path(CONFIG_PATH / "credentials.json")


def ensure_config_directory():
    try:
        os.mkdir(CONFIG_PATH)
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


def human_size(n: int) -> tuple[int, str]:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    for unit in units:
        if n < 1024:
            return n, unit
        n //= 1024
    return n, "EiB"


def make_filepath(path: str, filename: str = "") -> str:
    filepath = pathlib.PurePath("/", path, filename)
    return str(filepath)


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
