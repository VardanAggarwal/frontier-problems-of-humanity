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

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional, Sequence
from urllib.parse import urljoin, urlparse

import yaml

from search.confirm_policy import (
    CONFIRMED,
    DROP,
    PROMPT,
    SEARCH,
    SEED,
    VERIFY,
    THIN_PAGE_CHARS,
    SourceVerdict,
    apply_confirmations,
    prompt_set_is_thin,
)
from search.cover import cover
from search.fuse import fuse, normalize_url
from search.health import MIN_ENGINES_RETURNED, engines_returned, is_healthy
from store import db
from worker.config import MAX_SOURCES_ESCALATE, MAX_SOURCES_REGISTRY, MAX_SOURCES_TRACKED
from worker.depth import REGISTRY_TIER, TRACKED_TIER
from worker.extract_types import ConfirmedSource

DEFAULT_FAMILIES_PATH = Path(__file__).resolve().parents[1] / "search" / "families.yaml"

# Well-known feed paths probed directly off a candidate's own `seed_url`
# (2026-09-19), porting `actor-channel-finder`'s manual RSS-hunting step —
# a technique the `channel_*` search families above can't replicate, since a
# feed URL usually isn't itself indexed by a search engine the way a site's
# main pages are. No pre-check of our own: each candidate URL is just handed
# to the existing fetch -> gate2 -> confirm_policy pipeline below like any
# other URL, so a path that 404s or doesn't exist comes back with no/thin
# text and gets dropped by the existing DROP logic, same as any dead URL.
FEED_PROBE_PATHS: tuple[str, ...] = (
    "/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/blog/feed",
)

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


def extract_hint(evidence: str) -> str:
    """Pull the disambiguating `hint` out of a candidate's `evidence` column,
    e.g. `{"hint": "Researcher who studied biochar-vermicompost effects on
    okra yield...", "from_candidate": 675, ...}` (`worker.py`'s mint path).
    `evidence` predates this parsing and is not guaranteed to be JSON (a bare
    string, or empty) — any failure to parse or find a `hint` key falls back
    to treating the whole value as the hint, which is what every pre-JSON
    caller already meant by "evidence"."""
    if not evidence:
        return ""
    try:
        parsed = json.loads(evidence)
    except (TypeError, ValueError):
        return evidence
    if isinstance(parsed, dict):
        return str(parsed.get("hint") or "")
    return evidence


def render_queries(name: str, families_path=None, kind: str = "actor",
                   hint: str = "") -> list[tuple[str, str]]:
    """[(family_id, rendered_query_string), ...] for every `retrievable:
    true` family of the given candidate `kind` in `families.yaml`. `{name}`
    is substituted verbatim — `search/families.yaml`'s own contract, not
    reinterpreted here. `kind` defaults to `"actor"` for backward
    compatibility with callers that predate the `problem` family set
    (2026-09-14) — every family in the registry from before that date is
    tagged `kind: actor`.

    `hint` (2026-09-19) — the candidate's own `evidence.hint`, the sentence
    that caused it to be minted (`worker.py`'s `payload["hint"]` /
    `edge.get("evidence", "")`). families.yaml's six/twenty templates are
    measured from PoC-0b/questions.yaml and are deliberately left untouched
    (module comment: "not invented" — do not fold hint text into them). A
    bare `{name}` query is blind on a common name ("Arjun Subedi" collides
    with a security tool, a journalist, a Twitter handle with no relation to
    the actual person — gate2.py:37-45's documented "second signal" gap) and
    on a generic company (LT Foods returns stock-ticker boilerplate instead
    of whatever angle it was actually cited for). One extra query anchored
    on name+hint targets the cited angle directly without touching the
    measured set; skipped when there is no hint to add (every pre-existing
    caller, and any candidate minted before `evidence.hint` existed)."""
    families = _load_retrievable_families(families_path or DEFAULT_FAMILIES_PATH, kind)
    queries = [(fam["id"], fam["query_template"].format(name=name)) for fam in families]
    if hint:
        queries.append(("hint", f"{name} {hint}"))
    return queries


# Domain+path patterns for the deterministic channel classifier below. A bare
# domain match (linkedin.com/*, twitter.com/*, ...) accepted ANYTHING under
# that domain — LinkedIn `/pulse/<article>` posts, Facebook `/posts/`,
# `/photo.php`, `/watch/` links, Instagram `/p/<post>` and `/reel/<reel>`
# permalinks all matched and got written as the actor's "channel", when none
# of them is a page to follow. Each pattern below is anchored to end right
# after the profile identifier (optional trailing slash/query/fragment), so
# a URL with a further path segment — the shape every one of those non-
# profile cases has — fails to match instead of falling through to "closest
# domain wins". Order is the check order per source, not a priority order
# across sources — see `channels_from_confirmed`'s docstring for how ties
# across sources resolve.
_CHANNEL_URL_PATTERNS: tuple[tuple[str, "re.Pattern"], ...] = (
    # Personal (`/in/<slug>`), company and school profile URLs only —
    # `/pulse/...` (articles), `/posts/...`, `/feed/...` etc. all have a
    # different top-level segment and never match.
    ("linkedin", re.compile(
        r"^https?://(?:[\w-]+\.)?linkedin\.com/(?:in|company|school)/"
        r"[^/?#]+/?(?:[?#].*)?$", re.I)),
    # A single path segment right after the domain, restricted to legal
    # handle characters. Reserved non-profile top-levels (i, hashtag,
    # search, explore, home, notifications, messages, settings) are
    # excluded by name since they'd otherwise match the same shape as a
    # handle. A tweet permalink (`/<handle>/status/<id>`) has a second path
    # segment and fails the end anchor before the exclusion list even runs.
    ("twitter", re.compile(
        r"^https?://(?:[\w-]+\.)?(?:twitter|x)\.com/"
        r"(?!i/|hashtag/|search|explore|home|notifications|messages|settings)"
        r"[A-Za-z0-9_]{1,15}/?(?:[?#].*)?$", re.I)),
    # Page/profile URL (`/<slug>` or the legacy `/profile.php?id=...`) —
    # excludes `/posts/`, `/photo(.php)`, `/story.php`, `/watch`, `/videos`,
    # `/photos`, `/groups`, `/events`, all of which are content permalinks
    # or hubs on the domain, not the actor's own page.
    ("facebook", re.compile(
        r"^https?://(?:[\w-]+\.)?facebook\.com/"
        r"(?:profile\.php\?id=\d+"
        r"|(?!posts/|photo(?:\.php)?|story\.php|watch|videos|photos|groups|"
        r"events|marketplace|gaming|ads|help|policies|legal)"
        r"[^/?#]+/?)$", re.I)),
    # Username page only — excludes `/p/<post>`, `/reel(s)/`, `/tv/`,
    # `/stories/`, `/explore/`, `/accounts/`, `/directory/` post/feature
    # permalinks.
    ("instagram", re.compile(
        r"^https?://(?:[\w-]+\.)?instagram\.com/"
        r"(?!p/|reel/|reels/|tv/|stories/|explore/|accounts/|directory/)"
        r"[^/?#]+/?(?:[?#].*)?$", re.I)),
)

# A share/intent/embed link is never a page to follow — it is another site
# putting a "share to X" button on ITS OWN page, not X's page about the
# actor. Checked before the domain patterns above claim the URL.
_CHANNEL_URL_EXCLUDE = re.compile(
    r"/(?:share|sharer|intent|plugins|dialog|embed)(?:[/?]|$)", re.I)


# Generic legal-entity / filler words that would otherwise count as a
# "distinctive" name token and match almost anything (`Foundation Trust`
# appears in hundreds of unrelated bios). Stripped before the mention check
# below; org-type suffixes only — a real given/family name never collides
# with this list.
_NAME_TOKEN_STOPWORDS = {
    "pvt", "ltd", "private", "limited", "the", "and", "of", "foundation",
    "trust", "india", "group", "inc", "llp", "co", "company", "society",
    "association", "committee", "welfare",
}


def _name_tokens(name: str) -> list[str]:
    """`name` -> its distinctive tokens for the mention check below: casefolded/
    punctuation-stripped (`store.db.norm`), 3+ chars, legal-suffix words
    dropped. Empty for a name that is nothing but stopwords/short tokens —
    the caller treats that as "can't check" rather than "never matches"."""
    return [t for t in db.norm(name).split()
            if len(t) >= 3 and t not in _NAME_TOKEN_STOPWORDS]


def _text_mentions_actor(text: str, name_tokens: Sequence[str]) -> bool:
    """Does `text` contain at least one of the actor's own distinctive name
    tokens, as a whole word? Word-boundary, not substring — `"sah"` must not
    match inside `"flash"`.

    2026-09-19: `tara-mani-sah`'s `channel:twitter` was written as
    `x.com/DonaldTrump` — gate2 embed-confirmed a thin, templated X.com
    profile shell (161 words, no page-specific content) against the
    candidate's context, and `channels_from_confirmed` trusted that verdict
    on URL pattern alone, never looking at what the page actually said. A
    genuine profile page says the actor's own name somewhere in its first
    ~500-1000 chars (bio, page title, "About"); a mismatched page fetched
    clean off a generic search hit does not. This is a second, independent
    signal on top of gate2's cosine band, not a replacement for it — cheap,
    exact-string, and catches exactly the class of failure a semantic
    embedding is worst at (a templated page with no distinguishing text)."""
    if not name_tokens:
        return True
    words = set(db.norm(text or "").split())
    return any(t in words for t in name_tokens)


def channels_from_confirmed(
        sources: Sequence[ConfirmedSource],
        name: str = "",
        context: str = "",
        judge: Optional[Callable[[str, str, str, str], tuple[bool, str]]] = None,
) -> list[dict]:
    """Confirmed source URLs -> `[{"kind": ..., "url": ...}, ...]`, one per
    platform, by domain pattern first, then two identity checks the URL
    pattern alone cannot do.

    Closes a reliability gap the LLM-extracted `channel:<kind>` path
    (`worker/extract.py`, `Answer.kind` fixed 2026-09-19) still has: it
    depends on the model NOTICING a channel URL among the pages it read and
    correctly naming a `kind` for it — a platform's own URL sitting
    confirmed in the source set is a cheaper, deterministic signal than
    hoping generation surfaces it. Paired with `families.yaml`'s
    `channel_linkedin`/`channel_twitter`/`channel_facebook`/
    `channel_instagram` site-search families (same date): those get the
    platform's URL INTO the confirmed set, this reads it back out — get-in
    and read-out are two different failure points and this only fixes the
    second, so both changes ship together.

    2026-09-19: the domain pattern plus gate2's CONFIRMED verdict was not
    enough — `tara-mani-sah` got `x.com/DonaldTrump` written as her twitter
    channel because gate2 embed-confirmed a thin, templated profile shell
    against her candidate context, and this function never looked at what
    the page actually said. Two checks now sit between "URL shape matches"
    and "written as the channel", cheapest first:

      1. `_text_mentions_actor` (free, no LLM): does the fetched text
         contain even one of the entity's own distinctive name tokens?
         Zero-overlap pages — a wrong same-shape URL fetched off a noisy
         search hit — are rejected here for the cost of a set lookup. This
         alone would have caught the Trump case: nothing in a Trump-profile
         fetch shares a token with "Tara Mani Sah".
      2. `judge`, when supplied — `(name, context, url, text) -> (bool, why)`,
         normally `prompts.channel_identity_prompt` + an `llm.call` + `
         prompts.parse_channel_identity`, injected by the caller the same
         way `fetch`/`confirm` are injected elsewhere in this module (this
         module still does not import `llm` or touch the network itself).
         Only called for a URL that already passed check 1 — the harder
         case check 1 cannot resolve (a same-named different person, or a
         passing mention that isn't the entity's own page), spent only on
         URLs cheap enough already-plausible to be worth an LLM call.
         `judge is None` skips this check (test callers, or a run with no
         model budget for it) and keeps check 1 as the only gate — better
         than the old always-trust-gate2 behaviour, not as strong as with
         a judge.

    A URL that fails either check is skipped, not just for the current
    source — the loop moves on to the NEXT confirmed source for that
    platform (first-match-wins operates over the URLs that pass both
    checks, not over the raw confirmed set), so a misidentified top hit
    doesn't block a genuine second one from being written instead.

    One `kind` per call: first CONFIRMED-verdict match wins per platform.
    `sources` is expected in `search_sources`' own return order (identity/
    money/... families before the channel_* families before `hint`, per
    `render_queries`), so "first match" is "earliest, most on-topic query
    result", not an arbitrary pick. No `website` entry — a generic domain
    cannot be told apart from "an article about the actor" by a URL pattern
    alone; that one stays the LLM's job (`channel:website`, still routed
    through `Answer.kind` as of the same fix).
    """
    name_tokens = _name_tokens(name)
    seen: dict[str, str] = {}
    for s in sources:
        if s.verdict != CONFIRMED:
            continue
        if _CHANNEL_URL_EXCLUDE.search(s.url):
            continue
        for kind, pat in _CHANNEL_URL_PATTERNS:
            if kind in seen:
                continue
            if not pat.match(s.url):
                continue
            if not _text_mentions_actor(s.text, name_tokens):
                break
            if judge is not None:
                ok, _why = judge(name, context, s.url, s.text)
                if not ok:
                    break
            seen[kind] = s.url
            break
    return [{"kind": k, "url": u} for k, u in seen.items()]


def _resolve_max_sources(depth: str, max_sources: Optional[int]) -> int:
    if max_sources is not None:
        return max_sources
    if depth == TRACKED_TIER:
        return MAX_SOURCES_TRACKED
    if depth == REGISTRY_TIER:
        return MAX_SOURCES_REGISTRY
    raise ValueError(
        f"unknown depth {depth!r}, expected {TRACKED_TIER!r} or {REGISTRY_TIER!r}")


def _fetch_and_route(
        to_fetch: list[tuple[str, str]],
        *,
        name: str,
        evidence: str,
        fetch: Callable,
        confirm: Callable,
        thin_page_chars: Optional[int],
        log: Callable,
        confirm_many: Optional[Callable] = None,
) -> tuple[list, list]:
    """`[(url, origin), ...] -> (confirmed, to_verify)` — steps 4-7 of
    `search_sources`'s docstring pipeline (fetch -> gate 2 -> confirm_policy
    -> route), factored out so the escalation round below can run the same
    fetch/confirm/route logic over a second batch of URLs without
    duplicating it. Pure aside from the injected `fetch`/`confirm`
    callables; does not know about `fused`/`cover`/counters."""
    with ThreadPoolExecutor(max_workers=max(1, len(to_fetch))) as pool:
        results = list(pool.map(lambda pair: fetch(pair[0]), to_fetch))

    verdicts = []
    texts_by_source_id = {}
    # Split first, confirm second. Pages with no fetched text never reach
    # `confirm` at all (blocked fetch, empty page): they are recorded as
    # NO_VERDICT (verdict=None) rather than confirmed against an empty
    # string — confirm_policy.SourceVerdict's own contract for this case.
    pending = []
    for (url, origin), result in zip(to_fetch, results):
        text = result.text
        texts_by_source_id[result.source_id] = text
        if not text:
            verdicts.append(SourceVerdict(
                source_id=result.source_id, url=url, origin=origin, verdict=None))
            continue
        pending.append((url, origin, result.source_id, text))

    # Step-reached, not just failure: the hang that produced candidate 28's
    # stuck run (2026-09-14T22:45, `[exit null]`, no exception) sat inside
    # the confirm call with nothing logged before or after it — the last line
    # anyone could see was "Loading weights". These lines exist so a future
    # stall names the URL it stalled on. In the batched path the whole batch
    # is named up front, since one `encode()` covers all of them and there is
    # no longer a per-URL boundary to stall at.
    if confirm_many is not None and pending:
        for url, origin, _sid, text in pending:
            log(f"search_stage: confirming {url} ({origin}, {len(text)} chars)")
        log(f"search_stage: gate2 batch of {len(pending)} page(s)")
        outcomes = confirm_many(name, evidence, [t for _u, _o, _s, t in pending])
    else:
        outcomes = []
        for url, origin, _sid, text in pending:
            log(f"search_stage: confirming {url} ({origin}, {len(text)} chars)")
            outcomes.append(confirm(name, evidence, text))

    for (url, origin, source_id, text), (verdict, cosine, note) in zip(pending, outcomes):
        verdicts.append(SourceVerdict(
            source_id=source_id, url=url, origin=origin,
            verdict=verdict, cosine=cosine, note=note, text_chars=len(text)))

    decisions = apply_confirmations(verdicts, thin_page_chars=thin_page_chars)

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
            # Previously silent — only DROP and VERIFY were logged, so a
            # clean confirm left no trace in the run log at all. Log the
            # success path too: `reason` already carries gate2's cosine.
            log(f"search_stage: confirmed {decision.url} ({decision.origin}): "
                f"{decision.reason}")
            confirmed.append(source)
        else:
            log(f"search_stage: to verify {decision.url} "
                f"({decision.origin}): {decision.reason}")
            to_verify.append(source)
    return confirmed, to_verify


def search_sources(
        name: str,
        *,
        depth: str,
        kind: str = "actor",
        provider,
        fetch: Callable,
        confirm: Callable,
        confirm_many: Optional[Callable] = None,
        evidence: str = "",
        seed_url: Optional[str] = None,
        max_sources: Optional[int] = None,
        slug: Optional[str] = None,
        families_path=None,
        min_engines_returned: Optional[int] = None,
        thin_page_chars: Optional[int] = THIN_PAGE_CHARS,
        escalate: bool = False,
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

    `escalate` — one further `cover()` pass, widened to `cap +
    worker.config.MAX_SOURCES_ESCALATE`, over the SAME fused pool, when the
    first pass's confirmed set comes back thin
    (`confirm_policy.prompt_set_is_thin`, the same check `worker.py`'s own
    verify-pass gate uses). Re-covers the full pool rather than just fetching
    the leftover `unread_urls` in whatever order `fuse` left them, because
    `cover()`'s set-cover selection over the wider cap is a better pick than
    the first cap's leftovers — and the escalation budget is added on top of
    `cap`, not carved out of it, since the first budget having proved
    insufficient is the reason this round exists at all. Runs at most once —
    if the widened set is still thin, that is `worker.py`'s existing
    verify-pass / degrade-path job, not this function's. Default `False`
    (opt-in) so every caller predating this — including every existing
    test — keeps its old one-pass behaviour unchanged. `worker.py` passes
    `True`.
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
            name, families_path or DEFAULT_FAMILIES_PATH, kind=kind,
            hint=extract_hint(evidence)):
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
    # PDF urls flow through the pool like any other url now that
    # `worker/fetch.py` extracts text from them — no pre-fetch rejection.
    fused = fuse(results_by_query)
    covered_urls = cover(fused, cap)

    # --- 4. fetch: seed is SEED, everything from search is SEARCH ----------
    to_fetch = []  # [(url, origin), ...]
    seen_norm = set()
    if seed_url:
        to_fetch.append((seed_url, SEED))
        seen_norm.add(normalize_url(seed_url))
        # RSS/feed direct probe (`FEED_PROBE_PATHS`, module docstring above)
        # — uncapped, same as the seed line just above: this is an extension
        # of the same seed-adjacent exception the `max_sources` docstring
        # already documents, not a `cover()` output, so it must not count
        # against the search-sourced cap. `SEARCH` origin reused (no
        # `confirm_policy` bucket fits better) since these aren't the seed
        # itself but aren't search-engine-sourced either.
        parsed_seed = urlparse(seed_url)
        probe_added = 0
        if parsed_seed.scheme and parsed_seed.netloc:
            base = f"{parsed_seed.scheme}://{parsed_seed.netloc}"
            for path in FEED_PROBE_PATHS:
                probe_url = urljoin(base, path)
                norm = normalize_url(probe_url)
                if norm in seen_norm:
                    continue
                to_fetch.append((probe_url, SEARCH))
                seen_norm.add(norm)
                probe_added += 1
        if probe_added:
            log(f"search_stage: probing {probe_added} feed path(s) off the "
                f"seed for {resolved_slug}")
    for url in covered_urls:
        norm = normalize_url(url)
        if norm in seen_norm:
            continue
        to_fetch.append((url, SEARCH))
        seen_norm.add(norm)

    # `fetch` per URL is the pipeline's dominant wall-clock cost (one HTTP GET
    # each, up to MAX_SOURCES_TRACKED+1 of them) and each call is independent
    # — no shared state between URLs at this call site. Run them concurrently
    # rather than one at a time; `confirm` stays sequential inside
    # `_fetch_and_route` since it's cheap local scoring, not the thing worth
    # overlapping.
    #
    # --- 4-7. fetch -> gate 2 -> confirm_policy -> route (`_fetch_and_route`,
    # deliberate behaviour change adopted at integration —
    # `04-worker-build-plan.md` §5, hole #1, and this task's brief: today's
    # worker.py lets a no-text candidate through to extraction unconfirmed
    # (`if text:` guard at worker.py:496-499); `confirm_policy.
    # apply_confirmations` drops NO_VERDICT outright instead.
    confirmed, to_verify = _fetch_and_route(
        to_fetch, name=name, evidence=evidence, fetch=fetch, confirm=confirm,
        confirm_many=confirm_many,
        thin_page_chars=thin_page_chars, log=log)

    # --- 8. one escalation round, opt-in (`escalate=True`) ------------------
    # Widen the cap and re-cover the SAME fused pool rather than just fetching
    # whatever `unread_urls` left over in fuse order — see the docstring for
    # why a wider `cover()` pass beats fetching leftovers. Fetches only the
    # URLs the first pass didn't already take (`seen_norm` dedup, same as the
    # seed-vs-search dedup above); if the widened cover() picks nothing new
    # (pool exhausted at the first cap already), there is nothing to escalate
    # into and this is a no-op past the thinness check.
    escalated = False
    if escalate:
        thin, why = prompt_set_is_thin([s.text for s in confirmed])
        log(f"search_stage: {resolved_slug} confirmed-set thin check "
            f"(pre-escalation): {why}")
        if thin:
            escalated = True
            widened_cap = cap + MAX_SOURCES_ESCALATE
            covered_urls = cover(fused, widened_cap)
            more_to_fetch = []
            for url in covered_urls:
                norm = normalize_url(url)
                if norm in seen_norm:
                    continue
                more_to_fetch.append((url, SEARCH))
                seen_norm.add(norm)
            if more_to_fetch:
                log(f"search_stage: {resolved_slug} escalating — cap {cap} -> "
                    f"{widened_cap}, fetching {len(more_to_fetch)} additional "
                    "url(s) from the fused pool")
                more_confirmed, more_to_verify = _fetch_and_route(
                    more_to_fetch, name=name, evidence=evidence, fetch=fetch,
                    confirm=confirm, confirm_many=confirm_many,
                    thin_page_chars=thin_page_chars, log=log)
                confirmed.extend(more_confirmed)
                to_verify.extend(more_to_verify)
            else:
                log(f"search_stage: {resolved_slug} escalation found no "
                    "additional urls in the fused pool — cover() had "
                    "already exhausted it at the first cap")

    # Three destinations, not two (`confirm_policy`'s PROMPT/VERIFY/DROP,
    # 2026-09-14). Only PROMPT sources are returned as the confirmed set. The
    # VERIFY bucket — gate-2 `uncertain`, plus confirmed-but-thin — is handed
    # back through the optional `unverified` list rather than widened into the
    # return type: every existing caller keeps working, and a caller that
    # does not ask for the bucket cannot accidentally put it in the
    # extraction prompt.
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
    # fused URL set cover did not take — post-escalation, `covered_urls` is
    # whichever cover() call ran last (the widened one, if escalation fired),
    # so this reports what actually got fetched, not just the first pass's.
    if counters is not None:
        taken = {normalize_url(u) for u in covered_urls}
        counters["pool_size"] = len(fused)
        counters["covered"] = len(covered_urls)
        counters["escalated"] = escalated
        counters["unread_urls"] = [r.url for r in fused
                                   if normalize_url(r.url) not in taken]
        counters["prompt_sources"] = len(confirmed)
        counters["verify_sources"] = len(to_verify)
    return confirmed
