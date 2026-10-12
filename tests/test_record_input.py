"""Offline tests for how `fulcra record` and `fulcra delete` read JSON input
(PLAT-693): one object, an array of objects, or one object per line, any of
which may span several lines, and a clear error for anything else."""

import click
import pytest
from click.testing import CliRunner

from fulcra_api.cli.record import delete_records, parse_records, record

from .conftest import offline_client

TYPE_ID = "Event/3982a39a-ed7b-444b-b54d-90134ac46309"
ID_A = "43775c1c-4c79-45a5-9370-535719f17233"
ID_B = "514dea97-00c8-4b3c-bbd6-ace002489ca7"


@pytest.mark.parametrize(
    "content, expected",
    [
        ('{"body": "hi"}', [{"body": "hi"}]),
        (
            '{\n  "body": "hi",\n  "kind": "message"\n}',
            [{"body": "hi", "kind": "message"}],
        ),
        ('[{"body": "1"}, {"body": "2"}]', [{"body": "1"}, {"body": "2"}]),
        ('[\n {"body": "1"},\n {"body": "2"}\n]', [{"body": "1"}, {"body": "2"}]),
        ('{"body": "1"}\n{"body": "2"}', [{"body": "1"}, {"body": "2"}]),
        ('{"body": "1"}\n\n  {"body": "2"}  \n', [{"body": "1"}, {"body": "2"}]),
        ("[]", []),
    ],
)
def test_parse_records_accepts_objects_arrays_and_lines(content, expected):
    assert parse_records(content) == expected


@pytest.mark.parametrize(
    "content, message",
    [
        ("5", "The input isn't a JSON object (5)"),
        ('"oops"', 'The input isn\'t a JSON object ("oops")'),
        ("null", "The input isn't a JSON object (null)"),
        ('[{"body": "1"}, 5]', "Item 2 of the array isn't a JSON object (5)"),
        ('{"body": "1"}\n"oops"', 'Line 2 isn\'t a JSON object ("oops")'),
        ('{"body": "1"}\n{"body": oops}', "Invalid JSON on line 2"),
        # a multi-line object with a mistake: the error is placed in the whole
        (
            '{\n  "body": "1"\n  "kind": "message"\n}',
            "Invalid JSON: Expecting ',' delimiter: line 3",
        ),
    ],
)
def test_parse_records_refuses_anything_else_clearly(content, message):
    with pytest.raises(click.ClickException) as raised:
        parse_records(content)
    assert raised.value.message.startswith(message), raised.value.message


def test_long_values_are_shortened_in_the_error():
    with pytest.raises(click.ClickException) as raised:
        parse_records('"' + "x" * 100 + '"')
    assert "..." in raised.value.message and len(raised.value.message) < 120


def _client():
    client = offline_client()
    client.get_fulcra_userid = lambda: "me"
    client.resolve_data_type = lambda *a, **k: [
        {
            "id": TYPE_ID,
            "api_version": "v1",
            "record_spec": {"type": "event"},
            "fulcra_userid": "me",
            "recordable": True,
        }
    ]
    client.validate_records = lambda *a, **k: []
    sent = {}

    def fake_record(data_type, records, api_version):
        sent.update(data_type=data_type, records=records)
        return {"upload_id": "upload-1"}

    client.record_data_type = fake_record
    return client, sent


def test_record_takes_an_object_written_over_several_lines():
    client, sent = _client()
    piped = '{\n  "sender": "alice",\n  "kind": "message",\n  "body": "It\'s \\"7pm\\"\\nok"\n}\n'

    result = CliRunner().invoke(record, [TYPE_ID, "-f", "-"], obj=client, input=piped)

    assert result.exit_code == 0, result.output
    [sent_record] = sent["records"]
    assert sent_record["body"] == 'It\'s "7pm"\nok'
    assert sent_record["sender"] == "alice"


def test_record_refuses_a_non_object_with_a_field_option_cleanly():
    client, sent = _client()

    result = CliRunner().invoke(
        record, [TYPE_ID, "-f", "-", "--body=x"], obj=client, input="5\n"
    )

    assert result.exit_code == 1
    assert "isn't a JSON object" in result.output
    assert not isinstance(result.exception, AttributeError)
    assert sent == {}


def test_delete_takes_a_multi_line_array_of_ids():
    client, sent = _client()
    piped = f'[\n  {{"record_id": "{ID_A}"}},\n  {{"record_id": "{ID_B}"}}\n]\n'

    result = CliRunner().invoke(
        delete_records, [TYPE_ID, "-f", "-"], obj=client, input=piped
    )

    assert result.exit_code == 0, result.output
    assert sent["data_type"] == "DeletedRecord"
    assert [r["record_id"] for r in sent["records"]] == [ID_A, ID_B]
    assert "Deleted 2 records" in result.output


def test_delete_refuses_a_non_object_line_cleanly():
    client, sent = _client()

    result = CliRunner().invoke(
        delete_records, [TYPE_ID, "-f", "-"], obj=client, input="5\n"
    )

    assert result.exit_code == 1
    assert "isn't a JSON object" in result.output
    assert not isinstance(result.exception, TypeError)
    assert sent == {}
