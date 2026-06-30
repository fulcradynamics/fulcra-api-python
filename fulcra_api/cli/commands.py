import json
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.error import HTTPError
from uuid import UUID

import click

from .utils import parse_time, related_cli_commands, requires_auth, time_range


@click.command("calendars", short_help="Return Apple calendars")
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


@click.command("calendar-events", short_help="Return Apple calendar events")
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


@click.command("apple-workouts", short_help="Return Apple workouts")
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


@click.command(
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


@click.command(
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


@click.command(
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


@click.command(
    "apple-location-visits", short_help="Return Apple location visit records"
)
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


@click.command(
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


@click.command("location-at-time", short_help="Return location at specified time")
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


@click.command(
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


@click.command(
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


@click.command(
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


@click.command("get-records", short_help="Return raw sample records for a data type")
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


@click.command(
    "catalog", short_help="Return a list of queryable Fulcra data types and metadata"
)
@click.option("-d", "--data-type", type=str, help="Data Type to look up by ID.")
@click.option("-n", "--name", type=str, help="Filter results by partial name.")
@click.option("--base-types-only", is_flag=True, default=False)
@click.option("-c", "--category", type=str, help="Filter by category.")
@click.pass_context
@requires_auth
def catalog(
    ctx,
    base_types_only: bool,
    data_type: str | None = None,
    name: str | None = None,
    category: str | None = None,
):
    """
    Return a list of Fulcra Data Types that can be queried with `get-records`, `metric-time-series`, and other commands.

    The `related_cli_commands` property contains a list of CLI sub-commands that can be used with a given data type.
    """

    try:
        if base_types_only:
            catalog_category = "base_type"
        elif category:
            catalog_category = category
        else:
            catalog_category = None

        response = ctx.obj.v1_catalog(data_type=data_type, category=catalog_category)
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException("Type not found")
        else:
            raise click.ClickException(exc) from exc

    if name:
        response = [c for c in response if name.lower() in c.get("name", "").lower()]

    for c in response:
        c["related_cli_commands"] = related_cli_commands(c)
        click.echo(json.dumps(c))


@click.command(
    "user-info", short_help="Return information about the authenticated user"
)
@click.pass_context
@requires_auth
def user_info(ctx):
    """Return user information object for authenticated user"""
    try:
        resp = ctx.obj.get_user_info()
    except HTTPError as exc:
        raise click.ClickException(exc) from exc

    click.echo(json.dumps(resp))


@click.command(
    "data-updates", short_help="Info on data updates that occurred during a period"
)
@time_range
@click.pass_context
@requires_auth
def data_updates(ctx, start_time: datetime, end_time: datetime):
    """Return a summary of the data that was updated across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)

    The result contains the data types that had records processed (along with
    the number of records processed for each) and any uploaded files that changed.
    """
    try:
        resp = ctx.obj.data_updates(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc) from exc

    click.echo(json.dumps(resp))
