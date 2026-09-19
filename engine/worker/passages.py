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

This module encodes whatever question set the caller hands it, and that is
now the decided behaviour rather than a degrade. `03-worker.md` §7 (decided
2026-09-14) splits the old, undefined `open question` into **filled** (≥1
answer in the ledger — what §11c's counter 1 reads) and **saturated** (a pass
added no value already held — what a future pass 2 would read here). Pass 1
has no saturated questions by construction, so the pass-1 encode set is every
`retrieval: true` question and the union is not inflated by `multi`-ness.
Narrowing the set to the unsaturated ones is the caller's job, and only from
pass 2, which §11b has not committed to building.

**Entity-density top-up.** All the buckets above are question-shaped
semantic queries, so a chunk that is mostly a list of names — "co-signed by
the X Collective, funded by the Y Foundation, coordinated with Z Trust" —
doesn't read as similar to "who is working on this"; it can rank low in
every bucket and never make a top-k cut, even though it is exactly the
`emits`/`edges` source material. `_entity_density()` is a cheap regex count
of capitalized multi-word runs (no ML, no new dependency, per this repo's
config.py: "no other config surface yet"); `select()` adds the top
`ENTITY_DENSITY_TOP_N` chunks by that score which no bucket already caught,
then runs them through the same `expand_neighbours()`/`_cap_tokens()` path
as everything else — no bypass of the token cap.

**India-anchor top-up (`kind: problem` only).** Same shape of miss, a
different axis: a chunk naming India or a named Indian institution can lose
every bucket to a denser global/other-country source even when both are
topically on-target — cosine similarity to a question string does not know
this corpus is India-anchored (`CLAUDE.md`). Measured on `cookfire-smoke`
2026-09-14: a WHO fact sheet entered the fetched pool once the search
queries got an India bias, but never won a single bucket's top-k against a
Nature global-projection paper and a Frontiers China cohort study — both
topically correct, neither India-specific. `_india_anchor_density()` is the
same cheap-regex-count shape as `_entity_density()` (a small term list, not
an ML classifier); `select(..., geography_bias=True)` adds the top
`INDIA_ANCHOR_TOP_N` chunks by that score which no bucket already caught,
through the same expand/cap path. Callers pass `geography_bias` only for
`kind: problem` — actors are legitimately global (a funder need not be
Indian), so this must never run on actor selection. This is the
belt-and-suspenders half of the fix; the primary one is `problem-core`'s
retrieval_query itself, reworded the same day to name "occurrence in India"
explicitly (`questions.yaml`) — a bucket that ranks India-relevant content
higher to begin with needs this top-up less, but a term-list top-up costs
nothing when the ranking already got it right (it only adds chunks no
bucket already kept).

**Candidate-identity gate.** All of the above ranks by topical similarity to
the question buckets; nothing checked that a chunk was actually about the
candidate being processed. 2026-09-19: `anaemia-mukt-bharat` (candidate.id
839) had all 20 of its extracted answers describe an unrelated org,
"WeTheChange" (a menstrual-health nonprofit). Root cause: one fetched source,
a LinkedIn page pulled in because it mentioned "Anaemia Mukt Bharat" once,
also carried an unrelated WeTheChange "we're hiring" job-ad paragraph
(feed/sidebar bleed from the page's own layout). That paragraph was a
near-perfect semantic match for buckets like funding/contact/ask-offer, so it
out-scored the ~34 genuinely on-topic chunks across nearly every bucket and
dominated the extraction prompt. `select(..., candidate_name=...)` adds a
cheap pre-filter, reusing `worker/identity.py`'s `_name_tokens`/
`_text_mentions_actor` (built for the structurally identical
`tara-mani-sah` channel-mismatch bug, see that module's docstring): before
ranking, narrow `chunks` to those that mention at least one of the
candidate's own distinctive name tokens, *if* any chunk does. If none of the
fetched chunks ever spell out the candidate's name (abbreviation-only or
pronoun-heavy source set — a real, if rarer, shape than the failure above),
the filter is a no-op rather than a wipeout: `select()` degrades to the
unfiltered pool, same "degraded selection rather than a crash" philosophy as
the encoder-unavailable path above (`03-worker.md` §13) — precision over
recall, with a non-zero-recall escape hatch rather than an empty result.
"""
from __future__ import annotations

import re
from typing import Sequence

from embed.model import encode
from text.chunk import Chunk
from worker.identity import _name_tokens, _text_mentions_actor
from worker.questions import Question, Registry
from worker.questions import REGISTRY as DEFAULT_REGISTRY

try:
    from worker.config import PASSAGE_TOKEN_CAP as _PASSAGE_TOKEN_CAP
    from worker.config import TOP_K_PER_BUCKET as _TOP_K_PER_BUCKET
    from worker.config import NEIGHBOUR_RADIUS as _NEIGHBOUR_RADIUS
    from worker.config import ENTITY_DENSITY_TOP_N as _ENTITY_DENSITY_TOP_N
    from worker.config import INDIA_ANCHOR_TOP_N as _INDIA_ANCHOR_TOP_N
except Exception:
    _PASSAGE_TOKEN_CAP = 9000
    _TOP_K_PER_BUCKET = 3
    _NEIGHBOUR_RADIUS = 1
    _ENTITY_DENSITY_TOP_N = 2
    _INDIA_ANCHOR_TOP_N = 2

# Two-or-more-capitalized-word run, e.g. "Zilla Parishad" or "Rural
# Development Trust" — the run must be >=2 words so a lone sentence-initial
# capital ("The scheme...") doesn't count as an entity on its own. A single
# internal "of" is tolerated ("Ministry of Labour", "Department of Mines")
# since official-body names routinely carry it — measured missing entirely
# without this (density 0 on "Ministry of Labour"). "and"/"the" are
# deliberately NOT tolerated here even though they also appear inside some
# names: both routinely separate two DIFFERENT names in a list ("the Adivasi
# Trust and Ministry of Health"), and allowing them merges two real matches
# into one, undercounting rather than fixing anything — checked empirically
# before adding "of" alone.
_ENTITY_RUN_RE = re.compile(
    r"\b[A-Z][a-zA-Z&.'-]*(?:\s+(?:of\s+)?[A-Z][a-zA-Z&.'-]*)+\b")


def _entity_density(text: str) -> int:
    """Count of capitalized multi-word runs in `text` — a cheap stand-in for
    "how many org/person names does this chunk name-drop", with no NER model
    (module docstring). Overcounts sentence-initial two-word capitals ("The
    Ministry...") and undercounts single-word names ("Oxfam") and names
    joined by "and"/"the" in a list; all three are accepted imprecision for
    a ranking signal, not a classification one."""
    return len(_ENTITY_RUN_RE.findall(text))


# India-anchor term list (module docstring's "India-anchor top-up"). Country
# names/demonyms plus currency denominations (crore/lakh/₹ are strong,
# low-false-positive signals — they essentially never appear in a China- or
# globally-scoped source) plus the institutional-source vocabulary
# `CLAUDE.md`'s own research standards name (IQAir, CREA, CGWB, CPCB, CSE,
# NFHS, UDISE+, ICMR, NITI Aayog, HLRN, Census) minus UNEP (global, not an
# India signal). Deliberately NOT state/city names — too many collide with
# common English words or other countries' places, unlike this shorter list.
_INDIA_TERMS = (
    "india", "indian", "bharat", "crore", "lakh", "₹",
    "niti aayog", "lok sabha", "rajya sabha", "ministry of",
    "government of india", "gov.in", "iqair", "crea", "cgwb", "cpcb", "cse",
    "nfhs", "udise", "icmr", "hlrn",
)
_INDIA_TERM_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in _INDIA_TERMS) + r")\b",
    re.IGNORECASE)


def _india_anchor_density(text: str) -> int:
    """Count of India-anchor term matches in `text` — same cheap-regex shape
    as `_entity_density()`, not a geography classifier. A chunk that never
    mentions India or an India-specific institution scores 0 and is never
    topped up; this is a recall net for chunks the bucket ranking missed,
    not a filter that penalises global chunks elsewhere in the prompt."""
    return len(_INDIA_TERM_RE.findall(text))


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
           neighbour_radius: int | None = None,
           geography_bias: bool = False,
           candidate_name: str | None = None) -> list[Chunk]:
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

    `geography_bias`: also run the India-anchor top-up (module docstring).
    Callers pass this only for `kind: problem` candidates — never for
    actors, which are legitimately global.

    `candidate_name`: the candidate-identity gate (module docstring,
    "Candidate-identity gate"), applied PER SOURCE, not across the whole
    pool. For each source that has at least one chunk mentioning one of the
    candidate's own distinctive name tokens, that source is narrowed to just
    its name-mentioning chunks before ranking/top-up/neighbour-expansion run
    — an unrelated, topically-similar chunk bled into an otherwise on-topic
    page (the WeTheChange-in-an-Anaemia-Mukt-Bharat-source shape) can no
    longer win a bucket. A source with ZERO name-mentioning chunks anywhere
    in itself is left untouched, not dropped — a source can legitimately
    read entirely as "the fund"/"it" after gate 2 already confirmed the page
    is about this candidate, and a global (pool-wide) version of this gate
    filtered such a source's real content out entirely whenever ANY other
    source in the pool happened to name-drop the candidate (regression
    caught by `test_seed_url_returned_by_search_is_not_a_second_source` /
    `test_no_resume_discards_the_cached_blocks`, 2026-09-19 — PAGE_B never
    says "Acumen" and was silently dropped from a 2-source pool because
    PAGE_A did). Per-source scoping keeps the WeTheChange-shaped protection
    (that source DOES have a name-mentioning chunk, so its noise chunk still
    loses) without punishing a legitimately pronoun-heavy source that has
    none at all.
    """
    k = k if k is not None else _TOP_K_PER_BUCKET
    chunks = list(chunks)
    if not chunks:
        return []

    if candidate_name:
        name_tokens = _name_tokens(candidate_name)
        if name_tokens:
            by_source: dict[str, list[Chunk]] = {}
            for c in chunks:
                by_source.setdefault(c.source_id, []).append(c)
            gated: list[Chunk] = []
            for src_chunks in by_source.values():
                mentioning = [c for c in src_chunks
                             if _text_mentions_actor(c.text, name_tokens)]
                gated.extend(mentioning if mentioning else src_chunks)
            chunks = gated

    bucket_ids = _bucket_ids(questions)
    if not bucket_ids:
        return _cap_tokens(chunks[:k], _PASSAGE_TOKEN_CAP)

    ranked_by_rank: dict[str, int] = {}   # chunk_ref -> best (lowest) rank seen
    kept: dict[str, Chunk] = {}

    # Encoded once for every bucket below, not once per bucket — the chunk
    # vectors are query-independent. `None` means the encoder is unreachable;
    # `_rank_chunks` then returns the given order, exactly as before.
    p_vecs = _encode_chunks(chunks)

    for bucket_id in bucket_ids:
        bucket = registry.bucket(bucket_id)
        query = bucket.retrieval_query
        if not query:
            continue
        ranking = _rank_chunks(query, chunks, p_vecs)
        for rank, ch in enumerate(ranking[:k]):
            ref = ch.chunk_ref
            if ref not in kept or rank < ranked_by_rank[ref]:
                kept[ref] = ch
                ranked_by_rank[ref] = rank

    ordered = sorted(kept.values(), key=lambda c: (ranked_by_rank[c.chunk_ref], c.source_id, c.ordinal))
    ordered = ordered + _entity_dense_top_up(chunks, kept)
    if geography_bias:
        already = {c.chunk_ref: c for c in ordered}
        ordered = ordered + _india_anchor_top_up(chunks, already)
    ordered = expand_neighbours(ordered, chunks, radius=neighbour_radius)
    return _cap_tokens(ordered, _PASSAGE_TOKEN_CAP)


def _entity_dense_top_up(chunks: Sequence[Chunk], already_kept: dict[str, Chunk],
                          top_n: int | None = None) -> list[Chunk]:
    """The name-list chunks the question-shaped buckets above miss (module
    docstring): the `top_n` chunks with the highest `_entity_density()` score
    among those *not* already in `already_kept`, ties broken by document
    order. A score of 0 never qualifies — no entity-like content means
    nothing to top up, not "least bad of the losers"."""
    top_n = _ENTITY_DENSITY_TOP_N if top_n is None else top_n
    if top_n <= 0:
        return []
    candidates = [c for c in chunks if c.chunk_ref not in already_kept]
    scored = [(c, _entity_density(c.text)) for c in candidates]
    scored = [(c, s) for c, s in scored if s > 0]
    scored.sort(key=lambda pair: (-pair[1], pair[0].source_id, pair[0].ordinal))
    return [c for c, _s in scored[:top_n]]


def _india_anchor_top_up(chunks: Sequence[Chunk], already_kept: dict[str, Chunk],
                          top_n: int | None = None) -> list[Chunk]:
    """The India-anchored chunks the question-shaped buckets above miss
    (module docstring): the `top_n` chunks with the highest
    `_india_anchor_density()` score among those *not* already in
    `already_kept`, ties broken by document order. A score of 0 never
    qualifies — a chunk with no India-anchor term is not "least bad of the
    losers", it genuinely isn't India-specific content."""
    top_n = _INDIA_ANCHOR_TOP_N if top_n is None else top_n
    if top_n <= 0:
        return []
    candidates = [c for c in chunks if c.chunk_ref not in already_kept]
    scored = [(c, _india_anchor_density(c.text)) for c in candidates]
    scored = [(c, s) for c, s in scored if s > 0]
    scored.sort(key=lambda pair: (-pair[1], pair[0].source_id, pair[0].ordinal))
    return [c for c, _s in scored[:top_n]]


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


def _encode_chunks(chunks: Sequence[Chunk]):
    """The chunk matrix, encoded once. `None` if the encoder is unreachable.

    Split out of `_rank_chunks` because the passage vectors do not depend on
    the query: `select()` ranks the same chunk set against one retrieval
    query per bucket, and encoding inside that loop re-encoded every chunk
    once per bucket. `questions.yaml` defines six problem buckets and six
    actor buckets, so a run was paying 6x the necessary passage encodes —
    the single largest embed cost in the worker, and pure waste.

    Failure is `None`, not a raise: `_rank_chunks`'s contract is to degrade
    to "whatever order chunking produced" when the encoder can't be loaded
    at all (no network for a first-time model download in a constrained
    test/CI environment), and hoisting must not turn that into a crash.
    """
    try:
        return encode([c.text for c in chunks], role="passage")
    except Exception:
        return None


def _rank_chunks(query: str, chunks: Sequence[Chunk], p_vecs=None) -> list[Chunk]:
    """`chunks` ranked best-first by cosine against `query`. Falls back to
    the given order (stable) if the encoder can't be loaded at all — e.g. no
    network for a first-time model download in a constrained test/CI
    environment — so a caller degrades to "whatever order chunking produced"
    rather than raising.

    `p_vecs` is the already-encoded chunk matrix from `_encode_chunks`. When
    omitted this encodes them itself, so the function stays callable on its
    own (tests, and any future single-query caller) with the same signature
    it had before the hoist.
    """
    if p_vecs is None:
        p_vecs = _encode_chunks(chunks)
        if p_vecs is None:
            return list(chunks)
    try:
        q_vec = encode([query], role="query")[0]
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
