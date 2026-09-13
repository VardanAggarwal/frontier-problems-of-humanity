"""Track D (`04-worker-build-plan.md` §5) — `fuse()`, one of the two frozen
contracts:

    fuse(results_by_query) -> [(url, rrf_score, coverage_set)]

Pure function. No network, no model, no database, no knowledge of the
pipeline that will call it.

`results_by_query` is a mapping of query/family id -> list of result dicts,
each carrying at least `url` and `score` (SearXNG's own relevance score,
already present in the recorded PoC-0b responses' `raw_response.results`).

Rank is derived from that `score` field, sorted descending, **never** from
the JSON list index — `04-worker-build-plan.md` §4's explicit obligation,
verified against PoC-0a (score is monotone with agreement). Ties in score
keep the response's own (stable) ordering.

RRF: score = sum over queries of 1 / (k + rank), k = 60, rank 1-based.

`coverage_set` is the set of query/family ids that returned that URL, after
URL normalisation (see `normalize_url` below).
"""
from typing import NamedTuple
from urllib.parse import urlsplit, urlunsplit

RRF_K = 60


class FusedResult(NamedTuple):
    url: str
    rrf_score: float
    coverage_set: frozenset


def normalize_url(url):
    """Lowercase the host, strip the fragment, strip a single trailing
    slash. Query strings are kept — do not strip them. Deterministic.
    """
    if not url:
        return url
    parts = urlsplit(url)
    netloc = parts.netloc.lower()
    path = parts.path
    if path.endswith("/"):
        path = path[:-1]
    return urlunsplit((parts.scheme, netloc, path, parts.query, ""))


def fuse(results_by_query):
    """results_by_query: {query_id: [result_dict, ...]}.

    Returns a list of FusedResult, sorted by rrf_score descending (tie-break
    url ascending, for a deterministic return order — the contract doesn't
    mandate an order but downstream consumers benefit from a stable one).
    """
    url_score = {}
    url_coverage = {}

    for query_id, results in results_by_query.items():
        ranked = sorted(
            results or [], key=lambda r: r.get("score", 0.0), reverse=True
        )
        for idx, res in enumerate(ranked):
            raw_url = res.get("url")
            url = normalize_url(raw_url)
            if not url:
                continue
            rank = idx + 1  # rank from score-sorted position, not JSON index
            url_score[url] = url_score.get(url, 0.0) + 1.0 / (RRF_K + rank)
            url_coverage.setdefault(url, set()).add(query_id)

    fused = [
        FusedResult(url, url_score[url], frozenset(url_coverage[url]))
        for url in url_score
    ]
    fused.sort(key=lambda f: (-f.rrf_score, f.url))
    return fused
