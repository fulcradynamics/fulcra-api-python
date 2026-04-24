import json
import os
import pathlib
import webbrowser
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from uuid import UUID

import click
import dateparser

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
            interval = dateparser.parse(time_range[0])
            if interval is None:
                raise click.UsageError("Invalid date range")
            end_time = datetime.now()
            start_time = interval
        elif len(time_range) == 2:
            try:
                start_time = datetime.fromisoformat(time_range[0])
                end_time = datetime.fromisoformat(time_range[1])
            except ValueError as e:
                raise click.UsageError(f"Invalid datetime format: {e}")
        else:
            raise click.UsageError("Expected either 1 or 2 values for TIME_RANGE")

        return func(*args, start_time=start_time, end_time=end_time, **kwargs)

    return wrapper


@click.group()
@click.pass_context
def cli(ctx):
    ensure_config_directory()
    creds: FulcraCredentials | None = load_creds()
    kwargs: Dict[str, Any] = {"refresh_callback": save_creds}
    if creds:
        kwargs["credentials"] = creds

    ctx.obj = FulcraAPI(**kwargs)


@cli.group(help="Fulcra authentication sub-commands")
def auth():
    pass


@auth.command(help="Authenticate to Fulcra")
@click.pass_context
def login(ctx):

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


@auth.command("print-access-token", help="Print Fulcra oauth2 access token")
@click.pass_context
def get_access_token(ctx):
    if ctx.obj.fulcra_credentials.is_expired():
        ctx.obj.refresh_access_token()
    click.echo(ctx.obj.fulcra_credentials.access_token)


#
# mvp API implementation
#


@cli.command("calendars", help="List calendars")
@click.pass_context
def list_calendars(ctx):
    results = ctx.obj.calendars()

    for c in results:
        click.echo(json.dumps(c))


@cli.command("calendar-events", help="List calendar events")
@time_range
@click.pass_context
def list_calendar_events(ctx, start_time: datetime, end_time: datetime):
    results = ctx.obj.calendar_events(start_time, end_time)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("apple-workouts", help="List apple workouts")
@time_range
@click.pass_context
def list_apple_workouts(ctx, start_time: datetime, end_time: datetime):
    results = ctx.obj.apple_workouts(start_time, end_time)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("metric-time-series", help="List calculated time series for a Metric")
@click.argument("metric")
@time_range
@click.option(
    "-s", "--sample-rate", type=int, default=60, help="Length of each sample in seconds"
)
@click.option(
    "-n",
    "--replace-nulls",
    default=False,
    is_flag=True,
    help="Replace NA/null/None values with 0",
)
@click.option(
    "-a",
    "--agg-function",
    type=str,
    multiple=True,
    default=None,
    help="Aggregate functions to apply to time series window (max, min, delta, mean, uniques, allpoints, rollingmean)",
)
@click.pass_context
def metric_time_series(
    ctx,
    metric: str,
    start_time: datetime,
    end_time: datetime,
    sample_rate: int,
    replace_nulls: bool,
    agg_function: Tuple[str],
):

    try:
        data_type = ctx.obj.v1_catalog(metric)
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException("Type not found")
        else:
            raise click.ClickException(exc)

    if data_type[0]["api_version"] != "v0" or data_type[0]["class"] != "metric":
        raise click.ClickException(
            f"{data_type[0]['id']} cannot be returned with metric-time-series, use get-records instead to return raw sample records."
        )

    df = ctx.obj.metric_time_series(
        start_time,
        end_time,
        metric,
        sample_rate,
        replace_nulls,
        calculations=list(agg_function),
    )

    # Not exactly the most efficient implementation but here we are for now
    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@cli.command("google-location-updates", help="List Google Maps location updates")
@time_range
@click.pass_context
def google_location_updates(ctx, start_time: datetime, end_time: datetime):
    results = ctx.obj.gmaps_location_updates(start_time, end_time)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("apple-location-updates", help="List Apple location updates")
@time_range
@click.pass_context
def apple_location_updates(ctx, start_time: datetime, end_time: datetime):
    results = ctx.obj.apple_location_updates(start_time, end_time)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("apple-location-visits", help="List Apple location updates")
@time_range
@click.pass_context
def apple_location_visits(ctx, start_time: datetime, end_time: datetime):
    results = ctx.obj.apple_location_visits(start_time, end_time)

    for c in results:
        click.echo(json.dumps(c))


@cli.command("location-time-series", help="Return time series of locations")
@time_range
@click.option("-m", "--change-meters", help="Resolution granularity in meters")
@click.option("-s", "--sample-rate", default=900, help="Time series sample rate")
@click.option(
    "-l",
    "--look-back",
    default=14400,
    help="Maximum time in seconds to look back to find a value for a sample",
)
@click.option(
    "-r",
    "--reverse-geocode",
    is_flag=True,
    default=False,
    help="Reverse geolocate coordinates",
)
@click.pass_context
def location_time_series(
    ctx,
    start_time: datetime,
    end_time: datetime,
    change_meters: int,
    sample_rate: int,
    look_back: int,
    reverse_geocode: bool,
):
    results = ctx.obj.location_time_series(
        start_time, end_time, change_meters, sample_rate, look_back, reverse_geocode
    )

    for c in results:
        click.echo(json.dumps(c))


@cli.command("location-at-time", help="Return location at specified time")
@click.argument("time", type=click.DateTime())
@click.option(
    "-s", "--window-size", default=14400, help="Size window to look for samples within"
)
@click.option(
    "-i",
    "--include-after",
    is_flag=True,
    default=False,
    help="Include samples after the given time if it's the closest",
)
@click.option(
    "-r",
    "--reverse-geocode",
    is_flag=True,
    default=False,
    help="Reverse geolocate coordinates",
)
@click.pass_context
def location_at_time(
    ctx,
    time: datetime,
    window_size: int,
    include_after: bool,
    reverse_geocode: bool,
):
    results = ctx.obj.location_at_time(
        time, window_size, include_after, reverse_geocode
    )

    for c in results:
        click.echo(json.dumps(c))


@cli.command(
    "sleep-stages", help="Return sleep stages derived from sleep-related metric records"
)
@time_range
@click.pass_context
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
    help="Sleep stage to include. Can be passed multiple times. Defaults to all stages.",
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

    df = ctx.obj.sleep_stages(**kwargs)

    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@cli.command("sleep-cycles", help="Return sleep cycles summarized from sleep stages")
@time_range
@click.pass_context
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
    help="Sleep stage to include. Can be passed multiple times. Defaults to all stages.",
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
def sleep_cycles(
    ctx,
    start_time: datetime,
    end_time: datetime,
    cycle_gap: Optional[str],
    stage: Optional[Tuple[int]],
    gap_stage: Optional[Tuple[int]],
    no_clip_to_range: bool,
):
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

    df = ctx.obj.sleep_cycles(**kwargs)

    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@cli.command(
    "sleep-cycles-aggregated",
    help="Return sleep cycles aggregated by a specific period",
)
@time_range
@click.option(
    "--mode",
    type=str,
    default=None,
    help="Use cycle start or cycle end to assign cycles to periods, or split intervals at period boundaries.",
)
@click.option(
    "--period", type=str, default=None, help="Period interval. Defaults to 1d"
)
@click.option(
    "--function",
    multiple=True,
    default=None,
    help="Aggregation function to return. Can be specified multiple times. Defaults to 'sum'",
)
@click.option(
    "--time-zone",
    type=str,
    default=None,
    help="IANA time zone to return results in. Defaults to 'UTC'",
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
    help="Sleep stage to include. Can be passed multiple times. Defaults to all stages.",
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

    df = ctx.obj.sleep_agg(**kwargs)

    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@cli.command("get-records", help="Return raw sample records of a Fulcra data type")
@click.argument("data_type")
@time_range
@click.pass_context
def get_records(
    ctx,
    data_type: str,
    start_time: datetime,
    end_time: datetime,
):

    # Deal with user-configured annotation shorthand (AnnotationType/UUID)
    user_annotation_id = None
    parts = data_type.split("/", maxsplit=2)
    if len(parts) > 1:
        data_type = parts[0]
        try:
            user_annotation_id = UUID(parts[1])
        except ValueError as exc:
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
    "catalog", help="Return a list of queryable Fulcra data types and metadata"
)
@click.option("-d", "--data-type", type=str, help="Data Type to look up by ID")
@click.pass_context
def catalog(ctx, data_type: Optional[str]):

    try:
        response = ctx.obj.v1_catalog(data_type)
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException("Type not found")
        else:
            raise click.ClickException(exc) from exc

    for c in response:
        click.echo(json.dumps(c))


@cli.command("user-info", help="Return information about the authenticated user")
@click.pass_context
def user_info(ctx):
    resp = ctx.obj.get_user_info()
    click.echo(json.dumps(resp))


if __name__ == "__main__":
    cli()
