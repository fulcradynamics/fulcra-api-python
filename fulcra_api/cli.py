import json
import os
import pathlib
import webbrowser
import re
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from uuid import UUID

import click
import dateparser
import puremagic

from .core import FulcraAPI
from .credentials import FulcraCredentials

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
    def wrapper(ctx, *args, **kwargs):
        if ctx.obj.fulcra_credentials is None:
            raise click.ClickException(
                f"No credentials found, please run `{ctx.find_root().info_name} auth login`"
            )

        return f(ctx, *args, **kwargs)

    return wrapper


def human_size(n: int) -> tuple[int, str]:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    for unit in units:
        if n < 1024:
            return n, unit
        n //= 1024
    return n, "EiB"


def make_filepath(path: str, filename: str = "") -> str:
    """make file path string from given path and filename"""
    filepath = pathlib.PurePath("/", path, filename)

    return str(filepath)


def parse_time(ctx: click.Context, param: click.Parameter, value: str) -> datetime:
    """
    callback to parse a time string through dateparser and return datetime
    """
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
        # we got a time domain in a single interval argument
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


@click.group()
@click.option("--beta", is_flag=True, default=False, help="Enable beta features")
@click.pass_context
def cli(ctx, beta):
    """Command line interface for authenticating and interacting with the Fulcra Life API.

    Sub-commands return JSON data by default for convienent piping into tools like `jq` for parsing and filtering.
    """
    ensure_config_directory()
    creds: FulcraCredentials | None = load_creds()
    kwargs: Dict[str, Any] = {"refresh_callback": save_creds}
    if creds:
        kwargs["credentials"] = creds

    ctx.obj = FulcraAPI(**kwargs)


@cli.group(help="Authentication sub-commands")
def auth():
    pass


@auth.command(short_help="Authenticate to Fulcra")
@click.pass_context
def login(ctx):
    """Authenticates to the Fulcra Platform.

    The OAuth Device Authorization Flow isused to authenticate a user to the Fulcra Life API. A URL will be presented to load in browser. A new browser session will be automatically launched on supported platforms.

    Once run this command will poll for a valid token from the completion of the flow for up to two minutes.

    Credentials are persisted on the filesystem at ~/.config/fulcra/credentials.json
    """

    def prompt(device_code: str, uri: str, code: str):
        webbrowser.open_new_tab(uri)
        click.echo(
            f"✨ Use your browser to log into Fulcra. If your browser does not automatically open, visit this URL: {uri}"
        )
        click.echo(
            f"❗ Ensure the following code matches what's displayed in your browser: {code}"
        )

    try:
        creds = ctx.obj.oidc.authorize_via_device_flow(prompt_callback=prompt)
    except Exception as exc:
        print(exc)
        raise click.ClickException("Authorization failed, try again.") from exc

    click.echo("✅ Authorization successful!")

    save_creds(creds)


@auth.command("print-access-token", short_help="Print Fulcra oauth2 access token")
@click.pass_context
@requires_auth
def get_access_token(ctx):
    """Print a OAuth2 bearer token for use with accessing the Fulcra Life API.

    This is useful for making direct calls to the Fulcra Life API.

    \b
    EXAMPLE:
        curl --oauth2-bearer "$(fulcra auth print-access-token)" 'https://api.fulcradynamics.com/user/v1alpha1/info'
    """
    if ctx.obj.fulcra_credentials.is_expired():
        ctx.obj.refresh_access_token()
    click.echo(ctx.obj.fulcra_credentials.access_token)


#
# API commands
#


@cli.command("calendars", short_help="Return Apple calendars")
@click.pass_context
@requires_auth
def list_calendars(ctx):
    """Return Apple Calendar records."""

    try:
        results = ctx.obj.calendars()
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("calendar-events", short_help="Return Apple calendar events")
@time_range
@click.pass_context
@requires_auth
def list_calendar_events(ctx, start_time: datetime, end_time: datetime):
    """Return Apple Calendar Event records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    try:
        results = ctx.obj.calendar_events(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("apple-workouts", short_help="Return Apple workouts")
@time_range
@click.pass_context
@requires_auth
def list_apple_workouts(ctx, start_time: datetime, end_time: datetime):
    """Return Apple Workout records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """

    try:
        results = ctx.obj.apple_workouts(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@cli.command(
    "metric-time-series", short_help="Return a calculated time series for a metric"
)
@click.argument("metric")
@time_range
@click.option(
    "-s",
    "--sample-rate",
    type=int,
    default=60,
    help="Length of each sample in seconds. [default: 60]",
)
@click.option(
    "-n",
    "--replace-nulls",
    default=False,
    is_flag=True,
    help="Replace NA/null/None values with 0.",
)
@click.option(
    "-a",
    "--agg-function",
    type=str,
    multiple=True,
    default=None,
    help="Aggregate functions (max, min, delta, mean, uniques, allpoints, rollingmean) to apply to time series window, can be passed multiple times.",
)
@click.pass_context
@requires_auth
def metric_time_series(
    ctx,
    metric: str,
    start_time: datetime,
    end_time: datetime,
    sample_rate: int,
    replace_nulls: bool,
    agg_function: Tuple[str],
):
    """Return calculated time series data for METRIC across TIME_RANGE.

    METRIC: A Fulcra Data Type ID. Only API v0 'metric' types are supported. A full list of Fulcra Data Types can be returned from `fulcra catalog`.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)

    Time series values are calculated from multiple sources by sample rate according to source prioritization rules.

    """
    try:
        data_type = ctx.obj.v1_catalog(metric)
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException("Type not found")
        else:
            raise click.ClickException(exc)

    if data_type[0]["api_version"] != "v0" or data_type[0]["class"] != "metric":
        raise click.ClickException(
            f"{data_type[0]['id']} cannot be returned with metric-time-series, use `{ctx.find_root().info_name} get-records {metric}` instead to return raw sample records."
        )

    df = ctx.obj.metric_time_series(
        start_time,
        end_time,
        metric,
        sample_rate,
        replace_nulls,
        calculations=list(agg_function),
    )

    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@cli.command(
    "google-location-updates", short_help="Return Google Maps location update records"
)
@time_range
@click.pass_context
@requires_auth
def google_location_updates(ctx, start_time: datetime, end_time: datetime):
    """Return raw Google location update sample records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """

    try:
        results = ctx.obj.gmaps_location_updates(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@cli.command(
    "apple-location-updates", short_help="Return Apple location update records"
)
@time_range
@click.pass_context
@requires_auth
def apple_location_updates(ctx, start_time: datetime, end_time: datetime):
    """Return raw Apple location update sample records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """

    try:
        results = ctx.obj.apple_location_updates(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("apple-location-visits", short_help="Return Apple location visit records")
@time_range
@click.pass_context
@requires_auth
def apple_location_visits(ctx, start_time: datetime, end_time: datetime):
    """Return raw Apple location visit sample records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """

    try:
        results = ctx.obj.apple_location_visits(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@cli.command(
    "location-time-series",
    short_help="Return a calculated time series of location data",
)
@time_range
@click.option("-m", "--change-meters", help="Resolution granularity in meters.")
@click.option(
    "-s",
    "--sample-rate",
    default=900,
    help="Time series sample rate in seconds. [default: 900]",
)
@click.option(
    "-l",
    "--look-back",
    default=14400,
    help="Maximum time in seconds to look back to find a value for a sample. [default: 14400]",
)
@click.option(
    "-r",
    "--reverse-geocode",
    is_flag=True,
    default=False,
    help="Reverse geolocate coordinates.",
)
@click.pass_context
@requires_auth
def location_time_series(
    ctx,
    start_time: datetime,
    end_time: datetime,
    change_meters: int,
    sample_rate: int,
    look_back: int,
    reverse_geocode: bool,
):
    """Return a computed time series of visited locations across TIME_RANGE. This uses the most precise underlying data sources available at the given time.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    try:
        results = ctx.obj.location_time_series(
            start_time, end_time, change_meters, sample_rate, look_back, reverse_geocode
        )
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("location-at-time", short_help="Return location at specified time")
@click.argument("time", metavar="TIME", callback=parse_time)
@click.option(
    "-s",
    "--window-size",
    default=14400,
    help="Size window in seconds to look for samples within. [default: 14400]",
)
@click.option(
    "-i",
    "--include-after",
    is_flag=True,
    default=False,
    help="Include samples after the given time if they're the closest.",
)
@click.option(
    "-r",
    "--reverse-geocode",
    is_flag=True,
    default=False,
    help="Reverse geolocate coordinates.",
)
@click.pass_context
@requires_auth
def location_at_time(
    ctx,
    time: datetime,
    window_size: int,
    include_after: bool,
    reverse_geocode: bool,
):
    """Return the location at specified TIME.

    TIME: The time in ISO8601 format or as human readable string. ("now", "2025-05-05T01:30:00Z", "1 day", "5 days ago", etc)

    If no sample is available for the exact time, searches for the closest sample up to `window_size` seconds back. If `--include_after` is passed then also searches `window_size` seconds forward.
    """

    try:
        results = ctx.obj.location_at_time(
            time, window_size, include_after, reverse_geocode
        )
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@cli.command(
    "sleep-stages",
    short_help="Return sleep stages derived from sleep-related metric records",
)
@time_range
@click.option(
    "--cycle-gap",
    type=str,
    default=None,
    help="Minimum time interval seperating distinct cycles.",
)
@click.option(
    "--stage",
    type=int,
    multiple=True,
    default=None,
    help="Sleep stage to include. Can be passed multiple times. [default: all stages]",
)
@click.option(
    "--gap-stage",
    type=int,
    multiple=True,
    default=None,
    help="Sleep stage to consider as gaps in sleep cycles. Can be passed multiple times.",
)
@click.option(
    "--no-merge-overlapping",
    is_flag=True,
    default=False,
    help="Don't merge overlapping stages based on priority and start time.",
)
@click.option(
    "--no-merge-contiguous",
    is_flag=True,
    default=False,
    help="Don't merge contiguous samples with the same sleep stage.",
)
@click.option(
    "--no-clip-to-range",
    is_flag=True,
    default=False,
    help="Do not clip the data to the requested date range.",
)
@click.pass_context
@requires_auth
def sleep_stages(
    ctx,
    start_time: datetime,
    end_time: datetime,
    cycle_gap: str,
    stage: List[int],
    gap_stage: List[int],
    no_merge_overlapping: bool,
    no_merge_contiguous: bool,
    no_clip_to_range: bool,
):
    """Return computed sleep stages from sleep data over TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)

    Sleep stage integer values map to the following:

    \b
    0: In Bed
    1: Asleep (Unknown)
    2: Awake
    3: Asleep (Light)
    4: Asleep (Deep)
    5: Asleep (REM)
    """

    kwargs = {
        "start_time": start_time,
        "end_time": end_time,
        "cycle_gap": cycle_gap,
    }

    if stage:
        kwargs["stages"] = list(stage)

    if gap_stage:
        kwargs["gap_stages"] = list(gap_stage)

    if no_merge_overlapping:
        kwargs["merge_overlapping"] = False

    if no_merge_contiguous:
        kwargs["merge_contiguous"] = False

    if no_clip_to_range:
        kwargs["clip_to_range"] = False

    try:
        df = ctx.obj.sleep_stages(**kwargs)
    except HTTPError as exc:
        raise click.ClickException(exc)

    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@cli.command(
    "sleep-cycles", short_help="Return sleep cycles summarized from sleep stages"
)
@time_range
@click.option(
    "--cycle-gap",
    type=str,
    default=None,
    help="Minimum time interval seperating distinct cycles.",
)
@click.option(
    "--stage",
    type=int,
    multiple=True,
    default=None,
    help="Sleep stage to include. Can be passed multiple times. [default: all stages]",
)
@click.option(
    "--gap-stage",
    type=int,
    multiple=True,
    default=None,
    help="Sleep stage to consider as gaps in sleep cycles. Can be passed multiple times.",
)
@click.option(
    "--no-clip-to-range",
    is_flag=True,
    default=False,
    help="Do not clip the data to the requested date range.",
)
@click.pass_context
@requires_auth
def sleep_cycles(
    ctx,
    start_time: datetime,
    end_time: datetime,
    cycle_gap: Optional[str],
    stage: Optional[Tuple[int]],
    gap_stage: Optional[Tuple[int]],
    no_clip_to_range: bool,
):
    """Return computed sleep cycles summarized from sleep stages over TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    kwargs = {
        "start_time": start_time,
        "end_time": end_time,
        "cycle_gap": cycle_gap,
    }

    if stage:
        kwargs["stages"] = list(stage)

    if gap_stage:
        kwargs["gap_stages"] = list(gap_stage)

    if no_clip_to_range:
        kwargs["clip_to_range"] = False

    try:
        df = ctx.obj.sleep_cycles(**kwargs)
    except HTTPError as exc:
        raise click.ClickException(exc)

    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@cli.command(
    "sleep-cycles-aggregated",
    short_help="Return sleep cycles aggregated by a specific period",
)
@time_range
@click.option(
    "--mode",
    type=str,
    default=None,
    help="Use cycle start or cycle end to assign cycles to periods, or split intervals at period boundaries.",
)
@click.option("--period", type=str, default=None, help="Period interval. [default: 1d]")
@click.option(
    "--function",
    multiple=True,
    default=None,
    help="Aggregation function to return. Can be specified multiple times. [default: sum]",
)
@click.option(
    "--time-zone",
    type=str,
    default=None,
    help="IANA time zone to return results in. [default: UTC]",
)
@click.option(
    "--cycle-gap",
    type=str,
    default=None,
    help="Minimum time interval seperating distinct cycles.",
)
@click.option(
    "--stage",
    type=int,
    multiple=True,
    default=None,
    help="Sleep stage to include. Can be passed multiple times. [default: all stages]",
)
@click.option(
    "--gap-stage",
    type=int,
    multiple=True,
    default=None,
    help="Sleep stage to consider as gaps in sleep cycles. Can be passed multiple times.",
)
@click.option(
    "--no-clip-to-range",
    is_flag=True,
    default=False,
    help="Do not clip the data to the requested date range.",
)
@click.pass_context
@requires_auth
def sleep_cycles_aggregated(
    ctx,
    start_time: datetime,
    end_time: datetime,
    cycle_gap: Optional[str],
    stage: Optional[Tuple[str]],
    gap_stage: Optional[Tuple[str]],
    no_clip_to_range: bool,
    mode: Optional[str],
    period: Optional[str],
    function: Tuple[str],
    time_zone: Optional[str],
):
    """Return computed sleep cycles aggregated by a specific function over TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """

    kwargs = {
        "start_time": start_time,
        "end_time": end_time,
        "cycle_gap": cycle_gap,
        "mode": mode,
        "period": period,
        "tz": time_zone,
    }

    if stage:
        kwargs["stages"] = list(stage)

    if gap_stage:
        kwargs["gap_stages"] = list(gap_stage)

    if no_clip_to_range:
        kwargs["clip_to_range"] = False

    if function:
        kwargs["agg_functions"] = list(function)

    try:
        df = ctx.obj.sleep_agg(**kwargs)
    except HTTPError as exc:
        raise click.ClickException(exc)

    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@cli.command("get-records", short_help="Return raw sample records for a data type")
@click.argument("data_type")
@time_range
@click.pass_context
@requires_auth
def get_records(
    ctx,
    data_type: str,
    start_time: datetime,
    end_time: datetime,
):
    """Return raw sample records of DATA_TYPE across TIME_RANGE.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)

    Returned records may have multiple sources and require additional filtering and prioritization to calculate correct results.

    Examples:

    \b
    Return seven days of HeartRate records:
    fulcra get-records HeartRate "2025-05-01T00:00:00Z" "2025-05-08T00:00:00Z"

    \b
    Return the last day of StepCount records:
    fulcra get-records StepCount "1 day"
    """

    # Deal with user-configured annotation shorthand (AnnotationType/UUID)
    user_annotation_id = None
    parts = data_type.split("/", maxsplit=2)
    if len(parts) > 1:
        data_type = parts[0]
        try:
            user_annotation_id = UUID(parts[1])
        except ValueError:
            raise click.ClickException(
                "User configured annotation shorthand must be <Annotation Type>/<UUID>"
            )

    try:
        data_type = ctx.obj.v1_catalog(data_type)
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException("Type not found")
        else:
            raise click.ClickException(exc)

    results = []

    for dt in data_type:
        if dt["api_version"] == "v0" and dt["class"] == "metric":
            query_func = ctx.obj.metric_samples
            kwargs = {
                "start_time": start_time,
                "end_time": end_time,
                "metric": dt["id"],
            }
        elif dt["api_version"] == "v1alpha1" and dt["class"] == "metric":
            query_func = ctx.obj.fulcra_v1_api
            kwargs = {
                "data_class": dt["class"],
                "data_type": dt["id"],
                "params": {"start_time": start_time, "end_time": end_time},
            }
            if user_annotation_id:
                kwargs["params"]["filter"] = (
                    f"source:com.fulcradynamics.annotation.{user_annotation_id}"
                )
        elif dt["api_version"] == "v1alpha1" and dt["class"] == "event":
            query_func = ctx.obj.fulcra_v1_api
            kwargs = {
                "data_class": dt["class"],
                "data_type": dt["id"],
                "params": {"start_time": start_time, "end_time": end_time},
            }
            if user_annotation_id:
                kwargs["params"]["filter"] = (
                    f"source:com.fulcradynamics.annotation.{user_annotation_id}"
                )
        else:
            raise click.ClickException(
                f"Could not derive API endpoint for data type '{dt['id']}'"
            )

        resp = query_func(**kwargs)

        if isinstance(resp, bytes):
            resp = json.loads(resp)

        results = results + resp

    for x in results:
        click.echo(json.dumps(x))


@cli.command(
    "catalog", short_help="Return a list of queryable Fulcra data types and metadata"
)
@click.option("-d", "--data-type", type=str, help="Data Type to look up by ID.")
@click.option("-n", "--name", type=str, help="Filter results by partial name.")
@click.option("--base-types-only", is_flag=True)
@click.pass_context
@requires_auth
def catalog(ctx, data_type: Optional[str], name: Optional[str], base_types_only: bool):
    """
    Return a list of Fulcra Data Types that can be queried with `get-records`, `metric-time-series`, and other commands.

    The `related_cli_commands` property contains a list of CLI sub-commands that can be used with a given data type.
    """

    try:
        response = ctx.obj.v1_catalog(data_type)
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException("Type not found")
        else:
            raise click.ClickException(exc) from exc

    if name:
        response = [c for c in response if name.lower() in c.get("name", "").lower()]

    if base_types_only:
        pattern = r"^.*Annotation$"  # TODO: filter this based on flag from catalog items (or category)
        response = [
            c
            for c in response
            if "user_configured" not in c.get("categories")
            and re.match(pattern, c.get("id"))
        ]

    for c in response:
        c["related_cli_commands"] = related_cli_commands(c)
        click.echo(json.dumps(c))


#
# Tag functionality
#


@cli.command("tags", short_help="Return a list of user-defined tags")
@click.option("-n", "--name", type=str, help="Filter results by partial name.")
@click.option("--tag-name", type=str, help="Filter results by full tag name.")
@click.option("--tag-id", type=str, help="Filter results by tag ID.")
@click.pass_context
@requires_auth
def tags(ctx, name: Optional[str], tag_name: Optional[str], tag_id: Optional[str]):
    """
    Return a list of user-defined tags that can be used when creating and recording custom data types.
    """

    try:
        response = ctx.obj.tags()

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


@cli.command("tag", short_help="Get a user-defined tag")
@click.option("--name", type=str, help="Tag name")
@click.option("--id", type=str, help="Tag ID")
@click.pass_context
@requires_auth
def tag(ctx, name: Optional[str], id: Optional[str]):
    if name and id:
        raise click.UsageError("--name and --id are mutually exclusive")

    try:
        if name:
            resp = ctx.obj.get_tag_by_name(name=name)
            click.echo(json.dumps(resp))
        elif id:
            resp = ctx.obj.get_tag_by_id(tag_id=id)
            click.echo(json.dumps(resp))
    except HTTPError as exc:
        if exc.status == 404:
            click.echo(f"No tag found: {name or id}")
        else:
            raise click.ClickException(f"Failed to get tag: {exc}")


@cli.command("create-tags", short_help="Create user-defined tags")
@click.argument("names", nargs=-1)
@click.pass_context
@requires_auth
def create_tags(ctx, names: Tuple[str, ...]):
    """
    Create case-insensitive user-defined tags by name that can be used when creating and recording custom data types.
    """

    created_tags = []

    for name in names:
        tag_name = name.lower()
        try:
            resp = ctx.obj.create_tag(tag_name)
            created_tags.append(resp)
        except HTTPError as exc:
            if exc.status == 409:
                continue
            raise click.ClickException(f"Failed to create tag {tag_name}: {exc}")

    click.echo(json.dumps(created_tags))


@cli.command("delete-tag", short_help="Delete user-defined tag")
@click.argument("tag_id")
@click.pass_context
@requires_auth
def delete_tag(ctx, tag_id: str):
    """
    Delete a user-defined tag by tag ID.
    """

    try:
        ctx.obj.delete_tag(tag_id)
    except HTTPError as exc:
        raise click.ClickException(f"Failed to delete tag {tag_id}: {exc}")

    click.echo(f"Tag deleted: {tag_id}")


#
# Data type functionality
#


@cli.command("create-data-type", short_help="Create a new base data type")
@click.argument(
    "base_data_type",
    type=click.Choice(
        [
            "MomentAnnotation",  # TODO: use the fulcradatatypes package for these?
            "DurationAnnotation",
            "BooleanAnnotation",
            "NumericAnnotation",
            "ScaleAnnotation",
        ],
        case_sensitive=False,
    ),
)
@click.argument("name", type=str)
@click.option(
    "-d", "--description", type=str, default=None, help="Description of the data type"
)
@click.option(
    "-t",
    "--tag",
    "tags",
    type=str,
    multiple=True,
    help="Tags to attach to the data type",
)
@click.option(
    "-k",
    "--kind",
    "metric_kind",
    type=click.Choice(
        [
            "cumulative",
            "discrete",
        ]
    ),
)
@click.option(
    "-v",
    "--value",
    "raw_value",
    type=str,
    help="Default value for recording the data type",
)
@click.option("-u", "--unit", "unit", type=str, help="Unit for recording the data type")
@click.option(
    "-s",
    "--scale-label",
    "scale_labels",
    type=str,
    multiple=True,
    help="Used for ScaleAnnotation labels",
)
@click.option(
    "--add-to-timeline", is_flag=True, help="Add created data type to timeline"
)
@click.pass_context
@requires_auth
def create_data_type(
    ctx,
    base_data_type: str,
    name: str,
    description: Optional[str],
    tags: List[str],
    metric_kind: Optional[str],
    raw_value: Optional[str],
    unit: Optional[str],
    scale_labels: List[str],
    add_to_timeline: bool,
):
    """Create a new moment annotation definition.

    BASE_DATA_TYPE: The base data type to create

    NAME: The given name of the data type

    Use -d/--description to add an optional description
    """

    value = None
    if base_data_type == "MomentAnnotation":
        annotation_type = "moment"
        if metric_kind is not None:
            raise click.BadOptionUsage(
                "metric_kind",
                f"-k / --kind cannot be used with base data type {base_data_type}",
                ctx,
            )
        if raw_value is not None:
            raise click.BadOptionUsage(
                "raw_value",
                f"-v / --value cannot be used with base data type {base_data_type}",
                ctx,
            )
        if unit is not None:
            raise click.BadOptionUsage(
                "unit",
                f"-u / --unit cannot be used with base data type {base_data_type}",
                ctx,
            )
        if len(scale_labels) > 0:
            raise click.BadOptionUsage(
                "scale_labels",
                f"-s / --scale-labels cannot be used with base data type {base_data_type}",
                ctx,
            )
    elif base_data_type == "DurationAnnotation":
        annotation_type = "duration"
        if unit is not None:
            raise click.BadOptionUsage(
                "unit",
                f"-u / --unit cannot be used with base data type {base_data_type}",
                ctx,
            )
        if len(scale_labels) > 0:
            raise click.BadOptionUsage(
                "scale_labels",
                f"-s / --scale-labels cannot be used with base data type {base_data_type}",
                ctx,
            )
    elif base_data_type == "BooleanAnnotation":
        annotation_type = "boolean"
        if raw_value is not None:
            value = click.types.BoolParamType().convert(raw_value, None, None)
        if unit is not None:
            raise click.BadOptionUsage(
                "unit",
                f"-u / --unit cannot be used with base data type {base_data_type}",
                ctx,
            )
        if len(scale_labels) > 0:
            raise click.BadOptionUsage(
                "scale_labels",
                f"-s / --scale-labels cannot be used with base data type {base_data_type}",
                ctx,
            )
    elif base_data_type == "NumericAnnotation":
        annotation_type = "numeric"
        if raw_value is not None:
            value = click.types.FloatParamType().convert(raw_value, None, None)
        if len(scale_labels) > 0:
            raise click.BadOptionUsage(
                "scale_labels",
                f"-s / --scale-labels cannot be used with base data type {base_data_type}",
                ctx,
            )
    elif base_data_type == "ScaleAnnotation":
        if len(scale_labels) != 5:
            raise click.BadOptionUsage(
                "scale_labels",
                f"-s / --scale-labels must be used with exactly 5 values with base data type {base_data_type}",
                ctx,
            )
        annotation_type = "scale"
    else:
        raise click.ClickException(f"Unsupported base data type {base_data_type}")

    try:
        ann = ctx.obj.create_annotation(
            annotation_type=annotation_type,
            name=name,
            description=description,
            tags=tags,
            metric_kind=metric_kind,
            value=value,
            unit=unit,
            scale_labels=scale_labels,
        )

        if add_to_timeline:
            try:
                info = ctx.obj.get_user_info()
                current_prefs = info.get("preferences", {})
                existing_metrics_map = current_prefs.get("selected_metrics_map", {})

                current_selection = existing_metrics_map.get(info["userid"], [])
                ann_id = ann["id"]

                # TODO: this is a legacy naming convention for timeline data tracks
                updated_selection = [f"fulcra_custom_event.{ann_id}"] + current_selection

                prefs_payload = {
                    "selected_metrics_map": {
                        **existing_metrics_map,
                        info["userid"]: updated_selection,
                    }
                }

                ctx.obj.update_user_preferences(prefs_payload)
            except HTTPError as exc:
                click.echo(f"Failed to add annotation to timeline: {exc}", err=True)

        click.echo(json.dumps(ann))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise click.ClickException(
            f"Failed to create event data type: {exc}\n{error_body}"
        )


@cli.command("archive-data-type", short_help="Archive a user-defined data type")
@click.argument("data_type")
@click.pass_context
@requires_auth
def archive_data_type(ctx, data_type: str):
    """
    Archive a user-defined data type by ID.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types
    """

    try:
        filtered_types = ctx.obj.v1_catalog(data_type=data_type)
    except HTTPError:
        raise click.ClickException(f"Could not find data type matching id: {data_type}")

    if len(filtered_types) == 0:
        raise click.ClickException(f"Could not find data type matching id: {data_type}")
    elif len(filtered_types) > 1:
        raise click.ClickException(f"Found multiple data types matching id: {data_type}")

    ann_id = None
    try:
        parts = data_type.split("/", maxsplit=2)
        ann_id = parts[1]
        ann_id = str(UUID(ann_id))
    except (ValueError, IndexError):
        raise click.ClickException("DATA_TYPE must be <Annotation Type>/<UUID>")

    try:
        ctx.obj.delete_annotation(annotation_id=ann_id)
        click.echo(f"Archived data type: {data_type}")
    except HTTPError as exc:
        raise click.ClickException(f"Failed to archive data type {data_type}: {exc}")


@cli.command("restore-data-type", short_help="Restore an archived user-defined data type")
@click.argument("data_type")
@click.pass_context
@requires_auth
def restore_data_type(ctx, data_type: str):
    """
    Restore an archived user-defined data type by ID.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog` for a list of Fulcra Data Types
    """

    try:
        filtered_types = ctx.obj.v1_catalog(data_type=data_type)
    except HTTPError:
        raise click.ClickException(f"Could not find data type matching id: {data_type}")

    if len(filtered_types) == 0:
        raise click.ClickException(f"Could not find data type matching id: {data_type}")
    elif len(filtered_types) > 1:
        raise click.ClickException(f"Found multiple data types matching id: {data_type}")

    ann_id = None
    try:
        parts = data_type.split("/", maxsplit=2)
        ann_id = parts[1]
        ann_id = str(UUID(ann_id))
    except (ValueError, IndexError):
        raise click.ClickException("DATA_TYPE must be <Annotation Type>/<UUID>")

    try:
        ann = ctx.obj.restore_annotation(annotation_id=ann_id)
        click.echo(json.dumps(ann))
    except HTTPError as exc:
        raise click.ClickException(f"Failed to restore data type {data_type}: {exc}")


@cli.command("user-info", short_help="Return information about the authenticated user")
@click.pass_context
@requires_auth
def user_info(ctx):
    """Return user information object for authenticated user"""
    try:
        resp = ctx.obj.get_user_info()
    except HTTPError as exc:
        raise click.ClickException(exc) from exc

    click.echo(json.dumps(resp))


#
# File functionality
#


@cli.group(help="File management sub-commands")
def file():
    pass


@file.command("list", short_help="List files")
@click.argument("path", type=str, default="/")
@click.pass_context
@requires_auth
def file_list(ctx, path: str):
    """List uploaded files.

    PATH: Path to list files in [Default: /]
    """

    path = make_filepath(path)

    results = ctx.obj.list_files(path)

    if results.get("folders") is not None:
        for d in results.get("folders", []):
            click.echo(f"{d}/")

    for f in results.get("files", []):
        size, unit = human_size(f.get("size"))
        try:
            dt = datetime.fromisoformat(f.get("uploaded_at"))
        except TypeError as exc:
            dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        click.echo(
            f"{str(size) + unit:7} {dt.strftime('%Y-%m-%d %I:%M%p %Z')}  {f.get('name')}"
        )


@file.command("stat", short_help="Get information about a file")
@click.argument("path", type=str)
@click.pass_context
@requires_auth
def file_stat(ctx, path: str):
    """Returns information about an uploaded file, including size, date uploaded, and all previously uploaded versions of the file.

    PATH: Full path of the file.
    """

    path = make_filepath(path)

    try:
        f = ctx.obj.resolve_filepath(path, all_versions=True)
    except Exception as exc:
        raise click.ClickException(exc)

    latest_version = f[0]

    click.echo(
        f"{make_filepath(latest_version['path'], latest_version['name'])} ({latest_version['size']} bytes)"
    )
    click.echo(f"Uploaded: {latest_version['uploaded_at']}")
    click.echo(f"Version: {latest_version['id']}")
    click.echo(f"Previous Versions: {len(f[1:])}")
    for file in f[1:]:
        click.echo(f"- {file['id']} {file['uploaded_at']} ({file['size']} bytes)")


@file.command("download", short_help="Download a file")
@click.argument("remote_file", type=str)
@click.argument("local_file", type=click.File(mode="wb"), required=False, default=None)
@click.pass_context
@requires_auth
def file_download(ctx, remote_file: str, local_file=None):
    """Download a file.

    REMOTE_FILE: Full path of file to download.

    LOCAL_FILE: Path to save downloaded file to, use `-` to print file contents to STDOUT. [Default: REMOTE_FILE name]
    """

    remote_file = make_filepath(remote_file)

    try:
        f = ctx.obj.resolve_filepath(remote_file)
    except Exception as exc:
        raise click.ClickException(exc)

    resp = ctx.obj.download_file(f[0].get("id"))

    if local_file is None:
        local_file = click.open_file(pathlib.PurePath(f[0].get("name")).name, mode="wb")

    local_file.write(resp.read())

    if local_file.name != "<stdout>":
        click.echo(f"⬇️ fulcra:{remote_file} -> {local_file.name}")


@file.command("upload", short_help="Upload a file")
@click.argument("local_file", type=click.File(mode="rb"))
@click.argument("remote_file", type=str, default="")
@click.pass_context
@requires_auth
def file_upload(ctx, local_file: click.File, remote_file: str):
    """Upload a file.

    LOCAL_FILE: File to upload.

    REMOTE_FILE: Full path to upload file to. [Default: LOCAL_FILE name]
    """
    if local_file.name == "<stdin>":
        raise click.ClickException("Cannot upload from stdin")

    if remote_file != "":
        path = make_filepath(remote_file)
    else:
        path = make_filepath(local_file.name)

    file_size = os.path.getsize(local_file.name)
    try:
        file_type = puremagic.from_file(local_file.name, mime=True)
    except puremagic.PureError as exc:
        file_type = "application/octet-stream"

    try:
        new_file = ctx.obj.upload_file(local_file, file_type, file_size, path)
        full_path = make_filepath(new_file["file"]["path"], new_file["file"]["name"])
    except HTTPError as exc:
        raise click.ClickException(exc.fp.read())

    click.echo(f"⬆️ {local_file.name} -> fulcra:{full_path}")


@file.command("delete", short_help="Delete a file")
@click.argument("path", type=str)
@click.pass_context
@requires_auth
def file_delete(ctx, path):
    """Delete a file.

    PATH: Path of the file to delete.
    """
    path = make_filepath(path)

    try:
        f = ctx.obj.resolve_filepath(path)
    except Exception as exc:
        raise click.ClickException(exc)

    ctx.obj.delete_file(f[0].get("id"))

    click.echo(f"❌ fulcra:{path}")


@file.command("restore", short_help="Restore a file")
@click.argument("version_id", type=UUID)
@click.pass_context
@requires_auth
def file_restore(ctx, version_id):
    """Restore a previous version of a file.

    VERSION_ID: UUID of the file version you want to restore. Versions are returned via the `file stat` command.
    """

    try:
        file_version = ctx.obj.get_file_by_version(version_id)
    except HTTPError as exc:
        if exc.status == 404:
            raise click.ClickException(f"File version {version_id} not found")
        else:
            raise click.ClickException(exc)

    full_file_name = make_filepath(file_version["path"], file_version["name"])

    new_file = ctx.obj.restore_file(file_version["id"])

    click.echo(
        f"fulcra:{full_file_name}  {file_version['id']} ({file_version['uploaded_at']}) ➡️ {new_file['id']} ({new_file['uploaded_at']})"
    )


if __name__ == "__main__":
    cli()
