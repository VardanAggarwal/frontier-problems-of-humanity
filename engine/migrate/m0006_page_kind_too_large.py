"""Schema v5 -> v6: let `source.page_kind` accept `'too_large'`.

`engine/worker/fetch.py`'s `_pdf_too_large_state()` (2026-09-19, PDF text
extraction) tags an oversized PDF with `PageState(kind="too_large", ...)`.
`store/schema.sql` was updated the same day to allow it in `page_kind`'s
CHECK constraint, but a CHECK constraint is baked into the table at
creation time — editing schema.sql does not touch an existing database
file. Every live db still has the old constraint, so every oversized-PDF
fetch raises `sqlite3.IntegrityError` on the `source` upsert, mid-batch,
and `worker.py`'s per-candidate rollback drops the whole candidate (seen
repeatedly in engine/worker/runs/2026-09-18T21-49-40-546Z-64250.log:
candidates 691-696, 709, ...).

SQLite has no `ALTER TABLE ... ALTER CONSTRAINT`, so this rebuilds `source`
under a temporary name, copies every row across (the new CHECK is a
superset of the old, so no existing row can violate it), then swaps it in
under the original name — the standard SQLite "12-step" table rebuild,
trimmed to what this schema needs (no rows to re-point via foreign keys
into `source` need to change; `canonical_of` and `candidate_source.source_id`
still resolve to the same `source.id` values afterward).

Run as:
    python -m migrate.m0006_page_kind_too_large <db-path>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

TARGET_VERSION = "6"

NEW_SOURCE_DDL = """
CREATE TABLE source_new (
  id            TEXT PRIMARY KEY,
  url           TEXT NOT NULL,
  url_canonical TEXT NOT NULL,
  title         TEXT,
  org           TEXT,
  year          INTEGER,
  lang          TEXT,
  kind          TEXT,
  simhash       TEXT,
  page_state    TEXT CHECK (page_state IS NULL OR page_state IN
                ('ok', 'thin', 'blocked', 'missing', 'empty')),
  page_kind     TEXT CHECK (page_kind IS NULL OR page_kind IN
                ('js', 'cookies', 'bot', 'forbidden', 'login', 'missing', 'shell',
                 'too_large')),
  words         INTEGER,
  http_status   INTEGER,
  fetched_at    TEXT,
  path          TEXT,
  canonical_of  TEXT REFERENCES source (id),
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def _accepts_too_large(conn: sqlite3.Connection) -> bool:
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='source'"
    ).fetchone()
    return bool(sql) and "too_large" in sql[0]


def migrate(conn: sqlite3.Connection) -> bool:
    """Apply the migration if not already applied. Returns True if it made
    any change, False if everything was already in place (idempotent)."""
    if _accepts_too_large(conn):
        changed = False
    else:
        conn.execute("PRAGMA foreign_keys = OFF")
        # `edge` has a trigger (edge_endpoints_ins) whose body references
        # `source` by name. Without this pragma, sqlite's RENAME TO tries to
        # rewrite that trigger's SQL in place and fails mid-flight because
        # the old `source` table is already gone by then ("no such table:
        # main.source"). legacy_alter_table makes RENAME a pure name swap,
        # leaving dependent trigger/view SQL untouched — safe here since the
        # trigger only ever refers to the table by its stable name `source`,
        # which exists again immediately after the rename below.
        conn.execute("PRAGMA legacy_alter_table = ON")
        conn.execute(NEW_SOURCE_DDL)
        conn.execute(
            "INSERT INTO source_new SELECT id, url, url_canonical, title, org, "
            "year, lang, kind, simhash, page_state, page_kind, words, "
            "http_status, fetched_at, path, canonical_of, created_at FROM source"
        )
        conn.execute("DROP TABLE source")
        conn.execute("ALTER TABLE source_new RENAME TO source")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute(
            "CREATE UNIQUE INDEX source_canonical_ix ON source (url_canonical)")
        conn.execute(
            "CREATE INDEX source_dup_ix ON source (canonical_of) "
            "WHERE canonical_of IS NOT NULL")
        conn.execute("PRAGMA foreign_keys = ON")
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
        print("usage: python -m migrate.m0006_page_kind_too_large <db-path>",
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
