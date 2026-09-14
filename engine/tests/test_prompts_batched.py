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
from worker import prompts
from worker.prompts import (
    extract_prompt_batched, parse_answers, retry_per_source)
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


# ------------------------------------------------ rule 4: misidentified ----
# The main extraction prompt's own escape hatch. Its sources cleared gate 2,
# but the band sweep found false positives above CONFIRMED_ABOVE, and the
# model is reading the whole page while gate 2 read 500 characters of it.

from worker.prompts import drop_misidentified, parse_misidentified  # noqa: E402


def test_prompt_asks_for_misidentified_and_shows_it_in_the_schema():
    system, _ = extract_prompt_batched("actor", "Jyoti Pande Lavakare", _srcs(2))
    assert "misidentified" in system
    assert "shares the name" in system
    assert '"about_what"' in system


def test_absent_key_is_no_objection_not_no_verdict():
    """Asymmetric with the verify pass on purpose: here the sources cleared
    gate 2, so silence means the model had nothing to say."""
    flagged, problems = parse_misidentified({"answers": []}, _srcs(2))
    assert flagged == {}
    assert problems == []


def test_flagged_source_loses_its_answers():
    sources = _srcs(2)
    body = {
        "answers": [
            {"question_id": "q1", "source_id": "S1", "answer": "kept"},
            {"question_id": "q10_funding", "source_id": "S2",
             "answer": "revenue of 40 crore"},
        ],
        "misidentified": [
            {"source_id": "S2", "about_what": "a water heater manufacturer",
             "why": "the page sells appliances"},
        ],
    }
    answers, _ = parse_answers(body, sources)
    flagged, _ = parse_misidentified(body, sources)
    kept, dropped = drop_misidentified(answers, flagged)
    assert [a.question_id for a in kept] == ["q1"]
    assert any("water heater manufacturer" in d for d in dropped)


def test_flag_without_about_what_is_kept_but_noted():
    sources = _srcs(1)
    flagged, problems = parse_misidentified(
        {"misidentified": [{"source_id": "S1"}]}, sources)
    assert "src1" in flagged
    assert any("unreviewable" in p for p in problems)


def test_unknown_source_id_in_a_flag_is_never_guessed():
    flagged, problems = parse_misidentified(
        {"misidentified": [{"source_id": "S9", "about_what": "x"}]}, _srcs(1))
    assert flagged == {}
    assert any("unknown source_id" in p for p in problems)


def test_misidentified_not_a_list_is_ignored_loudly():
    flagged, problems = parse_misidentified(
        {"misidentified": "S2 is wrong"}, _srcs(2))
    assert flagged == {}
    assert any("not a list" in p for p in problems)


def test_drop_misidentified_is_a_no_op_with_no_flags():
    sources = _srcs(1)
    answers, _ = parse_answers(
        {"answers": [{"question_id": "q1", "source_id": "S1", "answer": "x"}]},
        sources)
    kept, dropped = drop_misidentified(answers, {})
    assert kept == answers and dropped == []


# ------------------------------------- rule 5: per-chunk markers (2026-09-14)

def _src(label="S1", refs=("src:0", "src:1", "src:2"),
         texts=("alpha text", "bravo text", "charlie text")):
    return PromptSource(source_id="src", label=label, url="https://x/",
                        text="\n\n".join(texts), chunk_refs=refs,
                        chunk_texts=texts)


def test_block_marks_every_chunk_inside_it():
    system, prompt = prompts.extract_prompt_batched("actor", "X", [_src()])
    assert "⟨S1.1⟩ alpha text" in prompt
    assert "⟨S1.2⟩ bravo text" in prompt
    assert "⟨S1.3⟩ charlie text" in prompt
    assert prompt.count("[S1] https://x/") == 1   # still ONE block per source


def test_block_without_chunk_texts_renders_unmarked():
    """`retry_per_source` and any caller holding only joined text still
    work — the marker is an aid, not a precondition."""
    bare = PromptSource("src", "S1", "https://x/", "joined body", ("src:0",))
    _, prompt = prompts.extract_prompt_batched("actor", "X", [bare])
    assert "joined body" in prompt and "⟨" not in prompt


def test_answer_chunk_marker_resolves_to_the_durable_chunk_ref():
    answers, problems = prompts.parse_answers(
        {"answers": [{"question_id": "q1_one_line", "source_id": "S1",
                      "chunk": "S1.3", "answer": "a"}]}, [_src()])
    assert problems == []
    assert answers[0].chunk_ref == "src:2"     # 1-based marker, 0-based tuple


def test_chunk_marker_naming_another_source_is_refused_not_trusted():
    """That combination means the model lost track of which block it was
    reading — the exact condition chunk_ref exists to let a reviewer see."""
    answers, problems = prompts.parse_answers(
        {"answers": [{"question_id": "q1_one_line", "source_id": "S1",
                      "chunk": "S4.1", "answer": "a"}]}, [_src()])
    assert answers[0].chunk_ref is None
    assert any("names S4" in p for p in problems)


def test_out_of_range_and_unparseable_markers_leave_chunk_ref_null():
    for bad in ("S1.9", "third one", "S1.0"):
        answers, problems = prompts.parse_answers(
            {"answers": [{"question_id": "q1_one_line", "source_id": "S1",
                          "chunk": bad, "answer": "a"}]}, [_src()])
        assert answers and answers[0].chunk_ref is None, bad
        assert problems, bad


def test_absent_marker_is_not_a_problem_and_keeps_the_one_chunk_fallback():
    one = PromptSource("src", "S1", "u", "only", ("src:7",), ("only",))
    answers, problems = prompts.parse_answers(
        {"answers": [{"question_id": "q1_one_line", "source_id": "S1",
                      "answer": "a"}]}, [one])
    assert problems == [] and answers[0].chunk_ref == "src:7"

    answers, problems = prompts.parse_answers(
        {"answers": [{"question_id": "q1_one_line", "source_id": "S1",
                      "answer": "a"}]}, [_src()])
    assert problems == [] and answers[0].chunk_ref is None


# ------------------------------------ claims left the batched schema --------

def test_batched_schema_does_not_ask_for_claims_and_asks_once():
    system, _ = prompts.extract_prompt_batched("actor", "X", [_src()])
    assert '"claims"' not in system
    assert system.count("Respond with strict JSON") == 1


def test_single_source_prompt_still_asks_for_claims():
    """That path has no findings ledger to derive claims from."""
    system, _ = prompts.extract_prompt("actor", "X", "body")
    assert '"claims"' in system


# ------------------------------------------------ signals on problem emits --

def test_batched_schema_asks_for_the_four_gate_signals_on_the_edge():
    """On the `works_on` EDGE, not the emit: PoC-2d measured 31 emits across
    ten calls, every one `actor`, against 23 problems named as `works_on`
    destinations. Asking on the emit asks somewhere the model never goes."""
    system, _ = prompts.extract_prompt_batched("actor", "X", [_src()])
    for key in ("harmed_population", "magnitude", "agent", "actionable"):
        assert key in system
    assert "uncounted" in system      # a real value, not a null
    assert "`works_on` edge whose `dst_kind` is `problem`" in system

    emits_line = next(l for l in system.splitlines() if '"emits"' in l)
    edges_line = next(l for l in system.splitlines() if '"edges"' in l)
    assert "signals" not in emits_line
    assert "signals" in edges_line


# ------------------------ list-valued answers (PoC-2d, 2026-09-14) ----------

def test_list_answer_is_serialised_not_dropped():
    """`_ACTOR_SYSTEM` calls these fields "a JSON list from …" while the
    answers schema shows a string, so the model is entitled to either. Three
    of one PoC-2d call's eleven answers arrived as lists and were discarded
    as "missing/empty answer text", which they were not."""
    answers, problems = prompts.parse_answers(
        {"answers": [{"question_id": "q3_legs", "source_id": "S1",
                      "answer": ["enterprise", "service"]}]}, [_src()])
    assert len(answers) == 1
    assert answers[0].answer == '["enterprise", "service"]'
    assert any("serialised" in p for p in problems)


def test_serialised_list_round_trips_to_a_real_list_for_json_columns():
    """The serialisation is chosen so `worker._coerce_json_list` parses it
    back out — the parser cannot import `worker` to learn which columns are
    list-valued, so the shape has to survive the trip on its own."""
    from worker.worker import _coerce_json_list
    answers, _ = prompts.parse_answers(
        {"answers": [{"question_id": "q3_legs", "source_id": "S1",
                      "answer": ["enterprise", "service"]}]}, [_src()])
    assert _coerce_json_list(answers[0].answer) == ["enterprise", "service"]


def test_empty_list_answer_is_still_dropped():
    answers, problems = prompts.parse_answers(
        {"answers": [{"question_id": "q3_legs", "source_id": "S1",
                      "answer": []}]}, [_src()])
    assert answers == [] and any("empty list" in p for p in problems)


def test_non_text_answer_reports_its_actual_type():
    """The old message said "missing/empty", which is what sent a real
    defect undiagnosed."""
    _, problems = prompts.parse_answers(
        {"answers": [{"question_id": "q3_legs", "source_id": "S1",
                      "answer": 42}]}, [_src()])
    assert any("is int, not text" in p for p in problems)


def test_batched_schema_states_the_dst_kind_enum():
    """Splitting `_EXTRACT_COMMON` removed the batched prompt's only
    statement of the allowed values, and PoC-2d measured the cost: 3 of 28
    live-arm edges used `org`/`individual` against 0 of 22 in the control."""
    system, _ = prompts.extract_prompt_batched("actor", "X", [_src()])
    edges_line = next(l for l in system.splitlines() if '"edges"' in l)
    assert '"dst_kind": "problem"|"actor"' in edges_line
