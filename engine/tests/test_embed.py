"""Tier 1 — the encoder contract, the text rules, and the vector index.

Everything here except the two `needs_model` tests runs offline. The split is
deliberate: the expensive, downloadable part of tier 1 is the encoder, and the
parts most likely to be got wrong (the e5 prefix, the cosine conversion, what
text stands for an entity) are all testable without it.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import math
import sqlite3

import pytest

from embed import index, texts
from embed.model import EMBED_DIM, MODEL_NAME, encode, prefix
from store import db

vec = pytest.importorskip("sqlite_vec")
needs_model = pytest.mark.skipif(
    not pathlib.Path.home().joinpath(
        ".cache/huggingface/hub",
        "models--" + MODEL_NAME.replace("/", "--")).exists(),
    reason=f"{MODEL_NAME} not downloaded")


@pytest.fixture
def conn(tmp_path):
    c = index.connect(tmp_path / "g.db")
    yield c
    c.close()


def unit(*head) -> list[float]:
    """A unit vector whose first components are `head`."""
    v = list(head) + [0.0] * (EMBED_DIM - len(head))
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


# ------------------------------------------------------------ the prefix ----
# e5 degrades silently without one, so the failure has to be made loud here.

def test_prefix_applies_the_role():
    assert prefix("silicosis in Rajasthan", "query") == "query: silicosis in Rajasthan"
    assert prefix("silicosis in Rajasthan", "passage") == "passage: silicosis in Rajasthan"


def test_prefix_rejects_an_unknown_role():
    with pytest.raises(ValueError, match="role must be"):
        prefix("x", "document")


def test_prefix_rejects_empty_text():
    for empty in ("", "   ", "\n"):
        with pytest.raises(ValueError, match="empty"):
            prefix(empty, "query")


def test_prefix_refuses_to_double_prefix():
    """Double-prefixing is the silent-degradation case in the other direction —
    the model sees the literal word 'query' as content."""
    with pytest.raises(ValueError, match="already carries"):
        prefix("query: silicosis", "query")
    with pytest.raises(ValueError, match="already carries"):
        prefix("Passage:  silicosis", "query")


def test_encode_requires_role_as_a_keyword():
    with pytest.raises(TypeError):
        encode(["x"], "query")        # positional — must not be accepted


# ------------------------------------------------------------- the texts ----

def test_clip_cuts_on_a_word_boundary():
    out = texts.clip("alpha beta gamma delta", limit=12)
    assert out == "alpha beta" and not out.endswith(" ")


def test_clip_collapses_whitespace():
    assert texts.clip("a\n\n b\tc") == "a b c"


def test_lead_paragraph_survives_a_body_that_contains_a_rule(tmp_path):
    """The migration's original frontmatter split broke on exactly this file
    shape — a `---` inside the body — so it is pinned here too."""
    p = tmp_path / "a.md"
    p.write_text("---\nname: X\n---\n\n# X\n\n**What they do.** They do a thing.\n\n"
                 "---\n\n## Scope\n- more\n")
    assert texts.lead_paragraph(p) == "What they do. They do a thing."


def test_lead_paragraph_skips_headings_and_comments(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Title\n\n<!-- a note -->\n\n## Scope\n\nReal prose here.\n")
    assert texts.lead_paragraph(p) == "Real prose here."


def test_lead_paragraph_of_a_missing_file_is_empty(tmp_path):
    assert texts.lead_paragraph(tmp_path / "nope.md") == ""


def test_problem_text_is_title_plus_one_line(conn):
    db.put(conn, "problem", {"id": "p1", "title": "Cookfire smoke",
                             "one_line": "Household air pollution from solid fuel."},
           by="test")
    row = conn.execute("SELECT * FROM problem WHERE id='p1'").fetchone()
    assert texts.problem_text(row) == (
        "Cookfire smoke. Household air pollution from solid fuel.")


def test_problem_text_without_a_one_line_is_just_the_title(conn):
    db.put(conn, "problem", {"id": "p2", "title": "A stub"}, by="test")
    row = conn.execute("SELECT * FROM problem WHERE id='p2'").fetchone()
    assert texts.problem_text(row) == "A stub."


def test_actor_text_falls_back_to_the_title(conn, tmp_path):
    db.put(conn, "actor", {"id": "a1", "title": "Some Org", "type": "org"}, by="test")
    row = conn.execute("SELECT * FROM actor WHERE id='a1'").fetchone()
    assert texts.actor_text(row, tmp_path) == "Some Org"


def test_actor_text_appends_the_lead(conn, tmp_path):
    (tmp_path / "a.md").write_text("# Some Org\n\n**What they do.** Field work.\n")
    db.put(conn, "actor", {"id": "a1", "title": "Some Org", "type": "org",
                           "doc": "a.md"}, by="test")
    row = conn.execute("SELECT * FROM actor WHERE id='a1'").fetchone()
    assert texts.actor_text(row, tmp_path) == "Some Org — What they do. Field work."


# ------------------------------------------------------------- the index ----

def test_knn_returns_cosine_not_distance(conn):
    """Vectors are normalized, so cos = 1 - d^2/2 is exact, not an approximation.
    An identical vector must come back at 1.0, an orthogonal one at 0.0."""
    index.put(conn, "problem", "same", unit(1.0), "t")
    index.put(conn, "problem", "orthogonal", unit(0.0, 1.0), "t")
    hits = dict(index.knn(conn, "problem", unit(1.0), k=2))
    assert hits["same"] == pytest.approx(1.0, abs=1e-5)
    assert hits["orthogonal"] == pytest.approx(0.0, abs=1e-5)


def test_knn_orders_by_similarity_descending(conn):
    index.put(conn, "actor", "near", unit(0.9, 0.1), "t")
    index.put(conn, "actor", "far", unit(0.1, 0.9), "t")
    assert [i for i, _ in index.knn(conn, "actor", unit(1.0), k=2)] == ["near", "far"]


def test_knn_can_exclude_the_query_entity(conn):
    """Self-similarity is 1.0 and would otherwise take every top slot in an
    all-pairs sweep."""
    index.put(conn, "problem", "self", unit(1.0), "t")
    index.put(conn, "problem", "other", unit(0.8, 0.6), "t")
    hits = index.knn(conn, "problem", unit(1.0), k=1, exclude="self")
    assert [i for i, _ in hits] == ["other"]


def test_ids_containing_a_colon_survive_the_key_encoding(conn):
    index.put(conn, "source", "doi:10.1/abc", unit(1.0), "t")
    assert index.knn(conn, "source", unit(1.0), k=1)[0][0] == "doi:10.1/abc"


def test_put_is_idempotent(conn):
    index.put(conn, "problem", "p", unit(1.0), "t")
    index.put(conn, "problem", "p", unit(0.0, 1.0), "t2")
    assert index.counts(conn)["problem"] == 1
    assert conn.execute("SELECT count(*) FROM vec_problem").fetchone()[0] == 1
    assert index.knn(conn, "problem", unit(0.0, 1.0), k=1)[0][1] == pytest.approx(1.0, abs=1e-5)


def test_roles_do_not_collide(conn):
    """One entity can hold both a symmetric and an asymmetric vector; a kNN in
    one role must not see the other (01-minimal.md §8)."""
    index.put(conn, "problem", "p", unit(1.0), "t", role="query")
    index.put(conn, "problem", "p", unit(0.0, 1.0), "t", role="passage")
    assert index.counts(conn)["problem"] == 2
    assert index.knn(conn, "problem", unit(1.0), k=5, role="query") == [
        ("p", pytest.approx(1.0, abs=1e-5))]
    assert index.knn(conn, "problem", unit(0.0, 1.0), k=5, role="passage") == [
        ("p", pytest.approx(1.0, abs=1e-5))]


def test_drop_removes_both_halves(conn):
    index.put(conn, "problem", "p", unit(1.0), "t")
    index.drop(conn, "problem", "p")
    assert index.counts(conn)["problem"] == 0
    assert index.knn(conn, "problem", unit(1.0), k=5) == []


def test_stale_is_false_only_for_the_same_text_and_model(conn, monkeypatch):
    index.put(conn, "problem", "p", unit(1.0), "the text")
    assert index.stale(conn, "problem", "p", "the text") is False
    assert index.stale(conn, "problem", "p", "other text") is True
    assert index.stale(conn, "problem", "missing", "the text") is True
    monkeypatch.setattr(index, "MODEL_NAME", "some/other-model")
    assert index.stale(conn, "problem", "p", "the text") is True


def test_put_rejects_an_unknown_kind(conn):
    with pytest.raises(ValueError, match="kind must be"):
        index.put(conn, "edge", "e", unit(1.0), "t")


def test_the_graph_stays_readable_without_the_extension(tmp_path):
    """The vectors live in the same file as the graph, so a reader that never
    loads sqlite-vec must still be able to read every ordinary table."""
    path = tmp_path / "g.db"
    c = index.connect(path)
    db.put(c, "problem", {"id": "p", "title": "T"}, by="test")
    index.put(c, "problem", "p", unit(1.0), "t")
    c.commit(); c.close()

    plain = sqlite3.connect(path)
    plain.row_factory = sqlite3.Row
    assert plain.execute("SELECT title FROM problem").fetchone()["title"] == "T"
    assert plain.execute("SELECT count(*) FROM embedding").fetchone()[0] == 1
    with pytest.raises(sqlite3.OperationalError, match="no such module"):
        plain.execute("SELECT count(*) FROM vec_problem").fetchall()
    plain.close()


# -------------------------------------------------------------- the model ---

@needs_model
def test_encode_is_normalized_and_the_right_width():
    v = encode(["silicosis in Rajasthan sandstone quarries"], role="query")
    assert v.shape == (1, EMBED_DIM)
    assert float((v[0] ** 2).sum()) == pytest.approx(1.0, abs=1e-4)


@needs_model
def test_the_prefix_actually_moves_the_vector():
    """If this ever comes back identical, the prefix is being stripped somewhere
    and every vector in the file is worth less than it looks."""
    same = encode(["a sentence about water"], role="query")[0]
    other = encode(["a sentence about water"], role="passage")[0]
    assert float((same * other).sum()) < 0.9999


# ---------------------------------------------- defects found under review --
# Each of these reproduces a real half-write, leak or hang before its fix.

def test_a_rejected_write_leaves_nothing_behind(conn):
    """A wrong-width vector used to land the DELETE, fail the INSERT, and leave
    a bookkeeping row claiming the entity was current — so `stale` said no and
    `knn` returned nothing, permanently."""
    index.put(conn, "problem", "p", unit(1.0), "first")
    with pytest.raises(ValueError, match="dimensions"):
        index.put(conn, "problem", "p", [0.1] * 768, "second")
    assert index.knn(conn, "problem", unit(1.0), k=1)[0][0] == "p"
    assert index.stale(conn, "problem", "p", "first") is False
    assert index.stale(conn, "problem", "p", "second") is True


def test_a_bad_role_is_refused_by_every_entry_point(conn):
    index.put(conn, "problem", "p", unit(1.0), "t")
    for call in (lambda: index.put(conn, "problem", "p", unit(1.0), "t", role="Query"),
                 lambda: index.drop(conn, "problem", "p", role="Query"),
                 lambda: index.stale(conn, "problem", "p", "t", role="Query"),
                 lambda: index.knn(conn, "problem", unit(1.0), role="Query"),
                 lambda: index.indexed(conn, "problem", role="Query")):
        with pytest.raises(ValueError, match="role must be"):
            call()
    assert conn.execute("SELECT count(*) FROM vec_problem").fetchone()[0] == 1


def test_prune_drops_what_the_store_has_ruled_out(conn):
    """The index only ever grew. An actor set to `depth: excluded` kept
    answering kNN, and a source given a `canonical_of` left the duplicate in
    beside its own survivor."""
    for aid in ("keep", "excluded"):
        index.put(conn, "actor", aid, unit(1.0), "t")
    assert index.prune(conn, "actor", {"keep"}) == ["excluded"]
    assert index.indexed(conn, "actor") == {"keep"}
    assert index.counts(conn)["actor"] == 1


def test_prune_leaves_the_other_role_alone(conn):
    index.put(conn, "problem", "p", unit(1.0), "t", role="query")
    index.put(conn, "problem", "p", unit(1.0), "t", role="passage")
    assert index.prune(conn, "problem", set(), role="query") == ["p"]
    assert index.indexed(conn, "problem", role="passage") == {"p"}


def test_encode_of_an_empty_list_still_checks_the_role():
    """`prefix` is never reached on an empty input, so the only role check that
    could fire is the one in `encode` itself."""
    with pytest.raises(ValueError, match="role must be"):
        encode([], role="documnet")


def test_a_blank_problem_is_not_embeddable(conn):
    """`". ".join([]) + "."` is the string ".", which is truthy, so backfill
    used to schedule an encode of `query: .` as if it were a record."""
    db.put(conn, "problem", {"id": "blank", "title": " "}, by="test")
    row = conn.execute("SELECT * FROM problem WHERE id='blank'").fetchone()
    assert texts.problem_text(row) == ""


def test_auc_scores_ties_at_a_half():
    """`argsort().argsort()` counts every tie as a loss, so two identical
    distributions read 0.0 instead of 0.5 — an AUC biased down by exactly the
    amount a narrow-band model produces most of."""
    np = pytest.importorskip("numpy")
    from embed.calibrate import auc
    assert auc(np, np.array([0.8, 0.8]), np.array([0.8, 0.8])) == 0.5
    assert auc(np, np.array([0.9, 0.8]), np.array([0.1, 0.2])) == 1.0
    assert auc(np, np.array([0.9, 0.5]), np.array([0.4, 0.6])) == 0.75


def test_the_negative_sampler_terminates_when_there_are_no_negatives(conn):
    """Every (actor, problem) pair being an edge used to hang the sweep with no
    output at all."""
    np = pytest.importorskip("numpy")
    import random as _random
    from embed.calibrate import screen
    db.put(conn, "problem", {"id": "p", "title": "P"}, by="test")
    db.put(conn, "actor", {"id": "a", "title": "A", "type": "org"}, by="test")
    db.link(conn, ("actor", "a"), "works_on", ("problem", "p"), by="test")
    index.put(conn, "problem", "p", unit(1.0), "t")
    index.put(conn, "actor", "a", unit(1.0), "t")
    pos, neg = screen(conn, np, _random.Random(0), 50)
    assert len(pos) == 1 and len(neg) == 0


def test_nearest_matches_the_dense_computation(conn):
    """The chunked version replaced one that allocated n^2 plus an int64
    argsort of it — ~28 GB at 50k entities to return ten rows."""
    np = pytest.importorskip("numpy")
    from embed.calibrate import nearest
    rng = np.random.default_rng(0)
    m = rng.normal(size=(40, EMBED_DIM)).astype("float32")
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    ids = [f"e{i}" for i in range(40)]
    sims = m @ m.T
    iu = np.triu_indices(40, k=1)
    want = sorted(((float(sims[i, j]), ids[i], ids[j])
                   for i, j in zip(*iu)), reverse=True)[:5]
    got = nearest(np, ids, m, top=5, chunk=7)
    assert [round(s, 5) for s, _, _ in got] == [round(s, 5) for s, _, _ in want]


# ------------------------------------------- dedup, against the real labels --
# The `silicosis-rajasthan-2026-09` set is the only labelled document corpus the
# project has, and §8 finding 2 was derived from it. Running tier 1 against the
# same labels is the only honest check on that finding's claim about embeddings.

LIVE = pathlib.Path(__file__).parent / "fixtures" / "live"
GROUND_TRUTH = [{"04", "06", "10", "18", "19", "20"}, {"02", "21"}, {"05", "07"}]
needs_fixtures = pytest.mark.skipif(not LIVE.exists(), reason="live fixtures absent")


def _usable_documents():
    """Cleaned text for the pages that are documents at all (gate 0)."""
    from text.clean import clean
    from text.pagestate import assess
    out = {}
    for path in sorted(LIVE.glob("*.html")):
        raw = path.read_text(errors="replace")
        body = clean(raw)
        if assess(body, raw=raw).state in ("ok", "thin"):
            out[path.stem] = texts.clip(body)
    return out


@needs_model
@needs_fixtures
def test_embeddings_alone_do_not_separate_same_work_from_same_topic():
    """A pinned NEGATIVE result, and the reason gate 0 stays in front.

    §8 finding 2 promoted embeddings to "the primary dedup path". Measured on
    the labels that finding came from, they are not: the lowest same-work pair
    (04~06, the PMC/Ovid renderings SimHash missed) scores BELOW the highest
    different-work pair (13~16, two distinct articles about one settlement).
    No threshold separates them, so no threshold may be hard-coded downstream.

    If a model change ever makes this separable, this test fails — which is the
    point. Re-measure and rewrite the finding rather than deleting the test."""
    import itertools
    docs = _usable_documents()
    keys = sorted(docs)
    sims = encode([docs[k] for k in keys], role="query")
    sims = sims @ sims.T
    same, different = [], []
    for i, j in itertools.combinations(range(len(keys)), 2):
        pair = {keys[i], keys[j]}
        bucket = same if any(pair <= g for g in GROUND_TRUTH) else different
        bucket.append(float(sims[i, j]))
    assert same and different
    assert min(same) <= max(different), (
        f"embeddings now separate cleanly ({min(same):.3f} > {max(different):.3f}) "
        "— re-measure §8 finding 2 and rewrite it")


@needs_model
@needs_fixtures
def test_gate_0_still_covers_what_the_vectors_cannot_reach():
    """Ten of the 21 pages never yield text, so no vector of them can exist.
    Whatever tier 1 is worth, it is worth it on half the set."""
    assert len(_usable_documents()) == 11


# ----------------------------------------------- the second review, 2026-09-13 --
def test_plan_does_not_touch_the_encoder(conn, monkeypatch, tmp_path):
    """A no-op re-run must not load a 470 MB model to discover it has nothing
    to do. `plan` used to token-fit every row before checking the hash, so the
    documented cheap case paid the full model load."""
    import embed.model as model
    from embed import backfill
    monkeypatch.setattr(model, "get_encoder",
                        lambda: pytest.fail("plan loaded the encoder"))
    db.put(conn, "problem", {"id": "p1", "title": "Silicosis", "one_line": "Dust."},
           by="test")
    work, fresh, empty, keep = backfill.plan(conn, "problem", tmp_path, force=False)
    assert [w[0] for w in work] == ["p1"] and keep == {"p1"}


def test_a_current_row_stays_current_without_the_tokenizer(conn, tmp_path):
    """The hash is over the pre-truncation text, so `stale` answers without
    fitting — the property that makes the test above possible."""
    from embed import backfill
    db.put(conn, "problem", {"id": "p1", "title": "Silicosis", "one_line": "Dust."},
           by="test")
    text = texts.problem_text(conn.execute(
        "SELECT id, title, one_line, doc FROM problem").fetchone())
    index.put(conn, "problem", "p1", unit(1.0), "TRUNCATED AT 512 TOKENS",
              hashed=text)
    work, fresh, _, _ = backfill.plan(conn, "problem", tmp_path, force=False)
    assert work == [] and fresh == 1


def test_put_records_the_encoded_length_and_the_source_hash(conn):
    index.put(conn, "problem", "p", unit(1.0), "short", hashed="a much longer source")
    row = conn.execute("SELECT chars, text_hash FROM embedding").fetchone()
    assert row["chars"] == len("short")
    assert row["text_hash"] == index.text_hash("a much longer source")
    assert not index.stale(conn, "problem", "p", "a much longer source")


@needs_model
def test_fit_never_overruns_the_encoder_once_prefixed():
    """The truncation used to slice the joint tokenization and drop
    `len(tokenize(prefix))` tokens off the front, which assumes a sub-word
    tokenizer cannot merge across the prefix boundary. Measure the whole
    prefixed string instead — that is the only length the model sees."""
    from embed.model import fit, get_encoder, prefix
    enc = get_encoder()
    budget = getattr(enc, "max_seq_length", 512) - 2
    for body in ("ख़तरनाक सिलिका धूल " * 400,        # Devanagari, dense tokens
                 "silica dust exposure in stone crushing units " * 300,
                 "देश" * 2000):                      # no spaces at all
        cut = fit(body)
        assert cut, "fit returned nothing"
        n = len(enc.tokenizer(prefix(cut, "query"),
                              add_special_tokens=False)["input_ids"])
        assert n <= budget, f"{n} tokens > {budget}"
        assert body.startswith(cut[:20]), "truncation started mid-string"


@needs_model
def test_fit_leaves_a_short_text_byte_identical():
    from embed.model import fit
    assert fit("  Silicosis in Rajasthan sandstone.  ") == \
        "Silicosis in Rajasthan sandstone."
