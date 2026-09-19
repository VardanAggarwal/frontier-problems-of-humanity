"""Schema v6 -> v7: `actor.context` and `finding.kind`.

Two independent additive columns, bundled into one migration because
neither depends on the other and both are plain `ALTER TABLE ... ADD
COLUMN`s (no CHECK constraint involved, unlike m0006's `page_kind` — no
table rebuild needed here).

- `actor.context TEXT` — WHY this actor was worth minting, as opposed to
  `one_line`'s "what does it do" (`store/schema.sql`'s comment on the
  column has the full reasoning: a for-profit's `one_line` reads as
  generic company boilerplate and says nothing about why THIS actor
  showed up here). Backfilled from `candidate.evidence`'s `hint` at write
  time (`worker.py:_write_entity`) when the model's own `q0_relevance`
  answer (questions.yaml) doesn't produce one — never backfilled by this
  migration itself, since a candidate's `evidence` is looked up live by
  the write path, not reconstructed here from a resolved actor id.

- `finding.kind TEXT` — a templated claim_field's free-text remainder
  (`worker/extract_types.py`'s `Answer.kind`), added alongside the
  `ask:need:<kind>` / `ask:offer:<kind>` / `channel:<kind>` claim-routing
  fix in `worker/extract.py:claims_from_findings` (2026-09-19). Same
  audit-trail reasoning as `reason` (m0003_finding_reason.py).

No backfill for either column, same reasoning as m0002/m0003/m0005:
findings and actors written before this migration simply come back NULL
— there is nothing on disk to recover either value from after the fact.

Run as:
    python -m migrate.m0007_actor_context_and_finding_kind <db-path>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

TARGET_VERSION = "7"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def migrate(conn: sqlite3.Connection) -> bool:
    """Apply the migration if not already applied. Returns True if it made
    any change, False if everything was already in place (idempotent)."""
    changed = False

    if not _has_column(conn, "actor", "context"):
        conn.execute("ALTER TABLE actor ADD COLUMN context TEXT")
        changed = True

    if not _has_column(conn, "finding", "kind"):
        conn.execute("ALTER TABLE finding ADD COLUMN kind TEXT")
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
        print("usage: python -m migrate.m0007_actor_context_and_finding_kind "
              "<db-path>", file=sys.stderr)
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
