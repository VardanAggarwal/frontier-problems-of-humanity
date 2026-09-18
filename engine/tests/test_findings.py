"""Track E4 (`04-worker-build-plan.md` §5, `03-worker.md` §9) — the findings
ledger and the claims derived from it.

`03-worker.md` §9's conflicting branch has never run against a real
contradiction: PoC-2b tried and its plant was unanswerable by construction
(`poc/poc2c-spec.md`). These tests are therefore the only evidence that
branch works, and they cover each of §9's four rules by name — one answer,
consistent duplicates, substring specificity, genuine conflict at two and at
three sides, and zero answers.

No network, no LLM, no encoder. `write_findings` runs against a real sqlite
database built from `store/schema.sql` via `store/db.py`.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from store import db
from worker import extract
from worker.extract_types import Answer


def A(qid, answer, source_id="src-1", confidence=None, chunk_ref=None, reason=None):
    return Answer(question_id=qid, answer=answer, source_id=source_id,
                  confidence=confidence, chunk_ref=chunk_ref, reason=reason)


# ------------------------------------------------------- write_findings ---
@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute("INSERT INTO candidate (id, kind, name) VALUES (1, 'actor', 'X')")
    for sid, url in (("s-a", "https://a.example/x"), ("s-b", "https://b.example/y")):
        c.execute("INSERT INTO source (id, url, url_canonical) VALUES (?, ?, ?)",
                  (sid, url, url))
    yield c
    c.close()


def test_write_findings_writes_one_row_per_answer(conn):
    answers = [A("q1_one_line", "A gig-worker union", "s-a", 0.9, "s-a:3"),
               A("q10_funding", "Member dues", "s-b", 0.4)]
    n = extract.write_findings(conn, 1, answers,
                               urls={"s-a": "https://a.example/x",
                                     "s-b": "https://b.example/y"})
    assert n == 2
    rows = conn.execute(
        "SELECT question_id, answer, confidence, source_url, source_id, "
        "chunk_ref, gathered_at FROM finding ORDER BY id").fetchall()
    assert [r["question_id"] for r in rows] == ["q1_one_line", "q10_funding"]
    assert rows[0]["source_id"] == "s-a"
    assert rows[0]["chunk_ref"] == "s-a:3"
    assert rows[0]["source_url"] == "https://a.example/x"
    assert rows[0]["confidence"] == 0.9
    assert rows[0]["gathered_at"]            # column default, not passed in
    assert rows[1]["chunk_ref"] is None      # block held >1 chunk


def test_write_findings_without_urls_leaves_source_url_null(conn):
    extract.write_findings(conn, 1, [A("q1_one_line", "x", "s-a")])
    row = conn.execute("SELECT source_url, source_id FROM finding").fetchone()
    assert row["source_url"] is None
    assert row["source_id"] == "s-a"        # the durable join survives


def test_write_findings_of_nothing_writes_nothing(conn):
    assert extract.write_findings(conn, 1, []) == 0
    assert conn.execute("SELECT count(*) FROM finding").fetchone()[0] == 0


def test_write_findings_is_append_only_across_calls(conn):
    extract.write_findings(conn, 1, [A("q1_one_line", "first", "s-a")])
    extract.write_findings(conn, 1, [A("q1_one_line", "second", "s-b")])
    # The ledger keeps every input to a claim; it does not overwrite.
    assert conn.execute("SELECT count(*) FROM finding").fetchone()[0] == 2


def test_write_findings_does_not_commit(conn):
    """The caller owns the transaction — a rollback must lose the rows."""
    extract.write_findings(conn, 1, [A("q1_one_line", "x", "s-a")])
    conn.rollback()
    assert conn.execute("SELECT count(*) FROM finding").fetchone()[0] == 0


def test_write_findings_persists_reason(conn):
    """`Answer.reason` — the closed-enum classification justification
    parsed by `worker/prompts.py` — must reach `finding.reason`, not be
    dropped before the INSERT (the bug this test guards)."""
    extract.write_findings(conn, 1, [
        A("q1_one_line", "x", "s-a", reason="named in the source as chronic, not latent")])
    row = conn.execute("SELECT reason FROM finding").fetchone()
    assert row["reason"] == "named in the source as chronic, not latent"


def test_write_findings_without_reason_leaves_it_null(conn):
    extract.write_findings(conn, 1, [A("q1_one_line", "x", "s-a")])
    row = conn.execute("SELECT reason FROM finding").fetchone()
    assert row["reason"] is None


def test_write_findings_resolves_chunk_text_by_chunk_ref(conn):
    """`chunk_texts` maps `chunk_ref` -> paragraph; `finding.chunk_text`
    must carry the paragraph for the answer's own `chunk_ref`, not any
    other entry in the map (schema v5, migrate/m0005_finding_chunk_text.py)."""
    n = extract.write_findings(
        conn, 1, [A("q1_one_line", "x", "s-a", chunk_ref="s-a:3")],
        chunk_texts={"s-a:2": "wrong paragraph", "s-a:3": "the right paragraph"})
    assert n == 1
    row = conn.execute("SELECT chunk_text FROM finding").fetchone()
    assert row["chunk_text"] == "the right paragraph"


def test_write_findings_without_chunk_ref_leaves_chunk_text_null(conn):
    """An answer with no resolvable chunk marker must not guess a paragraph
    from the map, even when the map is non-empty."""
    extract.write_findings(
        conn, 1, [A("q1_one_line", "x", "s-a")],
        chunk_texts={"s-a:0": "some paragraph"})
    row = conn.execute("SELECT chunk_text FROM finding").fetchone()
    assert row["chunk_text"] is None


def test_write_findings_chunk_ref_absent_from_map_leaves_chunk_text_null(conn):
    """A chunk_ref that does not resolve in the map (e.g. `retry_per_source`'s
    solo blocks, which never build one) writes NULL rather than raising."""
    extract.write_findings(
        conn, 1, [A("q1_one_line", "x", "s-a", chunk_ref="s-a:9")])
    row = conn.execute("SELECT chunk_text FROM finding").fetchone()
    assert row["chunk_text"] is None


def test_write_findings_source_id_is_a_real_fk(conn):
    """`finding.source_id REFERENCES source (id)` with foreign_keys ON."""
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        extract.write_findings(conn, 1, [A("q1_one_line", "x", "no-such-source")])


# ------------------------------ §9 rule 4: zero findings -> no claim -------
def test_zero_findings_yields_no_claim():
    claims, notes = extract.claims_from_findings([])
    assert claims == []
    assert notes == []


def test_a_question_with_no_answer_is_absent_not_guessed():
    claims, _ = extract.claims_from_findings([A("q1_one_line", "A union")])
    fields = {c["field"] for c in claims}
    assert fields == {"one_line"}
    # Nothing invented for the other 35 registry questions, and no "unknown".
    assert not any(c["value"] in (None, "", "unknown") for c in claims)


# ------------------------------ §9 rule 1: one finding -> claim directly ---
def test_one_finding_becomes_the_claim_directly():
    claims, notes = extract.claims_from_findings(
        [A("q1_one_line", "A gig-worker union in Bengaluru", "s-a", 0.7)])
    assert claims == [{"field": "one_line",
                       "value": "A gig-worker union in Bengaluru",
                       "confidence": 0.7}]
    assert notes == []


# --------------- §9 rule 2: multiple + consistent -> the most specific -----
def test_consistent_duplicates_collapse_to_one_claim():
    claims, notes = extract.claims_from_findings([
        A("q1_one_line", "A gig-worker union", "s-a", 0.9),
        A("q1_one_line", "a gig-worker union.", "s-b", 0.5),   # norm-equal
    ])
    assert len(claims) == 1
    assert claims[0]["field"] == "one_line"
    assert claims[0]["value"] in ("A gig-worker union", "a gig-worker union.")
    assert claims[0]["confidence"] == 0.5      # the weakest input
    assert "consistent" in notes[0]


def test_substring_picks_the_most_specific_never_a_concatenation():
    claims, notes = extract.claims_from_findings([
        A("q1_one_line", "A gig-worker union", "s-a"),
        A("q1_one_line", "A gig-worker union in Bengaluru", "s-b"),
    ])
    assert len(claims) == 1
    assert claims[0]["value"] == "A gig-worker union in Bengaluru"
    # explicitly NOT a join of the two
    assert ";" not in claims[0]["value"] and " / " not in claims[0]["value"]
    assert "most specific" in notes[0]


def test_three_way_nesting_is_still_consistent():
    claims, _ = extract.claims_from_findings([
        A("q1_one_line", "union", "s-a"),
        A("q1_one_line", "a gig-worker union", "s-b"),
        A("q1_one_line", "A gig-worker union in Bengaluru", "s-c"),
    ])
    assert len(claims) == 1
    assert claims[0]["value"] == "A gig-worker union in Bengaluru"


# --------------- §9 rule 3: multiple + conflicting -> state the disagreement
def test_two_conflicting_findings_make_one_claim_holding_both_sides():
    claims, notes = extract.claims_from_findings([
        A("q11_scale_metric", "12 lakh members", "s-a", 0.8),
        A("q11_scale_metric", "9 lakh members", "s-b", 0.6),
    ])
    assert len(claims) == 1                       # ONE claim, not two
    value = claims[0]["value"]
    assert claims[0]["field"] == "scale_metric"
    assert "12 lakh members" in value and "9 lakh members" in value
    assert "s-a" in value and "s-b" in value      # both sources named
    assert "disagree" in value.lower()
    # never averaged
    assert "10.5" not in value and "10,5" not in value
    assert claims[0]["confidence"] == 0.6         # no more confident than the weakest
    assert "conflicting" in notes[0]


def test_three_sided_conflict_drops_no_side():
    claims, notes = extract.claims_from_findings([
        A("q11_scale_metric", "12 lakh", "s-a"),
        A("q11_scale_metric", "9 lakh", "s-b"),
        A("q11_scale_metric", "40,000", "s-c"),
    ])
    assert len(claims) == 1
    value = claims[0]["value"]
    for side in ("12 lakh", "9 lakh", "40,000"):
        assert side in value
    for src in ("s-a", "s-b", "s-c"):
        assert src in value
    assert "3 conflicting values" in notes[0]


def test_conflict_groups_the_sources_agreeing_on_one_side():
    claims, _ = extract.claims_from_findings([
        A("q11_scale_metric", "9 lakh", "s-a"),
        A("q11_scale_metric", "9 lakh", "s-b"),
        A("q11_scale_metric", "12 lakh", "s-c"),
    ])
    value = claims[0]["value"]
    assert "sources s-a, s-b" in value
    assert "source s-c" in value


def test_a_partly_overlapping_set_is_a_conflict_not_a_pick():
    """"abc" ~ "b" and "b" ~ "xbz", but "abc" and "xbz" are not consistent —
    the rule is all-pairs, so this is a conflict rather than a silent pick."""
    claims, _ = extract.claims_from_findings([
        A("q11_scale_metric", "abc", "s-a"),
        A("q11_scale_metric", "b", "s-b"),
        A("q11_scale_metric", "xbz", "s-c"),
    ])
    assert "disagree" in claims[0]["value"].lower()
    assert claims[0]["value"].count('"') == 6      # three sides quoted


def test_no_numeric_threshold_is_consulted():
    """Confidence never decides which side wins — a low-confidence
    contradiction is still written down (§9: never silently drop a side)."""
    claims, _ = extract.claims_from_findings([
        A("q11_scale_metric", "12 lakh", "s-a", 0.99),
        A("q11_scale_metric", "9 lakh", "s-b", 0.01),
    ])
    assert "9 lakh" in claims[0]["value"]


# ------------------------------------------- multi, and the non-fields ----
def test_multi_valued_question_emits_one_claim_per_distinct_value():
    claims, notes = extract.claims_from_findings([
        A("q3_legs", "activism", "s-a"),
        A("q3_legs", "enterprise", "s-b"),
        A("q3_legs", "activism", "s-c"),
    ])
    assert {c["value"] for c in claims} == {"activism", "enterprise"}
    assert all(c["field"] == "legs" for c in claims)
    assert "multi-valued" in notes[0]


def test_multi_valued_question_still_prefers_the_most_specific_per_group():
    claims, _ = extract.claims_from_findings([
        A("p12_mechanism", "aggregation", "s-a"),
        A("p12_mechanism", "aggregation masks failure", "s-b"),
        A("p12_mechanism", "authority mismatched to harm", "s-c"),
    ])
    assert {c["value"] for c in claims} == {
        "aggregation masks failure", "authority mismatched to harm"}


def test_templated_and_emit_claim_fields_make_no_claim():
    claims, notes = extract.claims_from_findings([
        A("q16_channel", "https://x.example/feed", "s-a"),   # channel:<kind>
        A("q10b_funder_identity", "Azim Premji Philanthropic Initiatives", "s-b"),
    ])
    assert claims == []
    assert len(notes) == 2
    # Wording changed 2026-09-18: this note fires on every problem candidate
    # and used to read like a misconfiguration warning. What it must still
    # assert is that no claim was produced and the finding was kept.
    assert all("rather than a claim" in n for n in notes)
    assert all("finding(s) kept" in n for n in notes)


def test_unknown_question_id_makes_no_claim_but_is_reported():
    claims, notes = extract.claims_from_findings([A("q99_invented", "x", "s-a")])
    assert claims == []
    assert "not in the question registry" in notes[0]


# ------------------------------------------------ the shape worker.py eats -
def test_claim_shape_is_what_split_claims_consumes():
    from worker.worker import _split_claims
    claims, _ = extract.claims_from_findings([
        A("q2_type", "org", "s-a"),
        A("q3_legs", "activism", "s-b"),
        A("q9_contact_route", "office@example.org", "s-a"),
        A("q9_contact_route", "press@example.org", "s-b"),   # conflicting
        A("q5_ecosystem_role", "convener", "s-a"),           # tag: claim
    ])
    logged: list[str] = []
    columns, other = _split_claims("actor", claims, log=logged.append)
    assert columns["type"] == "org"
    assert columns["legs"] == ["activism"]        # JSON-list coerced, not dropped
    assert "disagree" in columns["contact_route"].lower()
    assert [c["field"] for c in other] == ["tag:ecosystem_role"]
    assert logged == []          # nothing rejected, nothing unrecognised


def test_split_claims_keeps_the_three_actor_fields_e6_added():
    """E4 found `worker.py:_COLUMNS["actor"]` missing `one_line`, `funding`
    and `scale_metric` though the `actor` table has all three and
    `questions.yaml` asks for each — so those claims were extracted, logged
    and dropped. E6 added the names. This is the same test inverted: it now
    asserts they reach `columns`, so a future edit that drops one from
    `_COLUMNS` fails here instead of silently losing the claim again."""
    from worker.worker import _split_claims
    claims, _ = extract.claims_from_findings([
        A("q1_one_line", "A gig-worker union", "s-a"),
        A("q10_funding", "Member dues", "s-a"),
        A("q11_scale_metric", "12 lakh members", "s-a"),
    ])
    columns, other = _split_claims("actor", claims, log=lambda *_: None)
    assert sorted(columns) == ["funding", "one_line", "scale_metric"]
    assert other == []


def test_ledger_and_claims_are_derived_from_the_same_answers(conn):
    """§9's ordering: every answer is written to `finding` BEFORE claims are
    resolved, and the claims are derived from those same answers."""
    answers = [A("q11_scale_metric", "12 lakh", "s-a", 0.8),
               A("q11_scale_metric", "9 lakh", "s-b", 0.6)]
    assert extract.write_findings(conn, 1, answers) == 2
    claims, _ = extract.claims_from_findings(answers)
    assert len(claims) == 1
    # The ledger keeps both sides individually; the claim states the conflict.
    ledger = [r["answer"] for r in conn.execute(
        "SELECT answer FROM finding ORDER BY id")]
    assert ledger == ["12 lakh", "9 lakh"]
