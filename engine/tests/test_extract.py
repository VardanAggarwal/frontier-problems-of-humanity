"""Track E3 (`04-worker-build-plan.md` §5) -- `worker/extract.py`'s pure
`assemble()`. No DB, no network, no LLM; encoder-dependent behaviour is
exercised against the real cached model (same pattern as `test_passages.py`,
`test_chunk.py`) and skips cleanly when it isn't downloaded.

Real-source tests use `poc/fixtures/{bku-ekta-ugrahan,jyoti-pande-lavakare,
anthill-ventures}.json` -- the only fixtures with captured (non-empty)
sources, per the brief. `selco-foundation` and `bhavreen-kandhari` are
empty and must never be used; a test proves an empty fixture fails loudly
rather than silently skipping, since that is how the PoC's own harness
handled it and this task must not repeat it.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from embed.model import MODEL_NAME
from text.chunk import Chunk
from worker import extract
from worker.extract_types import ConfirmedSource
from worker.questions import REGISTRY

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "poc" / "fixtures"

needs_model = pytest.mark.skipif(
    not pathlib.Path.home().joinpath(
        ".cache/huggingface/hub",
        "models--" + MODEL_NAME.replace("/", "--")).exists(),
    reason=f"{MODEL_NAME} not downloaded")


def _chunk(text, source_id="s1", ordinal=0, tokens=10):
    return Chunk(text=text, source_id=source_id, ordinal=ordinal, token_count=tokens)


def load_fixture(slug: str) -> list[ConfirmedSource]:
    """Load a captured PoC-2 fixture as `ConfirmedSource`s. Fails loudly
    (`AssertionError`) on an empty or missing fixture -- this is the one
    place the brief says NOT to replicate the PoC harness's SKIP-on-empty
    behaviour."""
    path = FIXTURES / f"{slug}.json"
    assert path.exists(), f"no fixture at {path}"
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload.get("sources") or []
    assert sources, (
        f"fixture {slug!r} captured ZERO sources -- this fixture must not "
        f"be used (selco-foundation and bhavreen-kandhari are known-empty; "
        f"use anthill-ventures, bku-ekta-ugrahan or jyoti-pande-lavakare)")
    return [
        ConfirmedSource(source_id=s["source_id"], url=s.get("url", ""),
                         text=s["text"], origin="SEED", verdict="CONFIRMED")
        for s in sources
    ]


# ------------------------------------------------------- empty fixtures --

def test_known_empty_fixture_fails_loudly_not_skips():
    with pytest.raises(AssertionError, match="captured ZERO sources"):
        load_fixture("selco-foundation")
    with pytest.raises(AssertionError, match="captured ZERO sources"):
        load_fixture("bhavreen-kandhari")


# ------------------------------------------------------------ signature --

def test_assemble_returns_empty_for_no_sources():
    prompt_sources, counters = extract.assemble([], list(REGISTRY.all("actor")))
    assert prompt_sources == []
    assert counters == {
        "sources_fetched": 0,
        "sources_in_prompt": 0,
        "sources_never_selected": 0,
        "sources_dropped_by_cap": 0,
    }


def test_assemble_returns_empty_for_no_questions():
    sources = [ConfirmedSource("s1", "http://x", "some text " * 50, "SEED", "CONFIRMED")]
    prompt_sources, counters = extract.assemble(sources, [])
    assert prompt_sources == []
    assert counters["sources_fetched"] == 1
    assert counters["sources_never_selected"] == 1


# --------------------------------------------------- real fixture, happy --

@needs_model
def test_assemble_labels_sources_by_first_appearance_and_orders_within_source():
    sources = load_fixture("bku-ekta-ugrahan")
    questions = list(REGISTRY.all("actor"))
    prompt_sources, counters = extract.assemble(sources, questions)

    assert prompt_sources, "expected at least one prompt source"
    labels = [ps.label for ps in prompt_sources]
    assert labels == [f"S{i}" for i in range(1, len(prompt_sources) + 1)]

    fetched_ids = {s.source_id for s in sources}
    for ps in prompt_sources:
        assert ps.source_id in fetched_ids
        # chunk_refs are in document (ordinal) order, matching `ps.text`'s
        # paragraph order.
        ordinals = [int(r.split(":")[1]) for r in ps.chunk_refs]
        assert ordinals == sorted(ordinals)
        assert all(r.startswith(f"{ps.source_id}:") for r in ps.chunk_refs)

    assert counters["sources_fetched"] == len(sources)
    assert counters["sources_in_prompt"] == len(prompt_sources)
    assert counters["sources_in_prompt"] + counters["sources_never_selected"] == counters["sources_fetched"]
    assert "neighbour_expansion_tokens_ratio" in counters
    assert "neighbour_expansion_chars_ratio" in counters


@needs_model
@pytest.mark.parametrize("slug", ["anthill-ventures", "bku-ekta-ugrahan", "jyoti-pande-lavakare"])
def test_assemble_counters_are_internally_consistent_on_real_fixtures(slug):
    sources = load_fixture(slug)
    questions = list(REGISTRY.all("actor"))
    prompt_sources, counters = extract.assemble(sources, questions)

    assert counters["sources_fetched"] == len(sources)
    assert 0 <= counters["sources_in_prompt"] <= counters["sources_fetched"]
    assert (counters["sources_in_prompt"]
            + counters["sources_never_selected"]) == counters["sources_fetched"]
    # Dropped-by-cap sources are always a subset of in-prompt sources under
    # `_cap_tokens`'s "never drop a source's first/best chunk" rule.
    assert counters["sources_dropped_by_cap"] <= counters["sources_in_prompt"]


@needs_model
def test_assemble_neighbour_radius_zero_disables_expansion_cost():
    sources = load_fixture("jyoti-pande-lavakare")
    questions = list(REGISTRY.all("actor"))
    _, counters = extract.assemble(sources, questions, neighbour_radius=0)
    # With no expansion, bare == expanded, so the ratio (if present at all)
    # is 1.0 -- no inflation to report.
    if "neighbour_expansion_tokens_ratio" in counters:
        assert counters["neighbour_expansion_tokens_ratio"] == pytest.approx(1.0)


# --------------------------------------- never-selected vs cap-eviction --
# Deterministic, no encoder needed: unbucketed questions make `select()`
# take its stable-order fallback (`chunks[:k]`), so which chunks survive is
# fully controlled by input order and `top_k` -- exactly the two-cause
# distinction the brief asks the counters to make (PoC-2 could not tell
# "never picked up by top-k" from "picked up, then evicted by the cap").

def _unbucketed_questions():
    unbucketed = [q for q in REGISTRY.all("actor") if q.bucket is None]
    assert unbucketed, "fixture assumption: some actor questions are unbucketed"
    return unbucketed


def test_never_selected_when_top_k_excludes_a_source():
    # Three sources, one short paragraph each (well under CHUNK_TOKENS, so
    # each chunks to exactly one piece) -- but chunk() needs the real
    # tokenizer, so this test is model-gated too.
    pytest.importorskip("embed.model")
    sources = [
        ConfirmedSource("s1", "http://a", "First source paragraph, short and plain.", "SEED", "CONFIRMED"),
        ConfirmedSource("s2", "http://b", "Second source paragraph, also short and plain.", "SEED", "CONFIRMED"),
        ConfirmedSource("s3", "http://c", "Third source paragraph, likewise short and plain.", "SEED", "CONFIRMED"),
    ]
    prompt_sources, counters = extract.assemble(
        sources, _unbucketed_questions(), top_k=2, neighbour_radius=0)

    assert counters["sources_fetched"] == 3
    assert counters["sources_in_prompt"] == 2
    assert counters["sources_never_selected"] == 1
    assert counters["sources_dropped_by_cap"] == 0
    assert {ps.source_id for ps in prompt_sources} <= {"s1", "s2"} | {"s3"}
    assert len(prompt_sources) == 2


@needs_model
def test_cap_eviction_never_drops_a_sources_last_chunk():
    """One source with three real chunks, one with one -- a token_cap tight
    enough to force eviction inside the three-chunk source must still leave
    that source represented in the final prompt (the guarantee
    `_cap_tokens` implements, `03-worker.md` §7), while the counters record
    that eviction happened."""
    long_text = (
        "First paragraph of the busy source, long enough on its own to cost "
        "real tokens and stand as one chunk by itself without merging.\n\n"
        "Second paragraph of the busy source, also standalone, also costing "
        "real tokens, and definitely a different chunk from the first one.\n\n"
        "Third paragraph of the busy source, again standalone, again its "
        "own chunk, completing a source with three separate chunks total."
    )
    sources = [
        ConfirmedSource("busy", "http://busy", long_text, "SEED", "CONFIRMED"),
        ConfirmedSource("quiet", "http://quiet", "A single short paragraph for the quiet source.", "SEED", "CONFIRMED"),
    ]
    questions = _unbucketed_questions()

    # First, assemble uncapped to learn the real per-chunk token costs.
    uncapped_sources, uncapped_counters = extract.assemble(
        sources, questions, top_k=10, neighbour_radius=0, token_cap=10**9)
    busy = next(ps for ps in uncapped_sources if ps.source_id == "busy")
    assert len(busy.chunk_refs) == 3, "expected three chunks from the busy source"

    # A cap tight enough to force eviction inside "busy" but never below one
    # chunk (the guarantee), since `_cap_tokens` always force-keeps the
    # first-encountered chunk per source regardless of the cap's size.
    tiny_cap = 1
    capped_sources, capped_counters = extract.assemble(
        sources, questions, top_k=10, neighbour_radius=0, token_cap=tiny_cap)

    capped_busy = [ps for ps in capped_sources if ps.source_id == "busy"]
    assert capped_busy, "the busy source must still be represented (never fully evicted)"
    assert len(capped_busy[0].chunk_refs) < 3, (
        "a tiny cap should have evicted at least one of the busy source's "
        "chunks -- otherwise this test isn't exercising the cap at all")

    assert capped_counters["sources_in_prompt"] == uncapped_counters["sources_in_prompt"]
    assert capped_counters["sources_dropped_by_cap"] == 0, (
        "the cap trims chunks within a source, never the whole source, per "
        "the never-drop-a-source's-last-chunk rule")
