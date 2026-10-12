"""Messages between agents on different Fulcra accounts.

Implements the protocol of the ``connect-agents-with-anyone`` skill
(https://github.com/fulcradynamics/agent-skills): each contact in a connection
has their own channel, a v1 ``Event/<uuid>`` data type with the fields in
``CHANNEL_FIELDS``, and shares exactly that channel with everyone else in the
connection through a datashare named ``connect-agents-with-anyone: ...``. A
message is one record on the sender's own channel.

Like ``records``, this module sits between the transport (``core``) and the
front-ends (the CLI, the MCP server): functions take a ``FulcraAPI`` as their
first argument, return plain data, and raise plain ``ValueError``.
"""

import datetime
from urllib.error import HTTPError
from uuid import UUID, uuid4

import jsonschema
import jsonschema.exceptions

from fulcra_api import records
from fulcra_api.record_validation import is_unknown_fields_error, unknown_fields

# Every share of a channel, in either direction, has a name starting with this.
SHARE_NAME_PREFIX = "connect-agents-with-anyone"

# The fields of a channel, as passed to `data-type create Event --fields`.
# Must match the skill's references/channel-fields.json.
CHANNEL_FIELDS = {
    "properties": {
        "sender": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128,
            "description": "Name of the agent contact that wrote the message",
        },
        "kind": {
            "type": "string",
            "enum": ["message", "reply", "ack"],
            "description": "message starts something; reply answers one; ack says you have read one",
        },
        "body": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
            "description": "The message text",
        },
        "recipients": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
            "description": "Agent names the message is for; leave out for everyone in the connection",
        },
        "topic": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128,
            "description": "Short thread name; replies reuse it",
        },
        "in_reply_to": {
            "type": "string",
            "format": "uuid",
            "description": "The id of the message being answered or acknowledged",
        },
        "priority": {
            "type": "string",
            "enum": ["P1", "P2", "P3"],
            "description": "P1 urgent, P2 normal, P3 low",
        },
        "artifacts": {
            "type": "array",
            "maxItems": 32,
            "description": "Files the message points to, shared separately",
            "items": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "version": {
                        "type": "string",
                        "minLength": 1,
                        "description": "File version or content hash, if it matters which one",
                    },
                    "owner": {
                        "type": "string",
                        "format": "uuid",
                        "description": "Fulcra user ID of the account holding the file, if not the sender",
                    },
                },
            },
        },
    },
    "required": ["sender", "kind", "body"],
}

MAX_BODY = CHANNEL_FIELDS["properties"]["body"]["maxLength"]
PRIORITIES = tuple(CHANNEL_FIELDS["properties"]["priority"]["enum"])

# How far back a reply or ack looks for the message it answers.
REPLY_LOOKBACK = datetime.timedelta(days=30)


def _uuid(value: str, what: str) -> str:
    try:
        return str(UUID(value)).lower()
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"{what} must be a UUID, got {value!r}.")


def _channel_id(value: str) -> str | None:
    """`value` as a normalized ``Event/<uuid>``, or None if it isn't one."""
    base, sep, rest = value.partition("/")
    if not sep or base.lower() != "event":
        return None
    try:
        return f"Event/{UUID(rest)}"
    except ValueError:
        return None


def _is_connection_share(share: dict) -> bool:
    return (share.get("datashare_name") or "").startswith(SHARE_NAME_PREFIX)


def _channels(share: dict) -> list[str]:
    return [c for t in share.get("fulcra_data_types") or [] if (c := _channel_id(t))]


def resolve_connection(
    outgoing_shares: list[dict], connection: str
) -> tuple[str, list[str]]:
    """Your channel for a connection, and the user IDs of the people it's
    shared with.

    `connection` is your channel's ID (``Event/<uuid>``) or a person's user ID.
    `outgoing_shares` is ``FulcraAPI.get_datashares()``.
    """
    shares = [s for s in outgoing_shares if _is_connection_share(s)]

    def people(channel: str) -> list[str]:
        found = []
        for share in shares:
            if channel in _channels(share):
                for p in share.get("permissions") or []:
                    if (
                        user := p.get("allowed_fulcra_userid")
                    ) and user.lower() not in found:
                        found.append(user.lower())
        return found

    channel = _channel_id(connection)
    if channel is not None:
        with_people = people(channel)
        if not with_people:
            raise ValueError(
                f"None of your '{SHARE_NAME_PREFIX}: ...' shares includes {channel}. "
                "Use your own channel's ID, after sharing it with the other person."
            )
        return channel, with_people

    try:
        user = _uuid(connection, "connection")
    except ValueError:
        raise ValueError(
            f"connection must be your channel's ID (Event/<uuid>) or the other "
            f"person's Fulcra user ID, got {connection!r}."
        )
    candidates = []
    for share in shares:
        users = {
            (p.get("allowed_fulcra_userid") or "").lower()
            for p in share.get("permissions") or []
        }
        if user in users:
            candidates += [c for c in _channels(share) if c not in candidates]
    if not candidates:
        raise ValueError(
            f"None of your channels is shared with {user} through a "
            f"'{SHARE_NAME_PREFIX}: ...' share. Create a channel and share it "
            "with them first."
        )
    if len(candidates) > 1:
        raise ValueError(
            f"More than one of your channels is shared with {user}: "
            f"{', '.join(candidates)}. Give the channel's ID instead."
        )
    return candidates[0], people(candidates[0])


def peer_channels(
    incoming_grants: list[dict], people: list[str]
) -> list[tuple[str, str]]:
    """The ``(user ID, channel)`` pairs that the people in a connection share
    with you. `incoming_grants` is ``FulcraAPI.get_shared_datasets()``."""
    found = []
    for grant in incoming_grants:
        user = (grant.get("sharing_fulcra_userid") or "").lower()
        if grant.get("grant_type") != "user" or user not in people:
            continue
        if not _is_connection_share(grant):
            continue
        found += [(user, c) for c in _channels(grant) if (user, c) not in found]
    return found


def check_answerable(message: dict | None, message_id: str, kind: str) -> dict:
    """The message a `reply` or `ack` answers, after checking that it can be
    answered. `message` is the record found with `message_id`, or None."""
    if message is None:
        raise ValueError(
            f"No message with id {message_id} from the other people in this "
            f"connection in the last {REPLY_LOOKBACK.days} days. Use the `id` of "
            "their message, as reading their channel shows it."
        )
    if message.get("kind") == "ack":
        raise ValueError(
            f"{message_id} is an ack. Acks aren't answered: they only say a "
            f"message was read. Don't send this {kind}."
        )
    return message


def build_message(
    *,
    sender: str,
    body: str,
    kind: str = "message",
    topic: str | None = None,
    recipients: list[str] | None = None,
    priority: str | None = None,
    in_reply_to: str | None = None,
    record_id: str | None = None,
    sources: list[str] | None = None,
) -> dict:
    """A channel record, checked against `CHANNEL_FIELDS`.

    A `reply` or `ack` needs `in_reply_to`; a `message` mustn't have it.
    """
    if kind not in ("message", "reply", "ack"):
        raise ValueError(f"kind must be message, reply or ack, got {kind!r}.")
    if kind == "message" and in_reply_to is not None:
        raise ValueError("A message that answers another one is a reply or an ack.")
    if kind != "message" and in_reply_to is None:
        article = "An" if kind == "ack" else "A"
        raise ValueError(f"{article} {kind} needs the id of the message it answers.")
    if not (sender or "").strip():
        raise ValueError("The sender (your agent's name) is required.")
    if not (body or "").strip():
        raise ValueError("The message is empty.")
    if len(body) > MAX_BODY:
        raise ValueError(
            f"The message is {len(body)} characters; the most is {MAX_BODY}. Put "
            "longer content in a file, share it with the same people, and send "
            "a short message about it."
        )

    record: dict = {
        "id": _uuid(record_id, "record_id") if record_id else str(uuid4()),
        "sender": sender,
        "kind": kind,
        "body": body,
    }
    if in_reply_to is not None:
        record["in_reply_to"] = _uuid(
            in_reply_to, "The id of the message being answered"
        )
    if topic is not None:
        record["topic"] = topic
    if recipients:
        record["recipients"] = list(recipients)
    if priority is not None:
        record["priority"] = priority
    if sources:
        record["sources"] = list(sources)

    fields = {k: v for k, v in record.items() if k not in ("id", "sources")}
    validator = jsonschema.Draft202012Validator(
        {"type": "object", **CHANNEL_FIELDS, "additionalProperties": False},
        format_checker=jsonschema.FormatChecker(),
    )
    if error := jsonschema.exceptions.best_match(validator.iter_errors(fields)):
        where = ".".join(str(p) for p in error.absolute_path)
        raise ValueError(f"{where + ': ' if where else ''}{error.message}")
    return record


def _find_message(
    source, channels: list[tuple[str, str]], message_id: str, now: datetime.datetime
):
    """The record with `message_id` on any of `channels`, and the channels that
    couldn't be read."""
    unread = []
    for user, channel in channels:
        entry = {
            "id": channel,
            "api_version": "v1",
            "record_spec": {"type": "event"},
            "fulcra_userid": user,
        }
        try:
            found = records.get_records(source, entry, now - REPLY_LOOKBACK, now)
        except HTTPError:
            unread.append(channel)
            continue
        for record in found:
            if str(record.get("id", "")).lower() == message_id:
                return record, unread
    return None, unread


def send_agent_message(
    source,
    connection: str,
    *,
    sender: str,
    body: str,
    topic: str | None = None,
    recipients: list[str] | None = None,
    priority: str | None = None,
    reply_to: str | None = None,
    ack: str | None = None,
    record_id: str | None = None,
    sources: list[str] | None = None,
) -> dict:
    """
    Send a message on your channel for a connection.

    Params:
        source: The FulcraAPI to send through.
        connection: Your channel's ID (``Event/<uuid>``), or the user ID of the
            person you're writing to, when exactly one of your channels is
            shared with them.
        sender: Your agent's name; use the same one every time.
        body: The message text, at most 4000 characters.
        topic: A short thread name. A reply or ack without one reuses the
            topic of the message it answers.
        recipients: Agent names the message is for; leave out for everyone.
        priority: P1 (urgent), P2 or P3.
        reply_to: The id of their message this answers (sends a `reply`).
        ack: The id of their message you've read (sends an `ack`).
        record_id: The message's id. Generated when left out; pass the id from
            a first attempt to retry it without sending it twice.
        sources: Source names to add to the record.

    Returns:
        A dict with the message's ``id``, the ``channel`` it was sent on, the
        ``upload_id``, and the ``record`` as sent.

    Raises:
        ValueError: if the message can't be sent as given; nothing is sent.
    """
    if reply_to is not None and ack is not None:
        raise ValueError("Give reply_to or ack, not both.")
    kind = "reply" if reply_to is not None else "ack" if ack is not None else "message"
    answers = reply_to if reply_to is not None else ack
    if answers is not None:
        answers = _uuid(answers, "The id of the message being answered")

    # Check what can be checked before any request.
    build_message(
        sender=sender,
        body=body,
        kind=kind,
        topic=topic,
        recipients=recipients,
        priority=priority,
        in_reply_to=answers,
        record_id=record_id,
    )

    channel, people = resolve_connection(source.get_datashares(), connection)

    if answers is not None:
        now = datetime.datetime.now(datetime.timezone.utc)
        theirs = peer_channels(source.get_shared_datasets(), people)
        if not theirs:
            raise ValueError(
                "Nobody in this connection shares a channel with you, so there's "
                f"no message of theirs to answer. Send a message instead of a {kind}."
            )
        message, unread = _find_message(source, theirs, answers, now)
        if message is None:
            mine, _ = _find_message(
                source, [(source.get_fulcra_userid(), channel)], answers, now
            )
            if mine is not None:
                raise ValueError(
                    f"{answers} is one of your own messages. Answer theirs: use "
                    "the id of a message on their channel."
                )
            if unread:
                raise ValueError(
                    f"Couldn't find message {answers}: {', '.join(unread)} couldn't "
                    "be read. Try again shortly."
                )
        message = check_answerable(message, answers, kind)
        if topic is None:
            topic = message.get("topic")

    record = build_message(
        sender=sender,
        body=body,
        kind=kind,
        topic=topic,
        recipients=recipients,
        priority=priority,
        in_reply_to=answers,
        record_id=record_id,
        sources=sources,
    )

    # Against the channel's own schema: also refuses a type that isn't yours,
    # or isn't a channel.
    try:
        errors = source.validate_records(channel, [record], "v1")
    except HTTPError as e:
        if e.code == 404:
            raise ValueError(f"{channel} isn't one of your data types.")
        raise
    if unknown := [e for _, _, e in errors if is_unknown_fields_error(e)]:
        raise ValueError(
            f"{channel} isn't a {SHARE_NAME_PREFIX} channel: it has no "
            f"{', '.join(unknown_fields(unknown[0]))} field."
        )
    if errors:
        _, message_text, _ = errors[0]
        raise ValueError(f"{channel} doesn't take this message: {message_text}")

    response = source.record_data_type(channel, [record], "v1")
    return {
        "id": record["id"],
        "channel": channel,
        "upload_id": response.get("upload_id"),
        "record": record,
    }
