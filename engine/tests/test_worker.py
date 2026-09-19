"""Build step 3 — worker, gates, resolver. Offline by default: every test
that would otherwise touch a network or an API key monkeypatches `worker.llm`
(and, where the real encoder would load, `embed.model`/`embed.index`).
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
import math
import sqlite3
import time

import pytest

vec = pytest.importorskip("sqlite_vec")

from embed import index
from embed.model import EMBED_DIM, MODEL_NAME
from store import db
from worker import fetch as fetchmod
from worker import gate1, gate2, llm, resolve, worker
from worker.prompts import extract_prompt, screen_prompt

needs_model = pytest.mark.skipif(
    not pathlib.Path.home().joinpath(
        ".cache/huggingface/hub",
        "models--" + MODEL_NAME.replace("/", "--")).exists(),
    reason=f"{MODEL_NAME} not downloaded")


@pytest.fixture
def conn(tmp_path):
    c = index.connect(tmp_path / "g.db")
    yield c
    c.close()


def unit(*head) -> list[float]:
    v = list(head) + [0.0] * (EMBED_DIM - len(head))
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def problem(c, pid, **kw):
    return db.put(c, "problem", {"id": pid, "title": pid, **kw}, by="test")


def actor(c, aid, **kw):
    row = {"id": aid, "title": aid, "type": "org", **kw}
    return db.put(c, "actor", row, by="test")


def make_candidate(c, kind="actor", name="Some Org", url=None, evidence=None,
                   admitted=1):
    cur = c.execute(
        "INSERT INTO candidate (kind, name, url, evidence, admitted) "
        "VALUES (?, ?, ?, ?, ?)", (kind, name, url, evidence, admitted))
    c.commit()
    return c.execute("SELECT * FROM candidate WHERE id = ?",
                     (cur.lastrowid,)).fetchone()


# ------------------------------------------------------------- prompts.py ---

def test_screen_prompt_names_every_candidate_id():
    items = [{"id": 1, "name": "Alpha", "snippet": "", "url": ""},
             {"id": 2, "name": "Beta", "snippet": "", "url": ""}]
    system, prompt = screen_prompt(items)
    assert "1" in prompt and "2" in prompt and "Alpha" in prompt and "Beta" in prompt
    assert "keep" in system.lower() and "json" in system.lower()


def test_screen_prompt_is_tuned_for_recall():
    system, _ = screen_prompt([{"id": 1, "name": "X"}])
    # The instruction to bias toward keeping must be explicit in the prompt
    # text itself, not just in this module's docstring (01-minimal.md §5).
    assert "keep" in system.lower()
    assert "bias" in system.lower() or "recall" in system.lower() or \
        "when in doubt" in system.lower()


def test_extract_prompt_names_the_entity():
    _, prompt = extract_prompt("problem", "Cookfire smoke", "some source text")
    assert "Cookfire smoke" in prompt and "some source text" in prompt


def test_extract_prompt_problem_and_actor_are_different_system_prompts():
    problem_system, _ = extract_prompt("problem", "X", "t")
    actor_system, _ = extract_prompt("actor", "X", "t")
    assert problem_system != actor_system
    assert "mechanism" in problem_system.lower()
    assert "leg" in actor_system.lower() or "enterprise" in actor_system.lower()


def test_extract_prompt_rejects_an_unknown_kind():
    with pytest.raises(ValueError, match="kind must be"):
        extract_prompt("node", "X", "t")


def test_extract_prompt_with_empty_text_forbids_name_only_guessing():
    """2026-09-15: a bare registry row (no fetched text) used to be told to
    "extract what you can from the name alone" — letting one_line and other
    claims get fabricated from nothing. Now it's told the opposite."""
    _, prompt = extract_prompt("actor", "Some Org", "")
    assert "extract what you can from the name alone" not in prompt
    assert "not content" in prompt

    _, prompt_ws = extract_prompt("actor", "Some Org", "   \n  ")
    assert "not content" in prompt_ws


def test_extract_prompt_with_real_text_does_not_carry_the_empty_case_wording():
    _, prompt = extract_prompt("actor", "Some Org", "Some Org runs a clinic.")
    assert "not content" not in prompt
    assert "Some Org runs a clinic." in prompt


# --------------------------------------------------------------- gate1.py ---

def test_gate1_parses_a_well_formed_response(monkeypatch):
    def fake_call(prompt, **kw):
        return {"json": {"decisions": [
            {"id": "1", "keep": True, "reason": "on topic"},
            {"id": "2", "keep": False, "reason": "spam"},
        ]}, "model": "m"}
    monkeypatch.setattr(gate1.llm, "call", fake_call)
    out, cost = gate1.screen([{"id": "1", "name": "A"}, {"id": "2", "name": "B"}])
    assert out["1"] == (True, "on topic")
    assert out["2"] == (False, "spam")


def test_gate1_defaults_a_missing_id_to_keep(monkeypatch):
    def fake_call(prompt, **kw):
        return {"json": {"decisions": [{"id": "1", "keep": False, "reason": "no"}]}}
    monkeypatch.setattr(gate1.llm, "call", fake_call)
    out, cost = gate1.screen([{"id": "1", "name": "A"}, {"id": "2", "name": "B"}])
    assert out["1"] == (False, "no")
    assert out["2"][0] is True


def test_gate1_defaults_the_whole_batch_to_keep_on_llm_error(monkeypatch):
    def fake_call(prompt, **kw):
        raise llm.LLMError("all providers failed")
    monkeypatch.setattr(gate1.llm, "call", fake_call)
    out, cost = gate1.screen([{"id": "1", "name": "A"}, {"id": "2", "name": "B"}])
    assert out["1"][0] is True and "gate1 unavailable" in out["1"][1]
    assert out["2"][0] is True


def test_gate1_reports_cost(monkeypatch):
    def fake_call(prompt, **kw):
        return {"json": {"decisions": [{"id": "1", "keep": True, "reason": "ok"}]},
                "cost": 0.0042}
    monkeypatch.setattr(gate1.llm, "call", fake_call)
    out, cost = gate1.screen([{"id": "1", "name": "A"}])
    assert cost == pytest.approx(0.0042)


def test_gate1_non_object_json_defaults_to_keep(monkeypatch):
    """A model returning a bare JSON array has no `.get` — must not crash."""
    def fake_call(prompt, **kw):
        return {"json": [1, 2, 3], "cost": 0.0}
    monkeypatch.setattr(gate1.llm, "call", fake_call)
    out, cost = gate1.screen([{"id": "1", "name": "A"}])
    assert out["1"][0] is True


# --------------------------------------------------------------- gate2.py ---

def test_gate2_bands_are_pure_math(monkeypatch):
    """Stub the encoder so the banding logic is tested without downloading
    the real model."""
    vectors = {
        "high query": unit(1.0),
        "high text": unit(0.999, 0.001),
        "low query": unit(1.0),
        "low text": unit(0.0, 1.0),
        "mid query": unit(1.0),
        "mid text": unit(0.8, 0.6),
    }

    def fake_encode_one(text, *, role):
        return vectors[text]

    monkeypatch.setattr(gate2, "encode_one", fake_encode_one)

    verdict, cosine, note = gate2.confirm(None, "high query", "", "high text")
    assert verdict == "confirmed" and note == ""

    verdict, cosine, note = gate2.confirm(None, "low query", "", "low text")
    assert verdict == "mismatch"

    verdict, cosine, note = gate2.confirm(None, "mid query", "", "mid text")
    assert verdict == "uncertain" and note


def test_gate2_empty_input_is_uncertain_not_a_crash(monkeypatch):
    verdict, cosine, note = gate2.confirm(None, "", "", "")
    assert verdict == "uncertain" and cosine == 0.0 and note


def test_gate2_long_context_is_fit_before_encode(monkeypatch):
    """candidate_context can be the full extracted text, not just a snippet
    (production case: candidate 28's run, 2026-09-14T22:45, hit an
    8.7x-over-budget string past `clip()`'s character bound and hung the
    worker inside `encode_one` with no exception). `left`/`right` must be
    bounded by `fit()` — token-exact, not char-based — before they reach
    `encode_one`."""
    seen = {}

    def recording_encode_one(text, *, role):
        seen.setdefault(role, []).append(text)
        return unit(1.0)

    # `fit()` itself needs the real encoder (to tokenize) — stub it here so
    # this test stays offline, same as `encode_one` above, per this file's
    # own "offline by default" contract (module docstring).
    monkeypatch.setattr(gate2, "encode_one", recording_encode_one)
    monkeypatch.setattr(gate2, "fit", lambda text, *, role: text[:2000])
    long_context = "word " * 3000  # far past any reasonable token budget
    gate2.confirm(None, "Some Org", long_context, "short fetched text")
    left_sent = seen["query"][0]
    assert len(left_sent) <= 2000, "candidate_context was not fit before encode_one"


@needs_model
def test_gate2_real_encoder_smoke():
    verdict, cosine, note = gate2.confirm(
        None, "Mine Labour Protection Campaign", "silicosis Rajasthan",
        "Mine Labour Protection Campaign works on silicosis in Rajasthan.")
    assert verdict in ("confirmed", "uncertain", "mismatch")
    assert isinstance(cosine, float)


# -------------------------------------------------------------- resolve.py --

def test_exact_match_short_circuits_before_any_embedding_call(conn, monkeypatch):
    actor(conn, "mlpc", title="Mine Labour Protection Campaign")
    db.alias(conn, "actor", "mlpc", "MLPC", by="test")

    def boom(*a, **kw):
        raise AssertionError("knn should not be called on an exact/alias hit")
    monkeypatch.setattr(resolve.index, "knn", boom)
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: boom())

    result = resolve.resolve_entity(conn, pathlib.Path("."), "actor", "MLPC", "")
    assert result.decision == "exact" and result.entity_id == "mlpc"


def test_resolve_long_context_is_fit_before_encode(conn, monkeypatch):
    """`context` can be the full extracted/fetched text (worker.py passes
    the candidate's own extraction text or raw evidence), unbounded — must
    be bounded by `fit()` before `encode_one`, same fix as gate2.confirm's
    `left`."""
    seen = {}

    def recording_encode_one(text, *, role):
        seen["text"] = text
        return unit(1.0)

    monkeypatch.setattr(resolve, "encode_one", recording_encode_one)
    monkeypatch.setattr(resolve, "fit", lambda text, *, role: text[:2000])
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])

    long_context = "word " * 3000
    resolve.resolve_entity(conn, pathlib.Path("."), "actor", "Some Org", long_context)
    assert len(seen["text"]) <= 2000, "context was not fit before encode_one"


def test_new_id_slugifies_and_dedupes_on_collision(conn):
    assert resolve.new_id(conn, "actor", "Mine Labour Protection Campaign!") == \
        "mine-labour-protection-campaign"
    actor(conn, "mine-labour-protection-campaign")
    assert resolve.new_id(conn, "actor", "Mine Labour Protection Campaign!") == \
        "mine-labour-protection-campaign-2"
    actor(conn, "mine-labour-protection-campaign-2")
    assert resolve.new_id(conn, "actor", "Mine Labour Protection Campaign!") == \
        "mine-labour-protection-campaign-3"


def test_new_id_avoids_a_former_id_held_only_as_an_alias(conn):
    actor(conn, "real-id")
    db.alias(conn, "actor", "real-id", "old-slug", by="test")
    assert resolve.new_id(conn, "actor", "old-slug") == "old-slug-2"


def test_shortlist_above_the_safe_band_is_shortlist_top(conn, monkeypatch):
    actor(conn, "existing")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [("existing", 0.95)])
    result = resolve.resolve_entity(conn, pathlib.Path("."), "actor", "New Name", "ctx")
    assert result.decision == "shortlist_top" and result.entity_id == "existing"


def test_shortlist_below_the_safe_band_but_lexically_overlapping_is_ambiguous(conn, monkeypatch):
    # "Existing Org" vs title "existing" shares the distinctive token
    # "existing" — cosine alone can't decide, and the lexical check agrees
    # there might be a real match, so this stays the genuinely hard case.
    actor(conn, "existing")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [("existing", 0.85)])
    result = resolve.resolve_entity(conn, pathlib.Path("."), "actor", "Existing Org", "ctx")
    assert result.decision == "ambiguous"
    assert result.entity_id is None
    assert result.shortlist == [("existing", 0.85)]


def test_shortlist_below_the_safe_band_with_no_lexical_overlap_is_new(conn, monkeypatch):
    # Found live 2026-09-13: a real sweep named three real new actors (RESET
    # Air, GBCI/USGBC LEED Arc, GMDA) whose top shortlist hits were all
    # unrelated Delhi air-quality orgs at cosine 0.83-0.85 — topically close,
    # not the same identity. Before this fix every one of them came back
    # `ambiguous` forever, because a non-empty shortlist (which is every
    # shortlist, once the store has any real size) could never resolve "new".
    actor(conn, "existing")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [("existing", 0.85)])
    result = resolve.resolve_entity(conn, pathlib.Path("."), "actor", "New Name", "ctx")
    assert result.decision == "new"
    assert result.entity_id is None


def test_empty_shortlist_is_new(conn, monkeypatch):
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])
    result = resolve.resolve_entity(conn, pathlib.Path("."), "actor", "New Name", "ctx")
    assert result.decision == "new"


# ---------------------------------------------------------------- fetch.py --

def test_fetch_cache_hit_never_touches_the_network(conn, monkeypatch, tmp_path):
    conn.execute(
        "INSERT INTO source (id, url, url_canonical, page_state, words, "
        "fetched_at, path) VALUES ('abc', 'https://x.test/a', "
        "'https://x.test/a', 'ok', 50, datetime('now'), NULL)")
    conn.commit()

    def boom(*a, **kw):
        raise AssertionError("requests.get should not be called on a cache hit")
    monkeypatch.setattr(fetchmod, "requests", type("R", (), {"get": staticmethod(boom)}))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/a")
    assert result.cache_hit is True
    assert result.state.state == "ok"


def test_fetch_cache_hit_returns_the_cached_text(conn, monkeypatch, tmp_path):
    """The regression that made the cache write-only.

    `_upsert_source` stores `path` RELATIVE to `corpus`; `_row_to_result` used
    to resolve it with a bare `Path(row["path"])`, i.e. against the process
    CWD. Every cache hit therefore came back `text=None` while the row still
    reported its word count — so callers saw a usable page with no text and
    dropped it, and the PoC harness mislabelled those drops "OFF-TOPIC".

    The test above did not catch it because it inserts `path=NULL`. This one
    writes a real file at the real relative location.
    """
    body = "cached body word " * 60
    dest = tmp_path / fetchmod.CACHE_SUBDIR / "abc.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body)
    rel = str(dest.relative_to(tmp_path))          # what _upsert_source writes
    conn.execute(
        "INSERT INTO source (id, url, url_canonical, page_state, words, "
        "fetched_at, path) VALUES ('abc', 'https://x.test/c', "
        "'https://x.test/c', 'ok', 180, datetime('now'), ?)", (rel,))
    conn.commit()

    def boom(*a, **kw):
        raise AssertionError("requests.get should not be called on a cache hit")
    monkeypatch.setattr(fetchmod, "requests", type("R", (), {"get": staticmethod(boom)}))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/c")
    assert result.cache_hit is True
    assert result.text == body, "cache hit must return the cached text"
    assert result.error is None


def test_fetch_cache_hit_reports_missing_text_instead_of_dropping_it(
        conn, monkeypatch, tmp_path):
    """A usable row whose text file is gone is a cache defect, not a fact
    about the page. It must be reported, not returned as a bare None that
    looks identical to a blocked page."""
    conn.execute(
        "INSERT INTO source (id, url, url_canonical, page_state, words, "
        "fetched_at, path) VALUES ('gone', 'https://x.test/d', "
        "'https://x.test/d', 'ok', 180, datetime('now'), "
        "'problems/private/sources/gone.txt')")
    conn.commit()
    monkeypatch.setattr(fetchmod, "requests",
                        type("R", (), {"get": staticmethod(
                            lambda *a, **kw: (_ for _ in ()).throw(
                                AssertionError("no network on a cache hit")))}))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/d")
    assert result.text is None
    assert result.error is not None and "missing on disk" in result.error
    assert "180w" in result.error, "the error should carry what was lost"


def test_fetch_cache_hit_honours_an_absolute_legacy_path(conn, monkeypatch, tmp_path):
    """Rows written before the relative-path convention stored an absolute
    path. Those must still resolve."""
    dest = tmp_path / "elsewhere" / "legacy.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("legacy body " * 40)
    conn.execute(
        "INSERT INTO source (id, url, url_canonical, page_state, words, "
        "fetched_at, path) VALUES ('leg', 'https://x.test/e', "
        "'https://x.test/e', 'ok', 80, datetime('now'), ?)", (str(dest),))
    conn.commit()
    monkeypatch.setattr(fetchmod, "requests", type("R", (), {"get": staticmethod(
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no network")))}))

    result = fetchmod.fetch(conn, tmp_path, "https://x.test/e")
    assert result.text is not None and "legacy body" in result.text


def test_fetch_runs_a_mocked_response_through_pagestate(conn, monkeypatch, tmp_path):
    class FakeResp:
        text = "<html><body><p>" + ("real content word " * 150) + "</p></body></html>"
        status_code = 200

    class FakeRequests:
        @staticmethod
        def get(*a, **kw):
            return FakeResp()
        RequestException = Exception

    monkeypatch.setattr(fetchmod, "requests", FakeRequests)
    result = fetchmod.fetch(conn, tmp_path, "https://x.test/b")
    assert result.state.state == "ok"
    assert result.text and "real content" in result.text
    row = conn.execute("SELECT * FROM source WHERE url_canonical = ?",
                       ("https://x.test/b",)).fetchone()
    assert row["fetched_at"] is not None
    assert row["path"] is not None
    assert (tmp_path / row["path"]).exists()


def test_fetch_network_failure_degrades_without_raising(conn, monkeypatch, tmp_path):
    class Boom(Exception):
        pass

    class FakeRequests:
        RequestException = Boom
        @staticmethod
        def get(*a, **kw):
            raise Boom("connection refused")

    monkeypatch.setattr(fetchmod, "requests", FakeRequests)
    result = fetchmod.fetch(conn, tmp_path, "https://x.test/c")
    assert result.text is None
    assert result.state.usable is False


def test_fetch_is_safe_to_call_concurrently_on_one_connection(
        conn, monkeypatch, tmp_path):
    """`worker/search_stage.py` now calls `fetch(url)` for several URLs from
    a thread pool sharing one `conn` (store/db.py's `connect` opens it with
    check_same_thread=False for exactly this). Every real network GET must
    land its own row with no interleaving/corruption, and none must raise —
    the failure mode this guards is a sqlite `ProgrammingError` from
    cross-thread use, or a lost/garbled row from two threads writing without
    `fetchmod._DB_LOCK` serializing them."""
    import threading

    class FakeResp:
        def __init__(self, url):
            self.text = ("<html><body><p>content for " + url + " "
                        + ("word " * 150) + "</p></body></html>")
            self.status_code = 200

    class FakeRequests:
        RequestException = Exception
        @staticmethod
        def get(url, *a, **kw):
            time.sleep(0.05)  # give threads a real window to interleave in
            return FakeResp(url)

    monkeypatch.setattr(fetchmod, "requests", FakeRequests)

    urls = [f"https://x.test/concurrent-{i}" for i in range(8)]
    results = [None] * len(urls)
    errors = []

    def run(i, url):
        try:
            results[i] = fetchmod.fetch(conn, tmp_path, url)
        except Exception as e:  # pragma: no cover - failure path under test
            errors.append(e)

    threads = [threading.Thread(target=run, args=(i, u))
              for i, u in enumerate(urls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"fetch() raised under concurrent use: {errors}"
    assert all(r is not None and r.text and u in r.text
              for r, u in zip(results, urls)), \
        "a result's text does not match its own url — cross-thread corruption"

    rows = conn.execute("SELECT url_canonical FROM source").fetchall()
    assert {r["url_canonical"] for r in rows} == set(urls), \
        "not every concurrently-fetched url landed its own row"


# --------------------------------------------------------------- worker.py --

def _stub_llm_for_run_batch(monkeypatch, *, screen_decisions, extract_json):
    def fake_call(prompt, *, system=None, tier="mechanical", max_tokens=2048, **kw):
        if "decisions" in prompt or "Screen these candidates" in prompt:
            return {"json": {"decisions": screen_decisions}, "model": "test-model",
                    "cost": 0.0}
        return {"json": extract_json, "model": "test-model", "cost": 0.001}
    monkeypatch.setattr(worker.llm, "call", fake_call)
    monkeypatch.setattr(gate1.llm, "call", fake_call)


def test_run_batch_end_to_end_new_shortlist_and_ambiguous(conn, monkeypatch, tmp_path):
    # Fixture: one existing actor for the shortlist/ambiguous candidates to
    # find, and three fresh candidates covering the three live outcomes.
    actor(conn, "existing-org", title="Existing Org")

    c_new = make_candidate(conn, kind="actor", name="Brand New Org")
    c_shortlist = make_candidate(conn, kind="actor", name="Existing Org (alt spelling)")
    c_ambiguous = make_candidate(conn, kind="actor", name="Ambiguous Org")

    screen_decisions = [
        {"id": str(c_new["id"]), "keep": True, "reason": "ok"},
        {"id": str(c_shortlist["id"]), "keep": True, "reason": "ok"},
        {"id": str(c_ambiguous["id"]), "keep": True, "reason": "ok"},
    ]
    extract_json = {
        "claims": [{"field": "title", "value": "Some Org", "confidence": 0.9}],
        "emits": [{"kind": "actor", "name": "Spun Off Org", "hint": "mentioned"}],
        "edges": [],
    }
    _stub_llm_for_run_batch(monkeypatch, screen_decisions=screen_decisions,
                            extract_json=extract_json)

    # Route resolution deterministically without the real encoder: "new" name
    # gets an empty shortlist, "alt spelling" clears the safe band, "ambiguous"
    # sits in the escalation band. `knn` only sees the vector, not the text, so
    # route on the text `encode_one` was just called with (resolve_entity
    # calls encode_one immediately before knn, so this is exact, not a race).
    text_hint = [""]

    def tracking_encode_one(text, *, role):
        text_hint[0] = text.lower()
        return unit(1.0)

    def fake_knn(c, kind, vector, *, k=10, role="query", exclude=None):
        return {
            "brand new org": [],
            "existing org (alt spelling)": [("existing-org", 0.95)],
            "ambiguous org": [("existing-org", 0.85)],
        }.get(text_hint[0], [])

    monkeypatch.setattr(resolve, "encode_one", tracking_encode_one)
    monkeypatch.setattr(resolve.index, "knn", fake_knn)
    monkeypatch.setattr(gate2, "encode_one", lambda text, *, role: unit(1.0))

    candidates = [conn.execute("SELECT * FROM candidate WHERE id = ?", (cid["id"],)).fetchone()
                 for cid in (c_new, c_shortlist, c_ambiguous)]
    report = worker.run_batch(conn, tmp_path, candidates)

    assert report["resolved_new"] == 1
    assert report["resolved_shortlist"] == 1
    assert report["resolved_ambiguous"] == 1
    assert report["candidates_emitted"] == 2   # one `emits` per resolved (non-ambiguous) candidate

    new_row = conn.execute("SELECT * FROM candidate WHERE id = ?", (c_new["id"],)).fetchone()
    assert new_row["resolved_to"] is not None and new_row["admitted"] == 1
    new_actor = conn.execute("SELECT * FROM actor WHERE id = ?",
                             (new_row["resolved_to"],)).fetchone()
    assert new_actor is not None
    assert conn.execute("SELECT count(*) c FROM alias WHERE entity_id = ?",
                        (new_row["resolved_to"],)).fetchone()["c"] == 1

    shortlist_row = conn.execute("SELECT * FROM candidate WHERE id = ?",
                                 (c_shortlist["id"],)).fetchone()
    assert shortlist_row["resolved_to"] == "existing-org"

    ambiguous_row = conn.execute("SELECT * FROM candidate WHERE id = ?",
                                 (c_ambiguous["id"],)).fetchone()
    assert ambiguous_row["resolved_to"] is None
    events = conn.execute(
        "SELECT * FROM event WHERE entity_kind = 'candidate' AND entity_id = ? "
        "AND field = 'resolve'", (str(c_ambiguous["id"]),)).fetchall()
    assert len(events) == 1

    # emit never processes what it writes: still unresolved / unadmitted.
    emitted = conn.execute(
        "SELECT * FROM candidate WHERE name = 'Spun Off Org'").fetchall()
    assert len(emitted) == 2   # one emitted per non-ambiguous candidate above
    for row in emitted:
        assert row["admitted"] is None and row["resolved_to"] is None


def test_run_batch_gate1_rejection_marks_admitted_zero(conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Spam Org")

    def fake_call(prompt, *, system=None, tier="mechanical", max_tokens=2048, **kw):
        return {"json": {"decisions": [
            {"id": str(cand["id"]), "keep": False, "reason": "spam"}]}, "model": "m"}
    monkeypatch.setattr(gate1.llm, "call", fake_call)

    report = worker.run_batch(conn, tmp_path,
                              [conn.execute("SELECT * FROM candidate WHERE id = ?",
                                           (cand["id"],)).fetchone()])
    assert report["gate1_rejected"] == 1
    row = conn.execute("SELECT * FROM candidate WHERE id = ?", (cand["id"],)).fetchone()
    assert row["admitted"] == 0


def test_run_batch_returns_empty_report_for_no_candidates(conn, tmp_path):
    report = worker.run_batch(conn, tmp_path, [])
    assert report["gate1_kept"] == 0 and report["cost"] == 0.0


def test_run_batch_isolates_a_crashing_candidate_from_the_rest_of_the_batch(
        conn, monkeypatch, tmp_path):
    """2026-09-18: candidate 528 raised mid-`resolve` in a 6-candidate `--ids`
    run and took the other 5 down with it — the per-candidate loop had no
    try/except, so one candidate's bug crashed the whole batch (`[exit 1]`,
    no other candidate even started). A crash must now cost only that
    candidate: no exception escapes run_batch, its own row is left
    untouched (rolled back, not half-written), report["candidate_crashed"]
    counts it, and every other candidate still gets fully processed."""
    c_boom = make_candidate(conn, kind="actor", name="Boom Org")
    c_fine = make_candidate(conn, kind="actor", name="Fine Org")

    screen_decisions = [
        {"id": str(c_boom["id"]), "keep": True, "reason": "ok"},
        {"id": str(c_fine["id"]), "keep": True, "reason": "ok"},
    ]
    extract_json = {"claims": [], "emits": [], "edges": []}
    _stub_llm_for_run_batch(monkeypatch, screen_decisions=screen_decisions,
                            extract_json=extract_json)

    real_resolve_entity = resolve.resolve_entity

    def flaky_resolve_entity(conn, corpus, kind, name, evidence):
        if name == "Boom Org":
            raise RuntimeError("simulated crash — e.g. an embedder deadlock")
        return real_resolve_entity(conn, corpus, kind, name, evidence)

    monkeypatch.setattr(resolve, "resolve_entity", flaky_resolve_entity)
    monkeypatch.setattr(resolve, "encode_one", lambda text, *, role: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])

    candidates = [conn.execute("SELECT * FROM candidate WHERE id = ?", (c["id"],)).fetchone()
                 for c in (c_boom, c_fine)]
    report = worker.run_batch(conn, tmp_path, candidates)

    assert report["candidate_crashed"] == 1
    assert report["resolved_new"] == 1   # c_fine still resolved normally

    boom_row = conn.execute("SELECT * FROM candidate WHERE id = ?",
                            (c_boom["id"],)).fetchone()
    # `admitted=1` was gate1's decision, committed before the per-candidate
    # loop even starts — the crash (inside resolve, later) and its rollback
    # can't touch that. `resolved_to` is what the crash must have prevented:
    # `_settle`'s write never reached a commit for this candidate.
    assert boom_row["resolved_to"] is None

    fine_row = conn.execute("SELECT * FROM candidate WHERE id = ?",
                            (c_fine["id"],)).fetchone()
    assert fine_row["resolved_to"] is not None and fine_row["admitted"] == 1


def test_run_batch_rescues_via_13_then_resolves_with_sane_attribution(
        conn, monkeypatch, tmp_path):
    """2026-09-18T14:00 production log, candidate 528: the batched extraction
    call raised `llm.JSONParseError` on every attempt, the §13 per-source
    rescue then succeeded (one source parsed clean on retry), and
    `stage=resolve` crashed with `UnboundLocalError: cannot access local
    variable 'result'` — the §13 branch never sets `result`, but the
    attribution line at the bottom of the per-candidate loop unconditionally
    read `result.get('model', '?')`. This asserts the rescued path reaches
    resolve/write without crashing, is NOT counted as `candidate_crashed`,
    and gets a sane (non-crashing) attribution string derived from the
    rescue call's own model rather than the absent batched-call `result`."""
    from worker import extract as extract_mod
    from worker.extract_types import PromptSource
    from text.pagestate import PageState

    cand = make_candidate(conn, kind="actor", name="Rescued Org",
                          url="https://x.test/rescued")

    # A real `source` row: `write_findings` FK-references `source.id`, so the
    # `fetchmod.fetch` stub below still needs a matching row on disk (the
    # real fetch() would have inserted one itself).
    conn.execute(
        "INSERT INTO source (id, url, url_canonical) VALUES (?, ?, ?)",
        ("src-1", "https://x.test/rescued", "https://x.test/rescued"))
    conn.commit()

    # fetch — long enough text to clear THIN_PAGE_CHARS and route PROMPT.
    fake_fetch = fetchmod.FetchResult(
        text="x" * 1000, state=PageState("ok", "", False, True, 500, ""),
        source_id="src-1", cache_hit=False)
    monkeypatch.setattr(fetchmod, "fetch", lambda conn, corpus, url: fake_fetch)
    monkeypatch.setattr(gate2, "confirm", lambda conn, name, ev, text: ("confirmed", 0.95, "ok"))

    # assemble — bypass real chunking/ranking, hand back one prompt source so
    # `batched` is True and the §13 rescue path (which only fires when
    # `batched`) is reachable.
    solo = PromptSource(source_id="src-1", label="S1", url="https://x.test/rescued",
                        text="x" * 1000, chunk_refs=("src-1:0",))
    monkeypatch.setattr(extract_mod, "assemble",
                        lambda sources, questions, **kw: ([solo], {}))

    calls = {"n": 0}

    def fake_call(prompt, *, system=None, tier="mechanical", max_tokens=2048, **kw):
        if "decisions" in prompt or "Screen these candidates" in prompt:
            return {"json": {"decisions": [
                {"id": str(cand["id"]), "keep": True, "reason": "ok"}]},
                    "model": "gate-model", "cost": 0.0}
        calls["n"] += 1
        if calls["n"] == 1:
            # The batched extraction call — every retry inside `llm.call`
            # exhausted itself on malformed JSON.
            raise llm.JSONParseError("malformed json on every attempt")
        # §13's per-source retry call — this is the one that rescued
        # candidate 528 in the production log.
        return {"json": {"answers": [
            {"question_id": "q1", "answer": "yes", "source_id": "S1",
             "confidence": 0.9}]},
                "model": "rescue-model", "cost": 0.001}

    monkeypatch.setattr(worker.llm, "call", fake_call)
    monkeypatch.setattr(gate1.llm, "call", fake_call)
    monkeypatch.setattr(resolve, "encode_one", lambda text, *, role: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])

    candidates = [conn.execute("SELECT * FROM candidate WHERE id = ?",
                               (cand["id"],)).fetchone()]
    report = worker.run_batch(conn, tmp_path, candidates)

    assert report.get("candidate_crashed", 0) == 0
    assert report["retry_per_source_rescued"] == 1
    assert report["resolved_new"] == 1

    row = conn.execute("SELECT * FROM candidate WHERE id = ?", (cand["id"],)).fetchone()
    assert row["resolved_to"] is not None and row["admitted"] == 1

    # Attribution: the `by=` string built from `model_used`, not a crash.
    # No single extraction-call `result` exists on the rescue path, so it
    # must be derived from the rescuing per-source call's own model.
    events = conn.execute(
        "SELECT * FROM event WHERE entity_kind = ? AND entity_id = ? "
        "ORDER BY id", (cand["kind"], row["resolved_to"])).fetchall()
    assert events, "expected at least one event recorded for the written entity"
    assert any(e["by"] == "worker:rescue-model" for e in events), \
        [dict(e) for e in events]


def test_run_batch_gate0_duplicate_inherits_the_survivors_terminal_state(
        conn, monkeypatch, tmp_path):
    """A candidate gate 0 collapses into another must not be left forever
    `admitted=1, resolved_to=NULL` — the CLI's own selection query would
    re-select and re-collapse it on every future run otherwise."""
    # `group()`'s representative is the lexicographically-first candidate id
    # in the merge group (`fetch_list` keeps `members[0]`) — create `rep`
    # first so it gets the smaller id and is the one gate 1 actually screens;
    # `dup` (created second, larger id) is the one gate 0 drops before gate 1
    # ever sees it.
    rep = make_candidate(conn, kind="actor", name="Mine Labour Protection Campaign",
                         evidence="silicosis Rajasthan")
    dup = make_candidate(conn, kind="actor",
                         name="Mine Labour Protection Campaign - About",
                         evidence="silicosis Rajasthan")

    def fake_call(prompt, *, system=None, tier="mechanical", max_tokens=2048, **kw):
        return {"json": {"decisions": [
            {"id": str(rep["id"]), "keep": False, "reason": "spam"}]}, "cost": 0.0}
    monkeypatch.setattr(gate1.llm, "call", fake_call)

    candidates = [conn.execute("SELECT * FROM candidate WHERE id = ?", (c["id"],)).fetchone()
                 for c in (dup, rep)]
    report = worker.run_batch(conn, tmp_path, candidates)
    assert report["gate0_collapsed"] == 1

    dup_row = conn.execute("SELECT * FROM candidate WHERE id = ?", (dup["id"],)).fetchone()
    rep_row = conn.execute("SELECT * FROM candidate WHERE id = ?", (rep["id"],)).fetchone()
    assert dup_row["admitted"] == rep_row["admitted"] == 0
    events = conn.execute(
        "SELECT * FROM event WHERE entity_kind = 'candidate' AND entity_id = ? "
        "AND by = 'worker:gate0'", (str(dup["id"]),)).fetchall()
    assert len(events) == 1


def test_write_entity_drops_an_invalid_enum_claim_instead_of_crashing(conn, tmp_path):
    decision = resolve.ResolveResult(decision="new", entity_id=None,
                                     shortlist=[], reason="")
    claims = [{"field": "title", "value": "New Org"},
             {"field": "depth", "value": "watched"}]   # not a real depth value
    entity_id = worker._write_entity(conn, tmp_path, "actor", "New Org", decision,
                                     claims, by="test", log=lambda *a: None)
    row = conn.execute("SELECT * FROM actor WHERE id = ?", (entity_id,)).fetchone()
    assert row is not None
    assert row["depth"] == "registry"   # the schema default, since the claim was dropped


def test_channel_claim_is_not_reinserted_on_a_handle_only_rerun(conn):
    """`UNIQUE(actor_id, kind, url, handle)` cannot dedupe a handle-only row —
    SQL's NULL <> NULL, so INSERT OR IGNORE never sees a repeat as a repeat.
    Applying the same `channel:twitter` claim twice must still leave one row."""
    actor(conn, "mlpc")
    claim = [{"field": "channel:twitter", "value": "@mlpc_org"}]
    worker._apply_other_claims(conn, "actor", "mlpc", claim, by="test")
    worker._apply_other_claims(conn, "actor", "mlpc", claim, by="test")
    rows = conn.execute(
        "SELECT * FROM channel WHERE actor_id = 'mlpc' AND kind = 'twitter'").fetchall()
    assert len(rows) == 1
    assert rows[0]["handle"] == "@mlpc_org" and rows[0]["url"] is None


def test_write_detected_channels_inserts_one_row_per_platform(conn):
    actor(conn, "ncml")
    detected = [{"kind": "linkedin", "url": "https://in.linkedin.com/company/ncml"},
               {"kind": "twitter", "url": "https://twitter.com/ncml_official"}]
    worker._write_detected_channels(conn, "ncml", detected, by="test")
    rows = conn.execute(
        "SELECT kind, url, status, last_checked FROM channel "
        "WHERE actor_id='ncml' ORDER BY kind").fetchall()
    # `live`, not `unconfirmed` (2026-09-19): everything reaching this
    # function already passed `channels_from_confirmed`'s full identity
    # chain (gate2 CONFIRMED + URL pattern + name-token + LLM judge when
    # supplied) — see `_write_detected_channels`'s own docstring.
    assert [(r["kind"], r["url"], r["status"]) for r in rows] == [
        ("linkedin", "https://in.linkedin.com/company/ncml", "live"),
        ("twitter", "https://twitter.com/ncml_official", "live"),
    ]
    assert all(r["last_checked"] for r in rows)


def test_write_detected_channels_does_not_duplicate_an_existing_kind(conn):
    """A `channel:twitter` claim the LLM already wrote (or an earlier run's
    detection) must not gain a second row when the deterministic pass finds
    a platform match too — first recorded, either path, stands."""
    actor(conn, "ncml")
    worker._apply_other_claims(
        conn, "actor", "ncml",
        [{"field": "channel:twitter", "value": "https://twitter.com/from_llm"}],
        by="test")
    worker._write_detected_channels(
        conn, "ncml",
        [{"kind": "twitter", "url": "https://twitter.com/from_detection"}],
        by="test")
    rows = conn.execute(
        "SELECT url FROM channel WHERE actor_id='ncml' AND kind='twitter'").fetchall()
    assert [r["url"] for r in rows] == ["https://twitter.com/from_llm"]


def test_write_entity_replaces_ask_and_channel_rows_on_reprocess(conn, tmp_path):
    """candidate 839 (anaemia-mukt-bharat) / 823 (poshan-abhiyaan), 2026-09-19:
    a reprocessed actor resolves 'exact' to the same existing entity and
    `_write_entity` re-runs `_apply_other_claims`, which inserts `ask`/
    `channel` unconditionally with no unique key tying a row to "the
    current claim set" — the second run's rows landed ALONGSIDE the first
    run's instead of replacing them (a duplicate need entry differing only
    in capitalization; a stale hiring ask and email channel surviving from
    a superseded first run). `_write_entity` must clear an existing actor's
    `ask`/`channel` rows once before applying the new claim set."""
    actor(conn, "poshan-abhiyaan")
    decision = resolve.ResolveResult(decision="exact", entity_id="poshan-abhiyaan",
                                     shortlist=[], reason="")
    first_claims = [{"field": "title", "value": "Poshan Abhiyaan"},
                    {"field": "ask:need:funding", "value": "seed grant"},
                    {"field": "channel:twitter", "value": "@poshan_old"}]
    worker._write_entity(conn, tmp_path, "actor", "Poshan Abhiyaan", decision,
                         first_claims, by="test", log=lambda *a: None)
    second_claims = [{"field": "title", "value": "Poshan Abhiyaan"},
                     {"field": "ask:need:volunteers", "value": "field staff"},
                     {"field": "channel:twitter", "value": "@poshan_new"}]
    worker._write_entity(conn, tmp_path, "actor", "Poshan Abhiyaan", decision,
                         second_claims, by="test", log=lambda *a: None)
    asks = conn.execute(
        "SELECT direction, kind, text FROM ask WHERE actor_id = ?",
        ("poshan-abhiyaan",)).fetchall()
    assert [(r["direction"], r["kind"], r["text"]) for r in asks] == [
        ("need", "volunteers", "field staff")]
    channels = conn.execute(
        "SELECT handle FROM channel WHERE actor_id = ?",
        ("poshan-abhiyaan",)).fetchall()
    assert [r["handle"] for r in channels] == ["@poshan_new"]


def test_write_entity_first_write_still_works_with_no_prior_ask_or_channel(conn, tmp_path):
    """A brand-new actor has nothing to clear — the unconditional DELETE
    added before `_apply_other_claims` (for the reprocess case above) must
    not error, or drop anything, on an entity's first write."""
    decision = resolve.ResolveResult(decision="new", entity_id=None,
                                     shortlist=[], reason="")
    claims = [{"field": "title", "value": "New Org"},
             {"field": "ask:offer:mentoring", "value": "monthly office hours"},
             {"field": "channel:linkedin",
              "value": "https://linkedin.com/company/neworg"}]
    entity_id = worker._write_entity(conn, tmp_path, "actor", "New Org", decision,
                                     claims, by="test", log=lambda *a: None)
    asks = conn.execute("SELECT text FROM ask WHERE actor_id = ?",
                        (entity_id,)).fetchall()
    assert [r["text"] for r in asks] == ["monthly office hours"]
    channels = conn.execute("SELECT url FROM channel WHERE actor_id = ?",
                            (entity_id,)).fetchall()
    assert [r["url"] for r in channels] == ["https://linkedin.com/company/neworg"]


def test_ecosystem_role_tag_claim_mirrors_into_the_actor_column(conn):
    """arjun-subedi/globus-warehousing/lt-foods/ncml, 2026-09-18 run:
    `finding.answer == "operator"` for q5_ecosystem_role on all four, the
    `tag` table has the row (claim_field is `tag:ecosystem_role`, so it gets
    `tag_validate_ins`'s closed-enum check), but `actor.ecosystem_role` —
    the bare JSON column `src/lib/corpus.mjs:251` actually renders — stayed
    `[]` for every one of them, tripping corpus.mjs's own "attaches to
    nothing" warning even though the actor plainly has a role. Mirrored in
    `_apply_other_claims` rather than retyping q5's claim_field, to keep the
    enum check."""
    actor(conn, "ncml")
    claim = [{"field": "tag:ecosystem_role", "value": "operator"}]
    worker._apply_other_claims(conn, "actor", "ncml", claim, by="test")
    tag_row = conn.execute(
        "SELECT * FROM tag WHERE entity_kind='actor' AND entity_id='ncml' "
        "AND ns='ecosystem_role'").fetchone()
    assert tag_row["value"] == "operator"
    actor_row = conn.execute(
        "SELECT ecosystem_role FROM actor WHERE id='ncml'").fetchone()
    assert json.loads(actor_row["ecosystem_role"]) == ["operator"]


def test_invalid_ecosystem_role_tag_is_not_mirrored(conn):
    """A value `tag_validate_ins` rejects (not in the closed enum) must not
    reach `actor.ecosystem_role` either — the mirror follows what was
    actually accepted into `tag`, not the raw claim."""
    actor(conn, "ncml")
    claim = [{"field": "tag:ecosystem_role", "value": "not-a-real-role"}]
    worker._apply_other_claims(conn, "actor", "ncml", claim, by="test",
                               log=lambda *a: None)
    actor_row = conn.execute(
        "SELECT ecosystem_role FROM actor WHERE id='ncml'").fetchone()
    assert json.loads(actor_row["ecosystem_role"]) == []


def test_write_entity_backfills_context_from_hint_on_a_new_actor(conn, tmp_path):
    """globus-warehousing/lt-foods, 2026-09-18 run: `one_line` reads as
    generic company boilerplate and says nothing about why the actor was
    minted. `hint` (the emitting candidate's `evidence.hint`) is a floor for
    `context` when the model's own q0_relevance answer doesn't supply one."""
    decision = resolve.ResolveResult(decision="new", entity_id=None,
                                     shortlist=[], reason="")
    claims = [{"field": "title", "value": "LT Foods"}]
    entity_id = worker._write_entity(
        conn, tmp_path, "actor", "LT Foods", decision, claims, by="test",
        log=lambda *a: None,
        hint="Key private company in warehousing and logistics")
    row = conn.execute("SELECT context FROM actor WHERE id = ?", (entity_id,)).fetchone()
    assert row["context"] == "Key private company in warehousing and logistics"


def test_write_entity_prefers_the_models_own_context_over_the_hint(conn, tmp_path):
    decision = resolve.ResolveResult(decision="new", entity_id=None,
                                     shortlist=[], reason="")
    claims = [{"field": "title", "value": "LT Foods"},
             {"field": "context", "value": "Cited for its rice-mill effluent discharge."}]
    entity_id = worker._write_entity(
        conn, tmp_path, "actor", "LT Foods", decision, claims, by="test",
        log=lambda *a: None, hint="Key private company in warehousing and logistics")
    row = conn.execute("SELECT context FROM actor WHERE id = ?", (entity_id,)).fetchone()
    assert row["context"] == "Cited for its rice-mill effluent discharge."


def test_write_entity_does_not_backfill_context_on_an_existing_actor(conn, tmp_path):
    """An existing actor's `context` may already hold a real q0_relevance
    answer from an earlier run that this run's claims don't repeat (the
    verify pass doesn't always ask every question) — backfilling from
    `hint` here would silently downgrade it on every re-run."""
    actor(conn, "lt-foods", context="Cited for its rice-mill effluent discharge.")
    decision = resolve.ResolveResult(decision="exact", entity_id="lt-foods",
                                     shortlist=[], reason="")
    claims = [{"field": "title", "value": "LT Foods"}]
    worker._write_entity(
        conn, tmp_path, "actor", "LT Foods", decision, claims, by="test",
        log=lambda *a: None, hint="Key private company in warehousing and logistics")
    row = conn.execute("SELECT context FROM actor WHERE id = 'lt-foods'").fetchone()
    assert row["context"] == "Cited for its rice-mill effluent discharge."


def test_shortlist_top_resolution_caches_an_alias(conn):
    """A shortlist hit paid for an encode + kNN. Without caching it as an
    alias, the same name variant pays that cost again on every future
    mention instead of hitting the free exact/alias path next time."""
    actor(conn, "existing-org", title="Existing Org")
    decision = resolve.ResolveResult(decision="shortlist_top", entity_id="existing-org",
                                     shortlist=[("existing-org", 0.95)], reason="")
    entity_id = worker._write_entity(conn, pathlib.Path("."), "actor",
                                     "Existing Org (alt spelling)", decision, [],
                                     by="test", log=lambda *a: None)
    assert entity_id == "existing-org"
    assert db.resolve(conn, "actor", "Existing Org (alt spelling)") == "existing-org"


def test_openrouter_falls_back_to_the_next_configured_model(monkeypatch):
    """Candidate 12 (groundwater-depletion-from-irrigation, 2026-09-14/15):
    the single configured openrouter model came back HTTP 200 with a
    whitespace-only body (free-tier gateway closing the stream on a slow
    generation) and the whole run produced nothing. A second, differently-
    backed model must be tried before this rung gives up."""
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm.config, "OPENROUTER_MODELS_JUDGMENT",
                        ["flaky/model:free", "backup/model:free"])
    calls = []

    def fake_call_openrouter(prompt, model, max_tokens, system):
        calls.append(model)
        if model == "flaky/model:free":
            raise llm.LLMError("openrouter flaky/model:free: HTTP 200 but body is whitespace-only")
        return {"text": '{"ok": true}', "provider": "openrouter", "model": model,
               "input_tokens": 1, "output_tokens": 1, "cost": 0.0}
    monkeypatch.setattr(llm, "_call_openrouter", fake_call_openrouter)

    result = llm.call("prompt", tier="judgment")
    assert calls == ["flaky/model:free", "backup/model:free"]
    assert result["model"] == "backup/model:free"


def test_openrouter_model_fallback_tries_next_model_on_rate_limit(monkeypatch):
    """Revised 2026-09-15 (same day as the fallback was added): a 429 from
    openrouter isn't always a per-key cap — candidate 12 hit one reading
    "google/gemma-4-31b-it:free is temporarily rate-limited upstream", an
    UPSTREAM VENDOR's congestion for that one free model, not the account
    key's own rate. A different model (different backend) can simply
    succeed instead of waiting on a jam nothing here controls."""
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm.config, "OPENROUTER_MODELS_JUDGMENT",
                        ["model-a:free", "model-b:free"])
    calls = []

    def fake_call_openrouter(prompt, model, max_tokens, system):
        calls.append(model)
        if model == "model-a:free":
            raise llm.RateLimitError(
                "openrouter 429: model-a:free is temporarily rate-limited upstream",
                retry_after=0)
        return {"text": '{"ok": true}', "provider": "openrouter", "model": model,
               "input_tokens": 1, "output_tokens": 1, "cost": 0.0}
    monkeypatch.setattr(llm, "_call_openrouter", fake_call_openrouter)

    result = llm.call("prompt", tier="judgment")
    assert calls == ["model-a:free", "model-b:free"]
    assert result["model"] == "model-b:free"


def test_openrouter_rate_limit_still_reaches_outer_wait_handler_if_every_model_fails(monkeypatch):
    """If EVERY configured model 429s, the last one's RateLimitError must
    still reach the outer wait-out-the-window handler unchanged — the
    model-level fallback must not swallow that safety net."""
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm.config, "OPENROUTER_MODELS_JUDGMENT",
                        ["model-a:free", "model-b:free"])
    monkeypatch.setattr(llm.config, "OPENROUTER_RATELIMIT_MAX_RETRIES", 0)
    calls = []

    def fake_call_openrouter(prompt, model, max_tokens, system):
        calls.append(model)
        raise llm.RateLimitError(f"openrouter 429: {model}", retry_after=0)
    monkeypatch.setattr(llm, "_call_openrouter", fake_call_openrouter)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    with pytest.raises(llm.LLMError, match="model-b:free"):
        llm.call("prompt", tier="judgment")
    assert calls == ["model-a:free", "model-b:free"]


def test_all_models_failed_message_includes_every_models_error(monkeypatch):
    """The masking bug candidate 12 hit: `last_err` used to be overwritten by
    each subsequent try, so the failure that mattered disappeared behind a
    later, uninteresting one. The axis used to be providers and is now models
    (the claude/gemini/local rungs went 2026-09-18), but the requirement is
    unchanged — the final message must show every model's own error."""
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm.config, "OPENROUTER_MODELS_MECHANICAL",
                        ["model-a:free", "model-b:free"])
    monkeypatch.setattr(llm.config, "LLM_MAX_ATTEMPTS", 1)

    def boom(prompt, model, max_tokens, system):
        if model == "model-a:free":
            raise llm.LLMError("HTTP 200 but body is whitespace-only")
        raise llm.LLMError("404 No endpoints found")
    monkeypatch.setattr(llm, "_call_openrouter", boom)

    with pytest.raises(llm.LLMError) as exc_info:
        llm.call("prompt")
    message = str(exc_info.value)
    assert "whitespace-only" in message, "model-a's real error was masked"
    assert "404 No endpoints found" in message, "model-b's error should be present too"


def test_call_sends_reasoning_disabled(monkeypatch):
    """The 2026-09-18 extraction failure in one assertion. Every configured
    free model is a reasoning model and OpenRouter bills hidden chain-of-
    thought against `max_tokens`; measured on the real 8-source prompt, that
    was 8,922 of a 10,240-token budget, leaving too little for the answer and
    returning a force-closed partial object. Extraction copies spans into a
    fixed schema — there is nothing to reason about — so the request must
    always carry `reasoning: {enabled: False}`. Without it the call does not
    fail loudly; it returns truncated JSON and burns 110s doing it."""
    import requests as requests_mod
    sent = {}

    class FakeResp:
        status_code = 200
        headers: dict = {}
        text = '{"choices": []}'

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0}}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return FakeResp()
    monkeypatch.setattr(requests_mod, "post", fake_post)
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm.config, "OPENROUTER_MIN_INTERVAL_S", 0)

    llm.call("prompt", tier="judgment")
    assert sent["reasoning"] == {"enabled": False}
    assert "provider" not in sent, (
        "require_parameters was removed — it 404'd on models that declare "
        "neither response_format nor structured_outputs")


def test_call_openrouter_diagnoses_a_non_json_200_body(monkeypatch):
    """HTTP 200 with an unparseable body (the actual production failure,
    2026-09-14/15) must not surface as a bare, contextless
    `json.JSONDecodeError` — it needs to say the response wasn't real
    content, not just that parsing broke."""
    import requests as requests_mod

    class _FakeResp:
        status_code = 200
        text = "\n   \n\n   \n"     # keep-alive whitespace padding, no JSON
        headers = {"content-length": "10", "transfer-encoding": "chunked"}
        def json(self):
            json.loads(self.text)   # raises the real json.JSONDecodeError

    monkeypatch.setattr(requests_mod, "post", lambda *a, **kw: _FakeResp())
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm, "_openrouter_pace", lambda: None)

    with pytest.raises(llm.LLMError, match="whitespace-only"):
        llm._call_openrouter("prompt", "some/model:free", 100, None)


def test_call_openrouter_flags_truncation_even_when_json_mode_closes_cleanly(
        monkeypatch):
    """2026-09-18, candidate 560: `response_format=json_object` (added
    2026-09-17 to kill unbalanced-brace errors) makes a grammar-constrained
    decoder force-close the object when it runs out of budget, so a
    truncated generation still ends on `}` — the bracket-ending heuristic
    added the same day can't see this, and it silently parsed into a valid
    but incomplete dict (missing `emits`/`edges`) that only failed
    worker.py's schema check, never call()'s own retry/escalation. Output
    tokens landing at the requested budget must still flag `truncated`."""
    import requests as requests_mod

    class _FakeResp:
        status_code = 200
        headers = {}
        def json(self):
            return {
                "choices": [{"message": {"content": '{"answers": []}'},
                            "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 500, "completion_tokens": 100,
                         "cost": 0.0},
            }

    monkeypatch.setattr(requests_mod, "post", lambda *a, **kw: _FakeResp())
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm, "_openrouter_pace", lambda: None)

    result = llm._call_openrouter("prompt", "some/model:free", 100, None)
    assert result["truncated"] is True


def test_call_openrouter_does_not_flag_truncation_well_under_budget(monkeypatch):
    """The new output-token-ratio check must not fire on an ordinary
    complete response that simply didn't use its whole budget."""
    import requests as requests_mod

    class _FakeResp:
        status_code = 200
        headers = {}
        def json(self):
            return {
                "choices": [{"message": {"content": '{"answers": []}'},
                            "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 500, "completion_tokens": 20,
                         "cost": 0.0},
            }

    monkeypatch.setattr(requests_mod, "post", lambda *a, **kw: _FakeResp())
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm, "_openrouter_pace", lambda: None)

    result = llm._call_openrouter("prompt", "some/model:free", 100, None)
    assert result["truncated"] is False


def test_extraction_max_tokens_scales_with_source_count_and_caps():
    """Flat 4096 was the real bottleneck behind candidate 560's "malformed
    extraction JSON (dict)" — the budget must grow with batch size, and
    never exceed MAX_TOKENS_CEILING regardless of how large the batch is."""
    assert llm.extraction_max_tokens(1) < llm.extraction_max_tokens(5)
    assert llm.extraction_max_tokens(5) < llm.extraction_max_tokens(20)
    assert llm.extraction_max_tokens(1000) == llm.MAX_TOKENS_CEILING


def test_call_raises_json_parse_error_when_every_attempt_is_broken_json(
        monkeypatch):
    """2026-09-18, candidates 528/552/560: the model itself emitted broken
    JSON on every attempt (genuine syntax errors — unquoted keys, missing
    commas — not a network blip). Before this, `parse_json`'s
    JSONDecodeError was caught by call()'s generic `except Exception`,
    retried like any transient failure, and on exhaustion raised as a plain
    LLMError — indistinguishable from a real outage by the time worker.py
    saw it, so it could never route to the §13 per-source rescue. It must
    now raise the more specific JSONParseError instead.

    The fixture text must survive `_repair_json`'s `json_repair.loads` too,
    not just `json.loads` — `{"answers": [}` (the original fixture here)
    turns out to be exactly the kind of bracket-balance slip json_repair
    fixes cleanly (`json_repair.loads('{"answers": [}')` == `{"answers":
    []}`), so it no longer represents an unrepairable failure once
    `_repair_json` is in the loop. Plain prose has no JSON structure for
    json_repair to recover — `json_repair.loads` on it returns `''`, not a
    dict — so it stays a real, unrepairable parse failure."""
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm.config, "LLM_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def fake_call_openrouter(prompt, model, max_tokens, system):
        return {"text": "the model just wrote prose here, not JSON at all",
                "provider": "openrouter",
                "model": model, "input_tokens": 1, "output_tokens": 1,
                "cost": 0.0, "truncated": False}
    monkeypatch.setattr(llm, "_call_openrouter", fake_call_openrouter)

    with pytest.raises(llm.JSONParseError):
        llm.call("prompt", tier="judgment")


def test_call_repairs_malformed_but_recoverable_json(monkeypatch, capsys):
    """A trailing comma / unbalanced bracket — the class json_repair targets
    — must parse successfully via the repair path instead of raising
    JSONParseError, and the repair must be logged so a persistently broken
    model still shows up as an anomaly."""
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm.config, "LLM_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def fake_call_openrouter(prompt, model, max_tokens, system):
        # Missing closing brace on the array — a genuine bracket-balance
        # slip, not prose.
        return {"text": '{"answers": [}', "provider": "openrouter",
                "model": model, "input_tokens": 1, "output_tokens": 1,
                "cost": 0.0, "truncated": False}
    monkeypatch.setattr(llm, "_call_openrouter", fake_call_openrouter)

    result = llm.call("prompt", tier="judgment")
    assert result["json"] == {"answers": []}
    assert "repaired" in capsys.readouterr().out


def test_repair_json_rejects_a_non_dict_repair():
    """json_repair.loads on pure prose returns '' (or some other non-dict),
    not an exception — `_repair_json` must not hand that back as a usable
    result."""
    assert llm._repair_json("just some prose, no JSON structure here") is None


def test_json_parse_error_is_still_an_llmerror(monkeypatch):
    """Every other `except llm.LLMError` in worker.py (network failures,
    unconfigured providers) must keep catching this — JSONParseError adds a
    more specific branch, it doesn't replace the general one."""
    assert issubclass(llm.JSONParseError, llm.LLMError)


def test_call_does_not_misclassify_a_real_network_failure_as_json_parse_error(
        monkeypatch):
    """Guard against over-broadening: a plain connection/provider error must
    still raise the ordinary LLMError, not JSONParseError, so it keeps being
    treated as a network/provider outage rather than routed into the §13
    per-source rescue (which would just repeat the same real failure once
    per source for no benefit)."""
    monkeypatch.setattr(llm.config, "OPENROUTER_KEY", "x")
    monkeypatch.setattr(llm.config, "LLM_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def fake_call_openrouter(prompt, model, max_tokens, system):
        raise llm.LLMError("openrouter 503: upstream overloaded")
    monkeypatch.setattr(llm, "_call_openrouter", fake_call_openrouter)

    with pytest.raises(llm.LLMError) as exc_info:
        llm.call("prompt", tier="judgment")
    assert not isinstance(exc_info.value, llm.JSONParseError)


# ------------------------------------------------- track A: problem emission

def _source_candidate(conn, *, resolved_to, evidence=None, kind="actor"):
    """A candidate row already resolved to a live entity — the shape `_emit`
    always receives its `source_candidate` in (`run_batch` re-fetches the
    row right after `_settle` sets `resolved_to`)."""
    cur = conn.execute(
        "INSERT INTO candidate (kind, name, url, evidence, admitted, resolved_to) "
        "VALUES (?, ?, NULL, ?, 1, ?)",
        (kind, "Src Candidate", evidence, resolved_to))
    conn.commit()
    return conn.execute("SELECT * FROM candidate WHERE id = ?",
                        (cur.lastrowid,)).fetchone()


def test_emit_mints_a_problem_candidate_for_an_unresolvable_works_on_edge(
        conn, monkeypatch):
    """The hole `03-worker.md` §10 names: before Track A this edge is
    silently dropped (0 problem candidates minted, ever) — worker.py:279-281."""
    actor(conn, "src-actor")
    src = _source_candidate(conn, resolved_to="src-actor")

    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])  # empty -> new

    # Signals ride the EMIT, per 03-worker.md §10 — the edge names the
    # problem, the emit describes it, and the mint matches them by name.
    # This test used to put them on the edge, which is the shape the code
    # read and the prompt never produced.
    claims = {"emits": [{
        "kind": "problem", "name": "Silicosis in stone quarries",
        "hint": "quarry dust",
        "signals": {"harmed_population": "quarry workers", "magnitude": "uncounted",
                   "agent": "silica dust", "actionable": "dust suppression"}}],
        "edges": [{
        "dst_kind": "problem", "dst_name": "Silicosis in stone quarries",
        "edge_kind": "works_on", "relevance": 2}]}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 1
    assert edges == 0   # deferred — nothing to link to yet, same as `emits`
    row = conn.execute(
        "SELECT * FROM candidate WHERE kind = 'problem' AND "
        "name = 'Silicosis in stone quarries'").fetchone()
    assert row is not None
    assert row["resolved_to"] is None and row["admitted"] is None
    payload = json.loads(row["evidence"])
    assert payload["signals"] == {
        "harmed_population": "quarry workers", "magnitude": "uncounted",
        "agent": "silica dust", "actionable": "dust suppression"}


def test_signals_ride_the_works_on_edge(conn, monkeypatch):
    """Where problems actually arrive. PoC-2d: 31 emits across ten calls, all
    `actor`; 23 problems, all `works_on` destinations. The prompt asks for
    emits as "other organisations or named individuals" and for edges as
    "actor or problem", so a problem emit is not what the model produces —
    and `signals` on the emit was a key nothing ever filled."""
    actor(conn, "src-actor")
    src = _source_candidate(conn, resolved_to="src-actor")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])

    claims = {"emits": [], "edges": [{
        "dst_kind": "problem", "dst_name": "Silicosis in stone quarries",
        "edge_kind": "works_on", "relevance": 2,
        "signals": {"harmed_population": "quarry workers",
                   "magnitude": "uncounted", "agent": "silica dust",
                   "actionable": "dust suppression"}}]}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 1 and edges == 0
    row = conn.execute(
        "SELECT * FROM candidate WHERE kind = 'problem' AND "
        "name = 'Silicosis in stone quarries'").fetchone()
    payload = json.loads(row["evidence"])
    assert payload["signals"] == {
        "harmed_population": "quarry workers", "magnitude": "uncounted",
        "agent": "silica dust", "actionable": "dust suppression"}


def test_edge_without_signals_mints_four_nulls_not_a_missing_key(conn, monkeypatch):
    """`null` is "the source was silent", not "no" — and the orchestrator
    reads a fixed shape either way."""
    actor(conn, "src-actor")
    src = _source_candidate(conn, resolved_to="src-actor")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])

    claims = {"emits": [], "edges": [{
        "dst_kind": "problem", "dst_name": "Fluorosis in Nalgonda",
        "edge_kind": "works_on", "relevance": 2}]}
    worker._emit(conn, src, claims, {}, log=lambda *a: None)

    row = conn.execute(
        "SELECT * FROM candidate WHERE kind = 'problem' AND "
        "name = 'Fluorosis in Nalgonda'").fetchone()
    assert json.loads(row["evidence"])["signals"] == {
        "harmed_population": None, "magnitude": None,
        "agent": None, "actionable": None}


def test_problem_emit_route_writes_signals_too(conn, monkeypatch):
    """Both mint routes write the same payload shape. The emits loop used to
    write no `signals` key at all, so the orchestrator's payload depended on
    which route happened to mint the candidate."""
    actor(conn, "src-actor")
    src = _source_candidate(conn, resolved_to="src-actor")

    claims = {"emits": [{
        "kind": "problem", "name": "Fluorosis in Nalgonda",
        "hint": "groundwater fluoride",
        "signals": {"harmed_population": "villagers on borewell supply",
                   "magnitude": "uncounted", "agent": "fluoride in groundwater",
                   "actionable": None}}], "edges": []}
    emitted, _ = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 1
    row = conn.execute(
        "SELECT * FROM candidate WHERE kind = 'problem' AND "
        "name = 'Fluorosis in Nalgonda'").fetchone()
    payload = json.loads(row["evidence"])
    assert payload["signals"]["harmed_population"] == "villagers on borewell supply"
    assert payload["signals"]["actionable"] is None   # null is "silent", not "no"


def test_emit_resolves_a_shortlist_matched_problem_edge_and_links_it(conn, monkeypatch):
    actor(conn, "src-actor")
    problem(conn, "silicosis-quarries", title="Silicosis in Stone Quarries")
    src = _source_candidate(conn, resolved_to="src-actor")

    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn",
                        lambda *a, **kw: [("silicosis-quarries", 0.95)])

    claims = {"emits": [], "edges": [{
        "dst_kind": "problem", "dst_name": "Silicosis in stone quarries",
        "edge_kind": "works_on", "relevance": 2}]}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 0    # resolved, not minted
    assert edges == 1
    linked = conn.execute(
        "SELECT * FROM edge WHERE src_id = 'src-actor' AND dst_id = 'silicosis-quarries' "
        "AND kind = 'works_on'").fetchone()
    assert linked is not None
    # shortlist_top caches an alias so the next mention hits the free path.
    assert db.resolve(conn, "problem", "Silicosis in stone quarries") == "silicosis-quarries"


def test_emit_ambiguous_problem_edge_escalates_without_minting_a_duplicate(
        conn, monkeypatch):
    actor(conn, "src-actor")
    problem(conn, "existing-problem", title="Existing Problem")
    src = _source_candidate(conn, resolved_to="src-actor")

    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    # Below the safe band but lexically overlapping "Existing" -> ambiguous.
    monkeypatch.setattr(resolve.index, "knn",
                        lambda *a, **kw: [("existing-problem", 0.85)])

    claims = {"emits": [], "edges": [{
        "dst_kind": "problem", "dst_name": "Existing Problem, restated",
        "edge_kind": "works_on", "relevance": 2}]}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 0
    assert edges == 0
    # No duplicate problem candidate minted for the ambiguous name.
    assert conn.execute(
        "SELECT count(*) c FROM candidate WHERE kind = 'problem'"
    ).fetchone()["c"] == 0
    events = conn.execute(
        "SELECT * FROM event WHERE entity_kind = 'candidate' AND entity_id = ? "
        "AND field = 'edge'", (str(src["id"]),)).fetchall()
    assert len(events) == 1


def test_emit_problem_emission_disabled_degrades_to_dropping_the_edge(
        conn, monkeypatch):
    """`problem_emission=False` reverts to pre-Track-A behaviour: an
    unresolvable problem edge is dropped, nothing minted — the fallback path
    `04-worker-build-plan.md` §4 requires landing before the switchable part.
    E6 turned the `WORKER_PROBLEM_EMISSION` env var this once monkeypatched
    into a call-site parameter, so the degrade is reached the way a caller
    reaches it."""
    actor(conn, "src-actor")
    src = _source_candidate(conn, resolved_to="src-actor")

    def boom(*a, **kw):
        raise AssertionError("resolve_entity must not run when the flag is off")
    monkeypatch.setattr(resolve, "encode_one", boom)

    claims = {"emits": [], "edges": [{
        "dst_kind": "problem", "dst_name": "Some New Problem",
        "edge_kind": "works_on"}]}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None,
                                  problem_emission=False)

    assert emitted == 0 and edges == 0
    assert conn.execute(
        "SELECT count(*) c FROM candidate WHERE kind = 'problem'"
    ).fetchone()["c"] == 0


# ------------------------------------------------ trigger-edge backfill on promotion

def test_new_problem_mint_carries_the_trigger_edge_on_its_own_evidence(
        conn, monkeypatch):
    """The edge dropped at mint time (`_mint_or_resolve_problem`'s "new"
    path) is not lost — it rides on the destination candidate's own
    evidence so `_backfill_trigger_edge` can write it once that candidate
    is promoted."""
    actor(conn, "src-actor")
    src = _source_candidate(conn, resolved_to="src-actor")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])

    claims = {"emits": [], "edges": [{
        "dst_kind": "problem", "dst_name": "Fluorosis in Nalgonda",
        "edge_kind": "works_on", "relevance": 2, "evidence": "cited groundwater study"}]}
    worker._emit(conn, src, claims, {}, log=lambda *a: None)

    row = conn.execute(
        "SELECT * FROM candidate WHERE kind = 'problem' AND "
        "name = 'Fluorosis in Nalgonda'").fetchone()
    payload = json.loads(row["evidence"])
    assert payload["from_kind"] == "actor"
    assert payload["from_id"] == "src-actor"
    assert payload["edge_kind"] == "works_on"
    assert payload["edge_relevance"] == 2
    assert payload["edge_evidence"] == "cited groundwater study"


def test_emit_mints_an_actor_candidate_for_an_unresolvable_edge(conn, monkeypatch):
    """Actor counterpart of the problem mint: before this, an edge naming an
    actor that the `emits` loop hadn't already surfaced was dropped outright
    — no candidate at all, unlike problems (which at least minted)."""
    problem(conn, "silicosis-quarries", title="Silicosis in Stone Quarries")
    src = _source_candidate(conn, resolved_to="silicosis-quarries", kind="problem")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])   # empty -> new

    claims = {"emits": [], "edges": [{
        "dst_kind": "actor", "dst_name": "Quarry Workers Collective",
        "edge_kind": "works_on", "relevance": 3, "evidence": "leads the campaign"}]}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 1
    assert edges == 0   # deferred, same as the problem case
    row = conn.execute(
        "SELECT * FROM candidate WHERE kind = 'actor' AND "
        "name = 'Quarry Workers Collective'").fetchone()
    assert row is not None
    assert row["resolved_to"] is None
    payload = json.loads(row["evidence"])
    assert payload["from_kind"] == "problem"
    assert payload["from_id"] == "silicosis-quarries"
    assert payload["edge_kind"] == "works_on"
    assert payload["edge_relevance"] == 3


def test_emit_actor_edge_does_not_double_mint_an_already_emitted_actor(
        conn, monkeypatch):
    """The same duplicate guard `minted_problems` already gave problems,
    extended to actors: a name minted by the `emits` loop must not be minted
    again by the edges loop's new actor mint path."""
    actor(conn, "src-actor")
    src = _source_candidate(conn, resolved_to="src-actor")
    monkeypatch.setattr(resolve, "encode_one",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            AssertionError("must not re-resolve an already-emitted name")))

    claims = {"emits": [{"kind": "actor", "name": "Warrior Moms", "hint": "coalition partner"}],
              "edges": [{"dst_kind": "actor", "dst_name": "Warrior Moms",
                        "edge_kind": "affiliated", "relevance": 2}]}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 1   # once, from the emits loop
    assert edges == 0
    assert conn.execute(
        "SELECT count(*) c FROM candidate WHERE kind = 'actor' AND name = 'Warrior Moms'"
    ).fetchone()["c"] == 1


def test_emit_synthesizes_works_on_for_an_actor_named_only_in_emits(
        conn, monkeypatch):
    """The bug this fix closes: the model reliably lists a `works_on` actor
    under `emits` (for the stub) but doesn't reliably restate it as an
    `edges` entry too — so newly-minted actors ended up with nothing for
    `_backfill_trigger_edge` to backfill and their "Working on" section
    stayed empty. `_emit` now synthesizes the `works_on` edge itself from a
    plain `emits` entry, with no matching `edges` entry required."""
    problem(conn, "silicosis-quarries", title="Silicosis in Stone Quarries")
    src = _source_candidate(conn, resolved_to="silicosis-quarries", kind="problem")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])   # empty -> new

    claims = {"emits": [{"kind": "actor", "name": "Quarry Workers Collective",
                         "hint": "leads the campaign"}], "edges": []}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 1   # minted once, by the emits loop
    assert edges == 0   # deferred — the actor isn't an entity yet
    row = conn.execute(
        "SELECT * FROM candidate WHERE kind = 'actor' AND "
        "name = 'Quarry Workers Collective'").fetchone()
    payload = json.loads(row["evidence"])
    assert payload["from_kind"] == "problem"
    assert payload["from_id"] == "silicosis-quarries"
    assert payload["edge_kind"] == "works_on"


def test_emit_does_not_double_write_works_on_when_model_states_it_explicitly(
        conn, monkeypatch):
    """An actor already resolved (not minted) that the model both `emits`
    and links via an explicit `works_on` edge must get exactly one edge, not
    a synthesized second attempt that then has to be swallowed as a
    duplicate-key error."""
    problem(conn, "silicosis-quarries", title="Silicosis in Stone Quarries")
    actor(conn, "Quarry Workers Collective")   # id == dst_name -> resolves by exact id
    src = _source_candidate(conn, resolved_to="silicosis-quarries", kind="problem")

    claims = {"emits": [{"kind": "actor", "name": "Quarry Workers Collective",
                         "hint": "leads the campaign"}],
              "edges": [{"dst_kind": "actor", "dst_name": "Quarry Workers Collective",
                        "edge_kind": "works_on", "relevance": 3}]}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert edges == 1
    assert conn.execute(
        "SELECT count(*) c FROM edge WHERE kind = 'works_on'"
    ).fetchone()["c"] == 1


def test_backfill_trigger_edge_writes_the_deferred_edge_on_promotion(conn):
    """The other half: once a candidate minted this way is itself promoted
    to a real actor/problem row, the edge its own evidence remembers gets
    written — this is the fix for actors and the problems that emitted them
    never ending up linked."""
    actor(conn, "src-actor")
    cand = make_candidate(
        conn, kind="problem", name="Fluorosis in Nalgonda",
        evidence=json.dumps({"from_kind": "actor", "from_id": "src-actor",
                            "edge_kind": "works_on", "edge_relevance": 2,
                            "edge_evidence": "cited groundwater study"}))

    worker._backfill_trigger_edge(conn, cand, "problem", "fluorosis-nalgonda",
                                  by="worker:test", log=lambda *a: None)

    linked = conn.execute(
        "SELECT * FROM edge WHERE src_kind = 'actor' AND src_id = 'src-actor' "
        "AND dst_kind = 'problem' AND dst_id = 'fluorosis-nalgonda' "
        "AND kind = 'works_on'").fetchone()
    assert linked is None   # dst doesn't exist as an entity yet -> trigger rejects it

    problem(conn, "fluorosis-nalgonda", title="Fluorosis in Nalgonda")
    worker._backfill_trigger_edge(conn, cand, "problem", "fluorosis-nalgonda",
                                  by="worker:test", log=lambda *a: None)
    linked = conn.execute(
        "SELECT * FROM edge WHERE src_kind = 'actor' AND src_id = 'src-actor' "
        "AND dst_kind = 'problem' AND dst_id = 'fluorosis-nalgonda' "
        "AND kind = 'works_on'").fetchone()
    assert linked is not None
    assert linked["relevance"] == 2
    assert linked["evidence"] == "cited groundwater study"


def test_backfill_trigger_edge_is_a_noop_for_candidates_without_one(conn):
    """A candidate minted any other way (corpus migration, a bare `emits`
    mention) has no `edge_kind` in its evidence — same "parse failure is the
    normal case" contract as `_predicted_depth`."""
    cand = make_candidate(conn, kind="actor", name="Some Org", evidence="just a snippet")
    worker._backfill_trigger_edge(conn, cand, "actor", "some-org",
                                  by="worker:test", log=lambda *a: None)
    assert conn.execute("SELECT count(*) c FROM edge").fetchone()["c"] == 0


def test_backfill_trigger_edge_logs_rather_than_raises_when_source_is_gone(conn):
    """The source entity id captured at mint time could, in principle,
    later be renamed/merged out from under this — the same defensive
    IntegrityError handling `_emit`'s own `db.link` call already has."""
    problem(conn, "fluorosis-nalgonda", title="Fluorosis in Nalgonda")
    cand = make_candidate(
        conn, kind="problem", name="Fluorosis in Nalgonda",
        evidence=json.dumps({"from_kind": "actor", "from_id": "no-such-actor",
                            "edge_kind": "works_on"}))
    logged = []
    worker._backfill_trigger_edge(conn, cand, "problem", "fluorosis-nalgonda",
                                  by="worker:test", log=logged.append)
    assert any("rejected" in m for m in logged)
    assert conn.execute("SELECT count(*) c FROM edge").fetchone()["c"] == 0


# -------------------------------------- actor->actor emits: ancestor problem
# 2026-09-19: raghubar-das (candidate 1102) was minted off saryu-roy
# (candidate 1075) — both `kind: actor` — and ended up with zero `works_on`
# edges, because `_emit`'s implicit-works_on synthesis only fires for
# (problem, actor) / (actor, problem) source/emit pairs, never (actor,
# actor). `works_on` is actor -> problem only (`store/schema.sql`), so the
# fix isn't to link the new actor to its immediate actor parent — it's to
# walk `from_candidate` up to the nearest ancestor that resolves to a
# problem. `_ancestor_problem` is the walk; `_emit` and
# `_backfill_trigger_edge` are its two call sites (an already-resolved
# destination actor vs. one still to be minted/promoted).

def test_ancestor_problem_walks_up_an_actor_chain_to_the_resolved_problem(conn):
    """The raghubar-das/saryu-roy chain, condensed: an actor candidate minted
    off another actor candidate, itself minted off a resolved problem
    candidate. The middle actor (santoshi-kumari in the real chain) is never
    resolved itself — only its `kind` and `from_candidate` matter."""
    grandparent = make_candidate(conn, kind="problem", name="Aadhaar-linked PDS exclusion")
    conn.execute("UPDATE candidate SET resolved_to = ? WHERE id = ?",
                ("aadhaar-linked-pds-exclusion", grandparent["id"]))
    conn.commit()
    middle = make_candidate(
        conn, kind="actor", name="Santoshi Kumari",
        evidence=json.dumps({"from_candidate": grandparent["id"]}))
    leaf = make_candidate(
        conn, kind="actor", name="Saryu Roy",
        evidence=json.dumps({"from_candidate": middle["id"]}))

    ancestor = worker._ancestor_problem(conn, leaf, log=lambda *a: None)
    assert ancestor == "aadhaar-linked-pds-exclusion"


def test_ancestor_problem_returns_none_when_the_chain_bottoms_out(conn):
    """An actor with no further `from_candidate` (no lineage to walk) — the
    chain simply ends in another actor, no problem anywhere upstream."""
    root_actor = make_candidate(conn, kind="actor", name="Root Actor",
                                evidence=json.dumps({"hint": "no lineage"}))
    child = make_candidate(
        conn, kind="actor", name="Child Actor",
        evidence=json.dumps({"from_candidate": root_actor["id"]}))

    assert worker._ancestor_problem(conn, child, log=lambda *a: None) is None


def test_ancestor_problem_caps_the_walk_and_does_not_crash_on_a_cycle(conn):
    """A malformed/cyclic evidence chain (a from a's own descendant) must
    bail via the cycle guard rather than looping forever."""
    a = make_candidate(conn, kind="actor", name="A", evidence=json.dumps({}))
    b = make_candidate(
        conn, kind="actor", name="B",
        evidence=json.dumps({"from_candidate": a["id"]}))
    conn.execute("UPDATE candidate SET evidence = ? WHERE id = ?",
                (json.dumps({"from_candidate": b["id"]}), a["id"]))
    conn.commit()
    a = conn.execute("SELECT * FROM candidate WHERE id = ?", (a["id"],)).fetchone()

    logged = []
    assert worker._ancestor_problem(conn, a, log=logged.append) is None
    assert any("cycle" in m for m in logged)


def test_emit_flags_ancestor_problem_check_for_actor_emitting_new_actor(
        conn, monkeypatch):
    """An actor candidate that emits another actor gets no implicit
    works_on (that mechanism only covers problem<->actor pairs) but IS
    flagged for the ancestor-problem backfill at promotion time, instead of
    being dropped as before."""
    actor(conn, "src-actor")
    src = _source_candidate(conn, resolved_to="src-actor", kind="actor")
    monkeypatch.setattr(resolve, "encode_one", lambda *a, **kw: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn", lambda *a, **kw: [])   # empty -> new

    claims = {"emits": [{"kind": "actor", "name": "Related Figure",
                        "hint": "named as a related figure"}], "edges": []}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 1
    assert edges == 0   # deferred — no edge_kind path fires for actor->actor
    row = conn.execute(
        "SELECT * FROM candidate WHERE kind = 'actor' AND "
        "name = 'Related Figure'").fetchone()
    payload = json.loads(row["evidence"])
    assert payload.get("ancestor_problem_check") is True
    assert "edge_kind" not in payload


def test_emit_writes_ancestor_works_on_immediately_for_an_already_resolved_actor(
        conn, monkeypatch):
    """When the emitted actor name already resolves to an existing entity
    (no candidate/promotion to defer to), the ancestor-problem edge is
    written right away instead of silently dropped."""
    problem(conn, "aadhaar-linked-pds-exclusion", title="Aadhaar-linked PDS exclusion")
    grandparent = make_candidate(conn, kind="problem", name="Aadhaar-linked PDS exclusion")
    conn.execute("UPDATE candidate SET resolved_to = ? WHERE id = ?",
                ("aadhaar-linked-pds-exclusion", grandparent["id"]))
    actor(conn, "src-actor")
    src = _source_candidate(
        conn, resolved_to="src-actor", kind="actor",
        evidence=json.dumps({"from_candidate": grandparent["id"]}))
    actor(conn, "related-figure")   # already exists as an entity

    claims = {"emits": [{"kind": "actor", "name": "related-figure",
                        "hint": "named as a related figure"}], "edges": []}
    emitted, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)

    assert emitted == 0
    assert edges == 1
    linked = conn.execute(
        "SELECT * FROM edge WHERE src_kind = 'actor' AND src_id = 'related-figure' "
        "AND dst_kind = 'problem' AND dst_id = 'aadhaar-linked-pds-exclusion' "
        "AND kind = 'works_on'").fetchone()
    assert linked is not None


def test_backfill_trigger_edge_resolves_actor_chain_to_ancestor_problem(conn):
    """Full raghubar-das/saryu-roy regression: an actor candidate minted off
    another actor candidate, whose OWN `from_candidate` resolves to a
    problem, ends up with a `works_on` edge to that ANCESTOR PROBLEM on
    promotion — not the immediate actor parent, and not left unlinked."""
    problem(conn, "aadhaar-linked-pds-exclusion", title="Aadhaar-linked PDS exclusion")
    grandparent = make_candidate(conn, kind="problem", name="Aadhaar-linked PDS exclusion")
    conn.execute("UPDATE candidate SET resolved_to = ? WHERE id = ?",
                ("aadhaar-linked-pds-exclusion", grandparent["id"]))
    parent = make_candidate(
        conn, kind="actor", name="Santoshi Kumari",
        evidence=json.dumps({"from_candidate": grandparent["id"]}))
    cand = make_candidate(
        conn, kind="actor", name="Saryu Roy",
        evidence=json.dumps({"from_candidate": parent["id"],
                            "ancestor_problem_check": True}))
    conn.commit()
    actor(conn, "saryu-roy")

    worker._backfill_trigger_edge(conn, cand, "actor", "saryu-roy",
                                  by="worker:test", log=lambda *a: None)

    linked = conn.execute(
        "SELECT * FROM edge WHERE src_kind = 'actor' AND src_id = 'saryu-roy' "
        "AND dst_kind = 'problem' AND dst_id = 'aadhaar-linked-pds-exclusion' "
        "AND kind = 'works_on'").fetchone()
    assert linked is not None
    # Not linked to the immediate actor parent — that edge would be
    # semantically wrong (works_on is actor -> problem only).
    assert conn.execute(
        "SELECT count(*) c FROM edge WHERE dst_kind = 'actor'"
    ).fetchone()["c"] == 0


def test_backfill_trigger_edge_noop_when_actor_chain_has_no_ancestor_problem(conn):
    """The chain bottoms out in another actor with no further
    `from_candidate` — no edge written, no crash, just a log line."""
    root = make_candidate(conn, kind="actor", name="Root Actor", evidence=json.dumps({}))
    cand = make_candidate(
        conn, kind="actor", name="Child Actor",
        evidence=json.dumps({"from_candidate": root["id"],
                            "ancestor_problem_check": True}))
    actor(conn, "child-actor")

    logged = []
    worker._backfill_trigger_edge(conn, cand, "actor", "child-actor",
                                  by="worker:test", log=logged.append)

    assert conn.execute("SELECT count(*) c FROM edge").fetchone()["c"] == 0
    assert any("no resolvable ancestor problem" in m for m in logged)


# ---------------------------------------------------------- track B: depth tier

def test_emit_stores_a_predicted_depth_for_an_actor_mention(conn):
    src = _source_candidate(conn, resolved_to="src-actor", kind="actor")
    conn.execute("INSERT INTO actor (id, title, type) VALUES ('src-actor', 'S', 'org')")
    conn.commit()
    claims = {"emits": [{"kind": "actor", "name": "Quarry Workers Collective",
                        "hint": "an affected-led collective"}], "edges": []}
    worker._emit(conn, src, claims, {}, log=lambda *a: None)
    row = conn.execute(
        "SELECT * FROM candidate WHERE name = 'Quarry Workers Collective'").fetchone()
    payload = json.loads(row["evidence"])
    assert payload["predicted_depth"] == "tracked"


def test_emit_predicted_depth_defaults_to_registry(conn):
    src = _source_candidate(conn, resolved_to="src-actor", kind="actor")
    conn.execute("INSERT INTO actor (id, title, type) VALUES ('src-actor', 'S', 'org')")
    conn.commit()
    claims = {"emits": [{"kind": "actor", "name": "Some Ministry Body",
                        "hint": "a national commission"}], "edges": []}
    worker._emit(conn, src, claims, {}, log=lambda *a: None)
    row = conn.execute(
        "SELECT * FROM candidate WHERE name = 'Some Ministry Body'").fetchone()
    payload = json.loads(row["evidence"])
    assert payload["predicted_depth"] == "registry"


def test_write_entity_escalates_depth_per_the_ground_test(conn, tmp_path):
    """A model claim of `depth: registry` is overridden to `tracked` when
    the extracted `affected_led`/`representation_unit` say otherwise —
    escalation only, never a silent narrowing."""
    decision = resolve.ResolveResult(decision="new", entity_id=None, shortlist=[], reason="")
    claims = [
        {"field": "title", "value": "Quarry Workers Collective"},
        {"field": "depth", "value": "registry"},
        {"field": "affected_led", "value": "yes"},
        {"field": "representation_unit", "value": "local-affected"},
    ]
    entity_id = worker._write_entity(conn, tmp_path, "actor", "Quarry Workers Collective",
                                     decision, claims, by="test", log=lambda *a: None)
    row = conn.execute("SELECT * FROM actor WHERE id = ?", (entity_id,)).fetchone()
    assert row["depth"] == "tracked"


def test_write_entity_leaves_depth_alone_when_ground_test_inputs_absent(conn, tmp_path):
    decision = resolve.ResolveResult(decision="new", entity_id=None, shortlist=[], reason="")
    claims = [{"field": "title", "value": "Some Org"}, {"field": "depth", "value": "registry"}]
    entity_id = worker._write_entity(conn, tmp_path, "actor", "Some Org",
                                     decision, claims, by="test", log=lambda *a: None)
    row = conn.execute("SELECT * FROM actor WHERE id = ?", (entity_id,)).fetchone()
    assert row["depth"] == "registry"


def test_write_entity_logs_requeue_when_predicted_registry_verdicts_tracked(
        conn, tmp_path):
    decision = resolve.ResolveResult(decision="new", entity_id=None, shortlist=[], reason="")
    claims = [{"field": "title", "value": "Quarry Workers Collective"},
             {"field": "affected_led", "value": "yes"}]
    logged = []
    worker._write_entity(conn, tmp_path, "actor", "Quarry Workers Collective",
                         decision, claims, by="test", log=logged.append,
                         predicted_depth="registry")
    assert any("requeue" in msg for msg in logged)


def test_write_entity_depth_tier_disabled_degrades_to_model_claim(conn, tmp_path):
    """`depth_tier=False` is E6's call-site parameter, replacing the
    `WORKER_DEPTH_TIER` env var this test used to monkeypatch."""
    decision = resolve.ResolveResult(decision="new", entity_id=None, shortlist=[], reason="")
    claims = [{"field": "title", "value": "Quarry Workers Collective"},
             {"field": "depth", "value": "registry"},
             {"field": "affected_led", "value": "yes"}]
    entity_id = worker._write_entity(conn, tmp_path, "actor", "Quarry Workers Collective",
                                     decision, claims, by="test", log=lambda *a: None,
                                     depth_tier=False)
    row = conn.execute("SELECT * FROM actor WHERE id = ?", (entity_id,)).fetchone()
    assert row["depth"] == "registry"   # ground test never ran — today's behaviour


def test_edge_dst_kind_synonyms_are_normalised_not_dropped(conn, monkeypatch):
    """`org` and `individual` are q2_type's vocabulary, not dst_kind's. Both
    name an actor; dropping the edge loses a real relation over a word."""
    actor(conn, "src-actor")
    actor(conn, "dst-actor")
    src = _source_candidate(conn, resolved_to="src-actor")

    claims = {"emits": [], "edges": [
        {"dst_kind": "org", "dst_name": "dst-actor",
         "edge_kind": "funds", "relevance": 2},
    ]}
    _, edges = worker._emit(conn, src, claims, {}, log=lambda *a: None)
    assert edges == 1


def test_unknown_dst_kind_is_logged_not_silent(conn):
    src = _source_candidate(conn, resolved_to="src-actor")
    lines = []
    claims = {"emits": [], "edges": [
        {"dst_kind": "galaxy", "dst_name": "Andromeda",
         "edge_kind": "funds"}]}
    worker._emit(conn, src, claims, {}, log=lines.append)
    assert any("galaxy" in l for l in lines)


# --- track D wired into the CLI (`--search-url` / `--no-search`) -----------


def test_build_search_provider_is_none_for_the_no_search_path():
    assert worker._build_search_provider(None) is None


def test_build_search_provider_wraps_a_searxng_provider_in_throttled():
    from search.provider import SearxngProvider, ThrottledProvider

    provider = worker._build_search_provider("http://localhost:8080")
    assert isinstance(provider, ThrottledProvider)
    assert isinstance(provider._inner, SearxngProvider)
    assert provider._inner.base_url == "http://localhost:8080"


def test_no_search_flag_reaches_run_batch_as_none(conn, tmp_path, monkeypatch):
    """`--no-search` is the escape hatch back to §13's seed-URL-only degrade
    — confirms the flag actually reaches `run_batch`, not just that the
    argparse flag parses."""
    monkeypatch.setattr(worker, "open_store", lambda args, log=print: conn)
    seen = {}
    real_run_batch = worker.run_batch

    def _spy(conn, corpus, candidates, *, log=print, search_provider=None, **kw):
        seen["search_provider"] = search_provider
        return real_run_batch(conn, corpus, candidates, log=log,
                              search_provider=search_provider, **kw)
    monkeypatch.setattr(worker, "run_batch", _spy)

    worker.main(["--corpus", str(tmp_path), "--no-search", "--quiet"])
    assert seen["search_provider"] is None


def test_search_url_flag_reaches_run_batch_as_a_provider(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "open_store", lambda args, log=print: conn)
    seen = {}
    real_run_batch = worker.run_batch

    def _spy(conn, corpus, candidates, *, log=print, search_provider=None, **kw):
        seen["search_provider"] = search_provider
        return real_run_batch(conn, corpus, candidates, log=log,
                              search_provider=search_provider, **kw)
    monkeypatch.setattr(worker, "run_batch", _spy)

    worker.main(["--corpus", str(tmp_path), "--search-url", "http://localhost:9999",
                "--quiet"])
    assert seen["search_provider"] is not None
    assert seen["search_provider"]._inner.base_url == "http://localhost:9999"


# --------------------------------------------------- --ids / --force rerun --

def test_select_ids_skips_already_resolved_by_default(conn):
    cand = make_candidate(conn, kind="actor", name="Resolved Org")
    conn.execute("UPDATE candidate SET resolved_to = 'resolved-org' WHERE id = ?",
                (cand["id"],))
    conn.commit()

    logged = []
    result = worker._select_ids_candidates(conn, [cand["id"]], force=False,
                                           log=logged.append)
    assert result == []
    assert any("skipping" in m for m in logged)


def test_select_ids_force_reprocesses_already_resolved(conn):
    cand = make_candidate(conn, kind="actor", name="Resolved Org")
    conn.execute("UPDATE candidate SET resolved_to = 'resolved-org' WHERE id = ?",
                (cand["id"],))
    conn.commit()

    logged = []
    result = worker._select_ids_candidates(conn, [cand["id"]], force=True,
                                           log=logged.append)
    assert [r["id"] for r in result] == [cand["id"]]
    assert any("reprocessing (--force)" in m for m in logged)


def test_select_ids_force_does_not_affect_missing_ids(conn):
    logged = []
    result = worker._select_ids_candidates(conn, [999999], force=True,
                                           log=logged.append)
    assert result == []
    assert any("999999 not found" in m for m in logged)


def test_main_force_flag_reaches_ids_selection(conn, tmp_path, monkeypatch):
    """Confirms `--force` on the CLI actually reaches `_select_ids_candidates`
    as `force=True`, not just that the argparse flag parses."""
    cand = make_candidate(conn, kind="actor", name="Resolved Org")
    conn.execute("UPDATE candidate SET resolved_to = 'resolved-org' WHERE id = ?",
                (cand["id"],))
    conn.commit()

    monkeypatch.setattr(worker, "open_store", lambda args, log=print: conn)
    seen = {}
    real_select = worker._select_ids_candidates

    def _spy(conn, ids, *, force, log=print):
        seen["force"] = force
        return real_select(conn, ids, force=force, log=log)
    monkeypatch.setattr(worker, "_select_ids_candidates", _spy)
    monkeypatch.setattr(worker, "run_batch", lambda *a, **kw: {})

    worker.main(["--corpus", str(tmp_path), "--no-search", "--quiet",
                "--ids", str(cand["id"]), "--force"])
    assert seen["force"] is True
