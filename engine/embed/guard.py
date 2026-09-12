"""Refuse to work on a store that no longer matches the corpus.

Written after a store built 45 minutes before the migration code was finalised
carried two retired problems through a whole session — vectors, an all-pairs
sweep and a set of reported thresholds, all on records the corpus had dropped.
Nothing in the pipeline noticed, because nothing was looking.

The check is one comparison and the fix is one command, so the default is to
stop. `--stale-ok` exists because measuring a deliberately old store is a real
thing to want, and the flag makes that a choice instead of an accident.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from store import db                                      # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def status(conn: sqlite3.Connection, corpus: Path) -> str | None:
    """-> None when the store matches `corpus`, else a sentence saying how not.

    `corpus` is the migration's root — `problems/` — which is NOT the root the
    `doc` columns are relative to. They differ by one directory and conflating
    them silently fingerprints the wrong tree, so both callers pass it
    explicitly."""
    if not corpus.is_dir():
        return f"corpus root {corpus} does not exist, so freshness cannot be checked"
    from migrate.from_corpus import corpus_fingerprint
    return db.check_fresh(conn, corpus_fingerprint(corpus))


def require_fresh(conn: sqlite3.Connection, corpus: Path, *, allow: bool = False,
                  log=print) -> str | None:
    problem = status(conn, corpus)
    if problem is None:
        return None
    if allow:
        log(f"!! {problem}\n!! continuing anyway (--stale-ok)")
        return problem
    raise SystemExit(
        f"{problem}\n\n  cd engine && python -m migrate.from_corpus "
        f"--corpus {corpus} --out <db> --force\n"
        "  (or pass --stale-ok to measure it as it is)")


# ------------------------------------------------------------- the CLI half --
def add_store_args(ap: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The store / corpus / freshness flags, defined once.

    Two reasons this is shared rather than copied. The flags and the check are
    one thing — a tool that takes `--stale-ok` and forgets to call
    `require_fresh` accepts the flag and ignores it, silently. And the defaults
    are absolute, anchored on the repo rather than on the cwd: `backfill` and
    `calibrate` had disagreed about whether a bare run meant repo root or
    `engine/`, and a relative default resolved against the wrong directory
    either fails loudly (no such db) or, worse, finds a different one."""
    ap.add_argument("--db", default=str(REPO / "problems" / "graph.db"))
    ap.add_argument("--corpus", default=str(REPO),
                    help="root that `doc` / `path` columns are relative to")
    ap.add_argument("--problems", default=None,
                    help="the migration's corpus root, for the freshness check "
                         "(default: <corpus>/problems)")
    ap.add_argument("--stale-ok", action="store_true",
                    help="work on a store that does not match the corpus anyway")
    return ap


def open_store(args, *, log=print) -> sqlite3.Connection:
    """Open the store named by `add_store_args`, refusing a stale one."""
    from . import index
    conn = index.connect(args.db, create=False)
    require_fresh(conn, Path(args.problems or Path(args.corpus) / "problems"),
                  allow=args.stale_ok, log=log)
    return conn
