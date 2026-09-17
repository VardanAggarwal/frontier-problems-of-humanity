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
import re

from worker.extract_types import Answer, PromptSource
from worker.questions import REGISTRY
from store.tags import REGISTRY as TAG_REGISTRY

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


# Split 2026-09-14. This used to be one constant carrying BOTH the shared
# prose and a full JSON schema block, and every prompt built on it appended a
# schema of its own — so the batched and verify prompts each showed the model
# two schemas. That was survivable while the two agreed; it stopped being
# survivable when `claims` left the batched schema, because the base was
# still asking for a key the batched schema had dropped. The prose is shared;
# the schema belongs to whichever prompt is being built.
_EXTRACT_COMMON_PROSE = (
    "Extract structured claims from the text below about the named entity. "
    "Never write prose summaries as a claim value — a claim is one field, "
    "one short value, one confidence in [0, 1]. If the text does not "
    "support a field, omit it; do not guess.\n\n"
    "Also list `emits`: EVERY other organisation or named individual "
    "mentioned in the text who looks worth a candidate record of their own "
    "(co-petitioners, funders, grantees, officials, affected-led leaders "
    "spoken for by an NGO, coalition partners, etc) — AND every distinct "
    "documented failure or need the text describes, separate from the "
    "entity itself, that isn't already the entity being profiled (kind: "
    "\"problem\"). Do not rely on `edges` alone to carry a problem mention: "
    "list it here too, the same as you would a co-mentioned actor. And list "
    "`edges`: typed "
    "relations this text evidences between the entity and another named "
    "actor or problem, with `edge_kind` one of: part_of, member_of, "
    "works_on, cites, funds, board, cohort, convenes, portfolio, "
    "affiliated, parent_org, superseded_by. `relevance` on a `works_on` "
    "edge is 0 (mentioned) / 1 (adjacent) / 2 (works it) / 3 "
    "(load-bearing) — omit if the text does not support a judgment.\n\n"
    "When answering p19_who_working / a `works_on` edge, consider all four "
    "response legs — activism, institution, enterprise (market-payer only), "
    "service (donor-funded, no earned revenue) — separately. If the given "
    "text plainly supports actors on some legs and is simply silent on "
    "others, only answer for the legs it supports; do not guess an actor "
    "into an unsupported leg to fill it in.\n\n"
)

# The single-source schema. `extract_prompt` is the ONLY caller: that path has
# no findings ledger, so `claims` there is the model's own list and is the
# only claim source (`worker.py`, the non-batched branch). The batched and
# verify prompts derive claims from findings and carry their own schemas.
_EXTRACT_SCHEMA_SINGLE = (
    "Respond with strict JSON only, no prose, no markdown fences:\n"
    '{"claims": [{"field": "...", "value": "...", "confidence": 0.0}, ...],\n'
    ' "emits":  [{"kind": "problem"|"actor", "name": "...", "hint": "..."}],\n'
    ' "edges":  [{"dst_name": "...", "dst_kind": "problem"|"actor", '
    '"edge_kind": "...", "relevance": 0|1|2|3|null, "evidence": "..."}]}'
)

_EXTRACT_COMMON = _EXTRACT_COMMON_PROSE + _EXTRACT_SCHEMA_SINGLE

_PROBLEM_ROLE = (
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
    "tree, not from source text.\n\n"
)

_PROBLEM_SYSTEM = _PROBLEM_ROLE + _EXTRACT_COMMON
_PROBLEM_SYSTEM_BASE = _PROBLEM_ROLE + _EXTRACT_COMMON_PROSE

_ACTOR_ROLE = (
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
    "the URL or handle, e.g. `channel:twitter`).\n\n"
)

_ACTOR_SYSTEM = _ACTOR_ROLE + _EXTRACT_COMMON
_ACTOR_SYSTEM_BASE = _ACTOR_ROLE + _EXTRACT_COMMON_PROSE


def extract_prompt(kind: str, entity_name: str, text: str) -> tuple[str, str]:
    """Claims extraction — the paid tier-4 call (§7), one per surviving
    candidate. `kind` is "problem" or "actor"; this is the literal "two
    prompts" of §4 — one shared function, a kind-conditioned system prompt.

    2026-09-15: the instruction used to invite the model to "extract what
    you can from the name alone" when `text` is empty — which let a
    substantive claim like `one_line` (CLAUDE.md's own browse-card
    definition field) get fabricated from nothing but the entity's name,
    with no fetched content behind it. `_EXTRACT_COMMON_PROSE`'s "if the
    text does not support a field, omit it; do not guess" already forbade
    this in spirit; a bare registry row just made it look licensed. Fixed:
    an empty `text` now gets an explicit instruction to return empty
    `claims`/`emits`/`edges` rather than reach for the name.
    """
    if kind not in ("problem", "actor"):
        raise ValueError(f"kind must be 'problem' or 'actor', got {kind!r}")
    system = _PROBLEM_SYSTEM if kind == "problem" else _ACTOR_SYSTEM
    if text.strip():
        body = f"Source text:\n\n{text}"
    else:
        body = (
            "Source text: (empty — a bare registry row with no document "
            "fetched yet is legitimate.) Do not invent a `one_line` or any "
            "other claim from the entity name alone — a name is not "
            "content. Return empty `claims`, `emits` and `edges` lists.")
    prompt = f"Entity name: {entity_name}\n\n{body}"
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

CHUNK_MARK = "\u27e8{label}.{k}\u27e9"      # ⟨S2.3⟩ — prompt-local, like the label


def render_block(source) -> str:
    """One `[Sn] <url>` block with every chunk inside it marked `⟨Sn.k⟩`.

    `k` is 1-based position within the block, so `⟨S2.3⟩` is
    `source.chunk_refs[2]` — the parser resolves it, nothing downstream ever
    sees the marker form (`extract_types.py`'s frozen contract).

    Why mark at all: `finding.chunk_ref` (03-worker.md §9, "audit a wrong
    answer back to the passage") could only ever be filled when a block held
    exactly ONE chunk, and measured across the five PoC fixtures at radius 1
    that never happens — 0 of 16 blocks, min 2 chunks, median ~11. The
    column, its migration and its frozen `source_id:ordinal` format all
    shipped; the prompt was the missing half.

    A source with no `chunk_texts` (the verify pass, `retry_per_source`, any
    caller holding only joined `text`) renders unmarked — the marker is an
    aid, and an answer with no resolvable marker keeps `chunk_ref=None`,
    which is the column's existing contract.
    """
    if not getattr(source, "chunk_texts", ()):
        return f"[{source.label}] {source.url}\n{source.text}"
    parts = [f"{CHUNK_MARK.format(label=source.label, k=k)} {t}"
             for k, t in enumerate(source.chunk_texts, start=1)]
    return f"[{source.label}] {source.url}\n" + "\n\n".join(parts)


def _question_block(kind: str) -> str:
    """One `- <id>: <question>` line per question of `kind`, in registry
    order — ported from `poc/poc2_extract.py:89-94` unchanged, extended
    2026-09-14.

    A `tag:<ns>` question whose namespace is CLOSED (`store/tags.py`'s
    `open=False`) now has its exact allowed values spelled out inline, plus
    an explicit output-format instruction for `multi` fields. Before this,
    the model saw only the English question text and a bare "[multiple
    answers allowed]" flag with no format spec — measured live on the
    silicosis leaf: `agent` came back as the literal substance
    (`"silica dust"`) instead of the category (`industrial-exposure`), and
    `mechanism`/`gap_missing_leg` came back as a comma-joined string and a
    JSON-list-shaped *string* respectively, neither of which matched
    `store/tags.py`'s closed enum or a parseable multi-value shape — all
    four got rejected at the `tag_validate_ins` trigger and silently
    dropped. Options are pulled from `store/tags.py`'s REGISTRY (the same
    source `questions.py` validates `claim_field` against at load time), not
    retyped here, so the two can't drift."""
    lines = []
    for q in REGISTRY.all(kind):
        flag = " [multiple answers allowed]" if q.multi else ""
        ns = q.claim_field[len("tag:"):] if q.claim_field.startswith("tag:") else None
        options_note = ""
        if ns is not None:
            _applies_to, is_open, _required_when, values = TAG_REGISTRY[ns]
            if not is_open and values:
                options = ", ".join(values)
                if q.multi:
                    options_note = (
                        f" Answer as a JSON array using ONLY these values: "
                        f"[{options}]."
                        f" Also give a one-clause `reason`: why this value "
                        f"and not a neighbouring one.")
                else:
                    options_note = (
                        f" Answer with EXACTLY ONE of these values, verbatim "
                        f"— not a paraphrase or a literal example of it: "
                        f"{options}."
                        f" Also give a one-clause `reason`: why this value "
                        f"and not a neighbouring one.")
        lines.append(f"- {q.id}: {q.question}{flag}{options_note}")
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

    Rule 4 (`misidentified`, added 2026-09-14) is the cheap half of §6a's
    verify pass, pointed at the sources that DID clear gate 2. The band sweep
    found false positives above `CONFIRMED_ABOVE`: `jyoti.com` at 0.813 and
    `screener.in/company/JYOTICNC` at 0.804 against a person who writes about
    air pollution, `vnrvjietexams.net` at 0.818 against a farmers' union. The
    model is already reading the whole page to answer the questions; asking it
    to say so costs one schema key and no extra call. Parsed by
    `parse_misidentified`, which the caller applies to `answers`.
    """
    if kind not in ("problem", "actor"):
        raise ValueError(f"kind must be 'problem' or 'actor', got {kind!r}")
    base = _PROBLEM_SYSTEM_BASE if kind == "problem" else _ACTOR_SYSTEM_BASE
    system = (
        base +
        "SEVERAL SOURCES ARE GIVEN AT ONCE, each opening with a marker line "
        "`[Sn] <url>`. Five additional rules follow from that:\n\n"
        "1. Answer the numbered questions below. Every answer carries the "
        "`question_id` it answers and the `source_id` (`S1`, `S2`, …) of the "
        "source it came from. An answer with no source id, or an id not in "
        "the list given, is DROPPED — never guess an id, and never merge two "
        "sources into one answer.\n"
        "2. If two sources disagree — a different figure, date, or status for "
        "the same thing — write the disagreement as the answer, naming both "
        "sides and both source ids. Do not silently pick one.\n"
        "3. A question no source answers is simply absent from `answers`.\n"
        "4. These sources passed an automated identity check, but that check "
        "is a similarity score over each page's opening and it does get this "
        "wrong — most often on a DIFFERENT entity that shares the name (a "
        "company with the same word in its name, a person with the same given "
        "name). If a source is not about the named entity, list it in "
        "`misidentified` with what it is actually about, and do not answer "
        "from it. You are reading the whole page and the check was not; "
        "flagging one is expected, not a complaint.\n"
        "5. Inside each source, every chunk is marked `\u27e8Sn.k\u27e9`. Each "
        "answer also carries `chunk`: the marker of the ONE chunk you read "
        "it from, exactly as written (`\"S2.3\"`). If the answer rests on "
        "more than one chunk, give the marker of the chunk carrying the "
        "figure or the claim itself. If you cannot point to one, omit "
        "`chunk` — an absent marker is fine, a guessed one is not.\n"
        "6. For a closed-enum classification answer, also give `reason`: "
        "the one-clause justification for this value over a neighbouring "
        "one. Omit for non-classification answers.\n\n"
        "QUESTIONS:\n" + _question_block(kind) + "\n\n"
        "A `works_on` edge whose `dst_kind` is `problem` also carries "
        "`signals` — the four leafability signals for that problem, captured "
        "while you still have the page open so nothing has to refetch it "
        "later (`03-worker.md` \u00a710):\n"
        "  `harmed_population` — who is harmed, bounded and nameable\n"
        "  `magnitude`         — the figure, or the string `uncounted`\n"
        "  `agent`             — what triggers the harm\n"
        "  `actionable`        — what could be done, and by whom\n"
        "Use `null` for any the source does not support. `null` means "
        "the source was silent, NOT that the answer is no — and "
        "`uncounted` in `magnitude` is a real value, not a null: absence "
        "of measurement is a finding. Every other edge omits `signals`.\n\n"
        "Respond with strict JSON only, no prose, no markdown fences. If any "
        "string value (an `answer`, `evidence`, `about_what`, `why`, `hint`, "
        "`reason`) contains a double-quote character — a quoted figure or "
        "claim copied from the source — escape it as `\\\"` so the JSON "
        "stays valid; never emit an unescaped `\"` inside a string value:\n"
        '{"answers": [{"question_id": "...", "source_id": "S2", '
        '"chunk": "S2.3", "answer": "...", "confidence": 0.0, '
        '"reason": null}],\n'
        ' "misidentified": [{"source_id": "S3", "about_what": "...", '
        '"why": "..."}],\n'
        ' "emits":   [{"kind": "problem"|"actor", "name": "...", '
        '"hint": "..."}],\n'
        ' "edges":   [{"dst_name": "...", "dst_kind": "problem"|"actor", '
        '"edge_kind": "...", "relevance": 0|1|2|3|null, "stance": null, '
        '"evidence": "...", "signals": {"harmed_population": null, '
        '"magnitude": null, "agent": null, "actionable": null}}]}'
    )
    blocks = [render_block(s) for s in sources]
    prompt = (f"Entity name: {entity_name}\n\n"
              "Sources:\n\n" + "\n\n---\n\n".join(blocks))
    return system, prompt


_CHUNK_MARK_RE = re.compile(r"^[\s\u27e8\[]*([A-Za-z]+\d+)\.(\d+)[\s\u27e9\]]*$")


def resolve_chunk_marker(raw, source, question_id: str, i: int,
                         problems: list[str]) -> str | None:
    """`"S2.3"` -> `source.chunk_refs[2]`, or None.

    Same discipline as the source label above it: resolved, never guessed.
    A marker naming a DIFFERENT source than the answer's own `source_id` is
    refused rather than quietly trusted — that combination means the model
    lost track of which block it was reading, which is exactly the condition
    `chunk_ref` exists to let a reviewer detect. An absent marker is not a
    problem worth logging: rule 5 permits omitting it.
    """
    if raw is None or raw == "":
        return None
    m = _CHUNK_MARK_RE.match(str(raw).strip())
    if not m:
        problems.append(f"answers[{i}] ({question_id}): unparseable chunk "
                        f"marker {raw!r} — chunk_ref left null")
        return None
    label, k = m.group(1), int(m.group(2))
    if label != source.label:
        problems.append(f"answers[{i}] ({question_id}): chunk marker {raw!r} "
                        f"names {label}, answer names {source.label} — "
                        f"chunk_ref left null")
        return None
    if not 1 <= k <= len(source.chunk_refs):
        problems.append(f"answers[{i}] ({question_id}): chunk marker {raw!r} "
                        f"out of range (block holds "
                        f"{len(source.chunk_refs)}) — chunk_ref left null")
        return None
    return source.chunk_refs[k - 1]


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
        if isinstance(answer_text, list):
            # The prompt asks for these BOTH ways and the model is entitled to
            # either: `_ACTOR_SYSTEM` describes `legs`, `ecosystem_role` and
            # `geography` as "a JSON list from …", while the answers schema
            # shows `"answer": "..."`. Measured in PoC-2d: three of one call's
            # eleven answers arrived as lists and were dropped here as
            # "missing/empty", which they were not.
            #
            # Serialised rather than joined, because `worker._coerce_json_list`
            # already parses a JSON-encoded list back out for the list-valued
            # columns — so this round-trips to the right shape without
            # teaching the parser which columns those are (it cannot import
            # `worker` without a cycle).
            if not answer_text:
                problems.append(f"answers[{i}] ({question_id}): empty list "
                                f"answer — dropped")
                continue
            answer_text = json.dumps(answer_text, ensure_ascii=False)
            problems.append(f"answers[{i}] ({question_id}): list answer "
                            f"serialised to JSON — kept")
        if not isinstance(answer_text, str) or not answer_text.strip():
            problems.append(
                f"answers[{i}] ({question_id}): answer is "
                f"{type(a.get('answer')).__name__}, not text — dropped")
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

        # The model names the chunk it read (rule 5, added 2026-09-14). The
        # old rule here — narrow only when the block held exactly one chunk —
        # left this null on every finding ever written: 0 of 16 blocks across
        # the five PoC fixtures at radius 1 held one chunk. The one-chunk case
        # is kept as the fallback for a caller whose block carries no markers
        # (the verify pass, `retry_per_source`), where it is still correct.
        chunk_ref = resolve_chunk_marker(a.get("chunk"), source,
                                         question_id, i, problems)
        if chunk_ref is None and len(source.chunk_refs) == 1:
            chunk_ref = source.chunk_refs[0]

        reason = a.get("reason")
        if not isinstance(reason, str):
            reason = None

        answers.append(Answer(
            question_id=question_id,
            answer=answer_text,
            source_id=source.source_id,
            confidence=confidence,
            chunk_ref=chunk_ref,
            reason=reason,
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


# --------------------------------------------------------------------------
# The verify-and-extract pass (`03-worker.md` §6a) — the uncertain bucket.
# --------------------------------------------------------------------------
# Gate 2 is a 500-char cosine. `poc/gate2-band-sweep.md` showed where that is
# not enough: for `jyoti-pande-lavakare`, four wrong-entity pages sharing the
# given name — `jyoti.co.in`, `jyoti.com`, `jyotiindia.com` (a water heater
# manufacturer), `screener.in/company/JYOTICNC` — scored ABOVE her own
# LinkedIn post and her own book. No global threshold separates those, because
# the distinguishing evidence is not in the first 500 characters and is not a
# similarity judgment at all: it is "this page is about a company that makes
# water heaters, and the entity is a person who writes about air pollution".
#
# A model reading the page can make that judgment. So the uncertain bucket is
# not discarded and not waved through — it gets a call whose FIRST job is the
# identity decision, per source, and which may only extract from the sources
# it accepted. One call, because the reject decision and the extraction read
# the same text; splitting them doubles the token cost to ask one question.

_VERIFY_RULES = (
    "THESE SOURCES ARE UNVERIFIED. An automated identity check could not "
    "confirm they are about the named entity, and it could not rule them out "
    "either. Several are likely to be about a DIFFERENT entity that shares "
    "the name — a company with the same word in its name, a person with the "
    "same given name, an unrelated site the search engine ranked highly. "
    "Assume nothing.\n\n"
    "Work in two steps, in this order.\n\n"
    "STEP 1 — VERDICT PER SOURCE. For every `[Sn]` block, decide whether it "
    "is about the entity described above. Judge on what the page is actually "
    "about: its subject's line of work, sector, location, and the kind of "
    "thing it is. A name match is NOT sufficient evidence — it is the reason "
    "this source is in front of you, not a reason to accept it. Give each "
    "source exactly one verdict:\n"
    "  `about`     — the page is about this entity. Say what convinced you.\n"
    "  `different` — the page is about a DIFFERENT entity with a similar or "
    "identical name. Say what the page is actually about.\n"
    "  `unrelated` — the page is not about any entity of this name (a "
    "product listing, a help page, a converter, an index with no content).\n"
    "  `insufficient` — too little text to tell. Not a polite `about`.\n\n"
    "STEP 2 — EXTRACT, FROM `about` SOURCES ONLY. Answer the questions using "
    "only sources you marked `about`. An answer citing a source you marked "
    "`different`, `unrelated` or `insufficient` is a contradiction and will "
    "be dropped. If you marked no source `about`, return an empty `answers` "
    "list — that is a correct and useful outcome, not a failure.\n\n"
    "A page being interesting is not a reason to accept it. A page about a "
    "different entity with the same name is the single most likely thing you "
    "are looking at, and marking it `different` is the most valuable thing "
    "you can do here.\n\n"
)


def verify_and_extract_prompt_batched(
    kind: str, entity_name: str, entity_context: str,
    sources: list[PromptSource],
) -> tuple[str, str]:
    """The second pass over the `uncertain`/thin bucket: identity verdict per
    source, then extraction restricted to the sources it accepted.

    Differs from `extract_prompt_batched` in three ways, all deliberate:

    1. It is given `entity_context` — the candidate's own description — and
       the main prompt is not. The sweep found context is what separates a
       name collision from the real entity (adding it moved `jyoti.co.in`
       -0.034 and a genuine page +0.10). A verdict asked without it is being
       asked in the regime where the signal inverts.
    2. It demands a verdict for EVERY source before any extraction, so a
       source cannot contribute silently.
    3. It states outright that a name match is not evidence. That is the
       specific error this pass exists to catch.

    Returns `(system, prompt)` like its sibling. Parsing is
    `parse_verified_answers`, which enforces rule 2 rather than trusting it.
    """
    if kind not in ("problem", "actor"):
        raise ValueError(f"kind must be 'problem' or 'actor', got {kind!r}")
    base = _PROBLEM_SYSTEM_BASE if kind == "problem" else _ACTOR_SYSTEM_BASE
    system = (
        base + _VERIFY_RULES +
        "Each answer carries the `question_id` it answers and the "
        "`source_id` (`S1`, `S2`, …) it came from. Never guess an id, never "
        "merge two sources into one answer. If two accepted sources disagree, "
        "write the disagreement as the answer, naming both sides and both "
        "ids. A question no accepted source answers is absent from "
        "`answers`. For a closed-enum classification answer, also give "
        "`reason`: the one-clause justification for this value over a "
        "neighbouring one. Omit for non-classification answers.\n\n"
        "QUESTIONS:\n" + _question_block(kind) + "\n\n"
        "Respond with strict JSON only, no prose, no markdown fences:\n"
        '{"verdicts": [{"source_id": "S1", "verdict": "about"|"different"'
        '|"unrelated"|"insufficient", "about_what": "...", "why": "..."}],\n'
        ' "answers": [{"question_id": "...", "source_id": "S2", '
        '"chunk": "S2.3", "answer": "...", "confidence": 0.0, '
        '"reason": null}],\n'
        ' "emits":   [{"kind": "problem"|"actor", "name": "...", '
        '"hint": "..."}],\n'
        ' "edges":   [{"dst_name": "...", "dst_kind": "problem"|"actor", '
        '"edge_kind": "...", "relevance": 0|1|2|3|null, "stance": null, '
        '"evidence": "...", "signals": {"harmed_population": null, '
        '"magnitude": null, "agent": null, "actionable": null}}]}\n\n'
        "`verdicts` must carry exactly one entry per source given. "
        "`about_what` is required on `different` and `unrelated` — it is how "
        "a reviewer checks your reasoning without refetching the page."
    )
    blocks = [render_block(s) for s in sources]
    prompt = (f"Entity name: {entity_name}\n"
              f"Entity description: {entity_context or '(none given)'}\n\n"
              "Unverified sources:\n\n" + "\n\n---\n\n".join(blocks))
    return system, prompt


# Verdict vocabulary for the verify pass. `about` is the only one that lets a
# source contribute; the other three are all reasons it may not, kept distinct
# because they mean different things to a reviewer and to the drop ledger.
V_ABOUT = "about"
V_DIFFERENT = "different"
V_UNRELATED = "unrelated"
V_INSUFFICIENT = "insufficient"
VERIFY_VERDICTS = (V_ABOUT, V_DIFFERENT, V_UNRELATED, V_INSUFFICIENT)


def parse_verified_answers(
    result_json, sources: list[PromptSource],
) -> tuple[list[Answer], dict[str, dict], list[str]]:
    """Parse a `verify_and_extract_prompt_batched` response.

    Returns `(answers, verdicts_by_source_id, problems)`.

    The prompt tells the model it may only answer from sources it marked
    `about`. This function does not trust that. It parses the verdicts first,
    then drops any answer citing a source that was not marked `about` —
    including a source the model gave no verdict for at all, which is the
    quiet way the rule gets broken. `problems` records every drop, so a model
    that systematically ignores the rule shows up as a run of log lines rather
    than as silently-admitted junk.

    A source with no verdict is treated as NOT `about`. That direction is
    deliberate: the whole bucket arrived here because an automated check could
    not confirm it, so silence is not consent.
    """
    problems: list[str] = []
    verdicts: dict[str, dict] = {}

    if not isinstance(result_json, dict):
        return [], {}, [f"result is not a JSON object "
                        f"(got {type(result_json).__name__})"]

    by_label = {s.label: s for s in sources}
    raw_verdicts = result_json.get("verdicts")
    if not isinstance(raw_verdicts, list):
        problems.append("'verdicts' is missing or not a list — no source can "
                        "be accepted, every answer will be dropped")
        raw_verdicts = []

    for i, v in enumerate(raw_verdicts):
        if not isinstance(v, dict):
            problems.append(f"verdicts[{i}]: not an object — ignored")
            continue
        label = str(v.get("source_id") or "").strip().strip("[]")
        source = by_label.get(label)
        if source is None:
            problems.append(
                f"verdicts[{i}]: unknown source_id {v.get('source_id')!r} "
                f"— ignored, never guessed")
            continue
        verdict = str(v.get("verdict") or "").strip().lower()
        if verdict not in VERIFY_VERDICTS:
            problems.append(
                f"verdicts[{i}] ({label}): unknown verdict "
                f"{v.get('verdict')!r} — treated as not-about")
            verdict = V_INSUFFICIENT
        if verdict in (V_DIFFERENT, V_UNRELATED) and not str(
                v.get("about_what") or "").strip():
            problems.append(
                f"verdicts[{i}] ({label}): {verdict} with no `about_what` "
                f"— verdict kept, but the reasoning is unreviewable")
        verdicts[source.source_id] = {
            "label": label, "url": source.url, "verdict": verdict,
            "about_what": str(v.get("about_what") or ""),
            "why": str(v.get("why") or ""),
        }

    missing = [s.label for s in sources if s.source_id not in verdicts]
    if missing:
        problems.append(
            f"no verdict returned for {missing} — treated as not-about, so "
            f"nothing may be extracted from them (silence is not consent)")

    accepted = {sid for sid, v in verdicts.items()
                if v["verdict"] == V_ABOUT}
    answers, answer_problems = parse_answers(result_json, sources)
    problems.extend(answer_problems)

    kept: list[Answer] = []
    for a in answers:
        if a.source_id in accepted:
            kept.append(a)
            continue
        verdict = verdicts.get(a.source_id, {}).get("verdict", "no verdict")
        problems.append(
            f"answer to {a.question_id} cites source {a.source_id} marked "
            f"{verdict!r}, not 'about' — dropped, the model contradicted its "
            f"own verdict")
    return kept, verdicts, problems


def parse_misidentified(
    result_json, sources: list[PromptSource],
) -> tuple[dict[str, dict], list[str]]:
    """Parse the batched prompt's `misidentified` list (rule 4).

    -> `(flagged_by_source_id, problems)`. Returns an empty dict when the key
    is absent, which is the normal case and not a problem: rule 4 asks the
    model to speak up only when something is wrong.

    Deliberately asymmetric with `parse_verified_answers`. There, a source is
    guilty until proven `about`, because the whole bucket arrived unconfirmed.
    Here the sources cleared gate 2, so the default is innocent and the flag
    is an exception the model has to actively raise. A missing key means "no
    objection", never "no verdict".

    An unknown `source_id` is ignored with a note rather than guessed at, the
    same rule as everywhere else in this module.
    """
    problems: list[str] = []
    flagged: dict[str, dict] = {}
    if not isinstance(result_json, dict):
        return flagged, problems

    raw = result_json.get("misidentified")
    if raw is None:
        return flagged, problems
    if not isinstance(raw, list):
        problems.append("'misidentified' is present but not a list — ignored")
        return flagged, problems

    by_label = {s.label: s for s in sources}
    for i, m in enumerate(raw):
        if not isinstance(m, dict):
            problems.append(f"misidentified[{i}]: not an object — ignored")
            continue
        label = str(m.get("source_id") or "").strip().strip("[]")
        source = by_label.get(label)
        if source is None:
            problems.append(
                f"misidentified[{i}]: unknown source_id "
                f"{m.get('source_id')!r} — ignored, never guessed")
            continue
        about_what = str(m.get("about_what") or "").strip()
        if not about_what:
            problems.append(
                f"misidentified[{i}] ({label}): flagged with no `about_what` "
                f"— flag kept, but the reasoning is unreviewable")
        flagged[source.source_id] = {
            "label": label, "url": source.url,
            "about_what": about_what, "why": str(m.get("why") or ""),
        }
    return flagged, problems


def drop_misidentified(
    answers: list[Answer], flagged: dict[str, dict],
) -> tuple[list[Answer], list[str]]:
    """Remove answers citing a source the model itself flagged, and say so.

    Rule 4 tells the model not to answer from a source it flags. This applies
    that rather than trusting it, for the same reason `parse_verified_answers`
    does: an instruction the parser does not enforce is an instruction that
    holds until the day it doesn't, silently.

    The answers are dropped from the ledger; nothing about the source is
    deleted. The flag, its `about_what`, the url and the page text all remain
    — this removes a claim the model retracted, not the record of the source.
    """
    if not flagged:
        return answers, []
    kept, problems = [], []
    for a in answers:
        if a.source_id not in flagged:
            kept.append(a)
            continue
        f = flagged[a.source_id]
        problems.append(
            f"answer to {a.question_id} cites {f['label']}, which the model "
            f"flagged as misidentified"
            + (f" (actually about: {f['about_what']})" if f["about_what"] else "")
            + " — dropped")
    return kept, problems
