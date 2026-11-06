"""`--config-dir` / FULCRA_CONFIG_DIR keep each Fulcra account's login in its own directory."""

import datetime

from click.testing import CliRunner

import fulcra_api.cli as cli_module
from fulcra_api.credentials import FulcraCredentials
from fulcra_api.credentials_store import CredentialsFile
from fulcra_api.oidc import FulcraOIDCProvider


def creds(token: str) -> FulcraCredentials:
    return FulcraCredentials(
        access_token=token,
        access_token_expiration=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=1),
    )


def test_login_saves_to_the_config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        FulcraOIDCProvider, "poll_for_token", lambda self, **kwargs: creds("test-token")
    )

    result = CliRunner().invoke(
        cli_module.cli,
        ["--config-dir", str(tmp_path / "test"), "auth", "login", "--device-code", "x"],
    )

    assert result.exit_code == 0, result.output
    saved = CredentialsFile(tmp_path / "test" / "credentials.json").load()
    assert saved.access_token == "test-token"


def test_commands_use_the_env_config_dir(tmp_path):
    for name in ("knowledge", "test"):
        CredentialsFile(tmp_path / name / "credentials.json").save(
            creds(f"{name}-token")
        )

    result = CliRunner().invoke(
        cli_module.cli,
        ["auth", "print-access-token"],
        env={"FULCRA_CONFIG_DIR": str(tmp_path / "test")},
    )

    assert result.exit_code == 0, result.output
    assert result.output.strip() == "test-token"
