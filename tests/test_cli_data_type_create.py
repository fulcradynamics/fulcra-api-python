"""Offline tests for `data-type create --add-to-timeline`.

Covers the null `selected_metrics_map` bug: a fresh account's stored
preferences carry "selected_metrics_map" as an explicit null rather than
omitting the key, which crashed `.get(info["userid"], [])` with an
AttributeError before the created data type was ever echoed to the user.
"""

import json

from click.testing import CliRunner

from fulcra_api.cli.data_types import data_type_create

from .conftest import offline_client

ANNOTATION = {"id": "ann-123", "annotation_type": "moment", "name": "harness-test"}

# A minimal v1 catalog entry for the "MomentAnnotation" base type, matching
# what data_type_create's own validation requires: exactly one v1alpha1
# entry tagged "base_type" for the given id.
MOMENT_BASE_TYPE = {
    "id": "MomentAnnotation",
    "api_version": "v1alpha1",
    "categories": ["base_type"],
    "record_spec": {"type": "event"},
}


def _client(user_info, ann=None, update_prefs=None):
    """An offline FulcraAPI with the calls data_type_create makes mocked out.

    v1_catalog/get_fulcra_userid are mocked too: the command looks up
    BASE_DATA_TYPE in the catalog before creating anything, and the offline
    client's fake token isn't valid JWT shape, so any un-mocked call that
    tries to decode it for a user id fails with "Token is in an incorrect
    format" rather than the error under test.
    """
    client = offline_client()
    client.v1_catalog = lambda **kwargs: [dict(MOMENT_BASE_TYPE)]
    client.get_fulcra_userid = lambda: "user-1"
    client.create_annotation = lambda **kwargs: dict(ann or ANNOTATION)
    client.get_user_info = lambda: user_info
    client.update_user_preferences = (
        update_prefs if update_prefs is not None else lambda prefs: {}
    )
    return client


def test_null_selected_metrics_map_adds_to_timeline():
    """A fresh account's null selected_metrics_map is treated as empty, not a crash."""
    user_info = {
        "userid": "user-1",
        "preferences": {"selected_metrics_map": None},
    }
    captured = {}

    def update_prefs(prefs):
        captured["prefs"] = prefs
        return {}

    client = _client(user_info, update_prefs=update_prefs)

    result = CliRunner().invoke(
        data_type_create, ["MomentAnnotation", "harness-test", "--add-to-timeline"], obj=client
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output.splitlines()[0]) == ANNOTATION
    assert captured["prefs"] == {
        "selected_metrics_map": {"user-1": ["fulcra_custom_event.ann-123"]}
    }


def test_null_preferences_adds_to_timeline():
    """A null "preferences" key (not just a null selected_metrics_map) is also tolerated."""
    user_info = {"userid": "user-1", "preferences": None}
    client = _client(user_info)

    result = CliRunner().invoke(
        data_type_create, ["MomentAnnotation", "harness-test", "--add-to-timeline"], obj=client
    )

    assert result.exit_code == 0, result.output


def test_timeline_failure_still_reports_created_id_and_exits_nonzero():
    """If the timeline step fails, the created id must already be visible, and

    the command must not exit 0 -- the old behavior silently swallowed this
    error and always reported success.
    """
    user_info = {
        "userid": "user-1",
        "preferences": {"selected_metrics_map": {}},
    }

    def raising_update(prefs):
        raise RuntimeError("backend rejected preferences update")

    client = _client(user_info, update_prefs=raising_update)

    result = CliRunner().invoke(
        data_type_create, ["MomentAnnotation", "harness-test", "--add-to-timeline"], obj=client
    )

    assert result.exit_code != 0
    # The created data type (with its id) must have reached the user despite
    # the timeline step failing, so a retry doesn't create a duplicate.
    assert json.loads(result.output.splitlines()[0]) == ANNOTATION
    assert "ann-123" in result.output
    assert "backend rejected preferences update" in result.output


def test_create_without_add_to_timeline_is_unaffected():
    """The plain create path (no --add-to-timeline) never touches preferences."""
    user_info = {"userid": "user-1", "preferences": None}
    client = _client(user_info)
    client.get_user_info = lambda: (_ for _ in ()).throw(
        AssertionError("get_user_info should not be called without --add-to-timeline")
    )

    result = CliRunner().invoke(
        data_type_create, ["MomentAnnotation", "harness-test"], obj=client
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output.splitlines()[0]) == ANNOTATION
