"""Schema v1 -> v2: give `finding` the provenance columns store/schema.sql:308
promises (03-worker.md §9, 04-worker-build-plan.md §5 "Two holes found by the
user" item 2).

Adds two nullable columns to `finding`:

- `source_id TEXT REFERENCES source (id)` — joins a finding to the fetched
  page, not just its URL string.
- `chunk_ref TEXT` — which passage produced the answer, format frozen by
  `text/chunk.py:93` (`chunk_ref`) as f"{source_id}:{ordinal}"; not
  reconstructed here, just stored.

No backfill: `finding` has 0 rows in the live DB at the time this migration
was written. If that stops being true before this runs, the added columns
still come back NULL for every pre-existing row — which is correct, since
there is no way to recover which source/chunk answered a finding written
before this column existed.

Empirical note on the "SQLite can't add an FK via ALTER TABLE" folklore:
tested directly against this sqlite3 build (3.53.2, bundled with the project
venv's Python) — `ALTER TABLE finding ADD COLUMN source_id TEXT REFERENCES
source (id)` DOES record the REFERENCES clause: it shows up verbatim in
`sqlite_master.sql` for the table and in `PRAGMA foreign_key_list(finding)`,
and `PRAGMA foreign_keys = ON` enforces it on subsequent inserts (a bogus
source_id raises "FOREIGN KEY constraint failed"). Modern SQLite (3.25+,
tested here on 3.51/3.53) treats ADD COLUMN as legacy ALTER TABLE and simply
appends the column definition — including its REFERENCES clause — to the
stored CREATE TABLE text; it does not require the "12-step generalized ALTER
TABLE" recipe (new table + copy + drop + rename) that older folklore says is
necessary to add a foreign key. That recipe is still needed to add a
constraint that requires rewriting existing rows (e.g. NOT NULL without a
default), which is not the case here since both columns are nullable.

Run as:
    python -m migrate.m0002_finding_provenance <db-path>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

TARGET_VERSION = "2"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def migrate(conn: sqlite3.Connection) -> bool:
    """Apply the migration if not already applied. Returns True if it made
    any change, False if everything was already in place (idempotent)."""
    changed = False

    if not _has_column(conn, "finding", "source_id"):
        conn.execute(
            "ALTER TABLE finding ADD COLUMN source_id TEXT REFERENCES source (id)"
        )
        changed = True

    if not _has_column(conn, "finding", "chunk_ref"):
        conn.execute("ALTER TABLE finding ADD COLUMN chunk_ref TEXT")
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
        print(f"usage: python -m migrate.m0002_finding_provenance <db-path>",
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
