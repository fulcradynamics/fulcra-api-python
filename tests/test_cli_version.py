"""PLAT-1005: `fulcra --version` reports the installed package version."""

from click.testing import CliRunner

import fulcra_api.cli as cli_module
from fulcra_api import __version__


def test_version_prints_package_version():
    result = CliRunner().invoke(cli_module.cli, ["--version"])
    assert result.exit_code == 0, result.output
    assert result.output == f"fulcra-api, version {__version__}\n"


def test_version_does_not_touch_credentials(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("--version must not load credentials")

    monkeypatch.setattr(cli_module, "credentials_store", fail)
    result = CliRunner().invoke(
        cli_module.cli, ["--config-path", str(tmp_path / "missing"), "--version"]
    )
    assert result.exit_code == 0, result.output
    assert __version__ in result.output
