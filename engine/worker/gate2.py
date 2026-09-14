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

from embed.model import encode_one
from embed.texts import clip

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
    # `right` is already bounded by PREVIEW_CHARS (500 chars) — `clip()`'s
    # own threshold is 2,000, so wrapping an already-500-char string in it
    # would be a no-op; not done. `left`'s `candidate_context` is the one
    # unbounded side (a caller may hand in the full extraction text), hence
    # `clip()` here and not on `right`.
    #
    # A token-dense 500-char `right` (CJK, or a scraped page's symbol-heavy
    # nav/footer) CAN still exceed e5's 512-token budget and trip the
    # tokenizer's own "longer than the specified maximum sequence length"
    # warning — confirmed live 2026-09-15 on one of candidate 12's fetched
    # sources with `left` already short (empty `candidate_context`).
    # Verified directly (not assumed) that this is cosmetic, not a
    # correctness bug: `SentenceTransformer.encode()` truncates internally
    # regardless of the warning — a forced >512-token string round-tripped
    # to a well-formed, unit-norm 384-dim vector with no exception. The
    # warning is noisy but harmless; not chased further than this note.
    left = clip(f"{candidate_name} {candidate_context}".strip())
    right = cleaned_text[:PREVIEW_CHARS]
    if not left or not right:
        return "uncertain", 0.0, "gate2: empty candidate context or empty fetched text"

    a = encode_one(left, role="query")
    b = encode_one(right, role="query")
    # Plain zip-sum rather than a numpy `(a * b).sum()`: both are
    # L2-normalized so the dot product is cosine either way, but summing by
    # hand works whether `encode_one` returns a numpy array (the real
    # encoder) or a plain list (test doubles), with no numpy dependency here.
    cosine = float(sum(x * y for x, y in zip(a, b)))

    if cosine < MISMATCH_BELOW:
        return "mismatch", cosine, ""
    if cosine > CONFIRMED_ABOVE:
        return "confirmed", cosine, ""
    return ("uncertain", cosine,
            f"gate2: cosine {cosine:.3f} in the unresolved middle band "
            f"({MISMATCH_BELOW}-{CONFIRMED_ABOVE}) — bands are provisional, "
            f"not measured; flag for review rather than deciding")
