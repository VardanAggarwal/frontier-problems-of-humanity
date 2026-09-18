"""Schema v3 -> v4: the extraction resume point
(`05-worker-optimisations.md`, "Handling failures instead starting from
scratch" — "Extraction fails, restart -> another half an hour gone").

Adds the two things `worker/worker.py:run_batch` needs to re-enter a
candidate at the extraction stage instead of at the fetch stage:

- `candidate_source` — which sources belonged to a candidate's set, with
  `origin`/`route`/`verdict` from `search/confirm_policy.py`. The page text
  is NOT stored: `source.path` has always held it on disk, and a cache hit
  in `worker/fetch.py` already reads it back. What was missing was the
  membership and gate 2's verdict, both of which only ever lived in
  `run_batch`'s frame.
- `candidate_prompt` — the assembled `[Sn]` blocks per bucket. Without it a
  resume still pays `worker/extract.py:assemble`, which chunks every source
  and encodes every chunk against every retrieval question — more embedding
  work than gate 2 does, and the dominant local cost once the network is
  out of the picture.
- `candidate_resolution` — the resolver's verdict, so an escalated
  (`ambiguous`) candidate stops paying a fresh encode + kNN on every run to
  reach the same verdict. Reuse is guarded, not blind — see the table's note
  in `store/schema.sql`.
- `candidate.searched_at` — the resume flag. It distinguishes "searched,
  and the set is legitimately empty" from "never searched", which a row
  count alone cannot.

No backfill, same reasoning as `migrate/m0002_finding_provenance.py`: the
membership of an already-run candidate's source set was never written
anywhere, so it cannot be recovered. Candidates processed before this
migration simply have `searched_at IS NULL` and search from scratch once
more, after which they resume like any other.

Run as:
    python -m migrate.m0004_candidate_source <db-path>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

TARGET_VERSION = "4"

CANDIDATE_SOURCE_DDL = """
CREATE TABLE candidate_source (
  candidate_id INTEGER NOT NULL REFERENCES candidate (id),
  source_id    TEXT NOT NULL REFERENCES source (id),
  url          TEXT NOT NULL,
  origin       TEXT NOT NULL CHECK (origin IN ('seed', 'search')),
  route        TEXT NOT NULL CHECK (route IN ('prompt', 'verify')),
  verdict      TEXT CHECK (verdict IS NULL OR verdict IN ('confirmed', 'uncertain')),
  recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (candidate_id, source_id)
) WITHOUT ROWID
"""

CANDIDATE_PROMPT_DDL = """
CREATE TABLE candidate_prompt (
  candidate_id INTEGER NOT NULL REFERENCES candidate (id),
  bucket       TEXT NOT NULL CHECK (bucket IN ('prompt', 'verify')),
  blocks       TEXT NOT NULL,
  coverage     TEXT,
  assembled_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (candidate_id, bucket)
) WITHOUT ROWID
"""

CANDIDATE_RESOLUTION_DDL = """
CREATE TABLE candidate_resolution (
  candidate_id INTEGER PRIMARY KEY REFERENCES candidate (id),
  decision     TEXT NOT NULL CHECK (decision IN
               ('exact', 'shortlist_top', 'ambiguous', 'new')),
  entity_id    TEXT,
  shortlist    TEXT,
  reason       TEXT,
  resolved_at  TEXT NOT NULL DEFAULT (datetime('now'))
) WITHOUT ROWID
"""


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def migrate(conn: sqlite3.Connection) -> bool:
    """Apply the migration if not already applied. Returns True if it made
    any change, False if everything was already in place (idempotent)."""
    changed = False

    if not _has_table(conn, "candidate_source"):
        conn.execute(CANDIDATE_SOURCE_DDL)
        changed = True

    if not _has_table(conn, "candidate_prompt"):
        conn.execute(CANDIDATE_PROMPT_DDL)
        changed = True

    if not _has_table(conn, "candidate_resolution"):
        conn.execute(CANDIDATE_RESOLUTION_DDL)
        changed = True

    if not _has_column(conn, "candidate", "searched_at"):
        conn.execute("ALTER TABLE candidate ADD COLUMN searched_at TEXT")
        changed = True

    current = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    current_version = current[0] if current else None
    if current_version != TARGET_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (TARGET_VERSION,),
        )
        changed = True

    conn.commit()
    return changed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m migrate.m0004_candidate_source <db-path>",
              file=sys.stderr)
        return 2

    db_path = Path(argv[1])
    if not db_path.exists():
        print(f"no such file: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        changed = migrate(conn)
    finally:
        conn.close()

    print("migrated" if changed else "already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
