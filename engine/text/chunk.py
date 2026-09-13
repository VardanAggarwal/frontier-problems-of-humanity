"""Token-aware paragraph chunking — track C (`04-worker-build-plan.md` §4,
`engine/03-worker.md` §7 "Chunking").

`chunk(text) -> [Chunk]` is a pure function: no network, no database, no
model loading at import time. It does load the encoder's own tokenizer
(`embed/model.py:get_encoder`) the first time it is called, because the whole
point — per PoC-3 — is to measure token count against the tokenizer that will
actually embed the text, not against a character proxy. `embed/texts.py`'s
`MAX_CHARS` is a character *pre-bound* (~544 English tokens), not a window
guard, and is not reused here for that reason.

**Respect the window when chunking; do not rely on `fit()` to rescue an
oversized chunk.** PoC-3 (`engine/poc/poc3-results.md` §5) demonstrated the
failure this exists to prevent: a chunk handed to `encode()` over the 512-token
window is embedded on its head alone — cosine 1.0000 against its own
truncation — with no error and no warning. `fit()` only helps a caller who
calls it; a chunk that already fits under `CHUNK_TOKENS` (`worker/config.py`)
never needs rescuing.

Boundary rule: **prefer paragraph boundaries.** A paragraph under the token
target is its own chunk (adjacent short paragraphs are not merged — merging
would blur `chunk_ref`'s claim that one ordinal is one paragraph's worth of
text, and PoC-1's target sections are themselves paragraph-shaped). A
paragraph over the target is split further, on sentence boundaries where any
exist, else on a hard token cut — never truncated and dropped, because a
split chunk still contributes to the union in `passages.select`, where a
truncated-and-discarded one would silently lose text.

**No overlap, deliberately, and no `CHUNK_OVERLAP` constant to set.**
`03-worker.md` §7 originally specified `CHUNK_OVERLAP = 48` so a figure and
its denominator could not be separated by a chunk boundary. This module never
implemented it and now never will: PoC-1d (`engine/poc/poc1d-results.md`)
measured overlap repairing 95.8% of 284 real straddles while costing the
three strongest retrieval buckets most of their AUC — overlap puts a
neighbouring section's text inside every chunk's *embedding*. The straddle
repair moved to `worker/passages.py:expand_neighbours()`, which adds chunk
n±1 of each retrieved chunk to the extraction prompt at selection time. That
is only possible because ordinals here are contiguous per source, so keep
them that way: a gap in the ordinal sequence would silently break the
neighbour lookup rather than raise.

`Chunk` is frozen contract 3 (`04-worker-build-plan.md` §4): text, source id,
ordinal, token count. The ordinal is what makes a deterministic `chunk_ref`
(`03-worker.md` §9) possible without persisting a vector (§1b) — `chunk_ref`
is source id + ordinal, computed in this module so both writers (whatever
calls `chunk()`) and readers (whatever audits a finding) compute the same
string from the same two fields.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from embed.model import get_encoder

# Settled by PoC-3 (`engine/poc/poc3-results.md`): window 512, special tokens
# 2, `passage: ` prefix 3 tokens, chunk target 320 tokens (187 tokens margin).
# Track C reads these from `worker/config.py` so a later sweep moves one
# number in one place; the values are duplicated here as a fallback only if
# imported standalone, and are overridden by the config import below.
CHUNK_TOKENS = 320
_PASSAGE_PREFIX_TOKENS = 3
_SPECIAL_TOKENS = 2

try:
    from worker.config import CHUNK_TOKENS as _CFG_CHUNK_TOKENS
    CHUNK_TOKENS = _CFG_CHUNK_TOKENS
except Exception:
    pass

_BLANK_LINES = re.compile(r"\n\s*\n+")
# Sentence-ish split: keep the delimiter attached to the sentence that ends
# with it. Deliberately simple — this corpus is mostly English research prose
# with the occasional Devanagari proper noun (PoC-3 §2), not general-purpose
# sentence segmentation.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?॥।])\s+")


@dataclass(frozen=True)
class Chunk:
    text: str
    source_id: str
    ordinal: int
    token_count: int

    @property
    def chunk_ref(self) -> str:
        """Deterministic id: source id + ordinal, per §1b — auditable without
        a persisted vector."""
        return f"{self.source_id}:{self.ordinal}"


def chunk_ref(source_id: str, ordinal: int) -> str:
    """Compute a `chunk_ref` from its two parts without a `Chunk` in hand —
    for a reader (e.g. auditing `finding.chunk_ref`, §9) that only has the
    id string and wants to confirm it parses, or the reverse direction."""
    return f"{source_id}:{ordinal}"


def _token_len(text: str) -> int:
    """Token count of the bare text, i.e. what it will cost once `passage: `
    and the two special tokens are added at encode time. Matches the budget
    check PoC-3 ran: `length(prefix(s, role))`."""
    tok = get_encoder().tokenizer
    return len(tok(text, add_special_tokens=False)["input_ids"])


def _budget() -> int:
    encoder = get_encoder()
    window = getattr(encoder, "max_seq_length", 512)
    return window - _SPECIAL_TOKENS - _PASSAGE_PREFIX_TOKENS


def _split_paragraph(paragraph: str, target: int) -> list[str]:
    """A paragraph whose token count exceeds `target`: split on sentence
    boundaries, greedily packing sentences up to `target`; if a single
    sentence alone exceeds `target` (or there is no sentence boundary at
    all), fall back to a hard token-boundary cut via the tokenizer's own
    offsets — never silently truncated."""
    sentences = [s for s in _SENTENCE_SPLIT.split(paragraph.strip()) if s]
    if not sentences:
        sentences = [paragraph.strip()]

    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sent in sentences:
        sent_tokens = _token_len(sent)
        if sent_tokens > target:
            # Flush whatever is pending, then hard-cut this one sentence.
            if current:
                pieces.append(" ".join(current))
                current, current_tokens = [], 0
            pieces.extend(_hard_cut(sent, target))
            continue
        if current and current_tokens + sent_tokens > target:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sent)
        current_tokens += sent_tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def _hard_cut(text: str, target: int) -> list[str]:
    """Last resort: cut on the tokenizer's own token boundaries so a run-on
    sentence with no punctuation still splits without truncating text.

    Decode-then-retokenize is not guaranteed to round-trip to the same count
    — a sub-word cut can land mid-word, and the decoded, re-tokenized piece
    can come back a token or two *longer* than the slice that produced it.
    So each piece is shrunk (never grown) until it actually measures at or
    under `target`, the same defensive stance `embed/model.py:fit()` takes
    for exactly this reason.
    """
    tok = get_encoder().tokenizer
    ids = tok(text, add_special_tokens=False)["input_ids"]
    if not ids:
        return [text] if text.strip() else []

    pieces: list[str] = []
    i = 0
    while i < len(ids):
        end = min(i + target, len(ids))
        piece = tok.decode(ids[i:end], skip_special_tokens=True).strip()
        while piece and _token_len(piece) > target and end > i + 1:
            end -= 1
            piece = tok.decode(ids[i:end], skip_special_tokens=True).strip()
        if piece:
            pieces.append(piece)
        i = end
    return pieces or [text]


def chunk(text: str, source_id: str = "", *, target_tokens: int | None = None) -> list[Chunk]:
    """Token-aware paragraph chunking against the encoder's own tokenizer.

    Paragraph boundaries (blank-line-separated blocks) are preferred; a
    paragraph at or under `target_tokens` is kept whole as one chunk. A
    paragraph over the target is split (`_split_paragraph`) rather than
    truncated. The budget enforced is `target_tokens`, which already leaves
    room for the `passage: ` prefix and the two special tokens added at
    encode time (`_budget()` computes the hard ceiling those leave; passing a
    `target_tokens` above it is the caller's mistake to make, not this
    function's to silently correct, since `CHUNK_TOKENS`'s whole point is to
    sit well under that ceiling with margin — see PoC-3).

    Empty/blank input returns `[]`. Ordinals are 0-based, contiguous, and
    stable for a given input (same text in, same ordinals out — no
    non-determinism from set/dict ordering).
    """
    target = target_tokens if target_tokens is not None else CHUNK_TOKENS
    text = (text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in _BLANK_LINES.split(text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[Chunk] = []
    ordinal = 0
    for para in paragraphs:
        tokens = _token_len(para)
        if tokens <= target:
            chunks.append(Chunk(text=para, source_id=source_id,
                                 ordinal=ordinal, token_count=tokens))
            ordinal += 1
            continue
        for piece in _split_paragraph(para, target):
            piece_tokens = _token_len(piece)
            chunks.append(Chunk(text=piece, source_id=source_id,
                                 ordinal=ordinal, token_count=piece_tokens))
            ordinal += 1
    return chunks


def degrade_chunk(text: str, source_id: str = "", *, max_chars: int | None = None) -> list[Chunk]:
    """The degrade path (`04-worker-build-plan.md` §4 track-C row, `03-worker.md`
    §13: "Encoder unavailable -> Fall back to first-N-chars per source,
    capped. Degraded, not broken"). No tokenizer, no model — a single
    character-capped chunk per source, so the caller always gets *something*
    when the real chunker's dependency (the encoder) is unavailable.

    Deliberately not the function `select()` calls when the encoder IS
    available; this is what a caller reaches for directly when it isn't. It
    carries `token_count=-1` as a sentinel: the true token count is exactly
    what an unavailable encoder cannot supply, and inventing one from a
    chars-per-token guess would misreport the very failure this path exists
    to be honest about.
    """
    if max_chars is None:
        try:
            from worker.config import DEGRADE_CHUNK_CHARS as max_chars
        except Exception:
            max_chars = 2000
    text = (text or "").strip()
    if not text:
        return []
    capped = text[:max_chars]
    return [Chunk(text=capped, source_id=source_id, ordinal=0, token_count=-1)]
