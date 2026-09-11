import json
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.error import HTTPError

import click

from fulcra_api import records
from fulcra_api.core import FulcraAPI

from .utils import (
    group_participant_options,
    parse_time,
    pass_fulcra_api,
    related_cli_commands,
    requires_auth,
    resolve_data_source,
    resolve_data_type,
    time_range,
)


@click.command("calendars", short_help="Return Apple calendars")
@pass_fulcra_api
@requires_auth
def list_calendars(fulcra_api: FulcraAPI):
    """Return Apple Calendar records."""

    try:
        results = fulcra_api.calendars()
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@click.command("calendar-events", short_help="Return Apple calendar events")
@time_range
@pass_fulcra_api
@requires_auth
def list_calendar_events(
    fulcra_api: FulcraAPI, start_time: datetime, end_time: datetime
):
    """Return Apple Calendar Event records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    try:
        results = fulcra_api.calendar_events(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@click.command("apple-workouts", short_help="Return Apple workouts")
@time_range
@group_participant_options
@pass_fulcra_api
@requires_auth
def list_apple_workouts(
    fulcra_api: FulcraAPI,
    start_time: datetime,
    end_time: datetime,
    group_id,
    participant_id,
):
    """Return Apple Workout records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    source = resolve_data_source(fulcra_api, group_id, participant_id)

    try:
        results = source.apple_workouts(start_time, end_time)
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
@group_participant_options
@pass_fulcra_api
@requires_auth
def metric_time_series(
    fulcra_api: FulcraAPI,
    metric: str,
    start_time: datetime,
    end_time: datetime,
    sample_rate: int,
    replace_nulls: bool,
    agg_function: Tuple[str],
    group_id,
    participant_id,
):
    """Return calculated time series data for METRIC across TIME_RANGE.

    METRIC: A Fulcra Data Type ID. Only API v0 'metric' types are supported. A full list of Fulcra Data Types can be returned from `fulcra catalog`.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)

    Time series values are calculated from multiple sources by sample rate according to source prioritization rules.

    """
    try:
        data_type = fulcra_api.v1_catalog(metric)
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException("Type not found")
        else:
            raise click.ClickException(exc)

    if data_type[0]["api_version"] != "v0" or data_type[0]["class"] != "metric":
        raise click.ClickException(
            f"{data_type[0]['id']} cannot be returned with metric-time-series, use `fulcra get-records {metric}` instead to return raw sample records."
        )

    source = resolve_data_source(fulcra_api, group_id, participant_id)
    df = source.metric_time_series(
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
@group_participant_options
@pass_fulcra_api
@requires_auth
def google_location_updates(
    fulcra_api: FulcraAPI,
    start_time: datetime,
    end_time: datetime,
    group_id,
    participant_id,
):
    """Return raw Google location update sample records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    source = resolve_data_source(fulcra_api, group_id, participant_id)

    try:
        results = source.gmaps_location_updates(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@click.command(
    "apple-location-updates", short_help="Return Apple location update records"
)
@time_range
@group_participant_options
@pass_fulcra_api
@requires_auth
def apple_location_updates(
    fulcra_api: FulcraAPI,
    start_time: datetime,
    end_time: datetime,
    group_id,
    participant_id,
):
    """Return raw Apple location update sample records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    source = resolve_data_source(fulcra_api, group_id, participant_id)

    try:
        results = source.apple_location_updates(start_time, end_time)
    except HTTPError as exc:
        raise click.ClickException(exc)

    for c in results:
        click.echo(json.dumps(c))


@click.command(
    "apple-location-visits", short_help="Return Apple location visit records"
)
@time_range
@group_participant_options
@pass_fulcra_api
@requires_auth
def apple_location_visits(
    fulcra_api: FulcraAPI,
    start_time: datetime,
    end_time: datetime,
    group_id,
    participant_id,
):
    """Return raw Apple location visit sample records across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    source = resolve_data_source(fulcra_api, group_id, participant_id)

    try:
        results = source.apple_location_visits(start_time, end_time)
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
@group_participant_options
@pass_fulcra_api
@requires_auth
def location_time_series(
    fulcra_api: FulcraAPI,
    start_time: datetime,
    end_time: datetime,
    change_meters: int,
    sample_rate: int,
    look_back: int,
    reverse_geocode: bool,
    group_id,
    participant_id,
):
    """Return a computed time series of visited locations across TIME_RANGE. This uses the most precise underlying data sources available at the given time.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)
    """
    source = resolve_data_source(fulcra_api, group_id, participant_id)
    try:
        results = source.location_time_series(
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
@group_participant_options
@pass_fulcra_api
@requires_auth
def location_at_time(
    fulcra_api: FulcraAPI,
    time: datetime,
    window_size: int,
    include_after: bool,
    reverse_geocode: bool,
    group_id,
    participant_id,
):
    """Return the location at specified TIME.

    TIME: The time in ISO8601 format or as human readable string. ("now", "2025-05-05T01:30:00Z", "1 day", "5 days ago", etc)

    If no sample is available for the exact time, searches for the closest sample up to `window_size` seconds back. If `--include_after` is passed then also searches `window_size` seconds forward.
    """

    source = resolve_data_source(fulcra_api, group_id, participant_id)
    try:
        results = source.location_at_time(
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
@group_participant_options
@pass_fulcra_api
@requires_auth
def sleep_stages(
    fulcra_api: FulcraAPI,
    start_time: datetime,
    end_time: datetime,
    cycle_gap: str,
    stage: List[int],
    gap_stage: List[int],
    no_merge_overlapping: bool,
    no_merge_contiguous: bool,
    no_clip_to_range: bool,
    group_id,
    participant_id,
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

    source = resolve_data_source(fulcra_api, group_id, participant_id)
    try:
        df = source.sleep_stages(**kwargs)
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
@group_participant_options
@pass_fulcra_api
@requires_auth
def sleep_cycles(
    fulcra_api: FulcraAPI,
    start_time: datetime,
    end_time: datetime,
    cycle_gap: Optional[str],
    stage: Optional[Tuple[int]],
    gap_stage: Optional[Tuple[int]],
    no_clip_to_range: bool,
    group_id,
    participant_id,
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

    source = resolve_data_source(fulcra_api, group_id, participant_id)
    try:
        df = source.sleep_cycles(**kwargs)
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
@group_participant_options
@pass_fulcra_api
@requires_auth
def sleep_cycles_aggregated(
    fulcra_api: FulcraAPI,
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
    group_id,
    participant_id,
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

    source = resolve_data_source(fulcra_api, group_id, participant_id)
    try:
        df = source.sleep_agg(**kwargs)
    except HTTPError as exc:
        raise click.ClickException(exc)

    j = json.loads(df.to_json(orient="table"))

    for c in j["data"]:
        click.echo(json.dumps(c))


@click.command("get-records", short_help="Return raw sample records for a data type")
@click.option(
    "--user-id",
    type=str,
    default=None,
    is_eager=True,
    help="Fulcra user ID to query data for (requires an active datashare from that user).",
)
@click.argument(
    "data_type",
    callback=resolve_data_type(allow_multiple=True, user_id_param="user_id"),
)
@time_range(allow_latest=True)
@group_participant_options
@pass_fulcra_api
@requires_auth
def get_records(
    fulcra_api: FulcraAPI,
    data_type: list[dict],
    start_time: datetime | None,
    end_time: datetime | None,
    latest: bool,
    user_id: str | None,
    group_id,
    participant_id,
):
    """Return raw sample records of DATA_TYPE across TIME_RANGE.

    DATA_TYPE: ID of a Fulcra Data Type. Run `fulcra catalog --queryable` for a list of Fulcra Data Types you can query.

    TIME_RANGE: Two start & end date arguments in ISO8601 format, a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.), or the literal "latest" to return only the most recent record.

    Returned records may have multiple sources and require additional filtering and prioritization to calculate correct results.

    Examples:

    \b
    Return seven days of HeartRate records:
    fulcra get-records HeartRate "2025-05-01T00:00:00Z" "2025-05-08T00:00:00Z"

    \b
    Return the last day of StepCount records:
    fulcra get-records StepCount "1 day"

    \b
    Return the most recent HeartRate record:
    fulcra get-records HeartRate latest
    """

    # data_type is a list of resolved catalog entries (see resolve_data_type)
    if user_id and group_id:
        raise click.UsageError("--user-id cannot be used with --group-id")
    source = resolve_data_source(fulcra_api, group_id, participant_id)

    results = []
    for dt in data_type:
        try:
            results += records.get_records(
                source, dt, start_time, end_time, latest=latest
            )
        except ValueError as exc:
            raise click.ClickException(str(exc))

    for x in results:
        click.echo(json.dumps(x))


@click.command(
    "catalog", short_help="Return a list of queryable Fulcra data types and metadata"
)
@click.option("-d", "--data-type", type=str, help="Data Type to look up by ID.")
@click.option("-n", "--name", type=str, help="Filter results by partial name.")
@click.option(
    "--base-types-only",
    "--base-types",
    help="Only return base types that can be used with data-type create",
    is_flag=True,
    default=False,
)
@click.option(
    "--recordable-only",
    "--recordable",
    is_flag=True,
    default=False,
    help="Only show recordable data types.",
)
@click.option(
    "--queryable-only",
    "--queryable",
    is_flag=True,
    default=False,
    help="Only show queryable data types.",
)
@click.option("-c", "--category", type=str, help="Filter by category.")
@click.option(
    "--api-version",
    type=str,
    help="Filter by API version. When used with --data-type, fetches specific version including schema.",
)
@click.option(
    "--user-id",
    type=str,
    default=None,
    help="Fulcra user ID of which data types to fetch.",
)
@pass_fulcra_api
@requires_auth
def catalog(
    fulcra_api: FulcraAPI,
    base_types_only: bool,
    recordable_only: bool,
    queryable_only: bool,
    data_type: str | None = None,
    name: str | None = None,
    category: str | None = None,
    api_version: str | None = None,
    user_id: str | None = None,
):
    """
    Return a list of Fulcra Data Types that can be queried with `get-records`, `metric-time-series`, and other commands.

    The `related_cli_commands` property contains a list of CLI sub-commands that can be used with a given data type.
    """

    try:
        # If data_type, api_version, and user_id are specified, use the specific endpoint
        if data_type and api_version and user_id:
            catalog_entry = fulcra_api.v1_catalog_data_type(
                data_type=data_type, api_version=api_version, fulcra_userid=user_id
            )
            response = [catalog_entry]
        else:
            if base_types_only:
                catalog_category = "base_type"
            elif category:
                catalog_category = category
            else:
                catalog_category = None

            response = fulcra_api.v1_catalog(
                data_type=data_type, category=catalog_category, fulcra_userid=user_id
            )

            # Filter by api_version if provided
            if api_version:
                response = [c for c in response if c.get("api_version") == api_version]

            # Filter by category if provided
            if category:
                response = [c for c in response if category in c.get("categories", [])]
    except HTTPError as exc:
        if exc.code == 404:
            raise click.ClickException("Type not found")
        else:
            raise click.ClickException(exc) from exc

    if name:
        response = [c for c in response if name.lower() in c.get("name", "").lower()]

    if recordable_only:
        # TODO: Remove api_version filter once v0 type recording is supported via /ingest/v1/record
        # Currently, the ingest endpoint rejects v0 types with "Can not use this endpoint to record v0 data types"
        response = [
            c
            for c in response
            if c.get("recordable", False) and c.get("api_version") != "v0"
        ]

    if queryable_only:
        response = [c for c in response if c.get("queryable", True)]

    for c in response:
        c["related_cli_commands"] = related_cli_commands(c)
        click.echo(json.dumps(c))


@click.command(
    "user-info", short_help="Return information about the authenticated user"
)
@pass_fulcra_api
@requires_auth
def user_info(fulcra_api: FulcraAPI):
    """Return user information object for authenticated user"""
    try:
        resp = fulcra_api.get_user_info()
    except HTTPError as exc:
        raise click.ClickException(exc) from exc

    click.echo(json.dumps(resp))


@click.command(
    "data-updates", short_help="Return data/file updates that occurred during a period"
)
@click.option(
    "--user-id",
    type=str,
    default=None,
    is_eager=True,
    help="Fulcra user ID to query data updates for (requires an active datashare from that user).",
)
@time_range
@pass_fulcra_api
@requires_auth
def data_updates(
    fulcra_api: FulcraAPI, start_time: datetime, end_time: datetime, user_id: str | None
):
    """Return a summary of the data that was updated across TIME_RANGE.

    TIME_RANGE: Two start & end date arguments in ISO8601 format or a single interval argument relative to the current time ("1 week", "2 days", "3h", etc.)

    The result contains the data types that had records processed (along with
    the number of records processed for each) and any uploaded files that changed.
    """
    try:
        resp = fulcra_api.data_updates(
            start_time=start_time, end_time=end_time, fulcra_userid=user_id
        )
    except HTTPError as exc:
        raise click.ClickException(exc) from exc

    click.echo(
        json.dumps({"start_time": str(start_time), "end_time": str(end_time), **resp})
    )
