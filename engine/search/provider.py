"""Track D (`04-worker-build-plan.md` §5) — the SearXNG adapter.

Frozen contracts this file implements, settled by PoC-0 (`poc/poc0a-results.md`,
`poc/poc0b-results.md`) — not redesigned here:

    SearchResult = (rank, url, title, snippet, native_score | None)

`rank` derives from SearXNG's own `score` field, sorted DESCENDING, never the
JSON list index (verified in PoC-0a: `score` is monotone with agreement, not
a copy of array position). Ties in score keep the response's own order.

Per query, the adapter also records `unresponsive_engines` (shape
`[[engine, reason]]`, as SearXNG reports it), `engines_seen_in_results`
(derived from each result's `engine`/`engines` fields), and
`silently_absent_engines` — engines configured but present in neither of the
above. This last field exists because of PoC-0's central finding: an engine
(`mojeek`, reproduced independently three times — PoC-0a's addendum, PoC-0b's
dry run, PoC-0b's full run) can return zero results while appearing in
*neither* `unresponsive_engines` nor the results' engine fields.
`unresponsive_engines` is a lower bound on failure, not the failure set.

Engine set: `brave`, `google`, `bing`, `mojeek` — frozen by PoC-0.
`duckduckgo` and `qwant` are structurally blocked (CAPTCHA / anti-bot cookie,
independent of any setting this repo controls) and dropped for good; do not
reintroduce them or add a replacement.

Throttle floor: >=2.0s spacing between requests to the same engine (mojeek
suspends after 3-4 rapid requests, `suspended_time=180`, reliable past that
window at >=2.0s). `THROTTLE_FLOOR_S` below carries this number; callers of
the live path are responsible for pacing their own requests at or above it —
this module does not sleep on your behalf, so it stays a pure adapter.

Two modes:
- **Replay** (`ReplayProvider`) — reads a previously recorded PoC-0b response
  file from disk. Zero network. This is what tests use.
- **Live** (`SearxngProvider`) — issues a real HTTP request via `requests`.
  Kept thin: build the URL, GET it, hand the JSON to the same parsing path
  the replay mode uses. Not exercised by the test suite (no network in CI).

Output feeds `search.fuse.fuse()`'s `results_by_query` input shape directly:
`fuse()` wants `{query_id: [result_dict, ...]}` where each dict carries at
least `url` and `score` — exactly what `raw_response["results"]` already is
in the recorded shape, so `SearchResponse.results_for_fuse()` returns that
list unchanged (no reshaping, no renaming).
"""
import json
import time
from typing import NamedTuple, Optional

# Engine set — expanded 2026-09-14 from the original PoC-0 four
# (bing/brave/google/mojeek) after a full-catalog survey (267 engines, via a
# throwaway unrestricted SearXNG instance's /config endpoint) rather than
# hand-picking. Every general/news/science/scientific-publications engine
# with no api_key requirement was live-tested individually against a real
# query and the actor-name query that collapses plain Bing
# ("Mine Labour Protection Campaign Trust Jodhpur silicosis", engine.md #3).
# Full survey results, including everything rejected and why, are in
# `poc/searxng/settings.yml`'s `use_default_settings.engines` comment — do
# not re-derive that list from scratch, read it first.
#
#   general: yandex added. 0-unresponsive, contributing a meaningful share
#   of results with sources the other four missed. `startpage` was tried and
#   RETRACTED — it ships `inactive: true` upstream (Startpage added a
#   proof-of-work CAPTCHA, PR #6669) and SearXNG hard-skips `inactive`
#   engines at registration time; no settings.yml override can enable it.
#   An initial retest wrongly called it working — a methodology bug (results
#   from `google cse`/`duckduckgo` were misattributed to it because the
#   per-result `engine` field was never checked; see settings.yml for the
#   full account). Do not re-add without a SearXNG code change.
#   news: brave.news, google news, bing news, duckduckgo news added.
#   `duckduckgo news` is a DIFFERENT backend from the CAPTCHA'd general
#   `duckduckgo` engine (still dropped) — do not conflate the two, and do
#   not add plain `duckduckgo`/`qwant`/`yahoo` back (all reconfirmed
#   structurally blocked or dead 2026-09-14, see settings.yml).
#   science: pubmed, semantic scholar added (on-topic for the `evidence`
#   family's prevalence/denominator data).
#
# No reddit engine exists in SearXNG's catalog at all — dropped upstream
# after Reddit's 2023 API lockdown, not a config option.
#
# NOTE: `categories` must be sent on every live request (see
# `SearxngProvider.query`'s DEFAULT_CATEGORIES) for the news/science engines
# to be queried at all — SearXNG's `/search` defaults to `general` only.
CONFIGURED_ENGINES = (
    "bing", "brave", "google", "mojeek", "yandex",
    "brave.news", "google news", "bing news", "duckduckgo news",
    "pubmed", "semantic scholar",
    # Added 2026-09-14, live-probed against `poc/searxng/engines-section.yml`:
    # both are enabled there (no `disabled: true`) and requested by
    # `SearxngProvider.DEFAULT_CATEGORIES`'s "science" category, but a raw
    # probe query returned neither in `engines_seen_in_results` NOR in
    # `unresponsive_engines` — invisible to every diagnostic because neither
    # was in this tuple (`silently_absent_engines` only checks configured
    # engines). Same failure shape PoC-0 already named for mojeek: an engine
    # can return zero while appearing in neither field. Both are Google-
    # backed scrapers, so the same-probe `google`/`google news` CAPTCHA
    # suspension is the likely (not yet separately confirmed) cause. Adding
    # them here does not fix the suspension — it makes it visible in
    # `silently_absent_engines` instead of invisible.
    "google scholar", "arxiv",
)

# >=2.0s spacing between requests to the same engine (poc0a-results.md
# Addendum 2). This is a floor on per-request spacing only — a separate,
# unmeasured rolling cumulative-session-volume effect on google/brave was
# observed in PoC-0 and is explicitly left open (§14); this constant does not
# cover it.
THROTTLE_FLOOR_S = 2.0


class SearchResult(NamedTuple):
    rank: int
    url: str
    title: str
    snippet: str
    native_score: Optional[float]


class SearchResponse(NamedTuple):
    """One query's worth of adapter output."""

    results: list  # list[SearchResult], rank-ordered
    unresponsive_engines: list  # [[engine, reason], ...] as SearXNG reports it
    engines_seen_in_results: list
    configured_engines: list
    silently_absent_engines: list
    raw_results: list  # the raw result dicts, for feeding into fuse()

    def results_for_fuse(self):
        """The shape `search.fuse.fuse()`'s `results_by_query` values need:
        a list of dicts each carrying at least `url` and `score`. This is
        `raw_response["results"]` verbatim — no reshaping.
        """
        return self.raw_results


def _engines_seen(raw_results):
    seen = set()
    for res in raw_results:
        engine = res.get("engine")
        if engine:
            seen.add(engine)
        for e in res.get("engines") or []:
            seen.add(e)
    return seen


def parse_raw_response(raw_response, configured_engines=CONFIGURED_ENGINES):
    """Turn one raw SearXNG JSON payload (the `raw_response` key of a
    recorded poc0b file, or a live `.json()` response body) into a
    `SearchResponse`.

    rank is derived from `score` DESCENDING, never list index. Ties keep the
    response's own (stable) order — Python's sort is stable, so a plain
    descending sort on `score` alone preserves original order among ties.
    """
    raw_results = raw_response.get("results") or []
    ranked = sorted(raw_results, key=lambda r: r.get("score", 0.0), reverse=True)

    results = [
        SearchResult(
            rank=idx + 1,
            url=r.get("url"),
            title=r.get("title"),
            snippet=r.get("content"),
            native_score=r.get("score"),
        )
        for idx, r in enumerate(ranked)
    ]

    unresponsive_engines = raw_response.get("unresponsive_engines") or []
    unresponsive_names = {pair[0] for pair in unresponsive_engines if pair}
    seen = _engines_seen(raw_results)

    configured = set(configured_engines)
    silently_absent = sorted(configured - seen - unresponsive_names)

    return SearchResponse(
        results=results,
        unresponsive_engines=unresponsive_engines,
        engines_seen_in_results=sorted(seen),
        configured_engines=sorted(configured),
        silently_absent_engines=silently_absent,
        raw_results=raw_results,
    )


class ReplayProvider:
    """Zero-network adapter: reads a recorded PoC-0b response file and
    reparses it through the same `parse_raw_response` path the live
    provider uses, so replay and live share one parsing contract.

    `responses_dir` holds files shaped like `poc/poc0b-responses/*.json`
    (top-level `raw_response` key nesting the real SearXNG payload).
    """

    def __init__(self, responses_dir, configured_engines=CONFIGURED_ENGINES):
        self.responses_dir = responses_dir
        self.configured_engines = configured_engines

    def query(self, slug, family):
        """Load `<slug>__<family>.json` from `responses_dir` and return a
        `SearchResponse`.
        """
        path = self.responses_dir / f"{slug}__{family}.json"
        with open(path) as f:
            recorded = json.load(f)
        return self.from_recorded(recorded)

    def from_recorded(self, recorded):
        """Parse an already-loaded recorded record (dict with a
        `raw_response` key) into a `SearchResponse`. Recomputes
        `unresponsive_engines` / `engines_seen_in_results` /
        `silently_absent_engines` from `raw_response` rather than trusting
        the recorded top-level copies, so the adapter's own detection logic
        is what's under test, not the PoC harness's.
        """
        configured = recorded.get("configured_engines") or self.configured_engines
        return parse_raw_response(recorded["raw_response"], configured_engines=configured)

    def search(self, family_id, query_string, *, slug=None):
        """Uniform call shape shared with `SearxngProvider.search`, added so
        one call site (`worker/search_stage.py`) can drive either provider
        without knowing which one it holds. A recording is addressed by
        slug+family, not by the text that produced it, so `query_string` is
        accepted (for shape parity) and ignored — this is not a sign the
        replay path is wrong, it is what "replay" means. `slug` is required
        here even though it is optional in the signature, because without it
        there is no file to load."""
        if slug is None:
            raise ValueError(
                "ReplayProvider.search requires slug — a recording is looked "
                "up by slug+family, it has no other address")
        return self.query(slug, family_id)


class SearxngProvider:
    """Live adapter: thin wrapper over a `requests.get` to a local SearXNG
    instance's `/search?format=json` endpoint. Not covered by tests (no
    network in CI) — kept minimal on purpose so there is little surface for
    the live path to diverge from the replay path's parsing.

    Callers are responsible for spacing requests to the same engine at or
    above `THROTTLE_FLOOR_S`; this class does not throttle internally.

    `language` (added 2026-09-14): SearXNG's own `/search` locale param.
    Bing's engine (`bing.py:get_locale_params`/`request`) derives `mkt` /
    `setlang` / `cc` from it and NOTHING ELSE — there is no separate mkt/cc
    override to set at this call site, and passing them directly would be
    ignored (SearXNG doesn't forward arbitrary query params to the upstream
    engine, only ones its own engine code reads off `params["searxng_locale"]`
    via this `language` field). Measured live: unlocalized, a silicosis+India
    query returned 10/10 generic global health pages from Bing; the identical
    query with `language=en-IN` returned 8/8 India-specific occupational-health
    sources (ResearchGate, IJMEDPH, CWEJournal, PMC, Springer). Defaults to
    `en-IN` because this corpus is India-anchored by design (CLAUDE.md
    "Scope: India-anchored") — override per-call only for an explicitly
    non-Indian leaf.
    """

    DEFAULT_LANGUAGE = "en-IN"

    # Added 2026-09-14 alongside the news/science engine expansion — SearXNG's
    # `/search` defaults to `general` only when `categories` is omitted, so
    # without this the news/science engines in CONFIGURED_ENGINES are never
    # actually queried even though `keep_only` allows them. Comma-joined
    # into one param value; SearXNG accepts either a list or a
    # comma-separated string here, this adapter always sends the string.
    DEFAULT_CATEGORIES = ("general", "news", "science", "scientific publications")

    def __init__(self, base_url, configured_engines=CONFIGURED_ENGINES, session=None,
                 language=DEFAULT_LANGUAGE, categories=DEFAULT_CATEGORIES):
        self.base_url = base_url.rstrip("/")
        self.configured_engines = configured_engines
        self._session = session
        self.language = language
        self.categories = categories

    def query(self, query_string, **params):
        import requests  # imported lazily so replay-only test runs need no network lib assumption

        session = self._session or requests
        request_params = {"q": query_string, "format": "json"}
        if self.language:
            request_params["language"] = self.language
        if self.categories:
            request_params["categories"] = ",".join(self.categories)
        request_params.update(params)  # explicit per-call params win, including language=None to disable
        resp = session.get(
            f"{self.base_url}/search",
            params=request_params,
            timeout=30,
        )
        resp.raise_for_status()
        raw_response = resp.json()
        return parse_raw_response(raw_response, configured_engines=self.configured_engines)

    def search(self, family_id, query_string, *, slug=None):
        """Uniform call shape shared with `ReplayProvider.search` — see that
        method's docstring. A live engine is addressed by the query text
        itself, so `family_id` and `slug` are accepted (for shape parity
        with the replay path) and ignored; this is not a sign the live path
        is wrong, it is what "live search" means."""
        return self.query(query_string)


class ThrottledProvider:
    """Wraps any provider (typically `SearxngProvider`) to enforce
    `THROTTLE_FLOOR_S` spacing between `.search()` calls — `SearxngProvider`
    is deliberately thin and does not throttle itself (its own docstring),
    and `worker/search_stage.py:search_sources` calls `.search()` once per
    retrievable family with no pacing of its own, so unwrapped live use from
    the CLI would violate the floor on the second call of every candidate.

    Global spacing, not per-engine: the floor is measured per-engine
    (mojeek suspends after rapid requests to IT specifically), so pacing
    every call at the floor is conservative, not exact — it never
    under-throttles the engine that actually needs it. Sleeps before the
    call, not after, so the first call in a run pays no delay."""

    def __init__(self, inner, floor_s: float = THROTTLE_FLOOR_S, sleep=time.sleep,
                now=time.monotonic):
        self._inner = inner
        self._floor_s = floor_s
        self._sleep = sleep
        self._now = now
        self._last_call: Optional[float] = None

    def search(self, family_id, query_string, *, slug=None):
        if self._last_call is not None:
            wait = self._floor_s - (self._now() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._now()
        return self._inner.search(family_id, query_string, slug=slug)
