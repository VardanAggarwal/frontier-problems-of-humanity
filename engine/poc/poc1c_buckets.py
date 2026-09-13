"""PoC-1c -- can question-level retrieval queries be merged into per-bucket
shared queries?

Reuses poc1_retrieval.py's chunking (headings stripped, blank-line paragraph
split, ground-truth label recovered from the H2 the text sat under) and
poc1b_phrasing.py's candidate-phrasing + bootstrap-over-files machinery.
Nothing is re-implemented; both are imported.

Five tasks (see the task prompt for full spec):

  1. Re-examine q4_lifecycle against "Recent updates" and "Status ∪ Recent
     updates" instead of just "Status".
  2. Cross-apply test: within the `reach` bucket (q9,q16) and the `status`
     bucket (q4 settled by task 1, q10, q11), score EVERY candidate from
     EVERY question in the bucket against the bucket's target section(s).
  3. Buckets with no single H2 -- `identity` (q1,2,3,5,6,7,8) and `viability`
     (q12,13). Ground truth is inspected, not assumed.
  4. Problem-side buckets A-E on the 7 existing leaf files.
  5. Headline: 35 retrievals (per-question) vs ~11 (per-bucket) and the AUC
     cost/gain of merging.

Encodes each corpus's passage matrix ONCE and reuses it across every
candidate query in that corpus (actor corpus: 1 encode; leaf corpus: 1
encode) -- consistent with the runtime constraint stated in poc1b.

    python -m poc.poc1c_buckets                  # full run, both corpora
    python -m poc.poc1c_buckets --bootstrap 500   # fewer bootstrap iters
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from embed.model import encode  # noqa: E402
from poc.poc1_retrieval import chunk_file, roc_auc  # noqa: E402
from poc.poc1b_phrasing import (  # noqa: E402
    CANDIDATES as Q1B_CANDIDATES,
    bootstrap_margin,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTORS_DIR = REPO_ROOT / "problems" / "actors"
LEAVES_GLOB = "problems/tier-failure-history/*/*/*.md"


# ---------------------------------------------------------------------------
# Corpus loading (actor corpus + leaf corpus, both via poc1_retrieval's
# generic chunk_file -- it recovers whatever H2 text is present, so it works
# unchanged on leaf files' "A · Classification" etc headings).
# ---------------------------------------------------------------------------

def load_actor_chunks():
    paths = sorted(p for p in ACTORS_DIR.glob("*.md") if not p.name.startswith("_"))
    chunks = []
    for p in paths:
        chunks.extend(chunk_file(p.read_text(encoding="utf-8"), p.stem))
    return chunks


def load_leaf_chunks():
    paths = sorted(
        p for p in REPO_ROOT.glob(LEAVES_GLOB)
        if not p.name.startswith(("00-summary", "_", "_scratch"))
    )
    chunks = []
    for p in paths:
        chunks.extend(chunk_file(p.read_text(encoding="utf-8"), p.stem))
    return chunks, paths


def build_file_index(chunks):
    idx = {}
    for i, c in enumerate(chunks):
        idx.setdefault(c.file, []).append(i)
    return idx


def label_array(chunks, target_headings) -> np.ndarray:
    if isinstance(target_headings, str):
        target_headings = {target_headings}
    else:
        target_headings = set(target_headings)
    return np.array([1 if c.label in target_headings else 0 for c in chunks], dtype=int)


def eligible_files(files_idx, labels):
    return [f for f, idxs in files_idx.items() if labels[idxs].sum() > 0]


def score_query(qtext, all_vecs, labels, files_idx):
    qvec = encode([qtext], role="query")[0]
    scores = all_vecs @ qvec
    elig = eligible_files(files_idx, labels)
    top1 = top3 = 0
    for f in elig:
        idxs = files_idx[f]
        flabels = labels[idxs]
        fscores = scores[idxs]
        ranked = sorted(range(len(idxs)), key=lambda i: -fscores[i])
        if flabels[ranked[0]] == 1:
            top1 += 1
        if any(flabels[i] == 1 for i in ranked[:3]):
            top3 += 1
    auc = roc_auc(labels.tolist(), scores.tolist())
    return {
        "qtext": qtext, "scores": scores, "auc": auc,
        "top1": top1 / len(elig) if elig else None,
        "top3": top3 / len(elig) if elig else None,
        "n_eligible": len(elig),
    }


def fmt(r):
    t1 = f"{r['top1']:.1%}" if r["top1"] is not None else "n/a"
    t3 = f"{r['top3']:.1%}" if r["top3"] is not None else "n/a"
    auc = f"{r['auc']:.3f}" if r["auc"] is not None else "n/a"
    return f"top1={t1:>6} top3={t3:>6} AUC={auc}  n_elig={r['n_eligible']:>3}  | {r['qtext'][:65]!r}"


# ---------------------------------------------------------------------------
# Extra control-only queries, verbatim from engine/02-questions.md, for
# questions poc1b_phrasing.py didn't cover (identity, viability, problem A-E).
# One control string per question -- this PoC is testing whether ONE query
# serves a bucket, not re-sweeping phrasing per question.
# ---------------------------------------------------------------------------

ACTOR_EXTRA = {
    "q1_one_line": "In one concrete sentence: what does this actor actually do?",
    "q2_type": "Org or individual?",
    "q3_legs": ("Which leg(s) -- activism, institution, enterprise (market-payer "
                "only), service (donor-funded, no earned revenue)?"),
    "q5_ecosystem_role": ("Funder, intermediary, capacity-builder, convener, "
                           "field-builder, researcher, operator, or platform?"),
    "q6_affected_led": ("Is leadership drawn from the harmed population (yes), an "
                         "NGO/proxy speaking for them (no), or a mix (partial)?"),
    "q7_representation_unit": ("local-affected, central-org, enterprise, or "
                                "central-at-named-legitimacy-cost?"),
    "q8_geography": "Where do they operate?",
    "q12_viability_note": ("What makes them viable on their leg specifically -- the "
                            "paying customer, whether donor funding survives donor "
                            "exit, affected-led-ness, or authority/reporting-unit "
                            "match?"),
    "q13_failure_note": "Where has this actor deployed effort and had it fail, and why?",
}

# a hand-picked shared-query candidate per untested bucket, plus a couple of
# alternate phrasings so the bucket test isn't a single-shot
IDENTITY_SHARED_CANDIDATES = [
    ("control_q1", ACTOR_EXTRA["q1_one_line"]),
    ("noun_phrase", "what this actor does, org or individual, leg, role, geography"),
    ("statement_shaped",
     "A description of what this organisation or individual does, its type, "
     "leg, ecosystem role and where it operates."),
]

VIABILITY_SHARED_CANDIDATES = [
    ("control_q12", ACTOR_EXTRA["q12_viability_note"]),
    ("noun_phrase", "viability, unit economics, funding continuity, effort that failed"),
]

PROBLEM_QUESTIONS = {
    "A": {
        "target": "A · Classification",
        "questions": {
            "p5_onset": "Is the harm acute, chronic, or latent?",
            "p6_agent": "What triggers the harm -- the agent category?",
            "p7_channel": ("Is the harm direct, structural, cultural-normative, "
                            "or ambient-accidental?"),
            "p8_satisfier_relation": ("Is the satisfier absent, a violator, a "
                                       "pseudo-satisfier, maldistributed, or "
                                       "degraded-quality?"),
        },
    },
    "B": {
        "target": "B · Evidence",
        "questions": {
            "p9_magnitude": "Magnitude with its denominator, dated and sourced.",
            "p10_diff_vuln": ("Who is hit harder and why, and why they can't exit "
                               "or defend?"),
            "p11_measurement_state": "Is the harm counted anywhere?",
        },
    },
    "C": {
        "target": "C · Diagnosis",
        "questions": {
            "p12_mechanism": ("Which of the seven mechanisms does this show -- or "
                               "is it unclassified?"),
            "p13_burden_note": ("Is the visible, reported cause different from "
                                 "the load-bearing one?"),
            "p14_blocker": ("What specifically keeps the known fix from "
                             "happening -- the actual constraint?"),
        },
    },
    "D": {
        "target": "D · Who is working on this",
        "questions": {
            "p15_representation_verdict": ("Is there an actor at a unit that can "
                                            "perceive and act on this specific harm?"),
            "p19_who_working": ("Who is actively working this, on any leg, and "
                                 "what do they specifically do?"),
        },
    },
    "E": {
        "target": "E · Gap",
        "questions": {
            "p16_gap_kind": "Is the gap none, coverage, or representation?",
            "p17_gap_missing_leg": "Which leg(s) have nobody working them at all?",
            "p18_gap_note": "One paragraph on the specific shape of what's missing.",
        },
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    out = []

    def log(*a):
        line = " ".join(str(x) for x in a)
        print(line, flush=True)
        out.append(line)

    # ---------------- Actor corpus ----------------
    log("Loading + chunking actor corpus...")
    achunks = load_actor_chunks()
    afiles_idx = build_file_index(achunks)
    log(f"Actor files: {len(afiles_idx)}   chunks: {len(achunks)}")
    log("Encoding actor passage matrix ONCE...")
    avecs = encode([c.text for c in achunks], role="passage")
    log(f"Actor passage matrix: {avecs.shape}")

    # ===================================================================
    # TASK 1 -- q4_lifecycle against Status / Recent updates / union
    # ===================================================================
    log("\n" + "=" * 70)
    log("TASK 1 -- q4_lifecycle: Status vs Recent updates vs union")
    log("=" * 70)

    q4_candidates = Q1B_CANDIDATES["q4_lifecycle"]["candidates"]
    for target_name, target in [
        ("Status", "Status"),
        ("Recent updates", "Recent updates"),
        ("Status ∪ Recent updates", {"Status", "Recent updates"}),
    ]:
        labels = label_array(achunks, target)
        log(f"\n-- target: {target_name} (n_pos={labels.sum()}) --")
        results = {}
        for axis, qtext in q4_candidates:
            r = score_query(qtext, avecs, labels, afiles_idx)
            results[axis] = r
            log(f"  [{axis:>16}] {fmt(r)}")
        control_r = results["control"]
        best_axis = max((a for a in results if a != "control"),
                         key=lambda a: results[a]["auc"] or -1)
        best_r = results[best_axis]
        margin = (best_r["auc"] or 0) - (control_r["auc"] or 0)
        boot = bootstrap_margin(control_r["scores"], best_r["scores"], labels,
                                 afiles_idx, args.bootstrap, rng)
        log(f"  best-vs-control: {best_axis} margin={margin:+.3f}  "
            f"boot90%CI=[{boot['ci90_lo']:+.3f},{boot['ci90_hi']:+.3f}] "
            f"excludes_zero={boot['excludes_zero']}")

    # ===================================================================
    # TASK 2 -- cross-apply test: reach (q9,q16) and status (q4,q10,q11)
    # ===================================================================
    log("\n" + "=" * 70)
    log("TASK 2 -- cross-apply: reach bucket, status bucket")
    log("=" * 70)

    def cross_apply(bucket_name, question_ids, target):
        labels = label_array(achunks, target)
        log(f"\n-- bucket: {bucket_name}  target={target!r}  n_pos={labels.sum()} --")
        all_scored = []  # (qid, axis, r)
        per_question_best = {}
        for qid in question_ids:
            spec = Q1B_CANDIDATES[qid]
            best_for_q = None
            for axis, qtext in spec["candidates"]:
                r = score_query(qtext, avecs, labels, afiles_idx)
                all_scored.append((qid, axis, r))
                if best_for_q is None or (r["auc"] or -1) > (best_for_q[1]["auc"] or -1):
                    best_for_q = (axis, r)
            per_question_best[qid] = best_for_q
            log(f"  {qid} dedicated best: [{best_for_q[0]}] {fmt(best_for_q[1])}")
        # shared query = best AUC across ALL candidates from ALL questions in bucket
        shared_qid, shared_axis, shared_r = max(all_scored, key=lambda t: t[2]["auc"] or -1)
        log(f"  SHARED (bucket-best, from {shared_qid}/{shared_axis}): {fmt(shared_r)}")
        for qid in question_ids:
            ded_axis, ded_r = per_question_best[qid]
            cost = (ded_r["auc"] or 0) - (shared_r["auc"] or 0)
            log(f"    vs {qid} dedicated ({ded_axis}, AUC={ded_r['auc']:.3f}): "
                f"shared costs {cost:+.3f}")
        return shared_qid, shared_axis, shared_r, per_question_best

    cross_apply("reach", ["q9_contact_route", "q16_channel"], "How to reach them")
    cross_apply("status", ["q10_funding", "q11_scale_metric"], "Status")

    # ===================================================================
    # TASK 3 -- identity and viability (no single H2)
    # ===================================================================
    log("\n" + "=" * 70)
    log("TASK 3 -- identity and viability buckets (no single H2)")
    log("=" * 70)

    log("\n-- content check (grep-style, already done manually; recorded here) --")
    log("  preamble ('What they do.' paragraph) carries: what it does, org/")
    log("  individual framing, founding, sometimes geography and role.")
    log("  '## Scope' bullets are mostly typed edges (funds/board/funded-by) or")
    log("  leaf-specific notes -- heterogeneous, not clean identity prose.")
    log("  Viability/failure vocabulary (unit economics, donor exit, 'failed',")
    log("  'distressed') appears in only ~20/289 and ~10/289 files respectively")
    log("  -- no dedicated H2 exists for it at all in this corpus.")

    for target_name, target in [
        ("preamble only", ""),
        ("Scope only", "Scope"),
        ("preamble ∪ Scope", {"", "Scope"}),
    ]:
        labels = label_array(achunks, target)
        log(f"\n-- identity target: {target_name} (n_pos={labels.sum()}) --")
        for axis, qtext in IDENTITY_SHARED_CANDIDATES:
            r = score_query(qtext, avecs, labels, afiles_idx)
            log(f"  [{axis:>16}] {fmt(r)}")
        for qid, qtext in ACTOR_EXTRA.items():
            if qid.startswith("q1") or qid in ("q2_type", "q3_legs", "q5_ecosystem_role",
                                                "q6_affected_led", "q7_representation_unit",
                                                "q8_geography"):
                r = score_query(qtext, avecs, labels, afiles_idx)
                log(f"  [dedicated:{qid:>24}] {fmt(r)}")

    for target_name, target in [("Status (weak proxy)", "Status")]:
        labels = label_array(achunks, target)
        log(f"\n-- viability target: {target_name} (n_pos={labels.sum()}) --")
        for axis, qtext in VIABILITY_SHARED_CANDIDATES:
            r = score_query(qtext, avecs, labels, afiles_idx)
            log(f"  [{axis:>16}] {fmt(r)}")
        for qid in ("q12_viability_note", "q13_failure_note"):
            r = score_query(ACTOR_EXTRA[qid], avecs, labels, afiles_idx)
            log(f"  [dedicated:{qid:>24}] {fmt(r)}")

    # ===================================================================
    # TASK 4 -- problem side, 7 leaf files, A-E buckets
    # ===================================================================
    log("\n" + "=" * 70)
    log("TASK 4 -- problem side (7 leaf files), A-E buckets")
    log("=" * 70)

    lchunks, lpaths = load_leaf_chunks()
    lfiles_idx = build_file_index(lchunks)
    log(f"Leaf files: {len(lfiles_idx)}   chunks: {len(lchunks)}")
    log("Files: " + ", ".join(p.stem for p in lpaths))
    log("Encoding leaf passage matrix ONCE...")
    lvecs = encode([c.text for c in lchunks], role="passage")
    log(f"Leaf passage matrix: {lvecs.shape}")

    for bucket, spec in PROBLEM_QUESTIONS.items():
        target = spec["target"]
        labels = label_array(lchunks, target)
        log(f"\n-- bucket {bucket} (target={target!r}, n_pos={labels.sum()}) --")
        all_scored = []
        per_q_best = {}
        for qid, qtext in spec["questions"].items():
            r = score_query(qtext, lvecs, labels, lfiles_idx)
            all_scored.append((qid, r))
            per_q_best[qid] = r
            log(f"  {qid}: {fmt(r)}")
        shared_qid, shared_r = max(all_scored, key=lambda t: t[1]["auc"] or -1)
        log(f"  SHARED (bucket-best, from {shared_qid}): {fmt(shared_r)}")
        boot_note = ("bootstrap over 7 files -- CI will be very wide, "
                      "interpret with caution")
        log(f"  ({boot_note})")
        for qid, r in per_q_best.items():
            boot = bootstrap_margin(shared_r["scores"], r["scores"], labels,
                                     lfiles_idx, args.bootstrap, rng)
            log(f"    shared vs {qid} dedicated: diff={((r['auc'] or 0)-(shared_r['auc'] or 0)):+.3f} "
                f"boot90%CI=[{boot['ci90_lo']},{boot['ci90_hi']}] excludes_zero={boot['excludes_zero']}")

    log("\n" + "=" * 70)
    log("DONE")
    log("=" * 70)

    Path(__file__).with_name("poc1c_run_output.txt").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
