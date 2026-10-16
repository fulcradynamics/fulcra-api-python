"""PLAT-492: `fulcra user-info` leaves out account status, plan and subscription details."""

import json

from click.testing import CliRunner

from fulcra_api.cli.commands import user_info

from .conftest import offline_client

FULL_RESPONSE = {
    "userid": "00000000-1111-4222-8333-444444444444",
    "created": "2024-08-20T19:51:09.123456Z",
    "status": "active",
    "tier": "",
    "preferences": {"timezone": "America/Los_Angeles"},
    "service_status": {
        "is_active": True,
        "service_type": "subscribed_stripe",
        "active_until": "2026-11-01T00:00:00Z",
        "grace_period_ends": "2026-11-08T00:00:00Z",
        "manage_url": "https://portal.fulcradynamics.com",
    },
    "intercom_token": "secret-ish",
}


def test_user_info_leaves_out_account_and_subscription_fields():
    client = offline_client()
    client.get_user_info = lambda: dict(FULL_RESPONSE)

    result = CliRunner().invoke(user_info, [], obj=client)

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "userid": FULL_RESPONSE["userid"],
        "created": FULL_RESPONSE["created"],
        "preferences": FULL_RESPONSE["preferences"],
    }


def test_user_info_keeps_fields_it_does_not_know_about():
    client = offline_client()
    client.get_user_info = lambda: {"userid": "me", "preferences": {}, "new_field": 1}

    result = CliRunner().invoke(user_info, [], obj=client)

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "userid": "me",
        "preferences": {},
        "new_field": 1,
    }
