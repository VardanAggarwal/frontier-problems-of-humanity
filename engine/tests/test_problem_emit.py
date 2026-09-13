"""Track A (`04-worker-build-plan.md` §4) — the two pure functions in
`worker/problem_emit.py`. No DB, no network, no model, per §4's contract for
new modules; fixtures under `tests/fixtures/problem_edges.json` are this
track's own, per §4's "no shared golden file."
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from worker import problem_emit

FIXTURES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "problem_edges.json").read_text())


class FakeResolveResult:
    """Stand-in for `resolve.ResolveResult` — only `.decision` is read by
    `decide_problem_edge`, so nothing here touches `resolve.py` or a DB."""
    def __init__(self, decision):
        self.decision = decision


# --------------------------------------------------------- signals_from_edge

def test_signals_from_edge_reads_all_four_when_present():
    signals = problem_emit.signals_from_edge(FIXTURES["with_signals"])
    assert signals == {
        "harmed_population": "stone quarry workers, Rajasthan",
        "magnitude": "uncounted",
        "agent": "silica dust",
        "actionable": "dust suppression and PPE enforcement at quarry sites",
    }


def test_signals_from_edge_defaults_missing_key_to_none_not_absent():
    signals = problem_emit.signals_from_edge(FIXTURES["no_signals"])
    assert set(signals) == set(problem_emit.SIGNAL_KEYS)
    assert all(v is None for v in signals.values())


def test_signals_from_edge_partial_leaves_the_rest_none():
    signals = problem_emit.signals_from_edge(FIXTURES["partial_signals"])
    assert signals["magnitude"] == "uncounted"
    assert signals["harmed_population"] is None
    assert signals["agent"] is None
    assert signals["actionable"] is None


def test_signals_from_edge_uncounted_is_not_coerced_to_none():
    # The spec's key distinction: "uncounted" is a pass, not a missing value
    # — it must survive as the literal string, never collapsed to None.
    signals = problem_emit.signals_from_edge(FIXTURES["partial_signals"])
    assert signals["magnitude"] == "uncounted"
    assert signals["magnitude"] is not None


def test_signals_from_edge_non_dict_signals_value_is_ignored_not_a_crash():
    signals = problem_emit.signals_from_edge(FIXTURES["malformed_signals"])
    assert all(v is None for v in signals.values())


def test_signals_from_edge_missing_signals_key_entirely():
    signals = problem_emit.signals_from_edge({"dst_name": "X"})
    assert all(v is None for v in signals.values())


# --------------------------------------------------------- decide_problem_edge

def test_decide_exact_is_resolve():
    assert problem_emit.decide_problem_edge(FakeResolveResult("exact")) == "resolve"


def test_decide_shortlist_top_is_resolve():
    assert problem_emit.decide_problem_edge(FakeResolveResult("shortlist_top")) == "resolve"


def test_decide_ambiguous_is_escalate():
    assert problem_emit.decide_problem_edge(FakeResolveResult("ambiguous")) == "escalate"


def test_decide_new_is_new():
    assert problem_emit.decide_problem_edge(FakeResolveResult("new")) == "new"
