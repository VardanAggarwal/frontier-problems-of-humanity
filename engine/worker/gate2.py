"""Gate 2 — the free, embedding-only post-fetch confirmation (01-minimal.md
§5 "post-fetch, cheap: first ~500 cleaned chars: is this the entity we
thought?").

§8's "The gate-1 screen ranks well and thresholds badly" finding is about a
*different* comparison (candidate vs the problem it's being screened against,
scored on 20,000 random pairs), but the underlying fact it establishes —
e5-small compresses similarity into a narrow high band, and AUC 0.923 with
only 0.041 mean separation means no single global cutoff is both safe and
useful — has no reason to be less true of this comparison (candidate-name-
plus-context vs a fetched page's opening). No equivalent sweep has been run
for THIS pairing, so this module does not claim a measured threshold. It
picks two widely-separated, deliberately conservative bands and says so:
below the low band the page is almost certainly not about the named entity
at all (mismatch); above the high band it almost certainly is (confirmed);
the wide middle is `uncertain` and must not be silently resolved either way.

MISMATCH_BELOW was calibrated 2026-09-14 against a real URL-pool sweep
(`poc/gate2-band-sweep.md`); CONFIRMED_ABOVE was left where it was because the
same sweep supports it. Neither is a settled finding — five actors is a small
sample and the labels are the author's eye, not ground truth. When a fuller
calibration exists, replace the two numbers, not the three-way shape: an
`uncertain` band is doing real work (§8's whole argument against a bare
cutoff) regardless of where its edges sit.
"""
from __future__ import annotations

import sqlite3
from typing import Sequence

from embed.model import EmbedTimeout, encode, encode_one, fit, with_timeout

# MISMATCH_BELOW was 0.55, chosen conservatively in lieu of a sweep. The sweep
# has now been run — `poc/gate2-band-sweep.md`, five actors, ~200 pooled URLs
# against cached text — and it found 0.55 to be DEAD CODE: the lowest cosine
# observed anywhere was 0.712, so no source has ever been dropped by a
# `mismatch` verdict, and none could be. That is e5-small's compression doing
# exactly what §8 said it does.
#
# 0.78 is what that sweep supports, and no more precision than that is claimed:
# with the candidate's real context passed, no genuine page in the sample fell
# below it (lowest: 0.789, a real LinkedIn post), while it drops the clear junk
# — currency converters, recipe blogs, `360.cn` portal pages, Windows help
# articles — that clustered 0.712-0.779. The junk sitting just above it
# (0.78-0.80) is not dropped; it lands in `uncertain`, which no longer enters
# the extraction prompt (see `search/confirm_policy.py`).
#
# CONFIRMED_ABOVE stays 0.80. The sweep supports it as-is on organisations
# (genuine minima 0.811 / 0.831 / 0.848 against junk maxima 0.797 / 0.796 /
# 0.775) and shows it failing on ONE case it cannot be fixed for by moving:
# `jyoti-pande-lavakare`, where four wrong-entity pages sharing the given name
# (a water heater manufacturer among them) score 0.801-0.813 while her own
# LinkedIn post and her own book score 0.789-0.790. A common personal name
# beats a 500-char cosine at any single global threshold; that case needs a
# second signal, not a different number.
#
# The three-way shape is unchanged, per this module's own instruction: when a
# fuller calibration exists, move the numbers, not the shape.
MISMATCH_BELOW = 0.78
CONFIRMED_ABOVE = 0.80

PREVIEW_CHARS = 500


def confirm(conn: sqlite3.Connection, candidate_name: str,
           candidate_context: str, cleaned_text: str) -> tuple[str, float, str]:
    """-> (verdict, cosine, note). verdict in confirmed/uncertain/mismatch.

    `uncertain` carries a non-empty `note` — the worker's caller must treat
    it as "keep going, but flag for review," never as a silent pass or a
    silent fail (module docstring, and 01-minimal.md §5/§9: escalation is
    queued, not blocking, and not resolved by guessing).
    """
    # `right` is bounded by PREVIEW_CHARS (500 chars), which a token-dense
    # script (CJK, or a scraped page's symbol-heavy nav/footer) can still
    # blow past e5's 512-token budget — confirmed live 2026-09-15 on one of
    # candidate 12's fetched sources. `left`'s `candidate_context` is the
    # unbounded side (a caller may hand in the full extraction text).
    #
    # Originally both were bounded with `clip()`, a cheap character-based
    # pre-bound — fine for a small overflow, but candidate 28's run
    # (2026-09-14T22:45) hit a 4464-token overflow (8.7x the limit) on a
    # `clip()`-ed `left` and the worker hung indefinitely mid-`encode()` with
    # no exception, killed only by an external signal. `fit()` (unlike
    # `clip()`) truncates against the encoder's own tokenizer, so the string
    # handed to `encode_one()` is never more than the true token budget — but
    # candidate 71 (2026-09-15T07:54) hung again at 2922 tokens even with
    # `fit()` in place, so token-exact truncation alone does not bound the
    # *cost of computing* the truncation (`fit()`'s own first pass tokenizes
    # the whole untruncated input). See `_FIT_PRECLIP_CHARS` and
    # `EmbedTimeout` in embed/model.py for the two-part fix: a cheap char cap
    # ahead of `fit()`, and a wall-clock timeout as the backstop.
    left_raw = f"{candidate_name} {candidate_context}".strip()
    right_raw = cleaned_text[:PREVIEW_CHARS]
    if not left_raw or not right_raw:
        return "uncertain", 0.0, EMPTY_NOTE
    # `fit()` refuses empty text (embed/model.py:prefix), hence the emptiness
    # check above runs on the raw strings first.
    #
    # `with_timeout` — not the bare calls — because both candidate 28
    # (2026-09-14T22:45) and candidate 71 (2026-09-15T07:54) hung
    # indefinitely right here with no exception, killed only by an external
    # signal. A timeout turns that into an `uncertain` verdict instead of a
    # dead worker. Wrapped as a closure over the module's own `fit`/
    # `encode_one` (not a fixed helper) so tests can still monkeypatch
    # `gate2.fit`/`gate2.encode_one` directly.
    try:
        a = with_timeout(lambda: encode_one(fit(left_raw, role="query"), role="query"),
                         label="gate2 left-side embed")
        b = with_timeout(lambda: encode_one(fit(right_raw, role="query"), role="query"),
                         label="gate2 right-side embed")
    except EmbedTimeout as exc:
        return "uncertain", 0.0, f"gate2: {exc} — treated as unconfirmed, routed to verify pass"
    return _band(_cosine(a, b))


EMPTY_NOTE = "gate2: empty candidate context or empty fetched text"


def _band(cosine: float) -> tuple[str, float, str]:
    """The three-way verdict, factored out of `confirm` so `confirm_many`
    bands identically — one copy of the numbers, one copy of the note."""
    if cosine < MISMATCH_BELOW:
        return "mismatch", cosine, ""
    if cosine > CONFIRMED_ABOVE:
        return "confirmed", cosine, ""
    return ("uncertain", cosine,
            f"gate2: cosine {cosine:.3f} in the unresolved middle band "
            f"({MISMATCH_BELOW}-{CONFIRMED_ABOVE}) — bands are provisional, "
            f"not measured; flag for review rather than deciding")


def _cosine(a, b) -> float:
    """Plain zip-sum rather than a numpy `(a * b).sum()`: both sides are
    L2-normalized so the dot product is cosine either way, but summing by
    hand works whether the encoder returned a numpy array (the real one) or
    a plain list (a test double), with no numpy dependency here."""
    return float(sum(x * y for x, y in zip(a, b)))


def confirm_many(conn: sqlite3.Connection, candidate_name: str,
                 candidate_context: str,
                 texts: "Sequence[str]") -> "list[tuple[str, float, str]]":
    """`confirm` over N fetched pages at once -> one `(verdict, cosine, note)`
    per entry of `texts`, in the same order. Same bands, same notes, same
    verdicts as calling `confirm` N times — this is purely a cost change.

    Two wastes in the per-URL loop it replaces (`search_stage._fetch_and_route`),
    both from the fact that **`left` does not vary across the loop**: the
    candidate's name and evidence are fixed for the whole run
    (`search_stage.search_sources` takes `name`/`evidence` once), while only
    the fetched page changes.

    1. `confirm` re-ran `fit()` + `encode_one()` on that identical `left`
       string once per URL — N-1 encodes and N-1 tokenizer passes computing a
       vector already in hand. Here it is computed once.
    2. The `right` sides went one `encode_one` at a time. Here they go as one
       batched `encode()` call, which is where the local encoder is actually
       efficient: measured on this machine (2026-09-18, multilingual-e5-small,
       mps), a batch of 50 costs ~1.45s against ~2.1s for 50 singles, and the
       gap widens with N.

    Deliberately NOT a module-level cache of the left vector, which would be
    the obvious way to get win 1 without a new function: `tests/test_worker.py`
    monkeypatches `gate2.encode_one`/`gate2.fit` per test, so a vector cached
    across calls would be computed by one test's double and handed to the
    next. Hoisting inside a single call has no cross-call state to leak.

    `EmbedTimeout` keeps `confirm`'s contract — the whole batch degrades to
    `uncertain` (routed to the verify pass), never to a silent pass or fail.
    """
    rights = [(t or "")[:PREVIEW_CHARS].strip() for t in texts]
    left_raw = f"{candidate_name} {candidate_context}".strip()
    if not left_raw:
        return [("uncertain", 0.0, EMPTY_NOTE) for _ in rights]

    # Which rows have something to compare at all. `fit()` refuses empty text
    # (embed/model.py:prefix), so the emptiness check runs on the raw strings
    # first, exactly as `confirm` does.
    live = [i for i, r in enumerate(rights) if r]
    out: list[tuple[str, float, str]] = [
        ("uncertain", 0.0, EMPTY_NOTE) for _ in rights]
    if not live:
        return out

    # The batch timeout scales with N — `with_timeout`'s 45s default is sized
    # for a single call plus cold start (embed/model.py:with_timeout), and a
    # batch of 40 legitimately takes longer than a batch of 1 without being
    # the candidate-28 class of hang this bounds.
    batch_timeout = 45.0 + 1.0 * len(live)
    try:
        a = with_timeout(
            lambda: encode_one(fit(left_raw, role="query"), role="query"),
            label="gate2 left-side embed")
        b_vecs = with_timeout(
            lambda: encode([fit(rights[i], role="query") for i in live],
                           role="query"),
            timeout_s=batch_timeout,
            label=f"gate2 right-side embed (batch of {len(live)})")
    except EmbedTimeout as exc:
        note = (f"gate2: {exc} — treated as unconfirmed, routed to verify pass")
        return [("uncertain", 0.0, note) for _ in rights]

    for i, b in zip(live, b_vecs):
        out[i] = _band(_cosine(a, b))
    return out
