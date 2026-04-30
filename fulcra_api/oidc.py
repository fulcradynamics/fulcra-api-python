"""OIDC mechanics for authenticating with the Fulcra API"""

import datetime
import http.client
import json
import time
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from .credentials import FulcraCredentials


@dataclass
class FulcraOIDCProvider:
    domain: str
    client_id: str
    scope: str
    audience: str

    def _get_auth_connection(self, domain: str) -> http.client.HTTPSConnection:
        return http.client.HTTPSConnection(domain)

    def authorize_via_device_flow(
        self,
        poll_timeout: datetime.timedelta = datetime.timedelta(seconds=120),
        poll_interval: datetime.timedelta = datetime.timedelta(seconds=0.5),
        prompt_callback: Optional[Callable] = None,
    ) -> FulcraCredentials:
        """Get a device code, prompt the user via a callback, then poll for a valid token"""

        device_code, uri, code = self.get_device_code()

        if prompt_callback is not None:
            prompt_callback(device_code, uri, code)

        end_at = datetime.datetime.now() + poll_timeout
        creds = None
        while datetime.datetime.now() < end_at:
            time.sleep(poll_interval.seconds)
            try:
                creds = self.get_token(
                    "urn:ietf:params:oauth:grant-type:device_code",
                    {"device_code": device_code},
                )
                break
            except Exception:
                continue

        if creds is None:
            raise Exception("Authorization failed")

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

    def get_device_code(self) -> Tuple[str, str, str]:
        """requests a device code and complete verification URI from auth0"""
        conn = self._get_auth_connection(self.domain)
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
        conn.request("POST", "/oauth/device/code", body, headers)
        response = conn.getresponse()
        if response.status != 200:
            raise Exception(f"could not get device code: {response}")
        bdata = response.read()
        data = json.loads(bdata)

        r = (data["device_code"], data["verification_uri_complete"], data["user_code"])

        return r

    def get_token(self, grant_type: str, payload: dict) -> FulcraCredentials:
        """fetch a token from /oauth/token and return credentials"""

        conn = self._get_auth_connection(self.domain)
        payload = {
            "client_id": self.client_id,
            "grant_type": grant_type,
        } | payload
        body = urllib.parse.urlencode(payload)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        conn.request("POST", "/oauth/token", body, headers)
        response = conn.getresponse()
        if response.status != 200:
            raise Exception(
                f"Got non-200 response when requesting token: {response.status}"
            )

        data = json.loads(response.read())
        if "access_token" not in data:
            raise Exception("Got invalid response when requesting token")

        access_token = data["access_token"]
        expires_in = datetime.datetime.now() + datetime.timedelta(
            seconds=float(data["expires_in"])
        )
        refresh_token = data.get("refresh_token")

        return FulcraCredentials(
            access_token=access_token,
            access_token_expiration=expires_in,
            refresh_token=refresh_token,
        )

    def refresh_credentials(self, credentials: FulcraCredentials) -> FulcraCredentials:

        if credentials.refresh_token is None:
            raise Exception("No refresh token available to refresh credentials with")

        payload = {"refresh_token": credentials.refresh_token, "scope": self.scope}

        return self.get_token("refresh_token", payload)
