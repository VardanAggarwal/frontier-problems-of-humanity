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
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from search.confirm_policy import CONFIRMED, MISMATCH, SEARCH, SEED, UNCERTAIN
from search.cover import cover
from search.fuse import FusedResult
from search.provider import ReplayProvider, SearchResponse
from worker.config import MAX_SOURCES_ESCALATE, MAX_SOURCES_REGISTRY, MAX_SOURCES_TRACKED
from worker.depth import REGISTRY_TIER, TRACKED_TIER
from worker.extract_types import ConfirmedSource
from worker.search_stage import (
    _hint_anchor_top_up, channels_from_confirmed, extract_hint,
    render_queries, search_sources, website_and_feed_channels,
)

HERE = pathlib.Path(__file__).parent
POC0B_RESPONSES = HERE.parent / "poc" / "poc0b-responses"

NAME = "A2P Energy Solution Pvt Ltd"
SLUG = "a2p-energy"


class _ReplayOrEmptyProvider(ReplayProvider):
    """`ReplayProvider`, tolerant of a family with no recorded fixture.

    The five `channel_*` families (2026-09-19, families.yaml) postdate the
    frozen PoC-0b recording set in `poc/poc0b-responses/` — no
    `{slug}__channel_linkedin.json` etc. was ever going to exist for them.
    `ReplayProvider` itself stays strict (a real typo in `family_id`/`slug`
    elsewhere should still raise loudly); this subclass exists only so the
    tests below, which exercise escalation/seed/concurrency/routing logic
    and go through the FULL retrievable family list incidentally (one
    provider call per family, from `search_stage.search_sources`), aren't
    collateral damage every time a new family is added without a matching
    recording. An unrecorded family behaves like "no data" — a live
    SearxngProvider would just return few/no results for a very specific
    `site:` query on an obscure entity too."""
    def query(self, slug, family):
        try:
            return super().query(slug, family)
        except FileNotFoundError:
            return SearchResponse(results=[], unresponsive_engines=[],
                                  engines_seen_in_results=[],
                                  configured_engines=self.configured_engines,
                                  silently_absent_engines=[], raw_results=[])


def _provider():
    return _ReplayOrEmptyProvider(POC0B_RESPONSES)


class _FakeFetchResult:
    def __init__(self, text, source_id):
        self.text = text
        self.source_id = source_id


# Long enough to clear confirm_policy.THIN_PAGE_CHARS (measured 2026-09-14).
# A one-line fake used to be fine because no length rule was on; now a short
# page legitimately routes to the verify pass, so a fixture standing in for an
# ordinary substantive page has to look like one.
_PAGE_BODY = ("page text about the entity, at a length that a real fetched "
              "article would plausibly have, repeated to clear the thin-page "
              "floor without saying anything. ") * 12


def _fetch_all_confirmed(url):
    """Every URL fetches fine; source_id derived deterministically from url."""
    return _FakeFetchResult(text=f"{_PAGE_BODY}{url}", source_id=f"src-{url}")


def _confirm_all_confirmed(name, evidence, text):
    return (CONFIRMED, 0.90, "")


# ---------------------------------------------------------------------------
# render_queries
# ---------------------------------------------------------------------------

def test_render_queries_only_retrievable_families():
    queries = render_queries(NAME)
    ids = [q[0] for q in queries]
    assert "failure" not in ids, "failure is retrievable: false, must be excluded"
    # PoC-0b's original five, plus the five site-targeted channel families
    # added 2026-09-19 (not PoC-measured — see families.yaml's comment on
    # them — one `site:` query per major platform instead of relying on
    # `reach`'s single generic query to surface whichever one an actor
    # happens to be on), plus `channel_feed`/`channel_press` (same date) for
    # platforms the site-targeted five don't cover — newsletter/Substack/
    # Telegram and the Indian civic-journalism aggregator fallback.
    assert set(ids) == {
        "identity", "money", "people", "viability", "reach",
        "channel_linkedin", "channel_twitter", "channel_facebook",
        "channel_instagram", "channel_website",
        "channel_feed", "channel_press",
    }


def test_render_queries_substitutes_name_verbatim():
    queries = dict(render_queries(NAME))
    assert queries["identity"] == NAME
    assert NAME in queries["money"]


def test_render_queries_channel_families_target_their_platform():
    queries = dict(render_queries(NAME))
    assert queries["channel_linkedin"] == f"{NAME} site:linkedin.com"
    assert queries["channel_twitter"] == f"{NAME} site:twitter.com OR site:x.com"
    assert queries["channel_facebook"] == f"{NAME} site:facebook.com"
    assert queries["channel_instagram"] == f"{NAME} site:instagram.com"
    assert queries["channel_website"] == f"{NAME} official website"


def test_render_queries_no_hint_leaves_the_poc0b_measured_templates_untouched():
    """No `evidence.hint` on the candidate (every caller before 2026-09-19,
    and any candidate minted before `evidence.hint` existed): the original
    five PoC-0b-measured query TEXTS must be byte-identical to before this
    change — `families.yaml`'s own rule, "not invented". The full id SET
    grew with the 2026-09-19 channel-search additions (checked above); what
    must not move is what these five specific ids render to."""
    queries = dict(render_queries(NAME))
    assert "hint" not in queries
    assert queries["identity"] == NAME
    assert queries["money"] == f"{NAME} funding raised grant crore"
    assert queries["people"] == f"{NAME} founder director leadership"
    assert queries["viability"] == f"{NAME} revenue customers model"
    assert queries["reach"] == f"{NAME} contact twitter newsletter"


def test_render_queries_with_hint_adds_one_anchored_query():
    """A common name or a generic company (Arjun Subedi, LT Foods) is blind
    without the sentence that caused the candidate to be minted in the first
    place — see search_stage.py's `render_queries` docstring. The extra
    query carries name+hint; the five measured families are untouched."""
    hint = "Key private company in warehousing and logistics"
    queries = dict(render_queries(NAME, hint=hint))
    assert queries["hint"] == f"{NAME} {hint}"
    assert queries["money"] == f"{NAME} funding raised grant crore", (
        "measured families must not be rewritten to fold in the hint")


def test_extract_hint_parses_the_evidence_json():
    evidence = ('{"hint": "Researcher who studied biochar-vermicompost '
               'effects on okra yield.", "from_candidate": 675}')
    assert extract_hint(evidence) == (
        "Researcher who studied biochar-vermicompost effects on okra yield.")


def test_extract_hint_falls_back_to_the_raw_string():
    """`evidence` predates the JSON shape and is not guaranteed to parse —
    a bare string (or malformed JSON) is itself the hint, not nothing."""
    assert extract_hint("a plain-text hint, not JSON") == (
        "a plain-text hint, not JSON")


def test_extract_hint_json_without_a_hint_key_yields_empty():
    assert extract_hint('{"from_candidate": 675}') == ""


def test_extract_hint_empty_evidence_yields_empty():
    assert extract_hint("") == ""


def _cs(url, verdict=CONFIRMED, source_id=None, text="x"):
    return ConfirmedSource(source_id=source_id or url, url=url, text=text,
                           origin=SEARCH, verdict=verdict)


def test_channels_from_confirmed_matches_each_platform():
    sources = [
        _cs("https://in.linkedin.com/company/ncml"),
        _cs("https://twitter.com/CeetleHero"),
        _cs("https://www.facebook.com/ncmlindia"),
        _cs("https://www.instagram.com/ncml_official"),
        _cs("https://example.com/an-article-about-ncml"),
    ]
    channels = {c["kind"]: c["url"] for c in channels_from_confirmed(sources)}
    assert channels == {
        "linkedin": "https://in.linkedin.com/company/ncml",
        "twitter": "https://twitter.com/CeetleHero",
        "facebook": "https://www.facebook.com/ncmlindia",
        "instagram": "https://www.instagram.com/ncml_official",
    }


def test_channels_from_confirmed_x_dot_com_counts_as_twitter():
    channels = channels_from_confirmed([_cs("https://x.com/CeetleHero")])
    assert channels == [{"kind": "twitter", "url": "https://x.com/CeetleHero"}]


def test_channels_from_confirmed_ignores_unconfirmed_sources():
    channels = channels_from_confirmed([
        _cs("https://twitter.com/maybe_this_one", verdict=UNCERTAIN),
    ])
    assert channels == []


def test_channels_from_confirmed_excludes_share_and_intent_links():
    """A `facebook.com/sharer/...` or `twitter.com/intent/tweet?...` URL is
    another site's "share to X" button, not X's own page about the actor."""
    channels = channels_from_confirmed([
        _cs("https://www.facebook.com/sharer/sharer.php?u=https://example.com"),
        _cs("https://twitter.com/intent/tweet?text=hello"),
    ])
    assert channels == []


def test_channels_from_confirmed_first_match_wins_per_platform():
    """List order is search_sources' own return order (earliest, most
    on-topic query result) — the second twitter URL must not replace the
    first."""
    channels = channels_from_confirmed([
        _cs("https://twitter.com/real_handle"),
        _cs("https://twitter.com/a_retweet_mentioning_them"),
    ])
    assert channels == [{"kind": "twitter", "url": "https://twitter.com/real_handle"}]


def test_channels_from_confirmed_rejects_url_whose_text_never_mentions_the_name():
    """The tara-mani-sah regression: a pattern-matched, gate2-CONFIRMED URL
    whose fetched text shares no token with the actor's name must not be
    written as their channel, even with no `judge` supplied."""
    channels = channels_from_confirmed([
        _cs("https://x.com/DonaldTrump",
            text="Donald J. Trump 45th & 47th President of the United States"),
    ], name="Tara Mani Sah")
    assert channels == []


def test_channels_from_confirmed_accepts_url_whose_text_mentions_the_name():
    channels = channels_from_confirmed([
        _cs("https://x.com/TaraManiSah", text="Tara Mani Sah — activist, Simdega"),
    ], name="Tara Mani Sah")
    assert channels == [{"kind": "twitter", "url": "https://x.com/TaraManiSah"}]


def test_channels_from_confirmed_name_check_falls_through_to_next_source():
    """A first URL that fails the name-mention check must not block a later,
    genuine URL for the same platform from being written instead."""
    channels = channels_from_confirmed([
        _cs("https://x.com/DonaldTrump", text="Donald Trump's official account"),
        _cs("https://x.com/TaraManiSah", text="Tara Mani Sah, Simdega activist"),
    ], name="Tara Mani Sah")
    assert channels == [{"kind": "twitter", "url": "https://x.com/TaraManiSah"}]


def test_channels_from_confirmed_no_name_given_skips_the_mention_check():
    """Backward compatible: a caller with no `name` (or one that is nothing
    but stopwords) gets the old URL-pattern-only behaviour."""
    channels = channels_from_confirmed([_cs("https://x.com/CeetleHero")])
    assert channels == [{"kind": "twitter", "url": "https://x.com/CeetleHero"}]


def test_channels_from_confirmed_judge_rejection_falls_through():
    """A `judge` that rejects a name-token-passing URL is treated the same
    as a failed name-mention check — try the next source for that platform."""
    def judge(name, context, url, text):
        return ("TaraManiSah" in url), "handle mismatch" if "TaraManiSah" not in url else "match"

    channels = channels_from_confirmed([
        _cs("https://x.com/tara_unrelated", text="Tara something else entirely"),
        _cs("https://x.com/TaraManiSah", text="Tara Mani Sah, Simdega activist"),
    ], name="Tara Mani Sah", judge=judge)
    assert channels == [{"kind": "twitter", "url": "https://x.com/TaraManiSah"}]


def test_channels_from_confirmed_judge_not_called_when_name_check_fails():
    """The judge is spent only on URLs that already passed the free
    name-token check — never called at all when that check rejects first."""
    calls = []

    def judge(name, context, url, text):
        calls.append(url)
        return True, "would have accepted"

    channels = channels_from_confirmed([
        _cs("https://x.com/DonaldTrump", text="no relation to the query"),
    ], name="Tara Mani Sah", judge=judge)
    assert channels == []
    assert calls == []


def test_channels_from_confirmed_has_no_website_entry():
    """A generic domain can't be told apart from "an article about the
    actor" by URL pattern alone — deliberately left to the LLM path."""
    channels = channels_from_confirmed([_cs("https://ncml.com")])
    assert channels == []


def test_channels_from_confirmed_rejects_linkedin_articles():
    """`/pulse/<article>` is a LinkedIn post, not a profile — only `/in/`,
    `/company/` and `/school/` count."""
    channels = channels_from_confirmed([
        _cs("https://www.linkedin.com/pulse/some-article-about-the-actor"),
    ])
    assert channels == []


def test_channels_from_confirmed_rejects_tweet_permalinks():
    """A `/status/<id>` URL is one tweet, not the actor's own timeline."""
    channels = channels_from_confirmed([
        _cs("https://twitter.com/CeetleHero/status/1234567890"),
    ])
    assert channels == []


def test_channels_from_confirmed_rejects_facebook_post_and_photo_permalinks():
    channels = channels_from_confirmed([
        _cs("https://www.facebook.com/ncmlindia/posts/123456"),
        _cs("https://www.facebook.com/photo.php?fbid=123"),
        _cs("https://www.facebook.com/watch/?v=123"),
    ])
    assert channels == []


def test_channels_from_confirmed_accepts_facebook_profile_php_id():
    channels = channels_from_confirmed([
        _cs("https://www.facebook.com/profile.php?id=100012345678"),
    ])
    assert channels == [{
        "kind": "facebook",
        "url": "https://www.facebook.com/profile.php?id=100012345678",
    }]


# ------------------------- website_and_feed_channels (2026-09-19d) ---------

def test_website_and_feed_channels_no_own_domain_yields_nothing():
    """No confirmed source's hostname spells the candidate's name — nothing
    to anchor a website channel to, so no feed probing either."""
    channels = website_and_feed_channels(
        [_cs("https://en.wikipedia.org/wiki/JJ_Spices")], name="JJ Spices")
    assert channels == []


def test_website_and_feed_channels_website_only_without_fetch_confirm():
    """Own domain found, but no `fetch`/`confirm` injected (e.g. no budget
    left this candidate) — the website channel is still free, feed probing
    is just skipped."""
    channels = website_and_feed_channels(
        [_cs("https://jjspices.in/ne/quality")], name="JJ Spices")
    assert channels == [{"kind": "website", "url": "https://jjspices.in"}]


def test_website_and_feed_channels_confirms_a_guessed_feed_path():
    """The niehs shape: the model had a link LABEL but no URL to cite. This
    guesses common feed paths off the confirmed domain root and only writes
    one that both fetches usable text and gate2-confirms against the
    candidate — never a bare construction."""
    def fetch(url):
        if url == "https://niehs.nih.gov/feed":
            return _FakeFetchResult("NIEHS RSS Feed — latest research", "f1")
        return _FakeFetchResult(None, "other")

    def confirm(name, evidence, text):
        return (CONFIRMED, 0.9, "") if "NIEHS" in text else (MISMATCH, 0.5, "")

    channels = website_and_feed_channels(
        [_cs("https://niehs.nih.gov/about/visiting")], name="NIEHS",
        fetch=fetch, confirm=confirm)
    assert channels == [
        {"kind": "website", "url": "https://niehs.nih.gov"},
        {"kind": "rss", "url": "https://niehs.nih.gov/feed"},
    ]


def test_website_and_feed_channels_never_writes_an_unconfirmed_guess():
    """Every guessed path either 404s (no text) or fails gate2 — no `rss`
    channel is written, only `website`. This is the "never construct a URL
    that isn't verified" guarantee `q16_channel`'s prompt asks the model
    for, enforced here at the pipeline level instead of by instruction."""
    channels = website_and_feed_channels(
        [_cs("https://jjspices.in/ne/quality")], name="JJ Spices",
        fetch=lambda url: _FakeFetchResult(None, "x"),
        confirm=lambda *a: (CONFIRMED, 0.99, ""))
    assert channels == [{"kind": "website", "url": "https://jjspices.in"}]


def test_website_and_feed_channels_stops_at_first_confirmed_hit():
    calls = []

    def fetch(url):
        calls.append(url)
        return _FakeFetchResult("JJ Spices quality feed", "f")

    channels = website_and_feed_channels(
        [_cs("https://jjspices.in/ne/quality")], name="JJ Spices",
        fetch=fetch, confirm=lambda *a: (CONFIRMED, 0.9, ""))
    assert len(calls) == 1
    assert channels[-1]["kind"] == "rss"


def test_channels_from_confirmed_rejects_instagram_post_and_reel_permalinks():
    channels = channels_from_confirmed([
        _cs("https://www.instagram.com/p/CabcXYZ/"),
        _cs("https://www.instagram.com/reel/CabcXYZ/"),
    ])
    assert channels == []


def test_search_sources_hint_query_reaches_the_provider():
    """End to end: a candidate's `evidence` JSON hint must show up as an
    actual query string handed to the provider, not just as gate2's
    post-fetch confirmation context (which it already reached before this
    change) — the fix this closes is that the *search* itself was blind."""
    seen = {}

    class RecordingProvider(_FixedResponseProvider):
        def search(self, family_id, query_string, *, slug=None):
            seen[family_id] = query_string
            return super().search(family_id, query_string, slug=slug)

    search_sources(
        "LT Foods", depth=TRACKED_TIER,
        provider=RecordingProvider(["https://example.com/a"]),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        evidence='{"hint": "Key private company in warehousing and logistics"}',
        slug="lt-foods", log=lambda *a, **k: None,
    )
    assert seen["hint"] == "LT Foods Key private company in warehousing and logistics"


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


# ---------------------------------------------------------------------------
# hint-anchor top-up (raghubar-das / candidate 1102, 2026-09-19) — guarantees
# a hint-covered URL a floor in the fetched set even when cover()'s greedy,
# family-id-equal-weight selection would otherwise fill the cap with generic
# hits first.
# ---------------------------------------------------------------------------

def test_hint_anchor_top_up_rescues_url_crowded_out_by_generic_families():
    """Direct unit test of `_hint_anchor_top_up`, reproducing the actual
    crowding-out shape: one URL that appears in every generic family's
    results (a political-bio page cited under identity/money/elections/...)
    gets picked first by cover()'s greedy max-coverage — its gain is huge —
    and a small cap is exhausted before the URL uniquely covering the `hint`
    family is ever reached. Plain `cover()` drops the hint URL; the top-up
    must add it back."""
    crowd_url = "https://example.com/generic-bio"
    hint_url = "https://example.com/santoshi-kumari-aadhaar-directive"
    fused = [
        FusedResult(crowd_url, 0.5, frozenset(
            {"identity", "money", "people", "viability", "reach"})),
        FusedResult(hint_url, 0.01, frozenset({"hint"})),
    ]
    # cover() alone, cap=1: greedy picks crowd_url (gain 5) and stops —
    # exactly the bug.
    plain = cover(fused, 1)
    assert hint_url not in plain, "test setup must reproduce the crowd-out"

    topped_up = _hint_anchor_top_up(plain, fused)
    assert hint_url in topped_up
    assert crowd_url in topped_up, "top-up must not evict cover()'s picks"
    assert len(topped_up) == len(plain) + 1, "top-up grows the set by at most one"


def test_hint_anchor_top_up_is_noop_when_hint_url_already_covered():
    hint_url = "https://example.com/hint-page"
    fused = [
        FusedResult(hint_url, 0.9, frozenset({"identity", "hint"})),
    ]
    covered_urls = cover(fused, 5)
    assert hint_url in covered_urls
    result = _hint_anchor_top_up(covered_urls, fused)
    assert result == covered_urls, "hint URL already present — no-op"


def test_hint_anchor_top_up_is_noop_when_no_hint_family_was_queried():
    """Every caller that predates `evidence.hint`, or a candidate with none:
    `fused` carries no `hint`-covered entry at all. Must be provably
    harmless — identical output to plain `cover()`."""
    fused = [
        FusedResult("https://example.com/a", 0.5, frozenset({"identity"})),
        FusedResult("https://example.com/b", 0.4, frozenset({"money"})),
    ]
    covered_urls = cover(fused, 1)
    result = _hint_anchor_top_up(covered_urls, fused)
    assert result == covered_urls


def test_hint_anchor_top_up_picks_top_ranked_hint_url_when_several_exist():
    hi = "https://example.com/hint-strong"
    lo = "https://example.com/hint-weak"
    fused = [
        FusedResult("https://example.com/crowd", 0.9, frozenset({"identity"})),
        FusedResult(lo, 0.05, frozenset({"hint"})),
        FusedResult(hi, 0.2, frozenset({"hint"})),
    ]
    plain = cover(fused, 1)
    result = _hint_anchor_top_up(plain, fused)
    assert hi in result
    assert lo not in result


def test_search_sources_end_to_end_rescues_crowded_out_hint_source():
    """Integration: through `search_sources` itself, with a provider that
    reproduces the real crowding shape — every generic actor family returns
    the same well-known-figure bio URL, only `hint` returns the one URL
    anchored on the actual seeding reason — and a cap of 1. Without the
    top-up, the confirmed set would be entirely the generic bio page (the
    raghubar-das bug: right person, wrong topic); with it, the hint-anchored
    source is also fetched and confirmed."""
    crowd_url = "https://example.com/generic-bio"
    hint_url = "https://example.com/santoshi-kumari-aadhaar-directive"

    class CrowdingProvider:
        def search(self, family_id, query_string, *, slug=None):
            url = hint_url if family_id == "hint" else crowd_url
            return SearchResponse(
                results=[], unresponsive_engines=[],
                engines_seen_in_results=["bing", "brave", "google", "mojeek", "yandex"],
                configured_engines=[], silently_absent_engines=[],
                raw_results=[{"url": url, "score": 1.0, "engine": "bing"}])

    result = search_sources(
        "Raghubar Das", depth=TRACKED_TIER, provider=CrowdingProvider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        evidence=('{"hint": "Jharkhand Chief Minister who issued interim '
                   "relief and ordered a probe after Santoshi Kumari's "
                   'death; in conflict with Saryu Roy over Aadhaar directive."}'),
        slug="raghubar-das", max_sources=1, log=lambda *a, **k: None,
    )
    urls = {s.url for s in result}
    assert hint_url in urls, "hint-anchored source must survive the crowd-out"
    assert crowd_url in urls, "top-up must not evict cover()'s own pick"


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


def test_uncertain_source_is_routed_to_verify_not_into_the_prompt():
    """Changed 2026-09-14. `uncertain` used to be returned in the confirmed
    set — which put an unconfirmed page straight into the extraction prompt,
    and putting it there IS resolving it as a pass, the one thing gate2's
    contract forbids. `poc/gate2-band-sweep.md` measured the cost: ~60 of 200
    pooled URLs sat in that band and were essentially all junk.

    It is still not dropped. It goes to the verify-and-extract pass."""
    def confirm_uncertain(name, evidence, text):
        return (UNCERTAIN, 0.79, "gate2: cosine in the unresolved middle band")

    unverified = []
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=confirm_uncertain,
        slug=SLUG, unverified=unverified, log=lambda *a, **k: None,
    )
    assert result == [], "uncertain must not reach the extraction prompt"
    assert unverified, "uncertain must not be dropped either"
    for src in unverified:
        assert src.verdict == UNCERTAIN


def test_verify_bucket_is_announced_when_nobody_collects_it():
    """A caller may decline the verify pass, but material set aside and left
    unread must be visible rather than looking like there was none."""
    logged = []

    def confirm_uncertain(name, evidence, text):
        return (UNCERTAIN, 0.79, "middle band")

    search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=confirm_uncertain,
        slug=SLUG, log=lambda m: logged.append(m),
    )
    assert any("no `unverified` list" in m for m in logged)


def test_thin_confirmed_source_is_routed_to_verify():
    """THIN_PAGE_CHARS is measured and on by default now, so a confirmed but
    very short page is no longer a clean confirm."""
    def confirm_ok(name, evidence, text):
        return (CONFIRMED, 0.95, "")

    def fetch_thin(url):
        return _FakeFetchResult(text="short page", source_id=f"src-{url}")

    unverified = []
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=fetch_thin, confirm=confirm_ok,
        slug=SLUG, unverified=unverified, log=lambda *a, **k: None,
    )
    assert result == []
    assert unverified, "a thin confirm is set aside, not discarded"


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


# ---------------------------------------------------------------------------
# fetch concurrency — the URLs in `to_fetch` are fetched in parallel, not
# one at a time
# ---------------------------------------------------------------------------

def test_fetch_calls_run_concurrently_not_sequentially():
    """Each `fetch` call sleeps SLEEP_S; if the loop were still the old
    sequential `for url, origin in to_fetch: fetch(url)`, N urls would cost
    at least N * SLEEP_S wall-clock. Overlapping calls in a thread pool must
    finish in well under that, close to one SLEEP_S."""
    SLEEP_S = 0.3
    max_concurrent = 0
    current = 0
    lock = threading.Lock()

    def slow_fetch(url):
        nonlocal max_concurrent, current
        with lock:
            current += 1
            max_concurrent = max(max_concurrent, current)
        time.sleep(SLEEP_S)
        with lock:
            current -= 1
        return _fetch_all_confirmed(url)

    start = time.monotonic()
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=slow_fetch, confirm=_confirm_all_confirmed,
        slug=SLUG, log=lambda *a, **k: None,
    )
    elapsed = time.monotonic() - start

    n_urls = len(result)
    assert n_urls >= 2, "need at least 2 fetched urls for a concurrency test to mean anything"
    assert max_concurrent >= 2, "fetch calls never overlapped — still sequential"
    assert elapsed < n_urls * SLEEP_S, (
        f"elapsed {elapsed:.2f}s not faster than sequential bound "
        f"{n_urls * SLEEP_S:.2f}s ({n_urls} urls) — fetch calls did not overlap"
    )


def test_fetch_result_order_preserved_regardless_of_completion_order():
    """`pool.map` must yield results in call order, not completion order —
    verdicts/texts_by_source_id must line up with `to_fetch`'s own order
    even when slower urls are submitted first and finish last."""
    # Make the first url submitted the slowest, so if order were determined
    # by completion instead of submission, this would come back scrambled.
    delays = {}

    def variable_fetch(url):
        delay = delays.setdefault(url, 0.2 if not delays else 0.0)
        time.sleep(delay)
        return _fetch_all_confirmed(url)

    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=variable_fetch, confirm=_confirm_all_confirmed,
        slug=SLUG, log=lambda *a, **k: None,
    )
    # Every url fetched fine and confirmed — order corruption would show up
    # as a source's text not matching its own url (texts_by_source_id keyed
    # wrong, or a verdict attached to the wrong url).
    for src in result:
        assert src.url in src.text, "fetched text does not match its own url — result order corrupted"


# ---------------------------------------------------------------------------
# escalation — one widened cover() pass when the confirmed set is thin
# (candidate 12, groundwater-depletion-from-irrigation, 2026-09-14: 1 usable
# source out of 5 fetched, all from one narrow domain family)
# ---------------------------------------------------------------------------

def test_escalate_false_by_default_stays_at_the_first_cap():
    """Backward compat: every caller that predates `escalate` — including
    every test above — must see the unchanged one-pass cap."""
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, max_sources=1, log=lambda *a, **k: None,
    )
    assert len(result) == 1


def test_escalate_true_widens_past_the_cap_when_thin():
    """A cap of 1 confirmed source is thin by `MIN_PROMPT_SOURCES` alone
    regardless of page length. `escalate=True` must re-cover the fused pool
    at cap + MAX_SOURCES_ESCALATE and pick up more of it — not just the one
    url the first, too-small cap allowed."""
    counters = {}
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, max_sources=1, escalate=True, counters=counters,
        log=lambda *a, **k: None,
    )
    assert len(result) > 1, "escalation did not fetch anything beyond the first cap"
    assert counters["escalated"] is True
    assert counters["covered"] == len(result)


def test_escalate_true_no_op_when_confirmed_set_is_not_thin():
    """The common case — the first pass already cleared the thinness floor
    — must not pay for a second cover()/fetch round at all."""
    counters = {}
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, escalate=True, counters=counters, log=lambda *a, **k: None,
    )
    baseline = search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, escalate=False, log=lambda *a, **k: None,
    )
    assert len(result) == len(baseline)
    assert counters["escalated"] is False


def test_escalate_does_not_double_fetch_urls_the_first_pass_already_took():
    fetch_calls = []

    def counting_fetch(url):
        fetch_calls.append(url)
        return _fetch_all_confirmed(url)

    search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=counting_fetch, confirm=_confirm_all_confirmed,
        slug=SLUG, max_sources=1, escalate=True, log=lambda *a, **k: None,
    )
    assert len(fetch_calls) == len(set(fetch_calls)), "a url was fetched twice across the two rounds"


# ---------------------------------------------------------------------------
# PDF urls — `worker/fetch.py` now extracts text from PDFs, so a `.pdf` url
# is treated like any other url: it reaches `fetch`, counts against the
# cover cap, and is not specially logged or rejected here. (Superseded
# 2026-09-19; candidate 12's CGWB Kollam district PDF, 2026-09-14, was the
# instance that motivated the old pre-fetch rejection.)
# ---------------------------------------------------------------------------

class _FixedResponseProvider:
    """Every family's query returns the same fixed result list — one .pdf
    url mixed in with plain html urls, plus enough engines to read healthy
    without a warning cluttering the log assertions below."""
    def __init__(self, urls):
        self._results = [{"url": u, "score": 1.0 - i * 0.01, "engine": "bing"}
                         for i, u in enumerate(urls)]

    def search(self, family_id, query_string, *, slug=None):
        return SearchResponse(
            results=[], unresponsive_engines=[],
            engines_seen_in_results=["bing", "brave", "google", "mojeek", "yandex"],
            configured_engines=[], silently_absent_engines=[],
            raw_results=list(self._results))


def test_pdf_url_reaches_fetch_like_any_other_url():
    fetch_calls = []

    def counting_fetch(url):
        fetch_calls.append(url)
        return _fetch_all_confirmed(url)

    provider = _FixedResponseProvider([
        "https://cgwb.gov.in/old_website/District_Profile/Kerala/kollam.pdf",
        "https://groundwater.kerala.gov.in",
    ])
    search_sources(
        NAME, depth=TRACKED_TIER, provider=provider,
        fetch=counting_fetch, confirm=_confirm_all_confirmed,
        slug=SLUG, log=lambda *a, **k: None,
    )
    assert any(u.lower().endswith(".pdf") for u in fetch_calls), \
        "a .pdf url should reach fetch now that fetch() extracts pdf text"
    assert "https://groundwater.kerala.gov.in" in fetch_calls


def test_pdf_seed_url_is_fetched_not_rejected():
    fetch_calls = []

    def counting_fetch(url):
        fetch_calls.append(url)
        return _fetch_all_confirmed(url)

    logged = []
    search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=counting_fetch, confirm=_confirm_all_confirmed,
        slug=SLUG, seed_url="https://a2p-energy.example/report.pdf",
        log=logged.append,
    )
    assert "https://a2p-energy.example/report.pdf" in fetch_calls
    assert not any("seed url is a pdf" in m for m in logged)


def test_pdf_url_counts_against_the_cover_cap():
    """A pdf url is a normal pool member now — cover() may spend a slot on
    it just like any other url, and a cap of 2 over a 3-url pool (one pdf)
    still only returns 2 confirmed sources."""
    provider = _FixedResponseProvider([
        "https://cgwb.gov.in/old_website/District_Profile/Kerala/kollam.pdf",
        "https://groundwater.kerala.gov.in",
        "https://groundwater.kerala.gov.in/kollam",
    ])
    result = search_sources(
        NAME, depth=TRACKED_TIER, provider=provider,
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, max_sources=2, log=lambda *a, **k: None,
    )
    assert len(result) == 2


def test_escalate_logs_when_the_widened_pool_has_nothing_new(monkeypatch):
    """`MAX_SOURCES_ESCALATE=0` widens the cap to itself — cover() re-picks
    the identical set, so every url is already in `seen_norm` and the second
    round has nothing to fetch. Must say so rather than silently no-op."""
    import worker.search_stage as search_stage_mod
    monkeypatch.setattr(search_stage_mod, "MAX_SOURCES_ESCALATE", 0)

    logged = []
    search_sources(
        NAME, depth=TRACKED_TIER, provider=_provider(),
        fetch=_fetch_all_confirmed, confirm=_confirm_all_confirmed,
        slug=SLUG, max_sources=1, escalate=True, log=logged.append,
    )
    assert any("no additional urls" in m for m in logged)
