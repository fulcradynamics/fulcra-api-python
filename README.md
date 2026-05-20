# Fulcra Dynamics Python Client Library

This is a Python library to simplify calling the [Fulcra Dynamics](https://fulcradynamics.com/) Life API.

For a guide to installation, getting started, and an API reference, view the [documentation site](https://fulcradynamics.github.io/fulcra-api-python/).

## Fulcra CLI

This library also includes a CLI tool for authenticating & interacting with the Fulcra Life API which may be useful to developers and AI agents. It can be run via `fulcra` or `fulcra-api`:

```shell
❯ fulcra --help
Usage: fulcra [OPTIONS] COMMAND [ARGS]...

  Command line interface for authenticating and interacting with the Fulcra
  Life API.

  Sub-commands return JSON data by default for convienent piping into tools
  like `jq` for parsing and filtering.

Options:
  --help  Show this message and exit.

Commands:
  apple-location-updates   Return Apple location update records
  apple-location-visits    Return Apple location visit records
  apple-workouts           Return Apple workouts
  auth                     Authentication sub-commands
  calendar-events          Return Apple calendar events
  calendars                Return Apple calendars
  catalog                  Return a list of queryable Fulcra data types and
                           metadata
  get-records              Return raw sample records for a data type
  google-location-updates  Return Google Maps location update records
  location-at-time         Return location at specified time
  location-time-series     Return a calculated time series of location data
  metric-time-series       Return a calculated time series for a metric
  sleep-cycles             Return sleep cycles summarized from sleep stages
  sleep-cycles-aggregated  Return sleep cycles aggregated by a specific period
  sleep-stages             Return sleep stages derived from sleep-related
                           metric records
  user-info                Return information about the authenticated user
```

## Bugs / Feature Requests

Please report any bugs or feature requests using [GitHub issues](https://github.com/fulcradynamics/fulcra-api-python).
