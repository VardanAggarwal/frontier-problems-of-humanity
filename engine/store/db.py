"""Opening, creating and writing the store.

Every mutation goes through `put` / `link` / `tag` / `untag` / `alias` so that
`event` gets written without a trigger per column. The trigger-based
alternative is 40 triggers that have to be edited whenever a column is added;
this is one place instead.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import tags

SCHEMA = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = "7"
FINGERPRINT = "corpus_fingerprint"

class _Clear:
    """Sentinel for `link()`: pass CLEAR to set a field to NULL. Plain None means
    "leave alone" — without this, an edge field, once set, could never be
    cleared back to NULL, because the diff would just see None and skip it."""
    def __repr__(self) -> str:
        return "CLEAR"


CLEAR = _Clear()

_JSON_COLUMNS = {
    "problem": {"geography", "needs_legs"},
    "actor": {"legs", "ecosystem_role", "geography"},
}
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE = re.compile(r"\s+")


def norm(name: str) -> str:
    """Match key for alias lookup: casefolded, punctuation stripped."""
    return _SPACE.sub(" ", _PUNCT.sub(" ", (name or "").casefold())).strip()


def connect(path: str | Path, *, create: bool = True) -> sqlite3.Connection:
    path = Path(path)
    fresh = not path.exists()
    if fresh and not create:
        raise FileNotFoundError(path)
    # check_same_thread=False: worker/fetch.py fetches URLs concurrently from
    # a thread pool (network I/O is the latency; the DB itself stays
    # serialized behind worker/fetch.py's own lock, not sqlite's default
    # same-thread guard). Every other caller still uses this connection from
    # a single thread, so this has no effect on them.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if fresh:
        init(conn)
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text())
    tags.seed(conn)
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()


# --------------------------------------------------------------- provenance --
def record(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: str,
    field: str | None,
    old: Any,
    new: Any,
    *,
    by: str,
    why: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO event (entity_kind, entity_id, field, old, new, by, why) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (entity_kind, entity_id, field, _text(old), _text(new), by, why),
    )


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _encode(table: str, row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for column in _JSON_COLUMNS.get(table, ()):
        if isinstance(out.get(column), (list, tuple)):
            out[column] = json.dumps(list(out[column]), ensure_ascii=False)
    return out


# ------------------------------------------------------------------- writes --
def put(
    conn: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
    *,
    by: str,
    why: str | None = None,
) -> str:
    """Insert or update one problem/actor row, emitting a field-level event per change."""
    if table not in ("problem", "actor"):
        raise ValueError(f"put is for problem/actor, not {table}")
    row = _encode(table, row)
    entity_id = row["id"]
    before = conn.execute(
        f"SELECT * FROM {table} WHERE id = ?", (entity_id,)
    ).fetchone()

    if before is None:
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        record(conn, table, entity_id, None, None, "created", by=by, why=why)
        return entity_id

    changed = {k: v for k, v in row.items() if k != "id" and before[k] != v}
    if not changed:
        return entity_id
    assignments = ", ".join(f"{k} = ?" for k in changed)
    conn.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        (*changed.values(), entity_id),
    )
    for field, value in changed.items():
        record(conn, table, entity_id, field, before[field], value, by=by, why=why)
    return entity_id


def link(
    conn: sqlite3.Connection,
    src: tuple[str, str],
    kind: str,
    dst: tuple[str, str],
    *,
    by: str,
    relevance: int | None = None,
    stance: str | None = None,
    evidence: str | None = None,
    source_id: str | None = None,
    as_of: str | None = None,
    why: str | None = None,
) -> int:
    """Create an edge if it does not exist; update its fields if it does."""
    (src_kind, src_id), (dst_kind, dst_id) = src, dst
    existing = conn.execute(
        "SELECT * FROM edge WHERE src_kind = ? AND src_id = ? AND dst_kind = ? "
        "AND dst_id = ? AND kind = ?",
        (src_kind, src_id, dst_kind, dst_id, kind),
    ).fetchone()
    fields = {
        "relevance": relevance, "stance": stance, "evidence": evidence,
        "source_id": source_id, "as_of": as_of,
    }
    if existing is None:
        # CLEAR makes no sense on an insert — there is nothing to clear yet —
        # so it degrades to NULL, same as omitting the field.
        fields = {k: (None if v is CLEAR else v) for k, v in fields.items()}
        cursor = conn.execute(
            "INSERT INTO edge (src_kind, src_id, dst_kind, dst_id, kind, relevance, "
            "stance, evidence, source_id, as_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (src_kind, src_id, dst_kind, dst_id, kind, fields["relevance"],
             fields["stance"], fields["evidence"], fields["source_id"],
             fields["as_of"]),
        )
        record(conn, "edge", str(cursor.lastrowid), None, None,
               f"{src_id} -{kind}-> {dst_id}", by=by, why=why)
        return int(cursor.lastrowid)

    # None means "leave alone"; CLEAR means "set to NULL" — otherwise a field,
    # once set, could never be cleared back to NULL again.
    fields = {k: (None if v is CLEAR else v) for k, v in fields.items()
              if v is not None}
    changed = {k: v for k, v in fields.items() if existing[k] != v}
    if changed:
        assignments = ", ".join(f"{k} = ?" for k in changed)
        conn.execute(f"UPDATE edge SET {assignments} WHERE id = ?",
                     (*changed.values(), existing["id"]))
        for field, value in changed.items():
            record(conn, "edge", str(existing["id"]), field, existing[field],
                   value, by=by, why=why)
    return int(existing["id"])


def tag(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: str,
    ns: str,
    value: Any,
    *,
    by: str,
    why: str | None = None,
) -> None:
    """mechanism/onset/agent/gap_kind are tags, not columns — the project's core
    classification judgments — so a reclassification needs the same audit
    trail as a `put()` field change. `by` is required for that reason."""
    value = str(value)
    cursor = conn.execute(
        "INSERT OR IGNORE INTO tag (entity_kind, entity_id, ns, value) VALUES (?, ?, ?, ?)",
        (entity_kind, entity_id, ns, value),
    )
    if cursor.rowcount:   # rowcount is 0 on the IGNORE no-op, not a real insert
        record(conn, entity_kind, entity_id, f"tag:{ns}", None, value, by=by, why=why)


def untag(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: str,
    ns: str,
    value: Any,
    *,
    by: str,
    why: str | None = None,
) -> None:
    """The inverse of `tag()`. A classification that can only be added and
    never corrected is not an audit trail."""
    value = str(value)
    cursor = conn.execute(
        "DELETE FROM tag WHERE entity_kind = ? AND entity_id = ? AND ns = ? AND value = ?",
        (entity_kind, entity_id, ns, value),
    )
    if cursor.rowcount:
        record(conn, entity_kind, entity_id, f"tag:{ns}", value, None, by=by, why=why)


def alias(conn: sqlite3.Connection, entity_kind: str, entity_id: str,
          name: str, *, by: str, why: str | None = None) -> None:
    if not name:
        return
    cursor = conn.execute(
        "INSERT OR IGNORE INTO alias (entity_kind, entity_id, alias, norm) "
        "VALUES (?, ?, ?, ?)",
        (entity_kind, entity_id, name, norm(name)),
    )
    if cursor.rowcount:
        record(conn, entity_kind, entity_id, "alias", None, name, by=by, why=why)


# ------------------------------------------------------------------- reads ---
def resolve(conn: sqlite3.Connection, entity_kind: str, name: str) -> str | None:
    """Exact id, then alias, then normalized title. Nothing fuzzy — that is the
    resolver's job (build step 3), and it needs vectors this layer does not have."""
    if entity_kind not in ("problem", "actor"):
        raise ValueError(f"resolve is for problem/actor, not {entity_kind}")
    table = entity_kind
    row = conn.execute(f"SELECT id FROM {table} WHERE id = ?", (name,)).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        "SELECT entity_id FROM alias WHERE entity_kind = ? AND norm = ?",
        (entity_kind, norm(name)),
    ).fetchone()
    return row["entity_id"] if row else None


def title_of(conn: sqlite3.Connection, entity_kind: str, entity_id: str) -> str | None:
    """`title` for a live problem/actor row, or None if the id doesn't exist.
    Used by the resolver (worker/resolve.py) to compare a candidate name
    against its top shortlist hit lexically, not just by cosine."""
    if entity_kind not in ("problem", "actor"):
        raise ValueError(f"title_of is for problem/actor, not {entity_kind}")
    row = conn.execute(
        f"SELECT title FROM {entity_kind} WHERE id = ?", (entity_id,)).fetchone()
    return row["title"] if row else None


def tags_of(conn: sqlite3.Connection, entity_kind: str, entity_id: str,
            ns: str | None = None) -> list[str]:
    if ns:
        rows = conn.execute(
            "SELECT value FROM tag WHERE entity_kind = ? AND entity_id = ? AND ns = ? "
            "ORDER BY value", (entity_kind, entity_id, ns)).fetchall()
        return [r["value"] for r in rows]
    rows = conn.execute(
        "SELECT ns, value FROM tag WHERE entity_kind = ? AND entity_id = ? "
        "ORDER BY ns, value", (entity_kind, entity_id)).fetchall()
    return [f"{r['ns']}:{r['value']}" for r in rows]


def validate(conn: sqlite3.Connection) -> list[str]:
    """What the triggers cannot see: missing required tags, orphans, dangling docs."""
    problems: list[str] = []

    for row in conn.execute("""
        SELECT p.id, p.status,
               (SELECT value FROM tag WHERE entity_kind = 'problem'
                 AND entity_id = p.id AND ns = 'kind') AS kind
        FROM problem p
    """):
        owed = tags.required(row["status"], row["kind"])
        held = {r["ns"] for r in conn.execute(
            "SELECT DISTINCT ns FROM tag WHERE entity_kind = 'problem' AND entity_id = ?",
            (row["id"],))}
        for ns in owed:
            if ns not in held:
                problems.append(f"problem/{row['id']}: missing required tag ns '{ns}'")

    for row in conn.execute(
        "SELECT id FROM problem WHERE doc IS NULL AND status <> 'stub'"
    ):
        problems.append(f"problem/{row['id']}: status is not stub but doc is NULL")

    for row in conn.execute("""
        SELECT p.id FROM problem p
        WHERE NOT EXISTS (SELECT 1 FROM edge e WHERE e.src_kind = 'problem'
                          AND e.src_id = p.id AND e.kind = 'part_of')
          AND NOT EXISTS (SELECT 1 FROM tag t WHERE t.entity_kind = 'problem'
                          AND t.entity_id = p.id AND t.ns = 'kind'
                          AND t.value IN ('need', 'cross-cutting'))
    """):
        problems.append(f"problem/{row['id']}: orphan — no parent and not a root kind")

    return problems


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = ("problem", "actor", "edge", "tag", "alias", "source", "channel",
             "ask", "candidate", "population", "event")
    return {n: conn.execute(f"SELECT count(*) c FROM {n}").fetchone()["c"]
            for n in names}


# ------------------------------------------------------- corpus freshness --
# The store is derived from `problems/` and nothing re-derives it automatically,
# so it can fall behind a commit and stay behind silently. It did: a store built
# 45 minutes before the migration code was finalised carried two problems the
# corpus had already retired, and a whole session of vectors and measurements
# was built on top without anything noticing. Content hashes, not mtimes —
# a checkout or a touch moves an mtime without changing a byte.

def fingerprint(paths: Iterable[Path], *, root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(str(path.relative_to(root)).encode())
        h.update(b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()[:32]


def stamp(conn: sqlite3.Connection, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                 (FINGERPRINT, value))


def stamped(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (FINGERPRINT,)).fetchone()
    return row[0] if row else None


def check_fresh(conn: sqlite3.Connection, current: str) -> str | None:
    """-> None when the store matches the corpus, else a sentence saying so.

    A store with no stamp at all is reported too: it predates this check, which
    is exactly the case that went wrong."""
    have = stamped(conn)
    if have is None:
        return ("this store carries no corpus fingerprint, so it predates the "
                "freshness check and may not match problems/")
    if have != current:
        return (f"this store was built from a different corpus "
                f"(stamped {have[:12]}, corpus is now {current[:12]}) — "
                "re-run engine/migrate/from_corpus.py if this store only "
                "exists (fresh, no worker data). If it's a live store — has "
                "candidates, sources, edges, asks or channels worth keeping "
                "— from_corpus.py will delete all of that; use "
                "engine/migrate/restamp.py instead (it only updates the "
                "fingerprint, --reason required).")
    return None
