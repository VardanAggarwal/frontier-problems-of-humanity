"""The vector index — `vec0` virtual tables living inside graph.db.

Same file as the graph, deliberately: a vector whose entity has been deleted is
a bug, and one file makes that one transaction rather than two that can diverge.
The cost is that `sqlite-vec` must be loaded on the connection before any vec
table is touched, so `connect` here wraps `store.db.connect` rather than
replacing it — a reader that never touches vectors never needs the extension.

Keys carry the role: `"{role}:{entity_id}"`, with `role` also a vec0 PARTITION
KEY so a kNN stays inside one role. Today every stored vector is `query` (§8:
every current comparison is symmetric, and one stored vector commits to one
pairing). The day an asymmetric path arrives it writes `passage` vectors
alongside, and nothing here changes.
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from .model import EMBED_DIM, MODEL_NAME   # noqa: E402

KINDS = ("problem", "actor", "source")
VEC_TABLE = {kind: f"vec_{kind}" for kind in KINDS}

_BOOKKEEPING = """
-- One row per stored vector. `text_hash` makes backfill incremental and makes a
-- silent change of the embedded text detectable; `model` makes a change of
-- encoder detectable, which invalidates every vector in the file at once.
-- `chars` is the length of the text that was *encoded*; `text_hash` may be over
-- the text before truncation (see `put`'s `hashed`), so the two can disagree.
CREATE TABLE IF NOT EXISTS embedding (
  entity_kind TEXT NOT NULL CHECK (entity_kind IN ('problem', 'actor', 'source')),
  entity_id   TEXT NOT NULL,
  role        TEXT NOT NULL CHECK (role IN ('query', 'passage')),
  model       TEXT NOT NULL,
  dim         INTEGER NOT NULL,
  text_hash   TEXT NOT NULL,
  chars       INTEGER NOT NULL,
  built_at    TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (entity_kind, entity_id, role)
) WITHOUT ROWID;
"""


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Load the sqlite-vec extension onto an open connection. Idempotent."""
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def connect(path: str | Path, *, create: bool = True) -> sqlite3.Connection:
    """`store.db.connect` plus the extension plus the vector tables."""
    from store import db
    conn = db.connect(path, create=create)
    load(conn)
    init(conn)
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(_BOOKKEEPING)
    for kind in KINDS:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_TABLE[kind]} USING vec0("
            f"role TEXT PARTITION KEY, key TEXT PRIMARY KEY, "
            f"embedding FLOAT[{EMBED_DIM}])")
    conn.commit()


ROLES = ("query", "passage")


def _check(kind: str, role: str) -> None:
    """Both, every time. `kind` was validated and `role` was not, which meant a
    typo'd role wrote a vec row and then tripped the bookkeeping CHECK — half a
    write, and the half that survived was invisible to `counts`."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")


def _key(entity_id: str, role: str) -> str:
    return f"{role}:{entity_id}"


# ------------------------------------------------------------------ writes --
def put(conn: sqlite3.Connection, kind: str, entity_id: str, vector,
        text: str, *, role: str = "query", hashed: str | None = None) -> None:
    """Replace the stored vector for one entity. Caller owns the transaction.

    `hashed` is the text staleness is keyed on when it differs from the text
    that was encoded. Backfill keys on the text *before* token truncation, so
    that deciding a record is current costs a sha256 rather than a tokenizer —
    and a tokenizer means loading a 470 MB model to discover there is nothing to
    do. Sound because truncation is a pure function of (text, tokenizer) and the
    tokenizer moves only with `model`, which `stale` compares separately."""
    from sqlite_vec import serialize_float32
    _check(kind, role)
    values = [float(x) for x in vector]
    if len(values) != EMBED_DIM:
        raise ValueError(f"expected {EMBED_DIM} dimensions, got {len(values)}")
    table, key = VEC_TABLE[kind], _key(entity_id, role)
    # The vector and its bookkeeping row are one write or neither. Half of this
    # pair surviving is worse than failing: a vec row with no `embedding` row is
    # re-encoded on every run, and an `embedding` row with no vector reports
    # itself current forever while `knn` returns nothing for it.
    conn.execute("SAVEPOINT vec_put")
    try:
        conn.execute(f"DELETE FROM {table} WHERE key = ?", (key,))
        conn.execute(
            f"INSERT INTO {table} (role, key, embedding) VALUES (?, ?, ?)",
            (role, key, serialize_float32(values)))
        conn.execute(
            "INSERT OR REPLACE INTO embedding "
            "(entity_kind, entity_id, role, model, dim, text_hash, chars, built_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (kind, entity_id, role, MODEL_NAME, EMBED_DIM,
             text_hash(text if hashed is None else hashed), len(text)))
    except Exception:
        conn.execute("ROLLBACK TO vec_put")
        raise
    finally:
        conn.execute("RELEASE vec_put")


def drop(conn: sqlite3.Connection, kind: str, entity_id: str,
         *, role: str = "query") -> None:
    _check(kind, role)
    conn.execute(f"DELETE FROM {VEC_TABLE[kind]} WHERE key = ?",
                 (_key(entity_id, role),))
    conn.execute(
        "DELETE FROM embedding WHERE entity_kind = ? AND entity_id = ? AND role = ?",
        (kind, entity_id, role))


def indexed(conn: sqlite3.Connection, kind: str, *, role: str = "query") -> set[str]:
    """Every entity id that currently holds a vector of this kind and role."""
    _check(kind, role)
    return {r["key"].split(":", 1)[1] for r in conn.execute(
        f"SELECT key FROM {VEC_TABLE[kind]} WHERE role = ?", (role,))}


def prune(conn: sqlite3.Connection, kind: str, keep: set[str],
          *, role: str = "query") -> list[str]:
    """Drop vectors for entities that are no longer indexable, and return what
    was dropped.

    Without this the index only ever grows: an actor set to `depth: excluded`
    keeps answering kNN, and a source given a `canonical_of` by a dedup merge
    leaves the *duplicate* in the index next to its own survivor — which is the
    failure the index exists to prevent."""
    gone = sorted(indexed(conn, kind, role=role) - keep)
    for entity_id in gone:
        drop(conn, kind, entity_id, role=role)
    return gone


def stale(conn: sqlite3.Connection, kind: str, entity_id: str, text: str,
          *, role: str = "query") -> bool:
    """True when this entity has no vector, or one built from different text or
    a different model. The whole point of backfill being cheap to re-run."""
    _check(kind, role)
    row = conn.execute(
        "SELECT model, dim, text_hash FROM embedding "
        "WHERE entity_kind = ? AND entity_id = ? AND role = ?",
        (kind, entity_id, role)).fetchone()
    if row is None:
        return True
    return (row["model"] != MODEL_NAME or row["dim"] != EMBED_DIM
            or row["text_hash"] != text_hash(text))


# ------------------------------------------------------------------- reads --
def knn(conn: sqlite3.Connection, kind: str, vector, *, k: int = 10,
        role: str = "query", exclude: str | None = None
        ) -> list[tuple[str, float]]:
    """-> [(entity_id, cosine)] descending. Vectors are L2-normalized, so
    sqlite-vec's L2 distance converts exactly: cos = 1 - d²/2."""
    from sqlite_vec import serialize_float32
    _check(kind, role)
    want = k + (1 if exclude else 0)
    rows = conn.execute(
        f"SELECT key, distance FROM {VEC_TABLE[kind]} "
        f"WHERE embedding MATCH ? AND role = ? AND k = ? ORDER BY distance",
        (serialize_float32([float(x) for x in vector]), role, want)).fetchall()
    out = []
    for row in rows:
        entity_id = row["key"].split(":", 1)[1]
        if entity_id == exclude:
            continue
        out.append((entity_id, 1.0 - (row["distance"] ** 2) / 2.0))
    return out[:k]


def vector(conn: sqlite3.Connection, kind: str, entity_id: str,
           *, role: str = "query"):
    _check(kind, role)
    row = conn.execute(
        f"SELECT embedding FROM {VEC_TABLE[kind]} WHERE key = ?",
        (_key(entity_id, role),)).fetchone()
    if row is None:
        return None
    import numpy as np
    return np.frombuffer(row["embedding"], dtype="float32")


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for kind in KINDS:
        out[kind] = conn.execute(
            "SELECT count(*) FROM embedding WHERE entity_kind = ?",
            (kind,)).fetchone()[0]
    return out
