"""Schema v4 -> v5: give `finding` the resolved paragraph text behind its
`chunk_ref`, so a reader (a leaf page, a generated doc) can show the evidence
a machine-extracted answer rests on without re-chunking `source.path` from
disk at read time.

Adds one nullable column to `finding`:

- `chunk_text TEXT` — the exact paragraph `chunk_ref` points at, taken
  verbatim from the `PromptSource.chunk_texts` already held in memory at
  extraction time (`worker/extract_types.py`). Resolving from a durable
  `chunk_ref` after the fact would mean re-running `text/chunk.py:chunk()`
  against the cached page text and hoping chunking stayed deterministic
  across any future tuning of `CHUNK_TOKENS` or the encoder — this column
  freezes the paragraph as extraction actually saw it, at zero extra cost,
  since the text is already assembled in the caller's hand
  (`worker/extract.py:write_findings`'s new `chunk_texts` argument).

No backfill, same reasoning as `migrate/m0002_finding_provenance.py`:
findings written before this column existed come back NULL for
`chunk_text` — nothing on disk lets it be recovered after the fact (a
chunk_ref alone does not pin which chunking pass produced it).

Run as:
    python -m migrate.m0005_finding_chunk_text <db-path>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

TARGET_VERSION = "5"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def migrate(conn: sqlite3.Connection) -> bool:
    """Apply the migration if not already applied. Returns True if it made
    any change, False if everything was already in place (idempotent)."""
    changed = False

    if not _has_column(conn, "finding", "chunk_text"):
        conn.execute("ALTER TABLE finding ADD COLUMN chunk_text TEXT")
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
        print(f"usage: python -m migrate.m0005_finding_chunk_text <db-path>",
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
