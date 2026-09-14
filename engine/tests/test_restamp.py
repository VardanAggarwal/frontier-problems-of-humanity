"""migrate/restamp.py — the safe fix for a stale corpus stamp on a live
store. See the module docstring for why this exists instead of just
re-running `from_corpus.py --force` (removed 2026-09-15 after that path
deleted a live store's worker-pipeline data)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlite3

import pytest

from migrate.from_corpus import corpus_fingerprint
from migrate.restamp import restamp
from store import db


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / "tier-failure-history").mkdir()
    (tmp_path / "actors").mkdir()
    (tmp_path / "data-model.yaml").write_text("a: 1\n")
    (tmp_path / "actors" / "x.md").write_text("---\nname: X\n---\n\n# X\n")
    return tmp_path


@pytest.fixture
def live_store(tmp_path):
    """A store carrying data no corpus re-derivation could reconstruct —
    the exact shape of state a `from_corpus.py` rebuild would have wiped."""
    conn = db.connect(tmp_path / "g.db")
    conn.execute(
        "INSERT INTO candidate (kind, name, admitted, discovered_via) "
        "VALUES ('actor', 'Test Org', 1, 'human:dev-seed-ui')")
    conn.commit()
    return conn


def test_restamp_updates_the_fingerprint(corpus, live_store):
    assert db.stamped(live_store) is None
    new = restamp(live_store, corpus, reason="initial stamp for a fresh store")
    assert new == corpus_fingerprint(corpus)
    assert db.stamped(live_store) == new


def test_restamp_touches_no_table_but_meta_and_event(corpus, live_store):
    before = db.counts(live_store)
    restamp(live_store, corpus, reason="frontmatter-only edit, ids unchanged")
    after = db.counts(live_store)
    for table in before:
        if table in ("event",):
            continue
        assert after[table] == before[table], f"{table} changed: {before[table]} -> {after[table]}"
    # candidate survives — the whole point.
    assert live_store.execute(
        "SELECT count(*) c FROM candidate").fetchone()["c"] == 1


def test_restamp_logs_the_bypass_to_event(corpus, live_store):
    restamp(live_store, corpus, reason="frontmatter-only edit, ids unchanged")
    row = live_store.execute(
        "SELECT * FROM event WHERE entity_kind = 'meta' "
        "AND entity_id = 'corpus_fingerprint' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["why"] == "frontmatter-only edit, ids unchanged"
    assert row["by"] == "human:restamp"


def test_restamp_refuses_a_blank_reason(corpus, live_store):
    with pytest.raises(ValueError):
        restamp(live_store, corpus, reason="")
    with pytest.raises(ValueError):
        restamp(live_store, corpus, reason="   ")


def test_restamp_makes_check_fresh_pass(corpus, live_store):
    fp = corpus_fingerprint(corpus)
    assert db.check_fresh(live_store, fp) is not None
    restamp(live_store, corpus, reason="verified: only X.md prose changed")
    assert db.check_fresh(live_store, fp) is None
