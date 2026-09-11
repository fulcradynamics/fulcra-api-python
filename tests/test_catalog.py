"""Offline tests for the `catalog` command's filtering flags."""

import json

from click.testing import CliRunner

from fulcra_api.cli.commands import catalog

from .conftest import offline_client

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
