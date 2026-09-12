"""The local encoder. Ported from ../slate_v2/core/encode.py, with one
substantive change and one contract that MiniLM did not have.

The change: `multilingual-e5-small` rather than `all-MiniLM-L6-v2`. §8 finding 2
promoted embeddings from a cross-lingual special case to the primary dedup path
for roughly half the corpus, and a corpus that will draw on Hindi, Marathi and
Tamil sources cannot have its dedup path be English-only. Same 384 dimensions,
so the vec0 column width is unchanged.

The contract: **e5 requires a prefix on every input, and the prefix marks the
input's role in the comparison, not the kind of text.** Two texts compared as
peers are both `query: ` — a problem's one-liner against a candidate's snippet
is symmetric, however document-shaped the candidate looks. `passage: ` is for
the long side of an asymmetric retrieval, where a short query is matched
against full documents; nothing in the engine does that yet (§8).

Omitting the prefix does not error. It silently degrades the vectors, which is
why `encode` takes `role` as a keyword with no default that can be gotten wrong
by accident, and refuses text that already carries a prefix.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Sequence

MODEL_NAME = os.getenv("FPH_EMBED_MODEL", "intfloat/multilingual-e5-small")
EMBED_DIM = 384

ROLES = ("query", "passage")
_PREFIXED = re.compile(r"^\s*(query|passage)\s*:\s", re.I)

_encoder = None


def get_encoder():
    """Singleton. First call downloads the model (~470 MB) and is slow; every
    call after is warm."""
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer(MODEL_NAME)
    return _encoder


def prefix(text: str, role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    text = (text or "").strip()
    if not text:
        raise ValueError("refusing to embed empty text")
    if _PREFIXED.match(text):
        raise ValueError(
            f"text already carries an e5 prefix: {text[:40]!r} — pass the bare "
            "text and let `role` decide")
    return f"{role}: {text}"


def fit(text: str, *, role: str = "query") -> str:
    """Truncate `text` so that, once prefixed, it survives the encoder whole.

    `texts.clip` bounds by characters, which is cheap and script-blind: 2,000
    characters is ~504 tokens of English but ~610 of Devanagari, so on the very
    corpus that motivated a multilingual encoder about a sixth of each long
    record was being dropped by the tokenizer with nothing said. Clipping in the
    tokenizer's own units makes the loss explicit.

    Every measurement below is taken on the *prefixed* string. The one-step
    version — tokenize `prefix + body`, drop `len(tokenize(prefix))` tokens off
    the front, keep the rest — assumes the joint tokenization begins with the
    prefix's own tokens, and a sub-word tokenizer gives no such guarantee: it
    may merge across the boundary, in which case the slice starts mid-word and
    the record is quietly embedded as something else. Nothing would have
    flagged it, since the result is still a valid string of the right length.
    """
    encoder = get_encoder()
    budget = getattr(encoder, "max_seq_length", 512) - 2   # the special tokens
    tok = encoder.tokenizer
    body = (text or "").strip()

    def length(s: str) -> int:
        return len(tok(prefix(s, role), add_special_tokens=False)["input_ids"])

    if length(body) <= budget:
        return body
    # Binary search on the body's own tokens for the longest prefix of it that
    # still fits once the role prefix is attached. ~9 tokenizations, and only
    # for a record that is actually over the limit.
    ids = tok(body, add_special_tokens=False)["input_ids"]
    lo, hi, best = 1, min(len(ids), budget), ""
    while lo <= hi:
        mid = (lo + hi) // 2
        cut = tok.decode(ids[:mid], skip_special_tokens=True).strip()
        if cut and length(cut) <= budget:
            best, lo = cut, mid + 1
        else:
            hi = mid - 1
    return best


def encode(texts: Sequence[str] | Iterable[str], *, role: str, batch_size: int = 32):
    """-> float32 (n, EMBED_DIM), L2-normalized, so cosine is a dot product."""
    if role not in ROLES:      # checked here too: an empty input never reaches
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    items = [prefix(t, role) for t in texts]
    if not items:              # `prefix`, and would have returned a valid shape
        import numpy as np
        return np.zeros((0, EMBED_DIM), dtype="float32")
    vectors = get_encoder().encode(
        items, batch_size=batch_size, normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False)
    return vectors.astype("float32")


def encode_one(text: str, *, role: str):
    """-> float32 (EMBED_DIM,)"""
    return encode([text], role=role)[0]
