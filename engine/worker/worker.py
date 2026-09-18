"""The worker loop (01-minimal.md §4 "worker: gate -> fetch -> gate -> claims
-> resolve -> write -> emit (N parallel)", §5, build order step 3).

`run_batch` takes candidates the caller has already selected and admitted
(selection / admission control / scheduling is step 5, explicitly out of
scope here — §9's budget ledger and cursor advance do not exist yet) and
carries each one through the four gates to a write or an escalation. The CLI
`main()` stands in for the not-yet-built scheduler with the simplest
"already admitted, not yet processed" query that makes sense today.

Step `emit` never recurses into processing what it writes (§5: "That is what
keeps depth a budget question rather than a recursion constant") — new
candidate rows land in the table and the function returns.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import traceback
from pathlib import Path

from embed.guard import add_store_args, open_store
from store import db
from text.preview import Preview, fetch_list, group

from search import confirm_policy
from search.confirm_policy import prompt_set_is_thin
from search.provider import SearxngProvider, ThrottledProvider

from . import config
from . import depth as depth_mod
from . import extract as extract_mod
from . import fetch as fetchmod
from . import gate1, gate2, llm, problem_emit, resolve, search_stage
from .extract_types import Answer, ConfirmedSource, PromptSource
from .prompts import (drop_misidentified, extract_prompt,
                      extract_prompt_batched, parse_answers,
                      parse_misidentified, parse_verified_answers,
                      retry_per_source, verify_and_extract_prompt_batched)
from .questions import REGISTRY

# Track B (`04-worker-build-plan.md` §4): predict a depth tier for every
# actor mention at mint time, and apply the post-extraction ground-test
# verdict when writing claims. No call site exists yet to feed a live
# candidate's stored prediction back into `_write_entity` (that plumbing
# runs through `run_batch`, frozen for this track) — see `_write_entity`'s
# `predicted_depth` kwarg — which E6 now plumbs from the candidate's stored
# intake prediction. Degrades to: every actor keeps whatever `depth` the
# model itself claimed (today's behaviour) whenever the three ground-test
# inputs are absent or the `depth_tier` parameter is False.
#
# E6 converted this from a switch into a DEFAULT. `run_batch`,
# `_write_entity` and `_emit` each take `depth_tier` as a call-site
# parameter; the env var only supplies the value when a caller passes None.
# Pipeline behaviour toggled by process environment was a workaround for
# `run_batch` being frozen for tracks A-D (`04-worker-build-plan.md` §6),
# and E6 is where that freeze lifts.
_DEPTH_TIER_DEFAULT = os.getenv("WORKER_DEPTH_TIER", "1") != "0"

# Track A (`04-worker-build-plan.md` §4): an unresolvable `works_on` problem
# edge now mints a problem candidate instead of being dropped (see
# `_mint_or_resolve_problem`). Per §4's "land the fallback before
# the code that degrades to it": `problem_emission=False` reverts `_emit` to
# today's behaviour (unresolvable problem edge silently dropped) with no
# code change. Like `depth_tier`, E6 turned this from an env-var switch into
# a call-site parameter whose default the env var supplies.
_PROBLEM_EMISSION_DEFAULT = os.getenv("WORKER_PROBLEM_EMISSION", "1") != "0"

# Columns claims may write directly (db.py's _JSON_COLUMNS mirrors these for
# problem/actor). Anything else in a claim's `field` must be a `tag:` /
# `ask:` / `channel:` convention (prompts.py docstring) or it is logged and
# dropped rather than crashing the batch.
_COLUMNS = {
    "problem": {"title", "one_line", "status", "geography", "needs_legs",
                "gap_note", "doc", "updated"},
    # `one_line`, `funding` and `scale_metric` were missing here while the
    # `actor` table carried all three and `questions.yaml` asked for each
    # (`q1_one_line`, `q10_funding`, `q11_scale_metric`) — so those claims
    # were extracted, logged and dropped. Found by E4 while deriving claims
    # from findings; fixed here, in E6, because this is E6's file.
    "actor": {"title", "type", "one_line", "legs", "depth", "lifecycle",
              "lifecycle_as_of", "ecosystem_role", "affected_led",
              "representation_unit", "stance", "geography", "contact_route",
              "funding", "scale_metric", "followed", "followed_date",
              "last_checked", "doc", "updated"},
}
_JSON_LIST_COLUMNS = {
    "problem": {"geography", "needs_legs"},
    "actor": {"legs", "ecosystem_role", "geography"},
}

# Every CHECK-constrained enum column a claim might target. Validated here,
# before `db.put`, so a model-supplied value outside the set is a dropped
# claim with a log line — not an uncaught `sqlite3.IntegrityError` that kills
# `run_batch` mid-batch and, because the failing candidate never gets a
# `resolved_to`, permanently re-heads the CLI's `resolved_to IS NULL` queue on
# every future run (01-minimal.md §3: "rejected at the bad write, not at the
# next build"). Mirrors the CHECK clauses in schema.sql — keep them in sync.
_ENUMS = {
    ("problem", "status"): {"stub", "researched", "stale"},
    ("actor", "type"): {"org", "individual"},
    ("actor", "depth"): {"registry", "tracked", "excluded"},
    ("actor", "lifecycle"): {"operating", "scaling", "distressed", "dormant",
                             "acquired", "shut", "won-and-dissolved"},
    ("actor", "affected_led"): {"yes", "no", "partial"},
    ("actor", "representation_unit"): {
        "local-affected", "central-org", "enterprise",
        "central-at-named-legitimacy-cost"},
    ("actor", "stance"): {"works-the-remedy", "neutral",
                          "organised-against-remedy", "ambiguous"},
}


# Which `tag:<ns>` fields are `multi: true` — derived from `questions.yaml`
# via `REGISTRY`, not retyped, so this can't drift from the prompt's own
# "[multiple answers allowed]" flag (`prompts.py:_question_block`).
_TAG_MULTI = {q.claim_field[len("tag:"):]: q.multi
             for q in REGISTRY.all() if q.claim_field.startswith("tag:")}

# Near-miss synonyms for closed tag-namespace values — the model answers
# with a real, sensible word that just isn't the exact enum spelling
# (`store/tags.py`'s `satisfier_relation` wants the noun "absence", a model
# reliably says the adjective "absent"). Scoped per namespace: the same
# surface word can mean different things in different namespaces, so this is
# not a single flat map. Precedent: `_DST_KIND_SYNONYMS` above, for the same
# class of near-miss on `dst_kind`. Add an entry here only for a value seen
# rejected in practice — this is not a hedge against every possible synonym.
_TAG_VALUE_SYNONYMS = {
    "satisfier_relation": {"absent": "absence"},
}


def _normalise_tag_value(ns: str, value: str) -> str:
    return _TAG_VALUE_SYNONYMS.get(ns, {}).get(value, value)


def _split_multi_tag_value(value):
    """A `multi: true` tag answer may arrive as a native list, a JSON-list
    *string* (the prompt now asks for this shape explicitly —
    `prompts.py:_question_block`), or, from a model that ignores the format
    instruction, a bare comma-joined string. Only the last needs splitting on
    ',' — reuses `_coerce_json_list`'s list/JSON-string handling first so a
    value that already parses as a list isn't also comma-split (a value
    could legitimately contain a comma inside one item)."""
    coerced = _coerce_json_list(value)
    if len(coerced) == 1 and isinstance(coerced[0], str) and "," in coerced[0]:
        return [v.strip() for v in coerced[0].split(",") if v.strip()]
    return coerced


def _coerce_json_list(value):
    """A list-column claim may arrive as a native list, a bare string (one
    item), or — plausibly, given the extract prompts literally say 'a JSON
    list' — a JSON-encoded *string* of a list. Only the last case needs
    parsing; get it wrong and `db.put`'s `_encode` re-`json.dumps`s a string
    that already looks like a list, producing a double-encoded column with no
    error raised anywhere."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return [value]
    return [value]


# The model's own vocabulary for an actor, seen in PoC-2d: `org` and
# `individual` — which are `q2_type`'s values, not `dst_kind`'s. Both name an
# actor, and dropping them loses a real edge over a word. Normalised rather
# than accepted blindly: anything not in this map still fails the check below
# and is now logged instead of vanishing.
#
# The cause was a prompt regression, since fixed: splitting `_EXTRACT_COMMON`
# removed the batched schema's only statement of `"dst_kind": "problem"|
# "actor"`. 0 of 22 control-arm edges used a bad value against 3 of 28 live.
_DST_KIND_SYNONYMS = {
    "org": "actor", "organisation": "actor", "organization": "actor",
    "individual": "actor", "person": "actor", "people": "actor",
    "ngo": "actor", "company": "actor", "institution": "actor",
    "failure": "problem", "need": "problem", "issue": "problem",
}


def _normalise_dst_kind(raw):
    if not isinstance(raw, str):
        return raw
    v = raw.strip().lower()
    return v if v in ("problem", "actor") else _DST_KIND_SYNONYMS.get(v, raw)


def _split_claims(kind: str, claims: list[dict], *, log=print
                  ) -> tuple[dict, list[dict]]:
    """-> (column values to `put`, everything else) for one entity's claims.
    An enum column claim outside the schema's allowed set is dropped and
    logged here, before it ever reaches `db.put` (see `_ENUMS`)."""
    columns: dict = {}
    other: list[dict] = []
    known = _COLUMNS[kind]
    json_cols = _JSON_LIST_COLUMNS[kind]
    for c in claims:
        field, value = c.get("field", ""), c.get("value")
        if value is None or field == "":
            continue
        if field in known:
            if field in json_cols:
                value = _coerce_json_list(value)
            allowed = _ENUMS.get((kind, field))
            if allowed is not None and value not in allowed:
                log(f"worker: rejected {kind} claim {field}={value!r} — "
                    f"not one of {sorted(allowed)}")
                continue
            columns[field] = value
        else:
            other.append(c)
    return columns, other


def _apply_other_claims(conn: sqlite3.Connection, kind: str, entity_id: str,
                        other: list[dict], *, by: str, log=print) -> None:
    """`tag:` / `ask:` / `channel:` claims — the conventions documented in
    `prompts.py`. A claim matching none of them is logged and dropped: an
    autonomous writer must not crash a batch over one bad field name."""
    for c in other:
        field, value = c.get("field", ""), c["value"]
        if field.startswith("tag:"):
            ns = field.split(":", 1)[1]
            # `multi: true` questions (mechanism, gap_missing_leg, ...) can
            # come back as a native list, a JSON-list string, or a bare
            # comma-joined string — split before writing, one `db.tag()`
            # call per value, so one bad value in a multi-answer doesn't
            # sink the good ones alongside it (each call catches its own
            # IntegrityError). A non-multi field stays a single value, never
            # run through the splitter — its enum values may themselves
            # contain no comma but there is no reason to risk it.
            values = (_split_multi_tag_value(value) if _TAG_MULTI.get(ns)
                     else [value])
            for v in values:
                v = _normalise_tag_value(ns, str(v))
                try:
                    db.tag(conn, kind, entity_id, ns, v, by=by)
                except sqlite3.IntegrityError as e:
                    log(f"worker: rejected tag claim {field}={v!r} on "
                        f"{kind}/{entity_id}: {e}")
            continue
        if kind == "actor" and field.startswith("ask:"):
            parts = field.split(":", 2)
            if len(parts) == 3 and parts[1] in ("need", "offer"):
                conn.execute(
                    "INSERT INTO ask (actor_id, direction, kind, text) "
                    "VALUES (?, ?, ?, ?)", (entity_id, parts[1], parts[2], str(value)))
                # `ask` has no `put`/`tag`-style wrapper, so provenance would
                # otherwise be silently lost for exactly the data the
                # connect-pass depends on (CLAUDE.md "Actor tracking").
                db.record(conn, kind, entity_id, field, None, str(value), by=by)
                continue
        if kind == "actor" and field.startswith("channel:"):
            chan_kind = field.split(":", 1)[1]
            val = str(value)
            is_url = val.startswith(("http://", "https://"))
            url_val, handle_val = (val, None) if is_url else (None, val)
            # `UNIQUE(actor_id, kind, url, handle)` cannot dedupe a
            # handle-only channel via INSERT OR IGNORE: SQL's NULL is never
            # equal to NULL, so the unique index sees every handle-only row
            # as distinct and each re-run of the same claim reinserts the
            # same channel. `IS` is SQLite's NULL-safe equality — check by
            # hand instead of trusting the constraint.
            exists = conn.execute(
                "SELECT 1 FROM channel WHERE actor_id = ? AND kind = ? AND "
                "url IS ? AND handle IS ?",
                (entity_id, chan_kind, url_val, handle_val)).fetchone()
            if exists is None:
                conn.execute(
                    "INSERT INTO channel (actor_id, kind, url, handle) "
                    "VALUES (?, ?, ?, ?)", (entity_id, chan_kind, url_val, handle_val))
                db.record(conn, kind, entity_id, field, None, val, by=by)
            continue
        log(f"worker: unrecognised claim field {field!r} on {kind}/{entity_id}, skipped")


def _write_cites(conn: sqlite3.Connection, kind: str, entity_id: str,
                 answers: list, *, by: str, log=print) -> int:
    """One `cites` edge per distinct source behind this entity's answers.

    `migrate/from_corpus.py:cite` wrote these for hand-authored markdown
    `## Sources` lists; a worker-authored entity (doc: NULL) never went
    through that migration, so its `finding` rows (extract.write_findings)
    carried `source_id` durably but no `cites` edge ever got derived from
    them — `corpus.mjs`'s leaf/actor `sources:` (built from `edgesOut(...,
    'cites')`) was silently empty for every doc-less record. `answers`
    already carries the resolved `source_id` (extract_types.Answer); this
    just writes the edge `write_findings` stopped short of. -> edges written
    or updated (an IntegrityError on one bad source_id does not sink the
    rest, same discipline as the tag-claim loop above).
    """
    written = 0
    for source_id in dict.fromkeys(a.source_id for a in answers if a.source_id):
        try:
            db.link(conn, (kind, entity_id), "cites", ("source", source_id), by=by)
            written += 1
        except sqlite3.IntegrityError as e:
            log(f"worker: cites edge {kind}/{entity_id} -> source/{source_id} "
                f"rejected: {e}")
    return written


def _safe_put(conn: sqlite3.Connection, kind: str, row: dict, *, by: str,
             log=print) -> bool:
    """`db.put`, with a fallback to a minimal row on `IntegrityError`.

    `_ENUMS` catches every enum column this module knows about before it
    reaches SQL; this is the backstop for anything it doesn't (a NOT NULL a
    claim left unset, a future column this module hasn't been taught yet).
    Per 01-minimal.md §3, a bad write must be rejected at the write, not crash
    the batch — so on failure this drops back to the columns that cannot
    plausibly be wrong (`id`, `title`, and `type` for a new actor, since
    `actor.type` is NOT NULL with no default) rather than losing the whole
    candidate. -> True if anything was written, False if even the minimal row
    failed (which the caller must treat as "no entity exists")."""
    try:
        db.put(conn, kind, row, by=by)
        return True
    except sqlite3.IntegrityError as e:
        log(f"worker: put({kind}/{row.get('id')}) rejected ({e}) — "
            f"retrying with a minimal row")
        minimal = {"id": row["id"]}
        if "title" in row:
            minimal["title"] = row["title"]
        if kind == "actor":
            minimal["type"] = "org"
        try:
            db.put(conn, kind, minimal, by=by)
            return True
        except sqlite3.IntegrityError as e2:
            log(f"worker: minimal put({kind}/{row.get('id')}) still rejected "
                f"({e2}) — giving up on this entity")
            return False


def _write_entity(conn: sqlite3.Connection, corpus: Path, kind: str, name: str,
                  decision: resolve.ResolveResult, claims: list[dict], *,
                  by: str, log=print, predicted_depth: str | None = None,
                  depth_tier: bool | None = None) -> str | None:
    """Apply one candidate's claims per its resolution. -> the written/matched
    entity id, or None when nothing was written — either `ambiguous`
    (module docstring: escalation writes no graph rows) or a catastrophic
    write failure `_safe_put` could not recover from.

    `predicted_depth` (Track B, `03-worker.md` §2): the tier `depth.predict_
    tier` assigned this actor at intake, if the caller has it — `run_batch`
    does not yet plumb a candidate's stored prediction through to here (that
    would touch `run_batch`, frozen for this track), so it defaults to None
    and `needs_requeue` simply has nothing to compare against on that path.
    """
    columns, other = _split_claims(kind, claims, log=log)
    depth_tier = _DEPTH_TIER_DEFAULT if depth_tier is None else depth_tier

    if kind == "actor" and depth_tier and any(
            f in columns for f in ("affected_led", "representation_unit", "legs")):
        # The ground-test verdict (`03-worker.md` §2 / `CLAUDE.md` -> Actor
        # tracking), applied once the three inputs the model itself just
        # extracted are on hand. One-way: it can escalate a `registry`
        # claim (or no claim at all) to `tracked`, never the reverse — same
        # discipline as `needs_requeue`, and consistent with gate 1's
        # recall bias (never silently narrow who gets the fuller pass).
        verdict = depth_mod.verdict_tier(
            affected_led=columns.get("affected_led"),
            representation_unit=columns.get("representation_unit"),
            legs=columns.get("legs"))
        claimed_depth = columns.get("depth")
        if verdict == depth_mod.TRACKED_TIER and claimed_depth != depth_mod.TRACKED_TIER:
            log(f"worker: depth ground-test verdict escalates {name!r} to "
                f"tracked (model claimed {claimed_depth!r})")
            columns["depth"] = depth_mod.TRACKED_TIER
        if predicted_depth is not None and depth_mod.needs_requeue(predicted_depth, verdict):
            log(f"worker: {name!r} predicted 'registry' at intake but "
                f"verdicts 'tracked' post-extraction — requeue for a full pass")

    if decision.decision == "new":
        entity_id = resolve.new_id(conn, kind, name)
        base = {"id": entity_id, "title": name}
        if kind == "actor":
            base["type"] = "org"     # overridden below if a claim said individual
        base.update(columns)
        if not _safe_put(conn, kind, base, by=by, log=log):
            return None
        db.alias(conn, kind, entity_id, name, by=by)
    elif decision.decision in ("exact", "shortlist_top"):
        entity_id = decision.entity_id
        if decision.decision == "shortlist_top":
            # A shortlist hit paid for an encode + kNN to get here. Without
            # caching it as an alias, the same name variant pays that cost
            # again on every future mention instead of hitting the free
            # exact/alias path `resolve_entity` tries first.
            db.alias(conn, kind, entity_id, name, by=by)
        if columns and not _safe_put(conn, kind, {"id": entity_id, **columns},
                                     by=by, log=log):
            # The entity already exists — a rejected column update is not a
            # reason to treat it as unwritten; just skip the bad columns.
            pass
    else:  # ambiguous
        return None

    _apply_other_claims(conn, kind, entity_id, other, by=by, log=log)
    return entity_id


def _mint_or_resolve_problem(conn: sqlite3.Connection, source_candidate: sqlite3.Row,
                             edge: dict, *, log=print) -> tuple[str | None, bool]:
    """Track A: the destination of a `works_on` edge naming a problem that
    doesn't resolve via `db.resolve` (exact/alias) or this batch's own
    writes. -> (dst_id | None, minted). `minted=True` only when a fresh
    candidate row was inserted — the caller folds that into the same
    `emitted` counter the `emits` loop above already reports.

    Problem names are descriptions, not proper nouns (03-worker.md §10), so
    dedupe goes through `resolve.resolve_entity`'s embedding shortlist here
    rather than stopping at the exact-match miss that got us into this
    function. `resolve_entity`'s `corpus` parameter is unused by its current
    implementation (verified in `resolve.py`) — a placeholder is passed
    rather than threading a real corpus path through `_emit`, whose
    signature `run_batch` (frozen for this track) already calls with no such
    argument.
    """
    dst_name = edge.get("dst_name") or ""
    context = edge.get("evidence") or source_candidate["evidence"] or ""
    decision = resolve.resolve_entity(conn, Path("."), "problem", dst_name, context)
    action = problem_emit.decide_problem_edge(decision)

    if action == "resolve":
        if decision.decision == "shortlist_top":
            # Same caching argument as `_write_entity`'s shortlist_top case:
            # without this, the same problem-name variant pays for an
            # encode + kNN again on every future mention.
            db.alias(conn, "problem", decision.entity_id, dst_name,
                     by=f"worker:problem_emit:{source_candidate['id']}")
        return decision.entity_id, False

    if action == "escalate":
        # `resolve.py`'s own docstring: an ambiguous merge is an escalation,
        # never an autonomous merge or a new duplicate (the dedupe argument
        # this track exists to satisfy). Mint nothing, write no edge.
        db.record(conn, "candidate", str(source_candidate["id"]), "edge",
                 None, dst_name, by="worker:problem_emit", why=decision.reason)
        log(f"worker: problem edge to {dst_name!r} ambiguous "
            f"({decision.reason}) — routed to human review, edge dropped")
        return None, False

    # action == "new" — mint a problem candidate carrying the four gate
    # signals captured at extraction time (03-worker.md §10). Leafability is
    # the orchestrator's decision, not this worker's: signals are captured
    # and emitted, never gated here. Read off THIS edge: PoC-2d measured 31
    # emits across ten calls, every one of them `actor`, against 23 problems
    # named as `works_on` destinations. The prompt's own emits sentence asks
    # for "other organisations or named individuals" and its edges sentence
    # admits "actor or problem", so the model was doing as told. §10's JSON
    # block put `signals` on the emit; the prompt and this mint path both say
    # edge, and the prompt now asks there.
    signals = problem_emit.signals_from_edge(edge)
    conn.execute(
        "INSERT INTO candidate (kind, name, url, discovered_via, evidence) "
        "VALUES (?, ?, NULL, ?, ?)",
        ("problem", dst_name, f"worker:{source_candidate['id']}",
         json.dumps({"hint": edge.get("evidence", ""), "signals": signals,
                    "from_candidate": source_candidate["id"],
                    **_trigger_edge_fields(source_candidate, edge)})))
    return None, True


def _trigger_edge_fields(source_candidate: sqlite3.Row, edge: dict) -> dict:
    """The edge that couldn't be linked yet because its destination isn't an
    entity — captured on the destination candidate's own `evidence` so a
    later promotion (`_backfill_trigger_edge`) can finish the write.

    Safe to capture now, not just at promotion time, because `run_batch`
    already resolved and settled `source_candidate` (`_settle` runs before
    `_emit`) — `source_candidate['resolved_to']` is never NULL here. The
    only thing still pending is THIS candidate becoming an entity."""
    return {
        "from_kind": source_candidate["kind"],
        "from_id": source_candidate["resolved_to"],
        "edge_kind": edge.get("edge_kind"),
        "edge_relevance": edge.get("relevance"),
        "edge_evidence": edge.get("evidence"),
    }


def _mint_or_resolve_actor(conn: sqlite3.Connection, source_candidate: sqlite3.Row,
                           edge: dict, *, log=print,
                           depth_tier: bool | None = None) -> tuple[str | None, bool]:
    """Actor counterpart of `_mint_or_resolve_problem` — same three-way
    split (resolve / escalate / new), same reason this exists at all: an
    edge whose `dst_kind` is `actor` had no mint path of its own before this,
    so `works_on`-style edges naming an actor the `emits` loop hadn't
    already surfaced were dropped outright (`worker.py`'s `dst_id is None`
    fallthrough), not just left unresolved like problems were pre-Track-A.

    Actor names ARE proper nouns (unlike problem descriptions), but the
    exact/alias path already tried and missed by the time `_emit` calls
    this — `resolve_entity`'s embedding shortlist is still the right dedupe
    step before minting a duplicate stub."""
    dst_name = edge.get("dst_name") or ""
    context = edge.get("evidence") or source_candidate["evidence"] or ""
    decision = resolve.resolve_entity(conn, Path("."), "actor", dst_name, context)
    action = problem_emit.decide_problem_edge(decision)   # kind-agnostic despite the name

    if action == "resolve":
        if decision.decision == "shortlist_top":
            db.alias(conn, "actor", decision.entity_id, dst_name,
                     by=f"worker:problem_emit:{source_candidate['id']}")
        return decision.entity_id, False

    if action == "escalate":
        db.record(conn, "candidate", str(source_candidate["id"]), "edge",
                 None, dst_name, by="worker:problem_emit", why=decision.reason)
        log(f"worker: actor edge to {dst_name!r} ambiguous "
            f"({decision.reason}) — routed to human review, edge dropped")
        return None, False

    # action == "new"
    depth_tier = _DEPTH_TIER_DEFAULT if depth_tier is None else depth_tier
    payload = {"hint": edge.get("evidence", ""),
               "from_candidate": source_candidate["id"],
               **_trigger_edge_fields(source_candidate, edge)}
    if depth_tier:
        payload["predicted_depth"] = depth_mod.predict_tier(
            {"name": dst_name, "hint": edge.get("evidence", "")})
    conn.execute(
        "INSERT INTO candidate (kind, name, url, discovered_via, evidence) "
        "VALUES (?, ?, NULL, ?, ?)",
        ("actor", dst_name, f"worker:{source_candidate['id']}", json.dumps(payload)))
    return None, True


def _emit(conn: sqlite3.Connection, source_candidate: sqlite3.Row,
         claims: dict, resolved_this_batch: dict[tuple[str, str], str],
         *, log=print, depth_tier: bool | None = None,
         problem_emission: bool | None = None) -> tuple[int, int]:
    """Write `emits` as fresh, unprocessed candidates and `edges` as graph
    links where the destination already resolves — never both for the same
    name, and never a recursive call into `run_batch` (module docstring).

    `depth_tier` / `problem_emission`: None takes the module default, which
    the env var supplies (see their definitions above).

    Track A (+ actor counterpart): an edge naming a problem or actor that
    doesn't resolve is no longer just dropped — `_mint_or_resolve_problem` /
    `_mint_or_resolve_actor` either resolve it (existing/shortlist match),
    escalate it (ambiguous), or mint a fresh candidate here, carrying the
    dropped edge on its own evidence so `_backfill_trigger_edge` can write it
    once that candidate is promoted."""
    depth_tier = _DEPTH_TIER_DEFAULT if depth_tier is None else depth_tier
    problem_emission = (_PROBLEM_EMISSION_DEFAULT if problem_emission is None
                        else problem_emission)
    emitted = 0
    # Problem names minted by the emits loop in THIS call. The edges loop
    # below mints from a `works_on` destination, and a model that does what
    # the prompt asks — emit the problem, and link `works_on` to it — names
    # the same problem in both places. `db.resolve` can't see the difference:
    # a freshly minted candidate is not an entity yet, so the edge's lookup
    # misses and mints a second candidate with the same name. Latent before
    # 2026-09-14 (nothing encouraged a problem emit); asking for `signals`
    # on problem emits makes both halves the expected response.
    minted_problems: set[str] = set()
    # Same duplicate-mint guard as `minted_problems`, kept separate because
    # the edges loop below now has its own actor mint path
    # (`_mint_or_resolve_actor`) mirroring the problem one — without this
    # set, an actor named in both `emits` and `edges` in the same call would
    # mint twice.
    minted_actors: set[str] = set()
    for e in claims.get("emits", []) or []:
        ekind, ename = e.get("kind"), e.get("name")
        if ekind not in ("problem", "actor") or not ename:
            continue
        # A mention of an entity that already exists (on disk, or just
        # written earlier in this same batch) is not a new candidate — the
        # `edges` loop below already makes exactly this check for its
        # destinations; `emits` was missing it, which would otherwise spawn
        # an unconsolidated duplicate stub every time any candidate's text
        # so much as names an already-tracked actor.
        if db.resolve(conn, ekind, ename) is not None:
            continue
        if resolved_this_batch.get((ekind, db.norm(ename))) is not None:
            continue
        payload = {"hint": e.get("hint", ""), "from_candidate": source_candidate["id"]}
        if ekind == "problem":
            # Both mint routes write the key, so the orchestrator's payload
            # shape no longer depends on which one minted the candidate. Each
            # reads its OWN object — the edge route the edge, this one the
            # emit — rather than one looking the other up by name.
            payload["signals"] = problem_emit.signals_from_edge(e)
        if ekind == "actor" and depth_tier:
            # Track B: the intake-time prediction, stored now so a future
            # caller processing this candidate can compare it against the
            # post-extraction verdict (`depth.needs_requeue`) — nothing in
            # `run_batch` reads this back yet (frozen for this track); it's
            # captured here so that plumbing has data to read once it does.
            payload["predicted_depth"] = depth_mod.predict_tier(
                {"name": ename, "hint": e.get("hint", "")})
        conn.execute(
            "INSERT INTO candidate (kind, name, url, discovered_via, evidence) "
            "VALUES (?, ?, NULL, ?, ?)",
            (ekind, ename, f"worker:{source_candidate['id']}", json.dumps(payload)))
        if ekind == "problem":
            minted_problems.add(db.norm(ename))
        else:
            minted_actors.add(db.norm(ename))
        emitted += 1

    edges_written = 0
    for e in claims.get("edges", []) or []:
        dst_kind, dst_name = _normalise_dst_kind(e.get("dst_kind")), e.get("dst_name")
        edge_kind = e.get("edge_kind")
        if dst_kind not in ("problem", "actor") or not dst_name or not edge_kind:
            if dst_name and edge_kind:
                log(f"worker: edge to {dst_name!r} dropped — dst_kind "
                    f"{e.get('dst_kind')!r} is not problem/actor")
            continue
        dst_id = db.resolve(conn, dst_kind, dst_name)
        if dst_id is None:
            dst_id = resolved_this_batch.get((dst_kind, db.norm(dst_name)))
        minted_set = minted_problems if dst_kind == "problem" else minted_actors
        if (dst_id is None and problem_emission
                and db.norm(dst_name) in minted_set):
            # Already minted by the emits loop above (problem: with the
            # signals the prompt put there; actor: same as any other emit).
            # Minting again would duplicate the candidate and double-count
            # `emitted`; the edge still can't be linked (a candidate is not
            # an entity), which is the same deferral the `dst_id is None`
            # case below has always taken. The candidate's OWN evidence now
            # carries the triggering edge either way (`_trigger_edge_fields`
            # / the emits-loop payload), so nothing here needs to remember it.
            continue
        if dst_id is None and problem_emission:
            # Track A (problem) + its actor counterpart: a `works_on`-style
            # edge naming an actor/problem that the `emits` loop hasn't
            # already surfaced this call is minted here instead of dropped,
            # per `03-worker.md` §10. `_mint_or_resolve_actor` only exists
            # because this branch used to be problem-only — an actor named
            # solely in `edges` (never in `emits`) had no mint path at all.
            mint_fn = (_mint_or_resolve_problem if dst_kind == "problem"
                      else lambda *a, **kw: _mint_or_resolve_actor(
                          *a, depth_tier=depth_tier, **kw))
            dst_id, minted = mint_fn(conn, source_candidate, e, log=log)
            if minted:
                emitted += 1
        if dst_id is None:
            continue   # not yet an entity — the emits loop above, this
                       # candidate's own mint just above, or a prior
                       # candidate is responsible for it turning into one;
                       # an `ambiguous` match is escalated instead, per
                       # §10's dedupe rule. Its `from_kind`/`from_id`/
                       # `edge_kind` are on the minted candidate's own
                       # evidence, so `_backfill_trigger_edge` writes this
                       # edge once that candidate is promoted.
        try:
            db.link(conn, (source_candidate["kind"], source_candidate["resolved_to"]),
                    edge_kind, (dst_kind, dst_id), by=f"worker:{source_candidate['id']}",
                    relevance=e.get("relevance"), evidence=e.get("evidence"))
            edges_written += 1
        except sqlite3.IntegrityError as ex:
            log(f"worker: edge {edge_kind} -> {dst_id} rejected: {ex}")
    return emitted, edges_written


# `03-worker.md` §11b's high-value question set — magnitude, who-works-it,
# funding, affected-led — as ids. Counter 1 of §11c counts how many of these
# a candidate leaves UNFILLED — zero answers, `03-worker.md` §7's decided
# predicate (2026-09-14). §11c carried a warning that this counter could never
# read 0 because `p19_who_working` is `multi` and a `multi` question never
# closes; that warning is retired. §7 split `open` into `filled` and
# `saturated`, counter 1 reads the first, and zero-answers is well-defined for
# a `multi` question. The number is evidence about §11b from the next run on.
_HIGH_VALUE_QUESTIONS = ("p9_magnitude", "p19_who_working",
                         "q10_funding", "q6_affected_led")

# Counter 1 now asks the registry which questions are unfilled, so an id here
# that is not a real question would silently stop being counted — where the
# old membership test counted it as open. Check the four at import rather than
# finding a quietly-shrinking counter in a report.
for _qid in _HIGH_VALUE_QUESTIONS:
    REGISTRY.get(_qid)   # raises KeyError on an unknown id
del _qid


def _predicted_depth(cand: sqlite3.Row) -> str | None:
    """Track B stored an intake-time depth prediction in the candidate's
    `evidence` payload (see `_emit`). Read it back — this is the plumbing
    `_write_entity`'s docstring said did not exist yet. `evidence` is plain
    snippet text for candidates minted anywhere else, so a parse failure is
    the normal case, not an error."""
    try:
        payload = json.loads(cand["evidence"] or "")
    except (ValueError, TypeError):
        return None
    return payload.get("predicted_depth") if isinstance(payload, dict) else None


def _backfill_trigger_edge(conn: sqlite3.Connection, cand: sqlite3.Row, kind: str,
                           entity_id: str, *, by: str, log=print) -> None:
    """The other half of `_trigger_edge_fields`: a candidate minted from an
    unresolved edge destination (`_mint_or_resolve_problem` /
    `_mint_or_resolve_actor`) carries its triggering entity and edge kind on
    its OWN evidence, captured back when it was minted — safe to capture
    then because the source candidate was already resolved (`_settle` runs
    before `_emit` in `run_batch`, below). The only thing deferred was this
    candidate itself becoming an entity. Now that it has (`entity_id` is
    freshly written), the edge that couldn't be linked at mint time finally
    can be.

    A candidate minted any other way (corpus migration, the `emits` loop,
    manually) simply has no `edge_kind` in its evidence and this is a no-op —
    same "parse failure is the normal case" contract as `_predicted_depth`."""
    try:
        payload = json.loads(cand["evidence"] or "")
    except (ValueError, TypeError):
        return
    if not isinstance(payload, dict):
        return
    from_kind, from_id, edge_kind = (payload.get("from_kind"),
                                      payload.get("from_id"),
                                      payload.get("edge_kind"))
    if not (from_kind and from_id and edge_kind):
        return
    try:
        db.link(conn, (from_kind, from_id), edge_kind, (kind, entity_id),
                by=by, relevance=payload.get("edge_relevance"),
                evidence=payload.get("edge_evidence"),
                why=f"backfilled on promotion of candidate {cand['id']} — "
                    "edge was dropped at mint time because this candidate "
                    "wasn't an entity yet")
    except sqlite3.IntegrityError as ex:
        log(f"worker: backfilled edge {edge_kind} {from_id} -> {entity_id} "
            f"rejected: {ex}")


# --------------------------------------------------- the extraction resume ---
# `05-worker-optimisations.md`: "Extraction fails, restart -> another half an
# hour gone. Instead just continue from extraction?"
#
# The two stages above extraction are the expensive ones and neither is paid
# for in tokens: the search stage runs ~17 query families at
# `provider.THROTTLE_FLOOR_S` (2s) apiece plus a fetch per covered URL, and
# gate 2 embeds every fetched page locally. Extraction is one call that
# either parses or does not. Retrying the cheap failing stage by redoing both
# expensive ones is the wrong ratio.
#
# The page text never needed saving — `source.path` has held cleaned text on
# disk since E0 and `fetch()` short-circuits on `url_canonical` before any
# HTTP. What died with the frame was the SET: which URLs search chose for
# this candidate, and what gate 2 said about each. Persisting those two facts
# (`candidate_source`) is what makes the fetch cache usable as a resume point
# rather than merely a bandwidth saving.


PROMPT_BUCKET = "prompt"
VERIFY_BUCKET = "verify"


def _save_assembly(conn: sqlite3.Connection, cid: str, bucket: str,
                   prompt_sources, coverage: dict) -> None:
    """Freeze one `assemble()` output. `label` is not written — see
    `store/schema.sql`'s note on `candidate_prompt.blocks`; it is re-derived
    on load, which reproduces it exactly because `assemble` assigns labels by
    first appearance in the order stored here."""
    blocks = [{"source_id": s.source_id, "url": s.url, "text": s.text,
               "chunk_refs": list(s.chunk_refs),
               "chunk_texts": list(s.chunk_texts)}
              for s in prompt_sources]
    conn.execute(
        "INSERT OR REPLACE INTO candidate_prompt "
        "(candidate_id, bucket, blocks, coverage, assembled_at) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (int(cid), bucket, json.dumps(blocks), json.dumps(coverage or {})))
    conn.commit()


def _load_assembly(conn: sqlite3.Connection, cid: str, bucket: str):
    """-> `(prompt_sources, coverage)`, or None when this bucket was never
    assembled for this candidate.

    An empty `blocks` array is a real answer, not a miss: `assemble` returning
    nothing is §13's degrade into the whole-text call, and re-running the
    ranking pass to rediscover that costs exactly what this table exists to
    avoid."""
    row = conn.execute(
        "SELECT blocks, coverage FROM candidate_prompt "
        "WHERE candidate_id = ? AND bucket = ?", (int(cid), bucket)).fetchone()
    if row is None:
        return None
    blocks = json.loads(row["blocks"])
    coverage = json.loads(row["coverage"] or "{}")
    prompt_sources = [
        PromptSource(source_id=b["source_id"], label=f"S{i}", url=b["url"],
                     text=b["text"], chunk_refs=tuple(b["chunk_refs"]),
                     chunk_texts=tuple(b.get("chunk_texts") or ()))
        for i, b in enumerate(blocks, start=1)]
    return prompt_sources, coverage


def _save_resolution(conn: sqlite3.Connection, cid: str, decision) -> None:
    """Freeze the resolver's verdict for this candidate."""
    conn.execute(
        "INSERT OR REPLACE INTO candidate_resolution "
        "(candidate_id, decision, entity_id, shortlist, reason, resolved_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (int(cid), decision.decision, decision.entity_id,
         json.dumps([[i, c] for i, c in decision.shortlist]), decision.reason))
    conn.commit()


def _load_resolution(conn: sqlite3.Connection, cid: str, kind: str, name: str,
                     *, log=print):
    """-> a stored `ResolveResult`, or None to resolve live.

    This is the only cached stage whose correct answer legitimately changes
    between runs: the graph gains entities, so a candidate that resolved
    `new` an hour ago may match one now. Reusing the row blindly would mint a
    duplicate. Two guards, both free — neither loads the encoder, which is
    the entire point of reusing this at all:

    1. **The alias match is re-run first.** `db.resolve` is the same
       normalized exact match `resolve_entity` opens with, it costs a lookup,
       and a live hit beats the stored row — which is exactly the case where
       the graph moved under a cached `new`.
    2. **A stored `entity_id` must still exist.** A merged-away or deleted
       entity falls through to a full resolve rather than being written to.
    """
    row = conn.execute("SELECT * FROM candidate_resolution WHERE candidate_id = ?",
                       (int(cid),)).fetchone()
    if row is None:
        return None

    exact = db.resolve(conn, kind, name)
    if exact is not None and exact != row["entity_id"]:
        log(f"worker: candidate {cid} stored resolution superseded — the "
            f"alias match now hits {exact}, resolving live")
        return None

    entity_id = row["entity_id"]
    if entity_id is not None and conn.execute(
            f"SELECT 1 FROM {kind} WHERE id = ?", (entity_id,)).fetchone() is None:
        log(f"worker: candidate {cid} stored resolution points at {entity_id}, "
            "which is gone — resolving live")
        return None

    return resolve.ResolveResult(
        decision=row["decision"], entity_id=entity_id,
        shortlist=[(i, c) for i, c in json.loads(row["shortlist"] or "[]")],
        reason=row["reason"] or "")


def _resume_available(conn: sqlite3.Connection) -> bool:
    """Whether this store carries schema v4's two resume structures.

    Checked once per batch rather than defended against per statement: on an
    unmigrated store the whole feature is off — no recording, no resuming —
    which is exactly the pre-v4 behaviour, instead of a run that dies at the
    first candidate over a missing table.
    """
    wanted = {"candidate_source", "candidate_prompt", "candidate_resolution"}
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    column = any(r[1] == "searched_at"
                 for r in conn.execute("PRAGMA table_info(candidate)"))
    return wanted <= tables and column


def _record_sources(conn: sqlite3.Connection, cid: str,
                    sources: list[ConfirmedSource],
                    unverified: list[ConfirmedSource]) -> None:
    """Freeze this candidate's post-gate-2 source set, and stamp
    `searched_at`.

    Rewritten whole rather than appended to: a re-run with `--no-resume`
    produces a new set, and a half-old/half-new union is not a set any run
    ever had. `searched_at` is stamped even when both lists are empty —
    "searched, found nothing" is a real outcome and must not read as "never
    searched" on the next pass.
    """
    conn.execute("DELETE FROM candidate_source WHERE candidate_id = ?", (int(cid),))
    # The assembled blocks are derived from the set being replaced, so they
    # go with it. Keeping them would resume a new source set into an old
    # prompt — the one way this cache could produce a wrong answer rather
    # than a slow one.
    conn.execute("DELETE FROM candidate_prompt WHERE candidate_id = ?", (int(cid),))
    # Likewise the resolution: its embedding context is the seed page, so a
    # new source set can mean a different vector and a different verdict.
    conn.execute("DELETE FROM candidate_resolution WHERE candidate_id = ?",
                 (int(cid),))
    rows = [(int(cid), s.source_id, s.url, s.origin, route, s.verdict)
            for route, bucket in ((confirm_policy.PROMPT, sources),
                                  (confirm_policy.VERIFY, unverified))
            for s in bucket]
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO candidate_source "
            "(candidate_id, source_id, url, origin, route, verdict) "
            "VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.execute("UPDATE candidate SET searched_at = datetime('now') WHERE id = ?",
                 (int(cid),))
    conn.commit()


def _load_sources(conn: sqlite3.Connection, corpus: Path, cand: sqlite3.Row,
                  *, log=print):
    """-> `(sources, unverified, text)`, or None when this candidate has
    never been searched.

    Text comes back through `fetch()`, which is a pure cache read here: every
    `source_id` in the table was fetched on the first pass, so the
    `url_canonical` lookup hits and no HTTP happens. A row whose text has
    since gone missing from disk (a cleared `problems/private/sources/`) is
    dropped with a log line rather than resurrected by a network call — a
    resumed set is allowed to be smaller than the original, but never to
    silently differ from it.

    `text` is the SEED page, which `resolve.resolve_entity` and the
    non-batched extraction path both need and which is not reconstructible
    from the prompt sources (they need not include the seed at all).
    """
    if cand["searched_at"] is None:
        return None
    rows = conn.execute(
        # `origin` before `recorded_at` puts the seed back at the head of the
        # prompt set, where the first run appended it — the whole row set is
        # usually written in one statement, so `recorded_at` alone ties and
        # cannot restore that order. Labels (`S1`…`Sn`) are assigned in list
        # order downstream, so this keeps a resumed prompt as close to the
        # original as the stored data allows.
        "SELECT * FROM candidate_source WHERE candidate_id = ? "
        "ORDER BY route, origin, recorded_at", (int(cand["id"]),)).fetchall()

    sources: list[ConfirmedSource] = []
    unverified: list[ConfirmedSource] = []
    text = ""
    for row in rows:
        fetched = fetchmod.fetch(conn, corpus, row["url"])
        if not fetched.text:
            log(f"worker: candidate {cand['id']} cached source "
                f"{row['source_id']} has no text on disk, dropped from the "
                f"resumed set: {row['url'][:70]}")
            continue
        source = ConfirmedSource(source_id=row["source_id"], url=row["url"],
                                 text=fetched.text, origin=row["origin"],
                                 verdict=row["verdict"])
        if row["origin"] == confirm_policy.SEED:
            text = fetched.text
        (sources if row["route"] == confirm_policy.PROMPT
         else unverified).append(source)
    return sources, unverified, text


def make_log(*, quiet: bool = False, stream=None):
    """The run's log callable — `print` plus elapsed and per-line delta.

    Every stage in the worker takes `log` injected (`log=print` defaults
    throughout this module, `search_stage.search_sources`, `gate1.screen`),
    so there is exactly one place a run's logger is built and this is it.

    Two numbers, because they answer different questions:
      `[03:12.4 +31.2s] search_stage: confirming https://...`
       ^^^^^^^ elapsed since the run started — where in the run this is
                ^^^^^ time since the PREVIOUS line — what that step cost

    The delta is the one that finds a stall. Bare `print` gave neither, so a
    run that took 50 minutes was indistinguishable from one that took 50
    seconds, and the line before a hang looked exactly like any other line.
    Candidate 28's stuck run (2026-09-14T22:45) was diagnosed by attaching
    lldb to a live process, because the log could not say which step had
    been sitting there and for how long.

    `flush=True` is not cosmetic. These runs are redirected to a file
    (`worker/runs/<ts>-<pid>.log`), where stdout is block-buffered, so a run
    killed externally — exactly what happens to a hang — lost the last
    several KB of its log, including the line naming the step it died in.
    Flushing per line costs nothing at this volume and means the log on disk
    is always current as of the last thing that happened.
    """
    if quiet:
        return lambda *a, **k: None
    t0 = time.monotonic()
    last = [t0]

    def log(*args, **kwargs):
        now = time.monotonic()
        elapsed, delta = now - t0, now - last[0]
        last[0] = now
        stamp = f"[{int(elapsed // 60):02d}:{elapsed % 60:04.1f} +{delta:5.1f}s]"
        kwargs.setdefault("flush", True)
        if stream is not None:
            kwargs.setdefault("file", stream)
        print(stamp, *args, **kwargs)

    return log


def run_batch(conn: sqlite3.Connection, corpus: Path, candidates: list[sqlite3.Row],
             *, log=print, depth_tier: bool | None = None,
             problem_emission: bool | None = None, search_provider=None,
             max_sources: int | None = None, resume: bool = True) -> dict:
    """`search_provider=None` is track D's documented degrade (§13): the
    candidate's own URL as the single source, which is exactly what this
    loop did before track D existed. Pass a `search.provider` adapter to
    turn the search stage on.

    `depth_tier` / `problem_emission`: None takes the env-supplied module
    default. They are parameters rather than env switches because
    `04-worker-build-plan.md` §6 called the env vars a workaround for this
    function being frozen, and E6 is where that freeze lifts.

    `resume=True` (the default) re-enters a candidate that has already been
    searched at the extraction stage, rebuilding its source set from
    `candidate_source` + the fetch cache instead of re-running search and
    gate 2. `resume=False` redoes both — which is what you want when the
    first run's set was thin and a wider cap or a fixed provider should now
    produce a better one, and nothing else.
    """
    depth_tier = _DEPTH_TIER_DEFAULT if depth_tier is None else depth_tier
    problem_emission = (_PROBLEM_EMISSION_DEFAULT if problem_emission is None
                        else problem_emission)
    report = {
        "gate0_collapsed": 0, "gate1_kept": 0, "gate1_rejected": 0, "fetched": 0,
        "gate2_confirmed": 0, "gate2_uncertain": 0, "gate2_mismatch": 0,
        "extracted": 0, "resolved_exact": 0, "resolved_shortlist": 0,
        "resolved_ambiguous": 0, "resolved_new": 0, "edges_written": 0,
        "candidates_emitted": 0, "cost": 0.0,
        # stage 7 (§9) and the batched call (§8)
        "findings_written": 0, "cites_written": 0,
        "extracted_batched": 0, "extracted_single": 0,
        "retry_per_source_calls": 0, "retry_per_source_rescued": 0,
        # E3's coverage counters — §3 correction 4. `sources_dropped_by_cap`
        # cannot currently fire (`_cap_tokens` never drops a source's last
        # chunk); it is a regression detector for that guarantee, not a
        # measurement. See `poc/poc2-results.md` -> "Item 6 answered".
        "sources_fetched": 0, "sources_in_prompt": 0,
        "sources_never_selected": 0, "sources_dropped_by_cap": 0,
        # §11c's three counters, batch totals. Per-candidate values are
        # logged (the resolution a single dict cannot hold), by decision:
        # report-dict-only, not `event` rows and not a new table.
        "hv_questions_open": 0, "unread_pool_urls": 0, "new_query_seeds": 0,
        # The verify pass (§6a) — how often the confirmed set could not carry
        # a candidate alone, and what the second opinion found. `verify_
        # different` is the interesting one: a page an automated cosine could
        # not rule out that a reading model identified as a different entity
        # sharing the name.
        # Rule 4 on the MAIN prompt: a source that cleared gate 2 which the
        # reading model says is a different entity. Directly comparable with
        # `verify_different` — that one is the uncertain bucket's false
        # negatives, this one is the confirmed set's false positives.
        "sources_flagged_misidentified": 0,
        "post_drop_thin": 0,
        "verify_pass_calls": 0, "verify_answers_merged": 0,
        "verify_about": 0, "verify_different": 0,
        "verify_unrelated": 0, "verify_insufficient": 0,
        # The resume point. `resumed` counts candidates that skipped
        # fetch/search/gate 2 entirely; `resumed_sources` the sources they
        # got back without a single HTTP request or embedding call;
        # `resolve_reused` the resolutions that did not re-pay encode + kNN.
        "resumed": 0, "resumed_sources": 0, "resolve_reused": 0,
        # A candidate's own failure must not lose the rest of the batch
        # (2026-09-18, exit-1 mid-batch with no traceback captured — see
        # the try/except wrapping the per-candidate loop body below).
        "candidate_crashed": 0,
    }
    if not candidates:
        return report
    by_id = {str(c["id"]): c for c in candidates}
    persist_sources = _resume_available(conn)
    if not persist_sources:
        log("worker: store predates schema v4 — resume disabled; run "
            "`python -m migrate.m0004_candidate_source <db>` to enable it")
    resume = resume and persist_sources

    # gate 0 — preview dedup, free, before anything is fetched. `fetch_list`
    # keeps exactly one representative per merge group (its first member) and
    # drops the rest from every later stage — `items`/`decisions`/`alive`
    # below never see a dropped duplicate again. Without `dupes`, those
    # duplicates get no `admitted`, no `resolved_to`, no event: they sit at
    # the front of the CLI's `resolved_to IS NULL ORDER BY first_seen` queue
    # forever, re-collapsed and re-skipped on every run. `_settle` (below)
    # closes that by copying the representative's terminal state onto them.
    previews = [Preview(key=str(c["id"]), title=c["name"] or "",
                        snippet=(c["evidence"] or ""), url=c["url"] or "")
                for c in candidates]
    dupes: dict[str, list[str]] = {}
    for g in group(previews):
        if g.verdict == "merge":
            rep, dropped = g.members[0], g.members[1:]
            dupes.setdefault(rep, []).extend(dropped)
            log(f"gate0: collapsed {g.members} into {rep} ({g.reason})")
            report["gate0_collapsed"] += len(dropped)
    survivors = set(fetch_list(previews))

    def _settle(cid: str, *, resolved_to: str | None, admitted: int | None,
               by: str, why: str, field: str = "admitted") -> None:
        """Apply one terminal outcome to `cid` AND every duplicate gate 0
        folded into it. Primary and duplicates get the same field values;
        only the duplicates additionally get an event naming the merge, since
        the primary's own event/write already explains itself."""
        conn.execute("UPDATE candidate SET resolved_to = ?, admitted = ? WHERE id = ?",
                     (resolved_to, admitted, int(cid)))
        for dup in dupes.get(cid, []):
            conn.execute("UPDATE candidate SET resolved_to = ?, admitted = ? WHERE id = ?",
                         (resolved_to, admitted, int(dup)))
            db.record(conn, "candidate", dup, field,
                      None, resolved_to if field == "resolve" else admitted,
                      by="worker:gate0", why=f"collapsed into {cid}: {why}")

    # gate 1 — batched pre-fetch screen, tuned for recall.
    #
    # A candidate being resumed is not re-screened. Gate 1 reads the name and
    # the intake snippet — exactly the inputs it read the first time, none of
    # which change between runs — so a second screen can only agree at a cost,
    # or disagree and throw away a source set already paid for in search time.
    # The first screen's verdict stands; `searched_at` is the evidence it
    # passed.
    resumable = ({str(c["id"]) for c in candidates
                  if str(c["id"]) in survivors and c["searched_at"] is not None}
                 if resume else set())
    items = [{"id": str(c["id"]), "kind": c["kind"], "name": c["name"],
             "snippet": c["evidence"] or "", "url": c["url"] or ""}
             for c in candidates
             if str(c["id"]) in survivors and str(c["id"]) not in resumable]
    decisions, gate1_cost = gate1.screen(items, log=log) if items else ({}, 0.0)
    report["cost"] += gate1_cost
    alive: list[str] = []
    for cid in (str(c["id"]) for c in candidates if str(c["id"]) in resumable):
        alive.append(cid)
        report["gate1_kept"] += 1
    for cid, (keep, reason) in decisions.items():
        if keep:
            alive.append(cid)
            report["gate1_kept"] += 1
        else:
            # entity_kind is "candidate", not by_id[cid]["kind"] — this event
            # is about the candidate ROW's admitted field, not about a
            # problem/actor graph entity (cid is a candidate id, and using
            # "actor"/"problem" here would make it look like one).
            db.record(conn, "candidate", cid, "admitted", None, 0,
                      by="worker:gate1", why=reason)
            _settle(cid, resolved_to=None, admitted=0, by="worker:gate1",
                   why=reason)
            report["gate1_rejected"] += 1
    conn.commit()

    resolved_this_batch: dict[tuple[str, str], str] = {}

    for cid in alive:
        cand = by_id[cid]
        name, kind = cand["name"], cand["kind"]
        try:
            log(f"worker: candidate {cid} stage=start ({kind} {name!r})")

            text = ""
            sources: list[ConfirmedSource] = []
            unverified: list = []

            # resume — the whole of fetch + search + gate 2, replaced by one
            # table read and a disk read per source. Every stage below that is
            # guarded on `cached is None` is a stage this candidate has already
            # paid for. Guarded rather than nested so the first-run path reads
            # exactly as it did before, unindented and unchanged.
            cached = _load_sources(conn, corpus, cand, log=log) if resume else None
            if cached is not None:
                sources, unverified, text = cached
                report["resumed"] += 1
                report["resumed_sources"] += len(sources) + len(unverified)
                log(f"worker: candidate {cid} stage=resume — {len(sources)} prompt "
                    f"+ {len(unverified)} unverified source(s) from the set "
                    f"searched {cand['searched_at']}, no fetch/search/gate2")

            # fetch — a bare name (no URL) skips straight to extraction with
            # empty text: a stub actor from a registry row legitimately has no
            # document yet, and that is not a reason to stop the pipeline.
            if cached is None and cand["url"]:
                log(f"worker: candidate {cid} stage=fetch {cand['url']}")
                fetched = fetchmod.fetch(conn, corpus, cand["url"])
                report["fetched"] += 1
                text = fetched.text or ""

                if text:
                    verdict, cosine, note = gate2.confirm(conn, name, cand["evidence"] or "", text)
                    report[f"gate2_{verdict}"] += 1
                    if verdict == "mismatch":
                        why = f"mismatch at cosine {cosine:.3f}"
                        db.record(conn, "candidate", cid, "admitted", None, 0,
                                  by="worker:gate2", why=why)
                        _settle(cid, resolved_to=None, admitted=0, by="worker:gate2",
                               why=why)
                        conn.commit()
                        continue
                    # Everything past `mismatch` goes through the same policy as
                    # a search source. It used to append to `sources`
                    # unconditionally, which meant an `uncertain` SEED reached the
                    # main extraction prompt even after the search path stopped
                    # letting uncertain through — the same hole, one origin later.
                    # Mismatch stays special above because that verdict is the
                    # CANDIDATE's admission decision, which no per-source policy
                    # can express.
                    seed_source = ConfirmedSource(
                        source_id=fetched.source_id, url=cand["url"], text=text,
                        origin=confirm_policy.SEED, verdict=verdict)
                    [seed_decision] = confirm_policy.apply_confirmations([
                        confirm_policy.SourceVerdict(
                            source_id=fetched.source_id, url=cand["url"],
                            origin=confirm_policy.SEED, verdict=verdict,
                            cosine=cosine, note=note, text_chars=len(text))])
                    if seed_decision.route == confirm_policy.PROMPT:
                        sources.append(seed_source)
                    else:
                        log(f"worker: candidate {cid} seed to verify: "
                            f"{seed_decision.reason}")
                        unverified.append(seed_source)

            # search (track D, wired here). The seed is fetched and gate-2'd
            # above rather than handed to `search_sources`, because that verdict
            # is the CANDIDATE's admission decision — a mismatch rejects the
            # candidate outright, which is not something a per-source policy can
            # express. So the search stage is asked only for what the seed did
            # not supply, hence `seed_url=None`.
            #
            # The NO_VERDICT drop (D3's policy, adopted at integration) applies
            # to search sources. A seed that fetched no text yields no source
            # here either — but the CANDIDATE still reaches extraction on its
            # name alone, because a bare registry row with no document is
            # legitimate (§7) and was never a source to drop in the first place.
            search_counters: dict = {}
            if cached is None and search_provider is not None:
                log(f"worker: candidate {cid} stage=search")
                # Deduped against the seed: `search_sources` is called with
                # `seed_url=None`, but nothing stops set cover from picking the
                # seed's own URL out of the search results. `fetch` is cached on
                # `url_canonical` and returns the same `source.id` for it, so the
                # seed would otherwise be gate-2'd a second time and appear twice
                # in `sources` — which `extract.assemble` then chunks twice,
                # repeating the same passages inside one `[Sn]` block and
                # inflating `sources_fetched`. `source_id` is the durable
                # identity (`extract_types.py`), so it is the right key here.
                already = {s.source_id for s in sources}
                sources.extend(s for s in search_stage.search_sources(
                    name, depth=_predicted_depth(cand) or depth_mod.TRACKED_TIER,
                    kind=cand["kind"],
                    provider=search_provider,
                    fetch=lambda url: fetchmod.fetch(conn, corpus, url),
                    confirm=lambda n, ev, txt: gate2.confirm(conn, n, ev, txt),
                    confirm_many=lambda n, ev, txts: gate2.confirm_many(conn, n, ev, txts),
                    evidence=cand["evidence"] or "", seed_url=None,
                    max_sources=max_sources, escalate=True,
                    counters=search_counters,
                    unverified=unverified, log=log)
                    if s.source_id not in already)
                unverified[:] = [s for s in unverified if s.source_id not in already]

            # Freeze the set here — after search and gate 2, before the first
            # paid call of the candidate. Everything from this line on (verify,
            # extraction, resolve, emit) can fail and be retried for the price of
            # the call that failed.
            if cached is None and persist_sources:
                _record_sources(conn, cid, sources, unverified)

            # The verify pass (§6a). `unverified` holds gate-2 `uncertain` and
            # confirmed-but-thin sources — material that must not enter the main
            # prompt, but is not junk by default: the band sweep found a real
            # LinkedIn post and a real book page sitting in it, below four
            # wrong-entity pages. It buys a second call ONLY when the confirmed
            # set cannot carry the candidate alone, because the pass costs as
            # much as the call it supplements.
            verified_answers: list[Answer] = []
            verify_sources: list = []

            def _run_verify_pass() -> tuple[list, list]:
                """The §6a pass over `unverified`, factored out 2026-09-18 so it
                has two callers. It used to have one, here, gated on gate 2's
                pre-extraction thinness verdict — but that is the verdict Rule 4
                exists to overrule, so the one case that most needs a second
                witness was the one case that could not ask for one. See the
                post-drop re-check below `drop_misidentified`.

                Returns `(answers, sources)`, both empty when the pass does not
                run or fails. Idempotent per candidate in practice: the second
                caller only fires when the first did not."""
                v_answers_out: list = []
                v_sources_out: list = []
                log(f"worker: candidate {cid} stage=verify")
                report["verify_pass_calls"] += 1
                # Cached like the main set: §6a assembles its own bucket and pays
                # its own ranking pass, so a resume that only cached the main one
                # would still chunk and encode every unverified source.
                v_cached = (_load_assembly(conn, cid, VERIFY_BUCKET)
                            if cached is not None else None)
                if v_cached is not None:
                    v_sources, _ = v_cached
                    log(f"worker: candidate {cid} verify set from cache "
                        f"({len(v_sources)} block(s)), no ranking pass")
                else:
                    v_sources, v_coverage = extract_mod.assemble(
                        unverified, REGISTRY.retrieval_questions(kind),
                        geography_bias=(kind == "problem"))
                    if persist_sources:
                        _save_assembly(conn, cid, VERIFY_BUCKET, v_sources, v_coverage)
                if v_sources:
                    v_system, v_prompt = verify_and_extract_prompt_batched(
                        kind, name, cand["evidence"] or "", v_sources)
                    try:
                        v_result = llm.call(
                            v_prompt, system=v_system, tier="judgment",
                            max_tokens=llm.extraction_max_tokens(len(v_sources)))
                    except llm.LLMError as e:
                        log(f"worker: candidate {cid} verify pass failed: {e}")
                    else:
                        report["cost"] += v_result.get("cost", 0.0)
                        v_answers, v_verdicts, v_problems = parse_verified_answers(
                            v_result.get("json"), v_sources)
                        for problem in v_problems:
                            log(f"worker: candidate {cid} verify: {problem}")
                        for sid, v in v_verdicts.items():
                            log(f"worker: candidate {cid} verify {v['label']} "
                                f"{v['verdict']}: {v['url'][:70]}"
                                + (f" — actually about: {v['about_what'][:60]}"
                                   if v["about_what"] else ""))
                            report[f"verify_{v['verdict']}"] += 1
                        # The verify pass's own answers are kept rather than
                        # thrown away and the accepted sources re-read in the main
                        # call: the model has already read that text once, and the
                        # whole point of the §8 batched call is that a source is
                        # paid for once. They merge into the ledger below with the
                        # same provenance as any other answer — `verify_sources`
                        # carries their urls so §9 can attribute them.
                        v_answers_out = v_answers
                        v_sources_out = v_sources
                return v_answers_out, v_sources_out

            thin, why = prompt_set_is_thin([s.text for s in sources])
            log(f"worker: candidate {cid} stage=verify-check: {why}")
            if thin and unverified:
                verified_answers, verify_sources = _run_verify_pass()
            elif unverified:
                log(f"worker: candidate {cid} {len(unverified)} unverified "
                    f"source(s) left unread — confirmed set was adequate")

            # claims — the one paid call in the loop (§7 tier 4). With sources in
            # hand it is §8's batched `[S1]…[Sn]` call over selected passages;
            # with none it is the original whole-text call, which is also §13's
            # degrade path when passage assembly yields nothing.
            #
            # The ranking pass is the expensive half of a resume: `assemble`
            # chunks every source and `passages._rank_chunks` encodes every chunk
            # against every retrieval question — strictly more embedding than
            # gate 2 does, and it loads the tokenizer besides. Cached, a resumed
            # candidate touches the encoder only for `resolve`'s single name
            # vector.
            prompt_sources, coverage = ([], {})
            assembly = (_load_assembly(conn, cid, PROMPT_BUCKET)
                        if cached is not None else None)
            if assembly is not None:
                prompt_sources, coverage = assembly
                log(f"worker: candidate {cid} prompt set from cache "
                    f"({len(prompt_sources)} block(s)), no chunking or ranking")
            elif sources:
                prompt_sources, coverage = extract_mod.assemble(
                    sources, REGISTRY.retrieval_questions(kind),
                    geography_bias=(kind == "problem"))
                if persist_sources:
                    _save_assembly(conn, cid, PROMPT_BUCKET, prompt_sources, coverage)
            batched = bool(prompt_sources)
            for key in ("sources_fetched", "sources_in_prompt",
                        "sources_never_selected", "sources_dropped_by_cap"):
                report[key] += int(coverage.get(key, 0))
            if coverage:
                log(f"worker: candidate {cid} coverage " +
                    " ".join(f"{k}={v}" for k, v in sorted(coverage.items())))

            if batched:
                system, prompt = extract_prompt_batched(kind, name, prompt_sources)
            else:
                system, prompt = extract_prompt(kind, name, text)
            log(f"worker: candidate {cid} stage=extract "
                f"({'batched' if batched else 'single'}, "
                f"{len(prompt_sources)} source(s))")
            # Batched calls scale with source count (§ llm.extraction_max_tokens
            # docstring — flat 4096 was the real bottleneck behind "malformed
            # extraction JSON (dict)", 2026-09-18). The non-batched whole-text
            # path keeps the flat budget: it has no `prompt_sources` count to
            # scale by, and was never observed to trip this failure.
            extract_max_tokens = (llm.extraction_max_tokens(len(prompt_sources))
                                  if batched else 4096)
            claims_json = None
            # Tracks which model(s) produced `claims_json`, for the `by=`
            # attribution string used at resolve/write time below. The normal
            # `else:` branch sets it from the one extraction call; the §13
            # per-source rescue path (candidate 528, 2026-09-18 production log)
            # has no single `result` to read `.model` off — each rescued source
            # is its own `llm.call()` with its own model — so it is built up
            # there instead. Never left unset: an UnboundLocalError here
            # previously killed the whole batch (candidate 528, 2026-09-18T14:00
            # log — `result` unset on the rescue path, `result.get('model')`
            # crashed at resolve time).
            model_used: str = "?"
            try:
                result = llm.call(prompt, system=system, tier="judgment",
                                  max_tokens=extract_max_tokens)
            except llm.JSONParseError as e:
                # The model itself emitted broken JSON on every attempt (not a
                # network blip) — 2026-09-18, candidates 528/552/560. Batched:
                # fall through to the same §13 per-source rescue below instead
                # of skipping the whole candidate; `claims_json` stays `None`,
                # which the `not isinstance(claims_json, dict)` check below
                # already treats as a parse failure. Non-batched has no
                # per-source rescue to fall into, so it still just skips.
                log(f"worker: candidate {cid} extraction JSON parse failed on "
                    f"every attempt: {e}")
                if not batched:
                    continue
            except llm.LLMError as e:
                log(f"worker: candidate {cid} extraction failed, skipping: {e}")
                continue
            else:
                report["cost"] += result.get("cost", 0.0)
                claims_json = result.get("json")
                model_used = result.get("model", "?")

            answers: list[Answer] = []
            if batched and not isinstance(claims_json, dict):
                # §13's per-source fallback. PoC-2 measured it rescuing 1/1 parse
                # failures, and that one failure was NOT prompt-size-driven — it
                # fired at 4,082 chars while a larger response parsed clean — so
                # the retry is warranted by the observation, not by a size rule.
                log(f"worker: candidate {cid} batched parse failed, retrying "
                    f"{len(prompt_sources)} sources one at a time (§13)")
                rescue_models: set[str] = set()
                # Circuit breaker, added 2026-09-18. §13's rescue was designed
                # for a PROMPT-shaped failure — one oversized batch the model
                # couldn't render cleanly, where splitting it genuinely helps.
                # It is useless against a PROVIDER-shaped one, and candidate
                # 528 is the case: every model was failing identically, so all
                # 8 per-source calls failed identically too, each burning the
                # full attempts x models fan-out (~5 minutes apiece) to learn
                # the same thing the batched call had already established.
                # 45 minutes, no output. If the first two sources both fail
                # outright, the provider is down and the remaining sources
                # cannot inform that — stop and let the candidate record a
                # failure it can be resumed from. A rescue that has worked
                # even once resets the counter, because then the failures
                # really are per-source.
                consecutive_failures = 0
                for src, sys_p, usr_p in retry_per_source(kind, name, prompt_sources):
                    if consecutive_failures >= 2:
                        log(f"worker: candidate {cid} §13 rescue abandoned after "
                            f"{consecutive_failures} consecutive provider failures "
                            f"— this is a provider outage, not a prompt-size "
                            f"problem; the remaining sources would fail identically")
                        break
                    report["retry_per_source_calls"] += 1
                    try:
                        one = llm.call(usr_p, system=sys_p, tier="judgment",
                                       max_tokens=4096)
                    except llm.LLMError as e:
                        consecutive_failures += 1
                        log(f"worker: candidate {cid} retry on {src.source_id} "
                            f"failed: {e}")
                        continue
                    consecutive_failures = 0
                    report["cost"] += one.get("cost", 0.0)
                    got, problems = parse_answers(one.get("json"), [src._replace(label="S1")])
                    for problem in problems:
                        log(f"worker: candidate {cid} retry {src.source_id}: {problem}")
                    if got:
                        report["retry_per_source_rescued"] += 1
                        answers.extend(got)
                        rescue_models.add(one.get("model", "?"))
                if not answers:
                    log(f"worker: candidate {cid} malformed extraction JSON "
                        f"({type(claims_json).__name__}) and no source rescued it, "
                        "skipping")
                    continue
                # §13's per-source rescue has no single extraction call to
                # attribute to — each surviving source may even have used a
                # different model on retry. One model across the board: name it.
                # More than one, or none recorded: a clear "rescued" marker
                # rather than a fabricated single model name.
                model_used = (rescue_models.pop() if len(rescue_models) == 1
                             else "rescued:" + "+".join(sorted(rescue_models))
                             if rescue_models else "rescued:?")
                claims_json = {"claims": [], "emits": [], "edges": []}
            elif not isinstance(claims_json, dict) or not all(
                    isinstance(claims_json.get(k), list)
                    for k in (("emits", "edges") if batched
                              else ("claims", "emits", "edges"))):
                # `claims` left the BATCHED schema 2026-09-14 — claims are derived
                # from findings there, so requiring the key would fail every
                # batched response the moment the prompt stopped asking for it.
                # The single-source prompt still asks and still needs it: that
                # path has no findings to derive from.
                # `.get` on a non-dict (the model returned a bare array, or
                # `parse_json` failed and left `json` unset) would crash the
                # batch — a malformed shape is a logged skip, same discipline as
                # gate1's non-object guard.
                log(f"worker: candidate {cid} malformed extraction JSON "
                    f"({type(claims_json).__name__}), skipping")
                continue
            elif batched:
                answers, problems = parse_answers(claims_json, prompt_sources)
                # Rule 4: the model may flag a source that cleared gate 2 as being
                # about a different entity. It reads the whole page and gate 2
                # read 500 characters of it, so it is the better-informed of the
                # two — but the flag is enforced here rather than trusted, the
                # same as the verify pass's verdicts.
                flagged, flag_problems = parse_misidentified(claims_json, prompt_sources)
                problems.extend(flag_problems)
                if flagged:
                    answers, dropped = drop_misidentified(answers, flagged)
                    problems.extend(dropped)
                    for sid, f in flagged.items():
                        report["sources_flagged_misidentified"] += 1
                        log(f"worker: candidate {cid} model flagged {f['label']} "
                            f"as misidentified: {f['url'][:70]}"
                            + (f" — actually about: {f['about_what'][:60]}"
                               if f["about_what"] else ""))
                    # Re-run the thinness check on what SURVIVED the drop
                    # (2026-09-18). Candidate 528 is the motivating case: 7 of
                    # its 8 sources were flagged misidentified — urbandictionary
                    # .com, openai.com, a UK cost-of-living article, a Nigerian
                    # logistics post, a Hindi UP-government page, all of which
                    # gate 2 had CONFIRMED (urbandictionary at cosine 0.812,
                    # openai.com at 0.811, against a candidate name containing
                    # the word "urban") — and the candidate then wrote a
                    # complete 19-finding record off the single survivor without
                    # anything saying so.
                    #
                    # The pre-extraction check above cannot catch this: it runs
                    # on gate 2's verdict, and Rule 4 exists precisely because
                    # gate 2's verdict is the unreliable one — it reads ~500
                    # characters, the extraction model reads the whole page. So
                    # the case where the confirmed set collapses is exactly the
                    # case the existing escalation could never see. Same
                    # function, same thresholds, applied to the set we actually
                    # ended up with rather than the one we hoped for.
                    surviving = [s_ for s_ in sources
                                 if s_.source_id not in flagged]
                    post_thin, post_why = prompt_set_is_thin(
                        [s_.text for s_ in surviving])
                    log(f"worker: candidate {cid} post-drop thin check: "
                        f"{len(flagged)} of {len(sources)} source(s) dropped — "
                        f"{post_why}")
                    if post_thin:
                        report["post_drop_thin"] += 1
                        if unverified and not verified_answers:
                            # The unverified pool was left unread because the
                            # PRE-drop set looked adequate. It no longer is, and
                            # this is the pool's whole purpose — gate-2
                            # `uncertain` material that the band sweep showed is
                            # not uniformly junk. Read it now.
                            log(f"worker: candidate {cid} post-drop set is thin "
                                f"and {len(unverified)} unverified source(s) "
                                f"were left unread — running the verify pass now")
                            verified_answers, verify_sources = _run_verify_pass()
                        else:
                            # Nothing left to escalate to. Say so plainly rather
                            # than writing a record that reads as well-sourced:
                            # this is a coverage finding about the candidate, not
                            # a silent success.
                            log(f"worker: candidate {cid} post-drop set is thin "
                                f"and there is nothing left to escalate to "
                                f"({len(unverified)} unverified, verify pass "
                                f"{'already run' if verified_answers else 'unavailable'})"
                                f" — findings rest on {len(surviving)} source(s)")
                for problem in problems:
                    log(f"worker: candidate {cid} {problem}")
            report["extracted"] += 1
            report["extracted_batched" if batched else "extracted_single"] += 1

            # stage 7 — the ledger, written BEFORE claims are resolved (§9), and
            # claims then derived from it rather than taken from the model.
            claims = claims_json.get("claims", [])
            if verified_answers:
                # Merged here, after the main parse, so the verify pass's answers
                # go through exactly the same ledger and claim derivation as the
                # confirmed set's — one provenance path, not two.
                log(f"worker: candidate {cid} merging {len(verified_answers)} "
                    f"answer(s) from the verify pass")
                answers = list(answers) + verified_answers
                report["verify_answers_merged"] += len(verified_answers)
            if batched or verified_answers:
                # A retry re-derives the whole ledger for this candidate from the
                # same source set, so the old rows are not history, they are the
                # same findings written twice — `write_findings` inserts
                # unconditionally and has no unique key to collide on. Cleared
                # here rather than in `write_findings` because only the caller
                # knows the unit being replaced is the candidate; on a first run
                # this deletes nothing.
                stale = conn.execute("DELETE FROM finding WHERE candidate_id = ?",
                                     (int(cid),)).rowcount
                if stale:
                    log(f"worker: candidate {cid} cleared {stale} finding(s) from "
                        "a previous run before rewriting the ledger")
                report["findings_written"] += extract_mod.write_findings(
                    conn, int(cid), answers,
                    urls={s.source_id: s.url
                          for s in list(prompt_sources) + list(verify_sources)},
                    # chunk_ref -> paragraph text, from whichever block
                    # produced it — both buckets' `PromptSource.chunk_texts`
                    # are already in hand, so this is a free lookup, not a
                    # re-chunk (schema v5, migrate/m0005_finding_chunk_text.py).
                    chunk_texts={ref: text
                                 for s in list(prompt_sources) + list(verify_sources)
                                 for ref, text in zip(s.chunk_refs, s.chunk_texts)})
                claims, notes = extract_mod.claims_from_findings(answers)
                for note in notes:
                    log(f"worker: candidate {cid} {note}")
                # The batched schema no longer asks for `claims` (2026-09-14):
                # claims come from findings, so the model's own list was a second
                # source of truth for the same value and the prompt was paying
                # output tokens for it. The log stays, inverted in meaning — a
                # non-zero count here now means the model volunteered a key it
                # was not asked for, which is worth seeing, not routine.
                model_claims = len(claims_json.get("claims") or [])
                if model_claims:
                    log(f"worker: candidate {cid} discarded {model_claims} "
                        f"unasked-for model claims in favour of {len(claims)} "
                        f"derived from findings")

            # §11c's counters, per candidate. Counter 1 counts high-value
            # questions left UNFILLED (§7) and is readable as a signal about §11b.
            answered = {a.question_id for a in answers}
            unfilled = {q.id for q in REGISTRY.unfilled_questions(answered)}
            hv_open = sum(1 for q in _HIGH_VALUE_QUESTIONS if q in unfilled)
            unread = len(search_counters.get("unread_urls", []))
            seeds = {(e or {}).get("name", "") for e in claims_json.get("emits", [])}
            new_seeds = sum(1 for n in seeds if n and db.norm(n) != db.norm(name))
            report["hv_questions_open"] += hv_open
            report["unread_pool_urls"] += unread
            report["new_query_seeds"] += new_seeds
            log(f"worker: candidate {cid} §11c hv_open={hv_open} "
                f"unread_pool={unread} new_seeds={new_seeds}")

            # resolve — normalized match first, embedding shortlist as fallback.
            log(f"worker: candidate {cid} stage=resolve")
            decision = (_load_resolution(conn, cid, kind, name, log=log)
                        if resume else None)
            if decision is not None:
                report["resolve_reused"] += 1
                log(f"worker: candidate {cid} resolution reused ({decision.decision}"
                    f"), no encode + kNN")
            else:
                decision = resolve.resolve_entity(conn, corpus, kind, name, text or
                                                  (cand["evidence"] or ""))
                if persist_sources:
                    _save_resolution(conn, cid, decision)
            report[f"resolved_{decision.decision if decision.decision != 'shortlist_top' else 'shortlist'}"] += 1

            by = f"worker:{model_used}"
            if decision.decision == "ambiguous":
                why = json.dumps([{"id": i, "cosine": c} for i, c in decision.shortlist])
                db.record(conn, "candidate", cid, "resolve", None, why,
                          by="worker", why=decision.reason)
                _settle(cid, resolved_to=None, admitted=None, by="worker",
                       why=decision.reason, field="resolve")
                conn.commit()
                continue

            entity_id = _write_entity(conn, corpus, kind, name, decision,
                                      claims, by=by, log=log,
                                      predicted_depth=_predicted_depth(cand),
                                      depth_tier=depth_tier)
            if entity_id is None:
                # `_write_entity` could not write even a minimal row — give up on
                # this candidate rather than leave it endlessly re-selectable
                # (resolved_to stays NULL, which the CLI's queue treats as "not
                # yet processed") with the same failure recurring every retry.
                why = "entity write failed even for a minimal row"
                db.record(conn, "candidate", cid, "admitted", None, 0,
                          by="worker:write", why=why)
                _settle(cid, resolved_to=None, admitted=0, by="worker:write", why=why)
                conn.commit()
                continue
            report["cites_written"] += _write_cites(conn, kind, entity_id, answers,
                                                    by=by, log=log)
            _backfill_trigger_edge(conn, cand, kind, entity_id, by=by, log=log)
            _settle(cid, resolved_to=entity_id, admitted=1, by=by,
                   why="resolved and written", field="resolve")
            resolved_this_batch[(kind, db.norm(name))] = entity_id
            conn.commit()

            log(f"worker: candidate {cid} stage=emit")
            row = conn.execute("SELECT * FROM candidate WHERE id = ?", (int(cid),)).fetchone()
            emitted, edges = _emit(conn, row, claims_json, resolved_this_batch,
                                   log=log, depth_tier=depth_tier,
                                   problem_emission=problem_emission)
            report["candidates_emitted"] += emitted
            report["edges_written"] += edges
            conn.commit()
            log(f"worker: candidate {cid} stage=done")
        except Exception as e:
            conn.rollback()
            report["candidate_crashed"] = report.get("candidate_crashed", 0) + 1
            log(f"worker: candidate {cid} crashed, rolled back and skipping "
                f"(one candidate's failure must not lose the rest of the batch "
                f"-- 2026-09-18, exit-1 mid-batch with no traceback captured): "
                f"{e!r}\n{traceback.format_exc()}")
            continue

    return report


def _build_search_provider(search_url: str | None):
    """`search_url` -> a `ThrottledProvider` wrapping a live `SearxngProvider`,
    or `None` when the caller passed `None` (the `--no-search` CLI path).
    Pure/constructive only — no network call happens until `.search()` is
    first invoked by `worker/search_stage.py` — so this is safe to unit test
    without a running SearXNG instance."""
    if search_url is None:
        return None
    return ThrottledProvider(SearxngProvider(search_url))


def _select_ids_candidates(conn: sqlite3.Connection, ids: list[int], *,
                           force: bool, log=print) -> list[sqlite3.Row]:
    """`main()`'s `--ids [--force]` selection, factored out so it's testable
    without argparse/`open_store`. Missing ids are always logged and dropped.
    Already-resolved ids are logged and dropped too, UNLESS `force` — then
    they're logged as reprocessing and kept in. `run_batch`/`resolve.
    resolve_entity` match the candidate's name against the entity already on
    disk, so a forced rerun refreshes that entity's claims rather than
    minting a duplicate — this function only decides which rows go through,
    not what happens once they do."""
    placeholders = ", ".join("?" for _ in ids)
    candidates = conn.execute(
        f"SELECT * FROM candidate WHERE id IN ({placeholders})", ids).fetchall()
    found = {int(c["id"]) for c in candidates}
    for missing in set(ids) - found:
        log(f"worker: --ids {missing} not found, skipping")
    already = [c for c in candidates if c["resolved_to"] is not None]
    if force:
        for c in already:
            log(f"worker: --ids {c['id']} ({c['name']!r}) already "
                f"resolved to {c['resolved_to']}, reprocessing (--force)")
        return candidates
    for c in already:
        log(f"worker: --ids {c['id']} ({c['name']!r}) already resolved "
            f"to {c['resolved_to']}, skipping")
    return [c for c in candidates if c["resolved_to"] is None]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_store_args(ap)
    ap.add_argument("--limit", type=int, default=50,
                    help="stopgap queue: candidates already admitted (by "
                         "step-5's not-yet-built scheduler) but not yet "
                         "resolved. Real admission control is build-order step 5. "
                         "Ignored when --ids is given.")
    ap.add_argument("--ids", default=None,
                    help="comma-separated candidate ids to run instead of the "
                         "oldest-first --limit queue — e.g. a caller (the /worker "
                         "portal page) picked specific rows. Runs exactly these, "
                         "regardless of admitted; already-resolved ids are "
                         "skipped with a log line rather than reprocessed, "
                         "unless --force is also given.")
    ap.add_argument("--force", action="store_true",
                    help="with --ids, reprocess candidates that already have "
                         "resolved_to set instead of skipping them. Re-runs "
                         "extraction and re-resolves "
                         "against the existing entity — `worker/resolve.py` "
                         "matches the candidate's name to the entity already "
                         "on disk, so this refreshes that entity's claims "
                         "rather than minting a duplicate. The stored source "
                         "set is reused unless --no-resume is given too — so "
                         "pair the two when the first run's set was thin and "
                         "a search-cap escalation or a widened "
                         "FPH_MAX_SOURCES_* should now give a better one. "
                         "Ignored without "
                         "--ids — the --limit queue already excludes resolved "
                         "rows by construction.")
    ap.add_argument("--no-resume", action="store_true",
                    help="re-run fetch, search and gate 2 for candidates that "
                         "already have a stored source set, instead of "
                         "resuming at extraction from it. The default is to "
                         "resume: the search stage is ~17 throttled queries "
                         "plus a fetch each and gate 2 embeds every page, so "
                         "retrying a failed extraction is otherwise a half-"
                         "hour round trip to redo work whose inputs did not "
                         "change. Pass this when the inputs DID change — a "
                         "widened FPH_MAX_SOURCES_*, a fixed SearXNG "
                         "instance, a thin first set worth re-searching.")
    ap.add_argument("--search-url", default=config.SEARXNG_URL,
                    help="SearXNG base URL (track D). Default reads "
                         "FPH_SEARXNG_URL / " + config.SEARXNG_URL + ". Start "
                         "the instance first: engine/poc/searxng/run.sh start "
                         "— an unreachable URL raises rather than degrading.")
    ap.add_argument("--no-search", action="store_true",
                    help="skip track D entirely: fall back to run_batch's "
                         "seed-URL-only degrade (search_provider=None, §13) "
                         "instead of querying SearXNG.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    log = make_log(quiet=args.quiet)
    search_provider = _build_search_provider(
        None if args.no_search else args.search_url)
    conn = open_store(args, log=log)
    try:
        if args.ids:
            ids = [int(x) for x in args.ids.split(",") if x.strip()]
            candidates = _select_ids_candidates(conn, ids, force=args.force, log=log)
        else:
            candidates = conn.execute(
                "SELECT * FROM candidate WHERE admitted = 1 AND resolved_to IS NULL "
                "ORDER BY first_seen LIMIT ?", (args.limit,)).fetchall()
        report = run_batch(conn, Path(args.corpus), candidates, log=log,
                           search_provider=search_provider,
                           resume=not args.no_resume)
    finally:
        conn.close()
    log("worker:", ", ".join(f"{k}={v}" for k, v in report.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
