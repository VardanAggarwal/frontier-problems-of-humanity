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

from . import depth as depth_mod
from . import fetch as fetchmod
from . import gate1, gate2, llm, problem_emit, resolve
from .prompts import extract_prompt

# Track B (`04-worker-build-plan.md` §4): predict a depth tier for every
# actor mention at mint time, and apply the post-extraction ground-test
# verdict when writing claims. No call site exists yet to feed a live
# candidate's stored prediction back into `_write_entity` (that plumbing
# runs through `run_batch`, frozen for this track) — see `_write_entity`'s
# `predicted_depth` kwarg, which defaults to None and is inert until a
# caller supplies it. Degrades to: every actor keeps whatever `depth` the
# model itself claimed (today's behaviour) whenever the three ground-test
# inputs are absent or `WORKER_DEPTH_TIER` is turned off.
_DEPTH_TIER_ENABLED = os.getenv("WORKER_DEPTH_TIER", "1") != "0"

# Track A (`04-worker-build-plan.md` §4): an unresolvable `works_on` problem
# edge now mints a problem candidate instead of being dropped (see
# `_mint_or_resolve_problem`). `run_batch` is frozen for this track (§4
# reserves it for track E), so there is no call-site parameter to gate this
# on; an env var is the switch instead, defaulting ON now that the track has
# landed. Per §4's "land the fallback before the code that degrades to it":
# setting `WORKER_PROBLEM_EMISSION=0` reverts `_emit` to today's behaviour
# (unresolvable problem edge silently dropped) with no code change.
_PROBLEM_EMISSION_ENABLED = os.getenv("WORKER_PROBLEM_EMISSION", "1") != "0"

# Columns claims may write directly (db.py's _JSON_COLUMNS mirrors these for
# problem/actor). Anything else in a claim's `field` must be a `tag:` /
# `ask:` / `channel:` convention (prompts.py docstring) or it is logged and
# dropped rather than crashing the batch.
_COLUMNS = {
    "problem": {"title", "one_line", "status", "geography", "needs_legs",
                "gap_note", "doc", "updated"},
    "actor": {"title", "type", "legs", "depth", "lifecycle", "lifecycle_as_of",
              "ecosystem_role", "affected_led", "representation_unit", "stance",
              "geography", "contact_route", "followed", "followed_date",
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
                  by: str, log=print, predicted_depth: str | None = None
                  ) -> str | None:
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

    if kind == "actor" and _DEPTH_TIER_ENABLED and any(
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
    # and emitted, never gated here.
    signals = problem_emit.signals_from_edge(edge)
    conn.execute(
        "INSERT INTO candidate (kind, name, url, discovered_via, evidence) "
        "VALUES (?, ?, NULL, ?, ?)",
        ("problem", dst_name, f"worker:{source_candidate['id']}",
         json.dumps({"hint": edge.get("evidence", ""), "signals": signals,
                    "from_candidate": source_candidate["id"]})))
    return None, True


def _emit(conn: sqlite3.Connection, source_candidate: sqlite3.Row,
         claims: dict, resolved_this_batch: dict[tuple[str, str], str],
         *, log=print) -> tuple[int, int]:
    """Write `emits` as fresh, unprocessed candidates and `edges` as graph
    links where the destination already resolves — never both for the same
    name, and never a recursive call into `run_batch` (module docstring).

    Track A: a `works_on` edge naming a problem that doesn't resolve is no
    longer just dropped — `_mint_or_resolve_problem` either resolves it
    (existing/shortlist match), escalates it (ambiguous), or mints it as a
    fresh problem candidate here, same as `emits` does for named actors."""
    emitted = 0
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
        if ekind == "actor" and _DEPTH_TIER_ENABLED:
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
        if dst_id is None and dst_kind == "problem" and _PROBLEM_EMISSION_ENABLED:
            # Track A: unlike actors (whose `emits` loop above already mints
            # a candidate for any mentioned name), nothing upstream mints a
            # problem candidate from a `works_on` destination — this is the
            # only place one turns into a candidate at all, per
            # `03-worker.md` §10.
            dst_id, minted = _mint_or_resolve_problem(conn, source_candidate,
                                                      e, log=log)
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


def run_batch(conn: sqlite3.Connection, corpus: Path, candidates: list[sqlite3.Row],
             *, log=print) -> dict:
    report = {
        "gate0_collapsed": 0, "gate1_kept": 0, "gate1_rejected": 0, "fetched": 0,
        "gate2_confirmed": 0, "gate2_uncertain": 0, "gate2_mismatch": 0,
        "extracted": 0, "resolved_exact": 0, "resolved_shortlist": 0,
        "resolved_ambiguous": 0, "resolved_new": 0, "edges_written": 0,
        "candidates_emitted": 0, "cost": 0.0,
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
        if cand["url"]:
            result = fetchmod.fetch(conn, corpus, cand["url"])
            report["fetched"] += 1
            text = result.text or ""

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
                if verdict == "uncertain":
                    log(f"worker: candidate {cid} gate2 uncertain — {note}")

        # claims — the one paid call in the loop (§7 tier 4).
        system, prompt = extract_prompt(kind, name, text)
        try:
            result = llm.call(prompt, system=system, tier="judgment", max_tokens=4096)
        except llm.LLMError as e:
            log(f"worker: candidate {cid} extraction failed, skipping: {e}")
            continue
        report["cost"] += result.get("cost", 0.0)
        claims_json = result.get("json")
        if not isinstance(claims_json, dict) or not all(
                isinstance(claims_json.get(k), list)
                for k in ("claims", "emits", "edges")):
            # `.get` on a non-dict (the model returned a bare array, or
            # `parse_json` failed and left `json` unset) would crash the
            # batch — a malformed shape is a logged skip, same discipline as
            # gate1's non-object guard.
            log(f"worker: candidate {cid} malformed extraction JSON "
                f"({type(claims_json).__name__}), skipping")
            continue
        report["extracted"] += 1

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
                                  claims_json["claims"], by=by, log=log)
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
        emitted, edges = _emit(conn, row, claims_json, resolved_this_batch, log=log)
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
