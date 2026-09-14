"""Track E6 — the integration seam. Every other `run_batch` test uses a
candidate with no URL, so none of them enters the batched path E6 wired
(search stage -> passage assembly -> batched call -> ledger -> claims from
findings). These do.

Offline like `tests/test_worker.py`: `worker.fetchmod.fetch`,
`worker.gate2.confirm`, `worker.llm.call` and the resolver's encoder are all
stubbed. The one real model load is `extract_mod.assemble`'s ranking encoder
— unavoidable, since selection is what makes a prompt source at all.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
import math

import pytest

vec = pytest.importorskip("sqlite_vec")

from embed import index
from embed.model import EMBED_DIM, MODEL_NAME
from search.provider import ReplayProvider, SearchResponse
from store import db
from worker import gate1, resolve, worker

needs_model = pytest.mark.skipif(
    not pathlib.Path.home().joinpath(
        ".cache/huggingface/hub",
        "models--" + MODEL_NAME.replace("/", "--")).exists(),
    reason=f"{MODEL_NAME} not downloaded")

POC0B = pathlib.Path(__file__).resolve().parents[1] / "poc" / "poc0b-responses"


@pytest.fixture
def conn(tmp_path):
    c = index.connect(tmp_path / "g.db")
    yield c
    c.close()


def unit(*head) -> list[float]:
    v = list(head) + [0.0] * (EMBED_DIM - len(head))
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def make_candidate(c, kind="actor", name="Some Org", url=None, evidence=None,
                   admitted=1):
    cur = c.execute(
        "INSERT INTO candidate (kind, name, url, evidence, admitted) "
        "VALUES (?, ?, ?, ?, ?)", (kind, name, url, evidence, admitted))
    c.commit()
    return c.execute("SELECT * FROM candidate WHERE id = ?",
                     (cur.lastrowid,)).fetchone()


# Long enough to chunk into several paragraphs, and different enough between
# the two pages that ranking has something to separate.
PAGE_A = "\n\n".join([
    "Acumen is a fund based in Mumbai that places patient capital into "
    "early-stage enterprises serving low-income customers across India.",
    "The fund was formed in 2001 and its first India office opened in 2006. "
    "It reports a portfolio of eighty-two companies as of the last annual "
    "letter, with agriculture and off-grid energy the two largest sectors.",
    "Funding comes from philanthropic donors rather than limited partners, "
    "and the fund states that returned capital is recycled into new "
    "investments rather than distributed.",
    "Its contact route is a public enquiries address published on the "
    "website, and it accepts unsolicited pitches through a web form.",
    # Padding, added 2026-09-14. confirm_policy.THIN_PAGE_CHARS is measured
    # and on by default now, and these fixtures were 644/656 chars — about
    # 100 words, which is genuinely a stub and correctly routes to the verify
    # pass. These tests are about search adding sources, not about thinness,
    # so the fixture is brought up to the length of an ordinary fetched
    # article rather than the threshold being loosened to fit it.
    "The annual letter goes on to describe the fund's approach to "
    "measurement, noting that it tracks reach rather than outcome for most "
    "of the portfolio, and that outcome measurement is confined to three "
    "sectors where a validated instrument already exists.",
    "A section on exits records that the fund has completed fourteen full "
    "or partial exits since inception, that the median holding period was "
    "just over seven years, and that two of those exits returned less than "
    "the original investment.",
])
PAGE_B = "\n\n".join([
    "A profile of the fund notes that it operates in India, Pakistan and "
    "several countries in East and West Africa, with the India programme "
    "the oldest of the three regional programmes.",
    "The profile describes the leadership as a professional investment team "
    "recruited from banking and consulting, not drawn from the communities "
    "the portfolio companies serve.",
    "Observers have questioned whether the returns reported by the fund are "
    "comparable with commercial venture benchmarks, since the fund's own "
    "cost of capital is a grant.",
    # See the note on PAGE_A: padded past THIN_PAGE_CHARS deliberately.
    "The same profile records that the fund publishes an annual portfolio "
    "list, that the list has grown in every year but two, and that the "
    "reporting unit is the investee company rather than the end customer.",
    "It closes by noting that the fund convenes an annual gathering of its "
    "investees, that attendance is not conditional on continued investment, "
    "and that several alumni companies continue to attend.",
    "The organisation publishes an annual report and a searchable portfolio "
    "directory listing every company it has backed since inception.",
])


class FakeFetch:
    """`worker.fetchmod.fetch`-shaped, and it writes a REAL `source` row —
    `finding.source_id` is an FK into `source` (`store/schema.sql:323`), so a
    stub that only invents an id would let a broken FK pass unnoticed."""

    def __init__(self, conn, texts, default_text=""):
        self.conn = conn
        self.texts = texts          # url -> text
        self.default_text = default_text
        self.urls = []

    def __call__(self, conn, corpus, url):
        self.urls.append(url)
        text = self.texts.get(url, self.default_text)
        source_id = "src-" + str(abs(hash(url)) % 10 ** 9)
        self.conn.execute(
            "INSERT OR IGNORE INTO source (id, url, url_canonical) "
            "VALUES (?, ?, ?)", (source_id, url, url))
        return type("FetchResult", (), {"text": text, "source_id": source_id})()


def stub_pipeline(monkeypatch, conn, *, fetch, extract_json, screen_ids,
                  verdict="confirmed"):
    """The house pattern of `tests/test_worker.py:_stub_llm_for_run_batch`,
    extended with the two things the batched path also touches: the fetcher
    and gate 2. `extract_json` may be a list — one entry per extraction call,
    for the §13 retry test."""
    calls = {"extract": 0}
    sequence = extract_json if isinstance(extract_json, list) else None

    def fake_call(prompt, *, system=None, tier="mechanical", max_tokens=2048, **kw):
        if "decisions" in prompt or "Screen these candidates" in prompt:
            return {"json": {"decisions": [
                {"id": str(i), "keep": True, "reason": "ok"} for i in screen_ids]},
                "model": "test-model", "cost": 0.0}
        i = calls["extract"]
        calls["extract"] += 1
        payload = sequence[min(i, len(sequence) - 1)] if sequence else extract_json
        return {"json": payload, "model": "test-model", "cost": 0.001}

    monkeypatch.setattr(worker.llm, "call", fake_call)
    monkeypatch.setattr(gate1.llm, "call", fake_call)
    monkeypatch.setattr(worker.fetchmod, "fetch", fetch)
    monkeypatch.setattr(worker.gate2, "confirm",
                        lambda c, name, ev, text: (verdict, 0.91, "stub"))
    monkeypatch.setattr(resolve, "encode_one", lambda text, *, role: unit(1.0))
    monkeypatch.setattr(resolve.index, "knn",
                        lambda c, kind, v, *, k=10, role="query", exclude=None: [])
    return calls


BATCHED_JSON = {
    "answers": [
        {"question_id": "q1_one_line", "source_id": "S1",
         "answer": "Patient-capital fund for early-stage enterprises",
         "confidence": 0.9},
        {"question_id": "q8_geography", "source_id": "S1",
         "answer": "India", "confidence": 0.8},
    ],
    # Deliberately DIFFERENT from what the answers imply. §9 says claims are
    # derived from findings; if the model's own list ever wins again, these
    # two values are what lands in the row.
    "claims": [
        {"field": "one_line", "value": "MODEL CLAIM THAT MUST LOSE",
         "confidence": 0.99},
        {"field": "geography", "value": "Kenya", "confidence": 0.99},
    ],
    "emits": [{"kind": "actor", "name": "Spun Off Org", "hint": "mentioned"}],
    "edges": [],
}


# ----------------------------------------------------- 1. the batched path --

@needs_model
def test_batched_path_writes_findings_and_claims_come_from_findings(
        conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A + "\n\n" + PAGE_B})
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    report = worker.run_batch(conn, tmp_path, [cand])

    assert report["extracted_batched"] == 1
    assert report["extracted_single"] == 0
    assert report["findings_written"] >= 1

    rows = conn.execute("SELECT * FROM finding WHERE candidate_id = ?",
                        (cand["id"],)).fetchall()
    assert rows, "the batched path wrote no findings"
    for row in rows:
        assert row["source_id"] is not None
        assert conn.execute("SELECT 1 FROM source WHERE id = ?",
                            (row["source_id"],)).fetchone() is not None
        assert row["source_url"]

    # THE assertion: the written columns came from `claims_from_findings`,
    # not from the model's `claims` key.
    row = conn.execute("SELECT * FROM candidate WHERE id = ?",
                       (cand["id"],)).fetchone()
    entity = conn.execute("SELECT * FROM actor WHERE id = ?",
                          (row["resolved_to"],)).fetchone()
    assert entity["one_line"] == "Patient-capital fund for early-stage enterprises"
    assert entity["one_line"] != "MODEL CLAIM THAT MUST LOSE"
    # `geography` is one of `_JSON_LIST_COLUMNS`, hence the list form.
    assert json.loads(entity["geography"]) == ["India"]
    assert "Kenya" not in entity["geography"]


# ----------------------------------------- 2. the no-url single-source path --

def test_no_url_candidate_still_takes_the_single_source_path(
        conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Registry Stub Org")
    fetch = FakeFetch(conn, {})
    prompts_seen = []
    stub_pipeline(monkeypatch, conn, fetch=fetch, screen_ids=[cand["id"]],
                  extract_json={"claims": [{"field": "one_line",
                                            "value": "from the single call"}],
                                "emits": [], "edges": []})
    real_call = worker.llm.call

    def spy(prompt, *, system=None, **kw):
        prompts_seen.append(prompt)
        return real_call(prompt, system=system, **kw)
    monkeypatch.setattr(worker.llm, "call", spy)

    report = worker.run_batch(conn, tmp_path, [cand])

    assert report["extracted_single"] == 1
    assert report["extracted_batched"] == 0
    assert report["findings_written"] == 0
    assert report["fetched"] == 0
    assert fetch.urls == []
    assert conn.execute("SELECT count(*) c FROM finding").fetchone()["c"] == 0
    # the single-source prompt, not the `[S1] <url>` batched one
    extraction = [p for p in prompts_seen if "Screen these candidates" not in p]
    assert extraction and "[S1]" not in extraction[-1]


# ------------------------------------------------ 3/4. the search provider --

def test_search_provider_none_is_the_degrade_seed_url_only(
        conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A})
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])
    called = []
    monkeypatch.setattr(worker.search_stage, "search_sources",
                        lambda *a, **kw: called.append(kw) or [])

    report = worker.run_batch(conn, tmp_path, [cand], search_provider=None)

    assert called == [], "the search stage ran with no provider"
    assert fetch.urls == ["https://a.test/one"]
    assert report["sources_fetched"] == 1


@needs_model
def test_search_provider_adds_sources_beyond_the_seed(conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A},
                      default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    report = worker.run_batch(conn, tmp_path, [cand],
                              search_provider=ReplayProvider(POC0B),
                              max_sources=3)

    assert len(fetch.urls) > 1, "only the seed was fetched"
    assert report["sources_fetched"] > 1
    assert report["sources_in_prompt"] >= 1
    assert report["unread_pool_urls"] > 0, (
        "the RRF pool was fully consumed — counter 2 cannot be read")


class SeedEchoProvider:
    """A provider whose results include the candidate's OWN seed URL — the
    case `search_sources(seed_url=None)` cannot dedupe by itself."""

    def __init__(self, urls):
        self.urls = urls

    def search(self, family_id, query_string, *, slug=None):
        raw = [{"url": u, "title": u, "content": "", "score": 1.0 - i * 0.1,
                "engine": "google", "engines": ["google", "bing", "duckduckgo"]}
               for i, u in enumerate(self.urls)]
        return SearchResponse(
            results=[], unresponsive_engines=[],
            engines_seen_in_results=["google", "bing", "duckduckgo"],
            configured_engines=["google", "bing", "duckduckgo"],
            silently_absent_engines=[], raw_results=raw)


@needs_model
def test_seed_url_returned_by_search_is_not_a_second_source(
        conn, monkeypatch, tmp_path):
    """Regression: set cover can pick the seed's own URL, and `fetch` returns
    the same cached `source.id` for it. Before the dedupe in `run_batch`, the
    seed was gate-2'd twice, counted twice in `sources_fetched`, and chunked
    twice by `assemble` — the same passages repeated inside one `[Sn]` block.
    """
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])
    provider = SeedEchoProvider(["https://a.test/one", "https://b.test/two"])

    report = worker.run_batch(conn, tmp_path, [cand], search_provider=provider)

    assert report["sources_fetched"] == 2, "the seed was counted twice"
    assert report["sources_in_prompt"] == 2


def test_out_of_range_confidence_does_not_abort_the_batch(
        conn, monkeypatch, tmp_path):
    """Regression: `finding.confidence` has a `BETWEEN 0 AND 1` CHECK. A model
    answering `95` raised sqlite3.IntegrityError straight out of `run_batch`,
    taking every later candidate in the batch with it. The parser now drops
    the bad confidence and keeps the answer, as it already did for a
    non-numeric one."""
    from worker.prompts import parse_answers
    from worker.extract_types import PromptSource

    src = PromptSource(source_id="src-1", label="S1", url="https://a.test/one",
                       text="x", chunk_refs=("src-1:0",))
    answers, problems = parse_answers(
        {"answers": [{"question_id": "q1_one_line", "source_id": "S1",
                      "answer": "kept", "confidence": 95}]}, [src])
    assert len(answers) == 1
    assert answers[0].confidence is None
    assert any("outside 0-1" in p for p in problems)


@needs_model
def test_out_of_range_confidence_still_writes_the_finding(
        conn, monkeypatch, tmp_path):
    """The same bug, end to end: the batch completes and the finding lands
    with a NULL confidence rather than no finding at all."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A + "\n\n" + PAGE_B})
    payload = json.loads(json.dumps(BATCHED_JSON))
    payload["answers"][0]["confidence"] = 95
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=payload,
                  screen_ids=[cand["id"]])

    report = worker.run_batch(conn, tmp_path, [cand])   # must not raise

    assert report["findings_written"] == 2
    row = conn.execute(
        "SELECT * FROM finding WHERE question_id = 'q1_one_line'").fetchone()
    assert row["confidence"] is None
    assert row["answer"] == "Patient-capital fund for early-stage enterprises"


# -------------------------------------------------- 5. §13 per-source retry --

@needs_model
def test_batched_parse_failure_retries_per_source_and_rescues(
        conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A + "\n\n" + PAGE_B})
    rescued = {
        "answers": [{"question_id": "q1_one_line", "source_id": "S1",
                     "answer": "rescued one-liner", "confidence": 0.7}],
        "claims": [], "emits": [], "edges": [],
    }
    # call 0 = the batched call, unparseable (llm.parse_json left `json` unset)
    stub_pipeline(monkeypatch, conn, fetch=fetch, screen_ids=[cand["id"]],
                  extract_json=[None, rescued])

    report = worker.run_batch(conn, tmp_path, [cand])

    assert report["retry_per_source_calls"] >= 1
    assert report["retry_per_source_rescued"] >= 1
    assert report["findings_written"] >= 1
    rows = conn.execute("SELECT * FROM finding WHERE candidate_id = ?",
                        (cand["id"],)).fetchall()
    assert [r["answer"] for r in rows] == ["rescued one-liner"] * len(rows)
    row = conn.execute("SELECT * FROM candidate WHERE id = ?",
                       (cand["id"],)).fetchone()
    entity = conn.execute("SELECT * FROM actor WHERE id = ?",
                          (row["resolved_to"],)).fetchone()
    assert entity["one_line"] == "rescued one-liner"


# ------------------------------------------------------------ 6. counters --

@needs_model
def test_report_counters_hold_plausible_values(conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A + "\n\n" + PAGE_B})
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])

    report = worker.run_batch(conn, tmp_path, [cand])

    # §11c. None of the four high-value questions is answered by BATCHED_JSON,
    # and `p*` ids are problem questions an actor candidate can never answer.
    assert report["hv_questions_open"] == len(worker._HIGH_VALUE_QUESTIONS)
    assert report["unread_pool_urls"] == 0          # no provider, no pool
    assert report["new_query_seeds"] == 1           # "Spun Off Org", != "Acumen"

    # E3's four coverage keys.
    assert report["sources_fetched"] == 1
    assert report["sources_in_prompt"] == 1
    assert report["sources_never_selected"] == 0
    assert report["sources_dropped_by_cap"] == 0    # `_cap_tokens`' guarantee


# ------------------------------ 7. the two switches, through `run_batch` --

def _emitting_json():
    return {
        "claims": [{"field": "one_line", "value": "a fund"}],
        "emits": [{"kind": "actor", "name": "Spun Off Org", "hint": "mentioned"}],
        "edges": [{"dst_kind": "problem", "dst_name": "Nobody counts silicosis",
                   "edge_kind": "works_on", "relevance": 3}],
    }


@pytest.mark.parametrize("depth_tier", [True, False])
def test_depth_tier_reaches_emit_through_run_batch(conn, monkeypatch, tmp_path,
                                                   depth_tier):
    cand = make_candidate(conn, kind="actor", name="Registry Stub Org")
    stub_pipeline(monkeypatch, conn, fetch=FakeFetch(conn, {}),
                  screen_ids=[cand["id"]], extract_json=_emitting_json())

    worker.run_batch(conn, tmp_path, [cand], depth_tier=depth_tier,
                     problem_emission=False)

    row = conn.execute("SELECT * FROM candidate WHERE name = 'Spun Off Org'"
                       ).fetchone()
    payload = json.loads(row["evidence"])
    assert ("predicted_depth" in payload) is depth_tier


@pytest.mark.parametrize("problem_emission", [True, False])
def test_problem_emission_reaches_emit_through_run_batch(
        conn, monkeypatch, tmp_path, problem_emission):
    cand = make_candidate(conn, kind="actor", name="Registry Stub Org")
    stub_pipeline(monkeypatch, conn, fetch=FakeFetch(conn, {}),
                  screen_ids=[cand["id"]], extract_json=_emitting_json())

    worker.run_batch(conn, tmp_path, [cand], problem_emission=problem_emission)

    minted = conn.execute(
        "SELECT count(*) c FROM candidate WHERE kind = 'problem'").fetchone()["c"]
    assert (minted > 0) is problem_emission


# ------------------------------------------------------- 8. _predicted_depth --

def test_predicted_depth_reads_track_bs_intake_prediction(conn):
    cand = make_candidate(conn, kind="actor", name="Emitted Org",
                          evidence=json.dumps({"hint": "mentioned",
                                               "from_candidate": 1,
                                               "predicted_depth": "tracked"}))
    assert worker._predicted_depth(cand) == "tracked"


def test_predicted_depth_is_none_for_ordinary_snippet_evidence(conn):
    cand = make_candidate(conn, kind="actor", name="Snippet Org",
                          evidence="a plain snippet of prose, not JSON")
    assert worker._predicted_depth(cand) is None
    assert worker._predicted_depth(
        make_candidate(conn, kind="actor", name="Empty Org", evidence=None)) is None


def test_predicted_depth_is_none_for_json_that_is_not_an_object(conn):
    cand = make_candidate(conn, kind="actor", name="List Org",
                          evidence=json.dumps(["tracked"]))
    assert worker._predicted_depth(cand) is None


# ------------------------------------------------------ the verify pass ----
# `03-worker.md` §6a. Gate-2 `uncertain` sources no longer enter the main
# extraction prompt; they go to a second call whose first job is an identity
# verdict per source. These tests drive it through `run_batch`.

VERIFY_JSON = {
    "verdicts": [
        {"source_id": "S1", "verdict": "about",
         "why": "describes the fund's portfolio and India office"},
    ],
    "answers": [
        {"question_id": "q8_geography", "source_id": "S1",
         "answer": "India", "confidence": 0.8},
    ],
    "claims": [], "emits": [], "edges": [],
}

VERIFY_ALL_REJECTED = {
    "verdicts": [
        {"source_id": "S1", "verdict": "different",
         "about_what": "a water heater manufacturer sharing the name"},
    ],
    "answers": [
        {"question_id": "q8_geography", "source_id": "S1",
         "answer": "Gujarat", "confidence": 0.9},
    ],
    "claims": [], "emits": [], "edges": [],
}


def _uncertain_pipeline(monkeypatch, conn, fetch, extract_json, screen_ids):
    """stub_pipeline, but gate 2 returns `uncertain` for every source, so the
    whole source set routes to the verify bucket."""
    return stub_pipeline(monkeypatch, conn, fetch=fetch,
                         extract_json=extract_json, screen_ids=screen_ids,
                         verdict="uncertain")


def test_uncertain_sources_do_not_reach_the_main_extraction_prompt(
        conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    seen = []

    calls = _uncertain_pipeline(monkeypatch, conn, fetch,
                               [VERIFY_JSON, BATCHED_JSON], [cand["id"]])
    real_call = worker.llm.call

    def recording_call(prompt, *, system=None, **kw):
        seen.append(system or "")
        return real_call(prompt, system=system, **kw)
    monkeypatch.setattr(worker.llm, "call", recording_call)

    report = worker.run_batch(conn, tmp_path, [cand],
                              search_provider=ReplayProvider(POC0B),
                              max_sources=3)

    assert report["sources_in_prompt"] == 0, (
        "an uncertain source reached the main extraction prompt")
    assert report["verify_pass_calls"] == 1
    assert any("UNVERIFIED" in s for s in seen), "the verify prompt never ran"


def test_verify_pass_merges_answers_from_sources_it_accepted(
        conn, monkeypatch, tmp_path):
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    _uncertain_pipeline(monkeypatch, conn, fetch, VERIFY_JSON, [cand["id"]])

    report = worker.run_batch(conn, tmp_path, [cand],
                              search_provider=ReplayProvider(POC0B),
                              max_sources=3)

    assert report["verify_about"] >= 1
    assert report["verify_answers_merged"] >= 1
    assert report["findings_written"] >= 1, (
        "a verified answer must reach the ledger like any other")


def test_verify_pass_rejecting_everything_writes_nothing(
        conn, monkeypatch, tmp_path):
    """The wrong-entity case. The model identifies a name collision and its
    answer from that source must not survive — the parser enforces it rather
    than trusting the instruction."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    _uncertain_pipeline(monkeypatch, conn, fetch, VERIFY_ALL_REJECTED,
                        [cand["id"]])

    report = worker.run_batch(conn, tmp_path, [cand],
                              search_provider=ReplayProvider(POC0B),
                              max_sources=3)

    assert report["verify_different"] >= 1
    assert report["verify_answers_merged"] == 0
    assert report["verify_about"] == 0


def test_adequate_confirmed_set_buys_no_verify_call(conn, monkeypatch, tmp_path):
    """The pass costs a second paid call. A candidate whose confirmed set can
    carry it alone must not buy one."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch, extract_json=BATCHED_JSON,
                  screen_ids=[cand["id"]])   # verdict="confirmed"

    report = worker.run_batch(conn, tmp_path, [cand],
                              search_provider=ReplayProvider(POC0B),
                              max_sources=3)

    assert report["sources_in_prompt"] >= 1
    assert report["verify_pass_calls"] == 0


MISIDENTIFIED_JSON = {
    "answers": [
        {"question_id": "q1_one_line", "source_id": "S1",
         "answer": "Patient-capital fund", "confidence": 0.9},
        {"question_id": "q10_funding", "source_id": "S1",
         "answer": "revenue of 40 crore", "confidence": 0.9},
    ],
    "misidentified": [
        {"source_id": "S1", "about_what": "a manufacturer sharing the name",
         "why": "the page sells appliances"},
    ],
    "claims": [], "emits": [], "edges": [],
}


def test_model_flagging_a_confirmed_source_drops_its_answers(
        conn, monkeypatch, tmp_path):
    """Rule 4 end to end. The source cleared gate 2 — the model read the whole
    page and says it is a different entity, and its answers must not reach the
    ledger."""
    cand = make_candidate(conn, kind="actor", name="Acumen",
                          url="https://a.test/one")
    fetch = FakeFetch(conn, {"https://a.test/one": PAGE_A}, default_text=PAGE_B)
    stub_pipeline(monkeypatch, conn, fetch=fetch,
                  extract_json=MISIDENTIFIED_JSON, screen_ids=[cand["id"]])

    report = worker.run_batch(conn, tmp_path, [cand],
                              search_provider=None, max_sources=3)

    assert report["sources_flagged_misidentified"] == 1
    assert report["findings_written"] == 0, (
        "answers from a flagged source reached the ledger")
