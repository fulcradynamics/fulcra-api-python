"""Offline tests for `build_v1_promql`."""

from datetime import datetime, timedelta, timezone

from fulcra_api.cli.utils import build_v1_promql


def test_builds_anchored_range_vector():
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 6, 2, tzinfo=timezone.utc)

    assert build_v1_promql("HeartRate", start, end) == "HeartRate[86400s] @ 1717286400"


def test_anchors_at_end_time_regardless_of_timezone():
    """The `@` timestamp is a Unix time, so a non-UTC end time still anchors
    at the same instant."""
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end_utc = datetime(2024, 6, 2, tzinfo=timezone.utc)
    end_other = end_utc.astimezone(timezone(timedelta(hours=-7)))

    assert build_v1_promql("HeartRate", start, end_other) == build_v1_promql(
        "HeartRate", start, end_utc
    )


def test_zero_length_window_clamps_to_one_second():
    """A degenerate start == end must not emit an invalid `[0s]` range."""
    t = datetime(2024, 6, 1, tzinfo=timezone.utc)

    assert build_v1_promql("StepCount", t, t) == "StepCount[1s] @ 1717200000"
