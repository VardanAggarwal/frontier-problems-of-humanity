"""One-off: backfill `finding.chunk_text` (schema v5,
`migrate/m0005_finding_chunk_text.py`) for findings written before that
column existed.

m0005 itself declares "no backfill, same reasoning as m0002" — but that
reasoning does not hold here the way it did for m0002's `source_id`/
`chunk_ref` or m0003's `reason`: those were never captured anywhere, so a
migration genuinely had nothing to recover. `chunk_text` is different.
`finding.chunk_ref` (`f"{source_id}:{ordinal}"`, `text/chunk.py:93`) and
`source.path` (the fetched page's cached text, still on disk) are both
already durable — the paragraph is reconstructible by re-running
`text/chunk.py:chunk()` against the same cached text, which is deterministic
for a given input (`chunk()`'s own docstring: "same text in, same ordinals
out"). So this is a real backfill, not a guess, PROVIDED chunking hasn't
changed since the finding was written (`CHUNK_TOKENS`, the encoder) — a
`chunk_ref` whose ordinal no longer exists in a fresh chunking is left NULL
rather than mis-attributed, exactly like an unresolvable marker at
extraction time.

Groups findings by `source_id` so each source's cached text is chunked once
(measured: 1003 findings backfillable, 150 distinct sources — re-chunking
per-finding would cost 6.7x more encoder passes for no benefit, since
`chunk()` loads the same tokenizer every call).

Usage:
    python -m migrate.backfill_chunk_text [--dry-run] [--db problems/graph.db]
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

from store import db
from text.chunk import chunk

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "problems" / "graph.db"


def backfill(conn: sqlite3.Connection, *, dry_run: bool = False, log=print,
             root: Path = ROOT) -> dict:
    """-> counters: written, no_source_id, no_path, file_missing,
    unparseable_ref, ordinal_out_of_range."""
    counters = {
        "written": 0, "no_source_id": 0, "no_path": 0, "file_missing": 0,
        "unparseable_ref": 0, "ordinal_out_of_range": 0,
    }

    rows = conn.execute(
        "SELECT id, source_id, chunk_ref FROM finding "
        "WHERE chunk_ref IS NOT NULL AND chunk_text IS NULL"
    ).fetchall()

    by_source: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for fid, source_id, chunk_ref_val in rows:
        if not source_id:
            counters["no_source_id"] += 1
            continue
        by_source[source_id].append((fid, chunk_ref_val))

    updates: list[tuple[str, int]] = []  # (chunk_text, finding_id)
    for source_id, findings in by_source.items():
        src = conn.execute(
            "SELECT path FROM source WHERE id = ?", (source_id,)
        ).fetchone()
        if not src or not src[0]:
            counters["no_path"] += len(findings)
            continue
        path = root / src[0]
        if not path.exists():
            counters["file_missing"] += len(findings)
            log(f"source {source_id}: cached file missing on disk: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = {c.ordinal: c.text for c in chunk(text, source_id=source_id)}
        for fid, chunk_ref_val in findings:
            try:
                sid, ordinal_s = chunk_ref_val.rsplit(":", 1)
                ordinal = int(ordinal_s)
            except (ValueError, AttributeError):
                counters["unparseable_ref"] += 1
                log(f"finding {fid}: unparseable chunk_ref {chunk_ref_val!r}")
                continue
            if sid != source_id or ordinal not in chunks:
                counters["ordinal_out_of_range"] += 1
                log(f"finding {fid}: chunk_ref {chunk_ref_val!r} does not resolve "
                    f"against a fresh chunking of source {source_id} "
                    f"({len(chunks)} chunk(s)) — left NULL")
                continue
            updates.append((chunks[ordinal], fid))

    if dry_run:
        counters["written"] = len(updates)
        return counters

    conn.executemany(
        "UPDATE finding SET chunk_text = ? WHERE id = ?", updates
    )
    counters["written"] = len(updates)
    return counters


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--root", default=str(ROOT),
                    help="base path source.path is relative to — override when "
                         "running against a checkout other than this script's own "
                         "(problems/private/sources/ is gitignored, so a worktree "
                         "has the DB but not the cached page text)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.connect(args.db, create=False)
    counters = backfill(conn, dry_run=args.dry_run, root=Path(args.root))
    if not args.dry_run:
        conn.commit()
    verb = "would write" if args.dry_run else "wrote"
    print(f"backfill_chunk_text: {verb} {counters['written']} chunk_text value(s)")
    for k, v in counters.items():
        if k != "written" and v:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
