"""Track D (`04-worker-build-plan.md` §5) — `search/fuse.py`'s pure `fuse()`.
No network, no model, no database, no pipeline knowledge.

Fixtures: ordinary unit-test cases are inline; the PoC-0b reproduction reads
the 120 recorded responses directly from `poc/poc0b-responses/` (per the
task brief, not copied into `tests/fixtures/`).
"""
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from search.fuse import fuse, normalize_url, RRF_K

HERE = pathlib.Path(__file__).parent
POC0B_RESPONSES = HERE.parent / "poc" / "poc0b-responses"


# --- ordinary unit tests --------------------------------------------------


def test_rank_from_score_not_index():
    # List order deliberately disagrees with score order: the *last* item
    # has the highest score and must end up rank 1.
    results = [
        {"url": "https://a.example/", "score": 0.1},
        {"url": "https://b.example/", "score": 0.2},
        {"url": "https://c.example/", "score": 5.0},
    ]
    fused = fuse({"q1": results})
    by_url = {f.url: f for f in fused}
    assert by_url["https://c.example"].rrf_score == 1.0 / (RRF_K + 1)
    assert by_url["https://b.example"].rrf_score == 1.0 / (RRF_K + 2)
    assert by_url["https://a.example"].rrf_score == 1.0 / (RRF_K + 3)


def test_rrf_arithmetic_sums_across_queries():
    # Same URL, rank 1 in query "a" and rank 2 in query "b".
    results_by_query = {
        "a": [
            {"url": "https://x.example", "score": 10.0},
            {"url": "https://y.example", "score": 1.0},
        ],
        "b": [
            {"url": "https://y.example", "score": 10.0},
            {"url": "https://x.example", "score": 1.0},
        ],
    }
    fused = fuse(results_by_query)
    by_url = {f.url: f for f in fused}
    expected_x = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 2)
    expected_y = 1.0 / (RRF_K + 2) + 1.0 / (RRF_K + 1)
    assert by_url["https://x.example"].rrf_score == expected_x
    assert by_url["https://y.example"].rrf_score == expected_y
    assert by_url["https://x.example"].coverage_set == frozenset({"a", "b"})
    assert by_url["https://y.example"].coverage_set == frozenset({"a", "b"})


def test_ties_in_score_keep_response_order():
    results = [
        {"url": "https://first.example", "score": 1.0},
        {"url": "https://second.example", "score": 1.0},
    ]
    fused = fuse({"q1": results})
    by_url = {f.url: f for f in fused}
    # first.example appeared first in the tied list -> rank 1
    assert by_url["https://first.example"].rrf_score == 1.0 / (RRF_K + 1)
    assert by_url["https://second.example"].rrf_score == 1.0 / (RRF_K + 2)


def test_url_normalisation_lowercases_host_strips_fragment_and_one_slash():
    assert normalize_url("HTTPS://Example.COM/path/#frag") == (
        "https://example.com/path"
    )
    # single trailing slash stripped, query string kept
    assert normalize_url("https://example.com/path/?q=1") == (
        "https://example.com/path?q=1"
    )
    # no trailing slash: unchanged
    assert normalize_url("https://example.com/path") == (
        "https://example.com/path"
    )


def test_url_normalisation_dedupes_across_case_and_fragment():
    results_by_query = {
        "q1": [
            {"url": "https://Example.com/page#a", "score": 2.0},
            {"url": "https://example.com/page#b", "score": 1.0},
        ]
    }
    fused = fuse(results_by_query)
    assert len(fused) == 1
    assert fused[0].url == "https://example.com/page"
    # both entries fused into ranks 1 and 2 of the same query
    assert fused[0].rrf_score == 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 2)


def test_empty_input():
    assert fuse({}) == []
    assert fuse({"q1": []}) == []


def test_single_query():
    results = [
        {"url": "https://only.example", "score": 3.0},
    ]
    fused = fuse({"q1": results})
    assert len(fused) == 1
    assert fused[0].url == "https://only.example"
    assert fused[0].rrf_score == 1.0 / (RRF_K + 1)
    assert fused[0].coverage_set == frozenset({"q1"})


def test_missing_url_skipped():
    results = [
        {"score": 5.0},
        {"url": "", "score": 4.0},
        {"url": "https://real.example", "score": 1.0},
    ]
    fused = fuse({"q1": results})
    assert len(fused) == 1
    assert fused[0].url == "https://real.example"


# --- PoC-0b reproduction ---------------------------------------------------


def _load_poc0b_by_actor():
    """Group recorded responses by actor slug, keyed by family."""
    by_actor = defaultdict(dict)
    for path in sorted(POC0B_RESPONSES.glob("*.json")):
        rec = json.loads(path.read_text())
        if "raw_response" not in rec:
            continue
        slug = rec["slug"]
        family = rec["family"]
        by_actor[slug][family] = rec.get("raw_response", {}).get("results", [])
    return by_actor


def _select_top_n(fused, n):
    return [f.url for f in fused[:n]]


def _select_set_cover(fused, n):
    from search.cover import cover

    return cover(fused, n)


def test_poc0b_reproduction_never_loses_and_report_counts(capsys):
    """Acceptance criterion: reproduce PoC-0b's own measurement (set-cover
    never loses to top-n) on its own recorded data, for n=3 and n=5.

    poc0b-results.md records: n=3 beats 3, ties 17; n=5 beats 2, ties 18
    (out of 20 actors). This test asserts the never-loses property (the
    thing the build plan requires) and reports the counts it measures so a
    human can compare them against that document — a mismatch is reported,
    not silently forced to match, since this implementation's URL
    normalisation and RRF/cover code are freshly written against the frozen
    contract, not copied from poc/poc0b_analyse.py.
    """
    by_actor = _load_poc0b_by_actor()
    assert len(by_actor) == 20, f"expected 20 actors, found {len(by_actor)}"

    results = {3: {"beats": 0, "ties": 0, "loses": 0, "beats_actors": []},
               5: {"beats": 0, "ties": 0, "loses": 0, "beats_actors": []}}

    for slug, results_by_family in by_actor.items():
        fused = fuse(results_by_family)
        all_families = set()
        cov_map = {}
        for f in fused:
            cov_map[f.url] = f.coverage_set
            all_families |= f.coverage_set

        for n in (3, 5):
            topn_urls = _select_top_n(fused, n)
            cover_urls = _select_set_cover(fused, n)

            topn_cov = set()
            for u in topn_urls:
                topn_cov |= cov_map.get(u, set())
            cover_cov = set()
            for u in cover_urls:
                cover_cov |= cov_map.get(u, set())

            # The property the build plan requires: set-cover never loses.
            assert len(cover_cov) >= len(topn_cov), (
                f"set-cover lost to top-n for actor={slug} n={n}: "
                f"cover={len(cover_cov)} top-n={len(topn_cov)}"
            )

            if len(cover_cov) > len(topn_cov):
                results[n]["beats"] += 1
                results[n]["beats_actors"].append(slug)
            elif len(cover_cov) == len(topn_cov):
                results[n]["ties"] += 1
            else:
                results[n]["loses"] += 1

    for n in (3, 5):
        print(
            f"n={n}: beats={results[n]['beats']} "
            f"ties={results[n]['ties']} loses={results[n]['loses']} "
            f"beats_actors={results[n]['beats_actors']}"
        )

    # Never-loses is asserted above per-actor; also assert it in aggregate.
    assert results[3]["loses"] == 0
    assert results[5]["loses"] == 0
