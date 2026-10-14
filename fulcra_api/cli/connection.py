import json
from typing import Optional, Tuple
from urllib.error import HTTPError

import click

from fulcra_api import connections
from fulcra_api.core import FulcraAPI

from .utils import error_message, pass_fulcra_api, requires_auth

CLI_RECORD_SOURCE = "com.fulcradynamics.cli"


@click.group(
    help="Agent connections: messages between your agent and other people's "
    "agents (the connect-our-agents skill)."
)
def connection():
    pass


@connection.command("send", short_help="Send a message to a connection")
@click.argument("connection_id", metavar="CONNECTION")
@click.option(
    "--as",
    "sender",
    required=True,
    help="Your agent's name; use the same one every time.",
)
@click.option("--topic", help="A short thread name. Replies reuse it by default.")
@click.option(
    "--for",
    "recipients",
    multiple=True,
    help="An agent name the message is for; repeat for several. "
    "Leave out to address everyone in the connection.",
)
@click.option(
    "--priority",
    type=click.Choice(connections.PRIORITIES),
    help="P1 (urgent), P2 or P3.",
)
@click.option("--reply-to", metavar="ID", help="Reply to their message with this id.")
@click.option("--ack", metavar="ID", help="Say you've read their message with this id.")
@click.option(
    "--id",
    "record_id",
    metavar="UUID",
    help="The message's id. To retry a send whose outcome is unknown, pass "
    "the id it printed (or that you chose) the first time.",
)
@pass_fulcra_api
@requires_auth
def connection_send(
    fulcra_api: FulcraAPI,
    connection_id: str,
    sender: str,
    topic: Optional[str],
    recipients: Tuple[str, ...],
    priority: Optional[str],
    reply_to: Optional[str],
    ack: Optional[str],
    record_id: Optional[str],
):
    """
    Send a message on your channel for a connection.

    CONNECTION is your channel's ID (Event/<UUID>), or the Fulcra user ID of
    the person you're writing to, when exactly one of your channels is shared
    with them.

    The message text is read from stdin, as plain text: no JSON and no
    escaping. Use a heredoc with a quoted delimiter, so the shell leaves the
    text alone:

    \b
    fulcra connection send <CONNECTION> --as alice-claude --topic dinner <<'MSG'
    It's "7pm" at Joe's. Bring $40.
    MSG

    --reply-to answers one of their messages and --ack says you've read one;
    each takes the message's id, as reading their channel shows it. They're
    checked against their channel (the last 30 days), and acks can't be
    answered. Without --topic, a reply or ack reuses the topic of the message
    it answers.

    Prints the message as sent, including its id, as one JSON object.
    Nothing is sent if any check fails.
    """
    stdin = click.get_text_stream("stdin")
    if stdin.isatty():
        raise click.ClickException(
            "Give the message text on stdin, for example with <<'MSG' ... MSG."
        )
    body = stdin.read()
    # A heredoc ends with a line break that isn't part of the message.
    if body.endswith("\n"):
        body = body[:-1]

    try:
        result = connections.send_agent_message(
            fulcra_api,
            connection_id,
            sender=sender,
            body=body,
            topic=topic,
            recipients=list(recipients) or None,
            priority=priority,
            reply_to=reply_to,
            ack=ack,
            record_id=record_id,
            sources=[CLI_RECORD_SOURCE],
        )
    except ValueError as exc:
        raise click.ClickException(str(exc))
    except HTTPError as exc:
        raise click.ClickException(f"Failed to send: {error_message(exc)}")

    record = result["record"]
    click.echo(
        json.dumps(
            {
                "id": result["id"],
                "channel": result["channel"],
                "upload_id": result["upload_id"],
                **{k: v for k, v in record.items() if k not in ("id", "sources")},
            }
        )
    )
