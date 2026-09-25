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


# --- checks before the upload -----------------------------------------------
# These run the real validate_records against a stubbed schema.

from fulcra_api.core import FulcraAPI  # noqa: E402

from .test_record_validation import EVENT_SCHEMA  # noqa: E402

START = "2026-09-25T12:00:00Z"


def _validating_client(entry=None, schema=EVENT_SCHEMA):
    client, sent = _client(entry or _entry(USER_TYPE, "v1", "event"))
    client.validate_records = FulcraAPI.validate_records.__get__(client)
    client.v1_catalog_schema = lambda data_type, api_version: schema
    return client, sent


def test_undeclared_field_warns_and_still_uploads():
    client, sent = _validating_client()

    result = CliRunner().invoke(
        record, [USER_TYPE, f"--start_time={START}", "--mod=typo"], obj=client
    )

    assert result.exit_code == 0, result.output
    assert (
        f"Warning: record 1: field 'mod' isn't part of {USER_TYPE} and will be dropped; "
        "its fields are: details, end_time, id, mood, sources, start_time, tags"
    ) in result.stderr
    assert "Recorded 1 record" in result.stdout
    # sent as given: the server decides what to keep
    assert _fields(sent) == [{"start_time": START, "mod": "typo"}]


def test_each_undeclared_field_is_warned_about_once():
    client, sent = _validating_client()
    piped = "\n".join(
        f'{{"start_time": "{START}", "mod": {i}, "x": 1}}' for i in range(3)
    )

    result = CliRunner().invoke(record, [USER_TYPE], obj=client, input=piped)

    assert result.exit_code == 0, result.output
    assert result.stderr.count("Warning:") == 2
    assert "record 1: field 'mod'" in result.stderr
    assert "record 1: field 'x'" in result.stderr
    assert len(sent["records"]) == 3


def test_value_on_an_event_type_is_warned_about():
    client, sent = _validating_client()

    result = CliRunner().invoke(
        record, [USER_TYPE, "5", f"--start_time={START}"], obj=client
    )

    assert result.exit_code == 0, result.output
    assert "field 'value' isn't part of" in result.stderr
    assert sent


@pytest.mark.parametrize(
    "start_time", ["not a time", "2026-02-30T00:00:00Z", "1790000000"]
)
def test_invalid_timestamp_is_refused_and_nothing_is_sent(start_time):
    client, sent = _validating_client()

    # piped, so the epoch seconds stay a string rather than becoming a number
    result = CliRunner().invoke(
        record, [USER_TYPE], obj=client, input=f'{{"start_time": "{start_time}"}}'
    )

    assert result.exit_code == 1
    assert "Validation error in record 1:" in result.output
    assert "is not a 'date-time'" in result.output
    assert sent == {}


def test_invalid_timestamp_with_an_undeclared_field_is_still_refused():
    client, sent = _validating_client()

    result = CliRunner().invoke(
        record, [USER_TYPE, "--start_time=garbage", "--mod=typo"], obj=client
    )

    assert result.exit_code == 1
    assert "is not a 'date-time'" in result.output
    assert "Warning" not in result.output
    assert sent == {}


@pytest.mark.parametrize(
    "start_time", [f"{START[:-1]}.123456789Z", "2026-09-25T12:00:00+00"]
)
def test_timestamps_the_v1_etl_parses_are_accepted(start_time):
    client, sent = _validating_client()

    result = CliRunner().invoke(
        record, [USER_TYPE, f"--start_time={start_time}"], obj=client
    )

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert _fields(sent) == [{"start_time": start_time}]


def test_hour_only_offset_is_refused_for_v1alpha1_types():
    schema = {
        "type": "object",
        "properties": {
            "value": {"type": "number"},
            "recorded_at": {"type": "string", "format": "date-time"},
            "sources": {"type": "array"},
        },
    }
    entry = _entry(f"NumericAnnotation/{TYPE_UUID}", "v1alpha1", "metric")
    client, sent = _validating_client(entry, schema)

    result = CliRunner().invoke(
        record,
        [entry["id"], "--value=1", "--recorded_at=2026-09-25T12:00:00+00"],
        obj=client,
    )

    assert result.exit_code == 1
    assert "needs minutes for v1alpha1" in result.output
    assert sent == {}


def test_no_validate_skips_every_check():
    client, sent = _validating_client()

    result = CliRunner().invoke(
        record,
        [USER_TYPE, "--no-validate", "--start_time=garbage", "--mod=typo"],
        obj=client,
    )

    assert result.exit_code == 0, result.output
    assert "Warning" not in result.output
    assert _fields(sent) == [{"start_time": "garbage", "mod": "typo"}]
