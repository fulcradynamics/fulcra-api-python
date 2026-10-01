"""Offline tests for the `catalog` command's filtering flags."""

import json

from click.testing import CliRunner

from fulcra_api.cli.commands import catalog

from .conftest import capture_request, offline_client

ENTRIES = [
    {"id": "HeartRate", "name": "Heart Rate", "api_version": "v1alpha1", "queryable": True},
    {"id": "SecretType", "name": "Secret", "api_version": "v1alpha1", "queryable": False},
]


def _catalog_client(entries=ENTRIES):
    client = offline_client()
    # Return fresh dicts each call; the command mutates entries in place.
    client.v1_catalog = lambda **kwargs: [dict(e) for e in entries]
    return client


def _ids(output):
    return [json.loads(line)["id"] for line in output.splitlines()]


def test_queryable_flag_drops_non_queryable_types():
    result = CliRunner().invoke(catalog, ["--queryable"], obj=_catalog_client())

    assert result.exit_code == 0, result.output
    assert _ids(result.output) == ["HeartRate"]


def test_without_flag_returns_all_types():
    result = CliRunner().invoke(catalog, [], obj=_catalog_client())

    assert result.exit_code == 0, result.output
    assert _ids(result.output) == ["HeartRate", "SecretType"]


def test_missing_queryable_field_is_treated_as_queryable():
    entries = [{"id": "HeartRate", "name": "Heart Rate", "api_version": "v1alpha1"}]

    result = CliRunner().invoke(catalog, ["--queryable"], obj=_catalog_client(entries))

    assert result.exit_code == 0, result.output
    assert _ids(result.output) == ["HeartRate"]


USER_TYPE = "Event/3982a39a-ed7b-444b-b54d-90134ac46309"
SHARED_TYPE = "Metric/11111111-aaaa-4aaa-8aaa-111111111111"


def test_user_defined_types_are_listed_with_their_ids():
    entries = [
        {"id": "Event", "name": "Event", "api_version": "v1", "queryable": True},
        {
            "id": USER_TYPE,
            "name": "My Event",
            "api_version": "v1",
            "queryable": True,
            "fulcra_userid": "me",
            "categories": ["user_defined"],
        },
        {
            "id": SHARED_TYPE,
            "name": "Their Metric",
            "api_version": "v1",
            "queryable": True,
            "fulcra_userid": "sharer",
            "categories": ["user_defined", "shared_type"],
        },
    ]

    result = CliRunner().invoke(catalog, ["--queryable"], obj=_catalog_client(entries))

    assert result.exit_code == 0, result.output
    assert _ids(result.output) == ["Event", USER_TYPE, SHARED_TYPE]


def test_user_defined_type_schema_path_keeps_its_slash():
    client = offline_client()
    captured = capture_request(client, response=b"{}")

    client.v1_catalog_schema(USER_TYPE, "v1")

    assert captured["path"] == f"/data/v1/catalog/{USER_TYPE}/v1/schema"

