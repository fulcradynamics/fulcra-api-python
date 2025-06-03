import http.client
import urllib.parse
import json
import base64
import datetime
import time
import pandas as pd
from typing import List, Tuple, Dict, Optional, Union
import io
import webbrowser

try:
    from IPython.display import HTML, display

    is_notebook = True
except ImportError:  # ugly
    is_notebook = False
    pass

FULCRA_OIDC_DOMAIN = "fulcra.us.auth0.com"
FULCRA_OIDC_CLIENT_ID = "48p3VbMnr5kMuJAUe9gJ9vjmdWLdnqZt"
FULCRA_OIDC_AUDIENCE = "https://api.fulcradynamics.com/" # Typically, the API audience URL
FULCRA_OIDC_SCOPE = "openid profile name email offline_access"


class FulcraAPI:
    """
    The main class for making Fulcra API functions.

    This contains functions for authorizing a token, authenticating HTTP requests,
    making calls, and loading data.
    """

    fulcra_cached_access_token = None
    fulcra_cached_access_token_expiration = None
    fulcra_cached_refresh_token = None

    def __init__(
        self,
        oidc_domain: Optional[str] = None,
        oidc_client_id: Optional[str] = None,
        oidc_scope: Optional[str] = None,
        oidc_audience: Optional[str] = None,
    ):
        """
        Initializes the FulcraAPI client.

        Params:
            oidc_domain: Optional. The OIDC provider domain to use for authentication.
                         Defaults to FULCRA_OIDC_DOMAIN.
            oidc_client_id: Optional. The OIDC client ID to use.
                            Defaults to FULCRA_OIDC_CLIENT_ID.
            oidc_scope: Optional. The OAuth scopes to request.
                        Defaults to FULCRA_OIDC_SCOPE.
            oidc_audience: Optional. The OIDC audience for the token.
                           Defaults to FULCRA_OIDC_AUDIENCE.
        """
        self.oidc_domain = oidc_domain or FULCRA_OIDC_DOMAIN
        self.oidc_client_id = oidc_client_id or FULCRA_OIDC_CLIENT_ID
        self.oidc_scope = oidc_scope or FULCRA_OIDC_SCOPE
        self.oidc_audience = oidc_audience or FULCRA_OIDC_AUDIENCE

    def _get_auth_connection(self, domain: str) -> http.client.HTTPSConnection:
        """
        Opens an https connection to the given server.

        Params:
            domain: The domain name to connect to

        Returns:
            an open `HTTPSConnection` to the server.
        """
        return http.client.HTTPSConnection(domain)

    def _request_device_code(
        self, domain: str, client_id: str, scope: str, audience: str
    ) -> Tuple[str, str, str]:
        """
        Requests a device code and complete verification URI from auth0.
        """
        conn = self._get_auth_connection(domain)
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

    def _fetch_token_from_auth_server(
        self, payload: Dict
    ) -> Tuple[Optional[str], Optional[datetime.datetime], Optional[str]]:
        """
        Internal helper to fetch tokens from the OIDC provider's /oauth/token endpoint.
        """
        conn = self._get_auth_connection(self.oidc_domain)
        body = urllib.parse.urlencode(payload)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        conn.request("POST", "/oauth/token", body, headers)
        response = conn.getresponse()
        if response.status != 200:
            return (None, None, None)
        data = json.loads(response.read())
        if "access_token" not in data:
            return (None, None, None)
        
        access_token = data["access_token"]
        expires_in = datetime.datetime.now() + datetime.timedelta(
            seconds=float(data["expires_in"])
        )
        refresh_token = data.get("refresh_token")

        return (access_token, expires_in, refresh_token)

    def get_token(
        self, device_code: str
    ) -> Tuple[Optional[str], Optional[datetime.datetime]]:
        """
        Polls for an access token using a device code.
        Used by the device authorization flow.
        """
        payload = {
            "client_id": self.oidc_client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        }
        access_token, expiration_date, _ = self._fetch_token_from_auth_server(payload)
        return access_token, expiration_date

    def authorize(self):
        """
        Request a device token, then prompt the user to authorize it.

        This uses the Device Authorization workflow, which requires the user
        to visit a link and confirm that the code shown on the screen matches.

        This function will attempt to open the link in a new browwser tab (using
        `webbrowser` module); it will also be either `print()`ed out (or `display()`ed
        out if run inside Jupyter).

        The function will wait until the user visits the page and authentiactes, or
        until a specified time has passed.

        Raises an exception on failure.

        Examples:

        >>> fulcra.authorize()
        Use your browser to log in to Fulcra.  If the tab does not open
        automatically, visit this URL to authenticate:
        https://fulcra.us.auth0.com/activate?user_code=SJZC-GRBW

        When the authorization succeeds, the following will be displayed:

        ```
        Authorization succeeded.
        ```
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
            return
        device_code, uri, code = self._request_device_code(
            self.oidc_domain,
            self.oidc_client_id,
            self.oidc_scope,
            self.oidc_audience,
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
                self.fulcra_cached_refresh_token = None
                return
        self.fulcra_cached_access_token = None
        self.fulcra_cached_access_token_expiration = None
        self.fulcra_cached_refresh_token = None
        raise Exception("Authorization failed.  Re-run these cells.")

    def get_authorization_code_url(
        self, redirect_uri: str, state: Optional[str] = None
    ) -> str:
        """
        Generates the URL to redirect the user to for the Authorization Code Grant flow.

        The calling application (e.g., a web service) should redirect the user
        to this URL. After the user authenticates and authorizes the application,
        Auth0 will redirect the user back to the specified `redirect_uri` with
        an authorization `code` (and `state` if provided) in the query parameters.

        Params:
            redirect_uri: The URL where the user will be redirected after authorization.
                          This must be registered in your Auth0 application settings.
            state: An opaque value used to maintain state between the request and
                   the callback. It's also used to prevent CSRF attacks.

        Returns:
            The authorization URL.
        """
        params = {
            "client_id": self.oidc_client_id,
            "audience": self.oidc_audience,
            "scope": self.oidc_scope,
            "response_type": "code",
            "redirect_uri": redirect_uri,
        }
        if state:
            params["state"] = state
        
        return f"https://{self.oidc_domain}/authorize?{urllib.parse.urlencode(params)}"

    def authorize_with_authorization_code(self, code: str, redirect_uri: str):
        """
        Exchanges an authorization code for an access token, refresh token,
        and ID token.

        This method should be called after the user has been redirected back
        to your application's `redirect_uri` with an authorization `code`.

        Params:
            code: The authorization code received from Auth0.
            redirect_uri: The same `redirect_uri` that was used when requesting
                          the authorization code.

        Raises:
            Exception: If the token exchange fails.
        """
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.oidc_client_id,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        
        access_token, expiration_date, refresh_token = self._fetch_token_from_auth_server(payload)

        if access_token and expiration_date:
            self.fulcra_cached_access_token = access_token
            self.fulcra_cached_access_token_expiration = expiration_date
            self.fulcra_cached_refresh_token = refresh_token
            if is_notebook:
                display(HTML("Authorization succeeded using authorization code."))
            else:
                print("Authorization succeeded using authorization code.")
        else:
            self.fulcra_cached_access_token = None
            self.fulcra_cached_access_token_expiration = None
            self.fulcra_cached_refresh_token = None
            raise Exception("Failed to exchange authorization code for token.")

    def refresh_access_token(self) -> bool:
        """
        Refreshes the access token using the stored refresh token.

        Returns:
            True if the token was successfully refreshed, False otherwise.
        
        Raises:
            Exception: If no refresh token is available.
        """
        if not self.fulcra_cached_refresh_token:
            raise Exception("No refresh token available to refresh the access token.")

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.oidc_client_id,
            "refresh_token": self.fulcra_cached_refresh_token,
            "scope": self.oidc_scope, # Request same scopes or subset
        }

        access_token, expiration_date, new_refresh_token = self._fetch_token_from_auth_server(payload)

        if access_token and expiration_date:
            self.fulcra_cached_access_token = access_token
            self.fulcra_cached_access_token_expiration = expiration_date
            # Auth0 may return a new refresh token (if refresh token rotation is enabled)
            if new_refresh_token:
                self.fulcra_cached_refresh_token = new_refresh_token
            if is_notebook:
                display(HTML("Access token refreshed successfully."))
            else:
                print("Access token refreshed successfully.")
            return True
        else:
            print("Failed to refresh access token.")
            return False

    def fulcra_api(self, access_token: str, url_path: str) -> bytes:
        """
        Make a call to the given url path (e.g. `/v0/data/time_series_grouped?...`)
        with the specified access token.

        Params:
            access_token: The access token to authenticate the request with
            url_path: The path of the URL to use (e.g. `"/v0/data/..."`)

        Returns:
            The raw response data (as bytes).  Raises an exception on failure.
        """
        conn = http.client.HTTPSConnection("api.fulcradynamics.com")
        headers = {"Authorization": f"Bearer {access_token}"}
        conn.request("GET", url_path, headers=headers)
        response = conn.getresponse()
        if response.status != 200:
            raise Exception(f"request failed: {response.read().decode('utf-8')}")
        return response.read()

    def get_fulcra_userid(self) -> str:
        """
        Retrieve the currently authorized Fulcra UserID.

        Returns:
            the Fulcra UserID of the currently-authorized user.
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
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        metrics: List[str],
        sample_rate: float = 60,
        replace_nulls: Optional[bool] = False,
        fulcra_userid: Optional[str] = None,
    ):
        """
        Retrieve a time-series data frame containing the specified set of
        Fulcra metrics from `start_time` (inclusive) until `end_time` (exclusive).

        If specified, the `sample_rate` parameter defines the number of
        seconds per sample.  This value can be smaller than 1.  The default
        value is 60 (one sample per minute).

        Requires a valid access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object
            metrics: The names of the time-series metrics to include in the result
            sample_rate: The length (in seconds) of each sample
            replace_nulls: When true, replace all NA/null/None values with 0
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            a pandas DataFrame containing the data.  For time ranges where data is
                missing, the values will be `<NA>`.

        Examples:
            To retrieve a dataframe containing four different metrics
            (`DistanceTraveledOnFoot`, `AppleWatchExerciseTime`,
            `ActiveCaloriesBurned`, and `BasalCaloriesBurned`):

            >>> df = fulcra.time_series_grouped(
            ...     start_time = "2023-07-01 04:00:00.000Z",
            ...     end_time = "2023-07-10 04:00:00.000Z",
            ...     metrics=["DistanceTraveledOnFoot",
            ...         "AppleWatchExerciseTime",
            ...         "ActiveCaloriesBurned",
            ...         "BasalCaloriesBurned"
            ...     ]
            ... )

            The index of the DataFrame will be the time:

            >>> df.index
            DatetimeIndex(['2023-07-01 04:00:00+00:00',
                           '2023-07-01 04:01:00+00:00',
                           '2023-07-01 04:02:00+00:00',
                           '2023-07-01 04:03:00+00:00',
                           '2023-07-01 04:04:00+00:00',
                           '2023-07-01 04:05:00+00:00',
                           '2023-07-01 04:06:00+00:00',
                           '2023-07-01 04:07:00+00:00',
                           '2023-07-01 04:08:00+00:00',
                           '2023-07-01 04:09:00+00:00',
                           ...
                           '2023-07-10 03:50:00+00:00',
                           '2023-07-10 03:51:00+00:00',
                           '2023-07-10 03:52:00+00:00',
                           '2023-07-10 03:53:00+00:00',
                           '2023-07-10 03:54:00+00:00',
                           '2023-07-10 03:55:00+00:00',
                           '2023-07-10 03:56:00+00:00',
                           '2023-07-10 03:57:00+00:00',
                           '2023-07-10 03:58:00+00:00',
                        '2023-07-10 03:59:00+00:00'],
                          dtype='datetime64[ns, UTC]', name='time', length=12960,
                            freq=None)

            Each metric requested will add at least one column to the dataframe:

            >>> df.columns
            Index(['distance_on_foot', 'apple_watch_exercise_time',
                   'active_calories_burned', 'basal_calories_burned'],
                    dtype='object')

        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "metrics": metrics,
            "output": "arrow",
            "samprate": sample_rate,
            "replace_nulls": int(replace_nulls == True),
        }
        if fulcra_userid is not None:
            params["fulcra_userid"] = fulcra_userid
        qparams = urllib.parse.urlencode(params, doseq=True)
        resp = self.fulcra_api(
            self.fulcra_cached_access_token, "/data/v0/time_series_grouped?" + qparams
        )
        return pd.read_feather(io.BytesIO(resp)).set_index("time")

    def calendars(
        self,
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve the list of calendars available in your data store.

        To request the calendars from another user's store, pass their user
        ID as the `fulcra_userid` parameter.

        Requires an authorized access token.

        Params:
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            A list of dicts, each of which represents a calendar.

        Examples:
            To retrieve all calendars from your data store:

            >>> calendars = fulcra.calendars()
            >>>

            To inspect the details of a calendar:

            >>> calendars[0]
            {'calendar_id': '02b761da-46d0-4074-a9c8-406fd0de3adf', 'calendar_name':
            'Birthdays', 'calendar_color':
            '[0.5098039507865906,0.5843137502670288,0.686274528503418,1.0]',
            'calendar_source_id': '03da9f61-7b58-4021-8f40-a93548258faf',
            'calendar_source_name': 'Other', 'fulcra_source': 'apple_calendar'}


        """
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/calendars",
        )
        return json.loads(resp)

    def calendar_events(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        calendar_ids: Optional[List[str]] = None,
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve the list of calendar events that occur (at least partially) during the
        specified time range.

        To request events from another user's store, pass their user
        ID as the `fulcra_userid` parameter.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object.
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object.
            calendar_ids:
                If included, the query results are limited to events that
                are on the specified calendars.
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            A list of dicts, each of which contains the data from a calendar event.

        Examples:
            To retrieve all calendar events that span a given range of time:

            >>> cal_events = fulcra.calendar_events(
            ...     start_time = "2023-09-24 07:00:00.000Z",
            ...     end_time = "2023-09-25 07:00:00.000Z",
            ...     calendar_ids=["01fb4138-db27-4792-867d-5cfbdc720165"]
            ... )

            To inspect the details of an event:
            >>> cal_events[0]
            {'calendar_event_id': 'c409a249-24cd-4c19-b763-3683cc21b9f8',
            'calendar_id': '01fb4138-db27-4792-867d-5cfbdc720165', 'start_date':
            '2023-09-24T20:10:00Z', 'end_date': '2023-09-24T21:10:00Z',
            'allow_new_time_proposals': None, 'alarms':
            ['19b7692e-7434-44be-a5ba-c8dfa338deb6'], 'availability': 'free',
            'calendar_item_external_identifier':
            '7kukuqrfedlm2f9tfbe684r6cqpk9mrk0aqdeoan7jdbr93e7963lagn9uq6pdsbac40',
            'calendar_item_identifier': '22153B27-4BEE-480C-9627-F2EABC698103',
            'event_identifier':
            'EC9D6240-04A7-4869-9D2E-1A7648EA7732:7kukuqrfedlm2f9tfbe684r6cqpk9mrk0aqdeoan7jdbr93e7963lagn9uq6pdsbac40',
            'creation_date': '2023-09-16T23:27:22Z', 'has_alarms': True,
            'has_attendees': True, 'has_notes': True, 'has_recurrence_rules':
            False, 'is_all_day': False, 'is_detached': False, 'last_modified_date':
            '2023-09-16T23:27:26Z', 'location': 'PETCO Park', 'notes':
            'This event was created from an email you received in Gmail.',
            'occurrence_date': '2023-09-24T20:10:00Z', 'organizer':
            '22381502-0af3-487a-820c-e22aa4cae201', 'recurrence_rules': None,
            'status': 'confirmed', 'geolocation': None, 'time_zone':
            'America/Los_Angeles (fixed)', 'title':
            'St. Louis Cardinals at San Diego Padres', 'url': None,
            'extras': {}, 'participants': [{'is_current_user': True,
            'participant_role': 'required', 'participant_type': 'person',
            'participant_status': 'accepted', 'url': 'mailto:cstone@gmail.com',
            'contact_id': '00900185-b290-4f1c-860d-e4433024a943',
            'name': 'cstone@gmail.com'}]}
        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
        }
        if calendar_ids is not None:
            params["calendar_ids"] = calendar_ids
        qparams = urllib.parse.urlencode(params, doseq=True)
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/calendar_events?{qparams}",
        )
        return json.loads(resp)

    def apple_workouts(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve the list of Apple workouts that occurred (at least partially) during
        the specified time range.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object.
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object.
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            A list of dicts, each of which contains the data from a workout.

        Examples:
            To retrieve all workouts during a time period:

            >>> workouts = fulcra.apple_workouts(
            ...     start_time = "2023-09-21 07:00:00.000Z",
            ...     end_time = "2023-09-22 07:00:00.000Z"
            ... )

            To inspect the details of a workout:

            >>> workouts[0]
            {'start_date': '2023-09-21T19:18:31.733000Z', 'end_date':
            '2023-09-21T19:49:08.773000Z', 'has_undetermined_duration': False,
            'apple_workout_id': '480b25fe-b229-41b9-bf13-7ccf5e2092ec', 'duration':
            1837.0397539138794, 'extras': {'HKTimeZone': 'America/Los_Angeles',
            'HKAverageMETs': '4.37848 kcal/hr·kg' ... }

        """
        params = {"start_time": start_time, "end_time": end_time}
        qparams = urllib.parse.urlencode(params, doseq=True)
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/apple_workouts?{qparams}",
        )
        return json.loads(resp)

    def simple_events(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        categories: Optional[List[str]] = None,
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve the events that occurred during the specified period of time,
        optionally filtering by categories.

        If included, the `categories` parameter only includes events from the specified
        categories.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object.
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object.
            categories:
                When present, the categories to filter on.  Only events
                matching these categories will be returned.
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            A list of dicts, each of which represents an event.

        Examples:
            To retrieve the stored events during a given range:

            >>> simple_events = fulcra.simple_events(
            ...     start_time="2022-05-01 04:00:00.000Z",
            ...     end_time="2023-08-03 04:00:00.000Z"
            ... )

            To get the details of an event:
            >>> simple_events[0]
            {'event_body': 'relieved', 'category': 'mood', 'event_id':
            '12680011-6668-4c8e-b4cd-3ca429445ac0', 'timestamp':
            '2022-09-21T05:51:22Z'}

        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
        }
        if categories is not None:
            params["categories"] = categories
        qparams = urllib.parse.urlencode(params, doseq=True)
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/simple_events?{qparams}",
        )
        return json.loads(resp)

    def metric_samples(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        metric: str,
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve the raw samples related to the given metric that occurred for the
        user during the specified period of time.

        In cases where samples cover ranges and not points in time, a sample will
        be returned if any part of its range intersects with the requested range.

        As an example, if you have `start_date` as 14:00 and `end_date` at 15:00,
        and there is a sample that covers 13:30-14:30, it will be included.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object.
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object.
            metric: The name of the metric to retrieve samples for.
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Examples:

            >>> samples = fulcra.metric_samples(
            ...     start_time="2023-08-09 07:00:00.000Z",
            ...     end_time="2023-08-10 07:00:00.000Z",
            ...     metric="StepCount"
            ... )

            To inspect the first sample:

            >>> samples[0]
            {'start_date': '2023-08-10T06:05:10.726+00:00', 'end_date':
            '2023-08-10T06:05:13.285+00:00', 'extras': None,
            'has_undetermined_duration': False, 'unit': 'count', 'count': 1,
            'uuid': '74983a94-8816-4b95-bbbd-d4108149261a', 'value': 8,
            'source_properties': {'name': 'b c’s iPhone', 'version': '16.6',
            'productType': 'iPhone12,8', 'operatingSystemVersion': [16, 6, 0],
            'sourceBundleIdentifier':
            'com.apple.health.F8872676-6D45-4981-8E14-C009D0AE5F27'},
            'device_properties': {'name': 'iPhone', 'model':
            'iPhone', 'manufacturer': 'Apple Inc.',
            'hardwareVersion': 'iPhone12,8',
            'softwareVersion': '16.6'}}
        """
        params = {"start_time": start_time, "end_time": end_time, "metric": metric}
        qparams = urllib.parse.urlencode(params, doseq=True)
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/metric_samples?{qparams}",
        )
        return json.loads(resp)

    def apple_location_updates(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """Retrieve the raw Apple location update samples during the specified
        period of time.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object.
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object.
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            A list of dicts, each of which contains the data from a location update.

        Examples:
            To retrieve all location updates within a specific hour:

            >>> updates = fulcra.apple_location_updates(
            ...     start_time="2023-09-24T20:00:00Z",
            ...     end_time="2023-09-24T21:10:00Z"
            ... )

            To see the details of the first update:

            >>> updates[0]
            {'speed': -1, 'horizontal_accuracy_meters': 35, 'longitude_degrees':
            -117.15661336566698, 'source_is_simulated_by_software': False,
            'source_is_produced_by_accessory': False, 'latitude_degrees':
            32.706505158026005, 'vertical_accuracy_meters': 3.0130748748779297,
            'course_heading_accuracy_degrees': -1, 'course_heading_degrees': -1,
            'ellipsoidal_altitude_meters': -6.280021667480469, 'floor': 0,
            'speed_accuracy_meters': -1, 'altitude_meters': 29.17388153076172, 'uuid':
            'e80feacc-54e9-414f-86cb-8d6ebd85ea41', 'timestamp':
            '2023-09-24T20:39:28.056+00:00'}

        """
        params = {"start_time": start_time, "end_time": end_time}
        qparams = urllib.parse.urlencode(params, doseq=True)
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/apple_location_updates?{qparams}",
        )
        return json.loads(resp)

    def apple_location_visits(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve the raw Apple location visit samples during the specified
        period of time.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object.
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object.
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            A list of dicts, each of which contains the data from a location visit.

        Examples:
            To retrieve all location updates within a specific hour:

            >>> visits = fulcra.apple_location_visits(
            ...     start_time="2023-09-24T20:00:00Z",
            ...     end_time="2023-09-24T21:10:00Z"
            ... )

            To see the details of the first update:

            >>> visits[0]
            {'longitude_degrees': -117.1224047932943, 'latitude_degrees':
            32.75812770726706, 'arrival_date': '0001-01-01T00:00:00+00:00',
            'departure_date': '2023-09-25T01:42:16.998+00:00',
            'horizontal_accuracy_meters': 32.93262639589646, 'uuid':
                '935971dd-0822-49ef-a74f-b09a24d68c3a'}


        """
        params = {"start_time": start_time, "end_time": end_time}
        qparams = urllib.parse.urlencode(params, doseq=True)
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/apple_location_visits?{qparams}",
        )
        return json.loads(resp)

    def metric_time_series(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        metric: str,
        sample_rate: float = 60,
        replace_nulls: Optional[bool] = False,
        fulcra_userid: Optional[str] = None,
        calculations: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """
        Retrieve time-series data from a single Fulcra metric, covering the
        time starting at `start_time` (inclusive) until `end_time`
        (exclusive).

        If specified, the `sample_rate` parameter defines the number of
        seconds per sample.  This value can be smaller than 1.  The default
        value is 60 (one sample per minute).

        Requires a valid access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object
            metric: The name of the time-series metric to retrieve
            sample_rate: The length (in seconds) of each sample
            replace_nulls: When true, replace all NA/null/None values with 0
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.
            calculations: When present, specifies additional calculations to perform for each time slice.  The current values are:
                - `max`: The maximum value for each time window
                - `min`: The minimum value for each time window
                - `delta`: The delta between the maximum and minimum value for each time window
                - `mean`: The mean value for each time window
                - `uniques`: The list of unique values for each time window
                - `allpoints`: The list of all values for each time window
                - `rollingmean`: The rolling mean value for each time window.  This mean is calculated relative to the beginning of the requested sample

        Returns:
            a pandas DataFrame containing the data.  For time ranges where data is
                missing, the values will be `<NA>`.

        Examples:
            To retrieve a dataframe containing the `StepCount` metric:

            >>> df = fulcra.metric_time_series(
            ...     start_time = "2024-01-24 00:00:00-08:00",
            ...     end_time = "2024-01-25 00:00:00-08:00",
            ...     sample_rate = 1,
            ...     metric = "StepCount"
            ... )

        The index of the DataFrame will be the time:

        >>> df.index
        DatetimeIndex(['2024-01-24 08:00:00+00:00', '2024-01-24 08:00:01+00:00',
                       '2024-01-24 08:00:02+00:00', '2024-01-24 08:00:03+00:00',
                       '2024-01-24 08:00:04+00:00', '2024-01-24 08:00:05+00:00',
                       '2024-01-24 08:00:06+00:00', '2024-01-24 08:00:07+00:00',
                       '2024-01-24 08:00:08+00:00', '2024-01-24 08:00:09+00:00',
                       ...
                       '2024-01-25 07:59:50+00:00', '2024-01-25 07:59:51+00:00',
                       '2024-01-25 07:59:52+00:00', '2024-01-25 07:59:53+00:00',
                       '2024-01-25 07:59:54+00:00', '2024-01-25 07:59:55+00:00',
                       '2024-01-25 07:59:56+00:00', '2024-01-25 07:59:57+00:00',
                       '2024-01-25 07:59:58+00:00', '2024-01-25 07:59:59+00:00'],
                      dtype='datetime64[us, UTC]', name='time', length=86400, freq=None)

        The non-index column(s) in the dataframe will be related to the metric.

        >>> df.columns
        Index(['step_count'], dtype='object')
        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "metric": metric,
            "output": "arrow",
            "samprate": sample_rate,
            "replace_nulls": int(replace_nulls == True),
        }
        if calculations is not None:
            params["calculations"] = calculations

        qparams = urllib.parse.urlencode(
            params,
            doseq=True,
        )
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/metric_time_series?{qparams}",
        )
        return pd.read_feather(io.BytesIO(resp)).set_index("time")

    def location_time_series(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        change_meters: Optional[float] = None,
        sample_rate: int = 900,
        look_back: int = 14400,
        reverse_geocode: bool = False,
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve a time series of locations that the user was at.  This uses
        the most precise underlying data sources available at the given time.

        Requires a valid access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object
            change_meters: when specified, subsequent samples that are fewer than this many meters away will not be included.
            sample_rate: The length (in seconds) of each sample
            look_back: The maximum number of seconds in the past to look back to find a value for a sample.
            reverse_geocode: When true, Fulcra will attempt to reverse geocode the locations and include the details in the results.
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            A list of samples; each sample represents a location sample.

        Examples:
                        >>> locations = fulcra.location_time_series(
                        ...     start_time = "2024-06-06T19:00:00-07:00",
                        ...     end_time = "2024-06-06T20:00:00-07:00",
                        ...     reverse_geocode = True
                        ... )
                        >>> print(pd.DataFrame(locations))
                                                          slice_time        lat        long                           time  distance_change_m                                            address                                   location_details
                        0  2024-06-07T02:00:00+00:00  32.706814 -117.156455   2024-06-07T01:50:10.92+00:00                NaN  Petco Park, 100 Park Boulevard, San Diego, CA ...  {'annotations': {'DMS': {'lat': '32° 42' 25.87...
                        1  2024-06-07T02:15:00+00:00  32.706722 -117.156576  2024-06-07T02:03:56.903+00:00          15.281598  Petco Park, 100 Park Boulevard, San Diego, CA ...  {'annotations': {'DMS': {'lat': '32° 42' 25.87...
                        2  2024-06-07T02:30:00+00:00  32.706699 -117.156583  2024-06-07T02:22:07.571+00:00           2.588992  Petco Park, 100 Park Boulevard, San Diego, CA ...  {'annotations': {'DMS': {'lat': '32° 42' 25.87...
                        3  2024-06-07T02:45:00+00:00  32.706699 -117.156583  2024-06-07T02:22:07.571+00:00           0.000000  Petco Park, 100 Park Boulevard, San Diego, CA ...  {'annotations': {'DMS': {'lat': '32° 42' 25.87...
        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "sample_rate": sample_rate,
            "look_back": look_back,
            "reverse_geocode": reverse_geocode,
        }
        if change_meters is not None:
            params["change_meters"] = change_meters
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        qparams = urllib.parse.urlencode(params, doseq=True)
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/location_time_series?{qparams}",
        )
        return json.loads(resp)

    def location_at_time(
        self,
        time: Union[str, datetime.datetime],
        window_size: int = 14400,
        include_after: bool = False,
        reverse_geocode: bool = False,
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Gets the user's location at the specified time.  If no sample is
        available for the exact time, searches for the closest sample up to
        `window_size` seconds back.  If `include_after` is true, then also
        searches `window_size` seconds forward.

        Params:
            time: The point in time to get the user's location for.
            window_size: The size (in seconds) to look back (and optionally forward) for samples
            include_after: When true, a sample that occurs after the requested time may be returned if it is the closest one.
            reverse_geocode: When true, Fulcra will attempt to reverse geocode the location and include the details in the results.
            fulcra_userid: When present, specifies the Fulcra user ID to request data for.

        Returns:
            A list of dicts; the first dict is the best location sample.

        Examples:

        >>> location = fulcra.location_at_time(
        ...     time = "2024-01-24 00:00:00-08:00",
        ... )

        >>> location
        [{'speed': 0, 'horizontal_accuracy_meters': 4.848857421534995, 'longitude_degrees': -117.15709954484828, 'latitude_degrees': 32.707083bb994486, 'vertical_accuracy_meters': 3.2114044806616686, 'course_heading_accuracy_degrees': 180, 'course_heading_degrees': 87.05299950647989, 'ellipsoidal_altitude_meters': 32.700060645118356, 'floor': 0, 'speed_accuracy_meters': 0.9654413396512306, 'altitude_meters': 6.15396384336054, 'uuid': '59b2d63b-9b0b-436f-a66f-01129e1b33dd', 'timestamp': '2024-01-24T00:01:45.941+00:00', 'location_source': 'apple_location_update'}]
        """
        params = {
            "time": time,
            "window_size": window_size,
            "include_after": include_after,
            "reverse_geocode": reverse_geocode,
        }
        qparams = urllib.parse.urlencode(params, doseq=True)
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/location_at_time?{qparams}",
        )
        return json.loads(resp)

    def metrics_catalog(
        self,
    ) -> List[Dict]:
        """
        Gets the list of time-series metrics that are available for this user.
        These metrics can be passed to the `metric_time_series` and
        `time_series_grouped` functions.

        Returns:
            The metrics, including descriptions.

        Examples:

                >>> metrics = fulcra_client.metrics_catalog()
                >>> metrics[0]
                {'name': 'AFibBurden', 'description': "A discrete measure of the percentage of time that the user's heart shows signs\n    of atrial fibrillation (AFib) during a given monitoring period.", 'unit': 'percent', 'is_time_series': True, 'metric_kind': 'discrete', 'value_column': 'afib_burden'}
                >>> metrics[1]
                {'name': 'ActiveCaloriesBurned', 'description': 'A cumulative measure of the amount of active energy the user has burned.', 'unit': 'cal', 'is_time_series': True, 'metric_kind': 'cumulative', 'value_column': 'active_calories_burned'}
        """
        resp = self.fulcra_api(
            self.fulcra_cached_access_token, "/data/v0/metrics_catalog"
        )
        return json.loads(resp)

    def custom_input_events(
        self,
        start_time: Union[str, datetime.datetime],
        end_time: Union[str, datetime.datetime],
        source: Optional[str] = None,
        fulcra_userid: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieves events from Fulcra custom inputs, along with any metadata,
        for the requested time ranges.

        Requires a valid access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string or `datetime` object
            end_time: The end of the range (exclusive), as an ISO 8601 string or `datetime` object
            source: When specified, the full name of the source to query records from
            fulcra_userid: When present, specifies the Fulcra user ID to request data for

        Returns:
            A list of events; each event is represnted by a dict.
        """
        params = {
            "start_time": start_time,
            "end_time": end_time,
        }
        if source is not None:
            params["source"] = source
        if fulcra_userid is not None:
            params["fulcra_userid"] = fulcra_userid
        qparams = urllib.parse.urlencode(params, doseq=True)
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v1alpha1/type/CustomInputEvent?{qparams}",
        )
        return json.loads(resp)

    def get_shared_datasets(self) -> List[Dict]:
        """
        Retrieves datasets that have been shared with the currently authenticated user

        Examples:

                >>> datasets = fulcra_client.get_shared_datasets()
                >>> datasets[0]
                {'permission_id': 'cf362f80-ef41-4c08-b5e3-b18bd3d1524b', 'created_at': '2024-08-21T17:52:10.658596Z', 'time_start': None, 'time_end': None, 'fulcra_userid': 'a24a9667-c2c6-4bbf-9a0f-4Bej0afcb521', 'fulcra_user_name': 'John Doe', 'fulcra_user_picture': 'https://lh3.googleusercontent.com/a/ACg8ocL-ggGYjOFq23Dfbf5GohDXbk01AoGmL0gCSbooVBXDgWeTLJk=s47-d', 'datashare_name': 'Provisioned for data analysis'}
        """
        resp = self.fulcra_api(
            self.fulcra_cached_access_token, "/user/v1alpha1/datasets"
        )
        return json.loads(resp)
