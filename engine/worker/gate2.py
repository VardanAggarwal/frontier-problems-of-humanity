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

These constants are provisional, unmeasured, and awaiting the kind of
calibration `embed/calibrate.py` ran for gate 1 — do not treat them as a
settled finding. When that calibration exists, replace the two numbers, not
the three-way shape: an `uncertain` band is doing real work (§8's whole
argument against a bare cutoff) regardless of where its edges sit.
"""
from __future__ import annotations

import sqlite3

from embed.model import encode_one

# Deliberately conservative and far apart, in lieu of a calibration sweep:
# below MISMATCH_BELOW the page's opening shares almost nothing with the
# candidate's own name+context, which not even topic-adjacency should produce;
# above CONFIRMED_ABOVE two texts about the same named entity are expected to
# sit, going by the general shape of the actor/problem bands in §8 (unrelated
# pairs cluster around 0.80-0.84 there). Everything between is uncertain.
MISMATCH_BELOW = 0.55
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
    left = f"{candidate_name} {candidate_context}".strip()
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
