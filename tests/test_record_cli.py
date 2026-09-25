"""Offline tests for where `fulcra record` sends records."""

import pytest
from click.testing import CliRunner

from fulcra_api.cli.record import record

from .conftest import offline_client

TYPE_UUID = "3982a39a-ed7b-444b-b54d-90134ac46309"


def _client(entry):
    """An offline client that resolves to `entry` and captures the upload."""
    client = offline_client()
    client.get_fulcra_userid = lambda: "me"
    client.resolve_data_type = lambda *a, **k: [entry]
    client.validate_records = lambda *a, **k: []
    sent = {}

    def fake_record(data_type, records, api_version):
        sent.update(data_type=data_type, records=records, api_version=api_version)
        return {"upload_id": "upload-1"}

    client.record_data_type = fake_record
    return client, sent


def _entry(id, api_version, record_type):
    return {
        "id": id,
        "api_version": api_version,
        "record_spec": {"type": record_type},
        "fulcra_userid": "me",
        "recordable": True,
    }


@pytest.mark.parametrize(
    "type_id, record_type",
    [(f"Event/{TYPE_UUID}", "event"), (f"Metric/{TYPE_UUID}", "metric")],
)
def test_v1_user_defined_type_records_go_to_its_full_id(type_id, record_type):
    client, sent = _client(_entry(type_id, "v1", record_type))

    result = CliRunner().invoke(record, [type_id], obj=client, input='{"mood": "calm"}')

    assert result.exit_code == 0, result.output
    # not the base type, which would store them as plain Event/Metric records
    assert sent["data_type"] == type_id
    assert sent["api_version"] == "v1"
    # v1 types aren't linked by an annotation source
    assert not any(
        s.startswith("com.fulcradynamics.annotation.")
        for s in sent["records"][0]["sources"]
    )
    assert f"Recorded 1 record to {type_id}" in result.output


def test_v1alpha1_annotation_records_go_to_the_base_type_with_its_source():
    type_id = f"NumericAnnotation/{TYPE_UUID.upper()}"
    client, sent = _client(_entry(type_id, "v1alpha1", "metric"))

    result = CliRunner().invoke(record, [type_id, "75.5"], obj=client)

    assert result.exit_code == 0, result.output
    assert sent["data_type"] == "NumericAnnotation"
    assert sent["records"][0]["value"] == 75.5
    assert f"com.fulcradynamics.annotation.{TYPE_UUID}" in sent["records"][0]["sources"]
    assert "Recorded 1 record to NumericAnnotation" in result.output


def test_plain_type_records_go_to_the_type():
    client, sent = _client(_entry("Event", "v1", "event"))

    result = CliRunner().invoke(record, ["Event"], obj=client, input='{"note": "x"}')

    assert result.exit_code == 0, result.output
    assert sent["data_type"] == "Event"
    assert sent["records"][0]["sources"] == ["com.fulcradynamics.cli"]


def test_empty_data_type_is_rejected_before_anything_is_sent():
    client, sent = _client(_entry("Event", "v1", "event"))
    client.resolve_data_type = lambda *a, **k: pytest.fail("looked up an empty type")

    result = CliRunner().invoke(record, [""], obj=client, input='{"mood": "calm"}')

    assert result.exit_code == 2
    assert "a data type is required" in result.output
    assert sent == {}


# --- where records come from: field options vs piped stdin -------------------
# CliRunner's stdin is never a terminal, like a script, cron job or CI run.

USER_TYPE = f"Event/{TYPE_UUID}"


def _event_client():
    return _client(_entry(USER_TYPE, "v1", "event"))


def _fields(sent):
    """each sent record without the sources the CLI adds"""
    return [{k: v for k, v in r.items() if k != "sources"} for r in sent["records"]]


def test_field_options_work_when_stdin_is_not_a_terminal_and_empty():
    client, sent = _event_client()

    result = CliRunner().invoke(record, [USER_TYPE, "--mood=calm"], obj=client, input="")

    assert result.exit_code == 0, result.output
    assert _fields(sent) == [{"mood": "calm"}]


def test_field_options_do_not_read_piped_stdin():
    client, sent = _event_client()

    result = CliRunner().invoke(
        record, [USER_TYPE, "--mood=calm"], obj=client, input='{"mood": "piped"}\n'
    )

    assert result.exit_code == 0, result.output
    assert _fields(sent) == [{"mood": "calm"}]


def test_dash_f_dash_merges_field_options_into_piped_records():
    client, sent = _event_client()

    result = CliRunner().invoke(
        record,
        [USER_TYPE, "-f", "-", "--energy=5"],
        obj=client,
        input='{"mood": "calm"}\n{"mood": "happy", "energy": 1}\n',
    )

    assert result.exit_code == 0, result.output
    assert _fields(sent) == [
        {"mood": "calm", "energy": 5},
        {"mood": "happy", "energy": 5},
    ]


def test_piped_records_are_still_read_without_field_options():
    client, sent = _event_client()

    result = CliRunner().invoke(
        record, [USER_TYPE], obj=client, input='{"mood": "calm"}\n{"mood": "happy"}\n'
    )

    assert result.exit_code == 0, result.output
    assert _fields(sent) == [{"mood": "calm"}, {"mood": "happy"}]


def test_empty_pipe_without_field_options_is_still_an_error():
    client, sent = _event_client()

    result = CliRunner().invoke(record, [USER_TYPE], obj=client, input="")

    assert result.exit_code == 1
    assert "No input provided" in result.output
    assert sent == {}


def test_file_with_field_options_is_not_mistaken_for_value(tmp_path):
    records_file = tmp_path / "records.jsonl"
    records_file.write_text('{"mood": "calm"}\n')
    client, sent = _event_client()

    result = CliRunner().invoke(
        record, [USER_TYPE, "-f", str(records_file), "--energy=3"], obj=client
    )

    assert result.exit_code == 0, result.output
    assert _fields(sent) == [{"mood": "calm", "energy": 3}]


def test_value_with_file_is_still_refused():
    client, sent = _event_client()

    result = CliRunner().invoke(
        record, [USER_TYPE, "5", "-f", "-"], obj=client, input="{}"
    )

    assert result.exit_code == 1
    assert "Cannot specify both VALUE and --file" in result.output
