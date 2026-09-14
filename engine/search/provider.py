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
from typing import NamedTuple, Optional

# Engine set — frozen by PoC-0. Do not add duckduckgo/qwant back; both are
# structurally blocked from this environment via the only request path
# SearXNG's engine implementations have for them.
CONFIGURED_ENGINES = ("bing", "brave", "google", "mojeek")

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
    """

    def __init__(self, base_url, configured_engines=CONFIGURED_ENGINES, session=None):
        self.base_url = base_url.rstrip("/")
        self.configured_engines = configured_engines
        self._session = session

    def query(self, query_string, **params):
        import requests  # imported lazily so replay-only test runs need no network lib assumption

        session = self._session or requests
        resp = session.get(
            f"{self.base_url}/search",
            params={"q": query_string, "format": "json", **params},
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
