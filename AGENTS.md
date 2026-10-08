# AGENTS.md - Fulcra Python library and CLI (`fulcra-api`)

> Fulcra - a durable, user-owned, agent-native context store Built for bridging the gap between agents and humans.

## About

[Fulcra](https://fulcradynamics.com/) is a personal data platform: a context lake where a person keeps their data and shares it with AI agents. The data belongs to the user, not to any single agent, so it persists across sessions, agents, and harnesses. An agent in Claude, ChatGPT/Codex, Hermes, OpenClaw, or code running on a machine or a notebook can all read and write the same datastore.

This repository is `fulcra-api`: the official Python client library and the `fulcra` command-line tool. The platform-wide guide for agents is [fulcradynamics.com/AGENTS.md](https://fulcradynamics.com/AGENTS.md), and platform concepts are documented at [docs.fulcradynamics.com/fulcra-platform](https://docs.fulcradynamics.com/fulcra-platform/).

What a Fulcra datastore holds:

* **Records of Data Types.** A Data Type describes something a user records; a Record is one saved instance. Users and their agents can create their own Data Types, with fields of their own, alongside a catalog of built-in ones. Every Data Type is either an **Event** (a point or span in time) or a **Metric** (a measured value over time). User-defined Data Types are referenced as `<BaseType>/<UUID>`, for example `Event/642f37c8-67aa-4758-8cc9-9368b47dd766`.
* **Files**, with full version history and restore: memory, notes, preferences, task boards, exports, anything an agent needs to keep.
* **Shares and groups**, for giving other Fulcra users read access to specific Data Types and files.
* **Device data, if the user opts in.** The optional [Context by Fulcra](https://apps.apple.com/us/app/context-personal-data-kit/id1633037434) iOS app can sync Apple Health, location, and calendar data into the same datastore.

## Repository Development

Always use `uv` to run Python commands in this repository. For example, run tests with `uv run python -m pytest [options...]`; do not invoke `python`, `python -m pytest`, or `pytest` directly.

By default the tests run fully offline, as CI does. Tests that talk to a real Fulcra backend are marked `live` and skipped unless you pass `--live` (`uv run python -m pytest --live`). That run opens a device login in the browser, which a person has to finish, so don't use `--live` unattended.

## What agents use Fulcra for

* **Coordinating a user's agents.** Several agents working for the same user, in different harnesses or sessions, share one datastore: they hand off work through shared files and records, and ask `data-updates` what changed since they last looked. See the skills in [the Fulcra skills repo](agent-skills) to set this up.
* **Connecting with other people's agents.** An agent can message the agent of anyone else on Fulcra (a colleague's assistant, a friend's agent, a company's support bot) through records each side shares only with the other, so both people opt in and nothing else is shared. The  skills in [fulcradynamics/agent-skills](https://github.com/fulcradynamics/agent-skills) handle invitations, consent and messaging.
* **Structured tracking.** Create a Data Type for anything (decisions, build times, habits, prices, a project's progress), record into it over time, and query it back later.
* **Durable memory across harnesses.** Keep an agent's memory, preferences, or working state in Fulcra files, then restore or clone it into another agent or a fresh session.
* **Situational awareness.** Combine the user's own records with device data (calendar, location, sleep, workouts) when the user has connected those sources.

The human explores their data, manages files and shares, and reviews what their agents have written in the [Context Web](https://context.fulcradynamics.com/) app and the iOS app.

## Interfaces for agents and code

| Interface | Best for | Where |
|---|---|---|
| **CLI** `fulcra` (run as `uvx fulcra-api`) | Agents with a shell. JSON output, agent-friendly auth. | [CLI docs](https://docs.fulcradynamics.com/cli/) |
| **MCP server** | Agents without a shell (Claude, ChatGPT, Codex, and other MCP clients). | [MCP docs](https://docs.fulcradynamics.com/mcp/), endpoint `https://mcp.fulcradynamics.com/mcp` |
| **Python library** `fulcra-api` | Code-first agents and notebooks. | [Library docs](https://fulcradynamics.github.io/fulcra-api-python/), [PyPI](https://pypi.org/project/fulcra-api/) |
| **REST API** | Any HTTP client. OAuth2 bearer tokens. | [REST reference](https://docs.fulcradynamics.com/rest-api/), [OpenAPI spec](https://api.fulcradynamics.com/openapi.json) |

The CLI and the Python library are this package (`fulcra-api`, Python 3.11 or newer).

If you are an agent setting Fulcra up for a user, [docs.fulcradynamics.com/agent-get-started.txt](https://docs.fulcradynamics.com/agent-get-started.txt) walks through connecting, authenticating, and doing something useful in the same session. The [fulcradynamics/agent-skills](https://github.com/fulcradynamics/agent-skills) library has skills for tracking, memory, shared workspaces, and connecting with other people's agents.

## Authorization

Every interface uses OAuth2 and never asks the agent to handle a password: the user authorizes in a browser, and the agent receives a token.

### Shell-first agents (CLI)

`uvx fulcra-api auth login` runs the device authorization flow and caches credentials in `~/.config/fulcra/credentials.json`, so later commands don't need to log in again. For non-interactive use, split it in two:

```sh
uvx fulcra-api auth login --get-auth-url                 # prints a URL and device code; send the URL to the user
uvx fulcra-api auth login --device-code <DEVICE CODE>    # waits until the user finishes in the browser
```

If `auth login` fails immediately, the environment probably has no outbound network access; suggest the MCP server instead of retrying.

### Code-first agents (Python)

`FulcraAPI().authorize()` prints a URL to send to the user and polls until they approve it (OAuth2 Device Authorization Flow). If it times out, call `authorize()` again for a new URL.

```
>>> from fulcra_api.core import FulcraAPI
>>> fulcra = FulcraAPI()
>>> fulcra.authorize()

            Use your browser to log in to Fulcra.  If the tab does not open
            automatically, visit this URL to authenticate: https://fulcra.us.auth0.com/activate?user_code=DBNV-DBQV
```

### Agents without a shell

Use the Fulcra MCP server instead of this package. Its setup is in the [MCP docs](https://docs.fulcradynamics.com/mcp/).

## The core loop

1. **Ask what changed first.** `uvx fulcra-api data-updates "1 hour"` summarizes the records and files that arrived in that window. Add `--include-shared` to cover everyone who shares data with the user, or `--user-id <UUID>` for one person. Counts appear a few minutes after the records themselves, so overlap the window with your previous check.
2. **Discover before you query.** `uvx fulcra-api catalog` lists every Data Type you can query or record. `catalog --user-defined` lists only the user-defined ones (the user's own and those shared with them); add `--recordable` for only the user's own.
3. **Create your own Data Types.** `uvx fulcra-api data-type create Event "<Name>" -d "<description>" --fields '<JSON Schema>'` (or `Metric` for a measured number). `uvx fulcra-api data-type schema <DataType>` prints a type's record schema.
4. **Read and write records.** `uvx fulcra-api record <DataType>` records one record from field options, or JSON lines piped in; records are checked against the type's schema before upload. `uvx fulcra-api get-records <DataType> "1 week"` returns JSON lines.
5. **Use files for anything unstructured.** `uvx fulcra-api file upload|list|stat|download|delete|restore`; `fulcra file download <path> -` prints a file to stdout. Remote paths are always `/`-rooted.

All times must include a time zone (ISO 8601) at API boundaries. Translate result timestamps to the user's local time zone when known.

### Example: the Python library

```python
import datetime

from fulcra_api import data_type_management, records
from fulcra_api.core import FulcraAPI

fulcra = FulcraAPI()
fulcra.authorize()

now = datetime.datetime.now(datetime.timezone.utc)
day_ago = now - datetime.timedelta(days=1)

# What changed in the last day, for the user and everyone who shares with them?
updates = fulcra.data_updates(day_ago, now, include_shared=True)

# Create a Data Type with fields of its own
[event] = fulcra.resolve_data_type("Event")
builds = data_type_management.create_data_type(
    fulcra, event, "Build finished",
    description="One record per CI build",
    fields_schema={
        "properties": {"repo": {"type": "string"}, "seconds": {"type": "number"}},
        "required": ["repo"],
    },

# Record into it, and read it back (records are readable within about a minute)
fulcra.record_data_type(builds["id"], [{"repo": "fulcra-api-python", "seconds": 312}], api_version="v1")
[entry] = fulcra.resolve_data_type(builds["id"])
recent = records.get_records(fulcra, entry, day_ago, datetime.datetime.now(datetime.timezone.utc))
```

## Command-Line Interface

Installing the `fulcra-api` package provides a `fulcra` command (also available as `fulcra-api`; agents usually run it as `uvx fulcra-api`). Sub-commands print JSON, mostly one object per line, designed for piping into tools like `jq`.

```sh
fulcra auth login                       # one-time device auth; credentials are cached
fulcra user-info                        # the authenticated user, including their user ID
fulcra data-updates "1 hour" --include-shared
fulcra catalog --user-defined
fulcra data-type create Event "Decision" -d "Decisions made in project meetings" \
    --fields '{"properties": {"summary": {"type": "string"}}, "required": ["summary"]}'
fulcra record Event/<UUID> --summary="Ship the beta on Friday"
fulcra get-records Event/<UUID> "1 week"
```

Notes:

- Time ranges can be given as two ISO8601 start/end arguments or a single relative interval like `"1 week"`, `"2 days"`, or `"3h"`. Ordinary query commands accept naive absolute timestamps, localize them to the machine's local timezone, and convert them to UTC. Timestamps that define access boundaries, such as group or share start and end times, must include an explicit timezone offset.
- Command families: the datastore (`catalog`, `data-type`, `record`, `get-records`, `delete`, `data-updates`, `metric-time-series`), files (`file`), sharing (`share`, `group`, `tag`), and device data (`calendars`, `calendar-events`, `location-at-time`, `location-time-series`, `sleep-cycles`, `sleep-stages`, `apple-workouts`, ...).
- `fulcra <command> --help` and `fulcra <group> <subcommand> --help` document every option. If a command or option shown here is missing, `uvx` is running an older cached version: use `uvx fulcra-api@latest`.
- `fulcra auth print-access-token` prints the OAuth2 access token, useful for calling the REST API directly.

## Data Groups

Data groups let a group owner collect read-only shared data from other Fulcra users who opt in. When a participant joins a group, they share the group's declared data types, within the group's declared time range, with the owner — until they leave. Most group parameters are immutable after creation, so the terms participants agreed to can't be changed later. Participant IDs are anonymized, per-group UUIDs that don't reveal the participant's Fulcra UserID.

Groups created through this library and CLI are always private (not publicly listed); creating public groups is not available to normal users.

Data types are optional. A group created without any collects nothing when people join, which makes it a pure audience — others can then share their own data with everyone in it (see "Sharing Data With a Group" below). A group's data types are immutable, so one created empty can never start collecting later.

The group's URL is optional too: a group with no webapp behind it reads back with `group_url: null`.

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

`fulcra group` sub-commands: `list` (public groups, or `--joined` for your memberships), `show`, `create`, `update`, `delete`, `join`, `leave`, `participants`, `get-metadata`, `set-metadata`, and `update-metadata`.

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

Share a user-defined Data Type by its full `<BaseType>/<UUID>` ID, so the share covers exactly that type.

### Python API

```python
# Share one of your Data Types with everyone in a group
share = fulcra.create_datashare(
    datashare_name="Project decisions",
    fulcra_data_types=["Event/642f37c8-67aa-4758-8cc9-9368b47dd766"],
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
fulcra share create --name "Project decisions" --data-type Event/<UUID> --group-id <GROUP-UUID>
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
# {'all_data_types': False, 'fulcra_data_types': ['Event/642f37c8-67aa-4758-8cc9-9368b47dd766']}
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

Ready-to-run notebooks are in the [Fulcra demos repository](https://github.com/fulcradynamics/demos): getting started, reading data other users share with you, visualization, and examples built on device data. They can also be opened in [Google Colab](https://colab.research.google.com/) with no install.

## Support

- **Email:** support@fulcradynamics.com
- **Discord:** [Fulcra Discord](https://discord.gg/fulcra)
- **GitHub:** [github.com/fulcradynamics](https://github.com/fulcradynamics)

## Official domains
* fulcradynamics.com
* context.fulcradynamics.com
* mcp.fulcradynamics.com
* fulcra.ai
