"""PLAT-864: every request names the library (and the CLI, or a caller's tool) in its User-Agent."""

import io
import json
import sys
import urllib.request

import pytest
from click.testing import CliRunner

import fulcra_api.cli as cli_module
from fulcra_api import __version__
from fulcra_api.core import FulcraAPI
from fulcra_api.oidc import FulcraOIDCProvider
from fulcra_api.user_agent import build_user_agent, default_user_agent

from .conftest import offline_client

LIBRARY = f"fulcra-api/{__version__} python/{sys.version_info[0]}.{sys.version_info[1]}"


class FakeResponse(io.BytesIO):
    status = 200


def capture_user_agents(monkeypatch, body: dict | None = None) -> list[str | None]:
    """Replace urlopen everywhere and collect the User-Agent of each request."""
    seen: list[str | None] = []

    def fake_urlopen(req, *args, **kwargs):
        # urllib.request.Request stores header names capitalized ("User-agent").
        seen.append(req.get_header("User-agent"))
        return FakeResponse(json.dumps(body or {}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_default_user_agent_names_library_and_python():
    assert default_user_agent() == LIBRARY
    assert build_user_agent() == LIBRARY


def test_api_request_sends_library_user_agent(monkeypatch):
    seen = capture_user_agents(monkeypatch)

    offline_client().fulcra_api("/user/v1alpha1/info")

    assert seen == [LIBRARY]


def test_unauthenticated_request_sends_user_agent(monkeypatch):
    seen = capture_user_agents(monkeypatch)

    offline_client().fulcra_api("/data/v1/catalog", authenticated=False)

    assert seen == [LIBRARY]


def test_caller_token_is_appended_not_substituted(monkeypatch):
    seen = capture_user_agents(monkeypatch)
    client = FulcraAPI(user_agent_extra="my-tool/1.0")
    client.fulcra_credentials = offline_client().fulcra_credentials

    client.fulcra_api("/user/v1alpha1/info")

    assert seen == [f"{LIBRARY} my-tool/1.0"]


def test_subclass_can_set_token_as_class_attribute(monkeypatch):
    class ToolAPI(FulcraAPI):
        user_agent_extra = "tool/2.0 (hosted)"

    seen = capture_user_agents(monkeypatch)
    client = ToolAPI(credentials=offline_client().fulcra_credentials)

    client.fulcra_api("/user/v1alpha1/info")

    assert seen == [f"{LIBRARY} tool/2.0 (hosted)"]
    # The class attribute doesn't leak into the base class.
    assert FulcraAPI.user_agent_extra is None


@pytest.mark.parametrize("bad", ["", "   ", "tool/1.0\r\nX-Injected: 1", "töol/1.0"])
def test_invalid_caller_token_is_rejected(bad):
    with pytest.raises(ValueError):
        FulcraAPI(user_agent_extra=bad)


def test_file_upload_sends_user_agent(monkeypatch):
    seen = capture_user_agents(monkeypatch, {"url": "https://upload.example/x"})
    client = offline_client()

    client.upload_file(io.BytesIO(b"hello"), "text/plain", 5, "/notes/hello.txt")

    # One request creates the upload, the second sends the bytes.
    assert seen == [LIBRARY, LIBRARY]


def test_oidc_requests_send_user_agent(monkeypatch):
    seen = capture_user_agents(
        monkeypatch,
        {
            "device_code": "dc",
            "verification_uri_complete": "https://auth.example/activate",
            "user_code": "ABCD",
            "expires_in": 600,
            "interval": 5,
            "access_token": "tok",
        },
    )
    client = FulcraAPI(user_agent_extra="my-tool/1.0")

    client.oidc.get_device_code()
    client.oidc.get_token("refresh_token", {"refresh_token": "rt"})

    assert seen == [f"{LIBRARY} my-tool/1.0"] * 2


def test_oidc_provider_defaults_to_library_user_agent():
    provider = FulcraOIDCProvider(
        domain="auth.example", client_id="cid", scope="openid", audience="aud"
    )
    assert provider.user_agent == LIBRARY


def test_cli_adds_its_own_token(monkeypatch):
    created: list[dict] = []

    # Commands look the client up by type, so this has to be a FulcraAPI.
    class RecordingAPI(FulcraAPI):
        def __init__(self, **kwargs):
            created.append(kwargs)
            super().__init__(**kwargs)

        def get_user_info(self):
            return {"userid": "me"}

    monkeypatch.setattr(cli_module, "FulcraAPI", RecordingAPI)
    monkeypatch.setattr(cli_module, "ensure_config_directory", lambda: None)
    monkeypatch.setattr(
        cli_module, "load_creds", lambda: offline_client().fulcra_credentials
    )

    result = CliRunner().invoke(cli_module.cli, ["user-info"])

    assert result.exit_code == 0, result.output
    assert created[0]["user_agent_extra"] == f"fulcra-cli/{__version__}"
