"""OIDC mechanics for authenticating with the Fulcra API"""

import datetime
import json
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from .credentials import FulcraCredentials, jwt_expiration

# Seconds to wait for Auth0 before giving up on a request.
TOKEN_REQUEST_TIMEOUT = 30

# Attempts at a refresh that fails for a reason worth retrying, and the delay
# before the first retry (doubled each time).
REFRESH_ATTEMPTS = 3
REFRESH_RETRY_DELAY = 2.0


class FulcraAuthError(Exception):
    """The access token could not be refreshed."""


class FulcraReauthRequired(FulcraAuthError):
    """
    Auth0 rejected the refresh token (revoked, expired, or reused), so the
    user has to log in again.
    """


class FulcraAuthUnavailable(FulcraAuthError):
    """
    Auth0 couldn't be reached or failed (network error, timeout, 429, 5xx).
    The credentials are probably still good; try again later.
    """


@dataclass
class FulcraOIDCProvider:
    domain: str
    client_id: str
    scope: str
    audience: str

    def authorize_via_device_flow(
        self,
        prompt_callback: Optional[Callable] = None,
    ) -> FulcraCredentials:
        """Get a device code, prompt the user via a callback, then poll for a valid token"""

        device_code, uri, code, timeout, interval = self.get_device_code()

        poll_timeout = datetime.timedelta(seconds=timeout)
        poll_interval = datetime.timedelta(seconds=interval)

        if prompt_callback is not None:
            prompt_callback(device_code, uri, code)

        return self.poll_for_token(
            device_code=device_code,
            poll_timeout=poll_timeout,
            poll_interval=poll_interval,
        )

    def poll_for_token(
        self,
        device_code: str,
        poll_timeout: datetime.timedelta = datetime.timedelta(seconds=900),
        poll_interval: datetime.timedelta = datetime.timedelta(seconds=5),
    ) -> FulcraCredentials:
        end_at = datetime.datetime.now() + poll_timeout
        creds = None
        while True:
            try:
                creds = self.get_token(
                    "urn:ietf:params:oauth:grant-type:device_code",
                    {"device_code": device_code},
                )
                break
            except HTTPError as e:
                body = json.loads(e.fp.read())

                if e.status == 403 and body.get('error') == "authorization_pending":
                    if datetime.datetime.now() > end_at:
                        raise Exception("Polling timeout")

                    time.sleep(poll_interval.total_seconds())
                    continue

                if e.status == 403 and body.get('error') == "expired_token":
                    raise Exception(body.get('error_description'))

                if e.status == 403 and body.get('error') == 'access_denied':
                    raise Exception("User cancelled request")

                if e.status == 429:
                    if datetime.datetime.now() > end_at:
                        raise Exception("Polling timeout")

                    poll_interval += poll_interval
                    time.sleep(poll_interval.total_seconds())
                    continue

                raise e

            except Exception as e:
                raise e

        return creds

    def authorize_via_authorization_code_flow(
        self,
        code: str,
        redirect_uri: str,
    ) -> FulcraCredentials:
        """Exchange an authorization code for credentials, then fire an optional callback"""
        creds = self.get_token(
            "authorization_code",
            {"code": code, "redirect_uri": redirect_uri},
        )
        return creds

    def make_authorization_code_url(
        self, redirect_uri: str, state: Optional[str] = None
    ) -> str:
        params = {
            "client_id": self.client_id,
            "audience": self.audience,
            "scope": self.scope,
            "response_type": "code",
            "redirect_uri": redirect_uri,
        }
        if state:
            params["state"] = state

        return f"https://{self.domain}/authorize?{urllib.parse.urlencode(params)}"

    def get_device_code(self) -> Tuple[str, str, str, int, int]:
        """requests a device code and complete verification URI from auth0"""

        body = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "audience": self.audience,
                "scope": self.scope,
            }
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        request = urllib.request.Request(
            f"https://{self.domain}/oauth/device/code",
            data=body.encode("UTF-8"),
            headers=headers,
            method="POST",
        )
        response = urllib.request.urlopen(request, timeout=TOKEN_REQUEST_TIMEOUT)

        if response.status != 200:
            raise Exception(f"could not get device code: {response}")
        bdata = response.read()
        data = json.loads(bdata)

        r = (data["device_code"], data["verification_uri_complete"], data["user_code"], data['expires_in'], data['interval'])

        return r

    def get_token(self, grant_type: str, payload: dict) -> FulcraCredentials:
        """fetch a token from /oauth/token and return credentials"""

        payload = {
            "client_id": self.client_id,
            "grant_type": grant_type,
        } | payload
        body = urllib.parse.urlencode(payload)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        request = urllib.request.Request(
            f"https://{self.domain}/oauth/token",
            data=body.encode("UTF-8"),
            headers=headers,
            method="POST",
        )
        response = urllib.request.urlopen(request, timeout=TOKEN_REQUEST_TIMEOUT)
        body = json.loads(response.read())

        if "access_token" not in body:
            raise Exception("Got invalid response when requesting token")

        access_token = body["access_token"]
        expires_in = jwt_expiration(access_token) or datetime.datetime.now(
            datetime.timezone.utc
        ) + datetime.timedelta(seconds=float(body["expires_in"]))

        refresh_token = body.get("refresh_token")
        id_token = body.get("id_token")

        return FulcraCredentials(
            access_token=access_token,
            access_token_expiration=expires_in,
            refresh_token=refresh_token,
            id_token=id_token,
        )

    def refresh_credentials(self, credentials: FulcraCredentials) -> FulcraCredentials:
        """
        Exchange the refresh token for new credentials, retrying failures
        that are likely to be temporary.

        Raises:
            FulcraReauthRequired: Auth0 rejected the refresh token.
            FulcraAuthUnavailable: Auth0 couldn't be reached or kept failing.
        """

        if credentials.refresh_token is None:
            raise Exception("No refresh token available to refresh credentials with")

        payload = {"refresh_token": credentials.refresh_token, "scope": self.scope}

        delay = REFRESH_RETRY_DELAY
        for attempt in range(REFRESH_ATTEMPTS):
            try:
                return self.get_token("refresh_token", payload)
            except HTTPError as exc:
                if 400 <= exc.code < 500 and exc.code not in (408, 429):
                    raise FulcraReauthRequired(_token_error(exc)) from exc
                error: Exception = exc
            except Exception as exc:
                # URLError, timeouts, and malformed responses
                error = exc
            if attempt + 1 < REFRESH_ATTEMPTS:
                time.sleep(delay)
                delay *= 2
        raise FulcraAuthUnavailable(
            f"could not reach the Fulcra login service to refresh the access token: {error}"
        ) from error


def _token_error(exc: HTTPError) -> str:
    """The OAuth error from a failed /oauth/token response, e.g. "invalid_grant: ..." """
    try:
        body = json.loads(exc.read())
        return ": ".join(
            str(part)
            for part in (body.get("error"), body.get("error_description"))
            if part
        ) or str(exc)
    except Exception:
        return str(exc)
