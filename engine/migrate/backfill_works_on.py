"""One-off: backfill `works_on` edges for already-promoted actors whose
originating candidate predates `worker.py`'s implicit-works_on synthesis
(commit e2e95d0, 2026-09-19, "Synthesize works_on edges for actors named
only in emits") — same gap `backfill_cites.py` closes for `cites` edges,
applied to `works_on` instead.

`jj-spices`/`niehs`/`bfsa` (minted 2026-09-18 21:42, from problem candidate
743 "Lead contamination in turmeric and spices") are the concrete case that
motivated this: their `candidate.evidence` carries none of the
`from_kind`/`from_id`/`edge_kind` trigger-edge fields the CURRENT code
stamps at mint time, because they were minted the day before that code
existed. `worker.py:_backfill_trigger_edge` only ever reads what's already
sitting in `evidence` — it has no way to retroactively derive a chain a
stale candidate was never given. This migration re-derives it instead, by
walking `from_candidate` from each affected actor's OWN candidate row — the
exact same walk `worker.worker._ancestor_problem` already does for the
actor-discovers-actor case (`raghubar-das`/`saryu-roy`), reused here for
"actor emitted directly by a problem" too. A stale candidate's chain is
just as walkable as a live one's; only the *live write path* stopped
capturing it, not the data the walk needs.

Idempotent and additive only: an actor that already has at least one
`works_on` edge is left alone (this fills gaps, it does not re-derive or
overwrite anything a live run already got right).

Usage:
    python -m migrate.backfill_works_on [--dry-run] [--db problems/graph.db]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from store import db
from worker.worker import _ancestor_problem

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "problems" / "graph.db"
BY = "migrate:backfill_works_on"


def backfill(conn: sqlite3.Connection, *, dry_run: bool = False, log=print) -> int:
    """For every actor with zero `works_on` edges, find the candidate that
    minted it and walk its ancestor chain to the nearest resolved problem —
    write the edge if one is found. Actors with no resolvable ancestor
    (e.g. a `registry` actor minted straight from a seed URL, never
    surfaced by any problem's extraction) are left as `gap: representation`
    candidates for a human pass, not guessed at here."""
    actors = conn.execute(
        "SELECT id FROM actor WHERE id NOT IN "
        "(SELECT src_id FROM edge WHERE src_kind = 'actor' AND kind = 'works_on')"
    ).fetchall()
    written = 0
    for (actor_id,) in actors:
        cand = conn.execute(
            "SELECT id, kind, resolved_to, evidence FROM candidate "
            "WHERE resolved_to = ? AND kind = 'actor' "
            "ORDER BY id LIMIT 1", (actor_id,)).fetchone()
        if cand is None:
            log(f"actor {actor_id}: no originating candidate row found — skipped")
            continue
        ancestor_id = _ancestor_problem(conn, cand, log=log)
        if ancestor_id is None:
            continue
        if dry_run:
            log(f"would link actor/{actor_id} -works_on-> problem/{ancestor_id} "
                f"(candidate {cand['id']})")
            written += 1
            continue
        try:
            db.link(conn, ("actor", actor_id), "works_on", ("problem", ancestor_id),
                    by=BY,
                    why="backfilled — originating candidate predates the "
                        "implicit-works_on synthesis fix (e2e95d0)")
            written += 1
        except sqlite3.IntegrityError as e:
            log(f"actor {actor_id} -> problem {ancestor_id} rejected: {e}")
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.connect(args.db, create=False)
    n = backfill(conn, dry_run=args.dry_run)
    if not args.dry_run:
        conn.commit()
    print(f"backfill_works_on: {n} edge(s) {'would be ' if args.dry_run else ''}written")


if __name__ == "__main__":
    main()
