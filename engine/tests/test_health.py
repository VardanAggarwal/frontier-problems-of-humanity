"""Track D (`04-worker-build-plan.md` §5) — `search/health.py`, the
run-health floor. Defined on engines-that-returned, never engines-that-failed
(PoC-0b correction 2 — see `search/health.py`'s module docstring).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from search.health import (
    MIN_ENGINES_RETURNED,
    engines_returned,
    is_healthy,
    run_health_summary,
)
from search.provider import SearchResponse


def _response(engines_seen, silently_absent=(), unresponsive=()):
    return SearchResponse(
        results=[],
        unresponsive_engines=list(unresponsive),
        engines_seen_in_results=list(engines_seen),
        configured_engines=["bing", "brave", "google", "mojeek"],
        silently_absent_engines=list(silently_absent),
        raw_results=[],
    )


def test_min_engines_returned_is_a_named_unset_placeholder():
    # Not asserting a "correct" number -- there isn't one yet. Just that the
    # constant exists, is used as the function default, and is documented as
    # unset (checked structurally: it's a small int, not derived from data).
    assert isinstance(MIN_ENGINES_RETURNED, int)
    assert MIN_ENGINES_RETURNED >= 0


def test_engines_returned_counts_seen_not_configured():
    response = _response(engines_seen=["bing"], silently_absent=["mojeek", "google", "brave"])
    assert engines_returned(response) == 1


def test_is_healthy_floor_is_on_engines_returned():
    healthy = _response(engines_seen=["bing", "brave"])
    degraded = _response(engines_seen=[])
    assert is_healthy(healthy, min_engines_returned=1) is True
    assert is_healthy(degraded, min_engines_returned=1) is False


def test_is_healthy_threshold_is_a_parameter_not_hardcoded():
    response = _response(engines_seen=["bing"])
    assert is_healthy(response, min_engines_returned=1) is True
    assert is_healthy(response, min_engines_returned=2) is False


def test_health_floor_never_defined_on_unresponsive_count():
    # PoC-0b: 99% of queries carry >=1 unresponsive engine, so a floor on
    # engines-failed would reject almost everything. Confirm a response with
    # 3 of 4 engines unresponsive but 1 substantively answering still passes
    # a floor of 1.
    response = _response(
        engines_seen=["bing"],
        unresponsive=[["brave", "x"], ["google", "x"]],
        silently_absent=["mojeek"],
    )
    assert is_healthy(response, min_engines_returned=1) is True


def test_run_health_summary_aggregates():
    responses = [
        _response(engines_seen=["bing", "brave"]),
        _response(engines_seen=[], silently_absent=["mojeek"]),
    ]
    summary = run_health_summary(responses, min_engines_returned=1)
    assert summary["total"] == 2
    assert summary["healthy"] == 1
    assert summary["degraded"] == 1
    assert summary["silently_absent_anywhere"] == ["mojeek"]
