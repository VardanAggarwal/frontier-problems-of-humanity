"""Track E1 (`04-worker-build-plan.md` §5) — the search stage.

Wires track D's already-shipped pure functions (`search/provider.py`,
`search/fuse.py`, `search/cover.py`, `search/health.py`,
`search/confirm_policy.py`) into one call that turns a candidate name into a
confirmed source set: render queries -> search -> fuse -> cover -> fetch ->
gate 2 -> confirm_policy. This module does not know the database exists —
`fetch` and `confirm` are injected callables, not `worker/fetch.py:fetch()`
and `worker/gate2.py:confirm()` themselves (those take a `sqlite3.Connection`
first; the caller that DOES know about the database binds it away, e.g. with
`functools.partial`, before passing either in here).

This closes "Two holes found by the user" item 1 (`04-worker-build-plan.md`
§5): today `worker/worker.py:495-521` runs gate 2 only on the seed URL and
lets every search-sourced URL through unconfirmed. Every source this module
returns, seed or search, has passed `confirm_policy.apply_confirmations`.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Callable, Optional

import yaml

from search.confirm_policy import (
    DROP,
    PROMPT,
    SEARCH,
    SEED,
    VERIFY,
    THIN_PAGE_CHARS,
    SourceVerdict,
    apply_confirmations,
)
from search.cover import cover
from search.fuse import fuse, normalize_url
from search.health import MIN_ENGINES_RETURNED, engines_returned, is_healthy
from worker.config import MAX_SOURCES_REGISTRY, MAX_SOURCES_TRACKED
from worker.depth import REGISTRY_TIER, TRACKED_TIER
from worker.extract_types import ConfirmedSource

DEFAULT_FAMILIES_PATH = Path(__file__).resolve().parents[1] / "search" / "families.yaml"

# A local copy of `worker/resolve.py`'s `_slugify`, not an import of it: that
# module also imports `store.db` and `embed.index` (real DB/model surface),
# and this module's whole point is to stay reachable with no database in the
# room. Same algorithm, kept in sync only by inspection since it is five
# lines and unlikely to drift.
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_SLUG_EDGE = re.compile(r"^-+|-+$")


def _slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    s = _SLUG_STRIP.sub("-", s.lower())
    s = re.sub(r"-{2,}", "-", s)
    return _SLUG_EDGE.sub("", s) or "entity"


def _load_retrievable_families(families_path, kind: str = "actor") -> list[dict]:
    with open(families_path) as f:
        doc = yaml.safe_load(f)
    return [fam for fam in doc["families"]
            if fam.get("retrievable") and fam.get("kind", "actor") == kind]


def render_queries(name: str, families_path=None, kind: str = "actor") -> list[tuple[str, str]]:
    """[(family_id, rendered_query_string), ...] for every `retrievable:
    true` family of the given candidate `kind` in `families.yaml`. `{name}`
    is substituted verbatim — `search/families.yaml`'s own contract, not
    reinterpreted here. `kind` defaults to `"actor"` for backward
    compatibility with callers that predate the `problem` family set
    (2026-09-14) — every family in the registry from before that date is
    tagged `kind: actor`."""
    families = _load_retrievable_families(families_path or DEFAULT_FAMILIES_PATH, kind)
    return [(fam["id"], fam["query_template"].format(name=name)) for fam in families]


def _resolve_max_sources(depth: str, max_sources: Optional[int]) -> int:
    if max_sources is not None:
        return max_sources
    if depth == TRACKED_TIER:
        return MAX_SOURCES_TRACKED
    if depth == REGISTRY_TIER:
        return MAX_SOURCES_REGISTRY
    raise ValueError(
        f"unknown depth {depth!r}, expected {TRACKED_TIER!r} or {REGISTRY_TIER!r}")


def search_sources(
        name: str,
        *,
        depth: str,
        kind: str = "actor",
        provider,
        fetch: Callable,
        confirm: Callable,
        evidence: str = "",
        seed_url: Optional[str] = None,
        max_sources: Optional[int] = None,
        slug: Optional[str] = None,
        families_path=None,
        min_engines_returned: Optional[int] = None,
        thin_page_chars: Optional[int] = THIN_PAGE_CHARS,
        counters: Optional[dict] = None,
        unverified: Optional[list] = None,
        log: Callable = print,
) -> list:
    """name -> a confirmed `list[ConfirmedSource]`, ready for E3's passage
    assembly.

    `kind` — the candidate's `kind` (`"problem"` or `"actor"`), selecting
    which family set in `families.yaml` renders the queries. Defaults to
    `"actor"` for callers that predate the `problem` family set
    (2026-09-14); the real caller (`worker/worker.py`) passes the
    candidate's own `kind`.

    `provider` — an object shaped like `search.provider.ReplayProvider` /
    `SearxngProvider`, injected rather than constructed here. Driven through
    `provider.search(family_id, query_string, slug=...)` — the uniform
    method added to both providers precisely because their existing
    `query()` methods are keyed on genuinely different things (a recording
    by slug+family, a live engine by text) and neither should be bent to
    match the other. `search()` lets this one call site drive both without
    knowing which it holds; each provider ignores the argument it doesn't
    need.

    `fetch` — `url -> FetchResult`-shaped (`.text`, `.source_id`), e.g.
    `functools.partial(worker.fetch.fetch, conn, corpus)`.

    `confirm` — `(name, evidence, text) -> (verdict, cosine, note)`, e.g.
    `functools.partial(worker.gate2.confirm, conn)`.

    `max_sources`, when left `None`, resolves from `depth` via
    `worker.config.MAX_SOURCES_TRACKED` / `MAX_SOURCES_REGISTRY`
    (`03-worker.md` §7's constants table). The cap governs `cover()`'s
    search-sourced picks only — the candidate's own `seed_url`, when
    present, is fetched and confirmed in addition to the capped search set,
    not counted against it, because it is not a `cover()` output at all.

    `thin_page_chars` defaults to the policy's measured value rather than
    to None, so the rule is ON unless a caller explicitly passes None to
    switch it off — None is the policy's own "no length rule" sentinel, and
    defaulting to it here silently disabled a threshold the policy had
    already set.

    `min_engines_returned` / `thin_page_chars` are passed straight through to
    `search.health.is_healthy` / `search.confirm_policy.apply_confirmations`
    — both are named, documented-unset placeholders in the modules that own
    them (`health.py`'s `MIN_ENGINES_RETURNED`, `confirm_policy.py`'s
    `THIN_PAGE_CHARS`), not thresholds invented here. Leaving both `None`
    (the default) defers to those modules' own defaults.
    """
    resolved_slug = slug or _slugify(name)
    cap = _resolve_max_sources(depth, max_sources)
    floor = MIN_ENGINES_RETURNED if min_engines_returned is None else min_engines_returned

    # --- 1-2. render + run queries, checked against the health floor -------
    # `render_queries` is the live path, not a spare — it is what puts the
    # PoC-0b-derived query text in front of the provider at all. Do not
    # replace this with a direct families.yaml read that skips it.
    results_by_query = {}
    for family_id, query_string in render_queries(
            name, families_path or DEFAULT_FAMILIES_PATH, kind=kind):
        response = provider.search(family_id, query_string, slug=resolved_slug)
        if not is_healthy(response, floor):
            log(
                f"search_stage: unhealthy search response for "
                f"{resolved_slug}/{family_id} "
                f"(engines_returned={engines_returned(response)} < floor={floor}); "
                "using it anyway rather than silently dropping it"
            )
        results_by_query[family_id] = response.results_for_fuse()

    # --- 3. fuse + cover -----------------------------------------------------
    fused = fuse(results_by_query)
    covered_urls = cover(fused, cap)

    # --- 4. fetch: seed is SEED, everything from search is SEARCH ----------
    to_fetch = []  # [(url, origin), ...]
    seen_norm = set()
    if seed_url:
        to_fetch.append((seed_url, SEED))
        seen_norm.add(normalize_url(seed_url))
    for url in covered_urls:
        norm = normalize_url(url)
        if norm in seen_norm:
            continue
        to_fetch.append((url, SEARCH))
        seen_norm.add(norm)

    verdicts = []
    texts_by_source_id = {}
    for url, origin in to_fetch:
        result = fetch(url)
        text = result.text
        texts_by_source_id[result.source_id] = text
        if not text:
            # No fetched text to confirm against at all (blocked fetch, empty
            # page). Recorded as NO_VERDICT (verdict=None) rather than calling
            # `confirm` on empty text — confirm_policy.SourceVerdict's own
            # contract for this case.
            verdicts.append(SourceVerdict(
                source_id=result.source_id, url=url, origin=origin, verdict=None))
            continue
        verdict, cosine, note = confirm(name, evidence, text)
        verdicts.append(SourceVerdict(
            source_id=result.source_id, url=url, origin=origin,
            verdict=verdict, cosine=cosine, note=note, text_chars=len(text)))

    # --- 5-6. confirm_policy decides who stays. Deliberate behaviour change
    # adopted at integration (04-worker-build-plan.md §5, hole #1, and this
    # task's brief): today's worker.py lets a no-text candidate through to
    # extraction unconfirmed (`if text:` guard at worker.py:496-499).
    # confirm_policy.apply_confirmations drops NO_VERDICT outright, and that
    # is the behaviour this module wires — it does not special-case NO_VERDICT
    # back into "let it through" the way worker.py does today.
    decisions = apply_confirmations(verdicts, thin_page_chars=thin_page_chars)

    # --- 7. route the survivors --------------------------------------------
    # Three destinations now, not two (`confirm_policy`'s PROMPT/VERIFY/DROP,
    # 2026-09-14). Only PROMPT sources are returned as the confirmed set. The
    # VERIFY bucket — gate-2 `uncertain`, plus confirmed-but-thin — is handed
    # back through the optional `unverified` list rather than widened into the
    # return type, the same in-place convention `counters` already uses below
    # and for the same reason: every existing caller keeps working, and a
    # caller that does not ask for the bucket cannot accidentally put it in
    # the extraction prompt.
    confirmed, to_verify = [], []
    for decision in decisions:
        if decision.route == DROP:
            log(f"search_stage: dropped {decision.url} ({decision.origin}): {decision.reason}")
            continue
        source = ConfirmedSource(
            source_id=decision.source_id,
            url=decision.url,
            text=texts_by_source_id.get(decision.source_id) or "",
            origin=decision.origin,
            verdict=decision.verdict,
        )
        if decision.route == PROMPT:
            confirmed.append(source)
        else:
            log(f"search_stage: to verify {decision.url} "
                f"({decision.origin}): {decision.reason}")
            to_verify.append(source)
    if unverified is not None:
        unverified.extend(to_verify)
    elif to_verify:
        # Not an error — a caller that does not run the verify pass is
        # entitled to skip it — but it must be visible that material was set
        # aside and nobody collected it, rather than looking like there was
        # none.
        log(f"search_stage: {len(to_verify)} source(s) routed to verify but "
            f"the caller passed no `unverified` list — set aside, unread")

    # `counters`, when the caller passes a dict, is filled in place rather
    # than returned: `03-worker.md` §11c's counter 2 ("unread URLs left in
    # the RRF pool covering those questions") needs the fused pool, which
    # dies with this function's frame, and widening the return type would
    # break every existing caller for a diagnostic. `unread_urls` is every
    # fused URL set cover did not take — the material the cheap route of
    # §11b would have to work with, and the number that decides whether that
    # branch is worth building at all.
    if counters is not None:
        taken = {normalize_url(u) for u in covered_urls}
        counters["pool_size"] = len(fused)
        counters["covered"] = len(covered_urls)
        counters["unread_urls"] = [r.url for r in fused
                                   if normalize_url(r.url) not in taken]
        counters["prompt_sources"] = len(confirmed)
        counters["verify_sources"] = len(to_verify)
    return confirmed
