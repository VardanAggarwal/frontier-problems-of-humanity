"""The safe fix for `store/db.py:check_fresh`'s "this store was built from a
different corpus" refusal, when the store is a live one and rebuilding it
from `migrate/from_corpus.py` would lose worker-pipeline state (`candidate`,
`source`, `edge`, `ask`, `channel` — none of it derivable from markdown).

What this does, and does not, do:

- Updates the store's `corpus_fingerprint` meta row to match the corpus as it
  is now. That's it. No table other than `meta` (and `event`, for the audit
  row below) is touched.
- Does NOT re-sync `problem`/`actor` content from the corpus. If a leaf's
  prose or frontmatter actually changed, this tool does not pull that change
  into the store — it only silences the guard. `store/db.py`'s own comment on
  `check_fresh` names exactly the failure this leaves open: "a store built 45
  minutes before the migration code was finalised carried two problems the
  corpus had already retired, and a whole session of vectors and measurements
  was built on top without anything noticing." Restamping without checking
  what actually changed reintroduces that risk in a new form.

So `--reason` is required, not optional, and it is written to `event` as an
audited bypass of the freshness guard — the same "ruling something out is a
recorded decision, not a deletion" discipline this repo already uses for
`npm run exclude`. Before restamping, look at what changed: `git diff` the
corpus, or diff `migrate.from_corpus.corpus_files()`'s list against the
store's own `problem`/`actor` ids for anything added, renamed or removed.
Give the reason a corpus_files diff would let a reviewer check
("frontmatter-only edit, ids unchanged" is checkable; "checked, looks fine"
is not).

If real content drift needs to land in the store too, that is a genuine gap
this tool does not close (`migrate/from_corpus.py`'s `migrate_needs`/
`migrate_leaves`/`migrate_actors` already use `store.db.put`, an idempotent
upsert, so re-running just those against a live connection would be safe;
`cite`/`db.link` are not idempotent yet — plain `INSERT`, no dedup — so
edges would duplicate on a second run. Fixing that is a real, separate piece
of work, not something to fold into this file.)

Run as:
    python -m migrate.restamp <db-path> --corpus problems --reason "..."
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from migrate.from_corpus import corpus_fingerprint   # noqa: E402
from store import db                                  # noqa: E402

BY = "human:restamp"


def restamp(conn: sqlite3.Connection, corpus: Path, *, reason: str,
            by: str = BY) -> str:
    """Updates the store's corpus fingerprint to match `corpus` now, logs the
    bypass to `event`, and returns the new fingerprint. Raises `ValueError`
    on a blank `reason` — an unaudited bypass is exactly what this tool
    exists to not be.

    Idempotent in the sense that matters: if the store is already fresh, this
    still writes (fingerprint unchanged, but the reason is still logged —
    calling it is itself the action being recorded), rather than silently
    no-op-ing in a way that could hide a caller's mistaken assumption that a
    restamp was needed at all.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError(
            "a reason is required — this bypasses the freshness guard "
            "without re-syncing content, and that decision needs a name")

    old = db.stamped(conn)
    new = corpus_fingerprint(corpus)
    db.stamp(conn, new)
    db.record(conn, "meta", "corpus_fingerprint", "corpus_fingerprint",
              old, new, by=by, why=reason)
    conn.commit()
    return new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path)
    parser.add_argument("--corpus", default="problems", type=Path)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    db_path = args.db.resolve()
    if not db_path.exists():
        print(f"no such file: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        new = restamp(conn, args.corpus.resolve(), reason=args.reason)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"restamped to {new[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
