"""SimHash near-duplicate detection — tier 0, pure, no model.

Catches the same document reaching the corpus twice in the same language:
syndicated press releases, mirrored pages, a story reprinted with a
different headline. Exact hashing misses all of these, because
timestamps, session ids and rotating banners perturb the bytes.

Run this on CLEANED text, never on raw HTML — the strip in clean.py is
load-bearing for dedup, not only for token cost.

What this CANNOT do is match a document against its translation. That is
the job of the cross-lingual embedding pass, which runs only on what
survives here.

Measurements behind the constants: EVIDENCE.md §simhash-perturbation.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

BITS = 64
BANDS = 4                  # 4 × 16 bits; see band_keys() for why 4
BAND_BITS = BITS // BANDS
DEFAULT_SHINGLE = 4        # measured: wrapped 0-1, reworded 15, unrelated 28
DEFAULT_THRESHOLD = 3      # Hamming distance at or below which we call it a dup
MIN_SHINGLES = 200         # floor where even heavy boilerplate stays within
                           # DEFAULT_THRESHOLD (3 at 204 words); see EVIDENCE.md

_WORD = re.compile(r"\w+", re.UNICODE)


def normalize(text: str) -> str:
    """Fold everything that varies without changing what the document says."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    return " ".join(_WORD.findall(text))


def _hash64(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(),
                          "big")


def shingles(text: str, k: int = DEFAULT_SHINGLE) -> list[str]:
    words = normalize(text).split()
    if len(words) < k:
        return [" ".join(words)] if words else []
    return [" ".join(words[i:i + k]) for i in range(len(words) - k + 1)]


def simhash(text: str, k: int = DEFAULT_SHINGLE) -> int:
    """64-bit SimHash of `text`.

    Short inputs (fewer than k words) degrade to a plain hash of the
    normalized text: with too few shingles the bit votes are dominated by
    a handful of features and near-duplicate distance stops meaning
    anything. Callers that care should check `is_reliable`.
    """
    grams = shingles(text, k)
    if not grams:
        return 0
    votes = [0] * BITS
    for g in grams:
        h = _hash64(g)
        for b in range(BITS):
            votes[b] += 1 if (h >> b) & 1 else -1
    out = 0
    for b in range(BITS):
        if votes[b] > 0:
            out |= 1 << b
    return out


def is_reliable(text: str, k: int = DEFAULT_SHINGLE,
                min_shingles: int = MIN_SHINGLES) -> bool:
    """Whether a SimHash comparison on this text means anything at all.

    Below MIN_SHINGLES the boilerplate perturbation exceeds
    DEFAULT_THRESHOLD and real duplicates are missed, so short documents
    must fall through to the embedding pass instead of being declared
    unique here. The floor is set where the measured curve holds against
    a heavy wrapper, not merely a light one — EVIDENCE.md
    §simhash-perturbation.
    """
    return len(shingles(text, k)) >= min_shingles


def distance(a: int, b: int) -> int:
    return ((a ^ b) & ((1 << BITS) - 1)).bit_count()


def is_duplicate(a: int, b: int, threshold: int = DEFAULT_THRESHOLD) -> bool:
    return distance(a, b) <= threshold


def band_keys(h: int) -> list[str]:
    """Blocking keys for candidate lookup without an all-pairs scan.

    Two hashes within Hamming distance 3 must agree on at least one of 4
    bands — 3 differing bits cannot dirty 4 disjoint bands — so this
    loses nothing at the default threshold. Proved, not measured.
    """
    return [f"{i}:{(h >> (i * BAND_BITS)) & ((1 << BAND_BITS) - 1):0{BAND_BITS // 4}x}"
            for i in range(BANDS)]
