"""Migration against the real corpus.

Asserts shape and the facts that would silently break — a leaf losing its
parent, an actor edge losing its weight, the browse tree losing a level.
Totals are floors, not equalities, because the corpus grows.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from migrate.from_corpus import run
from store import db

CORPUS = pathlib.Path(__file__).resolve().parents[2] / "problems"


@pytest.fixture(scope="module")
def migrated(tmp_path_factory):
    if not CORPUS.exists():
        pytest.skip("corpus not present")
    # 01-minimal.md §11 item 3b-B: corpus markdown is prose-only now (the
    # frontmatter this module parses was stripped on 2026-09-13; graph.db is
    # the durable source, no longer derived from problems/ on every run).
    # `run()` against today's corpus correctly migrates almost nothing — that
    # is not a regression in from_corpus.py, it is the frontmatter being
    # gone. These fixture-count assertions test the parser against a live
    # corpus that no longer carries what they're checking for; skip until a
    # frozen pre-3b-B fixture snapshot replaces `CORPUS` here (§12 debt).
    sample = next((CORPUS / "actors").glob("*.md"), None)
    if sample is None or not sample.read_text().startswith("---"):
        pytest.skip("corpus frontmatter removed by 3b-B — needs a frozen "
                     "fixture snapshot, see 01-minimal.md §12")
    out = tmp_path_factory.mktemp("graph") / "graph.db"
    report = run(CORPUS, out)
    conn = db.connect(out, create=False)
    yield conn, report
    conn.close()


def test_every_markdown_record_arrives(migrated):
    conn, report = migrated
    assert report.counts["need"] == 36
    assert report.counts["leaf"] >= 7
    assert report.counts["node"] == 6
    assert report.counts["actor"] >= 289


def test_needs_are_roots_and_leaves_are_not(migrated):
    conn, _ = migrated
    orphan_needs = conn.execute("""
        SELECT count(*) c FROM tag t
        WHERE t.ns = 'kind' AND t.value = 'leaf'
          AND NOT EXISTS (SELECT 1 FROM edge e WHERE e.src_kind = 'problem'
                          AND e.src_id = t.entity_id AND e.kind = 'part_of')
          AND (SELECT doc FROM problem WHERE id = t.entity_id) IS NOT NULL
    """).fetchone()["c"]
    assert orphan_needs == 0, "a written leaf lost its parent need"


def test_nodes_are_multi_parent(migrated):
    conn, _ = migrated
    # This is the whole reason parentage is an edge rather than a column.
    parents = conn.execute("""
        SELECT count(*) c FROM edge
        WHERE src_kind = 'problem' AND src_id = 'energy' AND kind = 'part_of'
    """).fetchone()["c"]
    assert parents == 5


def test_tree_reaches_leaves_through_needs(migrated):
    conn, _ = migrated
    row = conn.execute(
        "SELECT root, depth FROM problem_tree WHERE id = 'cookfire-smoke'"
    ).fetchone()
    assert (row["root"], row["depth"]) == ("air", 1)


def test_primary_role_survives_as_weight(migrated):
    conn, _ = migrated
    weights = dict(conn.execute(
        "SELECT relevance, count(*) FROM edge WHERE kind = 'works_on' GROUP BY 1"))
    assert weights.get(3, 0) >= 13, "role: primary lost its weight"
    assert weights.get(2, 0) >= 279


def test_dangling_leaf_reference_becomes_a_stub_not_a_drop(tmp_path):
    """Constructed, not observed. This used to assert against two real dangling
    ids in the corpus; they were repointed on 2026-09-13, and a test that only
    holds while the corpus is in debt stops testing the mechanism the moment
    the debt is paid. Inventing a parent for an unwritten leaf would be
    inventing research, so the stub with no parent is the designed outcome."""
    actors = tmp_path / "actors"
    actors.mkdir(parents=True)
    (actors / "ghost-org.md").write_text(
        "---\nslug: ghost-org\nname: Ghost Org\ntype: org\nleg: [activism]\n"
        "leaves: [never-written-leaf]\n---\n\n# Ghost Org\n")
    (tmp_path / "tier-failure-history").mkdir()
    (tmp_path / "tier-failure-history" / "needs.yaml").write_text("needs: []\n")

    out = tmp_path / "graph.db"
    run(tmp_path, out)
    conn = db.connect(out, create=False)
    try:
        row = conn.execute(
            "SELECT status, doc FROM problem WHERE id = 'never-written-leaf'"
        ).fetchone()
        assert (row["status"], row["doc"]) == ("stub", None)
        assert conn.execute(
            "SELECT count(*) c FROM edge WHERE dst_id = 'never-written-leaf' "
            "AND kind = 'works_on'").fetchone()["c"] == 1
        assert any("never-written-leaf" in line for line in db.validate(conn)), \
            "an unparented stub must show as validation debt, not pass silently"
    finally:
        conn.close()


def test_yaml_booleans_come_back_as_words(migrated):
    conn, _ = migrated
    # `affected_led: no` parses as False under YAML 1.1 and would fail the CHECK.
    values = {r["affected_led"] for r in conn.execute(
        "SELECT DISTINCT affected_led FROM actor")}
    assert values <= {"yes", "no", "partial", None}
    assert "no" in values


def test_channels_and_asks_land(migrated):
    conn, report = migrated
    assert report.counts["channel"] >= 655
    assert report.counts["ask_need"] >= 142
    assert conn.execute("SELECT count(*) c FROM ask WHERE direction='offer'"
                        ).fetchone()["c"] >= 240


def test_citations_become_sources_deduped_by_canonical_url(migrated):
    conn, _ = migrated
    sources = conn.execute("SELECT count(*) c FROM source").fetchone()["c"]
    cites = conn.execute("SELECT count(*) c FROM edge WHERE kind='cites'").fetchone()["c"]
    assert sources <= cites, "canonicalization should collapse repeats, not add rows"
    assert conn.execute(
        "SELECT count(*) c FROM source WHERE fetched_at IS NULL").fetchone()["c"] == sources


def test_recorded_gap_survives_as_tags(migrated):
    conn, _ = migrated
    assert db.tags_of(conn, "problem", "north-india-winter-smog", "gap_kind") == \
        ["representation"]
    assert db.tags_of(conn, "problem", "small-industrial-town-air",
                      "gap_missing_leg") == ["activism", "enterprise"]


def test_coverage_floor_is_coarser_than_the_recorded_finding(migrated):
    conn, _ = migrated
    # 25 enterprise actors, and the leaf still records a missing enterprise slot.
    row = conn.execute(
        "SELECT * FROM problem_coverage WHERE problem_id='crop-residue-burning'"
    ).fetchone()
    assert "enterprise" not in (row["uncovered_legs"] or "")
    assert "enterprise" in db.tags_of(conn, "problem", "crop-residue-burning",
                                      "gap_missing_leg")


def test_migration_leaves_no_validation_debt(migrated):
    """Was two known orphans — `asbestos-import-legal` and
    `ambient-asbestos-demolition-dust`, merged into `asbestos-in-air` on
    2026-09-09 but still named by actor/gopal-krishna until 2026-09-13. Now
    empty, and it should stay that way: anything here is a real reference to a
    record that does not exist, which is a corpus fix, not a test to update."""
    conn, _ = migrated
    assert db.validate(conn) == []


def test_every_write_is_in_the_event_log(migrated):
    conn, _ = migrated
    rows = conn.execute("SELECT count(*) c FROM event WHERE by='migration'").fetchone()["c"]
    entities = conn.execute(
        "SELECT count(*) c FROM problem").fetchone()["c"] + conn.execute(
        "SELECT count(*) c FROM actor").fetchone()["c"] + conn.execute(
        "SELECT count(*) c FROM edge").fetchone()["c"]
    assert rows >= entities


# --------------------------------------------------- two-sided assertions -----
def test_mutual_node_assertion_is_kept_not_overwritten(migrated):
    """An actor file's `nodes:` and a node file's `actors:` can name the same
    edge. The node pass used to overwrite the actor pass, discarding the fact
    that both records independently asserted it — which is stronger evidence
    than either alone, so the evidence string records which happened."""
    conn, _ = migrated
    both = conn.execute(
        "SELECT count(*) c FROM edge WHERE kind = 'works_on' "
        "AND evidence = 'node actors: + actor nodes:'").fetchone()["c"]
    one_side = conn.execute(
        "SELECT count(*) c FROM edge WHERE kind = 'works_on' "
        "AND evidence IN ('node', 'node actors:')").fetchone()["c"]
    assert both > 0, "no two-sided node edge survived — the merge regressed"
    assert one_side > 0, "every node edge reads as two-sided — the merge is too eager"


def test_tags_and_aliases_are_in_the_event_log(migrated):
    """The >= floor in test_every_write_is_in_the_event_log cannot see this:
    it passed both before and after tag/alias provenance existed."""
    conn, _ = migrated
    tags_written = conn.execute("SELECT count(*) c FROM tag").fetchone()["c"]
    tag_events = conn.execute(
        "SELECT count(*) c FROM event WHERE field LIKE 'tag:%'").fetchone()["c"]
    aliases = conn.execute("SELECT count(*) c FROM alias").fetchone()["c"]
    alias_events = conn.execute(
        "SELECT count(*) c FROM event WHERE field = 'alias'").fetchone()["c"]
    assert tag_events == tags_written
    assert alias_events == aliases


def test_run_refuses_to_overwrite_existing_output_unconditionally(tmp_path):
    """The default --out is problems/graph.db, so an unguarded re-run deletes
    a real file. There is no override — 2026-09-15, after a live `graph.db`
    (11 candidates, 92 sources, 524 edges, worker-pipeline data with no
    markdown representation) was wiped by exactly this path via `--force`.
    Recovering a live store now goes through `migrate/restamp.py`, which
    never deletes anything; a genuine from-scratch rebuild is `rm` by hand
    plus a bare re-run, not a flag this function accepts."""
    out = tmp_path / "graph.db"
    out.write_text("not a database")
    with pytest.raises(FileExistsError):
        run(CORPUS, out)
    assert out.read_text() == "not a database"
