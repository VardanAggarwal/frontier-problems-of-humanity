"""Schema v2 -> v3: give `finding` the `reason` column store/schema.sql:308
promises — the model's one-clause justification for a closed-enum
classification answer (`worker/extract_types.py`'s `Answer.reason`,
parsed in `worker/prompts.py`), which `worker/extract.py:write_findings()`
was generating and parsing but silently dropping before it reached the DB.

Adds one nullable column to `finding`:

- `reason TEXT` — why this value over a neighbouring one, e.g. why `onset`
  is `chronic` and not `latent`. None outside closed-enum classification
  questions.

No backfill, same reasoning as `migrate/m0002_finding_provenance.py`:
findings written before this column existed simply come back NULL for
`reason` — there is no way to recover a justification that was never
asked for at write time.

Run as:
    python -m migrate.m0003_finding_reason <db-path>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

TARGET_VERSION = "3"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def migrate(conn: sqlite3.Connection) -> bool:
    """Apply the migration if not already applied. Returns True if it made
    any change, False if everything was already in place (idempotent)."""
    changed = False

    if not _has_column(conn, "finding", "reason"):
        conn.execute("ALTER TABLE finding ADD COLUMN reason TEXT")
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
        print(f"usage: python -m migrate.m0003_finding_reason <db-path>",
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
