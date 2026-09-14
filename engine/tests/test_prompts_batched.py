"""Track E2 — the batched extraction prompt + parser promoted from PoC-2
(`poc/poc2-results.md`, `poc/poc2_extract.py`) into `worker/prompts.py`.

No network, no LLM call. Recorded-response tests replay real model output
from `poc/poc2-responses/` against fixture-derived `PromptSource` lists
built from `poc/fixtures/`. `selco-foundation` and `bhavreen-kandhari` were
excluded here as "captured zero sources"; that turned out to be a
`worker/fetch.py` cache bug rather than a fact about those actors, and both
now carry four sources (`poc/poc2-results.md`, addendum 2026-09-14). The
recorded responses still only exist for the original three, so the replay
tests below are unchanged.

The recorded response files predate `_response_envelope` and carry only
`raw`/`json`/`parse_error` — no saved prompt or label map — so the exact
`Sn -> source_id` order the model actually saw isn't recoverable. Each test
below builds a `PromptSource` list sized to the fixture's own source count,
labelled `S1..Sn` in fixture order, which is enough to resolve every label
the recorded response actually cites (checked per-file below) and exercises
the real parser against real model JSON rather than invented JSON.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from worker.extract_types import Answer, PromptSource
from worker.prompts import extract_prompt_batched, parse_answers, retry_per_source
from worker.questions import REGISTRY

POC = pathlib.Path(__file__).resolve().parents[1] / "poc"
FIXTURES = POC / "fixtures"
RESPONSES = POC / "poc2-responses"

USABLE_SLUGS = ("anthill-ventures", "bku-ekta-ugrahan", "jyoti-pande-lavakare")


def _fixture_sources(slug: str) -> list[PromptSource]:
    payload = json.loads((FIXTURES / f"{slug}.json").read_text())
    sources = payload["sources"]
    return [
        PromptSource(source_id=s["source_id"], label=f"S{i}",
                     url=s.get("url", ""), text=s["text"],
                     chunk_refs=(f"{s['source_id']}:0",))
        for i, s in enumerate(sources, start=1)
    ]


def _recorded_responses(slug: str) -> list[tuple[str, dict]]:
    out = []
    for path in sorted(RESPONSES.glob(f"{slug}__*.json")):
        if path.name.endswith("__retry.json"):
            continue
        payload = json.loads(path.read_text())
        out.append((path.name, payload))
    return out


# ── extract_prompt_batched — pure string building ────────────────────────

def test_rejects_bad_kind():
    with pytest.raises(ValueError):
        extract_prompt_batched("bogus", "Some Org", [])


def test_renders_given_labels_and_urls_in_order():
    sources = [
        PromptSource(source_id="durable-1", label="S1", url="https://a.example",
                     text="alpha passage", chunk_refs=("durable-1:0",)),
        PromptSource(source_id="durable-2", label="S2", url="https://b.example",
                     text="beta passage", chunk_refs=("durable-2:0",)),
    ]
    system, prompt = extract_prompt_batched("actor", "Anthill Ventures", sources)
    assert "Entity name: Anthill Ventures" in prompt
    assert "[S1] https://a.example\nalpha passage" in prompt
    assert "[S2] https://b.example\nbeta passage" in prompt
    # source order preserved, not resorted
    assert prompt.index("[S1]") < prompt.index("[S2]")


def test_batched_system_prompt_carries_the_batching_rules_and_questions():
    system, _ = extract_prompt_batched("actor", "X", [])
    assert "DROPPED" in system
    assert "never guess an id" in system
    assert "naming both sides and both source ids" in system  # the known defect
    for q in REGISTRY.all("actor"):
        assert q.id in system


def test_extract_prompt_unaffected():
    """`extract_prompt()` (the per-source, non-batched call) is untouched by
    this task — a later task decides the switchover."""
    from worker.prompts import extract_prompt
    system, prompt = extract_prompt("actor", "X", "some text")
    assert "SEVERAL SOURCES ARE GIVEN AT ONCE" not in system
    assert "some text" in prompt


# ── parse_answers — recorded PoC-2 responses ─────────────────────────────

@pytest.mark.parametrize("slug", USABLE_SLUGS)
def test_recorded_responses_round_trip_cleanly(slug):
    sources = _fixture_sources(slug)
    valid_labels = {s.label for s in sources}
    recorded = _recorded_responses(slug)
    assert recorded, f"expected at least one recorded response for {slug}"

    for name, payload in recorded:
        assert payload["json"] is not None, f"{name}: fixture presumed parsed"
        cited = {a.get("source_id") for a in payload["json"]["answers"]}
        assert cited <= valid_labels, (
            f"{name}: cites {cited - valid_labels}, outside the fixture's "
            f"{sorted(valid_labels)} — test's source list needs widening")

        answers, problems = parse_answers(payload["json"], sources)
        assert problems == [], f"{name}: unexpected drops: {problems}"
        assert len(answers) == len(payload["json"]["answers"])
        for a in answers:
            assert isinstance(a, Answer)
            assert a.source_id in {s.source_id for s in sources}


def test_drops_answer_with_no_source_id():
    sources = _fixture_sources("anthill-ventures")
    result = {"answers": [
        {"question_id": "q1_type", "answer": "org", "confidence": 0.9},
    ]}
    answers, problems = parse_answers(result, sources)
    assert answers == []
    assert len(problems) == 1
    assert "no source_id" in problems[0]


def test_drops_answer_with_unknown_source_id():
    """§8's mandatory guard: PoC-2 measured 0/95 unknown ids, but an id
    outside the map must still be dropped, never guessed."""
    sources = _fixture_sources("anthill-ventures")
    result = {"answers": [
        {"question_id": "q1_type", "source_id": "S9", "answer": "org",
         "confidence": 0.9},
    ]}
    answers, problems = parse_answers(result, sources)
    assert answers == []
    assert len(problems) == 1
    assert "unknown source_id" in problems[0]


def test_drops_non_dict_answer_and_missing_question_id():
    sources = _fixture_sources("anthill-ventures")
    result = {"answers": [
        "not an object",
        {"source_id": "S1", "answer": "x"},
    ]}
    answers, problems = parse_answers(result, sources)
    assert answers == []
    assert len(problems) == 2


def test_non_numeric_confidence_is_ignored_not_dropped():
    sources = _fixture_sources("anthill-ventures")
    result = {"answers": [
        {"question_id": "q1_type", "source_id": "S1", "answer": "org",
         "confidence": "high"},
    ]}
    answers, problems = parse_answers(result, sources)
    assert len(answers) == 1
    assert answers[0].confidence is None
    assert any("non-numeric confidence" in p for p in problems)


def test_result_not_a_dict():
    sources = _fixture_sources("anthill-ventures")
    answers, problems = parse_answers(None, sources)
    assert answers == []
    assert "not a JSON object" in problems[0]


def test_answers_key_missing_or_wrong_type():
    sources = _fixture_sources("anthill-ventures")
    answers, problems = parse_answers({"claims": []}, sources)
    assert answers == []
    assert "'answers' is missing or not a list" in problems[0]


def test_chunk_ref_narrowed_only_for_single_chunk_source():
    single = PromptSource(source_id="d1", label="S1", url="u",
                          text="t", chunk_refs=("d1:0",))
    multi = PromptSource(source_id="d2", label="S2", url="u",
                         text="t", chunk_refs=("d2:0", "d2:1"))
    result = {"answers": [
        {"question_id": "q1_type", "source_id": "S1", "answer": "a"},
        {"question_id": "q2_legs", "source_id": "S2", "answer": "b"},
    ]}
    answers, problems = parse_answers(result, [single, multi])
    assert problems == []
    by_qid = {a.question_id: a for a in answers}
    assert by_qid["q1_type"].chunk_ref == "d1:0"
    assert by_qid["q2_legs"].chunk_ref is None


# ── retry_per_source — §13's per-source fallback ─────────────────────────

def test_retry_per_source_builds_one_singleton_call_per_source():
    sources = _fixture_sources("bku-ekta-ugrahan")
    retries = retry_per_source("actor", "BKU Ekta Ugrahan", sources)
    assert len(retries) == len(sources)
    for original, (src, system, prompt) in zip(sources, retries):
        assert src is original
        assert "[S1]" in prompt
        assert original.url in prompt
        assert original.text in prompt
        # relabelled to S1 alone regardless of its label in the failed batch
        assert f"[{original.label}]" not in prompt or original.label == "S1"


def test_retry_per_source_prompt_matches_solo_batched_call():
    sources = _fixture_sources("jyoti-pande-lavakare")
    target = sources[2]  # label S3 in the original batch
    assert target.label == "S3"
    [(src, system, prompt)] = retry_per_source("actor", "Jyoti Pande Lavakare",
                                                [target])
    expected_system, expected_prompt = extract_prompt_batched(
        "actor", "Jyoti Pande Lavakare",
        [PromptSource(source_id=target.source_id, label="S1", url=target.url,
                      text=target.text, chunk_refs=target.chunk_refs)])
    assert system == expected_system
    assert prompt == expected_prompt


def test_retry_per_source_empty_list():
    assert retry_per_source("actor", "X", []) == []


# ------------------------------------------------- the verify-and-extract --
# `prompts.verify_and_extract_prompt_batched` + `parse_verified_answers`, the
# pass that handles the gate-2 `uncertain` bucket. The prompt instructs the
# model to give a verdict per source and extract only from sources it marked
# `about`; the parser does not trust that instruction. These tests are about
# the not-trusting.

from worker.prompts import (V_ABOUT, V_DIFFERENT, V_INSUFFICIENT,  # noqa: E402
                            V_UNRELATED, parse_verified_answers,
                            verify_and_extract_prompt_batched)


def _srcs(n=3):
    return [PromptSource(source_id=f"src{i}", label=f"S{i}",
                         url=f"https://e{i}.test/", text=f"body {i}",
                         chunk_refs=(f"src{i}:0",))
            for i in range(1, n + 1)]


def test_verify_prompt_carries_context_and_names_every_source():
    sources = _srcs(2)
    system, prompt = verify_and_extract_prompt_batched(
        "actor", "Jyoti Pande Lavakare",
        "Co-founder of Care for Air; writes on Delhi air pollution.", sources)
    assert "UNVERIFIED" in system
    assert "name match is NOT sufficient" in system
    # the context is what separates a name collision from the real entity
    assert "Care for Air" in prompt
    assert "Entity description:" in prompt
    for s in sources:
        assert f"[{s.label}] {s.url}" in prompt


def test_verify_prompt_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        verify_and_extract_prompt_batched("neither", "X", "ctx", _srcs(1))


def test_answers_from_a_source_marked_different_are_dropped():
    """The case the pass exists for: a water heater manufacturer sharing the
    entity's given name. The model correctly calls it `different` — and must
    not then answer from it."""
    sources = _srcs(2)
    body = {
        "verdicts": [
            {"source_id": "S1", "verdict": V_ABOUT, "why": "her own bio"},
            {"source_id": "S2", "verdict": V_DIFFERENT,
             "about_what": "a company manufacturing water heaters"},
        ],
        "answers": [
            {"question_id": "q10_funding", "source_id": "S1", "answer": "grants"},
            {"question_id": "q11_scale_metric", "source_id": "S2",
             "answer": "revenue of 40 crore"},
        ],
    }
    answers, verdicts, problems = parse_verified_answers(body, sources)
    assert [a.question_id for a in answers] == ["q10_funding"]
    assert verdicts["src2"]["verdict"] == V_DIFFERENT
    assert any("contradicted its own verdict" in p for p in problems)


def test_a_source_with_no_verdict_cannot_contribute():
    """Silence is not consent — the whole bucket is here because an automated
    check could not confirm it."""
    sources = _srcs(2)
    body = {
        "verdicts": [{"source_id": "S1", "verdict": V_ABOUT}],
        "answers": [
            {"question_id": "q1", "source_id": "S1", "answer": "kept"},
            {"question_id": "q2", "source_id": "S2", "answer": "dropped"},
        ],
    }
    answers, _, problems = parse_verified_answers(body, sources)
    assert [a.question_id for a in answers] == ["q1"]
    assert any("no verdict returned for ['S2']" in p for p in problems)


def test_missing_verdicts_block_everything():
    """A model that skips step 1 entirely must extract nothing, not
    everything."""
    sources = _srcs(2)
    body = {"answers": [{"question_id": "q1", "source_id": "S1", "answer": "x"}]}
    answers, verdicts, problems = parse_verified_answers(body, sources)
    assert answers == []
    assert verdicts == {}
    assert any("'verdicts' is missing" in p for p in problems)


def test_unknown_verdict_value_is_treated_as_not_about():
    sources = _srcs(1)
    body = {
        "verdicts": [{"source_id": "S1", "verdict": "probably yes"}],
        "answers": [{"question_id": "q1", "source_id": "S1", "answer": "x"}],
    }
    answers, verdicts, problems = parse_verified_answers(body, sources)
    assert answers == []
    assert verdicts["src1"]["verdict"] == V_INSUFFICIENT
    assert any("unknown verdict" in p for p in problems)


def test_rejection_without_about_what_is_flagged_but_kept():
    """`about_what` is how a reviewer checks the model's reasoning without
    refetching. Its absence does not overturn the verdict — it is recorded as
    unreviewable."""
    sources = _srcs(1)
    body = {"verdicts": [{"source_id": "S1", "verdict": V_UNRELATED}],
            "answers": []}
    _, verdicts, problems = parse_verified_answers(body, sources)
    assert verdicts["src1"]["verdict"] == V_UNRELATED
    assert any("unreviewable" in p for p in problems)


def test_all_sources_rejected_is_a_clean_empty_result():
    sources = _srcs(2)
    body = {"verdicts": [
        {"source_id": "S1", "verdict": V_UNRELATED, "about_what": "a help page"},
        {"source_id": "S2", "verdict": V_DIFFERENT, "about_what": "another firm"},
    ], "answers": []}
    answers, verdicts, problems = parse_verified_answers(body, sources)
    assert answers == []
    assert len(verdicts) == 2
    assert not any("contradicted" in p for p in problems)


def test_unknown_source_id_in_a_verdict_is_never_guessed():
    sources = _srcs(1)
    body = {"verdicts": [{"source_id": "S9", "verdict": V_ABOUT}], "answers": []}
    _, verdicts, problems = parse_verified_answers(body, sources)
    assert verdicts == {}
    assert any("unknown source_id" in p for p in problems)
