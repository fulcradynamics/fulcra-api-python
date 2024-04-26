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
    The main class for making Fulcra API functions.

    This contains functions for authorizing a token, authenticating HTTP requests,
    making calls, and loading data.
    """

    fulcra_cached_access_token = None
    fulcra_cached_access_token_expiration = None

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

    def get_token(self, device_code: str) -> Tuple[Optional[str], Optional[datetime.datetime]]:
        conn = self._get_auth_connection(FULCRA_AUTH0_DOMAIN)
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
        start_time: str,
        end_time: str,
        metrics: List[str],
        sample_rate: float = 60,
        replace_nulls: Optional[bool] = False
    ):
        """
        Retrieve a time-series data frame containing the specified set of
        Fulcra metrics from `start_time` (inclusive) until `end_time` (exclusive).

        If specified, the `sample_rate` parameter defines the number of
        seconds per sample.  This value can be smaller than 1.  The default
        value is 60 (one sample per minute).

        Requires a valid access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string
            end_time: The end of the range (exclusive), as an ISO 8601 string
            metrics: The names of the time-series metrics to include in the result
            sample_rate: The length (in seconds) of each sample
            replace_nulls: When true, replace all NA/null/None values with 0

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
        qparams = urllib.parse.urlencode(
            {
                "start_time": start_time,
                "end_time": end_time,
                "metrics": metrics,
                "output": "arrow",
                "samprate": sample_rate,
                "replace_nulls": int(replace_nulls == True)
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
        specified time range.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string.
            end_time: The end of the range (exclusive), as an ISO 8601 string.
            calendar_ids:
                If included, the query results are limited to events that
                are on the specified calendars.

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
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/calendar_events?{qparams}",
        )
        return json.loads(resp)

    def apple_workouts(self, start_time: str, end_time: str) -> List[Dict]:
        """
        Retrieve the list of Apple workouts that occurred (at least partially) during
        the specified time range.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string.
            end_time: The end of the range (exclusive), as an ISO 8601 string.

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

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string.
            end_time: The end of the range (exclusive), as an ISO 8601 string.
            categories:
                When present, the categories to filter on.  Only events
                matching these categories will be returned.

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

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string.
            end_time: The end of the range (exclusive), as an ISO 8601 string.
            metric: The name of the metric to retrieve samples for.

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
        """Retrieve the raw Apple location update samples during the specified
        period of time.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string.
            end_time: The end of the range (exclusive), as an ISO 8601 string.

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
        Retrieve the raw Apple location visit samples during the specified
        period of time.

        Requires an authorized access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string.
            end_time: The end of the range (exclusive), as an ISO 8601 string.

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


    def metric_time_series(
        self,
        start_time: str,
        end_time: str,
        metric: str,
        sample_rate: float = 60,
        replace_nulls: Optional[bool] = False
    ):
        """
        Retrieve time-series data from a single Fulcra metric, covering the
        time starting at `start_time` (inclusive) until `end_time`
        (exclusive).

        If specified, the `sample_rate` parameter defines the number of
        seconds per sample.  This value can be smaller than 1.  The default
        value is 60 (one sample per minute).

        Requires a valid access token.

        Params:
            start_time: The start of the time range (inclusive), as an ISO 8601 string
            end_time: The end of the range (exclusive), as an ISO 8601 string
            metric: The name of the time-series metric to retrieve
            sample_rate: The length (in seconds) of each sample
            replace_nulls: When true, replace all NA/null/None values with 0

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
        qparams = urllib.parse.urlencode(
            {
                "start_time": start_time,
                "end_time": end_time,
                "metric": metric,
                "output": "arrow",
                "samprate": sample_rate,
                "replace_nulls": int(replace_nulls == True)
            },
            doseq=True,
        )
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token, f"/data/v0/{fulcra_userid}/metric_time_series?{qparams}"
        )
        return pd.read_feather(io.BytesIO(resp)).set_index("time")


    def location_at_time(
        self,
        time: str,
        window_size: int = 14400,
        include_after: bool = False
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
            "include_after": include_after
        }
        qparams = urllib.parse.urlencode(params, doseq=True)
        fulcra_userid = self.get_fulcra_userid()
        resp = self.fulcra_api(
            self.fulcra_cached_access_token,
            f"/data/v0/{fulcra_userid}/location_at_time?{qparams}",
        )
        return json.loads(resp)


    def metrics_catalog(
        self
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
            self.fulcra_cached_access_token,
            "/data/v0/metrics_catalog"
        )
        return json.loads(resp)
