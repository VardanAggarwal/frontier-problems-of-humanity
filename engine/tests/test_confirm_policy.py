"""Tests for search/confirm_policy.py — track D's source-confirmation policy
layer (04-worker-build-plan.md §5, "Two holes found by the user", #1).

Fixtures below stand in for the real failure shapes PoC-2 hit feeding the
recorded URL pool for one actor: an off-topic page that fetches fine with
1000+ words (a currency converter / mountain-bike site / Japanese Wikipedia
article), a blocked/empty page, a thin page, the seed URL, and a genuinely
on-topic page. No network, no DB, no model — everything here is a
hand-built SourceVerdict.
"""
from __future__ import annotations

import copy

import pytest

from search.confirm_policy import (
    CONFIRMED,
    MISMATCH,
    SEARCH,
    SEED,
    ConfirmationDecision,
    SourceVerdict,
    apply_confirmations,
    requires_confirmation,
)


# ---------------------------------------------------------------------------
# requires_confirmation — the hole itself: today only SEED gets a gate-2
# pass; the fix is that both classes require one.
# ---------------------------------------------------------------------------

def test_requires_confirmation_true_for_seed():
    assert requires_confirmation(SEED) is True


def test_requires_confirmation_true_for_search():
    # This is the assertion that encodes the fix: today's worker.py skips
    # confirmation entirely for search-sourced URLs. The policy says no
    # origin is exempt.
    assert requires_confirmation(SEARCH) is True


def test_requires_confirmation_rejects_unknown_origin():
    with pytest.raises(ValueError):
        requires_confirmation("some-other-origin")


# ---------------------------------------------------------------------------
# SourceVerdict validation
# ---------------------------------------------------------------------------

def test_source_verdict_rejects_unknown_origin():
    with pytest.raises(ValueError):
        SourceVerdict(source_id="s1", url="https://x", origin="bogus", verdict=CONFIRMED)


def test_source_verdict_rejects_unknown_verdict_string():
    with pytest.raises(ValueError):
        SourceVerdict(source_id="s1", url="https://x", origin=SEED, verdict="definitely")


def test_source_verdict_allows_none_verdict():
    # None means "gate2 never ran" — a legitimate, distinct state.
    v = SourceVerdict(source_id="s1", url="https://x", origin=SEED, verdict=None)
    assert v.verdict is None


# ---------------------------------------------------------------------------
# apply_confirmations — the five PoC-2 failure shapes
# ---------------------------------------------------------------------------

def test_seed_url_confirmed_is_kept():
    v = SourceVerdict(
        source_id="seed-1", url="https://actual-org.example/about",
        origin=SEED, verdict=CONFIRMED, cosine=0.91,
    )
    [decision] = apply_confirmations([v])
    assert decision.kept is True
    assert decision.verdict == CONFIRMED
    assert decision.source_id == "seed-1"
    assert "confirmed" in decision.reason.lower()


def test_search_sourced_off_topic_page_with_long_text_is_dropped():
    # PoC-2's currency-converter / mountain-bike / ja.wikipedia shape: fetches
    # `ok`, well over 1000 words, but the embedding says mismatch.
    v = SourceVerdict(
        source_id="search-1", url="https://ja.wikipedia.org/wiki/Some_large_number",
        origin=SEARCH, verdict=MISMATCH, cosine=0.31, text_chars=6000,
    )
    [decision] = apply_confirmations([v])
    assert decision.kept is False
    assert decision.verdict == MISMATCH
    # Reason must record WHY, not just that it was dropped.
    assert "mismatch" in decision.reason.lower()
    assert "0.31" in decision.reason or "0.310" in decision.reason


def test_blocked_or_empty_page_has_no_verdict_and_is_dropped():
    # No fetched text at all -> gate2 was never run -> verdict is None.
    v = SourceVerdict(
        source_id="search-2", url="https://blocked.example/paywall",
        origin=SEARCH, verdict=None, text_chars=None,
    )
    [decision] = apply_confirmations([v])
    assert decision.kept is False
    assert decision.verdict is None
    reason = decision.reason.lower()
    assert "no" in reason and ("text" in reason or "verdict" in reason)


def test_thin_page_confirmed_is_downgraded_when_threshold_supplied():
    # A short page that happens to embed as "confirmed" (e.g. a redirect
    # stub mentioning the candidate's name once). With no thin_page_chars
    # supplied, this module makes no claim about thinness (unmeasured
    # threshold) and the source is kept outright.
    v = SourceVerdict(
        source_id="search-3", url="https://example.com/redirect-stub",
        origin=SEARCH, verdict=CONFIRMED, cosine=0.85, text_chars=40,
    )
    [decision_default] = apply_confirmations([v])
    assert decision_default.kept is True
    assert "downgrad" not in decision_default.reason.lower()

    # With a threshold supplied, the same verdict is kept but flagged rather
    # than treated as a clean confirm.
    [decision_flagged] = apply_confirmations([v], thin_page_chars=200)
    assert decision_flagged.kept is True
    assert "thin_page_chars" in decision_flagged.reason
    assert "40" in decision_flagged.reason


def test_thin_page_threshold_never_upgrades_a_mismatch():
    v = SourceVerdict(
        source_id="search-4", url="https://example.com/thin-mismatch",
        origin=SEARCH, verdict=MISMATCH, cosine=0.20, text_chars=10,
    )
    [decision] = apply_confirmations([v], thin_page_chars=200)
    assert decision.kept is False
    assert decision.verdict == MISMATCH


def test_genuinely_on_topic_search_sourced_page_is_kept():
    v = SourceVerdict(
        source_id="search-5", url="https://actual-org.example/press-release",
        origin=SEARCH, verdict=CONFIRMED, cosine=0.88, text_chars=1500,
    )
    [decision] = apply_confirmations([v])
    assert decision.kept is True
    assert decision.verdict == CONFIRMED


def test_uncertain_is_kept_and_flagged_not_silently_resolved():
    v = SourceVerdict(
        source_id="search-6", url="https://example.com/maybe",
        origin=SEARCH, verdict="uncertain", cosine=0.67,
        note="gate2: cosine 0.670 in the unresolved middle band (0.55-0.8)",
    )
    [decision] = apply_confirmations([v])
    assert decision.kept is True
    assert decision.verdict == "uncertain"
    assert "flag" in decision.reason.lower()
    assert "0.670" in decision.reason or "cosine 0.670" in decision.reason


# ---------------------------------------------------------------------------
# Every source gets a decision — no silent drops before the call (PoC-2:
# sources vanishing before the call at 3/4 for three of five actors).
# ---------------------------------------------------------------------------

def test_every_input_source_produces_exactly_one_decision():
    verdicts = [
        SourceVerdict(source_id="a", url="https://a", origin=SEED, verdict=CONFIRMED, cosine=0.9),
        SourceVerdict(source_id="b", url="https://b", origin=SEARCH, verdict=MISMATCH, cosine=0.2),
        SourceVerdict(source_id="c", url="https://c", origin=SEARCH, verdict=None),
        SourceVerdict(source_id="d", url="https://d", origin=SEARCH, verdict="uncertain",
                      cosine=0.6, note="middle band"),
    ]
    decisions = apply_confirmations(verdicts)
    assert len(decisions) == len(verdicts)
    assert {d.source_id for d in decisions} == {"a", "b", "c", "d"}
    assert all(isinstance(d, ConfirmationDecision) for d in decisions)
    assert all(d.reason for d in decisions), "every decision must record a reason, kept or dropped"


def test_empty_input_returns_empty_output():
    assert apply_confirmations([]) == []


# ---------------------------------------------------------------------------
# Purity: no network, no DB, deterministic on repeated calls.
# ---------------------------------------------------------------------------

def test_purity_no_network_or_db_imports():
    import search.confirm_policy as mod
    import inspect
    src = inspect.getsource(mod)
    for banned in ("sqlite3", "requests", "httpx", "urllib", "socket"):
        assert banned not in src, f"confirm_policy.py must not import {banned}"


def test_purity_deterministic_repeated_calls():
    verdicts = [
        SourceVerdict(source_id="a", url="https://a", origin=SEED, verdict=CONFIRMED, cosine=0.9),
        SourceVerdict(source_id="b", url="https://b", origin=SEARCH, verdict=MISMATCH, cosine=0.2,
                      text_chars=5000),
        SourceVerdict(source_id="c", url="https://c", origin=SEARCH, verdict=None),
    ]
    # Deep-copy the input to rule out the function mutating its argument and
    # that mutation being the only reason two calls would differ.
    verdicts_copy = copy.deepcopy(verdicts)

    first = apply_confirmations(verdicts)
    second = apply_confirmations(verdicts_copy)

    assert first == second
    assert verdicts == verdicts_copy  # input untouched
