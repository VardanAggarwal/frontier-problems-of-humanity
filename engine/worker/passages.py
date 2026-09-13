"""Passage selection — track C (`04-worker-build-plan.md` §4, `03-worker.md`
§7 "Selection: top-k per question, never a threshold").

`select(chunks, questions, k) -> [Chunk]` is a pure function: no network, no
database, no pipeline knowledge (it does not know `run_batch` exists). It
loads the encoder (`embed/model.py`) the first time it actually needs to
encode something, same as `text/chunk.py`.

**Selection is per bucket, not per question** (PoC-1c,
`engine/poc/poc1c-results.md`): 12 buckets, not 35 queries. A bucket's
`retrieval_query` (from `engine/questions.yaml`, loaded via
`worker/questions.py`) is encoded once as `query: `; every chunk is encoded
once as `passage: `; the top `k` chunks by cosine go into that bucket's slice
of the union. Questions with `retrieval: false` — q2_type, q3_legs,
q5_ecosystem_role, q7_representation_unit, q13_failure_note — drive no
retrieval at all: they are inference-only, reading whatever the retrieval
buckets already pulled, so they never reach this module as a thing to encode.

**Straddle repair lives here, not in the chunker** (PoC-1d,
`engine/poc/poc1d-results.md` §5-6). `03-worker.md` §7 specified
`CHUNK_OVERLAP = 48` so that a figure and its denominator could not be
separated by a chunk boundary; PoC-1d measured that setting repairing 95.8%
of 284 real straddles but costing the three strongest retrieval buckets most
of their AUC (reach 0.893→0.649, status 0.977→0.837, identity 0.503→0.367)
and 33% of the passage budget's source diversity, because overlap puts a
neighbouring section's text inside the *embedding* of every chunk. So
overlap stays 0 at chunk time and the same repair is made here, at selection
time: `expand_neighbours()` adds chunk n±1 of each selected chunk to the
extraction prompt. Contaminated context never reaches an embedding; the
extraction model still sees the sentence that got cut. The cost is prompt
tokens (`NEIGHBOUR_RADIUS`), paid against `PASSAGE_TOKEN_CAP` — which is why
expansion runs *before* the cap, never after.

`open question` (`03-worker.md` §7, §1d) is not yet a settled predicate for
`multi` questions (`04-worker-build-plan.md` §1d) — this module does not
try to settle it. Per §1c's stated degrade: with no closing rule, encode the
full question/bucket set every pass; the passage union is larger than it
needs to be, but nothing here is wrong for it. Filtering "open" questions
down to a smaller set is the caller's job, once §1d lands, not this one's.
"""
from __future__ import annotations

from typing import Sequence

from embed.model import encode
from text.chunk import Chunk
from worker.questions import Question, Registry
from worker.questions import REGISTRY as DEFAULT_REGISTRY

try:
    from worker.config import PASSAGE_TOKEN_CAP as _PASSAGE_TOKEN_CAP
    from worker.config import TOP_K_PER_BUCKET as _TOP_K_PER_BUCKET
    from worker.config import NEIGHBOUR_RADIUS as _NEIGHBOUR_RADIUS
except Exception:
    _PASSAGE_TOKEN_CAP = 9000
    _TOP_K_PER_BUCKET = 3
    _NEIGHBOUR_RADIUS = 1


def _bucket_ids(questions: Sequence[Question]) -> list[str]:
    """Distinct bucket ids referenced by `questions`, in first-seen order.
    Questions with no bucket (retrieval: false, or unbucketed) contribute
    nothing — they are read from whatever the buckets above them pulled."""
    seen: list[str] = []
    for q in questions:
        if q.bucket and q.bucket not in seen:
            seen.append(q.bucket)
    return seen


def select(chunks: Sequence[Chunk], questions: Sequence[Question], k: int | None = None,
           *, registry: Registry = DEFAULT_REGISTRY,
           neighbour_radius: int | None = None) -> list[Chunk]:
    """Top-`k` chunks per retrieval bucket touched by `questions`, unioned
    and deduped by `chunk_ref`, capped at `PASSAGE_TOKEN_CAP` tokens with at
    least one chunk kept per source (§7).

    `chunks` may span multiple sources (a candidate's whole fetched set) —
    this function does not care; it only ranks. Returns `[]` for no chunks
    or no bucketed questions (nothing to retrieve against). Falls back to a
    stable in-order slice, per bucket, if the encoder cannot be reached
    (import/download failure) — degraded selection rather than a crash;
    `03-worker.md` §13's actual encoder-unavailable path is `text.chunk.
    degrade_chunk`, upstream of this function, but a caller that got real
    chunks and then lost the encoder between chunking and selection should
    still get something ordered, not an exception.

    Each retrieved chunk then pulls its neighbours (`neighbour_radius`,
    default `NEIGHBOUR_RADIUS`) out of `chunks` before the cap is applied —
    PoC-1d's straddle repair, see the module docstring. Pass `0` to switch it
    off and get the bare retrieved set, which is what a cost measurement of
    the expansion wants for its baseline.
    """
    k = k if k is not None else _TOP_K_PER_BUCKET
    chunks = list(chunks)
    if not chunks:
        return []

    bucket_ids = _bucket_ids(questions)
    if not bucket_ids:
        return _cap_tokens(chunks[:k], _PASSAGE_TOKEN_CAP)

    ranked_by_rank: dict[str, int] = {}   # chunk_ref -> best (lowest) rank seen
    kept: dict[str, Chunk] = {}

    for bucket_id in bucket_ids:
        bucket = registry.bucket(bucket_id)
        query = bucket.retrieval_query
        if not query:
            continue
        ranking = _rank_chunks(query, chunks)
        for rank, ch in enumerate(ranking[:k]):
            ref = ch.chunk_ref
            if ref not in kept or rank < ranked_by_rank[ref]:
                kept[ref] = ch
                ranked_by_rank[ref] = rank

    ordered = sorted(kept.values(), key=lambda c: (ranked_by_rank[c.chunk_ref], c.source_id, c.ordinal))
    ordered = expand_neighbours(ordered, chunks, radius=neighbour_radius)
    return _cap_tokens(ordered, _PASSAGE_TOKEN_CAP)


def expand_neighbours(selected: Sequence[Chunk], pool: Sequence[Chunk],
                      radius: int | None = None) -> list[Chunk]:
    """Each chunk in `selected` plus its `radius` neighbours either side,
    drawn from `pool` by (`source_id`, `ordinal`) — PoC-1d's replacement for
    `CHUNK_OVERLAP` (module docstring).

    Pure, order-preserving and idempotent-in-spirit: `selected` is a
    priority-ordered list (best first), and a neighbour inherits the priority
    of the best-ranked chunk that pulled it in, so the result sorts as
    contiguous runs — a selected chunk sits next to its own neighbours in the
    returned order, which is what makes the straddled sentence readable again
    in the prompt. A chunk that is itself selected keeps its own priority and
    is never demoted by also being someone's neighbour.

    Neighbours never cross a source boundary: ordinals are only contiguous
    within one source (`text/chunk.py`), so `(source_id, ordinal)` is the
    lookup key, never the ordinal alone. `radius <= 0` returns `selected`
    unchanged. Nothing here consults the token cap — the caller applies it
    after, because the whole point is that the cap must see the expanded set.
    """
    radius = _NEIGHBOUR_RADIUS if radius is None else radius
    selected = list(selected)
    if radius <= 0 or not selected:
        return selected

    by_source: dict[str, dict[int, Chunk]] = {}
    for c in pool:
        by_source.setdefault(c.source_id, {})[c.ordinal] = c

    priority: dict[str, int] = {}
    out: dict[str, Chunk] = {}
    for i, c in enumerate(selected):   # selected chunks first: own priority wins
        ref = c.chunk_ref
        if ref not in priority:
            priority[ref] = i
            out[ref] = c
    for i, c in enumerate(selected):
        siblings = by_source.get(c.source_id, {})
        for delta in range(-radius, radius + 1):
            if delta == 0:
                continue
            n = siblings.get(c.ordinal + delta)
            if n is None:
                continue
            ref = n.chunk_ref
            if ref in out:
                # Already in, from its own selection or from a better-ranked
                # parent — `i` ascends, so the first claim is always the best
                # one and there is nothing to improve.
                continue
            priority[ref] = i
            out[ref] = n

    return sorted(out.values(), key=lambda c: (priority[c.chunk_ref], c.source_id, c.ordinal))


def _rank_chunks(query: str, chunks: Sequence[Chunk]) -> list[Chunk]:
    """`chunks` ranked best-first by cosine against `query`. Falls back to
    the given order (stable) if the encoder can't be loaded at all — e.g. no
    network for a first-time model download in a constrained test/CI
    environment — so a caller degrades to "whatever order chunking produced"
    rather than raising."""
    try:
        q_vec = encode([query], role="query")[0]
        p_vecs = encode([c.text for c in chunks], role="passage")
    except Exception:
        return list(chunks)
    scored = sorted(
        zip(chunks, (float(q_vec @ v) for v in p_vecs)),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [c for c, _score in scored]


def _cap_tokens(chunks: Sequence[Chunk], cap: int) -> list[Chunk]:
    """Enforce `PASSAGE_TOKEN_CAP` (§7): drop lowest-scoring (i.e. last, in
    the already-ranked order passed in) chunks first, but never drop a
    source's *only* remaining chunk — "a source that made it through set
    cover is never silently unread."""
    chunks = list(chunks)
    total = sum(max(c.token_count, 0) for c in chunks)
    if total <= cap or not chunks:
        return chunks

    kept: list[Chunk] = []
    running = 0
    sources_seen: set[str] = set()
    dropped: list[Chunk] = []
    for c in chunks:
        cost = max(c.token_count, 0)
        if running + cost <= cap or c.source_id not in sources_seen:
            kept.append(c)
            running += cost
            sources_seen.add(c.source_id)
        else:
            dropped.append(c)
    return kept
