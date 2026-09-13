"""Track C (`04-worker-build-plan.md` §4) — `worker/passages.py`'s pure
`select()`. No DB, no network, no pipeline knowledge; encoder-dependent
tests skip cleanly when the model isn't cached (same pattern as
`test_embed.py`).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from embed.model import MODEL_NAME
from text.chunk import Chunk
from worker import passages
from worker.questions import REGISTRY

needs_model = pytest.mark.skipif(
    not pathlib.Path.home().joinpath(
        ".cache/huggingface/hub",
        "models--" + MODEL_NAME.replace("/", "--")).exists(),
    reason=f"{MODEL_NAME} not downloaded")


def _chunk(text, source_id="s1", ordinal=0, tokens=10):
    return Chunk(text=text, source_id=source_id, ordinal=ordinal, token_count=tokens)


def test_select_returns_empty_for_no_chunks():
    assert passages.select([], list(REGISTRY.all("actor")), 3) == []


def test_select_with_no_bucketed_questions_falls_back_to_first_k():
    chunks = [_chunk(f"chunk {i}", ordinal=i) for i in range(5)]
    unbucketed = [q for q in REGISTRY.all("actor") if q.bucket is None]
    assert unbucketed, "fixture assumption: some actor questions are unbucketed"
    out = passages.select(chunks, unbucketed, k=2)
    assert out == chunks[:2]


@needs_model
def test_select_picks_per_bucket_not_per_question():
    """actor-reach (q9_contact_route, q16_channel) shares one retrieval_query
    across two questions — selecting for both should not double the k."""
    reach_questions = list(REGISTRY.in_bucket("actor-reach"))
    assert len(reach_questions) == 2
    chunks = [
        _chunk("Email us at contact@example.org or find us on Instagram and Twitter.", ordinal=0),
        _chunk("The organisation was founded in 2019 by three former quarry workers.", ordinal=1),
        _chunk("Annual budget was reported at twelve lakh rupees for the last cycle.", ordinal=2),
    ]
    # neighbour_radius=0: this test is about how many chunks *retrieval*
    # returns, so it must not count the neighbours expansion adds after.
    out = passages.select(chunks, reach_questions, k=2, neighbour_radius=0)
    # Same bucket queried once, not once per question -> at most k=2 chunks
    # come back, not more just because two questions share the bucket.
    assert len(out) <= 2


@needs_model
def test_select_ranks_the_relevant_chunk_first():
    reach_questions = list(REGISTRY.in_bucket("actor-reach"))
    contact_chunk = _chunk(
        "Reach the association by email at contact@example.org, or via their "
        "WhatsApp broadcast channel and Instagram page.", source_id="s1", ordinal=0)
    unrelated_chunk = _chunk(
        "The scheme requires a certified diagnosis from a government hospital "
        "before any compensation claim can be filed.", source_id="s1", ordinal=1)
    # neighbour_radius=0 again, and here it is load-bearing rather than
    # tidy: the two chunks are neighbours, so with expansion on, both come
    # back in ordinal order and the assertion would hold whichever one
    # retrieval actually ranked first.
    out = passages.select([unrelated_chunk, contact_chunk], reach_questions, k=1,
                          neighbour_radius=0)
    assert out == [contact_chunk]


@needs_model
def test_select_dedupes_a_chunk_shared_across_two_buckets():
    # q1_one_line (actor-identity) and q9/q16 (actor-reach) are different
    # buckets; a chunk that scores well for both should appear once.
    identity_and_reach = list(REGISTRY.in_bucket("actor-identity")) + list(
        REGISTRY.in_bucket("actor-reach"))
    chunks = [_chunk(f"chunk {i}", ordinal=i) for i in range(4)]
    out = passages.select(chunks, identity_and_reach, k=3)
    refs = [c.chunk_ref for c in out]
    assert len(refs) == len(set(refs))


def test_cap_tokens_keeps_at_least_one_chunk_per_source():
    chunks = [
        _chunk("a", source_id="s1", ordinal=0, tokens=5000),
        _chunk("b", source_id="s2", ordinal=0, tokens=5000),
        _chunk("c", source_id="s2", ordinal=1, tokens=5000),
    ]
    out = passages._cap_tokens(chunks, cap=6000)
    sources = {c.source_id for c in out}
    assert sources == {"s1", "s2"}, "every source must keep at least one chunk"


def test_cap_tokens_no_op_under_budget():
    chunks = [_chunk("a", tokens=100), _chunk("b", ordinal=1, tokens=100)]
    assert passages._cap_tokens(chunks, cap=9000) == chunks


def test_cap_tokens_empty_input():
    assert passages._cap_tokens([], cap=9000) == []


# ── Neighbour expansion — PoC-1d's replacement for CHUNK_OVERLAP ──────────
# Pure, no encoder: these run everywhere, unlike the retrieval tests above.

def test_expand_neighbours_radius_zero_is_identity():
    chunks = [_chunk(f"c{i}", ordinal=i) for i in range(5)]
    assert passages.expand_neighbours(chunks[2:3], chunks, radius=0) == chunks[2:3]


def test_expand_neighbours_adds_both_sides():
    chunks = [_chunk(f"c{i}", ordinal=i) for i in range(5)]
    out = passages.expand_neighbours([chunks[2]], chunks, radius=1)
    assert [c.ordinal for c in out] == [1, 2, 3]


def test_expand_neighbours_stops_at_document_edges():
    chunks = [_chunk(f"c{i}", ordinal=i) for i in range(3)]
    assert [c.ordinal for c in passages.expand_neighbours([chunks[0]], chunks, radius=1)] == [0, 1]
    assert [c.ordinal for c in passages.expand_neighbours([chunks[2]], chunks, radius=1)] == [1, 2]


def test_expand_neighbours_never_crosses_a_source_boundary():
    """Ordinals are only contiguous within one source (`text/chunk.py`), so
    s2:0 is not s1:1's neighbour however the pool happens to be ordered."""
    s1 = [_chunk("a", source_id="s1", ordinal=i) for i in range(2)]
    s2 = [_chunk("b", source_id="s2", ordinal=i) for i in range(2)]
    out = passages.expand_neighbours([s1[1]], s1 + s2, radius=1)
    assert {c.chunk_ref for c in out} == {"s1:0", "s1:1"}


def test_expand_neighbours_keeps_a_group_contiguous():
    """The straddle repair only works if a chunk and the neighbour holding
    its sheared-off denominator end up adjacent in the prompt."""
    chunks = [_chunk(f"c{i}", source_id="s1", ordinal=i) for i in range(10)]
    selected = [chunks[7], chunks[2]]          # priority order, not document order
    out = passages.expand_neighbours(selected, chunks, radius=1)
    assert [c.chunk_ref for c in out] == ["s1:6", "s1:7", "s1:8", "s1:1", "s1:2", "s1:3"]


def test_expand_neighbours_does_not_demote_a_selected_chunk():
    """s1:3 is selected second in its own right; being s1:8's... nothing, but
    being s1:2's neighbour must not move it ahead of or behind its own slot."""
    chunks = [_chunk(f"c{i}", source_id="s1", ordinal=i) for i in range(6)]
    out = passages.expand_neighbours([chunks[2], chunks[3]], chunks, radius=1)
    refs = [c.chunk_ref for c in out]
    assert refs == ["s1:1", "s1:2", "s1:3", "s1:4"]
    assert len(refs) == len(set(refs)), "a shared neighbour appears once"


def test_expand_neighbours_radius_two():
    chunks = [_chunk(f"c{i}", ordinal=i) for i in range(9)]
    out = passages.expand_neighbours([chunks[4]], chunks, radius=2)
    assert [c.ordinal for c in out] == [2, 3, 4, 5, 6]


def test_expand_neighbours_empty_selection():
    chunks = [_chunk(f"c{i}", ordinal=i) for i in range(3)]
    assert passages.expand_neighbours([], chunks, radius=1) == []


def test_expansion_is_capped_afterwards_not_before():
    """Order of operations (module docstring): the cap must see the expanded
    set, or neighbour tokens blow PASSAGE_TOKEN_CAP silently."""
    chunks = [_chunk(f"c{i}", source_id="s1", ordinal=i, tokens=4000) for i in range(4)]
    expanded = passages.expand_neighbours([chunks[1]], chunks, radius=1)
    assert len(expanded) == 3                              # 12,000 tokens
    capped = passages._cap_tokens(expanded, cap=9000)
    assert sum(c.token_count for c in capped) <= 9000
    assert capped[0].chunk_ref == "s1:0"                   # kept: first of its source


@needs_model
def test_select_expands_neighbours_of_the_retrieved_chunk():
    reach_questions = list(REGISTRY.in_bucket("actor-reach"))
    chunks = [
        _chunk("The scheme requires a certified diagnosis before a claim.",
               source_id="s1", ordinal=0, tokens=12),
        _chunk("Reach the association by email at contact@example.org or on Instagram.",
               source_id="s1", ordinal=1, tokens=14),
        _chunk("Their annual budget was twelve lakh rupees last cycle.",
               source_id="s1", ordinal=2, tokens=11),
    ]
    bare = passages.select(chunks, reach_questions, k=1, neighbour_radius=0)
    assert [c.chunk_ref for c in bare] == ["s1:1"]
    expanded = passages.select(chunks, reach_questions, k=1, neighbour_radius=1)
    assert [c.chunk_ref for c in expanded] == ["s1:0", "s1:1", "s1:2"]
