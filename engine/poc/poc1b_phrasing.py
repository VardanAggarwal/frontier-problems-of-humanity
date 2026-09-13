"""PoC-1b — question-phrasing sweep, extending PoC-1.

`04-worker-build-plan.md` §1a / §2 PoC-1 found that two questions targeting the
*identical* corpus section scored AUC 0.59 (q9) vs 0.66 (q16) purely on
wording, and that `ask:need` scored 0.518 — barely above chance on the
cleanest possible corpus. Decision: the e5 `query:` string is a tuned
retrieval parameter, and no threshold/constant decisions get made on it until
phrasing has been swept.

SCOPE: this sweeps the e5 `query:` string used in **stage 5 passage
retrieval only** — the same PoC-1 mechanism (chunk actor files ignoring
headings, encode `query:`/`passage:`, top-1/top-3 hit rate + pooled AUC
against the H2-recovered label). It does NOT touch search-engine query
families (`families.yaml`, stage 1) — that is a separate PoC.

Reuses `poc1_retrieval.py`'s corpus loading, chunking and AUC functions
directly (imported, not re-implemented). The one thing this script does that
poc1_retrieval doesn't: encode the 1,672-chunk passage matrix **once** and
reuse it across every candidate query — only the query vector changes per
candidate, so a ~35-candidate sweep costs one corpus-encode pass, not 35.

    python -m poc.poc1b_phrasing                # full corpus
    python -m poc.poc1b_phrasing --limit 40     # quick iteration
    python -m poc.poc1b_phrasing --bootstrap 500  # bootstrap iterations (default 1000)
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from embed.model import encode  # noqa: E402
from poc.poc1_retrieval import (  # noqa: E402
    load_corpus, roc_auc,
)

# ---------------------------------------------------------------------------
# Candidate phrasings. One control (verbatim PoC-1 wording) + 5 rephrasings
# per question, each tagged with the axis it varies. Axes:
#   control          — PoC-1's original wording, unchanged
#   noun_phrase       — bare noun phrase, no question form
#   statement_shaped  — phrased like the *answer* passage would read, not a question
#   keyword_list      — space-separated keywords, no grammar
#   entity_type_word  — control's question + an explicit "this actor/organisation" noun
#   vocab_overlap     — deliberately reuses the target section's actual surface vocabulary
# ---------------------------------------------------------------------------

CANDIDATES: dict[str, dict] = {
    "q9_contact_route": {
        "target_heading": "How to reach them",
        "candidates": [
            ("control", "How would you actually reach them?"),
            ("noun_phrase", "contact information and follow channels"),
            ("statement_shaped",
             "Follow them on social media, newsletter, or website; email or "
             "DM for contact."),
            ("keyword_list", "contact email website social media handle channel"),
            ("entity_type_word", "How would you actually reach this organisation or individual?"),
            ("vocab_overlap",
             "social media handles, newsletter signup, Telegram or WhatsApp "
             "channel, website contact form"),
        ],
    },
    "q16_channel": {
        "target_heading": "How to reach them",
        "candidates": [
            ("control", "What are its live follow channels?"),
            ("noun_phrase", "live follow channels"),
            ("statement_shaped",
             "Its live follow channels are Instagram, Twitter, a newsletter "
             "and a website."),
            ("keyword_list", "Instagram Twitter newsletter website Telegram follow channel"),
            ("entity_type_word", "What are the actor's live follow channels?"),
            ("vocab_overlap",
             "social media handles and platforms where they post updates"),
        ],
    },
    "q10_funding": {
        "target_heading": "Status",
        "candidates": [
            ("control",
             "Who funds them, at what scale, latest round/grant/budget, and "
             "when — one dated sentence."),
            ("noun_phrase", "funding source, scale, latest round or grant, date"),
            ("statement_shaped",
             "Funded by a named funder at a stated scale, latest round or "
             "grant on a given date."),
            ("keyword_list", "funder grant seed round budget scale amount date"),
            ("entity_type_word", "Who funds this organisation, at what scale?"),
            ("vocab_overlap", "₹ funding grant seed budget amount named funder"),
        ],
    },
    "q11_scale_metric": {
        "target_heading": "Status",
        "candidates": [
            ("control",
             "The one checkable number showing actual reach (members, homes, "
             "users, revenue, units), dated — flag if self-reported."),
            ("noun_phrase", "reach metric, members, users, revenue, dated"),
            ("statement_shaped",
             "Reaches a stated number of members, users or homes as of a "
             "given date, self-reported."),
            ("keyword_list", "members users revenue units reach number dated self-reported"),
            ("entity_type_word",
             "What is the one checkable number showing this actor's actual reach?"),
            ("vocab_overlap",
             "number of members, households, users served, revenue figure"),
        ],
    },
    "q4_lifecycle": {
        "target_heading": "Status",
        "candidates": [
            ("control",
             "Operating, scaling, distressed, dormant, acquired, shut, or "
             "won-and-dissolved — and current as of what date?"),
            ("noun_phrase", "lifecycle status and as-of date"),
            ("statement_shaped",
             "Currently operating and scaling, as of a stated date."),
            ("keyword_list",
             "status operating scaling distressed dormant shut acquired "
             "dissolved date"),
            ("entity_type_word", "What is this actor's current lifecycle status?"),
            ("vocab_overlap",
             "operating scaling distressed dormant acquired shut dissolved "
             "current as of"),
        ],
    },
    "q15_ask_offer": {
        "target_heading": "What they can offer",
        "candidates": [
            ("control", "What can it offer (funding, a channel, a service, distribution)?"),
            ("noun_phrase", "what they can offer: funding, channel, service, distribution"),
            ("statement_shaped",
             "Offers funding, a channel, a service, or distribution to partners."),
            ("keyword_list", "offer funding channel service distribution partnership"),
            ("entity_type_word", "What can this actor offer other actors?"),
            ("vocab_overlap",
             "can provide funding, platform access, service delivery, "
             "distribution network"),
        ],
    },
    "q14_ask_need": {
        "target_heading": "What they need",
        "candidates": [
            ("control",
             "What does this actor say it needs (funding, partners, data, "
             "policy access)?"),
            ("noun_phrase", "what they need: funding, partners, data, policy access"),
            ("statement_shaped",
             "Needs funding, partners, data, or policy access to scale."),
            ("keyword_list", "need funding partners data policy access requirement"),
            ("entity_type_word", "What does this organisation say it needs?"),
            ("vocab_overlap",
             "requires funding, seeks partners, needs data or policy access"),
        ],
    },
}


def build_label_array(chunks, target_heading) -> np.ndarray:
    return np.array([1 if c.label == target_heading else 0 for c in chunks], dtype=int)


def build_file_index(chunks) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = {}
    for i, c in enumerate(chunks):
        idx.setdefault(c.file, []).append(i)
    return idx


def eligible_files(files_idx: dict[str, list[int]], labels: np.ndarray) -> list[str]:
    out = []
    for fname, idxs in files_idx.items():
        if labels[idxs].sum() > 0:
            out.append(fname)
    return out


def score_candidate(query_vec: np.ndarray, all_vecs: np.ndarray, labels: np.ndarray,
                     files_idx: dict[str, list[int]]) -> dict:
    scores = all_vecs @ query_vec  # (N,) cosine, since both L2-normalized

    elig = eligible_files(files_idx, labels)
    top1 = top3 = 0
    for fname in elig:
        idxs = files_idx[fname]
        flabels = labels[idxs]
        fscores = scores[idxs]
        ranked = sorted(range(len(idxs)), key=lambda i: -fscores[i])
        if flabels[ranked[0]] == 1:
            top1 += 1
        if any(flabels[i] == 1 for i in ranked[:3]):
            top3 += 1

    auc = roc_auc(labels.tolist(), scores.tolist())
    return {
        "scores": scores,
        "top1": top1 / len(elig) if elig else None,
        "top3": top3 / len(elig) if elig else None,
        "auc": auc,
        "n_eligible": len(elig),
    }


def bootstrap_margin(control_scores: np.ndarray, cand_scores: np.ndarray,
                      labels: np.ndarray, files_idx: dict[str, list[int]],
                      n_boot: int, rng: random.Random) -> dict:
    """Resample FILES with replacement (not chunks) so within-file correlation
    is respected, recompute pooled AUC for control and candidate on the same
    resample, and track the distribution of (candidate_auc - control_auc).
    Returns the observed margin, the bootstrap mean/SD of the diff, and a
    90%-CI-excludes-zero verdict."""
    fnames = list(files_idx.keys())
    diffs = []
    for _ in range(n_boot):
        sample = [rng.choice(fnames) for _ in fnames]
        idxs: list[int] = []
        for fname in sample:
            idxs.extend(files_idx[fname])
        idxs_arr = np.array(idxs)
        lab = labels[idxs_arr]
        if lab.sum() == 0 or lab.sum() == len(lab):
            continue  # AUC undefined on this resample, skip
        auc_c = roc_auc(lab.tolist(), control_scores[idxs_arr].tolist())
        auc_x = roc_auc(lab.tolist(), cand_scores[idxs_arr].tolist())
        if auc_c is None or auc_x is None:
            continue
        diffs.append(auc_x - auc_c)

    diffs.sort()
    n = len(diffs)
    lo = diffs[int(0.05 * n)] if n else None
    hi = diffs[int(0.95 * n) - 1] if n else None
    mean = sum(diffs) / n if n else None
    return {
        "n_boot_used": n,
        "ci90_lo": lo,
        "ci90_hi": hi,
        "mean_diff": mean,
        "excludes_zero": (lo is not None and hi is not None and (lo > 0 or hi < 0)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    print("Loading + chunking corpus...", flush=True)
    chunks = load_corpus(args.limit)
    files_idx = build_file_index(chunks)
    print(f"Files: {len(files_idx)}   Chunks: {len(chunks)}", flush=True)

    print("Encoding passage matrix ONCE (this is the ~6min step)...", flush=True)
    texts = [c.text for c in chunks]
    all_vecs = encode(texts, role="passage")
    print(f"Passage matrix: {all_vecs.shape}", flush=True)

    rng = random.Random(args.seed)

    for group_name, spec in CANDIDATES.items():
        target = spec["target_heading"]
        labels = build_label_array(chunks, target)
        print(f"\n{'='*70}")
        print(f"## {group_name}  (target heading: {target!r})")
        print(f"{'='*70}")

        control_scores = None
        results = []
        for axis, qtext in spec["candidates"]:
            qvec = encode([qtext], role="query")[0]
            r = score_candidate(qvec, all_vecs, labels, files_idx)
            results.append((axis, qtext, r))
            if axis == "control":
                control_scores = r["scores"]
            t1 = f"{r['top1']:.1%}" if r["top1"] is not None else "n/a"
            t3 = f"{r['top3']:.1%}" if r["top3"] is not None else "n/a"
            auc = f"{r['auc']:.3f}" if r["auc"] is not None else "n/a"
            print(f"  [{axis:>16}] top1={t1:>6}  top3={t3:>6}  AUC={auc}"
                  f"  n_elig={r['n_eligible']}  | {qtext[:70]!r}")

        # winner = highest AUC among non-control candidates
        non_control = [(axis, qtext, r) for axis, qtext, r in results if axis != "control"]
        winner = max(non_control, key=lambda row: row[2]["auc"] or -1)
        control_r = [r for axis, _, r in results if axis == "control"][0]
        margin = (winner[2]["auc"] or 0) - (control_r["auc"] or 0)

        print(f"\n  Winner: {winner[0]} (AUC {winner[2]['auc']:.3f}) vs control "
              f"(AUC {control_r['auc']:.3f}) -> margin {margin:+.3f}")

        boot = bootstrap_margin(control_scores, winner[2]["scores"], labels,
                                 files_idx, args.bootstrap, rng)
        print(f"  Bootstrap ({boot['n_boot_used']} resamples over files): "
              f"mean diff={boot['mean_diff']:+.3f}  90% CI=[{boot['ci90_lo']:+.3f}, "
              f"{boot['ci90_hi']:+.3f}]  excludes_zero={boot['excludes_zero']}")


if __name__ == "__main__":
    main()
