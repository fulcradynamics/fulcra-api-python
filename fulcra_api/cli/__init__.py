from typing import Any, Dict

import click

from ..core import FulcraAPI
from ..credentials import FulcraCredentials
from .auth import auth
from .commands import (
    catalog,
    data_updates,
    get_records,
    google_location_updates,
    apple_location_updates,
    apple_location_visits,
    list_apple_workouts,
    list_calendar_events,
    list_calendars,
    location_at_time,
    location_time_series,
    metric_time_series,
    sleep_cycles,
    sleep_cycles_aggregated,
    sleep_stages,
    user_info,
)
from .data_types import data_type
from .files import file
from .tags import tag
from .utils import ensure_config_directory, load_creds, save_creds


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


cli.add_command(auth)
cli.add_command(tag)
cli.add_command(data_type)
cli.add_command(file)

cli.add_command(list_calendars)
cli.add_command(list_calendar_events)
cli.add_command(list_apple_workouts)
cli.add_command(metric_time_series)
cli.add_command(google_location_updates)
cli.add_command(apple_location_updates)
cli.add_command(apple_location_visits)
cli.add_command(location_time_series)
cli.add_command(location_at_time)
cli.add_command(sleep_stages)
cli.add_command(sleep_cycles)
cli.add_command(sleep_cycles_aggregated)
cli.add_command(get_records)
cli.add_command(catalog)
cli.add_command(user_info)
cli.add_command(data_updates)
