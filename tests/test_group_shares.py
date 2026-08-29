"""
Tests for sharing data with a whole data group, rather than with named users.

A datashare carries two independent lists of recipients: `permissions` (named
users) and `group_permissions` (groups).  The server leaves either one alone
when an update doesn't mention it, so most of what's tested here is which keys
end up in the request body.
"""

import datetime

import pytest
from click.testing import CliRunner

from fulcra_api.core import FulcraAPI

from .conftest import offline_client as _base_offline_client

GROUP_ID = "cf362f80-ef41-4c08-b5e3-b18bd3d1524b"
OTHER_GROUP_ID = "1a5b0c9e-3c4d-4e5f-8a9b-0c1d2e3f4a5b"
USER_ID = "a24a9667-c2c6-4bbf-9a0f-4bef0afcb521"
SHARE_ID = "9f8e7d6c-5b4a-4938-8271-605f4e3d2c1b"
GRANT_ID = "7c6d5e4f-3a2b-4c1d-9e8f-7a6b5c4d3e2f"


def offline_client() -> FulcraAPI:
    client = _base_offline_client()
    # create_datashare stamps the sharer's name into the body; the fake token
    # has no claims to read it from.
    client.get_fulcra_userid = lambda: USER_ID
    return client


def capture_request(client: FulcraAPI) -> dict:
    """Point the client's transport at a dict instead of the network."""
    captured: dict = {}

    def fake_fulcra_api(url_path, method="GET", data=None, **kwargs):
        captured["path"] = url_path
        captured["method"] = method
        captured["data"] = data
        return b"{}"

    client.fulcra_api = fake_fulcra_api
    return captured


#
# Offline tests (no authorization required)
#


def test_create_datashare_sends_group_permissions():
    client = offline_client()
    captured = capture_request(client)

    client.create_datashare(
        datashare_name="Step Challenge Share",
        fulcra_data_types=["StepCount"],
        allowed_group_ids=[GROUP_ID],
    )

    assert captured["data"]["group_permissions"] == [{"allowed_group_id": GROUP_ID}]
    # A group-only share names no individual recipients.
    assert captured["data"]["permissions"] == []


def test_create_datashare_can_name_users_and_groups_together():
    client = offline_client()
    captured = capture_request(client)

    client.create_datashare(
        datashare_name="Both",
        fulcra_data_types=["StepCount"],
        allowed_user_ids=[USER_ID],
        allowed_group_ids=[GROUP_ID],
    )

    assert captured["data"]["permissions"] == [{"allowed_fulcra_userid": USER_ID}]
    assert captured["data"]["group_permissions"] == [{"allowed_group_id": GROUP_ID}]


def test_create_datashare_omits_group_permissions_when_not_asked_for():
    """Callers that predate group sharing must send exactly what they used to."""
    client = offline_client()
    captured = capture_request(client)

    client.create_datashare(
        datashare_name="Users Only",
        fulcra_data_types=["StepCount"],
        allowed_user_ids=[USER_ID],
    )

    assert "group_permissions" not in captured["data"]


def update_datashare_body(**kwargs) -> dict:
    """Return the request body a given update_datashare call would send."""
    client = offline_client()
    captured = capture_request(client)
    client.update_datashare(datashare_id=SHARE_ID, **kwargs)
    return captured["data"]


def test_update_datashare_leaves_groups_alone_by_default():
    """
    Omitting the key is what makes the server leave a share's groups alone, so
    an update that doesn't mention groups must not send an empty list.
    """
    assert "group_permissions" not in update_datashare_body()


def test_update_datashare_replaces_groups():
    body = update_datashare_body(allowed_group_ids=[GROUP_ID, OTHER_GROUP_ID])
    assert body["group_permissions"] == [
        {"allowed_group_id": GROUP_ID},
        {"allowed_group_id": OTHER_GROUP_ID},
    ]


@pytest.mark.parametrize("value", [[], None])
def test_update_datashare_clears_groups(value):
    """An explicit empty list -- or None -- stops sharing with every group."""
    assert update_datashare_body(allowed_group_ids=value)["group_permissions"] == []


def test_datashare_methods_use_the_v1_paths():
    """The whole datashare/dataset surface moved to /user/v1."""
    client = offline_client()
    captured = capture_request(client)

    client.create_datashare(datashare_name="n", fulcra_data_types=[])
    assert (captured["path"], captured["method"]) == ("/user/v1/datashare", "POST")

    client.get_datashares()
    assert captured["path"] == "/user/v1/datashare"

    client.get_datashare(SHARE_ID)
    assert captured["path"] == f"/user/v1/datashare/{SHARE_ID}"

    client.delete_datashare(SHARE_ID)
    assert (captured["path"], captured["method"]) == (
        f"/user/v1/datashare/{SHARE_ID}",
        "DELETE",
    )

    client.get_shared_datasets()
    assert captured["path"] == "/user/v1/dataset"

    client.delete_dataset_permission(GRANT_ID)
    assert (captured["path"], captured["method"]) == (
        f"/user/v1/dataset/{GRANT_ID}",
        "DELETE",
    )


def test_update_datashare_sends_only_what_was_passed():
    """
    v1 changes only the fields the request carries, so an update that names
    one field must not resend the others and silently overwrite them.
    """
    assert update_datashare_body(datashare_name="Renamed") == {
        "datashare_name": "Renamed"
    }


@pytest.mark.parametrize("field", ["time_start", "time_end"])
def test_update_datashare_clears_a_time_bound_with_an_explicit_none(field):
    """
    An explicit None has to reach the server as a null: that is what makes the
    share open-ended at that end.  Omitting it leaves the bound alone.
    """
    assert update_datashare_body(**{field: None}) == {field: None}
    assert field not in update_datashare_body()


def test_update_datashare_serializes_a_time_bound():
    when = datetime.datetime(2026, 7, 1, tzinfo=datetime.UTC)
    assert update_datashare_body(time_start=when)["time_start"] == when.isoformat()


def test_list_shared_data_types_request():
    client = offline_client()
    captured: dict = {}

    def fake_fulcra_api(url_path, method="GET", query=None, **kwargs):
        captured["path"] = url_path
        captured["query"] = query
        return b"{}"

    client.fulcra_api = fake_fulcra_api

    client.list_shared_data_types(USER_ID, "2026-08-01T00:00:00Z", "2026-08-08T00:00:00Z")
    assert captured["path"] == f"/user/v1/shared/{USER_ID}/data_types"
    assert captured["query"] == {
        "start_time": "2026-08-01T00:00:00Z",
        "end_time": "2026-08-08T00:00:00Z",
    }


#
# CLI
#


def cli_option_names(command) -> set:
    return {opt for param in command.params for opt in getattr(param, "opts", [])}


def test_share_cli_exposes_group_options():
    from fulcra_api.cli.share import create, update

    assert "--group-id" in cli_option_names(create)
    assert {
        "--add-group-id",
        "--remove-group-id",
        "--set-group-id",
        "--no-group-id",
    } <= cli_option_names(update)


def test_share_create_requires_a_recipient():
    from fulcra_api.cli.share import create

    result = CliRunner().invoke(
        create,
        ["--name", "No Recipients", "--data-type", "StepCount", "--no-validate"],
        obj=offline_client(),
    )
    assert result.exit_code != 0
    assert "at least one --user-id or --group-id" in result.output


def run_share_update(args, current_share=None) -> dict:
    """
    Run `fulcra share update` against a stubbed client, returning the kwargs it
    would have passed to update_datashare.
    """
    from fulcra_api.cli.share import update

    client = offline_client()
    share = current_share or {
        "datashare_id": SHARE_ID,
        "datashare_name": "Share",
        "fulcra_data_types": ["StepCount"],
        "share_all_data": False,
        "time_start": None,
        "time_end": None,
        "permissions": [{"allowed_fulcra_userid": USER_ID}],
        "group_permissions": [{"allowed_group_id": GROUP_ID}],
    }
    captured: dict = {}

    client.get_datashares = lambda: [share]
    client.get_datashare = lambda _id: share

    def fake_update(**kwargs):
        captured.update(kwargs)
        return {}

    client.update_datashare = fake_update

    result = CliRunner().invoke(update, [SHARE_ID, "--no-validate", *args], obj=client)
    if result.exit_code != 0:
        raise AssertionError(f"share update failed: {result.output}")
    return captured


def test_share_update_leaves_groups_alone_unless_asked():
    assert "allowed_group_ids" not in run_share_update(["--name", "Renamed"])


def test_share_update_adds_and_removes_groups():
    kwargs = run_share_update(["--add-group-id", OTHER_GROUP_ID])
    assert kwargs["allowed_group_ids"] == sorted([GROUP_ID, OTHER_GROUP_ID])

    kwargs = run_share_update(["--remove-group-id", GROUP_ID])
    assert kwargs["allowed_group_ids"] == []


def test_share_update_sets_and_clears_groups():
    kwargs = run_share_update(["--set-group-id", OTHER_GROUP_ID])
    assert kwargs["allowed_group_ids"] == [OTHER_GROUP_ID]

    kwargs = run_share_update(["--no-group-id"])
    assert kwargs["allowed_group_ids"] == []
    # Clearing groups must not disturb the individually-shared users, which
    # under a partial update means not mentioning them at all.
    assert "allowed_user_ids" not in kwargs


def test_share_update_rejects_conflicting_group_options():
    from fulcra_api.cli.share import update

    for args in (
        ["--set-group-id", GROUP_ID, "--add-group-id", OTHER_GROUP_ID],
        ["--no-group-id", "--add-group-id", OTHER_GROUP_ID],
    ):
        result = CliRunner().invoke(update, [SHARE_ID, *args], obj=offline_client())
        assert result.exit_code != 0
        assert "cannot be used with" in result.output


#
# Live integration tests
#


def test_group_share_round_trip(fulcra_client):
    """
    Create a group, share into it, and confirm the grant shows up on the share
    and can be removed again without disturbing the rest of the share.
    """
    group = fulcra_client.create_group(
        title="fulcra-api-python group share test",
        responsible_entity="Fulcra Dynamics",
        description="Temporary group created by the test suite; safe to delete.",
        fulcra_data_types=["StepCount"],
        group_url="https://fulcradynamics.com/",
    )
    group_id = group["id"]
    share_id = None

    try:
        share = fulcra_client.create_datashare(
            datashare_name="fulcra-api-python group share test",
            fulcra_data_types=["StepCount"],
            allowed_group_ids=[group_id],
        )["datashare"]
        share_id = share["datashare_id"]
        assert share["group_permissions"] == [{"allowed_group_id": group_id}]

        # The single-share fetch agrees with the listing.
        fetched = fulcra_client.get_datashare(share_id)
        assert fetched["group_permissions"] == [{"allowed_group_id": group_id}]
        assert fetched in fulcra_client.get_datashares()

        # A partial update that only renames must leave everything else --
        # the group grant included -- exactly as it was.
        fulcra_client.update_datashare(
            datashare_id=share_id,
            datashare_name="fulcra-api-python group share test (renamed)",
        )
        renamed = fulcra_client.get_datashare(share_id)
        assert renamed["datashare_name"].endswith("(renamed)")
        assert renamed["group_permissions"] == [{"allowed_group_id": group_id}]
        assert renamed["fulcra_data_types"] == ["StepCount"]

        # Clearing the groups leaves the rest of the share intact.
        fulcra_client.update_datashare(datashare_id=share_id, allowed_group_ids=[])
        cleared = fulcra_client.get_datashare(share_id)
        assert cleared["group_permissions"] == []
        assert cleared["datashare_name"] == renamed["datashare_name"]
        assert cleared["fulcra_data_types"] == ["StepCount"]
    finally:
        if share_id is not None:
            fulcra_client.delete_datashare(share_id)
        fulcra_client.delete_group(group_id)


def test_datashare_with_an_unknown_group_is_rejected(fulcra_client):
    """
    A share naming a group that doesn't exist is refused outright, and no
    half-created share is left behind.
    """
    from urllib.error import HTTPError

    missing_group_id = "11111111-1111-4111-8111-111111111111"
    share_name = "fulcra-api-python unknown group test"

    with pytest.raises(HTTPError) as excinfo:
        fulcra_client.create_datashare(
            datashare_name=share_name,
            fulcra_data_types=["StepCount"],
            allowed_group_ids=[missing_group_id],
        )
    assert excinfo.value.code == 400
    assert missing_group_id in excinfo.value.read().decode("utf-8")

    assert not any(
        s["datashare_name"] == share_name for s in fulcra_client.get_datashares()
    )


def test_list_shared_data_types_for_yourself(fulcra_client):
    """
    Asking about your own data always reports everything shared, with an empty
    type list -- the flag says it all.
    """
    allowed = fulcra_client.list_shared_data_types(
        fulcra_client.get_fulcra_userid(),
        start_time="2026-08-01T00:00:00Z",
        end_time="2026-08-08T00:00:00Z",
    )
    assert allowed == {"all_data_types": True, "fulcra_data_types": []}


def test_list_shared_data_types_reports_nothing_rather_than_failing(fulcra_client):
    """
    A user who shares nothing with you is a normal answer, not an error.
    """
    stranger = "13371337-1337-4337-8337-a102ab7d3ff8"
    allowed = fulcra_client.list_shared_data_types(
        stranger,
        start_time="2026-08-01T00:00:00Z",
        end_time="2026-08-08T00:00:00Z",
    )
    assert allowed == {"all_data_types": False, "fulcra_data_types": []}


def test_shared_datasets_report_their_grant_type(fulcra_client):
    """
    The dataset listing leads with the caller's own data, and every entry says
    where it comes from.
    """
    datasets = fulcra_client.get_shared_datasets()
    assert datasets[0]["grant_type"] == "self"
    assert datasets[0]["sharing_fulcra_userid"] == fulcra_client.get_fulcra_userid()
    for dataset in datasets:
        assert dataset["grant_type"] in ("self", "user", "group")
        if dataset["grant_type"] == "group":
            assert dataset["group_id"] is not None
