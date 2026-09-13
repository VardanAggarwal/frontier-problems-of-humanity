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
