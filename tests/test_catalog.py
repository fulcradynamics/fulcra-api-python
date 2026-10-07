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



# --- user-defined data types (PLAT-619) --------------------------------------

MINE = {
    "id": "Event/3982a39a-ed7b-444b-b54d-90134ac46309",
    "name": "Headaches",
    "api_version": "v1",
    "categories": ["user_configured"],
    "recordable": True,
}
# The category's new name (PLAT-375), which the server will send after the rename.
MINE_RENAMED = {
    "id": "Metric/22222222-bbbb-4bbb-8bbb-222222222222",
    "name": "Caffeine",
    "api_version": "v1",
    "categories": ["user_defined"],
    "recordable": True,
}
SHARED = {
    "id": "Event/11111111-aaaa-4aaa-8aaa-111111111111",
    "name": "Their Event",
    "api_version": "v1",
    "categories": ["user_configured", "shared_type"],
    "recordable": False,
}
BASE = {
    "id": "Event",
    "name": "Event",
    "api_version": "v1",
    "categories": ["base_type"],
    "recordable": True,
}
BUILT_IN = {"id": "HeartRate", "name": "Heart Rate", "api_version": "v1alpha1"}
ALL = [MINE, MINE_RENAMED, SHARED, BASE, BUILT_IN]


def _catalog_client_capturing(entries=ALL):
    client = offline_client()
    captured = {}

    def v1_catalog(**kwargs):
        captured.update(kwargs)
        return [dict(e) for e in entries]

    client.v1_catalog = v1_catalog
    return client, captured


def _run(*args):
    client, captured = _catalog_client_capturing()
    result = CliRunner().invoke(catalog, list(args), obj=client)
    assert result.exit_code == 0, result.output
    return _ids(result.output), captured


def test_user_defined_lists_yours_and_shared_under_either_category_name():
    ids, _ = _run("--user-defined")
    assert ids == [MINE["id"], MINE_RENAMED["id"], SHARED["id"]]


def test_user_defined_with_recordable_lists_only_your_own():
    ids, _ = _run("--user-defined", "--recordable")
    assert ids == [MINE["id"], MINE_RENAMED["id"]]


def test_user_defined_combines_with_name_and_api_version():
    assert _run("--user-defined", "-n", "head")[0] == [MINE["id"]]
    assert _run("--user-defined", "--api-version", "v1alpha1")[0] == []


def test_user_defined_passes_user_id_through():
    client, captured = _catalog_client_capturing([SHARED, BUILT_IN])
    peer = "5ce6549b-91ff-4413-b326-93722f3cbbaf"
    result = CliRunner().invoke(catalog, ["--user-defined", "--user-id", peer], obj=client)
    assert result.exit_code == 0, result.output
    assert _ids(result.output) == [SHARED["id"]]
    assert captured["fulcra_userid"] == peer


def test_user_defined_cannot_be_combined_with_base_types():
    client, _ = _catalog_client_capturing()
    result = CliRunner().invoke(catalog, ["--user-defined", "--base-types"], obj=client)
    assert result.exit_code != 0
    assert "can't be combined" in result.output


def test_either_user_defined_category_name_matches_both():
    for name in ("user_defined", "user_configured"):
        ids, captured = _run("-c", name)
        assert ids == [MINE["id"], MINE_RENAMED["id"], SHARED["id"]], name
        # The server's filter matches only one exact name, so don't ask it to.
        assert captured.get("category") is None, name


def test_other_categories_still_filter_on_the_server():
    ids, captured = _run("-c", "base_type")
    assert ids == [BASE["id"]]
    assert captured.get("category") == "base_type"


def test_help_puts_user_defined_up_front():
    result = CliRunner().invoke(catalog, ["--help"])
    assert "--user-defined" in result.output
    assert "fulcra catalog --user-defined" in result.output
    assert "fulcra data-type list" in result.output
