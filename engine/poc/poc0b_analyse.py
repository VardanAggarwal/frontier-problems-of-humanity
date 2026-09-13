"""PoC-0b — offline analysis over recorded responses. No network.

Reads every `engine/poc/poc0b-responses/<slug>__<family>.json` record written
by `poc0b_run.py` and computes:

  1. The `unresponsive_engines` curve over the run (does the failure rate
     climb with query volume/time — the throttle question `poc0a-results.md`
     left open).
  2. Per-family predicted coverage: did the family's results include a URL
     whose title/snippet plausibly carries the answer-key text for the
     questions that family targets (`poc0b_families.yaml` question_ids
     against `poc0b-sample.json` answer_key groups).
  3. The set-cover vs top-n comparison (03-worker.md §5a/§5b): fuse the 6
     families' results per actor with RRF once, then select sources two ways
       (a) top-n by RRF score
       (b) greedy set cover over family-coverage sets
     and compare union family-coverage at equal n. This is the headline
     output — it is the thing that decides whether §5b's selection algorithm
     is worth building.

`rank` is derived from `score` here, never from JSON list index
(03-worker.md §4), matching the rule poc0b_run.py deliberately does not
enforce at record time (it stores the raw response verbatim).
"""

import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
RESPONSES_DIR = HERE / "poc0b-responses"
SAMPLE_PATH = HERE / "poc0b-sample.json"

RRF_K = 60


def load_sample():
    return json.loads(SAMPLE_PATH.read_text())


def load_records():
    records = []
    for p in sorted(RESPONSES_DIR.glob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if "raw_response" not in rec:
            # an error record from a failed query — keep it for the
            # unresponsive-curve section but skip it for coverage/fusion.
            rec["_error"] = True
        records.append(rec)
    return records


def canonical_url(url):
    """Strip common tracking params so ?utm_source=... variants fuse."""
    if not url:
        return url
    base = url.split("#")[0]
    base = re.sub(r"([?&])(utm_[a-z]+|ref|fbclid)=[^&]*", r"\1", base)
    base = re.sub(r"[?&]+$", "", base)
    return base.rstrip("/")


# --- 1. unresponsive_engines curve ---------------------------------------

def unresponsive_curve(records):
    print("\n=== 1. unresponsive_engines curve over the run ===")
    print(f"{'#':>4}  {'slug':45s} {'family':10s} {'unresponsive':30s} {'silently_absent'}")
    ok_records = [r for r in records if not r.get("_error")]
    running_unresp = 0
    for i, r in enumerate(ok_records, start=1):
        names = [u[0] if isinstance(u, list) else u for u in r.get("unresponsive_engines", [])]
        if names:
            running_unresp += 1
        print(
            f"{i:4d}  {r['slug']:45s} {r['family']:10s} "
            f"{','.join(names) or '-':30s} {r.get('silently_absent_engines') or ''}"
        )
    n = len(ok_records)
    if n:
        print(
            f"\n{running_unresp}/{n} queries ({100*running_unresp/n:.0f}%) had >=1 "
            "unresponsive engine reported. Compare the first-third vs last-third rate "
            "below to see whether it climbs with volume (the throttle question):"
        )
        third = max(1, n // 3)
        for label, chunk in [
            ("first third", ok_records[:third]),
            ("middle third", ok_records[third : 2 * third]),
            ("last third", ok_records[2 * third :]),
        ]:
            c = sum(
                1
                for r in chunk
                if [u[0] if isinstance(u, list) else u for u in r.get("unresponsive_engines", [])]
            )
            print(f"  {label:12s}: {c}/{len(chunk)}")
    else:
        print("(no records yet — run poc0b_run.py first)")


# --- 2. per-family predicted coverage ------------------------------------

def _answer_text_for_family(actor_answer_key, question_ids):
    """Map a family's question_ids (03-worker.md §3 naming) onto this repo's
    answer_key groups (poc0b-sample.json), which are coarser (identity/money/
    people/viability_asks/failure/reach) than the full question registry.
    This is a best-effort keyword bridge for the PoC, not the real F1
    question registry."""
    group_map = {
        "one_line": "identity", "type": "identity", "legs": "identity",
        "geography": "identity",
        "funding": "money", "scale_metric": "money", "lifecycle": "money",
        "affected_led": "people", "representation_unit": "people", "founders": "people",
        "tag:viability_note": "viability_asks",
        "tag:failure_note": "failure",
        "contact_route": "reach", "channel:*": "reach",
    }
    groups = {group_map.get(q, None) for q in question_ids}
    groups.discard(None)
    return " ".join(actor_answer_key.get(g, "") for g in groups)


def _plausibly_covers(answer_text, result):
    """Crude lexical overlap check: does the result's title+snippet share a
    distinctive token with the answer-key text? This is a coverage proxy, not
    a correctness check — 03-worker.md §5b: 'coverage here is predicted, not
    proven.'"""
    if not answer_text or answer_text.startswith("not stated") or answer_text.startswith("no "):
        return None  # no ground truth to check against
    hay = (result.get("title", "") + " " + result.get("content", "")).lower()
    # distinctive tokens: words >5 chars, not stopword-ish, from the answer key
    tokens = {t for t in re.findall(r"[a-z]{6,}", answer_text.lower())}
    hits = [t for t in tokens if t in hay]
    return len(hits) >= 1


def per_family_coverage(records, sample):
    print("\n=== 2. Per-family predicted coverage vs answer key ===")
    answer_keys = {a["slug"]: a["answer_key"] for a in sample["actors"]}
    fam_hits = defaultdict(lambda: [0, 0])  # family -> [covered, checkable]

    for r in records:
        if r.get("_error"):
            continue
        slug, fam = r["slug"], r["family"]
        ak = answer_keys.get(slug)
        if not ak:
            continue
        answer_text = _answer_text_for_family(ak, r.get("question_ids", []))
        results = r.get("raw_response", {}).get("results", [])
        covered = False
        checkable = False
        for res in results[:10]:
            v = _plausibly_covers(answer_text, res)
            if v is None:
                continue
            checkable = True
            if v:
                covered = True
                break
        if checkable:
            fam_hits[fam][1] += 1
            if covered:
                fam_hits[fam][0] += 1

    print(f"{'family':10s} {'covered/checkable':20s} {'rate'}")
    for fam, (cov, chk) in sorted(fam_hits.items()):
        rate = f"{100*cov/chk:.0f}%" if chk else "n/a"
        print(f"{fam:10s} {cov}/{chk:<18d} {rate}")
    if not fam_hits:
        print("(no records yet — run poc0b_run.py first)")


# --- 3. set-cover vs top-n -------------------------------------------------

def rrf_fuse_actor(actor_records):
    """actor_records: list of per-family JSON records for ONE actor.
    Returns [(url, rrf_score, coverage_set, title)], rank derived from
    `score`, never list index (03-worker.md §4)."""
    url_score = defaultdict(float)
    url_coverage = defaultdict(set)
    url_title = {}

    for r in actor_records:
        if r.get("_error"):
            continue
        fam = r["family"]
        results = r.get("raw_response", {}).get("results", [])
        # rank derives from `score`, descending; ties broken stably by
        # original order (which SearXNG itself already sorts by score, but
        # we re-sort explicitly here to make the rule an invariant of this
        # code, not an assumption about upstream ordering).
        ranked = sorted(
            results, key=lambda x: x.get("score", 0.0), reverse=True
        )
        for idx, res in enumerate(ranked):
            url = canonical_url(res.get("url"))
            if not url:
                continue
            rank = idx + 1  # rank from score-sorted position, not JSON index
            url_score[url] += 1.0 / (RRF_K + rank)
            url_coverage[url].add(fam)
            url_title.setdefault(url, res.get("title", ""))

    fused = [
        (url, url_score[url], url_coverage[url], url_title[url])
        for url in url_score
    ]
    fused.sort(key=lambda t: t[1], reverse=True)
    return fused


def select_top_n(fused, n):
    return [f[0] for f in fused[:n]]


def select_set_cover(fused, n):
    all_families = set()
    for _, _, cov, _ in fused:
        all_families |= cov
    remaining = dict((u, cov) for u, _, cov, _ in fused)
    scores = dict((u, s) for u, s, _, _ in fused)
    uncovered = set(all_families)
    selected = []
    candidates = list(remaining.items())
    while uncovered and len(selected) < n and candidates:
        best_url, best_gain = None, -1
        for url, cov in candidates:
            gain = len(cov & uncovered)
            if gain > best_gain or (
                gain == best_gain
                and best_url is not None
                and scores.get(url, 0) > scores.get(best_url, 0)
            ):
                best_url, best_gain = url, gain
        if best_gain <= 0:
            break
        selected.append(best_url)
        uncovered -= remaining[best_url]
        candidates = [(u, c) for u, c in candidates if u != best_url]
    # if set cover exhausted uncovered families before reaching n, top up
    # with next-best-by-score urls not already selected (keeps n comparable)
    if len(selected) < n:
        for url, _, _, _ in fused:
            if url not in selected:
                selected.append(url)
            if len(selected) >= n:
                break
    return selected


def set_cover_vs_topn(records, sample, n_values=(3, 5)):
    print("\n=== 3. Set cover vs top-n — the §5b test ===")
    by_actor = defaultdict(list)
    for r in records:
        by_actor[r["slug"]].append(r)

    for n in n_values:
        print(f"\n-- n = {n} --")
        print(f"{'actor':45s} {'top-n coverage':16s} {'set-cover coverage':18s} {'winner'}")
        topn_wins = cover_wins = ties = 0
        for slug, actor_records in by_actor.items():
            fused = rrf_fuse_actor(actor_records)
            if not fused:
                continue
            all_families = set()
            for _, _, cov, _ in fused:
                all_families |= cov

            topn_sel = select_top_n(fused, n)
            cover_sel = select_set_cover(fused, n)

            cov_map = {u: c for u, _, c, _ in fused}
            topn_union = set()
            for u in topn_sel:
                topn_union |= cov_map.get(u, set())
            cover_union = set()
            for u in cover_sel:
                cover_union |= cov_map.get(u, set())

            winner = (
                "set-cover" if len(cover_union) > len(topn_union)
                else "top-n" if len(topn_union) > len(cover_union)
                else "tie"
            )
            if winner == "set-cover":
                cover_wins += 1
            elif winner == "top-n":
                topn_wins += 1
            else:
                ties += 1

            print(
                f"{slug:45s} {len(topn_union)}/{len(all_families):<14d} "
                f"{len(cover_union)}/{len(all_families):<16d} {winner}"
            )
        print(
            f"\nAt n={n}: set-cover beats top-n on {cover_wins} actors, "
            f"top-n beats set-cover on {topn_wins}, tie on {ties}."
        )

    if not by_actor:
        print("(no records yet — run poc0b_run.py first)")


def main():
    sample = load_sample()
    records = load_records()
    if not records:
        print(
            "No responses found in poc0b-responses/. Run poc0b_run.py "
            "(--limit 2 for a dry run) first.",
        )
    unresponsive_curve(records)
    per_family_coverage(records, sample)
    set_cover_vs_topn(records, sample)


if __name__ == "__main__":
    main()
