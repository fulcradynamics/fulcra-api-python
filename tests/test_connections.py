"""Offline tests for sending connect-agents-with-anyone messages (PLAT-696):
the library's `connections` module and `fulcra connection send`."""

import json
import uuid
from urllib.error import HTTPError

import jsonschema
import pytest
from click.testing import CliRunner

from fulcra_api import connections
from fulcra_api.cli.connection import connection
from fulcra_api.core import FulcraAPI

from .conftest import offline_client

ME = "4f7e3d16-62a2-4c70-9511-0aae86a3de44"
BOB = "5ce6549b-91ff-4413-b326-93722f3cbbaf"
CAROL = "9e1c0d3a-2222-4c70-9511-0aae86a3de44"
MY_CHANNEL = "Event/ba11b917-19e4-4346-8d30-1c1233481e73"
MY_OTHER_CHANNEL = "Event/0d901e71-bda6-4a9f-b1c0-0241f4f3130a"
BOB_CHANNEL = "Event/3982a39a-ed7b-444b-b54d-90134ac46309"
THEIR_MESSAGE = "43775c1c-4c79-45a5-9370-535719f17233"
THEIR_ACK = "514dea97-00c8-4b3c-bbd6-ace002489ca7"
MY_MESSAGE = "f3de38e8-627e-59cb-80eb-1d91d5a64e8d"


def outgoing(name, channel, *users):
    return {
        "datashare_name": name,
        "fulcra_data_types": [channel],
        "permissions": [{"allowed_fulcra_userid": u} for u in users],
    }


def incoming(name, channel, user, grant_type="user"):
    return {
        "grant_type": grant_type,
        "datashare_name": name,
        "sharing_fulcra_userid": user,
        "fulcra_data_types": [channel],
    }


class FakeFulcra(FulcraAPI):
    """An offline client, faking just the methods the connections module uses."""

    def __init__(self, outgoing_shares=None, incoming_grants=None, channels=None):
        super().__init__(credentials=offline_client().fulcra_credentials)
        self.outgoing_shares = (
            outgoing_shares
            if outgoing_shares is not None
            else [outgoing("connect-agents-with-anyone: Me with Bob", MY_CHANNEL, BOB)]
        )
        self.incoming_grants = (
            incoming_grants
            if incoming_grants is not None
            else [incoming("connect-agents-with-anyone: Bob with Me", BOB_CHANNEL, BOB)]
        )
        self.channels = channels or {
            BOB_CHANNEL: [
                {
                    "id": THEIR_MESSAGE,
                    "kind": "message",
                    "topic": "dinner",
                    "body": "7?",
                },
                {
                    "id": THEIR_ACK,
                    "kind": "ack",
                    "in_reply_to": MY_MESSAGE,
                    "body": "ok",
                },
            ],
            MY_CHANNEL: [{"id": MY_MESSAGE, "kind": "message", "body": "hi"}],
        }
        self.unreadable = set()
        self.validation_errors = []
        self.sent = []

    def get_fulcra_userid(self):
        return ME

    def get_datashares(self):
        return self.outgoing_shares

    def get_shared_datasets(self):
        return [
            {"grant_type": "self", "sharing_fulcra_userid": ME}
        ] + self.incoming_grants

    def fulcra_v1_records(self, query, fulcra_userid=None):
        [channel] = [c for c in self.channels if c in query]
        if channel in self.unreadable:
            raise HTTPError("url", 403, "Forbidden", {}, None)
        return "\n".join(json.dumps(r) for r in self.channels[channel])

    def validate_records(self, data_type, records, api_version="v1alpha1", **kwargs):
        return self.validation_errors

    def record_data_type(self, data_type, records, api_version):
        self.sent.append((data_type, records, api_version))
        return {"upload_id": "upload-1"}


# resolve_connection


def test_a_channel_id_resolves_to_itself_and_its_people():
    shares = [
        outgoing("connect-agents-with-anyone: Me with Bob", MY_CHANNEL, BOB),
        outgoing("connect-agents-with-anyone: Me with Carol", MY_CHANNEL, CAROL),
    ]
    channel, people = connections.resolve_connection(
        shares, MY_CHANNEL.upper().replace("EVENT", "event")
    )
    assert channel == MY_CHANNEL
    assert people == [BOB, CAROL]


def test_a_user_id_resolves_to_the_one_channel_shared_with_them():
    shares = [
        outgoing("connect-agents-with-anyone: Me with Bob", MY_CHANNEL, BOB),
        outgoing("connect-agents-with-anyone: Me with Carol", MY_OTHER_CHANNEL, CAROL),
    ]
    assert connections.resolve_connection(shares, BOB.upper()) == (MY_CHANNEL, [BOB])


def test_shares_not_named_for_connections_are_ignored():
    shares = [outgoing("my calendar", MY_CHANNEL, BOB)]
    with pytest.raises(ValueError, match="None of your channels is shared with"):
        connections.resolve_connection(shares, BOB)
    with pytest.raises(ValueError, match="None of your .* shares includes"):
        connections.resolve_connection(shares, MY_CHANNEL)


def test_a_user_with_several_channels_needs_the_channel_id():
    shares = [
        outgoing("connect-agents-with-anyone: Me with Bob", MY_CHANNEL, BOB),
        outgoing(
            "connect-agents-with-anyone: Me, Bob and Carol",
            MY_OTHER_CHANNEL,
            BOB,
            CAROL,
        ),
    ]
    with pytest.raises(ValueError) as raised:
        connections.resolve_connection(shares, BOB)
    assert MY_CHANNEL in str(raised.value) and MY_OTHER_CHANNEL in str(raised.value)


@pytest.mark.parametrize("connection", ["bob", "Event/not-a-uuid", "Metric/" + BOB])
def test_a_connection_that_is_neither_id_is_refused(connection):
    with pytest.raises(ValueError, match="channel's ID .* or the other person's"):
        connections.resolve_connection([], connection)


# peer_channels


def test_peer_channels_are_named_user_grants_from_the_connection():
    grants = [
        incoming("connect-agents-with-anyone: Bob with Me", BOB_CHANNEL, BOB),
        incoming(
            "connect-agents-with-anyone: Bob's group", MY_OTHER_CHANNEL, BOB, "group"
        ),
        incoming("Bob's sleep", "Event/" + str(uuid.uuid4()), BOB),
        incoming("connect-agents-with-anyone: Carol with Me", MY_OTHER_CHANNEL, CAROL),
    ]
    assert connections.peer_channels(grants, [BOB]) == [(BOB, BOB_CHANNEL)]


# build_message


def test_build_message_gives_a_new_id_and_only_the_fields_given():
    record = connections.build_message(sender="alice-claude", body="hi")
    assert set(record) == {"id", "sender", "kind", "body"}
    assert record["kind"] == "message"
    assert str(uuid.UUID(record["id"])) == record["id"]


def test_build_message_keeps_a_given_id():
    record = connections.build_message(
        sender="a", body="b", record_id=THEIR_MESSAGE.upper()
    )
    assert record["id"] == THEIR_MESSAGE


def test_build_message_matches_the_channel_fields():
    record = connections.build_message(
        sender="a",
        body="b",
        kind="reply",
        in_reply_to=THEIR_MESSAGE,
        topic="dinner",
        recipients=["bob-claude"],
        priority="P1",
    )
    schema = {"type": "object", **connections.CHANNEL_FIELDS}
    schema["properties"] = {**schema["properties"], "id": {}}
    jsonschema.validate(record, schema)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(body="x" * 4001), "4001 characters; the most is 4000"),
        (dict(body="  \n"), "The message is empty"),
        (dict(sender=" "), "sender .* is required"),
        (dict(kind="reply"), "A reply needs the id"),
        (dict(kind="ack"), "An ack needs the id"),
        (dict(in_reply_to=THEIR_MESSAGE), "is a reply or an ack"),
        (dict(kind="note"), "kind must be"),
        (dict(priority="P9"), "priority: 'P9' is not one of"),
        (dict(topic=""), "topic: '' should be non-empty"),
        (dict(recipients=[""]), "recipients.0"),
        (dict(kind="reply", in_reply_to="nope"), "must be a UUID"),
        (dict(record_id="nope"), "record_id must be a UUID"),
    ],
)
def test_build_message_refuses_what_a_channel_would(kwargs, message):
    args = dict(sender="a", body="b")
    args.update(kwargs)
    with pytest.raises(ValueError, match=message):
        connections.build_message(**args)


# send_agent_message


def test_send_records_the_message_on_your_channel():
    fulcra = FakeFulcra()
    result = connections.send_agent_message(
        fulcra,
        BOB,
        sender="alice-claude",
        body="Dinner Friday?",
        topic="dinner",
        sources=["com.fulcradynamics.cli"],
    )
    [(data_type, [record], api_version)] = fulcra.sent
    assert (data_type, api_version) == (MY_CHANNEL, "v1")
    assert record == {
        "id": result["id"],
        "sender": "alice-claude",
        "kind": "message",
        "body": "Dinner Friday?",
        "topic": "dinner",
        "sources": ["com.fulcradynamics.cli"],
    }
    assert result["channel"] == MY_CHANNEL and result["upload_id"] == "upload-1"


def test_a_reply_answers_their_message_and_reuses_its_topic():
    fulcra = FakeFulcra()
    connections.send_agent_message(
        fulcra, MY_CHANNEL, sender="a", body="7 works", reply_to=THEIR_MESSAGE.upper()
    )
    [(_, [record], _)] = fulcra.sent
    assert record["kind"] == "reply"
    assert record["in_reply_to"] == THEIR_MESSAGE
    assert record["topic"] == "dinner"


def test_an_ack_with_its_own_topic_keeps_it():
    fulcra = FakeFulcra()
    connections.send_agent_message(
        fulcra, BOB, sender="a", body="Got it", ack=THEIR_MESSAGE, topic="other"
    )
    [(_, [record], _)] = fulcra.sent
    assert (record["kind"], record["topic"]) == ("ack", "other")


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(reply_to=THEIR_ACK), "is an ack. Acks aren't answered"),
        (dict(ack=str(uuid.uuid4())), "No message with id .* in the last 30 days"),
        (dict(reply_to=MY_MESSAGE), "one of your own messages"),
        (dict(reply_to=THEIR_MESSAGE, ack=THEIR_MESSAGE), "not both"),
    ],
)
def test_answers_that_cant_be_sent_send_nothing(kwargs, message):
    fulcra = FakeFulcra()
    with pytest.raises(ValueError, match=message):
        connections.send_agent_message(fulcra, BOB, sender="a", body="b", **kwargs)
    assert fulcra.sent == []


def test_an_unreadable_channel_is_reported_not_taken_as_missing():
    fulcra = FakeFulcra()
    fulcra.unreadable.add(BOB_CHANNEL)
    with pytest.raises(ValueError, match=f"{BOB_CHANNEL} couldn't be read"):
        connections.send_agent_message(
            fulcra, BOB, sender="a", body="b", reply_to=str(uuid.uuid4())
        )
    assert fulcra.sent == []


def test_answering_with_no_channel_from_them_is_refused():
    fulcra = FakeFulcra(incoming_grants=[])
    with pytest.raises(ValueError, match="Nobody in this connection shares a channel"):
        connections.send_agent_message(
            fulcra, BOB, sender="a", body="b", reply_to=THEIR_MESSAGE
        )


def test_a_type_without_the_channel_fields_is_refused():
    fulcra = FakeFulcra()
    error = jsonschema.ValidationError(
        "Additional properties are not allowed ('sender' was unexpected)",
        validator="additionalProperties",
        instance={"sender": "a"},
        schema={"properties": {"note": {}}, "additionalProperties": False},
    )
    fulcra.validation_errors = [(0, error.message, error)]
    with pytest.raises(ValueError, match="isn't a connect-agents-with-anyone channel"):
        connections.send_agent_message(fulcra, BOB, sender="a", body="b")
    assert fulcra.sent == []


def test_a_bad_message_is_refused_before_any_request():
    class NoRequests:
        def __getattr__(self, name):
            raise AssertionError(f"{name} called")

    with pytest.raises(ValueError, match="The message is empty"):
        connections.send_agent_message(NoRequests(), BOB, sender="a", body="")


# fulcra connection send


def run_send(fulcra, args, body):
    return CliRunner().invoke(connection, ["send", *args], obj=fulcra, input=body)


def test_cli_sends_the_text_exactly_as_written():
    fulcra = FakeFulcra()
    body = "It's \"7pm\" at Joe's, $40 `cash` $(whoami) C:\\tmp\n\nsecond line\n"

    result = run_send(fulcra, [BOB, "--as", "alice-claude", "--topic", "dinner"], body)

    assert result.exit_code == 0, result.output
    [(_, [record], _)] = fulcra.sent
    # only the heredoc's final line break is dropped
    assert record["body"] == body[:-1]
    assert record["sources"] == ["com.fulcradynamics.cli"]
    printed = json.loads(result.output)
    assert printed["id"] == record["id"]
    assert printed["channel"] == MY_CHANNEL
    assert printed["body"] == body[:-1]
    assert "sources" not in printed


def test_cli_reply_options():
    fulcra = FakeFulcra()
    result = run_send(
        fulcra,
        [
            BOB,
            "--as",
            "a",
            "--reply-to",
            THEIR_MESSAGE,
            "--for",
            "bob-claude",
            "--for",
            "all",
            "--priority",
            "P2",
        ],
        "7 works\n",
    )
    assert result.exit_code == 0, result.output
    [(_, [record], _)] = fulcra.sent
    assert record["recipients"] == ["bob-claude", "all"]
    assert (record["kind"], record["priority"], record["topic"]) == (
        "reply",
        "P2",
        "dinner",
    )


def test_cli_reports_a_refusal_cleanly():
    fulcra = FakeFulcra()
    result = run_send(fulcra, [BOB, "--as", "a", "--ack", THEIR_ACK], "ok\n")
    assert result.exit_code == 1
    assert "Acks aren't answered" in result.output
    assert fulcra.sent == []


def test_cli_needs_a_sender():
    result = run_send(FakeFulcra(), [BOB], "hi\n")
    assert result.exit_code == 2
    assert "--as" in result.output
