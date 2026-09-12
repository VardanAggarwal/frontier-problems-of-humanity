"""Markdown corpus -> SQLite graph. One direction, re-runnable, non-destructive
to the source: it reads `problems/` and writes a database, nothing else.

Four markdown record types collapse into `problem`:

    need (36)            root, one per row of needs.yaml
    leaf (7)             child of a need
    node (6)             child of every need it touches — this is what
                         "multi-parent" means and is why the tree is edges
    cross-cutting (2)    root, an axis rather than a container

Everything the migration cannot do honestly is reported rather than guessed at:
a reference to a leaf that was never written becomes a stub with no parent and
appears in the report, because inventing a parent for it would be inventing
research.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from store import db                                     # noqa: E402
from text.canonical import canonicalize, url_hash        # noqa: E402

BY = "migration"
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
H1 = re.compile(r"^#\s+(.+)$", re.M)
BLOCKQUOTE = re.compile(r"^>\s+(.+)$", re.M)

# A need file's maturity is not the same axis as a record's completeness.
# All 36 have prose, so all 36 are `researched`; how thin they are rides on a
# `sweep:` tag instead of being smuggled into `status`.
NEED_STATUS = "researched"

LEGS = ("activism", "institution", "enterprise", "service")


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.counts: dict[str, int] = {}

    def note(self, line: str) -> None:
        self.lines.append(line)

    def bump(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n


# ------------------------------------------------------------------ parsing --
def frontmatter(path: Path) -> dict[str, Any]:
    match = FRONTMATTER.match(path.read_text())
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def lead(path: Path) -> tuple[str | None, str | None]:
    """(title from H1, one_line from the leading blockquote)."""
    text = path.read_text()
    body = FRONTMATTER.sub("", text, count=1)
    title = H1.search(body)
    quote = BLOCKQUOTE.search(body)
    return (title.group(1).strip() if title else None,
            quote.group(1).strip() if quote else None)


def iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()[:10]
    return str(value)


def yesno(value: Any) -> str | None:
    """YAML 1.1 turns `yes`/`no` into booleans; the enum wants the words back."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def listof(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


# ------------------------------------------------------------------ sources --
def put_source(conn, url: str, *, title=None, org=None, year=None) -> str | None:
    if not url:
        return None
    canonical = canonicalize(url)
    sid = url_hash(canonical)
    row = conn.execute("SELECT id FROM source WHERE id = ?", (sid,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO source (id, url, url_canonical, title, org, year) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sid, url, canonical, title, org,
             int(year) if isinstance(year, int) or str(year or "").isdigit() else None),
        )
    return sid


def cite(conn, entity_kind: str, entity_id: str, rows: Any, report: Report) -> None:
    for row in listof_dicts(rows):
        url = row.get("url")
        sid = put_source(conn, url, title=row.get("title"), org=row.get("org"),
                         year=row.get("year"))
        if sid is None:
            continue
        # A bare publication year, not a date — acceptable here because a
        # citation's `as_of` only ever needs to answer "how old is this
        # source", never a day-level comparison the way an actor edge's does.
        db.link(conn, (entity_kind, entity_id), "cites", ("source", sid),
                by=BY, evidence=row.get("title"), as_of=iso(row.get("year")))
        report.bump("citations")


def listof_dicts(value: Any) -> list[dict]:
    if not value:
        return []
    return [v for v in value if isinstance(v, dict)]


# ----------------------------------------------------------------- problems --
def migrate_needs(conn, root: Path, report: Report) -> dict[str, dict]:
    registry = yaml.safe_load((root / "tier-failure-history/needs.yaml").read_text())
    needs = {}
    for row in registry["needs"]:
        path = root / "tier-failure-history" / row["file"]
        title, one_line = lead(path) if path.exists() else (None, None)
        if not path.exists():
            report.note(f"need/{row['id']}: file missing — {row['file']}")
        elif one_line is None:
            report.note(f"need/{row['id']}: no lead blockquote, one_line falls back to title")
        db.put(conn, "problem", {
            "id": row["id"],
            "title": row.get("title") or title or row["id"],
            "one_line": one_line,
            "status": NEED_STATUS,
            "geography": ["india"],
            "doc": str(path.relative_to(root.parent)) if path.exists() else None,
        }, by=BY, why="needs.yaml")
        db.tag(conn, "problem", row["id"], "kind", "need", by=BY)
        db.tag(conn, "problem", row["id"], "tier", row["tier"], by=BY)
        db.tag(conn, "problem", row["id"], "order", row["order"], by=BY)
        db.tag(conn, "problem", row["id"], "sweep", row["status"], by=BY)
        needs[row["id"]] = row
        report.bump("need")
    return needs


def migrate_leaves(conn, root: Path, report: Report, needs: dict) -> dict[str, dict]:
    leaves = {}
    for path in sorted(root.glob("tier-failure-history/*/*/*.md")):
        if path.name.startswith("_"):
            continue
        data = frontmatter(path)
        if not data.get("id"):
            report.note(f"leaf: no id in frontmatter — {path}")
            continue
        pid = data["id"]
        db.put(conn, "problem", {
            "id": pid,
            "title": data.get("title") or pid,
            "one_line": data.get("one_line"),
            "status": data.get("status", "stub"),
            "geography": listof(data.get("geography")) or ["india"],
            "gap_note": data.get("gap_note"),
            "doc": str(path.relative_to(root.parent)),
            "updated": iso(data.get("updated")),
        }, by=BY, why=str(path.name))
        db.tag(conn, "problem", pid, "kind", "leaf", by=BY)
        for ns, key in (("tier", "tier"), ("salience", "salience"),
                        ("scale", "scale"), ("channel", "channel"),
                        ("satisfier_relation", "satisfier_relation"),
                        ("onset", "onset"), ("agent", "agent"),
                        ("gap_kind", "gap")):
            if data.get(key) is not None:
                db.tag(conn, "problem", pid, ns, data[key], by=BY)
        for mechanism in listof(data.get("mechanisms")):
            db.tag(conn, "problem", pid, "mechanism", mechanism, by=BY)
        for axis in listof(data.get("cross_cutting")):
            db.tag(conn, "problem", pid, "cross_cutting", axis, by=BY)
        for leg in listof(data.get("gap_missing_leg")):
            db.tag(conn, "problem", pid, "gap_missing_leg", leg, by=BY)
        # .get, not [] — a leaf missing `need:` entirely must fall through to
        # the "not in the registry" note below rather than crashing here.
        if data.get("need") is not None:
            db.tag(conn, "problem", pid, "need", data["need"], by=BY)
        for name in listof(data.get("aliases")):
            db.alias(conn, "problem", pid, name, by=BY)
        db.alias(conn, "problem", pid, data.get("title") or pid, by=BY)

        parent = data.get("need")
        if parent in needs:
            db.link(conn, ("problem", pid), "part_of", ("problem", parent),
                    by=BY, as_of=iso(data.get("updated")))
        else:
            report.note(f"leaf/{pid}: need '{parent}' is not in the registry — no parent edge")
        leaves[pid] = data
        report.bump("leaf")
    return leaves


def migrate_cross_cutting(conn, root: Path, report: Report) -> None:
    # The two axis essays carry no frontmatter at all — they predate the record
    # schema. They migrate as problems with a title and a doc and nothing else,
    # which is a real hole in the corpus, not a migration shortcut.
    mapping = {"01-freedom-autonomy.md": "autonomy", "02-leisure-play.md": "leisure"}
    for name, pid in mapping.items():
        path = root / "tier-failure-history/cross-cutting" / name
        if not path.exists():
            report.note(f"cross-cutting/{pid}: file missing — {name}")
            continue
        title, one_line = lead(path)
        db.put(conn, "problem", {
            "id": pid, "title": title or pid, "one_line": one_line,
            "status": "researched", "geography": ["india"],
            "doc": str(path.relative_to(root.parent)),
        }, by=BY, why=name)
        db.tag(conn, "problem", pid, "kind", "cross-cutting", by=BY)
        db.tag(conn, "problem", pid, "cross_cutting", pid, by=BY)
        report.bump("cross-cutting")
        report.note(f"cross-cutting/{pid}: no frontmatter in source — migrated "
                    f"with title and doc only, no classification")


def migrate_nodes(conn, root: Path, report: Report, needs: dict) -> list[tuple[str, dict]]:
    """Returns the parsed (pid, data) pairs so migrate_node_actors doesn't have
    to re-glob and re-parse the same files."""
    parsed: list[tuple[str, dict]] = []
    for path in sorted((root / "cross-need-nodes").glob("*.md")):
        if path.name.startswith("00-"):
            continue
        data = frontmatter(path)
        pid = data.get("id")
        if not pid:
            report.note(f"node: no id in frontmatter — {path}")
            continue
        parsed.append((pid, data))
        db.put(conn, "problem", {
            "id": pid,
            "title": data.get("title") or pid,
            "one_line": data.get("one_line"),
            "status": "researched",
            "geography": listof(data.get("geography")) or ["india"],
            "doc": str(path.relative_to(root.parent)),
            "updated": iso(data.get("updated")),
        }, by=BY, why=str(path.name))
        db.tag(conn, "problem", pid, "kind", "node", by=BY)
        if data.get("type"):
            db.tag(conn, "problem", pid, "node_type", data["type"], by=BY)
        if data.get("status"):
            db.tag(conn, "problem", pid, "node_status", data["status"], by=BY)
        for mechanism in listof(data.get("mechanisms")):
            db.tag(conn, "problem", pid, "mechanism", mechanism, by=BY)
        db.alias(conn, "problem", pid, data.get("title") or pid, by=BY)

        for need in listof(data.get("needs")):
            if need in needs:
                db.link(conn, ("problem", pid), "part_of", ("problem", need),
                        by=BY, evidence="node needs:", as_of=iso(data.get("updated")))
                report.bump("node_parent")
            else:
                report.note(f"node/{pid}: need '{need}' not in registry")
        report.bump("node")
    return parsed


def stub_problem(conn, pid: str, report: Report, why: str) -> None:
    db.put(conn, "problem", {"id": pid, "title": pid, "status": "stub"},
           by=BY, why=why)
    db.tag(conn, "problem", pid, "kind", "leaf", by=BY)
    report.bump("stub")
    report.note(f"problem/{pid}: referenced by {why} but no file exists — "
                f"created as a stub with no parent")


# ------------------------------------------------------------------- actors --
def migrate_actors(conn, root: Path, report: Report
                   ) -> tuple[list[tuple], list[tuple[str, dict]]]:
    """Returns (deferred actor->actor edges, parsed (aid, data) pairs) — the
    latter so migrate_actor_work doesn't have to re-glob and re-parse the
    identical actor files a second time."""
    deferred: list[tuple] = []          # actor->actor edges, resolved in pass 2
    parsed: list[tuple[str, dict]] = []
    for path in sorted((root / "actors").glob("*.md")):
        if path.name.startswith("_"):
            continue
        data = frontmatter(path)
        aid = data.get("slug") or path.stem
        parsed.append((aid, data))
        db.put(conn, "actor", {
            "id": aid,
            "title": data.get("name") or aid,
            "type": data.get("type", "org"),
            "legs": listof(data.get("leg")),
            "depth": data.get("depth", "registry"),
            "lifecycle": data.get("lifecycle") or None,
            "lifecycle_as_of": iso(data.get("lifecycle_as_of")),
            "ecosystem_role": listof(data.get("ecosystem_role")),
            "affected_led": yesno(data.get("affected_led")),
            "representation_unit": data.get("representation_unit") or None,
            "stance": data.get("stance") or "works-the-remedy",
            "geography": listof(data.get("geography")),
            "contact_route": data.get("contact_route") or None,
            "followed": 1 if data.get("followed") else 0,
            "followed_date": iso(data.get("followed_date")),
            "last_checked": iso(data.get("last_checked")),
            "doc": str(path.relative_to(root.parent)),
            "updated": iso(data.get("updated")),
        }, by=BY, why=str(path.name))
        report.bump("actor")

        db.alias(conn, "actor", aid, data.get("name") or aid, by=BY)
        for name in listof(data.get("aka")):
            db.alias(conn, "actor", aid, name, by=BY)

        for row in listof_dicts(data.get("sources")):
            conn.execute(
                "INSERT OR IGNORE INTO channel (actor_id, kind, url, handle, "
                "status, last_checked) VALUES (?, ?, ?, ?, ?, ?)",
                (aid, row.get("kind") or "other", row.get("url"),
                 row.get("handle"), row.get("status") or "unconfirmed",
                 iso(row.get("last_checked"))))
            report.bump("channel")

        for direction, key in (("need", "needs"), ("offer", "offers")):
            for row in listof_dicts(data.get(key)):
                conn.execute(
                    "INSERT INTO ask (actor_id, direction, kind, text, as_of, "
                    "source, state) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (aid, direction, row.get("kind") or "other", row.get("text"),
                     iso(row.get("as_of")), row.get("source"), row.get("state")))
                report.bump("ask_" + direction)

        for rel, key in (("parent_org", "parent"), ("superseded_by", "superseded_by")):
            if data.get(key):
                deferred.append((aid, rel, str(data[key]), None, None))
        for row in listof_dicts(data.get("affiliations")):
            if row.get("actor"):
                deferred.append((aid, "affiliated", str(row["actor"]),
                                 row.get("role"), iso(row.get("from"))))
    return deferred, parsed


def migrate_actor_work(conn, report: Report, known: set[str],
                        actors: list[tuple[str, dict]]) -> None:
    """actor -> problem edges. `role: primary` is load-bearing (3); a bare slug
    is worked (2). Both clear the >= 2 threshold the gap view uses, which is
    what the hand-written gap lines assumed. Takes the already-parsed actor
    frontmatter from migrate_actors rather than re-reading the same files."""
    for aid, data in actors:
        stance = data.get("stance") or "works-the-remedy"
        as_of = iso(data.get("updated"))
        for entry in (data.get("leaves") or []):
            pid = entry["id"] if isinstance(entry, dict) else entry
            role = entry.get("role") if isinstance(entry, dict) else None
            if pid not in known:
                stub_problem(conn, pid, report, f"actor/{aid} leaves:")
                known.add(pid)
            db.link(conn, ("actor", aid), "works_on", ("problem", pid), by=BY,
                    relevance=3 if role == "primary" else 2, stance=stance,
                    evidence=role or "supporting", as_of=as_of)
            report.bump("works_on")
        for pid in listof(data.get("nodes")):
            if pid not in known:
                report.note(f"actor/{aid}: node '{pid}' does not exist — edge dropped")
                continue
            db.link(conn, ("actor", aid), "works_on", ("problem", pid), by=BY,
                    relevance=2, stance=stance, evidence="node", as_of=as_of)
            report.bump("works_on")


def migrate_node_actors(conn, report: Report, nodes: list[tuple[str, dict]]) -> None:
    """Runs after migrate_actor_work, which already wrote actor->node edges
    from each actor file's `nodes:` list (evidence="node"). Here we assert the
    same edge from the node file's `actors:` list. Rather than overwrite —
    which threw away the fact that both records independently name the same
    relation — detect the actor-side edge and fold both assertions into the
    evidence string; only the node side surviving keeps the plain wording."""
    for pid, data in nodes:
        for aid in listof(data.get("actors")):
            if conn.execute("SELECT 1 FROM actor WHERE id = ?", (aid,)).fetchone() is None:
                report.note(f"node/{pid}: actor '{aid}' has no record — edge dropped")
                continue
            existing = conn.execute(
                "SELECT evidence FROM edge WHERE src_kind='actor' AND src_id=? "
                "AND dst_kind='problem' AND dst_id=? AND kind='works_on'",
                (aid, pid)).fetchone()
            evidence = ("node actors: + actor nodes:"
                        if existing and existing["evidence"] == "node"
                        else "node actors:")
            db.link(conn, ("actor", aid), "works_on", ("problem", pid), by=BY,
                    relevance=2, evidence=evidence, as_of=iso(data.get("updated")))
            report.bump("works_on")


def resolve_deferred(conn, deferred: list[tuple], report: Report) -> None:
    for src, kind, dst, evidence, as_of in deferred:
        if conn.execute("SELECT 1 FROM actor WHERE id = ?", (dst,)).fetchone() is None:
            report.note(f"actor/{src}: {kind} target '{dst}' has no record — edge dropped")
            continue
        db.link(conn, ("actor", src), kind, ("actor", dst), by=BY,
                evidence=evidence, as_of=as_of)
        report.bump(kind)


# -------------------------------------------------------------- needs_legs ---
def set_needs_legs(conn, report: Report) -> None:
    """The corpus never recorded which legs a problem needs. It recorded a
    conclusion instead (`gap_missing_leg`), and that conclusion turns out to be
    finer-grained than a leg — see the note on `problem_coverage`.

    So the honest default is the question `process-leaf` actually asks of every
    researched failure: all four legs. The view then reports the one thing it
    can stand behind — a leg with nobody on it at all."""
    rows = conn.execute("""
        SELECT p.id FROM problem p
        JOIN tag t ON t.entity_kind = 'problem' AND t.entity_id = p.id
                  AND t.ns = 'kind' AND t.value = 'leaf'
        WHERE p.status = 'researched'
    """).fetchall()
    for row in rows:
        db.put(conn, "problem", {"id": row["id"], "needs_legs": list(LEGS)},
               by=BY, why="process-leaf asks all four legs of a researched failure")
        report.bump("needs_legs")

    for row in conn.execute("""
        SELECT c.problem_id, c.uncovered_legs,
               (SELECT group_concat(value, ',') FROM tag
                 WHERE entity_kind = 'problem' AND entity_id = c.problem_id
                   AND ns = 'gap_missing_leg') AS recorded
        FROM problem_coverage c WHERE c.uncovered_count > 0
    """):
        report.note(f"coverage floor: {row['problem_id']} has nobody on "
                    f"{row['uncovered_legs']} (recorded finding named "
                    f"{row['recorded'] or 'no leg'})")


# ------------------------------------------------------------------- driver --
def run(corpus: Path, out: Path, *, force: bool = False) -> Report:
    """`force=False` is the safe default for a caller writing to a real path;
    main() flips it on --force. Callers who already know they want a fresh
    file (tests using a scratch tmp_path) can just pass force=True."""
    report = Report()
    if out.exists() and not force:
        raise FileExistsError(
            f"refusing to overwrite existing output: {out} (pass --force to replace it)")
    if out.exists():
        out.unlink()
    for suffix in ("-wal", "-shm"):
        side = out.with_name(out.name + suffix)
        if side.exists():
            side.unlink()
    conn = db.connect(out)

    needs = migrate_needs(conn, corpus, report)
    leaves = migrate_leaves(conn, corpus, report, needs)
    migrate_cross_cutting(conn, corpus, report)
    nodes = migrate_nodes(conn, corpus, report, needs)

    for pid, data in leaves.items():
        cite(conn, "problem", pid, data.get("sources"), report)
        for node in listof(data.get("nodes")):
            if conn.execute("SELECT 1 FROM problem WHERE id = ?", (node,)).fetchone():
                db.link(conn, ("problem", pid), "member_of", ("problem", node),
                        by=BY, as_of=iso(data.get("updated")))
                report.bump("member_of")
            else:
                report.note(f"leaf/{pid}: node '{node}' does not exist — edge dropped")

    deferred, actors = migrate_actors(conn, corpus, report)
    known = {r["id"] for r in conn.execute("SELECT id FROM problem")}
    migrate_actor_work(conn, report, known, actors)
    migrate_node_actors(conn, report, nodes)
    resolve_deferred(conn, deferred, report)
    set_needs_legs(conn, report)

    conn.commit()
    report.counts.update({f"table:{k}": v for k, v in db.counts(conn).items()})
    for line in db.validate(conn):
        report.note("VALIDATE " + line)
    conn.commit()
    conn.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="problems", type=Path)
    parser.add_argument("--out", default="problems/graph.db", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="overwrite --out if it already exists")
    args = parser.parse_args()

    out = args.out.resolve()
    if out.exists() and not args.force:
        print(f"refusing to overwrite existing output: {out} (pass --force to replace it)")
        return 1

    report = run(args.corpus.resolve(), out, force=True)
    if not report.counts:
        print("no counts — nothing migrated")
        return 0
    width = max(len(k) for k in report.counts)
    for key in sorted(report.counts):
        print(f"  {key:<{width}}  {report.counts[key]:>6}")
    if report.lines and not args.quiet:
        print(f"\n{len(report.lines)} notes:")
        for line in report.lines:
            print("  -", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
