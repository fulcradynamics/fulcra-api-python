"""scripts/release.py: the version check a release PR must pass, and the bump."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
assert _spec and _spec.loader
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


def test_the_repos_own_version_is_valid():
    version = release.pyproject_version((ROOT / "pyproject.toml").read_text())
    assert release.version_problems(version) == []


def test_an_unchanged_version_passes():
    assert release.version_problems("0.1.44", "0.1.44") == []


def test_a_bumped_version_passes():
    assert release.version_problems("0.1.45", "0.1.44") == []
    assert release.version_problems("0.2.0", "0.1.44") == []


@pytest.mark.parametrize("version", ["0.1.43", "0.0.99"])
def test_a_lower_version_is_refused(version):
    assert release.version_problems(version, "0.1.44") == [
        f"pyproject.toml version {version} must be higher than 0.1.44"
    ]


@pytest.mark.parametrize("version", ["0.1", "0.1.45rc1", "v0.1.45"])
def test_a_malformed_version_is_refused(version):
    problems = release.version_problems(version, "0.1.44")
    assert len(problems) == 1 and "is not an X.Y.Z version" in problems[0]


def test_versions_compare_numerically():
    assert release.parse_version("0.1.100") > release.parse_version("0.1.99")


def test_bump_changes_only_the_project_version():
    pyproject = (
        '[project]\nname = "fulcra-api"\nversion = "0.1.44"\n\n'
        '[tool.other]\nversion = "9"\n'
    )
    bumped = release.bump_pyproject(pyproject, "0.1.45")
    assert release.pyproject_version(bumped) == "0.1.45"
    assert 'version = "9"' in bumped


def test_bump_refuses_a_malformed_version():
    with pytest.raises(ValueError):
        release.bump_pyproject('[project]\nversion = "0.1.44"\n', "0.1")
