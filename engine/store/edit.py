"""Human write path into problems/graph.db — 01-minimal.md §11 item 3b-B.

Corpus markdown lost its frontmatter in 3b-B: a human adding or correcting a
problem/actor field no longer edits a .md header, because nothing reads it
any more. This is the one CLI both a human and the worker's `_write_entity`
(engine/worker/worker.py) go through — same db.put/tag/alias/link primitives,
so there is exactly one write path into the store, not two that can disagree
(the failure mode 3b itself was named for).

Usage:
    python -m store.edit show problem cookfire-smoke
    python -m store.edit set problem cookfire-smoke title="New title" salience=4
    python -m store.edit set problem cookfire-smoke geography=india,nepal   # array column: comma or JSON ["india"]
    python -m store.edit tag problem cookfire-smoke channel structural
    python -m store.edit untag problem cookfire-smoke gap_missing_leg institution
    python -m store.edit alias actor gopal-krishna "G. Krishna"
    python -m store.edit link actor gopal-krishna works_on problem asbestos-in-air --relevance 3
    python -m store.edit doc problem cookfire-smoke problems/tier-failure-history/tier1-physiological/air/cookfire-smoke.md

All writes carry `--by` (default: the OS user) so they land in the same
`event` audit trail as worker writes — a reclassification's provenance is
"who", human or worker, either way.
"""
from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from . import db

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "problems" / "graph.db"

# schema.sql's json_valid/json_type(...) = 'array' columns on problem/actor —
# `set` on any of these needs a JSON array, not the bare string every other
# column takes, or the CHECK constraint raises a raw sqlite3.IntegrityError.
_ARRAY_FIELDS = {"geography", "needs_legs", "legs", "ecosystem_role"}


def _parse_kv(pairs: list[str]) -> dict[str, object]:
    import json

    row: dict[str, object] = {}
    for p in pairs:
        if "=" not in p:
            raise SystemExit(f"expected key=value, got: {p!r}")
        k, v = p.split("=", 1)
        if k not in _ARRAY_FIELDS:
            row[k] = v
            continue
        if v.startswith("["):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{k}: invalid JSON array {v!r}: {e}")
            if not isinstance(parsed, list):
                raise SystemExit(f"{k}: expected a JSON array, got {v!r}")
            row[k] = json.dumps(parsed)
        else:
            # comma-separated shorthand: geography=india or geography=india,pakistan
            row[k] = json.dumps([s.strip() for s in v.split(",") if s.strip()])
    return row


def cmd_show(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    if args.kind not in ("problem", "actor"):
        raise SystemExit("kind must be problem or actor")
    row = conn.execute(f"SELECT * FROM {args.kind} WHERE id = ?", (args.id,)).fetchone()
    if row is None:
        raise SystemExit(f"no {args.kind} with id {args.id!r}")
    for k in row.keys():
        print(f"{k}: {row[k]}")
    print("--- tags ---")
    for r in conn.execute(
        "SELECT ns, value FROM tag WHERE entity_kind = ? AND entity_id = ? ORDER BY ns",
        (args.kind, args.id),
    ):
        print(f"{r['ns']}: {r['value']}")
    print("--- aliases ---")
    for r in conn.execute(
        "SELECT alias FROM alias WHERE entity_kind = ? AND entity_id = ?", (args.kind, args.id)
    ):
        print(r["alias"])
    print("--- edges out ---")
    for r in conn.execute(
        "SELECT kind, dst_kind, dst_id, relevance, stance FROM edge "
        "WHERE src_kind = ? AND src_id = ?",
        (args.kind, args.id),
    ):
        print(f"{r['kind']} -> {r['dst_kind']}/{r['dst_id']} (relevance={r['relevance']}, stance={r['stance']})")


def cmd_set(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    row = {"id": args.id, **_parse_kv(args.fields)}
    entity_id = db.put(conn, args.kind, row, by=args.by, why=args.why)
    conn.commit()
    print(f"put {args.kind}/{entity_id}: {row}")


def cmd_tag(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    db.tag(conn, args.kind, args.id, args.ns, args.value, by=args.by, why=args.why)
    conn.commit()
    print(f"tagged {args.kind}/{args.id} {args.ns}={args.value}")


def cmd_untag(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    db.untag(conn, args.kind, args.id, args.ns, args.value, by=args.by, why=args.why)
    conn.commit()
    print(f"untagged {args.kind}/{args.id} {args.ns}={args.value}")


def cmd_alias(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    db.alias(conn, args.kind, args.id, args.name, by=args.by, why=args.why)
    conn.commit()
    print(f"aliased {args.kind}/{args.id} <- {args.name!r}")


def cmd_link(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    edge_id = db.link(
        conn, (args.src_kind, args.src_id), args.edge_kind, (args.dst_kind, args.dst_id),
        by=args.by, relevance=args.relevance, stance=args.stance,
        evidence=args.evidence, as_of=args.as_of, why=args.why,
    )
    conn.commit()
    print(f"edge {edge_id}: {args.src_kind}/{args.src_id} -{args.edge_kind}-> {args.dst_kind}/{args.dst_id}")


def cmd_doc(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    """Point a problem/actor at its prose file. `doc` is a plain column
    (db.put handles it), broken out as its own verb because it is the one
    field every new hand-authored record needs set before anything else."""
    entity_id = db.put(conn, args.kind, {"id": args.id, "doc": args.path}, by=args.by, why=args.why)
    conn.commit()
    print(f"doc {args.kind}/{entity_id} -> {args.path}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--by", default=f"human:{getpass.getuser()}")
    ap.add_argument("--why", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("show"); p.add_argument("kind"); p.add_argument("id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("set"); p.add_argument("kind"); p.add_argument("id")
    p.add_argument("fields", nargs="+", help="key=value pairs")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("tag"); p.add_argument("kind"); p.add_argument("id")
    p.add_argument("ns"); p.add_argument("value")
    p.set_defaults(func=cmd_tag)

    p = sub.add_parser("untag"); p.add_argument("kind"); p.add_argument("id")
    p.add_argument("ns"); p.add_argument("value")
    p.set_defaults(func=cmd_untag)

    p = sub.add_parser("alias"); p.add_argument("kind"); p.add_argument("id")
    p.add_argument("name")
    p.set_defaults(func=cmd_alias)

    p = sub.add_parser("link")
    p.add_argument("src_kind"); p.add_argument("src_id")
    p.add_argument("edge_kind"); p.add_argument("dst_kind"); p.add_argument("dst_id")
    p.add_argument("--relevance", type=int, default=None)
    p.add_argument("--stance", default=None)
    p.add_argument("--evidence", default=None)
    p.add_argument("--as-of", dest="as_of", default=None)
    p.set_defaults(func=cmd_link)

    p = sub.add_parser("doc"); p.add_argument("kind"); p.add_argument("id"); p.add_argument("path")
    p.set_defaults(func=cmd_doc)

    args = ap.parse_args(argv)
    conn = db.connect(args.db, create=False)
    try:
        args.func(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
