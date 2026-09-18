"""Track E3 — passage assembly. Source texts in, prompt-ready `[Sn]` blocks
out (`04-worker-build-plan.md` §5 contract, `03-worker.md` §7-§8).

`assemble()` is a pure function: no database, no network, no LLM call. It
wires together three pieces that already exist and were each frozen/measured
on their own —

    `text/chunk.py:chunk()` / `degrade_chunk()`   -- stage 4
    `worker/passages.py:select()` / `expand_neighbours()`  -- stage 5
    the block layout `poc/poc2_extract.py:build_prompt()` measured

— and does nothing new numerically. What it adds is the counters: §7 of
`03-worker.md` and §3 correction 4 of `04-worker-build-plan.md` both name the
same unmeasured gap — "a source that made it through set cover is never
silently unread" is a rule about the *cap*, not about *selection*, and
PoC-2's own run could not tell whether a missing source was never picked up
by top-k in the first place, or picked up and then evicted by the token cap.
`assemble()` returns both counts so that question stops being unanswerable.

**Order of operations, and why it is not a single call to `select()`:**
`select()` does ranking, neighbour expansion *and* capping in one call, but
its capping step reads `PASSAGE_TOKEN_CAP` from `worker/config.py` as a
module-level constant, not as a parameter — so a caller that wants a
non-default `token_cap` cannot get it from `select()` alone. This module
calls `select(..., neighbour_radius=0)` to get the bare per-bucket ranking
without triggering `select()`'s own internal expansion+cap, then runs
`expand_neighbours()` and the cap itself, both against the caller's actual
`neighbour_radius` / `token_cap`. This is a deliberate decision the brief
does not spell out; documented here rather than left implicit. One
consequence: in `select()`'s own no-bucketed-questions fallback branch (`03-
worker.md` §7's "falls back to a stable in-order slice"), that branch
applies `_cap_tokens` internally at the *config* default before this module
ever sees the result — harmless in practice because the pre-expansion slice
it caps is bounded by `top_k` chunks, far under the 9,000-token default, but
worth naming as a latent seam rather than a guarantee.

Cap eviction, per `worker/passages.py:_cap_tokens`, never drops the first
(highest-priority) chunk it encounters for a given source — so a source that
survives selection always keeps at least one chunk in the final prompt.
`sources_dropped_by_cap` below is therefore expected to read 0 under the
current `_cap_tokens` rule; it is kept as a counter (not asserted away)
because it is the only thing that would catch a future change to that rule,
or a caller-supplied `token_cap` of 0, silently regressing the guarantee.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Mapping, Sequence

from store.db import norm
from text.chunk import Chunk, chunk, chunk_ref, degrade_chunk
from worker.extract_types import Answer, ConfirmedSource, PromptSource
from worker.passages import _cap_tokens, expand_neighbours, select
from worker.questions import Question

try:
    from worker.config import NEIGHBOUR_RADIUS as _NEIGHBOUR_RADIUS
    from worker.config import PASSAGE_TOKEN_CAP as _PASSAGE_TOKEN_CAP
    from worker.config import TOP_K_PER_BUCKET as _TOP_K_PER_BUCKET
except Exception:
    _TOP_K_PER_BUCKET = 3
    _PASSAGE_TOKEN_CAP = 9000
    _NEIGHBOUR_RADIUS = 1


def assemble(
    sources: Sequence[ConfirmedSource],
    questions: Sequence[Question],
    *,
    top_k: int | None = None,
    token_cap: int | None = None,
    neighbour_radius: int | None = None,
    degrade: bool = False,
    geography_bias: bool = False,
) -> tuple[list[PromptSource], dict[str, int | float]]:
    """`sources` (E1's confirmed fetches) -> `[Sn]`-labelled prompt blocks
    plus the counters that distinguish why a source did or didn't make it.

    `top_k`, `token_cap`, `neighbour_radius` default to `worker/config.py`'s
    `TOP_K_PER_BUCKET`, `PASSAGE_TOKEN_CAP`, `NEIGHBOUR_RADIUS` respectively
    — none of the three is hardcoded here. `degrade=True` chunks with
    `text/chunk.py:degrade_chunk()` (§13's encoder-unavailable path) instead
    of `chunk()`; everything downstream of chunking is unchanged; whether
    ranking itself falls back gracefully when the encoder truly is
    unreachable is `worker/passages.py:_rank_chunks`'s own concern, not
    this module's.

    `geography_bias` passes straight through to `select()` — the caller
    (`worker/worker.py`) sets it for `kind: problem` candidates only
    (`worker/passages.py`'s India-anchor top-up, added 2026-09-14).

    Labels are assigned `S1..Sn` by first appearance in the final, capped,
    priority-ordered chunk list — matching
    `poc/poc2_extract.py:build_prompt()`'s ordering exactly, since that is
    the layout PoC-2 measured. Within a source, chunks are joined in
    document order (by ordinal), never priority order.
    """
    top_k = _TOP_K_PER_BUCKET if top_k is None else top_k
    token_cap = _PASSAGE_TOKEN_CAP if token_cap is None else token_cap
    neighbour_radius = _NEIGHBOUR_RADIUS if neighbour_radius is None else neighbour_radius

    url_by_id = {s.source_id: s.url for s in sources}
    fetched_source_ids = {s.source_id for s in sources}

    # 1. Chunk every source (or degrade-chunk it).
    all_chunks: list[Chunk] = []
    for s in sources:
        chunker = degrade_chunk if degrade else chunk
        all_chunks.extend(chunker(s.text, source_id=s.source_id))

    # 2. Rank per bucket, deduped — bare, un-expanded (radius=0 here so this
    #    module controls expansion itself, at the caller's own radius, once).
    if all_chunks and questions:
        selected = select(all_chunks, questions, k=top_k, neighbour_radius=0,
                         geography_bias=geography_bias)
    else:
        selected = []

    # 3. Neighbour expansion at the caller's radius.
    expanded = expand_neighbours(selected, all_chunks, radius=neighbour_radius) if selected else []

    # 5. Enforce the token cap (never drops a source's first/best chunk).
    capped = _cap_tokens(expanded, cap=token_cap)

    # 4 (grouping) + 6 (chunk_refs): group survivors by source, document
    # order within each, label by first appearance in `capped`'s priority
    # order — matching `poc2_extract.build_prompt`.
    order: list[str] = []
    by_source: dict[str, list[Chunk]] = defaultdict(list)
    for c in capped:
        if c.source_id not in by_source:
            order.append(c.source_id)
        by_source[c.source_id].append(c)

    prompt_sources: list[PromptSource] = []
    for i, sid in enumerate(order, start=1):
        group = sorted(by_source[sid], key=lambda c: c.ordinal)
        text = "\n\n".join(c.text for c in group)
        refs = tuple(chunk_ref(c.source_id, c.ordinal) for c in group)
        prompt_sources.append(PromptSource(
            source_id=sid, label=f"S{i}", url=url_by_id.get(sid, ""),
            text=text, chunk_refs=refs,
            # Parallel to `refs`, so `prompts.py` can mark each chunk inside
            # the block and the parser can resolve the marker the model names
            # back to one `chunk_ref`. Joining is still done above because
            # `retry_per_source` and the verify pass send whole text.
            chunk_texts=tuple(c.text for c in group)))

    # -- counters --------------------------------------------------------
    selected_source_ids = {c.source_id for c in selected}
    in_prompt_source_ids = set(order)

    counters: dict[str, int | float] = {
        "sources_fetched": len(sources),
        "sources_in_prompt": len(in_prompt_source_ids),
        "sources_never_selected": len(fetched_source_ids - selected_source_ids),
        "sources_dropped_by_cap": len(selected_source_ids - in_prompt_source_ids),
    }

    # Neighbour expansion's real cost — cheap here: both lists are already
    # in hand, no extra encode() call (PoC-2 measured 1.4-2.9x chars /
    # 1.6-3.4x tokens on real prompts; §3 correction 4 measured 2.01x/2.33x).
    bare_tokens = sum(max(c.token_count, 0) for c in selected)
    bare_chars = sum(len(c.text) for c in selected)
    expanded_tokens = sum(max(c.token_count, 0) for c in expanded)
    expanded_chars = sum(len(c.text) for c in expanded)
    if bare_tokens > 0:
        counters["neighbour_expansion_tokens_ratio"] = expanded_tokens / bare_tokens
    if bare_chars > 0:
        counters["neighbour_expansion_chars_ratio"] = expanded_chars / bare_chars

    return prompt_sources, counters


# =========================================================== E4: the ledger ==
# `03-worker.md` §9. Two functions: one writes every answer to `finding`
# (the ledger), one derives claims from those same answers (pure). Nothing
# has ever written to `finding` — 0 rows live — so this is the ledger, not
# provenance retro-fitted onto one.


def write_findings(conn: sqlite3.Connection, candidate_id: int,
                   answers: Sequence[Answer], *,
                   urls: Mapping[str, str] | None = None,
                   chunk_texts: Mapping[str, str] | None = None) -> int:
    """One `finding` row per `Answer`. -> rows inserted.

    The only DB-touching function in this module; everything else here is
    pure, deliberately (§9 derives claims *from* findings, so the derivation
    must be testable without a database).

    `urls` maps `source_id` -> the fetched page's URL, for `finding.source_url`.
    It is optional because `source_id` is the durable join (`store/schema.sql`
    :323, E0) and the URL is reachable through it; passing it stores the URL
    a reviewer sees without a join, and matches §9's original column list.

    `chunk_texts` maps `chunk_ref` -> the paragraph text the caller already
    assembled for the prompt (`PromptSource.chunk_texts`,
    `worker/extract_types.py`), for `finding.chunk_text`
    (schema v5, `migrate/m0005_finding_chunk_text.py`). Resolved here rather
    than by a reader re-chunking `source.path` later, so the reference stays
    pinned to the paragraph extraction actually saw. Optional and looked up
    by `a.chunk_ref`; an answer with no chunk marker, or one from a path that
    never built a `chunk_texts` map (e.g. `retry_per_source`'s solo blocks),
    simply writes NULL — never guessed.

    `gathered_at` is left to the column default (`datetime('now')`). No
    commit: the caller owns the transaction, as everywhere else the worker
    writes (`worker.py:run_batch` commits once per candidate).
    """
    urls = urls or {}
    chunk_texts = chunk_texts or {}
    rows = [
        (candidate_id, a.question_id, a.answer, a.confidence,
         urls.get(a.source_id), a.source_id, a.chunk_ref, a.reason,
         chunk_texts.get(a.chunk_ref) if a.chunk_ref else None)
        for a in answers
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT INTO finding (candidate_id, question_id, answer, confidence, "
        "source_url, source_id, chunk_ref, reason, chunk_text) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


# -- consistency and specificity ------------------------------------------
#
# STARTING RULE, not a finding — the same status as `worker/gate2.py:29-36`'s
# two bands. Two answers are CONSISTENT when their `store/db.py:norm` forms
# (casefold, punctuation -> space, whitespace collapsed — the repo's existing
# name-match key, reused rather than a second normaliser invented here) are
# equal, or when one is a contiguous substring of the other. Among consistent
# answers the MOST SPECIFIC is the longest normalised form; the substring rule
# is what makes "longest" well-defined rather than arbitrary. Anything else is
# CONFLICTING, and §9 says a conflict is written down, not resolved.
#
# The obvious alternative NOT used here is embedding similarity ("9 lakh
# workers" vs "roughly 900,000 workers" are the same fact and this rule calls
# them a conflict). It is not used because it needs a threshold, and
# `gate2.py:29-36` records the measurement that makes a threshold unsafe:
# e5-small compresses similarity into a narrow high band (AUC 0.923 on 0.041
# mean separation for gate 1), so no global cutoff is both safe and useful.
# There is therefore NO numeric threshold anywhere in this code. The failure
# direction is deliberate: this rule over-reports conflicts, and an
# over-reported conflict is a claim that states two values with their sources
# — legible and correctable — whereas an under-reported one silently drops a
# side, which §9 forbids outright.


def _norm(text: str) -> str:
    return norm(text)


def _consistent(a: str, b: str) -> bool:
    """The starting rule above, on two already-normalised forms."""
    if not a or not b:
        return a == b
    return a == b or a in b or b in a


def _group(answers: Sequence[Answer]) -> list[list[Answer]]:
    """Partition answers into consistency groups, most specific first within
    each group and each group's first member its representative.

    Greedy and order-independent: answers are sorted by normalised length
    descending (ties by the answer text, so the result is deterministic), and
    each joins the first existing group whose representative it is consistent
    with — which, the representative being the longest, means "is a substring
    of". Only reached for a `multi` question; a single-valued question that
    produces more than one group is a conflict, and conflicts are not grouped.
    """
    groups: list[list[Answer]] = []
    for a in sorted(answers, key=lambda x: (-len(_norm(x.answer)), x.answer)):
        for g in groups:
            if _consistent(_norm(g[0].answer), _norm(a.answer)):
                g.append(a)
                break
        else:
            groups.append([a])
    return groups


def _sides(answers: Sequence[Answer]) -> list[tuple[str, list[str]]]:
    """Distinct answer values (first surface form per normalised form, in
    first-seen order) with the source ids that carried each. Used to render a
    conflict: every side survives, none is averaged away."""
    seen: dict[str, tuple[str, list[str]]] = {}
    for a in answers:
        key = _norm(a.answer)
        if key not in seen:
            seen[key] = (a.answer, [])
        if a.source_id not in seen[key][1]:
            seen[key][1].append(a.source_id)
    return list(seen.values())


def _disagreement(sides: Sequence[tuple[str, list[str]]]) -> str:
    """One claim value that states the disagreement, per §9 and CLAUDE.md's
    "when sources disagree, write the disagreement". All sides, each with its
    sources, never a mean and never a pick."""
    parts = [f'"{value}" ({"source" if len(srcs) == 1 else "sources"} '
             f'{", ".join(srcs)})' for value, srcs in sides]
    return "sources disagree — " + "; ".join(parts)


def _confidence(answers: Sequence[Answer]) -> float | None:
    """The lowest stated confidence among the answers behind a claim, or None
    if none of them stated one. Lowest rather than mean or max: a claim is no
    more reliable than its weakest input, and for a conflict claim in
    particular an average would be the very move §9 rules out."""
    values = [a.confidence for a in answers if a.confidence is not None]
    return min(values) if values else None


def claims_from_findings(
    answers: Sequence[Answer], *, registry=None,
) -> tuple[list[dict], list[str]]:
    """§9's four rules, as a pure function. -> (claims, notes).

    Claims are `{"field": …, "value": …, "confidence": …}` — the shape
    `worker/worker.py:_split_claims` already consumes (it reads `field` and
    `value`; `confidence` rides along as the extraction contract's third key,
    `03-worker.md` §8). `notes` is human-readable strings about what this did,
    for a log line, in the same spirit as `prompts.parse_answers`'s `problems`.

    The four rules, verbatim from §9:
      one finding for a question   -> the claim comes from it directly;
      multiple, consistent         -> from the MOST SPECIFIC, never concatenated;
      multiple, conflicting        -> ONE claim stating the disagreement, both
                                      values with their sources — never
                                      averaged, never silently dropped;
      zero                         -> no claim. Not a guess, not "unknown".
    The last is structural: no answer for a question means that question is
    simply absent from the input, so nothing is emitted for it and nothing
    iterates over the registry looking for holes to fill.

    `registry` defaults to `worker/questions.py`'s module-level REGISTRY; it is
    a parameter only so a test can inject one. The registry is needed for the
    `field` (a question's `claim_field`) and for `multi`, and it is pure
    parsed YAML — no DB, no network.
    """
    if registry is None:
        from worker.questions import REGISTRY as registry  # noqa: N806

    claims: list[dict] = []
    notes: list[str] = []

    # Group by question, preserving first-appearance order for determinism.
    by_question: dict[str, list[Answer]] = defaultdict(list)
    for a in answers:
        by_question[a.question_id].append(a)

    for qid, group in by_question.items():
        try:
            question = registry.get(qid)
        except KeyError:
            notes.append(f"{qid}: not in the question registry — "
                         f"{len(group)} finding(s) kept in the ledger, no claim")
            continue

        field = question.claim_field
        # Two claim_field shapes are not bare fields and cannot be turned into
        # a claim from the answer text alone: `emits/edges` (the answer drives
        # stage 8, not a claim) and the templated `ask:need:<kind>` /
        # `channel:<kind>`, whose `<kind>` the model supplies per answer and
        # this function never sees. Emitting them anyway would hand
        # `_apply_other_claims` a literal "<kind>" to log and drop. The finding
        # is written either way; only the claim is withheld.
        if field == "emits/edges" or "<" in field:
            # Phrased as the routing decision it is, not as a complaint
            # (2026-09-18). The old wording — "claim_field 'emits/edges' is not
            # a bare claim field" — fires on every single problem candidate,
            # reads like a warning about a misconfiguration, and sent a reader
            # of the run log hunting for a bug in questions.yaml. Nothing is
            # wrong when this fires; it is the designed path.
            notes.append(f"{qid}: {len(group)} finding(s) kept, routed to "
                         f"{'stage 8 (emits/edges)' if field == 'emits/edges' else f'{field} at write time'} "
                         f"rather than a claim — as designed, not an error")
            continue

        if len(group) == 1:
            a = group[0]
            claims.append({"field": field, "value": a.answer,
                           "confidence": a.confidence})
            continue

        norms = [_norm(a.answer) for a in group]
        all_consistent = all(
            _consistent(norms[i], norms[j])
            for i in range(len(norms)) for j in range(i + 1, len(norms)))

        if all_consistent:
            best = max(group, key=lambda a: (len(_norm(a.answer)), ))
            # `max` on length alone is ambiguous only between answers whose
            # normalised forms are equal, where either is the same claim.
            claims.append({"field": field, "value": best.answer,
                           "confidence": _confidence(group)})
            notes.append(f"{qid}: {len(group)} consistent findings -> the most "
                         f"specific ({best.source_id}), not a concatenation")
            continue

        if question.multi:
            # A `multi` question's field legitimately holds several values
            # (`legs`, `tag:mechanism`), so disagreement is not the right
            # reading of two different answers: each consistency group is one
            # value, represented by its most specific member. Same rule, one
            # claim per group instead of one claim per question. §9 does not
            # cover `multi`; this is the reading that keeps §9's other three
            # rules intact for it.
            groups = _group(group)
            for g in groups:
                claims.append({"field": field, "value": g[0].answer,
                               "confidence": _confidence(g)})
            notes.append(f"{qid}: multi-valued — {len(group)} findings -> "
                         f"{len(groups)} claim(s), one per consistency group")
            continue

        sides = _sides(group)
        claims.append({"field": field, "value": _disagreement(sides),
                       "confidence": _confidence(group)})
        notes.append(f"{qid}: {len(sides)} conflicting values across "
                     f"{len(group)} findings -> one claim stating the "
                     f"disagreement; no side dropped, nothing averaged")

    return claims, notes
