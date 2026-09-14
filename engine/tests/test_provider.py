"""Track D (`04-worker-build-plan.md` §5) — `search/provider.py`.

Replay-only: zero network. Fixtures are PoC-0b's recorded responses in
`poc/poc0b-responses/` (per the task brief, not copied into
`tests/fixtures/`).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from search.fuse import fuse
from search.provider import (
    CONFIGURED_ENGINES,
    ReplayProvider,
    SearchResponse,
    SearchResult,
    SearxngProvider,
    THROTTLE_FLOOR_S,
    ThrottledProvider,
    parse_raw_response,
)

HERE = pathlib.Path(__file__).parent
POC0B_RESPONSES = HERE.parent / "poc" / "poc0b-responses"


def _provider():
    return ReplayProvider(POC0B_RESPONSES)


# --- replay mode against real recorded files ------------------------------


def test_replay_loads_a_recorded_file():
    provider = _provider()
    response = provider.query("a2p-energy", "identity")
    assert isinstance(response, SearchResponse)
    assert isinstance(response.results, list)
    # PoC-0b's recorded fixtures embed their own `configured_engines` (the
    # original 4-engine PoC-0 set) which `ReplayProvider.from_recorded`
    # honours over the live module default — asserting against the fixture's
    # own recorded value, not the current `CONFIGURED_ENGINES` (expanded
    # 2026-09-14 with news/science engines the PoC-0b run never used).
    assert response.configured_engines == sorted(["bing", "brave", "google", "mojeek"])


def test_replay_over_every_recorded_file_parses_without_error():
    files = sorted(POC0B_RESPONSES.glob("*.json"))
    assert len(files) == 120, "expected the full PoC-0b recorded corpus"
    provider = _provider()
    for path in files:
        slug, family = path.stem.split("__")
        response = provider.query(slug, family)
        assert isinstance(response, SearchResponse)
        for r in response.results:
            assert isinstance(r, SearchResult)


def test_throttle_floor_constant():
    assert THROTTLE_FLOOR_S == 2.0


# --- rank derives from score, never list index ----------------------------


def test_rank_from_score_not_list_index():
    raw_response = {
        "results": [
            {"url": "https://a.example/", "title": "A", "content": "a", "score": 0.1},
            {"url": "https://b.example/", "title": "B", "content": "b", "score": 5.0},
            {"url": "https://c.example/", "title": "C", "content": "c", "score": 1.0},
        ],
        "unresponsive_engines": [],
    }
    response = parse_raw_response(raw_response)
    # list order is a, b, c; score order is b (5.0), c (1.0), a (0.1)
    assert [r.url for r in response.results] == [
        "https://b.example/",
        "https://c.example/",
        "https://a.example/",
    ]
    assert [r.rank for r in response.results] == [1, 2, 3]
    assert response.results[0].native_score == 5.0


def test_rank_ties_keep_response_order():
    raw_response = {
        "results": [
            {"url": "https://first.example/", "title": "F", "content": "f", "score": 1.0},
            {"url": "https://second.example/", "title": "S", "content": "s", "score": 1.0},
        ],
        "unresponsive_engines": [],
    }
    response = parse_raw_response(raw_response)
    assert [r.url for r in response.results] == [
        "https://first.example/",
        "https://second.example/",
    ]


def test_native_score_none_when_absent():
    raw_response = {
        "results": [{"url": "https://a.example/", "title": "A", "content": "a"}],
        "unresponsive_engines": [],
    }
    response = parse_raw_response(raw_response)
    assert response.results[0].native_score is None


# --- silently-absent-engine detection (the reproduced mojeek behaviour) ---


def test_silently_absent_engine_synthetic():
    # mojeek returns zero results and is named in neither unresponsive_engines
    # nor any result's engine/engines field — the exact defect PoC-0 found
    # reproduced three times independently. Pinned to the original 4-engine
    # PoC-0 set explicitly rather than the live CONFIGURED_ENGINES default
    # (expanded 2026-09-14) so this test keeps testing that specific scenario.
    raw_response = {
        "results": [
            {"url": "https://a.example/", "title": "A", "content": "a", "score": 1.0, "engine": "bing", "engines": ["bing"]},
        ],
        "unresponsive_engines": [["google", "Suspended: CAPTCHA"], ["brave", "x"]],
    }
    response = parse_raw_response(raw_response, configured_engines=["bing", "brave", "google", "mojeek"])
    assert response.engines_seen_in_results == ["bing"]
    assert response.silently_absent_engines == ["mojeek"]
    # google and brave are accounted for (named unresponsive), so neither is "silent"
    assert "google" not in response.silently_absent_engines
    assert "brave" not in response.silently_absent_engines


def test_engine_named_unresponsive_is_not_also_silently_absent():
    raw_response = {
        "results": [],
        "unresponsive_engines": [
            ["bing", "x"], ["brave", "x"], ["google", "x"], ["mojeek", "x"],
        ],
    }
    response = parse_raw_response(raw_response, configured_engines=["bing", "brave", "google", "mojeek"])
    assert response.silently_absent_engines == []


def test_silent_absence_reproduced_on_a_real_recorded_file():
    # a2p-energy__failure.json (read directly above via provider) records
    # brave+google unresponsive, only bing seen in results, and mojeek
    # silently absent -- confirm the adapter recomputes this itself rather
    # than trusting the recorded copy.
    provider = _provider()
    response = provider.query("a2p-energy", "failure")
    assert response.engines_seen_in_results == ["bing"]
    assert response.silently_absent_engines == ["mojeek"]


# --- adapter output feeds fuse() unchanged --------------------------------


def test_adapter_output_feeds_fuse_directly():
    provider = _provider()
    slugs_families = [
        ("a2p-energy", "identity"),
        ("a2p-energy", "money"),
        ("a2p-energy", "people"),
    ]
    results_by_query = {}
    for slug, family in slugs_families:
        response = provider.query(slug, family)
        results_by_query[f"{slug}__{family}"] = response.results_for_fuse()

    fused = fuse(results_by_query)  # must not raise, and must return real fusions
    assert isinstance(fused, list)
    if fused:
        assert hasattr(fused[0], "url")
        assert hasattr(fused[0], "rrf_score")
        assert hasattr(fused[0], "coverage_set")


# --- search() — the uniform call shape added for worker/search_stage.py ---


def test_replay_search_delegates_to_slug_family_lookup():
    provider = _provider()
    response = provider.search("identity", "this text is ignored", slug="a2p-energy")
    assert isinstance(response, SearchResponse)
    direct = provider.query("a2p-energy", "identity")
    assert response.results == direct.results


def test_replay_search_requires_slug():
    provider = _provider()
    with pytest.raises(ValueError):
        provider.search("identity", "some query text")


class _StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _StubSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return _StubResponse(self._payload)


def test_searxng_search_passes_rendered_text_through_as_q():
    payload = {"results": [], "unresponsive_engines": []}
    session = _StubSession(payload)
    provider = SearxngProvider("http://localhost:8080", session=session)

    response = provider.search("money", '"Some Actor" funding raised grant crore', slug="some-actor")

    assert isinstance(response, SearchResponse)
    assert len(session.calls) == 1
    url, params, timeout = session.calls[0]
    assert params["q"] == '"Some Actor" funding raised grant crore'
    assert "family" not in params
    assert "slug" not in params


# --- ThrottledProvider: paces .search() at >= THROTTLE_FLOOR_S -------------


class _CountingProvider:
    def __init__(self):
        self.calls = []

    def search(self, family_id, query_string, *, slug=None):
        self.calls.append((family_id, query_string, slug))
        return "response"


def test_throttled_provider_sleeps_no_time_on_the_first_call():
    inner = _CountingProvider()
    clock = [0.0]
    sleeps = []
    wrapped = ThrottledProvider(inner, sleep=sleeps.append, now=lambda: clock[0])

    result = wrapped.search("identity", "q1", slug="s")

    assert result == "response"
    assert sleeps == []
    assert inner.calls == [("identity", "q1", "s")]


def test_throttled_provider_waits_the_remaining_floor_on_a_fast_second_call():
    inner = _CountingProvider()
    clock = [0.0]
    sleeps = []
    wrapped = ThrottledProvider(inner, floor_s=2.0, sleep=sleeps.append, now=lambda: clock[0])

    wrapped.search("identity", "q1", slug="s")
    clock[0] = 0.5  # only 0.5s elapsed, well under the 2.0s floor
    wrapped.search("money", "q2", slug="s")

    assert sleeps == [pytest.approx(1.5)]
    assert len(inner.calls) == 2


def test_throttled_provider_does_not_sleep_when_the_floor_has_already_elapsed():
    inner = _CountingProvider()
    clock = [0.0]
    sleeps = []
    wrapped = ThrottledProvider(inner, floor_s=2.0, sleep=sleeps.append, now=lambda: clock[0])

    wrapped.search("identity", "q1", slug="s")
    clock[0] = 5.0  # well past the floor
    wrapped.search("money", "q2", slug="s")

    assert sleeps == []
