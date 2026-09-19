"""The extraction resume point (`05-worker-optimisations.md`, "Handling
failures instead starting from scratch").

What these tests are actually defending: that a second run over an
already-searched candidate does not touch the search provider, does not call
gate 2, and does not re-screen at gate 1 — because those three, not the
extraction call, are where the half hour went. Asserting `report["resumed"]`
alone would pass with all three still running, so each is asserted by
counting its call site instead.

Offline like `tests/test_worker_e6.py`, whose fixtures and stubs this reuses:
`FakeFetch` writes real `source` rows, which matters here more than anywhere
else — `candidate_source.source_id` is an FK into `source`.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlite3

import pytest

vec = pytest.importorskip("sqlite_vec")

from embed import index
from migrate import m0004_candidate_source as mig4
from store import db
from worker import gate1, worker

# `ReplayProvider` here is `test_worker_e6`'s tolerant shadow, not
# `search.provider`'s own — see that module's docstring on it: the
# `channel_*` search families (2026-09-19) postdate the frozen PoC-0b
# recording set, and every test below goes through the full retrievable
# family list incidentally via `worker.run_batch`.
from test_worker_e6 import (BATCHED_JSON, POC0B, PAGE_A, PAGE_B, FakeFetch,
                            ReplayProvider, make_candidate, needs_model,
                            stub_pipeline)


@pytest.fixture
def conn(tmp_path):
    c = index.connect(tmp_path / "g.db")
    yield c
    c.close()


def reopen(conn, cand):
    return conn.execute("SELECT * FROM candidate WHERE id = ?",
                        (cand["id"],)).fetchone()


def unresolve(conn, cand):
    """Put a candidate back in the queue the way `--ids --force` does — the
    real trigger for a second pass. `searched_at` and `candidate_source` are
    deliberately left alone: they are what the second pass is meant to find.
    """
    conn.execute("UPDATE candidate SET resolved_to = NULL WHERE id = ?",
                 (cand["id"],))
    conn.commit()
    return reopen(conn, cand)


# --------------------------------------------------------- 1. recording ----

@needs_model
def test_first_run_records_the_source_set_and_stamps_searched_at(
        conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    worker.run_batch(conn, tmp_path, [cand],
                     search_provider=ReplayProvider(POC0B), max_sources=3)

    rows = conn.execute("SELECT * FROM candidate_source WHERE candidate_id = ?",
                        (cand["id"],)).fetchall()
    assert rows, "the source set was not recorded"
    assert reopen(conn, cand)["searched_at"] is not None

    # The seed is in the set and marked as the seed — `_load_sources` reads
    # `text` back off exactly that row, and resolve/the single-source path
    # both need it.
    seeds = [r for r in rows if r["origin"] == "seed"]
    assert len(seeds) == 1 and seeds[0]["url"] == "https://a.test/one"
    assert {r["origin"] for r in rows} <= {"seed", "search"}
    assert {r["route"] for r in rows} <= {"prompt", "verify"}
    # Every recorded source_id resolves — the FK is real, not invented.
    for r in rows:
        assert conn.execute("SELECT 1 FROM source WHERE id = ?",
                            (r["source_id"],)).fetchone() is not None


def test_searched_at_is_stamped_even_when_the_set_is_empty(
        conn, monkeypatch, tmp_path):
    """"Searched, found nothing" must not read as "never searched" — that is
    the whole reason `searched_at` exists next to a row count."""
    cand = make_candidate(conn, kind="actor", name="Registry Stub Org")
    fetch = FakeFetch(conn, {})
    stub_pipeline(monkeypatch, conn, fetch=fetch, screen_ids=[cand["id"]],
                  extract_json={"claims": [{"field": "one_line", "value": "x"}],
                                "emits": [], "edges": []})

    worker.run_batch(conn, tmp_path, [cand], search_provider=None)

    assert conn.execute("SELECT count(*) c FROM candidate_source").fetchone()["c"] == 0
    assert reopen(conn, cand)["searched_at"] is not None


# ------------------------------------------------------------ 2. resuming --

@needs_model
def test_second_run_skips_search_gate2_and_gate1(conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    worker.run_batch(conn, tmp_path, [cand],
                     search_provider=ReplayProvider(POC0B), max_sources=3)
    first_sources = conn.execute(
        "SELECT source_id FROM candidate_source WHERE candidate_id = ?",
        (cand["id"],)).fetchall()

    # Count the three expensive things on the second pass only.
    searches, confirms, screens = [], [], []
    monkeypatch.setattr(worker.search_stage, "search_sources",
                        lambda *a, **kw: searches.append(kw) or [])
    monkeypatch.setattr(worker.gate2, "confirm",
                        lambda *a, **kw: confirms.append(a) or ("confirmed", 0.9, ""))
    real_screen = gate1.screen
    monkeypatch.setattr(worker.gate1, "screen",
                        lambda items, log=print: screens.append(items) or real_screen(items, log=log))

    report = worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                              search_provider=ReplayProvider(POC0B),
                              max_sources=3)

    assert report["resumed"] == 1
    assert report["resumed_sources"] == len(first_sources)
    assert searches == [], "the search stage ran on a resumed candidate"
    assert confirms == [], "gate 2 re-embedded a resumed candidate's sources"
    # Not called at all: the resumed candidate is the only one in the batch,
    # so `items` is empty and the screen is skipped rather than sent empty.
    assert screens == [], "gate 1 re-screened a resumed candidate"
    # Resumed, not skipped: extraction still ran and the candidate still resolved.
    assert report["extracted"] == 1
    assert reopen(conn, cand)["resolved_to"] is not None


@needs_model
def test_resumed_set_is_the_recorded_set(conn, monkeypatch, tmp_path):
    """The point of resuming is the SAME prompt, one stage later — not a
    cheaper, smaller one."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    first = worker.run_batch(conn, tmp_path, [cand],
                             search_provider=ReplayProvider(POC0B), max_sources=3)
    second = worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                              search_provider=ReplayProvider(POC0B), max_sources=3)

    assert second["sources_in_prompt"] == first["sources_in_prompt"]
    assert second["sources_fetched"] == first["sources_fetched"]


@needs_model
def test_no_resume_redoes_the_search(conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    worker.run_batch(conn, tmp_path, [cand],
                     search_provider=ReplayProvider(POC0B), max_sources=3)

    searches = []
    real = worker.search_stage.search_sources
    monkeypatch.setattr(worker.search_stage, "search_sources",
                        lambda *a, **kw: searches.append(kw) or real(*a, **kw))

    report = worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                              search_provider=ReplayProvider(POC0B),
                              max_sources=3, resume=False)

    assert searches, "--no-resume did not re-run the search stage"
    assert report["resumed"] == 0


@needs_model
def test_resume_rewrites_the_ledger_instead_of_duplicating_it(
        conn, monkeypatch, tmp_path):
    """`write_findings` inserts unconditionally and `finding` has no unique
    key, so without the pre-write clear a resumed candidate's ledger doubles
    every run and `claims_from_findings` starts reconciling a source against
    itself."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    worker.run_batch(conn, tmp_path, [cand],
                     search_provider=ReplayProvider(POC0B), max_sources=3)
    after_first = conn.execute("SELECT count(*) c FROM finding WHERE candidate_id = ?",
                               (cand["id"],)).fetchone()["c"]
    assert after_first > 0

    worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                     search_provider=ReplayProvider(POC0B), max_sources=3)
    after_second = conn.execute("SELECT count(*) c FROM finding WHERE candidate_id = ?",
                                (cand["id"],)).fetchone()["c"]
    assert after_second == after_first


@needs_model
def test_recording_replaces_the_set_rather_than_unioning_it(
        conn, monkeypatch, tmp_path):
    """A `--no-resume` re-search must leave the set some single run produced,
    not the union of two."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    worker.run_batch(conn, tmp_path, [cand],
                     search_provider=ReplayProvider(POC0B), max_sources=3)
    first = {r["source_id"] for r in conn.execute(
        "SELECT source_id FROM candidate_source WHERE candidate_id = ?",
        (cand["id"],))}

    worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                     search_provider=None, resume=False)
    second = {r["source_id"] for r in conn.execute(
        "SELECT source_id FROM candidate_source WHERE candidate_id = ?",
        (cand["id"],))}

    # Second pass had no provider: the seed alone, and the search-sourced
    # rows are gone rather than lingering from the first pass.
    assert second < first


def test_resume_is_disabled_on_a_store_without_the_v4_structures(
        conn, monkeypatch, tmp_path):
    """An unmigrated store loses the feature, not the run."""
    conn.execute("DROP TABLE candidate_source")
    conn.commit()
    cand = make_candidate(conn, kind="actor", name="Registry Stub Org")
    fetch = FakeFetch(conn, {})
    stub_pipeline(monkeypatch, conn, fetch=fetch, screen_ids=[cand["id"]],
                  extract_json={"claims": [{"field": "one_line", "value": "x"}],
                                "emits": [], "edges": []})
    lines = []

    report = worker.run_batch(conn, tmp_path, [cand], search_provider=None,
                              log=lines.append)

    assert report["extracted"] == 1
    assert report["resumed"] == 0
    assert any("schema v4" in line for line in lines)


# --------------------------------------------- 3. the prompt-block cache --

@needs_model
def test_resume_does_no_chunking_or_ranking(conn, monkeypatch, tmp_path):
    """The point of `candidate_prompt`. Resuming from whole source text still
    paid `assemble` — chunk every source, encode every chunk against every
    retrieval question — which is more embedding work than gate 2 does and
    the dominant local cost once the network is out of the picture."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    first = worker.run_batch(conn, tmp_path, [cand],
                             search_provider=ReplayProvider(POC0B), max_sources=3)
    assert first["sources_in_prompt"] >= 1

    assembled = []
    monkeypatch.setattr(worker.extract_mod, "assemble",
                        lambda *a, **kw: assembled.append(a) or ([], {}))

    second = worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                              search_provider=ReplayProvider(POC0B), max_sources=3)

    assert assembled == [], "the resumed run re-ran passage assembly"
    # And it is the SAME prompt, not an empty one that happened not to crash.
    assert second["sources_in_prompt"] == first["sources_in_prompt"]
    assert second["extracted_batched"] == 1


@needs_model
def test_cached_blocks_reproduce_the_labels_and_refs(conn, monkeypatch, tmp_path):
    """`extract_types.py` freezes "label is prompt-local, source_id is
    durable", so the label is not stored — it is re-derived as `S{i}` over
    the stored order. That only reproduces the original if the order is the
    order `assemble` labelled by."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    built = []
    real_assemble = worker.extract_mod.assemble

    def spy(*a, **kw):
        out = real_assemble(*a, **kw)
        built.append(out[0])
        return out
    monkeypatch.setattr(worker.extract_mod, "assemble", spy)

    worker.run_batch(conn, tmp_path, [cand],
                     search_provider=ReplayProvider(POC0B), max_sources=3)
    original = built[0]
    assert original, "nothing was assembled to compare against"

    restored, coverage = worker._load_assembly(conn, str(cand["id"]),
                                               worker.PROMPT_BUCKET)
    assert [s.label for s in restored] == [s.label for s in original]
    assert [s.source_id for s in restored] == [s.source_id for s in original]
    assert [s.chunk_refs for s in restored] == [s.chunk_refs for s in original]
    assert [s.chunk_texts for s in restored] == [s.chunk_texts for s in original]
    assert [s.text for s in restored] == [s.text for s in original]
    # Coverage is stored, not recomputed — E3's counters are a regression
    # detector and a resumed run reporting zeroes would disarm it.
    assert coverage.get("sources_in_prompt", 0) >= 1

    # The label is derived, never persisted (extract_types.py's frozen rule).
    stored = conn.execute(
        "SELECT blocks FROM candidate_prompt WHERE candidate_id = ? AND bucket = ?",
        (cand["id"], worker.PROMPT_BUCKET)).fetchone()["blocks"]
    assert "label" not in stored


@needs_model
def test_no_resume_discards_the_cached_blocks(conn, monkeypatch, tmp_path):
    """Blocks are derived from the source set. Keeping them across a
    re-search would resume a new set into an old prompt — the one way this
    cache could be wrong rather than merely slow."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    worker.run_batch(conn, tmp_path, [cand],
                     search_provider=ReplayProvider(POC0B), max_sources=3)
    before = conn.execute(
        "SELECT blocks FROM candidate_prompt WHERE candidate_id = ? AND bucket = ?",
        (cand["id"], worker.PROMPT_BUCKET)).fetchone()["blocks"]

    worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                     search_provider=None, resume=False)
    after = conn.execute(
        "SELECT blocks FROM candidate_prompt WHERE candidate_id = ? AND bucket = ?",
        (cand["id"], worker.PROMPT_BUCKET)).fetchone()["blocks"]

    # Second pass had no provider — the seed alone, so a strictly smaller set.
    assert after != before


# ------------------------------------------------ 4. the resolution cache --

def ambiguous_candidate(conn, monkeypatch, name="Existing Org Trust"):
    """A candidate whose resolution escalates — and the ONLY case where this
    cache fires at all.

    A candidate that resolves cleanly writes an alias for its own name, so
    `resolve_entity`'s free exact match short-circuits every later run before
    it reaches the encoder; there is nothing left for a cache to save.
    `ambiguous` mints nothing, writes no alias, and leaves `resolved_to` NULL
    — which keeps the candidate in the CLI's `admitted = 1 AND resolved_to IS
    NULL` queue, re-selected and re-encoded on every single run. That is the
    cost this table exists to remove.
    """
    db.put(conn, "actor", {"id": "existing-org", "title": "Existing Org",
                           "type": "org"}, by="test")
    return make_candidate(conn, kind="actor", name=name)


def stub_ambiguous_knn(monkeypatch):
    """In the escalation band (below `resolve.SAFE_MATCH_ABOVE`) and lexically
    overlapping the top hit's title — which is what keeps the verdict
    `ambiguous` rather than rescued to `new`. Applied AFTER `stub_pipeline`,
    which sets its own empty-shortlist `knn`."""
    monkeypatch.setattr(worker.resolve.index, "knn",
                        lambda c, kind, v, *, k=10, role="query", exclude=None:
                        [("existing-org", 0.85)])


@needs_model
def test_resume_reuses_the_resolution_instead_of_re_encoding(
        conn, monkeypatch, tmp_path):
    fetch = FakeFetch(conn, {})
    cand = ambiguous_candidate(conn, monkeypatch)
    stub_pipeline(monkeypatch, conn, fetch=fetch, screen_ids=[cand["id"]],
                  extract_json={"claims": [{"field": "one_line", "value": "x"}],
                                "emits": [], "edges": []})
    stub_ambiguous_knn(monkeypatch)

    first = worker.run_batch(conn, tmp_path, [cand], search_provider=None)
    assert first["resolved_ambiguous"] == 1
    stored = conn.execute("SELECT * FROM candidate_resolution WHERE candidate_id = ?",
                          (cand["id"],)).fetchone()
    assert stored["decision"] == "ambiguous"
    assert reopen(conn, cand)["resolved_to"] is None, (
        "an ambiguous candidate must stay in the escalation queue")

    resolved = []
    monkeypatch.setattr(worker.resolve, "resolve_entity",
                        lambda *a, **kw: resolved.append(a) or None)

    second = worker.run_batch(conn, tmp_path, [reopen(conn, cand)],
                              search_provider=None)

    assert resolved == [], "the resumed run re-encoded to reach the same verdict"
    assert second["resolve_reused"] == 1
    # The report still counts the decision, so a resumed run reads the same as
    # the run that produced it.
    assert second["resolved_ambiguous"] == 1


@needs_model
def test_a_live_alias_hit_beats_the_stored_resolution(conn, monkeypatch, tmp_path):
    """The guard that makes this cache safe. A stored `new` must not be
    replayed as `new` once the graph holds a match for that name — replaying
    it is how a duplicate entity gets minted. `db.resolve` is free, so the
    check costs nothing the cache was meant to save.

    The first run itself moves the graph: resolving `new` mints the entity and
    writes its alias. So the second run's stored row says `new` while the
    alias now says otherwise, which is exactly the stale state under test.
    """
    cand = make_candidate(conn, kind="actor", name="Brand New Org")
    fetch = FakeFetch(conn, {})
    stub_pipeline(monkeypatch, conn, fetch=fetch, screen_ids=[cand["id"]],
                  extract_json={"claims": [{"field": "one_line", "value": "x"}],
                                "emits": [], "edges": []})

    worker.run_batch(conn, tmp_path, [cand], search_provider=None)
    first = conn.execute("SELECT * FROM candidate_resolution WHERE candidate_id = ?",
                         (cand["id"],)).fetchone()
    assert first["decision"] == "new" and first["entity_id"] is None
    minted = reopen(conn, cand)["resolved_to"]
    assert minted and db.resolve(conn, "actor", "Brand New Org") == minted

    resolved = []
    real = worker.resolve.resolve_entity
    monkeypatch.setattr(worker.resolve, "resolve_entity",
                        lambda *a, **kw: resolved.append(a) or real(*a, **kw))
    lines = []

    report = worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                              search_provider=None, log=lines.append)

    assert resolved, "the stale `new` was replayed instead of re-resolved"
    assert report["resolve_reused"] == 0
    assert any("superseded" in line for line in lines)
    # THE assertion: it lands on the entity the alias names, and mints no
    # second one for the same name.
    assert reopen(conn, cand)["resolved_to"] == minted
    assert conn.execute("SELECT count(*) c FROM actor").fetchone()["c"] == 1


@needs_model
def test_a_stored_resolution_pointing_at_a_gone_entity_falls_through(
        conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    worker.run_batch(conn, tmp_path, [cand],
                     search_provider=ReplayProvider(POC0B), max_sources=3)
    entity_id = reopen(conn, cand)["resolved_to"]
    assert entity_id

    # Point the stored row at something that does not exist, the way a merge
    # or a delete would leave it.
    conn.execute("UPDATE candidate_resolution SET entity_id = 'gone-entity', "
                 "decision = 'shortlist_top' WHERE candidate_id = ?", (cand["id"],))
    conn.execute("DELETE FROM alias WHERE entity_id = ?", (entity_id,))
    conn.commit()

    resolved = []
    real = worker.resolve.resolve_entity
    monkeypatch.setattr(worker.resolve, "resolve_entity",
                        lambda *a, **kw: resolved.append(a) or real(*a, **kw))
    lines = []

    report = worker.run_batch(conn, tmp_path, [unresolve(conn, cand)],
                              search_provider=ReplayProvider(POC0B),
                              max_sources=3, log=lines.append)

    assert resolved, "claims were written against an entity that is gone"
    assert report["resolve_reused"] == 0
    assert any("is gone" in line for line in lines)


# ----------------------------------------------------------- 5. migration --

def _v3_db(path) -> sqlite3.Connection:
    """A hand-built v3 database — `candidate` as schema.sql had it before
    v4, so the test exercises the real pre->post transition."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE source (id TEXT PRIMARY KEY);
        CREATE TABLE candidate (
          id         INTEGER PRIMARY KEY,
          kind       TEXT NOT NULL CHECK (kind IN ('problem', 'actor')),
          name       TEXT NOT NULL,
          url        TEXT,
          evidence   TEXT,
          first_seen TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO meta (key, value) VALUES ('schema_version', '3');
        INSERT INTO candidate (id, kind, name) VALUES (1, 'actor', 'Some Org');
    """)
    conn.commit()
    return conn


def test_v3_db_migrates_to_v4_with_no_backfill(tmp_path):
    path = tmp_path / "v3.db"
    _v3_db(path).close()

    conn = sqlite3.connect(path)
    assert mig4.migrate(conn) is True

    cols = {row[1] for row in conn.execute("PRAGMA table_info(candidate)")}
    assert "searched_at" in cols
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"candidate_source", "candidate_prompt",
            "candidate_resolution"} <= tables
    assert conn.execute("SELECT value FROM meta WHERE key = 'schema_version'"
                        ).fetchone()[0] == "4"
    # No backfill — an already-processed candidate searches once more, then
    # resumes like any other. The membership it would need was never stored.
    assert conn.execute("SELECT searched_at FROM candidate WHERE id = 1"
                        ).fetchone() == (None,)
    conn.close()


def test_m0004_migration_is_idempotent(tmp_path):
    path = tmp_path / "v3.db"
    _v3_db(path).close()

    conn = sqlite3.connect(path)
    first = mig4.migrate(conn)
    second = mig4.migrate(conn)
    conn.close()

    assert first is True
    assert second is False


def test_schema_sql_and_the_migration_agree(tmp_path):
    """The two definitions of `candidate_source` must not drift — a fresh
    store (schema.sql) and a migrated one (m0004) have to be the same shape,
    or a resume works on one and not the other."""
    fresh = db.connect(tmp_path / "fresh.db")
    fresh_cols = {t: [(r[1], r[2]) for r in fresh.execute(
        f"PRAGMA table_info({t})")]
        for t in ("candidate_source", "candidate_prompt", "candidate_resolution")}
    fresh.close()

    path = tmp_path / "v3.db"
    _v3_db(path).close()
    migrated = sqlite3.connect(path)
    mig4.migrate(migrated)
    migrated_cols = {t: [(r[1], r[2]) for r in migrated.execute(
        f"PRAGMA table_info({t})")]
        for t in ("candidate_source", "candidate_prompt", "candidate_resolution")}
    migrated.close()

    assert fresh_cols == migrated_cols
    # Not `==`: this went stale at m0005 (chunk_text) and again would have at
    # m0006/m0007 had it stayed an equality check — `db.SCHEMA_VERSION` is
    # the CURRENT latest migration's target, not m0004's specifically, so it
    # moves forward every time a migration ships while m0004's own
    # TARGET_VERSION never does. The real invariant this test protects
    # (`fresh_cols == migrated_cols`, above) doesn't need this line at all;
    # kept only as a sanity check that the schema has moved forward from
    # m0004, never backward.
    assert int(db.SCHEMA_VERSION) >= int(mig4.TARGET_VERSION)
