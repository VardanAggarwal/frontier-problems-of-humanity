"""PoC-1 — e5 can find the right paragraph.

`04-worker-build-plan.md` §2 PoC-1, testing the claim `03-worker.md` §7 makes
about gate ordering: *"No such label exists for 'does this chunk answer this
question.' Producing one means hand-annotating chunks, which is the work this
engine exists to avoid."* That is true of arbitrary web pages and false of
this corpus — the actor files' own H2 headings are a question-labelled chunk
set, already written, at annotation cost zero:

    ## How to reach them     -> contact_route, channel:*
    ## Status                -> funding, scale_metric, lifecycle
    ## What they can offer   -> ask:offer:*
    ## What they need        -> ask:need:*

The test: chunk each actor file **ignoring its headings**, encode each
question group's real wording (from `02-questions.md`) as `query: ` and every
chunk as `passage: ` (the repo's own encoder, `embed/model.py` — no second
model path), and ask whether the top-3 chunks by cosine came from the section
that heading actually labels.

Chunking choice (stated per the plan's requirement): **headings are stripped
out of the text entirely**, then the remaining body is split into chunks on
blank-line paragraph boundaries alone — the same split that would apply if
the `##` lines were never there. In practice this recovers ~one chunk per
section, because these files already write one paragraph per section; that is
a fact about this corpus's own writing style, not something the chunker
enforces. A chunk's ground-truth label is whichever H2 the text sat under
*before* stripping — the label is recovered from position, never used to
decide where a chunk boundary falls.

Per-file, per-question: cosine top-1/top-3 hit rate (did the top-1 / any of
the top-3 chunks in *that file* carry the target label). Pooled across every
file's chunks, per question: ROC AUC over the chunk-level binary label. Both
are reported, plus the fully pooled overall figures.

No network: the model must already be cached (`~/.cache/huggingface/hub`) or
this script stops rather than downloading ~470 MB silently.

    python -m poc.poc1_retrieval                # full corpus
    python -m poc.poc1_retrieval --limit 40      # quick iteration
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from embed.model import encode  # noqa: E402  (repo's own encoder, no second path)

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTORS_DIR = REPO_ROOT / "problems" / "actors"

# question group -> (target H2 heading text, [(question_id, question text), ...])
# Wording copied verbatim from engine/02-questions.md's `actor` table.
QUESTION_GROUPS: dict[str, dict] = {
    "contact_route/channel:*": {
        "target_heading": "How to reach them",
        "questions": [
            ("q9_contact_route", "How would you actually reach them?"),
            ("q16_channel", "What are its live follow channels?"),
        ],
    },
    "funding/scale_metric/lifecycle": {
        "target_heading": "Status",
        "questions": [
            ("q10_funding",
             "Who funds them, at what scale, latest round/grant/budget, and "
             "when — one dated sentence."),
            ("q11_scale_metric",
             "The one checkable number showing actual reach (members, homes, "
             "users, revenue, units), dated — flag if self-reported."),
            ("q4_lifecycle",
             "Operating, scaling, distressed, dormant, acquired, shut, or "
             "won-and-dissolved — and current as of what date?"),
        ],
    },
    "ask:offer:*": {
        "target_heading": "What they can offer",
        "questions": [
            ("q15_ask_offer",
             "What can it offer (funding, a channel, a service, distribution)?"),
        ],
    },
    "ask:need:*": {
        "target_heading": "What they need",
        "questions": [
            ("q14_ask_need",
             "What does this actor say it needs (funding, partners, data, "
             "policy access)?"),
        ],
    },
}

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
_H_LINE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    file: str
    label: str          # the H2 heading text this chunk sat under, or "" (preamble)
    text: str


def strip_frontmatter(text: str) -> str:
    """No-op on this corpus (no actor file carries a `---` YAML block — checked
    directly: zero of 289 files), kept so the script doesn't silently mis-chunk
    if that ever changes."""
    m = _FRONTMATTER.match(text)
    return text[m.end():] if m else text


def chunk_file(text: str, file_label: str) -> list[Chunk]:
    """Strip heading lines, then split into chunks on blank-line paragraph
    boundaries — headings are never consulted to decide where a chunk starts
    or ends. Ground truth is recovered separately: the label carried on each
    chunk is whichever H2 the source lines sat under *before* the heading line
    was dropped, tracked positionally as we walk the file."""
    lines = strip_frontmatter(text).splitlines()

    current_h2 = ""       # most recent ## heading text seen (top-level H1 title
                           # and any H3s do not count as a labelled section)
    blocks: list[tuple[str, list[str]]] = []   # (label, [prose lines])
    buf: list[str] = []

    def flush():
        if buf:
            blocks.append((current_h2, list(buf)))
            buf.clear()

    for line in lines:
        m = _H_LINE.match(line)
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            if level == 2:
                current_h2 = title
            # heading line itself is dropped — not carried into any chunk's text
            continue
        if line.strip() == "":
            flush()
        else:
            buf.append(line)
    flush()

    chunks = []
    for label, prose_lines in blocks:
        joined = " ".join(l.strip() for l in prose_lines).strip()
        if len(joined.split()) < 4:      # drop stray single-word/rule fragments
            continue
        chunks.append(Chunk(file=file_label, label=label, text=joined))
    return chunks


def load_corpus(limit: int | None) -> list[Chunk]:
    paths = sorted(
        p for p in ACTORS_DIR.glob("*.md")
        if not p.name.startswith("_")   # _template, _crawl-state, _excluded.yaml etc.
    )
    if limit:
        paths = paths[:limit]

    all_chunks: list[Chunk] = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        all_chunks.extend(chunk_file(text, p.stem))
    return all_chunks


def per_file(chunks: list[Chunk]) -> dict[str, list[Chunk]]:
    out: dict[str, list[Chunk]] = {}
    for c in chunks:
        out.setdefault(c.file, []).append(c)
    return out


def roc_auc(labels: list[int], scores: list[float]) -> float | None:
    """Plain rank-based AUC (Mann-Whitney U form) — no sklearn dependency,
    matches roc_auc_score exactly for the binary case. Returns None if one
    class is absent (AUC undefined)."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    sum_ranks_pos = sum(ranks[i] for i in range(len(labels)) if labels[i] == 1)
    u = sum_ranks_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def evaluate_question(question_text: str, target_heading: str,
                       chunks_by_file: dict[str, list[Chunk]]) -> dict:
    query_vec = encode([question_text], role="query")[0]

    top1_hits = top3_hits = eligible_files = 0
    pooled_labels: list[int] = []
    pooled_scores: list[float] = []

    for fname, fchunks in chunks_by_file.items():
        labels = [1 if c.label == target_heading else 0 for c in fchunks]
        if sum(labels) == 0 or sum(labels) == len(labels):
            # need both a positive and a negative chunk in this file to test
            # discrimination at all; still contributes to the pooled AUC below
            # only when it has a positive AND at least one other file supplies
            # negatives (handled globally, not here)
            pass
        vecs = encode([c.text for c in fchunks], role="passage")
        scores = [float(query_vec @ v) for v in vecs]

        pooled_labels.extend(labels)
        pooled_scores.extend(scores)

        if sum(labels) == 0:
            continue  # this file has no target section at all — nothing to hit
        eligible_files += 1
        ranked = sorted(range(len(fchunks)), key=lambda i: -scores[i])
        if labels[ranked[0]] == 1:
            top1_hits += 1
        if any(labels[i] == 1 for i in ranked[:3]):
            top3_hits += 1

    return {
        "question": question_text,
        "eligible_files": eligible_files,
        "top1_hit_rate": top1_hits / eligible_files if eligible_files else None,
        "top3_hit_rate": top3_hits / eligible_files if eligible_files else None,
        "auc": roc_auc(pooled_labels, pooled_scores),
        "pooled_labels": pooled_labels,
        "pooled_scores": pooled_scores,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                     help="cap the number of actor files read, for quick iteration")
    args = ap.parse_args()

    chunks = load_corpus(args.limit)
    files = per_file(chunks)
    print(f"Files read: {len(files)}   Chunks: {len(chunks)}\n")

    heading_counts: dict[str, int] = {}
    for c in chunks:
        heading_counts[c.label or "(preamble/no-H2)"] = \
            heading_counts.get(c.label or "(preamble/no-H2)", 0) + 1
    print("Chunk counts by heading:")
    for label, n in sorted(heading_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {label!r}: {n}")
    print()

    all_pooled_labels: list[int] = []
    all_pooled_scores: list[float] = []
    group_rows = []

    for group_name, spec in QUESTION_GROUPS.items():
        target = spec["target_heading"]
        print(f"## {group_name}  (target heading: {target!r})")
        for qid, qtext in spec["questions"]:
            r = evaluate_question(qtext, target, files)
            group_rows.append((group_name, qid, qtext, r))
            all_pooled_labels.extend(r["pooled_labels"])
            all_pooled_scores.extend(r["pooled_scores"])
            t1 = f"{r['top1_hit_rate']:.1%}" if r["top1_hit_rate"] is not None else "n/a"
            t3 = f"{r['top3_hit_rate']:.1%}" if r["top3_hit_rate"] is not None else "n/a"
            auc = f"{r['auc']:.3f}" if r["auc"] is not None else "n/a"
            print(f"  [{qid}] top1={t1}  top3={t3}  AUC={auc}  "
                  f"(n_files_with_target_section={r['eligible_files']})")
        print()

    overall_auc = roc_auc(all_pooled_labels, all_pooled_scores)
    n_files_total = sum(1 for r in (row[3] for row in group_rows) if r["eligible_files"])
    print("## Overall (pooled across all question groups)")
    print(f"  pooled AUC = {overall_auc:.3f}" if overall_auc is not None else "  n/a")
    weighted_top1 = [row[3]["top1_hit_rate"] for row in group_rows
                      if row[3]["top1_hit_rate"] is not None]
    weighted_top3 = [row[3]["top3_hit_rate"] for row in group_rows
                      if row[3]["top3_hit_rate"] is not None]
    if weighted_top1:
        print(f"  mean top1 hit rate across questions = "
              f"{sum(weighted_top1) / len(weighted_top1):.1%}")
    if weighted_top3:
        print(f"  mean top3 hit rate across questions = "
              f"{sum(weighted_top3) / len(weighted_top3):.1%}")


if __name__ == "__main__":
    main()
