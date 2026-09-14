"""Track E2 — the batched extraction prompt + parser promoted from PoC-2
(`poc/poc2-results.md`, `poc/poc2_extract.py`) into `worker/prompts.py`.

No network, no LLM call. Recorded-response tests replay real model output
from `poc/poc2-responses/` against fixture-derived `PromptSource` lists
built from `poc/fixtures/` — only `anthill-ventures` (2 sources),
`bku-ekta-ugrahan` (4) and `jyoti-pande-lavakare` (4) are usable;
`selco-foundation` and `bhavreen-kandhari` captured zero sources at fixture
time and are not used here (`poc/poc2-results.md` "Open gaps" §1).

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
