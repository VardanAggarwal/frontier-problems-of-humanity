"""The two prompts (01-minimal.md §4, §5): a batched pre-fetch screen (gate 1)
and a claims extraction, shared between problem and actor processing because
"Problem Agent and Actor Processing differ only in target table and prompt."

Both functions are pure string-building — no I/O, no model call — so they are
testable without a network and without `worker.llm`.

--------------------------------------------------------------------------
Claims field-name convention (used by `extract_prompt` and read by
`worker.run_batch` when it writes claims back):

  - A bare field name (`title`, `one_line`, `status`, `legs`, `depth`,
    `ecosystem_role`, `lifecycle`, `affected_led`, `representation_unit`,
    `stance`, `geography`, `contact_route`, `gap_note`, ...) must match a real
    column on `problem` or `actor` in schema.sql. These go through
    `store.db.put`.
  - `"tag:<ns>"` (e.g. `"tag:mechanism"`, `"tag:onset"`) is a classification
    tag — goes through `store.db.tag` with that namespace, value = the
    claim's `value`. Namespace must be one of `store/tags.py`'s REGISTRY.
  - `"ask:need:<kind>"` / `"ask:offer:<kind>"` is an actor need/offer — goes
    through an INSERT into the `ask` table, direction split out of the field
    name, `kind` the free-text remainder (e.g. `"ask:need:funding"` ->
    direction="need", kind="funding"), `text` = the claim's `value`.
  - `"channel:<kind>"` (e.g. `"channel:twitter"`, `"channel:newsletter"`) is
    a follow channel — goes through an INSERT into `channel`, `kind` the
    remainder, `url` or `handle` = the claim's `value` (whichever it looks
    like).
  - Anything else is not a recognised field and the writer logs it and moves
    on rather than crashing the batch (01-minimal.md build-order step 3,
    "write").

`claims` never carries prose blobs — each claim is one field, one value, one
confidence — because a claim graph that stores paragraphs is a second corpus
with no schema, which is the exact failure relational storage (§3) exists to
avoid.
"""
from __future__ import annotations

import json

from worker.extract_types import Answer, PromptSource
from worker.questions import REGISTRY

BATCH_SIZE = 50


def screen_prompt(items: list[dict]) -> tuple[str, str]:
    """Gate 1 (§5, §8 Layer 3/"the gate-1 screen"): pre-fetch, batched, judged
    on title/snippet/URL alone (Mode A) or a registry field map (Mode B, §10 —
    the function does not care which fields a candidate dict carries, only
    that it carries an `id`).

    Tuned for recall, not precision (§5): "An affected-led collective with a
    thin Facebook presence and no website looks identical to noise in a
    title-and-snippet screen... Let tier 4 do the rejecting." The prompt says
    this outright rather than leaving it to the model's own judgment of what
    "relevant" means, because the failure mode (quietly dropping the exact
    long-tail actors the sweep exists to find) is invisible unless the
    instruction is explicit.
    """
    system = (
        "You are a screening pass for a research pipeline that catalogues "
        "every organisation and named individual working on documented "
        "civilizational failures (public health, safety, environment, "
        "labour, and similar). You decide only whether a candidate is "
        "PLAUSIBLY RELEVANT enough to fetch and read in full — not whether "
        "it is well-documented, well-funded, or well-known.\n\n"
        "Bias hard toward keeping things. An affected-led collective with a "
        "thin Facebook presence and no website looks, on a title and "
        "snippet alone, identical to noise — and it is exactly the kind of "
        "actor this pipeline exists to find. A later, more expensive pass "
        "reads the full page and can still reject it then; nothing recovers "
        "a candidate discarded here. Only discard a candidate when it is "
        "CLEARLY: spam / SEO filler, wrong topic entirely (not adjacent, "
        "actually unrelated), in a language you cannot assess for topic at "
        "all, or a dead/parked page with no content signal whatsoever. When "
        "in doubt, keep it.\n\n"
        "Respond with strict JSON only, no prose, no markdown fences: "
        '{"decisions": [{"id": <id>, "keep": true|false, "reason": '
        '"<one line>"}, ...]}. Include exactly one decision per candidate id '
        "given, in any order."
    )
    lines = [
        "Screen these candidates. For each, decide keep or discard per the "
        "rule above.", "",
    ]
    for item in items:
        lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    prompt = "\n".join(lines)
    return system, prompt


_EXTRACT_COMMON = (
    "Extract structured claims from the text below about the named entity. "
    "Never write prose summaries as a claim value — a claim is one field, "
    "one short value, one confidence in [0, 1]. If the text does not "
    "support a field, omit it; do not guess.\n\n"
    "Also list `emits`: other organisations or named individuals mentioned "
    "in the text who look worth a candidate record of their own (co-"
    "petitioners, funders, grantees, officials, affected-led leaders spoken "
    "for by an NGO, coalition partners, etc). And list `edges`: typed "
    "relations this text evidences between the entity and another named "
    "actor or problem, with `edge_kind` one of: part_of, member_of, "
    "works_on, cites, funds, board, cohort, convenes, portfolio, "
    "affiliated, parent_org, superseded_by. `relevance` on a `works_on` "
    "edge is 0 (mentioned) / 1 (adjacent) / 2 (works it) / 3 "
    "(load-bearing) — omit if the text does not support a judgment.\n\n"
    "Respond with strict JSON only, no prose, no markdown fences:\n"
    '{"claims": [{"field": "...", "value": "...", "confidence": 0.0}, ...],\n'
    ' "emits":  [{"kind": "problem"|"actor", "name": "...", "hint": "..."}],\n'
    ' "edges":  [{"dst_name": "...", "dst_kind": "problem"|"actor", '
    '"edge_kind": "...", "relevance": 0|1|2|3|null, "evidence": "..."}]}'
)

_PROBLEM_SYSTEM = (
    "You extract facts about a documented failure instance or need — a "
    "`problem` record in a catalogue of civilizational failures — from "
    "source text. Relevant fields: `title`, `one_line` (a one-sentence "
    "browse-card definition), `status` (stub|researched), `geography` (a "
    "JSON list of place names/scopes), `needs_legs` (a JSON list from "
    "activism, institution, enterprise, service — which response types this "
    "problem needs), `gap_note` (a short paragraph on what's missing, if "
    "the text supports one), and classification tags: `tag:mechanism` "
    "(the causal pattern — aggregation-masks-failure, "
    "spend-mismatched-to-source, instrument-keyed-to-wrong-object, "
    "authority-mismatched-to-harm, primary-vs-derivative-burden, "
    "solution-at-hand-blocked, compensation-substitutes-for-counting, "
    "within-tier-loop, second-half-never-built, "
    "visible-win-strands-residual, or unclassified), `tag:onset` "
    "(acute|chronic|latent), `tag:agent` (what triggers the harm), "
    "`tag:channel` (direct|structural|cultural-normative|"
    "ambient-accidental), `tag:satisfier_relation` "
    "(absence|violator|pseudo-satisfier|maldistribution|degraded-quality). "
    "Do not invent a tier or need id — those come from the existing browse "
    "tree, not from source text.\n\n" + _EXTRACT_COMMON
)

_ACTOR_SYSTEM = (
    "You extract facts about an org or named individual working on a "
    "documented failure — an `actor` record — from source text, per the "
    "\"who is working on this\" method: establish what leg they work "
    "(activism / institution / enterprise / service — enterprise is "
    "market-payer only, service is donor-funded direct delivery with no "
    "earned revenue, a hybrid org carries both as separate revenue "
    "streams), what makes them viable on that leg, and how to reach them. "
    "Relevant fields: `title`, `type` (org|individual), `legs` (JSON list "
    "from activism/institution/enterprise/service), `depth` "
    "(registry|tracked — tracked is for actors operating where the harm "
    "is: affected-led local collectives, field enterprises, local "
    "regulators actually acting; registry is for cited-but-not-monitored "
    "actors like academics, ministers, national advocacy NGOs), "
    "`lifecycle` (operating|scaling|distressed|dormant|acquired|shut|"
    "won-and-dissolved), `ecosystem_role` (JSON list from funder, "
    "intermediary, capacity-builder, convener, field-builder, researcher, "
    "operator, platform), `affected_led` (yes|no|partial), "
    "`representation_unit` (local-affected|central-org|enterprise|"
    "central-at-named-legitimacy-cost), `stance` (works-the-remedy|"
    "neutral|organised-against-remedy|ambiguous), `geography`, "
    "`contact_route`. Needs and offers are `ask:need:<kind>` / "
    "`ask:offer:<kind>` (value = the free-text ask, e.g. "
    "`ask:need:funding`). Follow channels are `channel:<kind>` (value = "
    "the URL or handle, e.g. `channel:twitter`).\n\n" + _EXTRACT_COMMON
)


def extract_prompt(kind: str, entity_name: str, text: str) -> tuple[str, str]:
    """Claims extraction — the paid tier-4 call (§7), one per surviving
    candidate. `kind` is "problem" or "actor"; this is the literal "two
    prompts" of §4 — one shared function, a kind-conditioned system prompt.
    """
    if kind not in ("problem", "actor"):
        raise ValueError(f"kind must be 'problem' or 'actor', got {kind!r}")
    system = _PROBLEM_SYSTEM if kind == "problem" else _ACTOR_SYSTEM
    prompt = (
        f"Entity name: {entity_name}\n\n"
        f"Source text (may be empty — a bare registry row with no document "
        f"yet is legitimate; extract what you can from the name alone in "
        f"that case, or return empty lists):\n\n{text}"
    )
    return system, prompt


# ── batched extraction (`03-worker.md` §8, validated by PoC-2) ───────────────
#
# `extract_prompt()` above stays untouched — a later task decides the
# switchover to this one. Everything below is ported from `poc/poc2_extract.py`
# (`system_prompt`, `build_prompt`, `label_map`), which measured 95/95 answers
# carrying a valid `source_id` (`poc/poc2-results.md` Q2) and one retry
# rescuing the one malformed response observed (Q1). The wording that passed
# is kept verbatim; nothing here redesigns it.
#
# KNOWN DEFECT, carried forward rather than fixed (`poc/poc2c-spec.md`
# "Why 2 and 2b could not answer the question", and PoC-2's own record): the
# system prompt below self-contradicts. Rule 1 forbids merging two sources
# into one answer and gives every answer a single `source_id`; rule 2
# instructs writing a disagreement "naming both sides and both source ids",
# which that same one-slot schema cannot express. PoC-2b tried a prose fix
# (V1) and a structural `disagreements[]` slot (V2); both scored 0/3, but
# against a plant that was unanswerable by construction (the contradiction
# never landed on a question the sheet asks), so neither the contradiction
# nor either fix is validated. Do not adopt V1 or V2 here — `poc2c-spec.md`
# is the unrun test that would settle it.

def _question_block(kind: str) -> str:
    """One `- <id>: <question>` line per question of `kind`, in registry
    order — ported from `poc/poc2_extract.py:89-94` unchanged."""
    lines = []
    for q in REGISTRY.all(kind):
        flag = " [multiple answers allowed]" if q.multi else ""
        lines.append(f"- {q.id}: {q.question}{flag}")
    return "\n".join(lines)


def extract_prompt_batched(
    kind: str, entity_name: str, sources: list[PromptSource],
) -> tuple[str, str]:
    """The batched `[S1]…[Sn]` extraction call (`03-worker.md` §8). One call
    over every given source at once, so reconciliation ("sources disagree ->
    write the disagreement") can see both sides without a second synthesis
    call.

    `sources` carries its own `label` per `extract_types.py`'s frozen
    contract — this function renders the labels it is given, it does not
    invent them (that ordering is E3's job, upstream of this one).
    """
    if kind not in ("problem", "actor"):
        raise ValueError(f"kind must be 'problem' or 'actor', got {kind!r}")
    base = _PROBLEM_SYSTEM if kind == "problem" else _ACTOR_SYSTEM
    system = (
        base + "\n\n"
        "SEVERAL SOURCES ARE GIVEN AT ONCE, each opening with a marker line "
        "`[Sn] <url>`. Three additional rules follow from that:\n\n"
        "1. Answer the numbered questions below. Every answer carries the "
        "`question_id` it answers and the `source_id` (`S1`, `S2`, …) of the "
        "source it came from. An answer with no source id, or an id not in "
        "the list given, is DROPPED — never guess an id, and never merge two "
        "sources into one answer.\n"
        "2. If two sources disagree — a different figure, date, or status for "
        "the same thing — write the disagreement as the answer, naming both "
        "sides and both source ids. Do not silently pick one.\n"
        "3. A question no source answers is simply absent from `answers`.\n\n"
        "QUESTIONS:\n" + _question_block(kind) + "\n\n"
        "Respond with strict JSON only, no prose, no markdown fences:\n"
        '{"answers": [{"question_id": "...", "source_id": "S2", '
        '"answer": "...", "confidence": 0.0}],\n'
        ' "claims":  [{"field": "...", "value": "...", "confidence": 0.0}],\n'
        ' "emits":   [{"kind": "problem"|"actor", "name": "...", '
        '"hint": "...", "signals": {}}],\n'
        ' "edges":   [{"dst_name": "...", "dst_kind": "...", '
        '"edge_kind": "...", "relevance": 0, "stance": null, '
        '"evidence": "..."}]}'
    )
    blocks = [f"[{s.label}] {s.url}\n{s.text}" for s in sources]
    prompt = (f"Entity name: {entity_name}\n\n"
              "Sources:\n\n" + "\n\n---\n\n".join(blocks))
    return system, prompt


def parse_answers(
    result_json, sources: list[PromptSource],
) -> tuple[list[Answer], list[str]]:
    """Resolve the model's prompt-local `source_id` (`S1`, `S2`, …) back to
    the durable `source_id` on `PromptSource`, and drop — never guess — any
    answer whose label isn't in the map (`03-worker.md` §8/§13, "an answer
    with no source id, or an id not in the list given, is DROPPED"). PoC-2
    measured 0 occurrences of this at n=95 (`poc/poc2-results.md` Q2), but the
    guard is mandatory regardless.

    `result_json` is the already-parsed response body (a dict), not raw text
    — a malformed JSON string is this function's caller's problem
    (`llm.parse_json`), not this one's. Returns `(answers, problems)`, where
    `problems` is human-readable strings for every dropped or malformed
    answer, suitable for a log line.
    """
    problems: list[str] = []
    answers: list[Answer] = []

    if not isinstance(result_json, dict):
        problems.append(
            f"result is not a JSON object (got {type(result_json).__name__})")
        return answers, problems

    by_label = {s.label: s for s in sources}
    raw_answers = result_json.get("answers")
    if not isinstance(raw_answers, list):
        problems.append("'answers' is missing or not a list")
        return answers, problems

    for i, a in enumerate(raw_answers):
        if not isinstance(a, dict):
            problems.append(f"answers[{i}]: not an object — dropped")
            continue

        question_id = a.get("question_id")
        if not isinstance(question_id, str) or not question_id.strip():
            problems.append(f"answers[{i}]: missing question_id — dropped")
            continue

        raw_sid = a.get("source_id")
        label = str(raw_sid).strip().strip("[]") if raw_sid else ""
        if not label:
            problems.append(
                f"answers[{i}] ({question_id}): no source_id — dropped, "
                f"never guessed")
            continue
        source = by_label.get(label)
        if source is None:
            problems.append(
                f"answers[{i}] ({question_id}): unknown source_id "
                f"{raw_sid!r} — dropped, never guessed")
            continue

        answer_text = a.get("answer")
        if not isinstance(answer_text, str) or not answer_text.strip():
            problems.append(
                f"answers[{i}] ({question_id}): missing/empty answer text "
                f"— dropped")
            continue

        confidence = a.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                problems.append(
                    f"answers[{i}] ({question_id}): non-numeric confidence "
                    f"{confidence!r} — ignored, answer kept")
                confidence = None
            else:
                # 0-1 is not a threshold invented here: it is
                # `store/schema.sql`'s own CHECK on `finding.confidence`. A
                # model that answers `95` would otherwise raise
                # sqlite3.IntegrityError out of `extract.write_findings` and
                # abort the whole batch — every remaining candidate included
                # — where the rest of this parser drops the bad field and
                # keeps going.
                if not 0.0 <= confidence <= 1.0:
                    problems.append(
                        f"answers[{i}] ({question_id}): confidence "
                        f"{confidence!r} outside 0-1 — ignored, answer kept")
                    confidence = None

        # A block can hold >1 chunk (multiple passages selected from the same
        # source); the model doesn't say which one it read, so the chunk_ref
        # is only narrowed when the source's block was exactly one chunk
        # (`extract_types.py`'s `Answer.chunk_ref` docstring).
        chunk_ref = (source.chunk_refs[0]
                     if len(source.chunk_refs) == 1 else None)

        answers.append(Answer(
            question_id=question_id,
            answer=answer_text,
            source_id=source.source_id,
            confidence=confidence,
            chunk_ref=chunk_ref,
        ))

    return answers, problems


def retry_per_source(
    kind: str, entity_name: str, sources: list[PromptSource],
) -> list[tuple[PromptSource, str, str]]:
    """§13's per-source fallback: "Extraction JSON malformed -> Retry once
    per source separately; then write nothing and log." PoC-2 measured this
    path (there, a retry of the whole batched call rather than the
    decomposed per-source form specced here) rescuing the one malformed
    response observed, 1/1 (`poc/poc2-results.md` Q1).

    Takes the sources whose batched answer failed to parse and returns one
    single-source `(source, system, prompt)` triple per source — each built
    by `extract_prompt_batched` on a singleton list, so a source that was
    `S3` in the failed batch is relabelled `S1` alone in its own retry
    (`extract_prompt_batched` renders whatever label it is given; a
    singleton list always gets a fresh one here, since the caller is
    building a new, independent call per source, not replaying the old
    batch's labels).
    """
    out: list[tuple[PromptSource, str, str]] = []
    for s in sources:
        solo = PromptSource(source_id=s.source_id, label="S1", url=s.url,
                            text=s.text, chunk_refs=s.chunk_refs)
        system, prompt = extract_prompt_batched(kind, entity_name, [solo])
        out.append((s, system, prompt))
    return out
