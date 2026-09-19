"""Schema constraints. These are the promise that made relational storage worth
the migration: an autonomous writer is rejected at the bad write, not at the
next build."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlite3
import pytest

from store import db, tags


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def problem(c, pid, **kw):
    row = {"id": pid, "title": pid, **kw}
    return db.put(c, "problem", row, by="test")


def actor(c, aid, legs=("activism",), **kw):
    row = {"id": aid, "title": aid, "type": "org", "legs": list(legs), **kw}
    return db.put(c, "actor", row, by="test")


# ---------------------------------------------------------------- enums ------
def test_bad_status_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        problem(conn, "p1", status="in-progress")


def test_bad_edge_kind_rejected(conn):
    problem(conn, "p1"); problem(conn, "p2")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO edge (src_kind, src_id, dst_kind, dst_id, kind) "
                     "VALUES ('problem','p1','problem','p2','causes')")


def test_relevance_range(conn):
    problem(conn, "p1"); actor(conn, "a1")
    with pytest.raises(sqlite3.IntegrityError):
        db.link(conn, ("actor", "a1"), "works_on", ("problem", "p1"),
                by="test", relevance=7)


def test_geography_must_be_json_array(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO problem (id, title, geography) VALUES ('p','p','india')")


# ------------------------------------------------------- polymorphic edges ---
def test_edge_to_missing_problem_rejected(conn):
    actor(conn, "a1")
    with pytest.raises(sqlite3.IntegrityError, match="no such problem"):
        db.link(conn, ("actor", "a1"), "works_on", ("problem", "ghost"), by="test")


def test_edge_from_missing_actor_rejected(conn):
    problem(conn, "p1")
    with pytest.raises(sqlite3.IntegrityError, match="no such actor"):
        db.link(conn, ("actor", "ghost"), "works_on", ("problem", "p1"), by="test")


def test_problem_cannot_parent_itself(conn):
    problem(conn, "p1")
    with pytest.raises(sqlite3.IntegrityError, match="itself"):
        db.link(conn, ("problem", "p1"), "part_of", ("problem", "p1"), by="test")


def test_edge_is_idempotent(conn):
    problem(conn, "p1"); actor(conn, "a1")
    first = db.link(conn, ("actor", "a1"), "works_on", ("problem", "p1"),
                    by="test", relevance=2)
    second = db.link(conn, ("actor", "a1"), "works_on", ("problem", "p1"),
                     by="test", relevance=3)
    assert first == second
    assert conn.execute("SELECT relevance FROM edge WHERE id=?", (first,)).fetchone()[0] == 3


# ------------------------------------------------------------------ tags -----
def test_unknown_namespace_rejected(conn):
    problem(conn, "p1")
    with pytest.raises(sqlite3.IntegrityError, match="unknown namespace"):
        db.tag(conn, "problem", "p1", "vibe", "good", by="test")


def test_closed_namespace_rejects_new_value(conn):
    problem(conn, "p1")
    with pytest.raises(sqlite3.IntegrityError, match="closed namespace"):
        db.tag(conn, "problem", "p1", "mechanism", "the-eighth-one", by="test")


def test_open_namespace_accepts_anything(conn):
    problem(conn, "p1")
    db.tag(conn, "problem", "p1", "salience", 4, by="test")
    assert db.tags_of(conn, "problem", "p1", "salience") == ["4"]


def test_namespace_respects_entity_kind(conn):
    actor(conn, "a1")
    with pytest.raises(sqlite3.IntegrityError, match="does not apply"):
        db.tag(conn, "actor", "a1", "onset", "chronic", by="test")


def test_classification_required_only_for_researched_leaves():
    assert tags.required("stub", "leaf") == ("kind",)
    assert "mechanism" in tags.required("researched", "leaf")
    assert "mechanism" not in tags.required("researched", "need")


# ----------------------------------------------------------------- event -----
def test_put_emits_field_level_events(conn):
    problem(conn, "p1", one_line="first")
    problem(conn, "p1", one_line="second")
    rows = conn.execute("SELECT field, old, new FROM event WHERE entity_id='p1' "
                        "ORDER BY id").fetchall()
    assert rows[0]["new"] == "created"
    assert (rows[1]["field"], rows[1]["old"], rows[1]["new"]) == ("one_line", "first", "second")


def test_unchanged_put_writes_no_event(conn):
    problem(conn, "p1", one_line="same")
    before = conn.execute("SELECT count(*) c FROM event").fetchone()["c"]
    problem(conn, "p1", one_line="same")
    assert conn.execute("SELECT count(*) c FROM event").fetchone()["c"] == before


def test_event_is_append_only(conn):
    problem(conn, "p1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE event SET why='rewritten'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM event")


# ----------------------------------------------------------------- views -----
def test_coverage_floor_counts_only_empty_legs(conn):
    problem(conn, "p1", needs_legs=["activism", "enterprise"])
    actor(conn, "a1", legs=["activism"])
    db.link(conn, ("actor", "a1"), "works_on", ("problem", "p1"), by="test", relevance=2)
    row = conn.execute("SELECT * FROM problem_coverage WHERE problem_id='p1'").fetchone()
    assert row["uncovered_count"] == 1
    assert "enterprise" in row["uncovered_legs"]


def test_coverage_ignores_low_relevance_and_opponents(conn):
    problem(conn, "p1", needs_legs=["enterprise"])
    actor(conn, "mention", legs=["enterprise"])
    actor(conn, "opponent", legs=["enterprise"], stance="organised-against-remedy")
    db.link(conn, ("actor", "mention"), "works_on", ("problem", "p1"),
            by="test", relevance=1)
    db.link(conn, ("actor", "opponent"), "works_on", ("problem", "p1"),
            by="test", relevance=3)
    row = conn.execute("SELECT * FROM problem_coverage WHERE problem_id='p1'").fetchone()
    assert row["uncovered_count"] == 1


def test_coverage_silent_when_needs_legs_unset(conn):
    problem(conn, "p1")
    assert conn.execute("SELECT count(*) c FROM problem_coverage").fetchone()["c"] == 0


def test_tree_walks_multi_parent(conn):
    problem(conn, "root-a"); problem(conn, "root-b"); problem(conn, "node")
    db.link(conn, ("problem", "node"), "part_of", ("problem", "root-a"), by="test")
    db.link(conn, ("problem", "node"), "part_of", ("problem", "root-b"), by="test")
    roots = {r["root"] for r in conn.execute(
        "SELECT root FROM problem_tree WHERE id='node'")}
    assert roots == {"root-a", "root-b"}


def test_stub_is_a_row_with_null_doc(conn):
    problem(conn, "p1")
    db.tag(conn, "problem", "p1", "kind", "leaf", by="test")
    row = conn.execute("SELECT status, doc FROM problem WHERE id='p1'").fetchone()
    assert (row["status"], row["doc"]) == ("stub", None)
    assert db.validate(conn) == [
        "problem/p1: orphan — no parent and not a root kind"]


# ----------------------------------------------------------------- alias -----
def test_resolve_by_alias_ignores_case_and_punctuation(conn):
    actor(conn, "cse")
    db.alias(conn, "actor", "cse", "Centre for Science & Environment", by="test")
    assert db.resolve(conn, "actor", "centre for science  environment") == "cse"
    assert db.resolve(conn, "actor", "cse") == "cse"
    assert db.resolve(conn, "actor", "nobody") is None


def test_resolve_ignores_a_dangling_alias(conn):
    """2026-09-19d: `santoshi-kumari` had an `alias` row committed with no
    matching `actor` row (the insert that should have created it never did,
    or was rolled back separately) — `resolve` trusted the alias anyway and
    handed back a phantom id, which then blew up the first `db.link` that
    tried to use it as a src (`edge.src_id: no such actor`). An alias
    pointing nowhere must resolve to "not an entity", not to a lie."""
    db.alias(conn, "actor", "santoshi-kumari", "Santoshi Kumari", by="test")
    assert db.resolve(conn, "actor", "Santoshi Kumari") is None
    # Once the row actually exists, the same alias resolves normally — the
    # fix is about staleness, not about breaking aliasing altogether.
    actor(conn, "santoshi-kumari")
    assert db.resolve(conn, "actor", "Santoshi Kumari") == "santoshi-kumari"


# ------------------------------------------------- provenance beyond put ------
# tag / alias / CLEAR were added after the first pass, when the module docstring
# claimed every mutation wrote an event and only put() and link() actually did.
# Classification tags are the reason it matters: mechanism, onset, agent and
# gap_kind are tags, so without these a reclassification left no trace while a
# typo fix in one_line was fully audited.
def test_tagging_writes_an_event(conn):
    problem(conn, "p1")
    db.tag(conn, "problem", "p1", "mechanism", "unclassified", by="test")
    row = conn.execute(
        "SELECT field, old, new, by FROM event WHERE field = 'tag:mechanism'"
    ).fetchone()
    assert (row["field"], row["old"], row["new"], row["by"]) == (
        "tag:mechanism", None, "unclassified", "test")


def test_retagging_the_same_value_writes_one_event(conn):
    # INSERT OR IGNORE makes the second call a no-op; the log must agree.
    problem(conn, "p1")
    for _ in range(3):
        db.tag(conn, "problem", "p1", "mechanism", "unclassified", by="test")
    assert conn.execute(
        "SELECT count(*) c FROM event WHERE field = 'tag:mechanism'"
    ).fetchone()["c"] == 1


def test_untagging_writes_the_inverse_event(conn):
    problem(conn, "p1")
    db.tag(conn, "problem", "p1", "mechanism", "unclassified", by="test")
    db.untag(conn, "problem", "p1", "mechanism", "unclassified", by="test")
    old, new = conn.execute(
        "SELECT old, new FROM event WHERE field = 'tag:mechanism' "
        "ORDER BY id DESC").fetchone()[:2]
    assert (old, new) == ("unclassified", None)
    assert db.tags_of(conn, "problem", "p1", "mechanism") == []


def test_aliasing_writes_an_event(conn):
    actor(conn, "cse")
    db.alias(conn, "actor", "cse", "Centre for Science & Environment", by="test")
    assert conn.execute(
        "SELECT new FROM event WHERE field = 'alias'"
    ).fetchone()["new"] == "Centre for Science & Environment"


def test_clear_sets_an_edge_field_to_null(conn):
    """None means leave alone, CLEAR means set NULL. Without the distinction a
    field could never be corrected back to empty once written."""
    problem(conn, "p1")
    problem(conn, "p2")
    db.link(conn, ("problem", "p1"), "part_of", ("problem", "p2"),
            by="test", evidence="first guess")

    db.link(conn, ("problem", "p1"), "part_of", ("problem", "p2"),
            by="test", relevance=2)
    assert conn.execute("SELECT evidence FROM edge").fetchone()[0] == "first guess"

    db.link(conn, ("problem", "p1"), "part_of", ("problem", "p2"),
            by="test", evidence=db.CLEAR)
    assert conn.execute("SELECT evidence FROM edge").fetchone()[0] is None
    assert conn.execute(
        "SELECT old, new FROM event WHERE field = 'evidence' ORDER BY id DESC"
    ).fetchone()[:2] == ("first guess", None)


def test_resolve_rejects_an_unknown_entity_kind(conn):
    # entity_kind reaches an f-string in the SQL, so it is whitelisted.
    with pytest.raises(ValueError):
        db.resolve(conn, "source", "anything")
