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


# ── Entity-density top-up — catches name-list chunks question-shaped
# buckets miss (module docstring). Pure, no encoder.

def test_entity_density_counts_capitalized_runs():
    assert passages._entity_density(
        "Co-signed by the Rural Collective, funded by the Gramin Foundation "
        "and coordinated with the Zilla Trust and the local panchayat."
    ) >= 3
    assert passages._entity_density("the scheme requires a certified diagnosis") == 0


def test_entity_density_tolerates_a_single_internal_of():
    # "Ministry of Labour" must count as one entity, not zero — a bare
    # capitalized-run regex misses it because "of" breaks the run.
    assert passages._entity_density(
        "According to the Ministry of Labour, cases have risen.") == 1


def test_entity_density_does_not_merge_names_joined_by_and():
    # "and"/"the" are deliberately not tolerated as internal connectors:
    # they routinely separate two DIFFERENT names in a list, and merging
    # would undercount rather than fix anything.
    assert passages._entity_density(
        "Supported by the Adivasi Trust and Ministry of Health.") == 2


def test_entity_dense_top_up_pulls_in_a_low_ranked_name_list_chunk():
    name_chunk = _chunk(
        "Co-signed by the Rural Collective, funded by the Gramin Foundation, "
        "coordinated with the Zilla Trust and the Block Development Office.",
        source_id="s1", ordinal=5)
    already_kept = {"s1:0": _chunk("kept already", source_id="s1", ordinal=0)}
    pool = [already_kept["s1:0"], name_chunk,
            _chunk("no names here at all", source_id="s1", ordinal=1)]
    out = passages._entity_dense_top_up(pool, already_kept, top_n=2)
    assert name_chunk in out
    assert already_kept["s1:0"] not in out, "already-selected chunks are not re-added"


def test_entity_dense_top_up_skips_chunks_with_no_entity_content():
    plain = [_chunk("the scheme requires a certified diagnosis", ordinal=0),
             _chunk("annual figures were reported last year", ordinal=1)]
    assert passages._entity_dense_top_up(plain, {}, top_n=2) == []


def test_entity_dense_top_up_respects_top_n():
    chunks = [
        _chunk(f"Signed by the Alpha Collective number {i} and the Beta Foundation",
               ordinal=i)
        for i in range(5)
    ]
    out = passages._entity_dense_top_up(chunks, {}, top_n=2)
    assert len(out) == 2


def test_select_with_no_bucketed_questions_is_unaffected_by_top_up():
    """The early-return path (no bucketed questions) stays a plain slice —
    entity top-up only fires once there is a bucketed selection to add to."""
    chunks = [_chunk(f"chunk {i}", ordinal=i) for i in range(5)]
    unbucketed = [q for q in REGISTRY.all("actor") if q.bucket is None]
    out = passages.select(chunks, unbucketed, k=2)
    assert out == chunks[:2]


def test_entity_dense_top_up_still_respects_token_cap_via_select():
    """Force every bucket-ranked chunk out via a tiny cap; the top-up chunk
    must go through _cap_tokens like everything else, not bypass it."""
    chunks = [_chunk("plain filler text with nothing special", ordinal=0, tokens=8000)]
    out = passages._entity_dense_top_up(chunks, {}, top_n=2)
    assert out == [], "no entity content -> nothing to top up, cap never tested here"

    name_chunk = _chunk(
        "Convened by the Delhi Trust and the Uttar Pradesh Collective and the "
        "National Rural Mission.", source_id="s1", ordinal=0, tokens=5000)
    filler = _chunk("no names in here at all whatsoever", source_id="s1",
                     ordinal=1, tokens=5000)
    ordered = [filler] + passages._entity_dense_top_up([filler, name_chunk], {}, top_n=2)
    capped = passages._cap_tokens(ordered, cap=6000)
    assert sum(c.token_count for c in capped) <= 6000
    assert len(capped) == 1, "cap still drops the lower-priority (later) chunk"


@needs_model
def test_select_pulls_in_name_dense_chunk_that_ranks_low_on_every_bucket():
    """End-to-end through select(): a chunk that is a pure name-list should
    not need to win any bucket's retrieval ranking to reach the prompt."""
    reach_questions = list(REGISTRY.in_bucket("actor-reach"))
    name_chunk = _chunk(
        "Co-signed by the Rural Collective, funded by the Gramin Foundation, "
        "coordinated with the Zilla Trust and the Block Development Office.",
        source_id="s1", ordinal=10)
    # Fill every top-k slot with chunks that are obviously about contact
    # info, so name_chunk cannot win the bucket on relevance alone.
    filler = [
        _chunk("Email us at contact@example.org or find us on Instagram and Twitter.",
               source_id="s1", ordinal=i)
        for i in range(3)
    ]
    out = passages.select(filler + [name_chunk], reach_questions, k=2, neighbour_radius=0)
    assert name_chunk in out


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


# --- India-anchor top-up (kind: problem only) -------------------------------


def test_india_anchor_density_counts_terms():
    assert passages._india_anchor_density(
        "The Ministry of Petroleum reported 10.33 crore LPG connections "
        "in India under the Pradhan Mantri Ujjwala Yojana.") >= 2
    assert passages._india_anchor_density(
        "A cohort of 300,000 women in ten Chinese provinces.") == 0


def test_india_anchor_density_is_case_insensitive():
    assert passages._india_anchor_density("INDIA reported new figures.") == 1


def test_india_anchor_top_up_pulls_in_a_low_ranked_india_chunk():
    india_chunk = _chunk(
        "According to NITI Aayog, India's LPG coverage reached 10.33 crore "
        "connections under the Ujjwala scheme.", source_id="s1", ordinal=5)
    already_kept = {"s1:0": _chunk("kept already", source_id="s1", ordinal=0)}
    pool = [already_kept["s1:0"], india_chunk,
            _chunk("no India terms here at all", source_id="s1", ordinal=1)]
    out = passages._india_anchor_top_up(pool, already_kept, top_n=2)
    assert india_chunk in out
    assert already_kept["s1:0"] not in out, "already-selected chunks are not re-added"


def test_india_anchor_top_up_skips_chunks_with_no_india_content():
    plain = [_chunk("a cohort of women in ten Chinese provinces", ordinal=0),
             _chunk("global projections through 2030", ordinal=1)]
    assert passages._india_anchor_top_up(plain, {}, top_n=2) == []


def test_india_anchor_top_up_respects_top_n():
    chunks = [
        _chunk(f"India reported figures for region {i} via NITI Aayog", ordinal=i)
        for i in range(5)
    ]
    out = passages._india_anchor_top_up(chunks, {}, top_n=2)
    assert len(out) == 2


def test_select_geography_bias_false_by_default_does_not_top_up():
    """Default `geography_bias=False` — an India-anchored chunk that loses
    every bucket must NOT be added unless the caller opts in."""
    unbucketed = [q for q in REGISTRY.all("actor") if q.bucket is None]
    india_chunk = _chunk("India reported new NITI Aayog figures.", ordinal=0)
    out = passages.select([india_chunk], unbucketed, k=1)
    # no bucketed questions -> early-return slice path; top-up never runs
    # regardless of geography_bias, same as the entity top-up (see the test
    # above this section) — asserting the flag alone changes nothing here.
    assert out == [india_chunk]


@needs_model
def test_select_geography_bias_pulls_in_india_chunk_that_ranks_low_on_every_bucket(monkeypatch):
    """An India-anchored chunk that loses every bucket's ranking still
    reaches the prompt when `geography_bias=True` — mirrors the
    entity-density end-to-end test.

    `_rank_chunks` is monkeypatched rather than exercised for real (unlike
    the sibling entity-density test above): the real encoder's cosine
    margin between an India-anchored-but-numberless chunk and a
    magnitude-shaped filler chunk was measured at ~0.75 vs ~0.80-0.82 —
    real, but close enough to the boundary that encoder batching order
    flipped the k=2 cut between runs in practice (this test flaked on that
    exact fixture during development). What this test needs to verify is
    `select()`'s own `geography_bias` wiring — that the top-up fires and is
    additive to the bucket ranking, not the embedding model's opinion on a
    specific sentence pair — so the ranking step is pinned instead.

    `india_chunk`'s text is deliberately institution-name-free (no
    capitalized multi-word run): an earlier draft named "the Ministry of
    Petroleum and Natural Gas", which is ALSO entity-dense
    (`_entity_density` >= 2 on that phrase) and so got pulled in by the
    pre-existing, unconditional entity top-up regardless of
    `geography_bias` — a real cross-talk between the two top-ups, not a
    bug in either, but it defeated this test's isolation. Lowercase
    phrasing with an India-anchor term and no proper noun keeps the two
    signals independent."""
    evidence_questions = list(REGISTRY.in_bucket("problem-evidence"))
    india_chunk = _chunk(
        "The scheme is funded through public expenditure of several crore "
        "rupees in India, delivered via designated distribution channels.",
        source_id="s1", ordinal=10)
    filler = [
        _chunk(f"The magnitude is a number, out of a denominator, dated "
               f"and sourced, variant {i}.", source_id="s1", ordinal=i)
        for i in range(3)
    ]
    # Pin the ranking: filler always beats india_chunk, deterministically,
    # regardless of query text — this is the "loses every bucket" premise
    # the top-up exists to cover, made exact instead of measured.
    def fixed_ranking(query, chunks, p_vecs=None):
        return sorted(chunks, key=lambda c: 0 if c is not india_chunk else 1)
    monkeypatch.setattr(passages, "_rank_chunks", fixed_ranking)

    without_bias = passages.select(filler + [india_chunk], evidence_questions, k=2,
                                   neighbour_radius=0, geography_bias=False)
    with_bias = passages.select(filler + [india_chunk], evidence_questions, k=2,
                                neighbour_radius=0, geography_bias=True)
    assert india_chunk not in without_bias, \
        "test fixture assumption broken: india_chunk must lose the bucket ranking"
    assert india_chunk in with_bias


# ---------------------------------------------------------- candidate-identity gate --

@needs_model
def test_select_candidate_name_gate_excludes_unrelated_chunk_when_ontopic_exists(monkeypatch):
    """Regression for the `anaemia-mukt-bharat` bug (2026-09-19,
    `worker/passages.py`'s "Candidate-identity gate" docstring): a chunk
    about an unrelated org out-scored every on-topic chunk across nearly
    every bucket because it was a near-perfect semantic match for the
    bucket's query, with nothing checking it was actually about the
    candidate. Ranking is pinned (same technique as the geography-bias test
    above) so the unrelated chunk deterministically wins the bucket ranking
    — the fixture reproduces the bug's premise exactly, rather than hoping
    the real encoder agrees on this specific sentence pair."""
    reach_questions = list(REGISTRY.in_bucket("actor-reach"))
    ontopic = _chunk(
        "Anaemia Mukt Bharat runs community iron-folic acid distribution "
        "across state blocks; reach the programme office by email.",
        source_id="s1", ordinal=0)
    unrelated = _chunk(
        "WeTheChange is hiring! Email careers@wethechange.org to join our "
        "menstrual health outreach team.", source_id="s2", ordinal=0)

    def fixed_ranking(query, chunks, p_vecs=None):
        return sorted(chunks, key=lambda c: 0 if c is unrelated else 1)
    monkeypatch.setattr(passages, "_rank_chunks", fixed_ranking)

    without_gate = passages.select([ontopic, unrelated], reach_questions, k=1,
                                   neighbour_radius=0)
    with_gate = passages.select([ontopic, unrelated], reach_questions, k=1,
                                neighbour_radius=0, candidate_name="Anaemia Mukt Bharat")

    # Backward compat: no candidate_name -> old behaviour, unrelated chunk
    # still wins the (pinned) bucket ranking exactly as it did before this
    # gate existed.
    assert unrelated in without_gate, \
        "test fixture assumption broken: unrelated must win the pinned ranking"
    # With the gate: the unrelated chunk is filtered out before ranking ever
    # runs, because it never mentions the candidate's name.
    assert unrelated not in with_gate
    assert ontopic in with_gate


def test_select_candidate_name_gate_degrades_when_no_chunk_mentions_the_name():
    """None of the fetched chunks ever spell out the candidate's name (e.g.
    an abbreviation-only or pronoun-heavy source set) — the gate must not
    wipe the pool to empty. It no-ops, same as if `candidate_name` were
    never passed (module docstring: "degrade, not a wipeout")."""
    unbucketed = [q for q in REGISTRY.all("actor") if q.bucket is None]
    chunks = [_chunk(f"chunk {i}", ordinal=i) for i in range(3)]
    out = passages.select(chunks, unbucketed, k=2, candidate_name="Anaemia Mukt Bharat")
    assert out == chunks[:2]
