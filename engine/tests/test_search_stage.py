"""Tests for `worker/search_stage.py` — track E1, wiring track D's pure
functions into one call that turns a candidate into a confirmed source set.

No network, no database: `search.provider.ReplayProvider` reads the real
PoC-0b fixtures in `poc/poc0b-responses/` (nested under `raw_response`, per
that provider's own contract), and `fetch`/`confirm` are hand-built fakes
matching `worker/fetch.py`/`worker/gate2.py`'s call shapes.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from search.confirm_policy import CONFIRMED, MISMATCH, SEARCH, SEED, UNCERTAIN
from search.provider import ReplayProvider
from worker.config import MAX_SOURCES_REGISTRY, MAX_SOURCES_TRACKED
from worker.depth import REGISTRY_TIER, TRACKED_TIER
from worker.extract_types import ConfirmedSource
from worker.search_stage import render_queries, search_sources

HERE = pathlib.Path(__file__).parent
POC0B_RESPONSES = HERE.parent / "poc" / "poc0b-responses"

NAME = "A2P Energy Solution Pvt Ltd"
SLUG = "a2p-energy"


def _provider():
    return ReplayProvider(POC0B_RESPONSES)


class _FakeFetchResult:
    def __init__(self, text, source_id):
        self.text = text
        self.source_id = source_id


def _fetch_all_confirmed(url):
    """Every URL fetches fine; source_id derived deterministically from url."""
    return _FakeFetchResult(text=f"page text about {url}", source_id=f"src-{url}")


def _confirm_all_confirmed(name, evidence, text):
    return (CONFIRMED, 0.90, "")


# ---------------------------------------------------------------------------
# render_queries
# ---------------------------------------------------------------------------

def test_render_queries_only_retrievable_families():
    queries = render_queries(NAME)
    ids = [q[0] for q in queries]
    assert "failure" not in ids, "failure is retrievable: false, must be excluded"
    assert set(ids) == {"identity", "money", "people", "viability", "reach"}


def test_render_queries_substitutes_name_verbatim():
    queries = dict(render_queries(NAME))
    assert queries["identity"] == f'"{NAME}"'
    assert NAME in queries["money"]


# ---------------------------------------------------------------------------
# search_sources — end to end against real recorded fixtures
# ---------------------------------------------------------------------------

def test_rendered_query_text_reaches_the_provider():
    """The point of this follow-up: families.yaml's query templates must
    actually be what the provider is handed, not dead code bypassed by a
    slug+family shortcut."""
    seen = {}

    class RecordingProvider:
        def search(self, family_id, query_string, *, slug=None):
            seen[family_id] = query_string
            return _provider().search(family_id, query_string, slug=slug)

    search_sources(
        NAME, depth=TRACKED_TIER, provider=RecordingProvider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, log=lambda *a, **k: None,
    )
    expected = dict(render_queries(NAME))
    assert seen == expected, "provider was not handed the rendered query text"


def test_search_sources_returns_confirmed_sources_tracked():
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, log=lambda *a, **k: None,
    )
    assert isinstance(result, list)
    assert result, "expected at least one confirmed source from real fixtures"
    for src in result:
        assert isinstance(src, ConfirmedSource)
        assert src.origin == SEARCH
        assert src.verdict == CONFIRMED
        assert src.text


def test_search_sources_respects_max_sources_cap_tracked_vs_registry():
    tracked = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, log=lambda *a, **k: None,
    )
    registry = search_sources(
        NAME, depth=REGISTRY_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, log=lambda *a, **k: None,
    )
    assert len(tracked) <= MAX_SOURCES_TRACKED
    assert len(registry) <= MAX_SOURCES_REGISTRY
    assert len(registry) <= len(tracked)


def test_explicit_max_sources_overrides_depth_default():
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, max_sources=2, log=lambda *a, **k: None,
    )
    assert len(result) <= 2


def test_unknown_depth_raises():
    with pytest.raises(ValueError):
        search_sources(
            NAME, depth="bogus", provider=_provider(),
            fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
            slug=SLUG,
        )


# ---------------------------------------------------------------------------
# seed URL handling — origin SEED, not double-fetched if also covered
# ---------------------------------------------------------------------------

def test_seed_url_is_origin_seed_and_kept_when_confirmed():
    seed = "https://a2p-energy.example/about"
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, seed_url=seed, log=lambda *a, **k: None,
    )
    seed_sources = [s for s in result if s.url == seed]
    assert len(seed_sources) == 1
    assert seed_sources[0].origin == SEED


def test_seed_url_not_double_fetched_when_also_a_search_result():
    fetch_calls = []

    def counting_fetch(url):
        fetch_calls.append(url)
        return _fetch_all_confirmed(url)

    # First run to discover a real covered search URL for this candidate.
    baseline = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, log=lambda *a, **k: None,
    )
    assert baseline, "need at least one search-sourced url to test dedupe against"
    dup_url = baseline[0].url

    search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=counting_fetch, confirm=_confirm_all_confirmed,
        slug=SLUG, seed_url=dup_url, log=lambda *a, **k: None,
    )
    assert fetch_calls.count(dup_url) == 1, "seed url duplicated into the search set was fetched twice"


# ---------------------------------------------------------------------------
# confirm_policy wiring — NO_VERDICT dropped (the deliberate behaviour change)
# ---------------------------------------------------------------------------

def test_no_text_source_is_dropped_not_passed_through_unconfirmed():
    def fetch_no_text(url):
        return _FakeFetchResult(text=None, source_id=f"src-{url}")

    def confirm_should_never_be_called(name, evidence, text):
        raise AssertionError("confirm must not be called when there is no fetched text")

    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=fetch_no_text, confirm=confirm_should_never_be_called,
        slug=SLUG, log=lambda *a, **k: None,
    )
    assert result == [], "NO_VERDICT sources must be dropped, matching confirm_policy"


def test_mismatch_source_is_dropped():
    def confirm_mismatch(name, evidence, text):
        return (MISMATCH, 0.10, "")

    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=confirm_mismatch,
        slug=SLUG, log=lambda *a, **k: None,
    )
    assert result == []


def test_uncertain_source_is_kept_and_flagged():
    def confirm_uncertain(name, evidence, text):
        return (UNCERTAIN, 0.65, "gate2: cosine in the unresolved middle band")

    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=confirm_uncertain,
        slug=SLUG, log=lambda *a, **k: None,
    )
    assert result, "uncertain must be kept, not dropped"
    for src in result:
        assert src.verdict == UNCERTAIN


def test_dropped_sources_are_logged_not_silent():
    logged = []

    def fetch_no_text(url):
        return _FakeFetchResult(text=None, source_id=f"src-{url}")

    search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=fetch_no_text, confirm=lambda *a: (CONFIRMED, 0.9, ""),
        slug=SLUG, log=logged.append,
    )
    assert any("dropped" in line for line in logged)


# ---------------------------------------------------------------------------
# health — an unhealthy run is logged, not silently dropped from fusion
# ---------------------------------------------------------------------------

def test_unhealthy_response_is_logged_but_still_used():
    # a2p-energy__failure would be excluded anyway (retrievable: false); use
    # a real recorded family known from PoC-0b to run degraded (only one
    # engine returning is common per the fixtures) and confirm it still logs
    # rather than raising or vanishing results.
    logged = []
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, min_engines_returned=99,  # forces every response "unhealthy"
        log=logged.append,
    )
    assert any("unhealthy" in line for line in logged)
    assert result, "an unhealthy-but-present response must still feed fusion, not be dropped"
