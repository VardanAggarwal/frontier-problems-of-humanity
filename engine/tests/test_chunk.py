"""Track C (`04-worker-build-plan.md` §4) — `text/chunk.py`'s pure functions.
No DB, no network, no pipeline knowledge; the encoder is loaded lazily and
tests that need it skip cleanly (same pattern as `test_embed.py`,
`test_worker.py`) when the model isn't cached locally.

Fixtures under `tests/fixtures/chunk/`, this track's own, per §4's "no
shared golden file."
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from embed.model import MODEL_NAME
from text import chunk as chunk_mod

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "chunk"

needs_model = pytest.mark.skipif(
    not pathlib.Path.home().joinpath(
        ".cache/huggingface/hub",
        "models--" + MODEL_NAME.replace("/", "--")).exists(),
    reason=f"{MODEL_NAME} not downloaded")


# ---------------------------------------------------------------- degrade --
# No encoder involved at all — these run unconditionally.

def test_degrade_chunk_returns_one_chunk_capped_at_max_chars():
    text = "x" * 5000
    chunks = chunk_mod.degrade_chunk(text, "src-1", max_chars=2000)
    assert len(chunks) == 1
    assert len(chunks[0].text) == 2000
    assert chunks[0].source_id == "src-1"
    assert chunks[0].ordinal == 0


def test_degrade_chunk_token_count_is_a_sentinel():
    chunks = chunk_mod.degrade_chunk("hello world", "src-1")
    assert chunks[0].token_count == -1


def test_degrade_chunk_empty_text_returns_nothing():
    assert chunk_mod.degrade_chunk("   ", "src-1") == []


def test_degrade_chunk_short_text_is_not_padded_or_truncated():
    chunks = chunk_mod.degrade_chunk("short text", "src-1", max_chars=2000)
    assert chunks[0].text == "short text"


# ------------------------------------------------------------- chunk_ref --

def test_chunk_ref_is_source_id_and_ordinal():
    c = chunk_mod.Chunk(text="t", source_id="abc123", ordinal=4, token_count=10)
    assert c.chunk_ref == "abc123:4"


def test_chunk_ref_round_trips_through_the_module_function():
    c = chunk_mod.Chunk(text="t", source_id="abc123", ordinal=4, token_count=10)
    assert chunk_mod.chunk_ref("abc123", 4) == c.chunk_ref


def test_chunk_ref_distinguishes_sources_and_ordinals():
    a = chunk_mod.Chunk(text="t", source_id="a", ordinal=1, token_count=1)
    b = chunk_mod.Chunk(text="t", source_id="a", ordinal=2, token_count=1)
    c = chunk_mod.Chunk(text="t", source_id="b", ordinal=1, token_count=1)
    assert len({a.chunk_ref, b.chunk_ref, c.chunk_ref}) == 3


def test_chunk_empty_text_returns_no_chunks_without_touching_the_encoder():
    assert chunk_mod.chunk("") == []
    assert chunk_mod.chunk("   \n\n  ") == []


# -------------------------------------------------------- real tokenizer --

@needs_model
def test_token_target_is_respected_against_the_real_tokenizer():
    text = (FIXTURES / "sample.txt").read_text()
    chunks = chunk_mod.chunk(text, "src-1")
    assert chunks, "fixture should produce at least one chunk"
    for c in chunks:
        assert c.token_count <= chunk_mod.CHUNK_TOKENS, (
            f"chunk {c.ordinal} is {c.token_count} tokens, over the "
            f"{chunk_mod.CHUNK_TOKENS}-token target")


@needs_model
def test_oversized_paragraph_splits_rather_than_truncates():
    text = (FIXTURES / "sample.txt").read_text()
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    long_paragraph = max(paragraphs, key=len)
    chunks = chunk_mod.chunk(long_paragraph, "src-1")
    assert len(chunks) > 1, "the long paragraph should have been split"
    # Nothing is dropped: every word in the source paragraph appears in the
    # concatenation of the resulting chunks (split, not truncated).
    rejoined = " ".join(c.text for c in chunks)
    # A representative sample of words from the start, middle and end of the
    # paragraph all survive somewhere in the split output.
    assert "Government" in rejoined
    assert "certifying doctors" in rejoined
    assert "implementation" in rejoined


@needs_model
def test_ordinals_are_stable_and_contiguous():
    text = (FIXTURES / "sample.txt").read_text()
    chunks = chunk_mod.chunk(text, "src-1")
    ordinals = [c.ordinal for c in chunks]
    assert ordinals == list(range(len(chunks)))
    # Determinism: re-chunking the same text yields the same ordinals/text.
    again = chunk_mod.chunk(text, "src-1")
    assert [(c.ordinal, c.text) for c in chunks] == [(c.ordinal, c.text) for c in again]


@needs_model
def test_short_paragraphs_stay_whole_and_separate():
    text = (
        "First short paragraph, well under the token target.\n\n"
        "Second short paragraph, also well under the target."
    )
    chunks = chunk_mod.chunk(text, "src-1")
    assert len(chunks) == 2
    assert chunks[0].text.startswith("First")
    assert chunks[1].text.startswith("Second")


@needs_model
def test_chunk_respects_a_custom_target_tokens():
    text = (FIXTURES / "sample.txt").read_text()
    wide = chunk_mod.chunk(text, "src-1", target_tokens=320)
    narrow = chunk_mod.chunk(text, "src-1", target_tokens=40)
    assert len(narrow) > len(wide)
    for c in narrow:
        assert c.token_count <= 40


@needs_model
def test_devanagari_paragraph_is_not_silently_dropped():
    text = (FIXTURES / "sample.txt").read_text()
    chunks = chunk_mod.chunk(text, "src-1")
    assert any("सिलिकोसिस" in c.text for c in chunks)
