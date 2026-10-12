import datetime
import sys
import webbrowser

import click

from fulcra_api.core import FulcraAPI

from .utils import error_message, pass_fulcra_api, requires_auth, save_creds


@click.group(help="Authentication sub-commands")
def auth():
    pass


def _attended() -> bool:
    """Whether a person is at a terminal running this command.

    An agent's shell tool, a pipe or a script gives the command no terminal,
    and usually shows its output only once the command exits.  A login that
    waits for approval then hides the link from the person who must open it
    until the code has expired.
    """
    return sys.stdin.isatty() and sys.stdout.isatty()


def _print_auth_url(
    device_code: str, uri: str, code: str, timeout, interval, unattended: bool
):
    """Print the link and code, and how to finish logging in with the device code."""
    click.echo(
        "Open the web auth URL in a browser, verify the web auth code, and complete the web auth flow.\n"
    )
    click.echo(f"Web auth URL: {uri}")
    click.echo(f"- Web auth code: {code}")
    click.echo(f"- Device code: {device_code}\n")
    if unattended:
        click.echo(
            "NOTE FOR AI AGENTS AND SCRIPTS: a person must open the link above and approve it.\n"
            "Show them the link and code now, in your reply to them. Then finish logging in by running\n"
            "the command below, which waits until they have approved it.\n"
        )
    else:
        click.echo(
            "After finishing the web auth flow, complete authentication with the device code by running:\n"
        )
    click.echo(
        f"fulcra-api auth login --device-code {device_code} --poll-timeout {timeout} --poll-interval {interval}"
    )
    if unattended:
        click.echo(
            "\nIf the code expires first, run `fulcra-api auth login` again for a new one."
            "\n(To wait for approval in this command instead, add --wait.)"
        )


@auth.command(short_help="Authenticate to Fulcra")
@click.option(
    "-u",
    "--get-auth-url",
    default=False,
    is_flag=True,
    help="Run non-interactively. A web auth URL, web auth verification code, and a device code will be returned. Call `fulcra-api auth login --device-code <DEVICE CODE>` to complete authentication after finishing the web auth flow. This is the default when the command isn't run at a terminal.",
)
@click.option(
    "-w",
    "--wait",
    default=False,
    is_flag=True,
    help="Show the link and wait for approval in this command, even when it isn't run at a terminal.",
)
@click.option(
    "-d",
    "--device-code",
    type=str,
    default=None,
    help="Finish authentication with a device code after the browser auth flow is completed",
)
@click.option(
    "-p",
    "--poll-timeout",
    type=click.FloatRange(min=0),
    default=900,
    help="Number of seconds to poll while waiting for the web auth flow to be completed. Use with --device-code.",
)
@click.option(
    "-i",
    "--poll-interval",
    type=click.FloatRange(min=5),
    default=5,
    help="Number of seconds between polling attempts. Use with --device-code.",
)
@pass_fulcra_api
def login(
    fulcra_api: FulcraAPI,
    get_auth_url: bool,
    wait: bool,
    device_code: str | None,
    poll_timeout: float,
    poll_interval: float,
):
    """Authenticates to the Fulcra Platform.

    Uses the OAuth Device Authorization Flow: a person opens a link in a browser and approves the login.

    \b
    At a terminal, this opens the browser, shows the link and code, and waits
    for approval.

    \b
    When it isn't run at a terminal (an AI agent's shell, a pipe, a script),
    it prints the link, the code and a device code, then exits at once, as
    --get-auth-url does. Show the person the link and code, then finish with
    `fulcra-api auth login --device-code <DEVICE CODE>`, which waits for their
    approval. --wait keeps the waiting behavior instead.

    Credentials are persisted on the filesystem at ~/.config/fulcra/credentials.json
    """

    if get_auth_url and device_code is not None:
        raise click.ClickException(
            "--get-auth-url and --device-code are mutually exclusive"
        )
    if wait and (get_auth_url or device_code is not None):
        raise click.ClickException(
            "--wait can't be combined with --get-auth-url or --device-code"
        )

    unattended = (
        not wait and not get_auth_url and device_code is None and not _attended()
    )
    if get_auth_url or unattended:
        try:
            device_code, uri, code, timeout, interval = fulcra_api.oidc.get_device_code()
        except Exception as exc:
            print(exc)
            raise click.ClickException("Authorization failed, try again.") from exc

        _print_auth_url(device_code, uri, code, timeout, interval, unattended)
        return

    if device_code is not None:
        try:
            creds = fulcra_api.oidc.poll_for_token(
                device_code=device_code,
                poll_timeout=datetime.timedelta(seconds=poll_timeout),
                poll_interval=datetime.timedelta(seconds=poll_interval),
            )

        except Exception as exc:
            raise click.ClickException(
                f"Authorization failed, try again: {error_message(exc)}"
            ) from exc

        click.echo("✅ Authorization successful!")

        save_creds(creds)
        return

    def prompt(device_code: str, uri: str, code: str):
        webbrowser.open_new_tab(uri)
        click.echo(
            f"✨ Use your browser to log into Fulcra. If your browser does not automatically open, visit this URL: {uri}"
        )
        click.echo(
            f"❗ Ensure the following code matches what's displayed in your browser: {code}"
        )
        click.echo(
            "(AI agents: show this link and code to the person now, and keep this command running.)"
        )

    try:
        creds = fulcra_api.oidc.authorize_via_device_flow(
            prompt_callback=prompt
        )
    except Exception as exc:
        raise click.ClickException(
            f"Authorization failed, try again: {error_message(exc)}"
        ) from exc

    click.echo("✅ Authorization successful!")

    save_creds(creds)


@auth.command("print-access-token", short_help="Print Fulcra oauth2 access token")
@pass_fulcra_api
@requires_auth
def get_access_token(fulcra_api: FulcraAPI):
    """Print a OAuth2 bearer token for use with accessing the Fulcra Life API.

    This is useful for making direct calls to the Fulcra Life API.

    \b
    EXAMPLE:
        curl --oauth2-bearer "$(fulcra auth print-access-token)" 'https://api.fulcradynamics.com/user/v1alpha1/info'
    """
    if fulcra_api.fulcra_credentials.is_expired():
        fulcra_api.refresh_access_token()
    click.echo(fulcra_api.fulcra_credentials.access_token)
