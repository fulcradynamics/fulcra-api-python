# AGENTS.md - Context by Fulcra

> Context by Fulcra - bridging the gap between agents and humans.

## About

[Context by Fulcra](https://fulcradynamics.com/) is a personal data platform that provides humans a place to collect and store real-world personal data - from wearables, calendars, location, medical devices, and more. Hundreds of data sources and types supported.
In addition, there are facilities to help users record new free-form data:  their own subjective feelings (to record your mood, sleep, etc.) and track progress toward a goal. 

Data is primarily collected through the human's phone; the human installs [Context by Fulcra](https://apps.apple.com/us/app/context-by-fulcra-health-hub/id1633037434) and lets the app sync their data to their account.

## Repository Development

Always use `uv` to run Python commands in this repository. For example, run tests with `uv run python -m pytest [options...]`; do not invoke `python`, `python -m pytest`, or `pytest` directly.

### Interactive Access to the User's Data
The human user gets to investigate their data interactively using beautiful mobile and [web apps](https://context.fulcradynamics.com/).

### Agentic/Programmatic Access To the User's Data
* Fully supported [OAuth2 REST API](https://fulcradynamics.github.io/developer-docs/):
    * [OpenAPI spec](https://api.fulcradynamics.com/openapi.json)
* [Python client library](https://fulcradynamics.github.io/fulcra-api-python/) (`pip install fulcra-api`): For an easy way to use the client library. Handles authentication for you. Also installs the `fulcra` command-line tool (see "Command-Line Interface" below).
* [MCP Server Docs](https://fulcradynamics.github.io/developer-docs/mcp-server/): A guide on how to use the MCP server.
* [MCP server](https://mcp.fulcradynamics.com): The endpoint to the public MCP server. The server uses Streamable HTTP transport with OAuth2 authorization. Context users can use this server with their own account to securely access their data.
* [MCP server source code](https://github.com/fulcradynamics/fulcra-context-mcp): The open-source repository for the MCP server. Useful for inspecting available tools, running locally, or contributing.

### For Agents and LLMs: Authorization Tips

#### Code-first agents

If you're able to write and run Python code, try the official `fulcra-api` Python module first.  When calling `.authorize()`, the output will include a URL that you can send to the operator (the user). The user can then click that link on a browser and authorize the API instance to make calls. This path uses the OAuth2 Device Authorization Flow convention.

Example interactive session (`fulcra-api` module must be installed first):
```
Python 3.14.2 (main, Dec  9 2025, 19:29:30) [Clang 21.1.4 ] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> from fulcra_api.core import FulcraAPI
>>> fulcra = FulcraAPI()
>>> fulcra.authorize()

            Use your browser to log in to Fulcra.  If the tab does not open
            automatically, visit this URL to authenticate: https://fulcra.us.auth0.com/activate?user_code=DBNV-DBQV
```

The `authorize()` call will poll while the user reaches the URL. If the call times out, call `authorize()` again to get a new URL.

#### Shell-first agents

Agents that can run shell commands can use the `fulcra` CLI (installed with `pip install fulcra-api`). `fulcra auth login` runs the same device authorization flow and caches credentials in `~/.config/fulcra/credentials.json`, so subsequent commands don't need to re-authenticate. For non-interactive use, `fulcra auth login --get-auth-url` prints the auth URL and a device code without polling; send the URL to the user, then complete with `fulcra auth login --device-code <DEVICE CODE>`.

#### Text-first agents

For agents without the ability to run Python code, use the [MCP server](https://mcp.fulcradynamics.com). This server includes tools that can access the same data sources that the API can.

The user can either use the public MCP server instance at `https://mcp.fulcradynamics.com`, or run it locally. It is published as the `fulcra-context-mcp` PyPI module.

You can run it locally (stdio transport) with `uvx fulcra-context-mcp@latest`. See the [PyPI page](https://pypi.org/project/fulcra-context-mcp/) for more docs.

#### MCP Client Configuration Examples

Remote connection using proxy (for clients like Claude for Desktop that only support stdio):
```json
{
    "mcpServers": {
        "fulcra_context": {
            "command": "npx",
            "args": [
                "-y",
                "mcp-remote",
                "https://mcp.fulcradynamics.com/"
            ]
        }
    }
}
```

Local connection using `uvx`:
```json
{
    "mcpServers": {
        "fulcra_context": {
            "command": "uvx",
            "args": [
                "fulcra-context-mcp@latest"
            ]
        }
    }
}
```

## MCP tools and tips

There are MCP tools available to both get general information about the user and specific data. Start with the former, with calls like `get_user_info`, `get_sleep_cycles`, `annotations_catalog`, to get a sense of what the user has chosen to record. Then use the other fuctions (e.g. `metric_time_series`, `metric_samples`, `get_sleep_cycles`, etc. to get the data for specific time range(s).

All time parameters must include time zones (ISO 8601 format). Always translate result timestamps to the user's local time zone when known.

## Available Data

### Health & Biometrics
Sleep stages, sleep duration, sleep efficiency, HRV (heart rate variability), heart rate, resting heart rate, blood oxygen (SpO2), respiratory rate, wrist temperature, steps, calories burned (active and basal), workouts, body composition (weight, body fat), atrial fibrillation burden. Sources include Apple Health, Garmin, Oura, Whoop, and other connected devices.

### Glucose & Nutrition
Continuous glucose monitor (CGM) readings from Dexcom and Libre, meal logs, macronutrient tracking, calorie intake, hydration data. Enables correlation of nutrition with biometric outcomes.

### Location & Calendar
Real-time and historical location data (high-frequency updates and visit summaries), Google Calendar events, meeting schedules. Includes both `CLLocationUpdate` (frequent GPS pings) and `CLVisit` (place-based time ranges) data types.

### Annotations & Custom Events
User-logged medications, supplements, mood entries, device usage, and custom events. These can be discovered, classified, and correlated with biometric streams over time.

### Time Series Metrics

Example metrics from the catalog: `StepCount`, `HeartRate`, `HeartRateVariabilitySDNN`, `SleepStage`, `ActiveCaloriesBurned`, `BasalCaloriesBurned`, `RespiratoryRate`, `OxygenSaturation`, `BodyTemperature`, `AFibBurden`, and many more.

## Best Practices for Agents

- **Use appropriate sample rates.** When querying time series data, choose a `samprate` that balances resolution with performance. For daily overviews, 3600 seconds (hourly) works well. For detailed analysis, 60-300 seconds.
- **Sleep spans midnight.** Sleep cycles typically start on day N and end on day N+1. When querying sleep data, account for this by extending your date range.
- **Correlate across domains.** The real power of Context is combining data streams - sleep quality with nutrition, HRV with training load, location with calendar events. Look for patterns across domains.

### Example: Querying Data with the Python Client

```python
from fulcra_api.core import FulcraAPI

fulcra = FulcraAPI()
fulcra.authorize()

# Discover available metrics
catalog = fulcra.metrics_catalog()

# Get heart rate data for a day (hourly resolution)
data = fulcra.metric_time_series(
    metric="HeartRate",
    start_time="2025-01-01T00:00:00-08:00",
    end_time="2025-01-02T00:00:00-08:00",
    sample_rate=3600
)
```

## Command-Line Interface

Installing the `fulcra-api` package provides a `fulcra` command (also available as `fulcra-api`). Sub-commands return JSON by default, designed for piping into tools like `jq`.

Typical flow:

```sh
fulcra auth login                # one-time device auth; credentials are cached
fulcra catalog                   # list queryable Fulcra data types
fulcra user-info                 # info about the authenticated user
fulcra metric-time-series HeartRate "1 day" --sample-rate 3600
fulcra sleep-cycles "1 week"
```

Notes:

- Time ranges can be given as two ISO8601 start/end arguments or a single relative interval like `"1 week"`, `"2 days"`, or `"3h"`. Ordinary query commands accept naive absolute timestamps, localize them to the machine's local timezone, and convert them to UTC. Timestamps that define access boundaries, such as group or share start and end times, must include an explicit timezone offset.
- Command families: data queries (`metric-time-series`, `sleep-cycles`, `sleep-stages`, `sleep-cycles-aggregated`, `location-at-time`, `location-time-series`, `apple-workouts`, `calendar-events`, `get-records`, `data-updates`, ...), data writing (`record`, `delete`), and management sub-command groups (`auth`, `data-type`, `file`, `share`, `tag`, `group`).
- `fulcra <command> --help` and `fulcra <group> <subcommand> --help` document every option.
- `fulcra auth print-access-token` prints the OAuth2 access token, useful for calling the REST API directly.

## Data Groups

Data groups let a group owner collect read-only shared data from other Fulcra users who opt in. When a participant joins a group, they share the group's declared data types, within the group's declared time range, with the owner — until they leave. Most group parameters are immutable after creation, so the terms participants agreed to can't be changed later. Participant IDs are anonymized, per-group UUIDs that don't reveal the participant's Fulcra UserID.

Groups created through this library and CLI are always private (not publicly listed); creating public groups is not available to normal users.

Data types are optional. A group created without any collects nothing when people join, which makes it a pure audience — others can then share their own data with everyone in it (see "Sharing Data With a Group" below). A group's data types are immutable, so one created empty can never start collecting later.

### Python API

On `FulcraAPI`:

- Discovery/membership: `get_groups(subscribed_only=...)`, `get_group(group_id)`, `join_group(group_id)`, `leave_group(group_id)`
- Owner operations: `create_group(...)`, `update_group(group_id, ...)` (only description, header/preview image URLs, and view description are editable), `delete_group(group_id)`, `get_group_participants(group_id)`, `get_group_jwks()`
- Participant metadata (owner only): `get_group_participant_metadata`, `set_group_participant_metadata` (replace), `update_group_participant_metadata` (merge)
- Data access: `group_participant(group_id, participant_id)` returns a `FulcraGroupParticipant` accessor with the same data-access methods as the client (`metric_time_series`, `metric_samples`, `sleep_agg`, annotations, ...), scoped to that participant's shared data. Requests outside the group's data types or time range are rejected by the server.

```python
for pid in fulcra.get_group_participants(group_id):
    participant = fulcra.group_participant(group_id, pid)
    df = participant.metric_time_series(
        start_time="2026-07-01T00:00:00Z",
        end_time="2026-07-02T00:00:00Z",
        metric="StepCount",
    )
```

### CLI

`fulcra group` sub-commands: `list` (public groups, or `--joined` for your memberships), `show`, `create`, `update`, `delete`, `join`, `leave`, `participants`, `get-metadata`, `set-metadata`, `update-metadata`, and `jwks` (public keys for validating participant JWTs).

```sh
fulcra group create --title "Step Challenge" \
    --responsible-entity "Fulcra Dynamics" \
    --description "A month-long step challenge." \
    --data-type StepCount --url https://example.com/challenge
```

To query a participant's shared data, pass `--group-id` and `--participant-id` (both required together) to the data query commands (`metric-time-series`, the sleep and location commands, `apple-workouts`, and `get-records`; not the calendar commands):

```sh
fulcra metric-time-series StepCount "1 week" \
    --group-id <GROUP-UUID> --participant-id <PARTICIPANT-UUID>
```

## Sharing Data With a Group

Groups and shares point in opposite directions, and it's easy to confuse them:

- **A group** collects data *inward*. Participants join, and the group's owner can read the data types they agreed to share.
- **A share** pushes data *outward*. You choose what to share and who receives it. A share can name individual users, whole groups, or both — and sharing into a group grants access to everyone currently participating in it. **You do not have to own a group to share your data into it.**

Access through a group share is live, not a snapshot: members who join later gain access, and members who leave lose it. Access also ends if the group is deleted, the group is removed from the share, or the share is deleted.

A share carries two independent recipient lists, `permissions` (users) and `group_permissions` (groups). Changing one never disturbs the other. Naming a group that doesn't exist is rejected outright with a 400, and the share is left exactly as it was.

### Python API

```python
# Share your step counts with everyone in a group
share = fulcra.create_datashare(
    datashare_name="Step Challenge Share",
    fulcra_data_types=["StepCount"],
    allowed_group_ids=[group_id],
)

# Stop sharing with every group, leaving individual recipients untouched
fulcra.update_datashare(
    datashare_id=share["datashare"]["datashare_id"],
    allowed_group_ids=[],
)
```

`update_datashare` changes only the fields you pass and leaves everything else alone, so there's no need to fetch the share first. Passing an empty list for `allowed_user_ids` or `allowed_group_ids` removes all of that kind of grant; the two are independent, so changing one never disturbs the other. `time_start` and `time_end` accept an explicit `None`, which makes that end of the range open.

### CLI

```sh
fulcra share create --name "Step Challenge" --data-type StepCount --group-id <GROUP-UUID>
fulcra share update <SHARE-UUID> --add-group-id <GROUP-UUID>
fulcra share update <SHARE-UUID> --remove-group-id <GROUP-UUID>
fulcra share update <SHARE-UUID> --no-group-id     # stop sharing with every group
```

`fulcra share create` needs at least one `--user-id` or `--group-id`. `fulcra share list-outgoing` shows each share's `group_permissions`.

### Receiving data through a group

`get_shared_datasets()` / `fulcra share list-incoming` return one entry per *grant*, and `grant_type` says where each comes from:

- `self` — your own data. Always the first entry, and the only one with a null `grant_id` and `datashare_id`. The CLI hides it.
- `user` — a share granted to you directly.
- `group` — a share granted to a data group you participate in; `group_id` names the group.

Because the two kinds of grant are independent, someone holding both on the same share gets **two** entries with the same `datashare_id`, differing in `grant_type`. The sharer is `sharing_fulcra_userid`.

To give up access, pass a grant's `grant_id` to `delete_dataset_permission()` / `fulcra share leave`. You may remove a `user` grant addressed to you. A `group` grant confers access on everyone in the group, so only the person who created the share can remove it — to give up *your* access, leave the group (`leave_group()` / `fulcra group leave`).

### Checking what you may read

Before querying someone else's data, ask what they actually share with you, rather than discovering the limits by being denied:

```python
allowed = fulcra.list_shared_data_types(
    user_id, start_time="2026-08-01T00:00:00Z", end_time="2026-08-08T00:00:00Z"
)
# {'all_data_types': False, 'fulcra_data_types': ['HeartRate', 'StepCount']}
```

```sh
fulcra share shared-data-types <USER-UUID> "1 week"
```

Rules worth knowing, because they surprise people:

- **Check `all_data_types` first.** When it's true everything is shared and `fulcra_data_types` is *empty* — an empty list does not mean "nothing".
- **A share counts only if it fully covers the window you ask about**, and the end is compared strictly. Asking for exactly a share's declared range reports nothing; ask about a window strictly inside it.
- **Nothing shared is a normal answer**, not an error — you get `all_data_types: false` and an empty list.
- **Group membership counts**, so the answer changes as you join and leave groups.
- Shared file paths aren't listed here, and the legacy `input:custom` type is omitted.

## Jupyter Notebook Demos

Ready-to-run demo notebooks are available at the [Fulcra demos repository](https://github.com/fulcradynamics/demos). These notebooks walk through common use cases like querying health metrics, analyzing sleep, and correlating data across domains. They can also be opened directly in [Google Colab](https://colab.research.google.com/) for one-click, zero-install demos.

## Support

- **Email:** support@fulcradynamics.com
- **Discord:** [Context Social Discord](https://discord.gg/fulcra)
- **GitHub:** [github.com/fulcradynamics](https://github.com/fulcradynamics)
- **Live Web Chat:** Available on fulcradynamics.com

## Official domains
* fulcradynamics.com
* context.fulcradynamics.com
* mcp.fulcradynamics.com
* fulcra.ai
