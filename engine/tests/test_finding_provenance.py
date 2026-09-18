"""Track E0: `finding.source_id` / `finding.chunk_ref` (03-worker.md §9,
04-worker-build-plan.md §5 "Two holes found by the user" item 2) and the
migration that adds them to a pre-existing v1 database."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlite3

import pytest

from store import db
from migrate import m0002_finding_provenance as mig
from migrate import m0003_finding_reason as mig3


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def test_fresh_db_has_provenance_columns(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(finding)")}
    assert {"source_id", "chunk_ref"} <= cols


def test_fresh_db_has_reason_column(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(finding)")}
    assert "reason" in cols


def test_fresh_db_is_stamped_at_the_current_schema_version(conn):
    """Pinned to `db.SCHEMA_VERSION` rather than to a literal: this asserts
    that `init()` stamps the version at all, which is what a migration reads
    to decide whether it has work to do. Pinning the literal made every
    schema bump fail here (v4, the resume point, was the first) for no
    reason the test was written to catch. The floor keeps it from passing on
    an empty or absent stamp."""
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    assert row["value"] == db.SCHEMA_VERSION
    assert int(row["value"]) >= 3


def _v1_db(path) -> sqlite3.Connection:
    """A hand-built v1 database: schema.sql's finding table before this
    migration, so the test exercises the real pre->post transition rather
    than migrating a database that already has the columns."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE candidate (id INTEGER PRIMARY KEY);
        CREATE TABLE source (id TEXT PRIMARY KEY);
        CREATE TABLE finding (
          id            INTEGER PRIMARY KEY,
          candidate_id  INTEGER NOT NULL REFERENCES candidate (id),
          question_id   TEXT NOT NULL,
          answer        TEXT NOT NULL,
          confidence    REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
          source_url    TEXT,
          gathered_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO meta (key, value) VALUES ('schema_version', '1');
        INSERT INTO candidate (id) VALUES (1);
        INSERT INTO finding (candidate_id, question_id, answer, source_url)
          VALUES (1, 'q1', 'some answer', 'https://example.org');
    """)
    conn.commit()
    return conn


def test_v1_db_migrates_to_v2_with_columns_and_no_backfill(tmp_path):
    path = tmp_path / "v1.db"
    conn = _v1_db(path)
    conn.close()

    conn = sqlite3.connect(path)
    changed = mig.migrate(conn)
    assert changed is True

    cols = {row[1] for row in conn.execute("PRAGMA table_info(finding)")}
    assert {"source_id", "chunk_ref"} <= cols

    version = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()[0]
    assert version == "2"

    # No backfill: the pre-existing row comes back with NULL provenance.
    row = conn.execute(
        "SELECT source_id, chunk_ref FROM finding WHERE candidate_id = 1"
    ).fetchone()
    assert row == (None, None)
    conn.close()


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "v1.db"
    conn = _v1_db(path)
    conn.close()

    conn = sqlite3.connect(path)
    first = mig.migrate(conn)
    second = mig.migrate(conn)
    conn.close()

    assert first is True
    assert second is False  # nothing left to do the second time

    conn = sqlite3.connect(path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finding)")]
    # ALTER TABLE ADD COLUMN was not run twice — no duplicate columns.
    assert cols.count("source_id") == 1
    assert cols.count("chunk_ref") == 1
    conn.close()


def test_added_source_id_enforces_the_foreign_key(tmp_path):
    """Empirical check that SQLite honours the REFERENCES clause added via
    ALTER TABLE ADD COLUMN (see migrate/m0002_finding_provenance.py docstring)."""
    path = tmp_path / "v1.db"
    conn = _v1_db(path)
    conn.close()

    conn = sqlite3.connect(path)
    mig.migrate(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO finding (candidate_id, question_id, answer, source_id) "
            "VALUES (1, 'q2', 'ans', 'does-not-exist')"
        )
    conn.close()


# ------------------------------------------------------- v2 -> v3: reason ---
def _v2_db(path) -> sqlite3.Connection:
    """A hand-built v2 database: schema.sql's finding table after m0002 but
    before m0003, so the test exercises the real pre->post transition rather
    than migrating a database that already has the `reason` column."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE candidate (id INTEGER PRIMARY KEY);
        CREATE TABLE source (id TEXT PRIMARY KEY);
        CREATE TABLE finding (
          id            INTEGER PRIMARY KEY,
          candidate_id  INTEGER NOT NULL REFERENCES candidate (id),
          question_id   TEXT NOT NULL,
          answer        TEXT NOT NULL,
          confidence    REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
          source_url    TEXT,
          source_id     TEXT REFERENCES source (id),
          chunk_ref     TEXT,
          gathered_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO meta (key, value) VALUES ('schema_version', '2');
        INSERT INTO candidate (id) VALUES (1);
        INSERT INTO finding (candidate_id, question_id, answer, source_url)
          VALUES (1, 'q1', 'some answer', 'https://example.org');
    """)
    conn.commit()
    return conn


def test_v2_db_migrates_to_v3_with_reason_and_no_backfill(tmp_path):
    path = tmp_path / "v2.db"
    conn = _v2_db(path)
    conn.close()

    conn = sqlite3.connect(path)
    changed = mig3.migrate(conn)
    assert changed is True

    cols = {row[1] for row in conn.execute("PRAGMA table_info(finding)")}
    assert "reason" in cols

    version = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()[0]
    assert version == "3"

    # No backfill: the pre-existing row comes back with NULL reason.
    row = conn.execute(
        "SELECT reason FROM finding WHERE candidate_id = 1"
    ).fetchone()
    assert row == (None,)
    conn.close()


def test_m0003_migration_is_idempotent(tmp_path):
    path = tmp_path / "v2.db"
    conn = _v2_db(path)
    conn.close()

    conn = sqlite3.connect(path)
    first = mig3.migrate(conn)
    second = mig3.migrate(conn)
    conn.close()

    assert first is True
    assert second is False  # nothing left to do the second time

    conn = sqlite3.connect(path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finding)")]
    # ALTER TABLE ADD COLUMN was not run twice — no duplicate columns.
    assert cols.count("reason") == 1
    conn.close()
