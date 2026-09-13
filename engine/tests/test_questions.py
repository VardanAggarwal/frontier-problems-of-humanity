"""F1 — the question registry (`04-worker-build-plan.md` §1a / §4 contract 2).
Offline, no network, no model, no database — `worker/questions.py` is pure
YAML parsing plus validation."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import textwrap

import pytest

from worker import questions as qmod


def test_default_registry_loads():
    r = qmod.load()
    assert len(r.questions) == 36


def test_counts_match_02_questions_md():
    r = qmod.load()
    assert len(r.all("problem")) == 19
    assert len(r.all("actor")) == 17


def test_ids_unique():
    r = qmod.load()
    ids = [q.id for q in r.questions]
    assert len(ids) == len(set(ids))


def test_every_retrieval_question_has_a_valid_bucket():
    r = qmod.load()
    bucket_ids = {b.id for b in r.buckets}
    for q in r.retrieval_questions():
        assert q.bucket is not None, f"{q.id}: retrieval=true with no bucket"
        assert q.bucket in bucket_ids, f"{q.id}: bucket {q.bucket!r} doesn't exist"


def test_every_bucket_has_at_least_one_question():
    r = qmod.load()
    for b in r.buckets:
        assert len(b.questions) >= 1, f"bucket {b.id!r} is empty"


def test_non_retrieval_questions():
    """Two distinct reasons a question drives no retrieval, and both live
    behind the same `retrieval: false` flag.

    Five are PoC-1c's whole-record inferences — q2 type, q3 legs,
    q5 ecosystem_role, q7 representation_unit, q13 failure_note — enum
    judgments with no localized passage to find.

    One is q10b_funder_identity, which is different in kind: the fact is
    localized, but it is a *relation* rather than a property, so it arrives
    as an edge through the emit path instead of by retrieving a sentence.
    Keep the two reasons distinguishable; a future change that revives
    retrieval for one class must not silently revive it for the other.
    """
    r = qmod.load()
    non_retrieval = {q.id for q in r.questions if not q.retrieval}
    assert non_retrieval == {
        "q2_type", "q3_legs", "q5_ecosystem_role",
        "q7_representation_unit", "q13_failure_note",
        "q10b_funder_identity",
    }
    for qid in non_retrieval:
        q = r.get(qid)
        assert q.bucket is None
        assert q.retrieval_note, f"{qid}: retrieval=false with no retrieval_note"


def test_accessors():
    r = qmod.load()
    q = r.get("q9_contact_route")
    assert q.kind == "actor"
    assert q.claim_field == "contact_route"
    b = r.bucket_for("q9_contact_route")
    assert b.id == "actor-reach"
    assert "q9_contact_route" in b.questions
    assert "q16_channel" in b.questions
    in_bucket_ids = {qq.id for qq in r.in_bucket("actor-reach")}
    assert in_bucket_ids == {"q9_contact_route", "q16_channel"}


def test_lookup_unknown_question_raises():
    r = qmod.load()
    with pytest.raises(KeyError):
        r.get("no_such_question")


# ------------------------------------------------- validation failures ----
def _write(tmp_path, yaml_text):
    p = tmp_path / "bad.yaml"
    p.write_text(textwrap.dedent(yaml_text))
    return p


def test_duplicate_id_rejected(tmp_path):
    p = _write(tmp_path, """\
        questions:
          - id: q1_one_line
            kind: actor
            question: "a"
            claim_field: one_line
            multi: false
            retrieval: false
          - id: q1_one_line
            kind: actor
            question: "b"
            claim_field: one_line
            multi: false
            retrieval: false
        buckets: []
        """)
    with pytest.raises(qmod.QuestionRegistryError, match="duplicate question id"):
        qmod.load(p)


def test_unknown_bucket_reference_rejected(tmp_path):
    p = _write(tmp_path, """\
        questions:
          - id: q1_one_line
            kind: actor
            question: "a"
            claim_field: one_line
            multi: false
            retrieval: true
            bucket: ghost-bucket
        buckets:
          - id: real-bucket
            kind: actor
            questions: [q1_one_line]
        """)
    with pytest.raises(qmod.QuestionRegistryError, match="unknown bucket"):
        qmod.load(p)


def test_retrieval_true_with_no_bucket_rejected(tmp_path):
    p = _write(tmp_path, """\
        questions:
          - id: q1_one_line
            kind: actor
            question: "a"
            claim_field: one_line
            multi: false
            retrieval: true
        buckets: []
        """)
    with pytest.raises(qmod.QuestionRegistryError, match="no bucket"):
        qmod.load(p)


def test_bucket_with_no_questions_rejected(tmp_path):
    p = _write(tmp_path, """\
        questions:
          - id: q1_one_line
            kind: actor
            question: "a"
            claim_field: one_line
            multi: false
            retrieval: false
        buckets:
          - id: empty-bucket
            kind: actor
            questions: []
        """)
    with pytest.raises(qmod.QuestionRegistryError, match="no questions"):
        qmod.load(p)


def test_unknown_tag_namespace_rejected(tmp_path):
    p = _write(tmp_path, """\
        questions:
          - id: p99_bogus
            kind: problem
            question: "a"
            claim_field: "tag:not_a_real_namespace"
            multi: false
            retrieval: false
        buckets: []
        """)
    with pytest.raises(qmod.QuestionRegistryError, match="not_a_real_namespace"):
        qmod.load(p)


def test_duplicate_bucket_id_rejected(tmp_path):
    p = _write(tmp_path, """\
        questions:
          - id: q1_one_line
            kind: actor
            question: "a"
            claim_field: one_line
            multi: false
            retrieval: true
            bucket: b1
        buckets:
          - id: b1
            kind: actor
            questions: [q1_one_line]
          - id: b1
            kind: actor
            questions: [q1_one_line]
        """)
    with pytest.raises(qmod.QuestionRegistryError, match="duplicate bucket id"):
        qmod.load(p)
