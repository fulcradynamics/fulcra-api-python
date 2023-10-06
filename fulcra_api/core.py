import http.client
import urllib.parse
import json
import base64
import datetime
import time
import pandas as pd
from typing import List, Tuple, Dict, Optional
import io
import webbrowser

try:
    from IPython.display import HTML, display

    is_notebook = True
except ImportError:  # ugly
    is_notebook = False
    pass

FULCRA_AUTH0_DOMAIN = "fulcra.us.auth0.com"
FULCRA_AUTH0_CLIENT_ID = "48p3VbMnr5kMuJAUe9gJ9vjmdWLdnqZt"
FULCRA_AUTH0_AUDIENCE = "https://api.fulcradynamics.com/"
FULCRA_AUTH0_SCOPE = "openid profile name email offline_access"


class FulcraAPI:
    """
    The client class for calling Fulcra Data Service API functions.
    """

    fulcra_cached_access_token = None
    fulcra_cached_access_token_expiration = None

    def get_auth_connection(self, domain: str) -> http.client.HTTPSConnection:
        """
        Returns an https connection to the given server.
        """
        return http.client.HTTPSConnection(domain)

    def request_device_code(
        self, domain: str, client_id: str, scope: str, audience: str
    ) -> Tuple[str, str, str]:
        """
        Requests a device code and complete verification URI from auth0.
        """
        conn = self.get_auth_connection(domain)
        body = urllib.parse.urlencode(
            {"client_id": client_id, "audience": audience, "scope": scope}
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
        return (
            data["device_code"],
            data["verification_uri_complete"],
            data["user_code"],
        )

    def get_token(self, device_code: str) -> Tuple[str, datetime.datetime]:
        conn = self.get_auth_connection(FULCRA_AUTH0_DOMAIN)
        body = urllib.parse.urlencode(
            {
                "client_id": FULCRA_AUTH0_CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            }
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        conn.request("POST", "/oauth/token", body, headers)
        response = conn.getresponse()
        if response.status != 200:
            return (None, None)
        data = json.loads(response.read())
        if "access_token" not in data:
            return (None, None)
        expires_in = datetime.datetime.now() + datetime.timedelta(
            seconds=float(data["expires_in"])
        )
        return (data["access_token"], expires_in)

    def authorize(self):
        """
        Request a device token, then prompt the user to authorize it.

        This uses the Device Authorization workflow, which requires the user
        to visit a link and confirm that the code shown on the screen matches.

        Raises an exception on failure.
        """
        if (
            self.fulcra_cached_access_token is not None
            and self.fulcra_cached_access_token_expiration is not None
            and self.fulcra_cached_access_token_expiration > datetime.datetime.now()
        ):
            if is_notebook:
                display(HTML("<p>Your access token is still valid.</p>"))
            else:
                print("Your access token is still valid.")
            return self.fulcra_cached_access_token
        device_code, uri, code = self.request_device_code(
            FULCRA_AUTH0_DOMAIN,
            FULCRA_AUTH0_CLIENT_ID,
            FULCRA_AUTH0_SCOPE,
            FULCRA_AUTH0_AUDIENCE,
        )
        webbrowser.open_new_tab(uri)
        if is_notebook:
            display(
                HTML(
                    f'<a href="{uri}" target="_blank">'
                    + "Use your browser to log in to Fulcra.  If "
                    + " the tab does not open automatically, click here to "
                    + "log in to Fulcra.</a>  The code displayed will "
                    + f"be: <b>{code}</b><p>After you have authorized, "
                    + "close the browser tab.</p>"
                )
            )
        else:
            print(
                f"""
            Use your browser to log in to Fulcra.  If the tab does not open
            automatically, visit this URL to authenticate: {uri}
            """
            )
        stop_at = datetime.datetime.now() + datetime.timedelta(seconds=120)
        while datetime.datetime.now() < stop_at:
            time.sleep(0.5)
            token, expiration_date = self.get_token(device_code)
            if token is not None:
                if is_notebook:
                    display(HTML("Authorization succeeded."))
                else:
                    print("Authorization succeeded.")
                self.fulcra_cached_access_token = token
                self.fulcra_cached_access_token_expiration = expiration_date
                return
        self.fulcra_cached_access_token = None
        self.fulcra_cached_access_token_expiration = None
        raise Exception("Authorization failed.  Re-run these cells.")

    def fulcra_api(self, access_token: str, url_path: str) -> bytes:
        """
        Make a call to the given url path (e.g. `/v0/data/time_series_grouped?...`)
        with the specified access token.

        Returns the raw response data (as bytes).  Raises an exception on failure.
        """
        conn = http.client.HTTPSConnection("api.fulcradynamics.com")
        headers = {"Authorization": f"Bearer {access_token}"}
        conn.request("GET", url_path, headers=headers)
        response = conn.getresponse()
        if response.status != 200:
            raise Exception(f"request failed: {response.read()}")
        return response.read()

    def get_fulcra_userid(self) -> str:
        """
        Returns the Fulcra UserID of the currently-authorized user.
        """
        if self.fulcra_cached_access_token is None:
            raise Exception("Authorization must occur before retrieving user ID.")
        segs = self.fulcra_cached_access_token.split(".")
        if len(segs) < 2:
            raise Exception("Authorized token is in an incorrect format.")
        jd = json.loads(base64.b64decode(segs[1]))
        return jd["fulcradynamics.com/userid"]

    def time_series_grouped(
        self,
        start_time: str,
        end_time: str,
        metrics: List[str],
        sample_rate: float = 60,
    ):
        """
        Retrieve a time-series data frame containing the specified set of
        Fulcra metrics from `start_time` (inclusive) until `end_time` (exclusive).

        If specified, the `sample_rate` parameter defines the number of
        seconds per sample.  This value can be smaller than 1.  The default
        value is 60 (one sample per minute).

        When specified as strings, `start_time` and `end_time` must be in ISO8601
        format.

        Requires a valid access token.
        """
        qparams = urllib.parse.urlencode(
            {
                "start_time": start_time,
                "end_time": end_time,
                "metrics": metrics,
                "output": "arrow",
                "samprate": sample_rate,
            },
            doseq=True,
        )
        resp = self.fulcra_api(
            self.fulcra_cached_access_token, "/data/v0/time_series_grouped?" + qparams
        )
        return pd.read_feather(io.BytesIO(resp)).set_index("time")

    def calendars(self) -> List[Dict]:
        """
        Retrieve the list of calendars available in your data store.

        Requires an authorized access token.
        """
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/calendars",
        )
        return json.loads(resp)


    def calendar_events(
        self, start_time: str, end_time: str, calendar_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Retrieve the list of calendar events that occur (at least partially) during the
        time range described by `start_time` (inclusive) to `end_time` (exclusive).

        If included, the `calendar_ids` parameter limits the query to the specified
        calendar IDs.

        Requires an authorized access token.
        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
        }
        if calendar_ids is not None:
            params["calendar_ids"] = calendar_ids
        qparams = urllib.parse.urlencode(params, doseq=True)
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/calendar_events?{qparams}",
        )
        return json.loads(resp)

    def apple_workouts(self, start_time: str, end_time: str) -> List[Dict]:
        """
        Retrieve the list of Apple workouts that occurred (at least partially) during
        the time range described by `start_time` (inclusive) to `end_time` (exclusive).

        Requires an authorized access token.
        """
        params = {"start_time": start_time, "end_time": end_time}
        qparams = urllib.parse.urlencode(params, doseq=True)
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/apple_workouts?{qparams}",
        )
        return json.loads(resp)

    def simple_events(
        self, start_time: str, end_time: str, categories: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Retrieve the events that occurred during the specified period of time,
        optionally filtering by categories.

        If included, the `categories` parameter only includes events from the specified
        categories.

        Requires an authorized access token.
        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
        }
        if categories is not None:
            params["categories"] = categories
        qparams = urllib.parse.urlencode(params, doseq=True)
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/simple_events?{qparams}",
        )
        return json.loads(resp)

    def metric_samples(
        self, start_time: str, end_time: str, metric: str
    ) -> List[Dict]:
        """
        Retrieve the raw samples related to the given metric that occurred for the
        user during the specified period of time.

        In cases where samples cover ranges and not points in time, a sample will
        be returned if any part of its range intersects with the requested range.

        As an example, if you have `start_date` as 14:00 and `end_date` at 15:00,
        and there is a sample that covers 13:30-14:30, it will be included.

        Requires an authorized access token.
        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "metric": metric
        }
        qparams = urllib.parse.urlencode(params, doseq=True)
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/metric_samples?{qparams}",
        )
        return json.loads(resp)

    def apple_location_updates(
        self, start_time: str, end_time: str
    ) -> List[Dict]:
        """
        Retrieve the raw Apple location update samples for the specified
        user during the specified period of time.

        Requires an authorized access token.
        """
        params = {
            "start_time": start_time,
            "end_time": end_time
        }
        qparams = urllib.parse.urlencode(params, doseq=True)
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/apple_location_updates?{qparams}",
        )
        return json.loads(resp)


    def apple_location_visits(
        self, start_time: str, end_time: str
    ) -> List[Dict]:
        """
        Retrieve the raw Apple location visit samples for the specified
        user during the specified period of time.

        Requires an authorized access token.
        """
        params = {
            "start_time": start_time,
            "end_time": end_time
        }
        qparams = urllib.parse.urlencode(params, doseq=True)
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/apple_location_visits?{qparams}",
        )
        return json.loads(resp)



