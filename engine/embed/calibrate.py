"""Measure the similarity bands on this corpus. Never inherit a threshold.

e5 compresses similarity into a narrow high band — unrelated text lands around
0.7, not around 0.0 — so a cutoff copied from a paper or from MiniLM habit
fails in the way that looks most like working. The same discipline moved
`MIN_SHINGLES` from a guessed 16 to a measured 150 (§11 step 0).

Four measurements, each against labels the corpus already carries:

- **problem x problem** and **actor x actor** all-pairs — the unrelated band,
  and the near-duplicate tail that content dedup will have to cut above.
- **the gate-1 relevance screen**, scored on real labels: the 303 `works_on`
  edges are positives, random (problem, actor) pairs are negatives. This is the
  screen §5 actually runs, measured before anything depends on it.
- **entity resolution**, scored on the 532 aliases: encode the alias string,
  ask for the nearest actor, check it is the right one.

Prints summary statistics only — the point is three numbers, not 41,000.

    python -m embed.calibrate         # defaults are repo-anchored; any cwd
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from . import index, texts                       # noqa: E402
from .guard import add_store_args, open_store    # noqa: E402
from .model import encode                        # noqa: E402

PCTS = (1, 5, 25, 50, 75, 95, 99, 100)


def _np():
    import numpy as np
    return np


def centre(np, blocks, drop: int = 0):
    """Subtract the common context and renormalize: `all-but-the-top`, over the
    populations given together so they share one basis.

    Tested 2026-09-13 and **rejected as a default** — see §8. It does what it
    looks like it should to the numbers (the actor band goes from a 0.10-wide
    strip at 0.841 to a 0.49-wide one centred on zero) and makes every actual
    answer worse. Kept behind `--centre` because the right response to "these
    numbers are uninformative" is a re-measurement, not a memory of one."""
    stacked = np.vstack([b for b in blocks if len(b)])
    mu = stacked.mean(axis=0)
    basis = None
    if drop:
        _, _, basis = np.linalg.svd(stacked - mu, full_matrices=False)
    out = []
    for b in blocks:
        if not len(b):
            out.append(b)
            continue
        x = b - mu
        if drop:
            x = x - (x @ basis[:drop].T) @ basis[:drop]
        out.append(x / np.linalg.norm(x, axis=1, keepdims=True))
    return out


def matrix(conn, kind: str):
    """-> (ids, (n, dim) float32). Row order matches ids."""
    np = _np()
    rows = conn.execute(
        f"SELECT key, embedding FROM {index.VEC_TABLE[kind]} WHERE role = 'query'"
    ).fetchall()
    ids = [r["key"].split(":", 1)[1] for r in rows]
    if not ids:
        return [], np.zeros((0, 0), dtype="float32")
    m = np.vstack([np.frombuffer(r["embedding"], dtype="float32") for r in rows])
    return ids, m


def band(np, values, label: str) -> str:
    if len(values) == 0:
        return f"{label:<34} (no pairs)"
    p = np.percentile(values, PCTS)
    cells = " ".join(f"{v:5.3f}" for v in p)
    return f"{label:<34} n={len(values):>7,}  {cells}"


def header() -> str:
    return f"{'':<34} {'':>10}  " + " ".join(f"{('p%d' % q):>5}" for q in PCTS)


# ---------------------------------------------------------------- all-pairs --
MAX_DENSE = 4000       # 4k x 4k float32 is 64 MB; 50k would be 9.3 GB


def all_pairs(np, m, rng=None, cap: int = MAX_DENSE):
    """Upper triangle of the cosine matrix, self-pairs excluded.

    Dense and n^2, so above `cap` it reports a uniform sample of rows instead of
    silently trying to allocate the whole thing. A percentile band does not need
    every pair; it needs enough of them."""
    if len(m) > cap:
        rng = rng or random.Random(0)
        rows = sorted(rng.sample(range(len(m)), cap))
        m = m[rows]
    sims = m @ m.T
    return sims[np.triu_indices(len(m), k=1)]


def nearest(np, ids, m, top: int = 10, chunk: int = 512):
    """The `top` most similar pairs, row-chunked.

    The dense version allocated the full n^2 matrix AND an int64 argsort of it —
    at 50k entities that is ~28 GB to return ten rows. This keeps one chunk of
    rows in memory and only ever holds `top` candidates."""
    import heapq
    best: list[tuple[float, str, str]] = []
    for lo in range(0, len(m), chunk):
        block = m[lo:lo + chunk] @ m.T
        for r in range(block.shape[0]):
            i = lo + r
            row = block[r]
            row[:i + 1] = -1.0                       # upper triangle only
            for j in np.argpartition(row, -min(top, len(row) - 1))[-top:]:
                item = (float(row[j]), ids[i], ids[int(j)])
                if item[0] < 0:
                    continue
                if len(best) < top:
                    heapq.heappush(best, item)
                elif item[0] > best[0][0]:
                    heapq.heapreplace(best, item)
    return sorted(best, reverse=True)


# ------------------------------------------------------------ gate 1 screen --
def screen(conn, np, rng, negatives: int):
    """Positives are real `works_on` edges; negatives are random non-edges."""
    pids, pm = matrix(conn, "problem")
    aids, am = matrix(conn, "actor")
    pi = {p: n for n, p in enumerate(pids)}
    ai = {a: n for n, a in enumerate(aids)}

    edges = {(r["src_id"], r["dst_id"]) for r in conn.execute(
        "SELECT src_id, dst_id FROM edge WHERE kind = 'works_on' "
        "AND src_kind = 'actor' AND dst_kind = 'problem'")}
    pos = np.array([float(am[ai[a]] @ pm[pi[p]])
                    for a, p in edges if a in ai and p in pi])

    # Bounded: when nearly every pair is an edge there may be no negatives to
    # find, and an unbounded rejection loop hangs with no output.
    neg, tries, budget = [], 0, negatives * 20 + 1000
    while len(neg) < negatives and tries < budget and pids and aids:
        tries += 1
        a, p = rng.choice(aids), rng.choice(pids)
        if (a, p) in edges:
            continue
        neg.append(float(am[ai[a]] @ pm[pi[p]]))
    return pos, np.array(neg)


def sweep(np, pos, neg) -> list[str]:
    """Where to put the gate-1 cutoff, in the units the cutoff is expressed in."""
    lines = [f"{'cutoff':>8} {'recall':>8} {'precision':>10} {'kept':>8}"]
    if len(pos) == 0 or len(neg) == 0:
        return lines + ["  (not enough labelled pairs)"]
    for cut in np.arange(0.70, 0.9601, 0.02):
        tp = int((pos >= cut).sum())
        fp = int((neg >= cut).sum())
        recall = tp / len(pos)
        # Precision here is against THIS negative pool, not the real prior. The
        # honest column is `kept` — what fraction of a sweep survives the cut.
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        kept = (tp + fp) / (len(pos) + len(neg))
        lines.append(f"{cut:8.2f} {recall:8.1%} {prec:10.1%} {kept:8.1%}")
    return lines


def auc(np, pos, neg) -> float:
    """Mann-Whitney: P(a positive outranks a random negative)."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    both = np.concatenate([pos, neg])
    order = both.argsort()
    ranks = np.empty(len(both), dtype="float64")
    ranks[order] = np.arange(1, len(both) + 1)
    # Midranks, or ties are scored as losses and the AUC reads low: two
    # identical distributions would come back 0.0 instead of 0.5.
    sorted_vals = both[order]
    lo = 0
    while lo < len(sorted_vals):
        hi = lo
        while hi + 1 < len(sorted_vals) and sorted_vals[hi + 1] == sorted_vals[lo]:
            hi += 1
        if hi > lo:
            ranks[order[lo:hi + 1]] = (lo + hi + 2) / 2
        lo = hi + 1
    rsum = ranks[:len(pos)].sum()
    return (rsum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


# ------------------------------------------------------- entity resolution --
def resolution(conn, np, corpus: Path, limit: int | None):
    """Encode each alias string cold and ask the index for the actor it names."""
    rows = conn.execute(
        "SELECT a.entity_id, a.alias FROM alias a JOIN actor t ON t.id = a.entity_id "
        "WHERE a.entity_kind = 'actor' AND lower(a.alias) <> lower(t.title) "
        "ORDER BY a.entity_id, a.alias").fetchall()
    if limit:
        rows = rows[:limit]
    if not rows:
        return 0, 0, np.array([]), np.array([]), 0
    vectors = encode([r["alias"] for r in rows], role="query")
    hit_at_1, hit_at_5, hit_sim, miss_sim = 0, 0, [], []
    for row, v in zip(rows, vectors):
        top = index.knn(conn, "actor", v, k=5)
        ids = [i for i, _ in top]
        if not ids:
            continue
        if ids[0] == row["entity_id"]:
            hit_at_1 += 1
            hit_sim.append(top[0][1])
        else:
            miss_sim.append(top[0][1])
        if row["entity_id"] in ids:
            hit_at_5 += 1
    return hit_at_1, hit_at_5, np.array(hit_sim), np.array(miss_sim), len(rows)


# -------------------------------------------------------------------- main --
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_store_args(ap)
    ap.add_argument("--negatives", type=int, default=20000)
    ap.add_argument("--alias-limit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--centre", "--center", dest="centre", action="store_true",
                    help="subtract the corpus mean before comparing (rejected "
                         "as a default 2026-09-13; see §8)")
    ap.add_argument("--drop", type=int, default=0,
                    help="with --centre, also remove the top-N principal "
                         "directions (all-but-the-top)")
    args = ap.parse_args(argv)

    np = _np()
    rng = random.Random(args.seed)
    conn = open_store(args)
    try:
        pids, pm = matrix(conn, "problem")
        aids, am = matrix(conn, "actor")
        sids, sm = matrix(conn, "source")
        print(f"indexed: {len(pids)} problems, {len(aids)} actors, {len(sids)} sources\n")
        if args.centre:
            pm, am, sm = centre(np, [pm, am, sm], drop=args.drop)
            print(f"!! common context subtracted (drop top-{args.drop}); "
                  "cosines below are residual, not comparable to the defaults\n")

        print("== similarity bands ==")
        print(header())
        for label, (ids, m) in (("problem x problem", (pids, pm)),
                                ("actor x actor", (aids, am)),
                                ("source x source", (sids, sm))):
            if len(m):
                print(band(np, all_pairs(np, m, rng), label))

        print("\n== nearest pairs (dedup candidates) ==")
        for label, (ids, m) in (("problem", (pids, pm)), ("actor", (aids, am))):
            if len(m) < 2:
                continue
            print(f"-- {label}")
            for sim, a, b in nearest(np, ids, m, top=8):
                print(f"   {sim:5.3f}  {a}  ~  {b}")

        print("\n== gate 1 relevance screen (works_on edges as labels) ==")
        pos, neg = screen(conn, np, rng, args.negatives)
        print(header())
        print(band(np, pos, "positive (actor works_on problem)"))
        print(band(np, neg, "negative (random pair)"))
        print(f"\nAUC {auc(np, pos, neg):.3f}   "
              f"separation {float(np.mean(pos) - np.mean(neg)):+.3f}\n")
        for line in sweep(np, pos, neg):
            print(line)

        print("\n== entity resolution (aliases as labels) ==")
        at1, at5, hit_sim, miss_sim, total = resolution(
            conn, np, Path(args.corpus), args.alias_limit)
        if total:
            print(f"{total} aliases   rank-1 {at1 / total:.1%}   in top-5 {at5 / total:.1%}")
            print(header())
            print(band(np, hit_sim, "cosine at rank 1, correct"))
            print(band(np, miss_sim, "cosine at rank 1, wrong"))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
