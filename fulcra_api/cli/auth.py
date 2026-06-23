import webbrowser
import json

import click

from .utils import requires_auth, save_creds


@click.group(help="Authentication sub-commands")
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


@auth.command("start-login", short_help="Authenticate to Fulcra")
@click.pass_context
def start_login(ctx):
    """Gets a URL, code, and device code to authenticate to the Fulcra platform.

    Starts the OAuth Device Authorization Flow isused to authenticate a user to the Fulcra Life API. Returns a JSON object containing a URL the user can open in their browser, a code they should verify when authenticating, and device code that can be used with `fulcra auth finish-login` to complete the CLI authentication once the user has finished the browser flow.
    """

    try:
        device_code, uri, code = ctx.obj.oidc.get_device_code()
    except Exception as exc:
        print(exc)
        raise click.ClickException("Authorization failed, try again.") from exc

    click.echo(json.dumps({
        "url": uri,
        "code": code,
        "device_code": device_code,
    }))

@auth.command("finish-login", short_help="Authenticate to Fulcra")
@click.argument("device-code", type=str)
@click.pass_context
def finish_login(ctx, device_code: str):
    """Completes authentication to the Fulcra platform.

    Completes the OAuth Device Authorization Flow isused to authenticate a user to the Fulcra Life API, started by the `fulcra auth start-login` command. The user must complete the browser authentication flow before running this command.

    Credentials are persisted on the filesystem at ~/.config/fulcra/credentials.json
    """

    try:
        creds = ctx.obj.oidc.get_token(
            "urn:ietf:params:oauth:grant-type:device_code",
            {"device_code": device_code},
        )
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
