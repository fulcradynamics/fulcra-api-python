from unittest.mock import MagicMock

import click
import pytest

from fulcra_api.cli.utils import resolve_data_type
from fulcra_api.core import FulcraAPI


def _entry(api_version: str, *, recordable: bool, id: str = "HeartRate") -> dict:
    """Build a minimal catalog entry as returned by FulcraAPI.resolve_data_type."""
    return {
        "id": id,
        "api_version": api_version,
        "recordable": recordable,
        "fulcra_userid": "user-1",
    }


def _invoke(callback, value, *, resolved, api_version=None):
    """Run a resolve_data_type callback against a mocked FulcraAPI."""
    api = FulcraAPI()
    api.fulcra_credentials = object()  # truthy, passes the creds guard
    api.resolve_data_type = MagicMock(return_value=resolved)

    @click.command()
    def dummy():
        pass

    ctx = click.Context(dummy, obj=api)
    ctx.params = {"api_version": api_version}
    param = click.Argument(["data_type"])
    return callback(ctx, param, value)


def test_mixed_versions_narrows_to_recordable():
    """v0 (read-only) + v1alpha1 (recordable) resolves to the single writable entry."""
    cb = resolve_data_type(recordable_only=True, api_version_param="api_version")
    result = _invoke(
        cb,
        "HeartRate",
        resolved=[
            _entry("v0", recordable=False),
            _entry("v1alpha1", recordable=True),
        ],
    )
    assert result["api_version"] == "v1alpha1"


def test_v0_dropped_even_when_flagged_recordable():
    """v0 is a legacy read-only API and is excluded even if recordable=True.

    Most v0 types inherit the default recordable=True, so this is the common
    `fulcra record HeartRate` case: v0 + v1alpha1 both recordable.
    """
    cb = resolve_data_type(recordable_only=True, api_version_param="api_version")
    result = _invoke(
        cb,
        "HeartRate",
        resolved=[
            _entry("v0", recordable=True),
            _entry("v1alpha1", recordable=True),
        ],
    )
    assert result["api_version"] == "v1alpha1"


def test_v0_only_recordable_still_raises():
    """A type that exists only under v0 has no valid write target, even if flagged."""
    cb = resolve_data_type(recordable_only=True, api_version_param="api_version")
    with pytest.raises(click.BadParameter) as exc:
        _invoke(
            cb,
            "HeartRate",
            resolved=[_entry("v0", recordable=True)],
        )
    assert "is not recordable" in exc.value.message


def test_multiple_recordable_still_ambiguous():
    """Genuine ambiguity among writable versions still prompts for --api-version."""
    cb = resolve_data_type(recordable_only=True, api_version_param="api_version")
    with pytest.raises(click.BadParameter) as exc:
        _invoke(
            cb,
            "HeartRate",
            resolved=[
                _entry("v1alpha1", recordable=True),
                _entry("v1beta1", recordable=True),
            ],
        )
    assert "matches multiple API versions" in exc.value.message


def test_all_non_recordable_single_raises():
    """A type with only a read-only match raises a clear 'not recordable' error."""
    cb = resolve_data_type(recordable_only=True, api_version_param="api_version")
    with pytest.raises(click.BadParameter) as exc:
        _invoke(
            cb,
            "calendars",
            resolved=[_entry("v0", recordable=False, id="calendars")],
        )
    assert "is not recordable" in exc.value.message


def test_all_non_recordable_multiple_raises():
    """Multiple read-only matches also raise 'not recordable', not the version error."""
    cb = resolve_data_type(recordable_only=True, api_version_param="api_version")
    with pytest.raises(click.BadParameter) as exc:
        _invoke(
            cb,
            "calendars",
            resolved=[
                _entry("v0", recordable=False, id="calendars"),
                _entry("v1", recordable=False, id="calendars"),
            ],
        )
    assert "is not recordable" in exc.value.message


def test_explicit_api_version_recordable_returned():
    """An explicitly selected recordable version is returned unchanged."""
    cb = resolve_data_type(recordable_only=True, api_version_param="api_version")
    result = _invoke(
        cb,
        "HeartRate",
        resolved=[_entry("v1alpha1", recordable=True)],
        api_version="v1alpha1",
    )
    assert result["api_version"] == "v1alpha1"


def test_read_path_not_filtered():
    """Without recordable_only, read commands are unaffected and stay ambiguous."""
    cb = resolve_data_type(api_version_param="api_version")
    with pytest.raises(click.BadParameter) as exc:
        _invoke(
            cb,
            "HeartRate",
            resolved=[
                _entry("v0", recordable=False),
                _entry("v1alpha1", recordable=True),
            ],
        )
    assert "matches multiple API versions" in exc.value.message


def test_single_recordable_happy_path():
    """A single recordable match is returned."""
    cb = resolve_data_type(recordable_only=True, api_version_param="api_version")
    result = _invoke(
        cb,
        "HeartRate",
        resolved=[_entry("v1alpha1", recordable=True)],
    )
    assert result["api_version"] == "v1alpha1"
