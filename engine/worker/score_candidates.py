"""Priority scoring for the candidate queue (`candidate.admitted IS NULL`).

Standalone and exploratory: NOT wired into the worker/admission loop yet
(that integration is deferred). Computes `priority = 0.40*G + 0.25*D +
0.20*F + 0.15*S` for every unadmitted candidate and writes it to
`candidate.score`, with one `event` row per write so the number is
explainable later rather than a bare float.

Why these four terms, and why these weights:

- **G (gap coverage, 0.40 — the largest weight)** is the only term that asks
  "does the world actually need this," so it dominates. It walks the
  `discovered_via` chain (`worker:<parent_candidate_id>` or a chain-ending
  `human:...`/other origin) up to 10 hops looking for a resolved ancestor,
  then reads `problem_coverage.uncovered_count` for that problem
  (uncovered_count / 4.0, clamped to [0,1]; 4 is the leg count in
  `problem_leg`). Per schema.sql's own convention (`problem.needs_legs IS
  NULL` = "not yet judged", never coerced to zero), any case where the chain
  doesn't resolve in time, resolves to an actor rather than a problem, or the
  destination problem has no `needs_legs` judged yet, defaults G to a NEUTRAL
  0.5 rather than 0.0. Zeroing the unresolved majority would rank the whole
  queue by chance lineage instead of gap.

- **D (discovery signal, 0.25)** asks how many independent routes found the
  same thing. log1p(distinct `discovered_via` values across every member of
  the candidate's REAL dedup cluster), normalized by the pool max for that
  kind, then +0.15 flat if the candidate's OWN discovery was a human
  (`discovered_via` starts with `human:`) — a person naming something is a
  stronger prior than one more autonomous worker branch landing on it.

  The cluster comes from `dedup_candidates.compute_clusters`, imported, not
  re-derived. This term used to group by `resolve._slugify(name)` as a cheap
  stand-in, written that way only because that module was being repaired
  concurrently and could not be depended on. Keeping the stand-in now would
  leave two duplicate detectors in one pipeline, and the one that is not the
  CLI's is the one nobody notices drifting. The slug proxy was also strictly
  weaker: it could only ever see exact name matches, so `FCI` and `Food
  Corporation of India (FCI)` corroborated nothing, and the real tier-2
  embedding pass is what recovers those.

- **The pool is cluster REPRESENTATIVES, not every row.** A duplicate does
  not get its own score. Ranking each copy separately is what put `Food
  Corporation of India (FCI)` at #3 and #4 and `Ministry of Jal Shakti` at
  #7 and #8 in the first dry-run — the queue's top slots spent on one entity
  discovered twice. Note this has to be recomputed live: `dedup_candidates`
  has only ever run with `--dry-run`, so `candidate.dup_of` is still NULL
  throughout the store, and a `WHERE dup_of IS NULL` pool would quietly be
  the un-deduped pool. The cost is that scoring now pays for dedup's tier-2
  encode on every run.

- **F (freshness, 0.20)** is exp(-age_days / 60): a candidate seen last week
  outranks a stale one at equal G/D/S, but the 60-day half-life-ish decay is
  gentle enough that a good old candidate doesn't vanish under a mediocre new
  one. Already bounded to (0, 1], no further normalization.

- **S (scale/severity proxy, 0.15 — intentionally the weakest term)** is a
  regex scan of `evidence` for national/crore/ministry-class vs
  village/panchayat-class tokens. This is a placeholder for real scale data
  (e.g. an `actor.scale_metric`-shaped field once one exists on candidates)
  and should be the first term replaced, not tuned further — hence the
  lowest weight and the flattest prior (0.5) when evidence is absent, mixed,
  or silent on scale.

Run `--dry-run` first: it computes and prints without touching the store.
"""
from __future__ import annotations

import argparse
import math
import re
import sqlite3
import sys
from datetime import datetime, timezone

from embed.guard import add_store_args, open_store
from store import db

from .dedup_candidates import KINDS, Cluster, compute_clusters

MAX_HOPS = 10
MAX_LEGS = 4.0

_STRONG_SCALE = re.compile(
    r"national|central|ministry|federal|nationwide|state-wide|crore|million",
    re.IGNORECASE,
)
_LOCAL_SCALE = re.compile(
    r"local|village|district|panchayat|block-level", re.IGNORECASE
)


def _parse_dt(text: str | None):
    if not text:
        return None
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def compute_gap(conn: sqlite3.Connection, candidates_by_id: dict) -> dict[int, float]:
    """G per candidate id: uncovered_count / 4.0 at the resolved ancestor
    problem, clamped [0,1]; 0.5 (neutral, not zero) whenever the chain
    doesn't cleanly resolve to a judged problem within MAX_HOPS."""
    out: dict[int, float] = {}
    # cache resolved_to lookups against problem_coverage
    coverage_cache: dict[str, float | None] = {}

    def coverage_for(problem_id: str) -> float | None:
        if problem_id in coverage_cache:
            return coverage_cache[problem_id]
        row = conn.execute(
            "SELECT uncovered_count FROM problem_coverage WHERE problem_id = ?",
            (problem_id,),
        ).fetchone()
        val = None if row is None else min(1.0, max(0.0, row[0] / MAX_LEGS))
        coverage_cache[problem_id] = val
        return val

    for cid, cand in candidates_by_id.items():
        seen = set()
        cur = cand
        g = 0.5  # default: neutral, not zero
        for _hop in range(MAX_HOPS):
            if cur is None or cur["id"] in seen:
                break
            seen.add(cur["id"])
            resolved_to = cur["resolved_to"]
            if resolved_to is not None:
                if cur["kind"] == "problem":
                    cov = coverage_for(resolved_to)
                    if cov is not None:
                        g = cov
                # kind == "actor" (or any other) -> leave g at neutral 0.5
                break
            via = cur["discovered_via"] or ""
            if via.startswith("worker:"):
                parent_id_str = via[len("worker:"):].strip()
                if not parent_id_str.isdigit():
                    break
                parent = candidates_by_id.get(int(parent_id_str))
                if parent is None:
                    row = conn.execute(
                        "SELECT id, kind, discovered_via, resolved_to FROM candidate "
                        "WHERE id = ?", (int(parent_id_str),),
                    ).fetchone()
                    parent = dict(row) if row else None
                cur = parent
            else:
                break  # human:... or anything else — chain ends unresolved
        out[cid] = g
    return out


def compute_discovery(clusters: list[Cluster],
                      rows_by_id: dict[int, dict]) -> dict[int, float]:
    """D per cluster representative. D_raw = log1p(number of DISTINCT
    `discovered_via` values across the cluster's members), normalized by the
    max D_raw among that kind's clusters. +0.15 flat if the representative's
    own discovered_via is human:-sourced, then clamped to [0,1].

    Counting distinct routes, not members, is the point: five rows all
    written by one worker branch is one discovery repeated, while two rows
    from two branches is corroboration. Members missing from `rows_by_id`
    (a row that changed under us between the two queries) are skipped rather
    than counted as an empty route."""
    raw: dict[int, float] = {}
    max_by_kind: dict[str, float] = {}
    for c in clusters:
        routes = {rows_by_id[m]["discovered_via"] or ""
                  for m in c.members if m in rows_by_id}
        d_raw = math.log1p(len(routes))
        raw[c.representative] = d_raw
        max_by_kind[c.kind] = max(max_by_kind.get(c.kind, 0.0), d_raw)

    out: dict[int, float] = {}
    for c in clusters:
        denom = max_by_kind.get(c.kind, 0.0)
        d = (raw[c.representative] / denom) if denom > 0 else 0.0
        rep = rows_by_id.get(c.representative)
        via = (rep or {}).get("discovered_via") or ""
        if via.startswith("human:"):
            d += 0.15
        out[c.representative] = min(1.0, max(0.0, d))
    return out


def compute_freshness(row: dict, now: datetime) -> float:
    seen = _parse_dt(row["first_seen"])
    if seen is None:
        return 0.5  # shouldn't happen (first_seen is NOT NULL) but stay neutral
    age_days = max(0.0, (now - seen).total_seconds() / 86400.0)
    return math.exp(-age_days / 60.0)


def compute_scale(row: dict) -> float:
    evidence = row["evidence"] or ""
    strong = bool(_STRONG_SCALE.search(evidence))
    local = bool(_LOCAL_SCALE.search(evidence))
    if strong and not local:
        return 1.0
    if local and not strong:
        return 0.0
    return 0.5


def score_all(conn: sqlite3.Connection, *, log=None) -> list[dict]:
    """Returns one dict per SCORED candidate — one per dedup cluster, the
    representative — with id, kind, name, score, the G/D/F/S breakdown and
    the cluster size behind it, for both the write path and --dry-run.

    The full unadmitted pool is still read, because G walks parent chains
    through it and D counts routes across every member of a cluster; only
    the representative is scored and written."""
    rows = [dict(r) for r in conn.execute(
        "SELECT id, kind, name, discovered_via, evidence, first_seen, "
        "resolved_to, score AS old_score FROM candidate "
        "WHERE admitted IS NULL").fetchall()]
    if not rows:
        return []

    by_id = {r["id"]: r for r in rows}
    clusters: list[Cluster] = []
    for kind in KINDS:
        clusters.extend(compute_clusters(conn, kind))

    g_by_id = compute_gap(conn, by_id)
    d_by_rep = compute_discovery(clusters, by_id)
    now = datetime.now(timezone.utc)

    out = []
    for c in clusters:
        r = by_id.get(c.representative)
        if r is None:
            continue      # already admitted between the two reads
        g = g_by_id[r["id"]]
        d = d_by_rep[c.representative]
        f = compute_freshness(r, now)
        s = compute_scale(r)
        priority = 0.40 * g + 0.25 * d + 0.20 * f + 0.15 * s
        out.append({
            "id": r["id"], "kind": r["kind"], "name": r["name"],
            "old_score": r["old_score"], "score": priority,
            "g": g, "d": d, "f": f, "s": s,
            "cluster_size": len(c.members),
        })

    # Anything unadmitted that no cluster claimed already has `dup_of` set
    # (dedup's pool excludes those), so it is a known duplicate and is
    # deliberately left unscored — but say so rather than let the count
    # quietly shrink.
    skipped = len(rows) - sum(len(c.members) for c in clusters)
    if skipped and log:
        log(f"score_candidates: {skipped} unadmitted row(s) already carry "
            f"dup_of and were not scored")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_store_args(ap)
    ap.add_argument("--dry-run", action="store_true",
                     help="compute and print scores; do not UPDATE or write "
                          "event rows or commit.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    log = (lambda *a, **k: None) if args.quiet else print
    conn = open_store(args, log=log)
    try:
        results = score_all(conn, log=log)
        if not results:
            log("score_candidates: nothing to score (no admitted IS NULL rows)")
            return 0

        if args.dry_run:
            for r in sorted(results, key=lambda x: -x["score"]):
                why = (f"G={r['g']:.2f} D={r['d']:.2f} F={r['f']:.2f} "
                       f"S={r['s']:.2f}")
                size = (f" x{r['cluster_size']}" if r["cluster_size"] > 1
                        else "   ")
                log(f"[dry-run] #{r['id']:>5} ({r['kind']:>7}){size} "
                    f"{r['score']:.4f}  {why}  {r['name']}")
            log(f"score_candidates: dry-run, {len(results)} cluster "
                "representatives scored, nothing written")
            return 0

        for r in results:
            why = f"G={r['g']:.2f} D={r['d']:.2f} F={r['f']:.2f} S={r['s']:.2f}"
            conn.execute("UPDATE candidate SET score = ? WHERE id = ?",
                         (r["score"], r["id"]))
            db.record(conn, "candidate", str(r["id"]), "score",
                      r["old_score"], r["score"], by="score_candidates",
                      why=why)
        conn.commit()
        log(f"score_candidates: wrote scores for {len(results)} candidates")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
