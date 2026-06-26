import webbrowser
import sys

import click

from .utils import requires_auth, save_creds


@click.group(help="Authentication sub-commands")
def auth():
    pass


@auth.command(short_help="Authenticate to Fulcra")
@click.option("-u", "--get-auth-url", default=False, is_flag=True, help="Run non-interactively. A web auth URL, web auth verification code, and a device code will be returned. Call `fulcra-api auth login --device-code <DEVICE CODE>` to complete authentication after finishing the web auth flow.")
@click.option("-d", "--device-code", type=str, default=None, help="Finish authentication with a device code after the browser auth flow is completed")
@click.pass_context
def login(ctx, get_auth_url: bool, device_code: str | None):
    """Authenticates to the Fulcra Platform.

    The OAuth Device Authorization Flow isused to authenticate a user to the Fulcra Life API. Run interactively. A URL will be presented to load in browser. A new browser session will be automatically launched on supported platforms, and this command will poll for a valid token from the completion of the flow for up to two minutes.

    Credentials are persisted on the filesystem at ~/.config/fulcra/credentials.json
    """

    if get_auth_url and device_code is not None:
        raise click.ClickException("--get-auth-url and --device-code are mutually exclusive")

    if get_auth_url:
        try:
            device_code, uri, code = ctx.obj.oidc.get_device_code()
        except Exception as exc:
            print(exc)
            raise click.ClickException("Authorization failed, try again.") from exc

        click.echo("Open the web auth URL in a browser, verify the web auth code, and complete the web auth flow.\n")
        click.echo(f"Web auth URL: {uri}")
        click.echo(f"- Web auth code: {code}")
        click.echo(f"- Device code: {device_code}\n")
        click.echo("After finishing the web auth flow, complete authentication with the device code by running:\n")
        click.echo(f"fulcra-api auth login --device-code {device_code}")
        return
    
    if device_code is not None:
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
        return
    
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
