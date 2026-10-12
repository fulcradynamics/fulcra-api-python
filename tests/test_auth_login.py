"""Offline tests for `fulcra auth login`: a login that waits for approval
hides the link from the person who must open it when nobody is at a terminal
(an AI agent's shell, a pipe, a script), so there it prints the link and
exits instead."""

import importlib
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from .conftest import offline_client

# fulcra_api.cli re-exports the `auth` click group, which shadows the module.
auth_module = importlib.import_module("fulcra_api.cli.auth")
login = auth_module.login

DEVICE = (
    "dev-code-123",
    "https://fulcra.example/activate?user_code=ABCD-EFGH",
    "ABCD-EFGH",
    900,
    5,
)


@pytest.fixture
def client(monkeypatch):
    client = offline_client()
    client.oidc = MagicMock()
    client.oidc.get_device_code.return_value = DEVICE

    def authorize(prompt_callback):
        prompt_callback(DEVICE[0], DEVICE[1], DEVICE[2])
        return "creds"

    client.oidc.authorize_via_device_flow.side_effect = authorize
    client.oidc.poll_for_token.return_value = "creds"
    saved = []
    monkeypatch.setattr(auth_module, "save_creds", saved.append)
    monkeypatch.setattr(auth_module.webbrowser, "open_new_tab", lambda uri: None)
    client.saved = saved
    return client


def run(client, args=(), attended=False, monkeypatch=None):
    monkeypatch.setattr(auth_module, "_attended", lambda: attended)
    return CliRunner().invoke(login, list(args), obj=client)


def test_unattended_login_prints_the_link_and_exits(client, monkeypatch):
    result = run(client, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    # the same lines --get-auth-url prints, so anything reading them still works
    assert f"Web auth URL: {DEVICE[1]}" in result.output
    assert f"- Web auth code: {DEVICE[2]}" in result.output
    assert f"- Device code: {DEVICE[0]}" in result.output
    assert "NOTE FOR AI AGENTS AND SCRIPTS" in result.output
    assert f"fulcra-api auth login --device-code {DEVICE[0]}" in result.output
    assert "--wait" in result.output
    # it didn't wait for approval, and saved nothing
    client.oidc.authorize_via_device_flow.assert_not_called()
    client.oidc.poll_for_token.assert_not_called()
    assert client.saved == []


def test_attended_login_waits_for_approval(client, monkeypatch):
    result = run(client, attended=True, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    client.oidc.authorize_via_device_flow.assert_called_once()
    assert DEVICE[1] in result.output and DEVICE[2] in result.output
    assert "(AI agents: show this link and code to the person now" in result.output
    assert "Authorization successful" in result.output
    assert client.saved == ["creds"]


def test_wait_keeps_waiting_when_unattended(client, monkeypatch):
    result = run(client, ["--wait"], monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    client.oidc.authorize_via_device_flow.assert_called_once()
    assert client.saved == ["creds"]


def test_get_auth_url_at_a_terminal_keeps_its_output(client, monkeypatch):
    result = run(client, ["--get-auth-url"], attended=True, monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert "complete authentication with the device code by running" in result.output
    assert "NOTE FOR AI AGENTS" not in result.output
    client.oidc.authorize_via_device_flow.assert_not_called()


def test_device_code_finishes_the_login(client, monkeypatch):
    result = run(client, ["--device-code", DEVICE[0]], monkeypatch=monkeypatch)

    assert result.exit_code == 0, result.output
    assert client.oidc.poll_for_token.call_args.kwargs["device_code"] == DEVICE[0]
    assert client.saved == ["creds"]


@pytest.mark.parametrize(
    "args", [["--wait", "--get-auth-url"], ["--wait", "--device-code", "x"]]
)
def test_wait_conflicts(client, monkeypatch, args):
    result = run(client, args, monkeypatch=monkeypatch)

    assert result.exit_code != 0
    assert "--wait can't be combined" in result.output
    client.oidc.get_device_code.assert_not_called()
