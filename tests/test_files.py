"""
Tests for the file-store path handling and console output of the CLI.

Remote Fulcra file paths are API paths, so they must be POSIX-style on every
platform.  An earlier release built them with the platform-flavored
`pathlib.PurePath`, which on Windows produced backslash-separated paths: the
server rejected uploads, and listings/stats silently came back empty.  Because
`PurePosixPath` behaves the same everywhere, these tests simulate Windows by
swapping the platform-flavored class for `PureWindowsPath` -- so they fail on
macOS/Linux too if `PurePath` ever creeps back in.
"""

import io
import pathlib
import urllib.request

import pytest

import fulcra_api.cli.utils
import fulcra_api.core
from fulcra_api.cli.utils import make_filepath, tolerate_unencodable_output

from .conftest import capture_request, offline_client


@pytest.fixture
def windows_paths(monkeypatch):
    """Make any platform-flavored PurePath behave as it would on Windows."""
    monkeypatch.setattr(pathlib, "PurePath", pathlib.PureWindowsPath)
    monkeypatch.setattr(
        fulcra_api.core, "PurePath", pathlib.PureWindowsPath, raising=False
    )
    monkeypatch.setattr(
        fulcra_api.cli.utils, "PurePath", pathlib.PureWindowsPath, raising=False
    )


@pytest.mark.usefixtures("windows_paths")
@pytest.mark.parametrize(
    ("path", "filename", "expected"),
    [
        ("/team/demo", "", "/team/demo"),
        ("team/demo", "", "/team/demo"),
        ("/team/demo", "role.md", "/team/demo/role.md"),
        ("team/demo/", "role.md", "/team/demo/role.md"),
        ("/", "", "/"),
        ("", "", "/"),
    ],
)
def test_make_filepath_is_posix(path, filename, expected):
    result = make_filepath(path, filename)
    assert result == expected
    assert "\\" not in result


@pytest.mark.usefixtures("windows_paths")
def test_resolve_filepath_sends_posix_path_and_name():
    client = offline_client()
    captured = capture_request(client, response=b'{"files": [{"id": "x"}]}')

    client.resolve_filepath("/team/demo/role.md")

    assert captured["path"] == "/input/v1/file_upload"
    assert captured["query"]["path"] == "/team/demo"
    assert captured["query"]["name"] == "role.md"
    for value in captured["query"].values():
        assert "\\" not in value


@pytest.mark.usefixtures("windows_paths")
def test_upload_file_posts_posix_path_and_name(monkeypatch):
    client = offline_client()
    captured = capture_request(client, response=b'{"url": "https://upload.example/x"}')

    class Resp:
        def read(self):
            return b""

    monkeypatch.setattr(urllib.request, "urlopen", lambda req: Resp())

    client.upload_file(io.BytesIO(b"hi"), "text/markdown", 2, "/team/demo/role.md")

    assert captured["path"] == "/input/v1/file_upload"
    assert captured["method"] == "POST"
    assert captured["data"]["path"] == "/team/demo"
    assert captured["data"]["name"] == "role.md"
    for value in (captured["data"]["path"], captured["data"]["name"]):
        assert "\\" not in value


def test_tolerate_unencodable_output_replaces_on_legacy_code_page():
    """Emoji on a cp1252 stream must degrade to '?' rather than raise."""
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    tolerate_unencodable_output(stream)

    stream.write("⬆️ role.md -> fulcra:/team/demo/role.md\n")
    stream.flush()

    assert buffer.getvalue() == b"?? role.md -> fulcra:/team/demo/role.md\n"


def test_tolerate_unencodable_output_leaves_utf8_alone():
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="utf-8")
    tolerate_unencodable_output(stream)

    stream.write("⬆️ ok\n")
    stream.flush()

    assert buffer.getvalue() == "⬆️ ok\n".encode()


def test_tolerate_unencodable_output_ignores_streams_without_reconfigure():
    # StringIO has no reconfigure(); the helper must simply skip it.
    tolerate_unencodable_output(io.StringIO(), None)
