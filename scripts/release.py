"""Release helpers: version bumps, release-PR checks, and the publish plan for CI.

A release is a PR that bumps the version in pyproject.toml; merging it to main
publishes to PyPI (.github/workflows/release.yml). See RELEASING.md.

Usage:
    # In a release PR: bump pyproject.toml and uv.lock together.
    uv run python scripts/release.py bump 0.1.45

    # What the PR check runs (compares against the PR's base branch).
    python3 scripts/release.py check --base origin/main

    # Used by the release workflow: key=value lines for $GITHUB_OUTPUT.
    python3 scripts/release.py plan

Stdlib only, so CI can run it without installing the project.
"""

import argparse
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "fulcra-api"

VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def parse_version(version: str) -> tuple[int, int, int]:
    """A strict X.Y.Z version as a comparable tuple."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"{version!r} is not an X.Y.Z version")
    major, minor, patch = (int(p) for p in match.groups())
    return major, minor, patch


def pyproject_version(text: str) -> str:
    return tomllib.loads(text)["project"]["version"]


def version_problems(version: str, base_version: str | None = None) -> list[str]:
    """What's wrong with this version, compared with the base branch's."""
    try:
        parse_version(version)
    except ValueError as e:
        return [f"pyproject.toml version: {e}"]
    if base_version is not None and version != base_version:
        if parse_version(version) <= parse_version(base_version):
            return [f"pyproject.toml version {version} must be higher than {base_version}"]
    return []


def bump_pyproject(pyproject: str, version: str) -> str:
    parse_version(version)
    new_pyproject, count = VERSION_LINE.subn(f'version = "{version}"', pyproject, count=1)
    if count != 1:
        raise ValueError("no version line in pyproject.toml")
    return new_pyproject


def pypi_has(version: str) -> bool:
    request = urllib.request.Request(
        f"https://pypi.org/pypi/{PACKAGE}/{version}/json",
        headers={"User-Agent": f"{PACKAGE}-release"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise RuntimeError(f"PyPI returned HTTP {e.code} for {PACKAGE} {version}") from e


def git_show(ref: str, path: str) -> str | None:
    result = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT,
                            capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def cmd_bump(args) -> int:
    path = ROOT / "pyproject.toml"
    path.write_text(bump_pyproject(path.read_text(), args.version))
    subprocess.run(["uv", "lock"], cwd=ROOT, check=True)
    print(f"{PACKAGE} {args.version}. Commit pyproject.toml and uv.lock in a release PR.")
    return 0


def cmd_check(args) -> int:
    version = pyproject_version((ROOT / "pyproject.toml").read_text())
    base_version = None
    if args.base and (text := git_show(args.base, "pyproject.toml")) is not None:
        base_version = pyproject_version(text)
    problems = version_problems(version, base_version)
    for problem in problems:
        print(f"::error::{problem}" if args.github else problem)
    if not problems:
        change = f"{base_version} -> {version}" if base_version not in (None, version) else version
        print(f"OK: {PACKAGE} {change}")
    return 1 if problems else 0


def cmd_plan(args) -> int:
    version = pyproject_version((ROOT / "pyproject.toml").read_text())
    publish = not pypi_has(version)
    print(f"version={version}")
    print(f"publish_pypi={str(publish).lower()}")
    print(f"{PACKAGE} {version}: {'publish' if publish else 'already'} on PyPI", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    bump = sub.add_parser("bump", help="bump the version in pyproject.toml and uv.lock")
    bump.add_argument("version", help="new version, X.Y.Z")
    bump.set_defaults(func=cmd_bump)
    check = sub.add_parser("check", help="check the version against a base ref")
    check.add_argument("--base", help="git ref to compare with, e.g. origin/main")
    check.add_argument("--github", action="store_true", help="emit GitHub annotations")
    check.set_defaults(func=cmd_check)
    sub.add_parser("plan").set_defaults(func=cmd_plan)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
