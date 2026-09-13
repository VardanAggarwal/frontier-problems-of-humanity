"""Track D (`04-worker-build-plan.md` §5) — `cover()`, the second frozen
contract:

    cover(ranked, max_sources) -> [url]

Pure function. No network, no model, no database, no knowledge of the
pipeline that will call it.

`ranked` is the output of `search.fuse.fuse()` (or anything tuple-compatible
with it): an iterable of `(url, rrf_score, coverage_set)`.

Greedy maximum-coverage: repeatedly take the URL adding the most
not-yet-covered query/family ids; tie-break by rrf_score descending, then by
url ascending, so output is deterministic. Stop at `max_sources` or when no
remaining URL adds new coverage. When coverage is exhausted before
`max_sources`, keep filling by rrf_score descending (excluding URLs already
selected) so `cover` never returns fewer URLs than top-n would.
"""


def cover(ranked, max_sources):
    items = list(ranked)
    if max_sources <= 0 or not items:
        return []

    scores = {}
    coverage = {}
    for url, rrf_score, coverage_set in items:
        # First occurrence wins if the same url appears twice; ranked is
        # expected to already be deduped (fuse() guarantees this).
        scores.setdefault(url, rrf_score)
        coverage.setdefault(url, set(coverage_set))

    all_ids = set()
    for cov in coverage.values():
        all_ids |= cov

    uncovered = set(all_ids)
    selected = []
    candidates = set(coverage.keys())

    while uncovered and len(selected) < max_sources and candidates:
        # Iterate url-ascending so that, among ties on (gain, score), max()
        # returns the first (smallest-url) one encountered.
        ordered_candidates = sorted(candidates)
        best_url = max(
            ordered_candidates,
            key=lambda u: (len(coverage[u] & uncovered), scores[u]),
        )
        best_gain = len(coverage[best_url] & uncovered)
        if best_gain <= 0:
            break
        selected.append(best_url)
        uncovered -= coverage[best_url]
        candidates.discard(best_url)

    if len(selected) < max_sources:
        selected_set = set(selected)
        by_score = sorted(
            coverage.keys(), key=lambda u: (-scores[u], u)
        )
        for url in by_score:
            if len(selected) >= max_sources:
                break
            if url not in selected_set:
                selected.append(url)
                selected_set.add(url)

    return selected
