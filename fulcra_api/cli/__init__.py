import sys
from typing import Any, Dict

import click

from ..core import FulcraAPI
from ..credentials import FulcraCredentials
from ..oidc import FulcraAuthError, FulcraReauthRequired
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
from .connection import connection
from .data_types import data_type
from .files import file
from .groups import group
from .record import delete_records, record
from .share import share
from .tags import tag
from .utils import (
    CREDS_STORE,
    ensure_config_directory,
    load_creds,
    pass_fulcra_api,
    tolerate_unencodable_output,
)

# Exit codes for a failed token refresh, so a script or scheduler can tell
# "log in again" from "try again later" without parsing the message.
EXIT_REAUTH_REQUIRED = 3
EXIT_AUTH_UNAVAILABLE = 4


class AuthFailure(click.ClickException):
    def __init__(self, exc: FulcraAuthError):
        if isinstance(exc, FulcraReauthRequired):
            message = (
                f"Your Fulcra login has expired or been revoked ({exc}). "
                "Run `fulcra auth login` to log in again."
            )
            self.exit_code = EXIT_REAUTH_REQUIRED
        else:
            message = (
                f"{exc}. Your login is probably still valid; this is likely "
                "temporary, so try again shortly rather than logging in again."
            )
            self.exit_code = EXIT_AUTH_UNAVAILABLE
        super().__init__(message)


def _auth_failure(exc: BaseException) -> FulcraAuthError | None:
    """The token refresh failure behind `exc`, if any, however it was wrapped."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, FulcraAuthError):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


class FulcraGroup(click.Group):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (click.exceptions.Exit, click.exceptions.Abort):
            raise
        except Exception as exc:
            failure = _auth_failure(exc)
            if failure is None:
                raise
            raise AuthFailure(failure) from exc


@click.group(cls=FulcraGroup)
@click.option("--beta", is_flag=True, default=False, help="Enable beta features")
@click.pass_context
def cli(ctx, beta):
    """Command line interface for authenticating and interacting with the Fulcra Life API.

    Sub-commands return JSON data by default for convienent piping into tools like `jq` for parsing and filtering.
    """
    tolerate_unencodable_output(sys.stdout, sys.stderr)
    ensure_config_directory()
    creds: FulcraCredentials | None = load_creds()
    kwargs: Dict[str, Any] = {"credentials_store": CREDS_STORE}
    if creds:
        kwargs["credentials"] = creds

    ctx.obj = FulcraAPI(**kwargs)


cli.add_command(auth)
cli.add_command(tag)
cli.add_command(data_type)
cli.add_command(connection)
cli.add_command(file)
cli.add_command(share)
cli.add_command(group)
cli.add_command(record)
cli.add_command(delete_records)

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
