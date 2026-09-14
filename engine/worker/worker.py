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
from pathlib import Path

from embed.guard import add_store_args, open_store
from store import db
from text.preview import Preview, fetch_list, group

from search import confirm_policy
from search.confirm_policy import prompt_set_is_thin

from . import depth as depth_mod
from . import extract as extract_mod
from . import fetch as fetchmod
from . import gate1, gate2, llm, problem_emit, resolve, search_stage
from .extract_types import Answer, ConfirmedSource
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
            try:
                db.tag(conn, kind, entity_id, ns, value, by=by)
            except sqlite3.IntegrityError as e:
                log(f"worker: rejected tag claim {field}={value!r} on "
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
                             edge: dict, *, log=print, emits=()) -> tuple[str | None, bool]:
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
    # and emitted, never gated here. They are read off the matching `emits`
    # entry, not off this edge: §10 puts them on the emit and the prompt asks
    # there, so reading `edge["signals"]` yielded four Nones however well the
    # model cooperated.
    signals = problem_emit.signals_for_problem(emits, dst_name, db.norm)
    conn.execute(
        "INSERT INTO candidate (kind, name, url, discovered_via, evidence) "
        "VALUES (?, ?, NULL, ?, ?)",
        ("problem", dst_name, f"worker:{source_candidate['id']}",
         json.dumps({"hint": edge.get("evidence", ""), "signals": signals,
                    "from_candidate": source_candidate["id"]})))
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

    Track A: a `works_on` edge naming a problem that doesn't resolve is no
    longer just dropped — `_mint_or_resolve_problem` either resolves it
    (existing/shortlist match), escalates it (ambiguous), or mints it as a
    fresh problem candidate here, same as `emits` does for named actors."""
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
            # The other mint route (`_mint_or_resolve_problem`, from a
            # `works_on` edge) has always written a `signals` key and this one
            # never did, so the orchestrator's payload shape depended on which
            # route happened to mint the candidate. Both write it now.
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
        emitted += 1

    edges_written = 0
    for e in claims.get("edges", []) or []:
        dst_kind, dst_name = e.get("dst_kind"), e.get("dst_name")
        edge_kind = e.get("edge_kind")
        if dst_kind not in ("problem", "actor") or not dst_name or not edge_kind:
            continue
        dst_id = db.resolve(conn, dst_kind, dst_name)
        if dst_id is None:
            dst_id = resolved_this_batch.get((dst_kind, db.norm(dst_name)))
        if (dst_id is None and dst_kind == "problem" and problem_emission
                and db.norm(dst_name) in minted_problems):
            # Already minted by the emits loop above, with the signals the
            # prompt put there. Minting again would duplicate the candidate
            # and double-count `emitted`; the edge still can't be linked
            # (a candidate is not an entity), which is the same deferral the
            # `dst_id is None` case below has always taken.
            continue
        if dst_id is None and dst_kind == "problem" and problem_emission:
            # Track A: unlike actors (whose `emits` loop above already mints
            # a candidate for any mentioned name), nothing upstream mints a
            # problem candidate from a `works_on` destination — this is the
            # only place one turns into a candidate at all, per
            # `03-worker.md` §10.
            dst_id, minted = _mint_or_resolve_problem(
                conn, source_candidate, e, log=log,
                emits=claims.get("emits", []) or [])
            if minted:
                emitted += 1
        if dst_id is None:
            continue   # not yet an entity — the emits loop above, this
                       # candidate's own mint just above (deferred to a
                       # future batch), or a prior candidate is responsible
                       # for it turning into one; an `ambiguous` problem
                       # match is escalated instead, per §10's dedupe rule
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


def run_batch(conn: sqlite3.Connection, corpus: Path, candidates: list[sqlite3.Row],
             *, log=print, depth_tier: bool | None = None,
             problem_emission: bool | None = None, search_provider=None,
             max_sources: int | None = None) -> dict:
    """`search_provider=None` is track D's documented degrade (§13): the
    candidate's own URL as the single source, which is exactly what this
    loop did before track D existed. Pass a `search.provider` adapter to
    turn the search stage on.

    `depth_tier` / `problem_emission`: None takes the env-supplied module
    default. They are parameters rather than env switches because
    `04-worker-build-plan.md` §6 called the env vars a workaround for this
    function being frozen, and E6 is where that freeze lifts.
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
        "findings_written": 0, "extracted_batched": 0, "extracted_single": 0,
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
        "verify_pass_calls": 0, "verify_answers_merged": 0,
        "verify_about": 0, "verify_different": 0,
        "verify_unrelated": 0, "verify_insufficient": 0,
    }
    if not candidates:
        return report
    by_id = {str(c["id"]): c for c in candidates}

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
    items = [{"id": str(c["id"]), "kind": c["kind"], "name": c["name"],
             "snippet": c["evidence"] or "", "url": c["url"] or ""}
             for c in candidates if str(c["id"]) in survivors]
    decisions, gate1_cost = gate1.screen(items, log=log)
    report["cost"] += gate1_cost
    alive: list[str] = []
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

        # fetch — a bare name (no URL) skips straight to extraction with
        # empty text: a stub actor from a registry row legitimately has no
        # document yet, and that is not a reason to stop the pipeline.
        text = ""
        sources: list[ConfirmedSource] = []
        unverified: list = []
        if cand["url"]:
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
        if search_provider is not None:
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
                provider=search_provider,
                fetch=lambda url: fetchmod.fetch(conn, corpus, url),
                confirm=lambda n, ev, txt: gate2.confirm(conn, n, ev, txt),
                evidence=cand["evidence"] or "", seed_url=None,
                max_sources=max_sources, counters=search_counters,
                unverified=unverified, log=log)
                if s.source_id not in already)
            unverified[:] = [s for s in unverified if s.source_id not in already]

        # The verify pass (§6a). `unverified` holds gate-2 `uncertain` and
        # confirmed-but-thin sources — material that must not enter the main
        # prompt, but is not junk by default: the band sweep found a real
        # LinkedIn post and a real book page sitting in it, below four
        # wrong-entity pages. It buys a second call ONLY when the confirmed
        # set cannot carry the candidate alone, because the pass costs as
        # much as the call it supplements.
        verified_answers: list[Answer] = []
        verify_sources: list = []
        thin, why = prompt_set_is_thin([s.text for s in sources])
        log(f"worker: candidate {cid} verify-pass check: {why}")
        if thin and unverified:
            report["verify_pass_calls"] += 1
            v_sources, _ = extract_mod.assemble(
                unverified, REGISTRY.retrieval_questions(kind))
            if v_sources:
                v_system, v_prompt = verify_and_extract_prompt_batched(
                    kind, name, cand["evidence"] or "", v_sources)
                try:
                    v_result = llm.call(v_prompt, system=v_system,
                                        tier="judgment", max_tokens=4096)
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
                    verified_answers = v_answers
                    verify_sources = v_sources
        elif unverified:
            log(f"worker: candidate {cid} {len(unverified)} unverified "
                f"source(s) left unread — confirmed set was adequate")

        # claims — the one paid call in the loop (§7 tier 4). With sources in
        # hand it is §8's batched `[S1]…[Sn]` call over selected passages;
        # with none it is the original whole-text call, which is also §13's
        # degrade path when passage assembly yields nothing.
        prompt_sources, coverage = ([], {})
        if sources:
            prompt_sources, coverage = extract_mod.assemble(
                sources, REGISTRY.retrieval_questions(kind))
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
        try:
            result = llm.call(prompt, system=system, tier="judgment", max_tokens=4096)
        except llm.LLMError as e:
            log(f"worker: candidate {cid} extraction failed, skipping: {e}")
            continue
        report["cost"] += result.get("cost", 0.0)
        claims_json = result.get("json")

        answers: list[Answer] = []
        if batched and not isinstance(claims_json, dict):
            # §13's per-source fallback. PoC-2 measured it rescuing 1/1 parse
            # failures, and that one failure was NOT prompt-size-driven — it
            # fired at 4,082 chars while a larger response parsed clean — so
            # the retry is warranted by the observation, not by a size rule.
            log(f"worker: candidate {cid} batched parse failed, retrying "
                f"{len(prompt_sources)} sources one at a time (§13)")
            for src, sys_p, usr_p in retry_per_source(kind, name, prompt_sources):
                report["retry_per_source_calls"] += 1
                try:
                    one = llm.call(usr_p, system=sys_p, tier="judgment",
                                   max_tokens=4096)
                except llm.LLMError as e:
                    log(f"worker: candidate {cid} retry on {src.source_id} "
                        f"failed: {e}")
                    continue
                report["cost"] += one.get("cost", 0.0)
                got, problems = parse_answers(one.get("json"), [src._replace(label="S1")])
                for problem in problems:
                    log(f"worker: candidate {cid} retry {src.source_id}: {problem}")
                if got:
                    report["retry_per_source_rescued"] += 1
                    answers.extend(got)
            if not answers:
                log(f"worker: candidate {cid} malformed extraction JSON "
                    f"({type(claims_json).__name__}) and no source rescued it, "
                    "skipping")
                continue
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
            report["findings_written"] += extract_mod.write_findings(
                conn, int(cid), answers,
                urls={s.source_id: s.url
                      for s in list(prompt_sources) + list(verify_sources)})
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
        decision = resolve.resolve_entity(conn, corpus, kind, name, text or
                                          (cand["evidence"] or ""))
        report[f"resolved_{decision.decision if decision.decision != 'shortlist_top' else 'shortlist'}"] += 1

        by = f"worker:{result.get('model', '?')}"
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
        _settle(cid, resolved_to=entity_id, admitted=1, by=by,
               why="resolved and written", field="resolve")
        resolved_this_batch[(kind, db.norm(name))] = entity_id
        conn.commit()

        row = conn.execute("SELECT * FROM candidate WHERE id = ?", (int(cid),)).fetchone()
        emitted, edges = _emit(conn, row, claims_json, resolved_this_batch,
                               log=log, depth_tier=depth_tier,
                               problem_emission=problem_emission)
        report["candidates_emitted"] += emitted
        report["edges_written"] += edges
        conn.commit()

    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_store_args(ap)
    ap.add_argument("--limit", type=int, default=50,
                    help="stopgap queue: candidates already admitted (by "
                         "step-5's not-yet-built scheduler) but not yet "
                         "resolved. Real admission control is build-order step 5.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    log = (lambda *a, **k: None) if args.quiet else print
    conn = open_store(args, log=log)
    try:
        candidates = conn.execute(
            "SELECT * FROM candidate WHERE admitted = 1 AND resolved_to IS NULL "
            "ORDER BY first_seen LIMIT ?", (args.limit,)).fetchall()
        report = run_batch(conn, Path(args.corpus), candidates, log=log)
    finally:
        conn.close()
    log("worker:", ", ".join(f"{k}={v}" for k, v in report.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
