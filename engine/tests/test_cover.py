"""Track D (`04-worker-build-plan.md` §5) — `search/cover.py`'s pure
`cover()`. No network, no model, no database, no pipeline knowledge.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from search.cover import cover
from search.fuse import FusedResult


def fr(url, score, cov):
    return FusedResult(url, score, frozenset(cov))


def test_greedy_picks_max_new_coverage_first():
    ranked = [
        fr("https://a.example", 0.9, {"f1", "f2", "f3"}),
        fr("https://b.example", 0.8, {"f1"}),
        fr("https://c.example", 0.7, {"f4"}),
    ]
    result = cover(ranked, max_sources=2)
    assert result[0] == "https://a.example"  # covers 3 families in one shot
    # second pick should add the only remaining new family (f4), not b
    assert result[1] == "https://c.example"


def test_tie_break_by_rrf_score_then_url():
    # two urls each add the same new coverage (1 family) with equal score
    # -> tie-break by url ascending
    ranked = [
        fr("https://zzz.example", 0.5, {"f1"}),
        fr("https://aaa.example", 0.5, {"f1"}),
    ]
    result = cover(ranked, max_sources=1)
    assert result == ["https://aaa.example"]


def test_tie_break_gain_equal_score_differs():
    ranked = [
        fr("https://low.example", 0.1, {"f1"}),
        fr("https://high.example", 0.9, {"f1"}),
    ]
    result = cover(ranked, max_sources=1)
    assert result == ["https://high.example"]


def test_stops_at_max_sources():
    ranked = [
        fr("https://a.example", 0.9, {"f1"}),
        fr("https://b.example", 0.8, {"f2"}),
        fr("https://c.example", 0.7, {"f3"}),
    ]
    result = cover(ranked, max_sources=2)
    assert len(result) == 2


def test_tops_up_by_score_when_coverage_exhausted_before_max_sources():
    # Only 2 families total, but max_sources=4: after covering both
    # families (2 urls), cover() must keep filling by rrf_score descending
    # so it returns as many urls as top-n would, not fewer.
    ranked = [
        fr("https://a.example", 0.9, {"f1"}),
        fr("https://b.example", 0.8, {"f2"}),
        fr("https://c.example", 0.7, {}),  # adds no new coverage
        fr("https://d.example", 0.6, {}),  # adds no new coverage
    ]
    result = cover(ranked, max_sources=4)
    assert result == [
        "https://a.example",
        "https://b.example",
        "https://c.example",
        "https://d.example",
    ]


def test_never_returns_fewer_urls_than_topn_when_enough_exist():
    ranked = [
        fr("https://a.example", 0.9, {"f1"}),
        fr("https://b.example", 0.8, {"f1"}),
        fr("https://c.example", 0.7, {"f1"}),
    ]
    result = cover(ranked, max_sources=3)
    assert len(result) == 3


def test_determinism_repeated_calls_same_input():
    ranked = [
        fr("https://c.example", 0.5, {"f1", "f2"}),
        fr("https://a.example", 0.5, {"f1"}),
        fr("https://b.example", 0.4, {"f3"}),
    ]
    first = cover(ranked, max_sources=3)
    second = cover(ranked, max_sources=3)
    assert first == second


def test_empty_input():
    assert cover([], max_sources=5) == []


def test_max_sources_zero():
    ranked = [fr("https://a.example", 0.9, {"f1"})]
    assert cover(ranked, max_sources=0) == []


def test_single_query_single_url():
    ranked = [fr("https://only.example", 1.0, {"f1"})]
    assert cover(ranked, max_sources=1) == ["https://only.example"]
