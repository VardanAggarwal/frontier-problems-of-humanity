"""Fill the vector index from the store. Re-runnable, incremental, one direction.

Same contract as `migrate/from_corpus.py`: it reads the store (and the prose on
disk the store points at) and writes only vectors. Nothing here edits a graph
row, so a bad run costs an encode pass and nothing else.

Incremental by `text_hash` — a second run with nothing changed encodes nothing
and never loads the encoder, because the hash is taken on the text `texts.py`
produced rather than on the token-truncated text that reached the model.
`--force` is for the case the hash cannot see: a change in the *rules* in
`texts.py`, where the text differs but the code that built it is what moved.

    python -m embed.backfill          # defaults are repo-anchored; any cwd
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from . import index, texts
from .guard import add_store_args, open_store
from .model import MODEL_NAME, encode, fit

ROWS = {
    "problem": "SELECT id, title, one_line, doc FROM problem ORDER BY id",
    "actor": "SELECT id, title, doc FROM actor WHERE depth <> 'excluded' ORDER BY id",
    "source": ("SELECT id, title, org, year, path FROM source "
               "WHERE canonical_of IS NULL ORDER BY id"),
}


def plan(conn: sqlite3.Connection, kind: str, corpus: Path, *, force: bool
         ) -> tuple[list[tuple[str, str]], int, int, set[str]]:
    """-> (work, fresh, empty, keep).

    `work` carries the text as `texts.py` built it, *not* token-fitted —
    fitting happens in `run`, on the rows that are actually going to be encoded.
    Doing it here meant a re-run with nothing to do still paid a full model load
    to tokenize 426 records and conclude that all of them were current.

    `keep` is every entity that should hold a vector at all, so the caller can
    prune the ones that should not. `ROWS` filters — `depth <> 'excluded'`,
    `canonical_of IS NULL` — are exclusions that happen *after* a first index,
    so without a prune pass the index answers for records the store has ruled
    out. A row with no text lands in neither `work` nor `keep`: it is not
    encodable, so any vector it still holds is also stale."""
    work, fresh, empty, keep = [], 0, 0, set()
    for row in conn.execute(ROWS[kind]).fetchall():
        text = texts.for_entity(kind, row, corpus)
        if not text:
            empty += 1
            continue
        keep.add(row["id"])
        if not force and not index.stale(conn, kind, row["id"], text):
            fresh += 1
            continue
        work.append((row["id"], text))
    return work, fresh, empty, keep


def run(conn: sqlite3.Connection, corpus: Path, *, kinds=index.KINDS,
        force: bool = False, batch_size: int = 32, log=print) -> dict:
    report: dict = {"model": MODEL_NAME, "kinds": {}}
    for kind in kinds:
        work, fresh, empty, keep = plan(conn, kind, corpus, force=force)
        dropped = index.prune(conn, kind, keep)
        conn.commit()
        report["kinds"][kind] = {"encoded": len(work), "fresh": fresh,
                                 "empty": empty, "dropped": len(dropped)}
        if dropped:
            log(f"{kind}: dropped {len(dropped)} no longer indexable "
                f"({', '.join(dropped[:5])}{'...' if len(dropped) > 5 else ''})")
        if not work:
            log(f"{kind}: nothing to do ({fresh} current, {empty} with no text)")
            continue
        started = time.time()
        for lo in range(0, len(work), batch_size):
            chunk = work[lo:lo + batch_size]
            fitted = [fit(t) for _, t in chunk]
            vectors = encode(fitted, role="query", batch_size=batch_size)
            for (entity_id, source), text, vector in zip(chunk, fitted, vectors):
                index.put(conn, kind, entity_id, vector, text, role="query",
                          hashed=source)
            conn.commit()
            log(f"  {kind}: {min(lo + batch_size, len(work))}/{len(work)}")
        elapsed = time.time() - started
        report["kinds"][kind]["seconds"] = round(elapsed, 1)
        log(f"{kind}: {len(work)} encoded in {elapsed:.1f}s "
            f"({fresh} already current, {empty} with no text)")
    report["counts"] = index.counts(conn)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_store_args(ap)
    ap.add_argument("--kind", action="append", choices=list(index.KINDS),
                    help="repeatable; default is all three")
    ap.add_argument("--force", action="store_true",
                    help="re-encode even when the text hash is unchanged")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    log = (lambda *a, **k: None) if args.quiet else print
    conn = open_store(args, log=log)
    try:
        report = run(conn, Path(args.corpus), kinds=tuple(args.kind or index.KINDS),
                     force=args.force, batch_size=args.batch_size, log=log)
    finally:
        conn.close()
    log("indexed:", ", ".join(f"{k} {v}" for k, v in report["counts"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
