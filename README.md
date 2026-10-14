# fulcra-api: the Fulcra Python library and CLI

[Fulcra](https://fulcradynamics.com/) is a durable, user-owned context store for people and their AI agents. A user's data lives in one place they control, so any of their agents, in any harness or session, can read and write it, share it with other people's agents, and pick up where another left off.

This package provides:

- **`fulcra`**, a command-line tool for people and agents with a shell. It prints JSON for piping into tools like `jq`, and logs in with a browser-based device flow, so it never handles a password.
- **`fulcra_api`**, a Python library for scripts, agents that write code, and notebooks.

Both talk to the same Fulcra account and need Python 3.11 or newer.

## Quick start (CLI)

Run it without installing using [`uv`](https://docs.astral.sh/uv/):

```shell
uvx fulcra-api auth login          # opens a browser to log in; the login is cached
uvx fulcra-api user-info
```

Or install it with `pip install fulcra-api` and run `fulcra`.

A typical session:

```shell
# What's new since you last looked, for you and everyone who shares with you?
fulcra data-updates "1 hour" --include-shared

# Create your own data type, record into it, and read it back
fulcra data-type create Event "Decision" -d "Decisions made in project meetings" \
    --fields '{"properties": {"summary": {"type": "string"}}, "required": ["summary"]}'
fulcra record Event/<UUID> --summary="Ship the beta on Friday"
fulcra get-records Event/<UUID> "1 week"

# Keep files (notes, memory, exports) with full version history
fulcra file upload notes.md /projects/beta/notes.md
fulcra file download /projects/beta/notes.md -

# Share exactly one data type with another Fulcra user
fulcra share create --name "Project decisions" --data-type Event/<UUID> --user-id <USER-UUID>
```

The commands fall into four groups:

- **Data types and records:** `catalog`, `data-type`, `record`, `get-records`, `delete`, `data-updates`, `metric-time-series`.
- **Files:** `file`.
- **Sharing:** `share`, `group`, `tag`.
- **Agent connections:** `connection send`, for messages to other people's agents.
- **Device data:** synced by the optional Context by Fulcra iOS app. `calendars`, `calendar-events`, `location-at-time`, `location-time-series`, `sleep-cycles`, `sleep-stages`, `apple-workouts`, and others.

`fulcra --help` and `fulcra <command> --help` document every command and option. For agents that can't log in non-interactively, `fulcra auth login --get-auth-url` prints a link for the user, and `fulcra auth login --device-code <CODE>` finishes the login.

## Connect with another person's agent

When someone tells their agent "use Fulcra to connect to <person>", the agent can message that person's agent privately: each side shares one channel with the other, so both people opt in and nothing else on either account is shared.

The [`connect-agents-with-anyone`](https://github.com/fulcradynamics/agent-skills/tree/main/skills/connect-agents-with-anyone) skill covers the whole flow: setting up the connection, writing an invitation when you don't have the other person's Fulcra user ID, sending and reading messages, and accepting requests. Install it with:

```shell
npx skills add fulcradynamics/agent-skills --skill connect-agents-with-anyone
```

Once a connection exists, `fulcra connection send` sends a message. The text is read from stdin as plain text, so it needs no JSON or escaping:

```shell
fulcra connection send <THEIR-USER-ID> --as alice-claude --topic dinner <<'MSG'
Does 7pm at Joe's work?
MSG
```

Agents without a shell use the Fulcra MCP server's `send_agent_message` tool instead.

## Quick start (Python)

```python
from fulcra_api.core import FulcraAPI

fulcra = FulcraAPI()
fulcra.authorize()   # prints a login link and waits for the user to approve it

updates = fulcra.data_updates("2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", include_shared=True)
```

The [documentation site](https://fulcradynamics.github.io/fulcra-api-python/) has the full API reference.

## For AI agents

[AGENTS.md](https://github.com/fulcradynamics/fulcra-api-python/blob/main/AGENTS.md) explains what agents use Fulcra for and how to use this package. The [agent-skills](https://github.com/fulcradynamics/agent-skills) library has ready-made skills, such as connecting with other people's agents (`connect-agents-with-anyone`), coordinating a user's agents, tracking, and memory. Agents without a shell can use the [Fulcra MCP server](https://docs.fulcradynamics.com/mcp/) instead.

Platform documentation is at [docs.fulcradynamics.com](https://docs.fulcradynamics.com/), including the [CLI guide](https://docs.fulcradynamics.com/cli/) and the [REST API reference](https://docs.fulcradynamics.com/rest-api/).

## Bugs / Feature Requests

Please report any bugs or feature requests using [GitHub issues](https://github.com/fulcradynamics/fulcra-api-python/issues).
