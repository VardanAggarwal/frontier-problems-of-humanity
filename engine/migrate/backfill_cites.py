"""One-off: derive `cites` edges for candidates the worker already resolved
before `worker.py:_write_cites` existed. Same gap `_write_cites` closes going
forward — `finding.source_id` was durable but nothing turned it into a graph
edge — this is that fix applied retroactively to `problems/graph.db`'s
existing rows rather than only to future worker runs.

Usage:
    python -m migrate.backfill_cites [--dry-run] [--db problems/graph.db]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from store import db

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "problems" / "graph.db"
BY = "migrate:backfill_cites"


def backfill(conn: sqlite3.Connection, *, dry_run: bool = False, log=print) -> int:
    rows = conn.execute(
        "SELECT id, kind, resolved_to FROM candidate WHERE resolved_to IS NOT NULL"
    ).fetchall()
    written = 0
    for cid, kind, entity_id in rows:
        source_ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT source_id FROM finding WHERE candidate_id = ? "
            "AND source_id IS NOT NULL", (cid,))]
        for source_id in source_ids:
            if dry_run:
                log(f"would link {kind}/{entity_id} -cites-> source/{source_id} "
                    f"(candidate {cid})")
                written += 1
                continue
            try:
                db.link(conn, (kind, entity_id), "cites", ("source", source_id), by=BY)
                written += 1
            except sqlite3.IntegrityError as e:
                log(f"candidate {cid}: {kind}/{entity_id} -> source/{source_id} "
                    f"rejected: {e}")
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
    print(f"backfill_cites: {n} edge(s) {'would be ' if args.dry_run else ''}written")


if __name__ == "__main__":
    main()
