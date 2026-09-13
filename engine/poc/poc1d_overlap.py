"""PoC-1d -- does CHUNK_OVERLAP earn its place before track E integrates
`text/chunk.py`?

`03-worker.md` §7's constants table specifies CHUNK_OVERLAP = 48 (15% of
the 320-token chunk target). Track C shipped `text/chunk.py` with
paragraph-preferred chunking and NO overlap, flagging the gap. This PoC
settles it by measurement, reusing PoC-1c's harness unmodified:

  poc1_retrieval.chunk_file   -- headings-stripped, paragraph-level ground
                                  truth (label = the H2 a paragraph sat under)
  poc1c_buckets.label_array / build_file_index / score_query / fmt
                              -- bucket AUC scoring against precomputed
                                 passage vectors

The one new thing: **the real `chunk()` from `text/chunk.py`** runs on each
ground-truth paragraph block (paragraph-level input, so its own
blank-line-splitting is a no-op unless a single paragraph exceeds
CHUNK_TOKENS, in which case it sentence-splits exactly as it would inside the
worker). `text/chunk.py` has no overlap parameter -- overlap is layered on
top of its output here, as the natural adaptation of a paragraph-preferred
chunker: each chunk after the first in a document gets the last V tokens of
the PREVIOUS chunk's own (non-overlapped) text prepended. This does not
create new chunks (unlike a plain sliding window, which would); it only grows
existing ones -- itself a data point for the "which implementation" question
in §5 of the results.

Two measurements, per §1/§2/§3 of the task:

  1. Section-level bucket AUC, at overlap in {0, 32, 48, 64}, both corpora
     (actor `problems/actors/*.md`, leaf `problems/tier-failure-history/*/*/*.md`).
     Baseline to beat: PoC-1c's numbers (see poc1c-results.md).
  2. The straddle test: real "figure ... denominator/unit/date" instances
     split across a paragraph (= chunk, when unsplit) boundary in this
     corpus. At each V, does the overlap-carrying chunk now contain both
     halves? Direct count, not AUC -- this is what section AUC cannot see.
  3. Cost: total chunks (unchanged by this overlap scheme -- see above),
     total tokens encoded, mean tokens/chunk, and how that erodes
     PASSAGE_TOKEN_CAP=9000's effective chunk budget.

    python -m poc.poc1d_overlap                # full sweep, both corpora
    python -m poc.poc1d_overlap --overlaps 0,48 # subset, quick iteration
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from embed.model import encode, get_encoder  # noqa: E402
from text.chunk import chunk as real_chunk  # noqa: E402
from text.chunk import CHUNK_TOKENS  # noqa: E402
from poc.poc1_retrieval import chunk_file, roc_auc  # noqa: E402
from poc.poc1c_buckets import (  # noqa: E402
    label_array, build_file_index, eligible_files, score_query, fmt,
    load_actor_chunks as _unused_load_actor_chunks,  # not used directly (need raw text too)
    load_leaf_chunks as _unused_load_leaf_chunks,
    ACTORS_DIR, LEAVES_GLOB, REPO_ROOT,
)

try:
    from worker.config import PASSAGE_TOKEN_CAP
except Exception:
    PASSAGE_TOKEN_CAP = 9000

OVERLAPS_DEFAULT = [0, 32, 48, 64]


# ---------------------------------------------------------------------------
# Bucket definitions -- the FINAL bucket set PoC-1c settled on (§5 of
# poc1c-results.md), not the naive proposal it started from.
# ---------------------------------------------------------------------------

ACTOR_BUCKETS = {
    "reach":     ("How to reach them",  "contact email website social media handle channel"),
    "status":    ("Status",             "funding source, scale, latest round or grant, date"),
    "lifecycle": ("Recent updates",     "lifecycle status and as-of date"),
    "needs":     ("What they need",     "What does this actor say it needs (funding, partners, data, policy access)?"),
    "offers":    ("What they can offer","What can it offer (funding, a channel, a service, distribution)?"),
    "identity":  ("",                   "what this actor does, org or individual, leg, role, geography"),
}

LEAF_BUCKETS = {
    "A_classification": ("A · Classification",
                          "Is the harm direct, structural, cultural-normative, or ambient-accidental?"),
    "B_evidence":        ("B · Evidence",
                           "Magnitude with its denominator, dated and sourced."),
    "C_diagnosis":       ("C · Diagnosis",
                           "What specifically keeps the known fix from happening -- the actual constraint?"),
    "D_who_works":       ("D · Who is working on this",
                           "Who is actively working this, on any leg, and what do they specifically do?"),
    "E_gap":             ("E · Gap",
                           "Is the gap none, coverage, or representation?"),
}


@dataclass
class OChunk:
    file: str
    label: str
    text: str
    token_count: int


# ---------------------------------------------------------------------------
# Real-chunk() ground-truth chunking: run text/chunk.py's chunk() on each
# paragraph BLOCK (poc1_retrieval's headings-stripped unit), tag every
# resulting piece with that block's label. Equivalent to running chunk() on
# the whole headings-stripped document, since chunk() splits on blank lines
# first anyway and these blocks are exactly that split.
# ---------------------------------------------------------------------------

def build_base_chunks(paths: list[Path]) -> list[OChunk]:
    out: list[OChunk] = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        blocks = chunk_file(text, p.stem)  # poc1_retrieval.Chunk(file,label,text)
        for b in blocks:
            for sc in real_chunk(b.text, source_id=p.stem, target_tokens=CHUNK_TOKENS):
                out.append(OChunk(file=p.stem, label=b.label, text=sc.text,
                                   token_count=sc.token_count))
    return out


def _tok():
    return get_encoder().tokenizer


def _token_len(text: str) -> int:
    return len(_tok()(text, add_special_tokens=False)["input_ids"])


def _tail_text(text: str, n: int) -> str:
    if n <= 0:
        return ""
    ids = _tok()(text, add_special_tokens=False)["input_ids"]
    if not ids:
        return ""
    tail_ids = ids[-n:]
    return _tok().decode(tail_ids, skip_special_tokens=True).strip()


def apply_overlap(base: list[OChunk], v: int) -> list[OChunk]:
    """Per-document tail-prepend overlap: chunk i (i>0) gets the last `v`
    tokens of chunk i-1's ORIGINAL (non-overlapped) text prepended. Overlap
    is drawn from the original text at every step so it cannot compound
    across a long document."""
    if v <= 0:
        return list(base)
    out: list[OChunk] = []
    prev_file = None
    prev_orig_text = None
    for c in base:
        if c.file != prev_file:
            prev_orig_text = None
        if prev_orig_text:
            tail = _tail_text(prev_orig_text, v)
            new_text = f"{tail} {c.text}".strip() if tail else c.text
        else:
            new_text = c.text
        out.append(OChunk(file=c.file, label=c.label, text=new_text,
                           token_count=_token_len(new_text)))
        prev_file = c.file
        prev_orig_text = c.text
    return out


# ---------------------------------------------------------------------------
# Straddle test
# ---------------------------------------------------------------------------

FIGURE_RE = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s?(?:%|percent|per\s?cent|million|lakh|crore|billion|thousand)?\b",
    re.I,
)
# a "bare" figure match (just digits, no unit) is too noisy on its own (years,
# ordinals, list numbers) -- require either a unit word attached, or that the
# match is at least 2 digits long, to cut obvious false positives.
def _is_real_figure(m: re.Match, text: str) -> bool:
    s = m.group(0)
    digits = re.sub(r"[^\d]", "", s)
    has_unit = bool(re.search(r"%|percent|per\s?cent|million|lakh|crore|billion|thousand", s, re.I))
    return has_unit or len(digits) >= 2


DENOM_HINT_RE = re.compile(
    r"\b(out of|of (?:the|an estimated|approximately|india'?s|all)|per\s|"
    r"percent of|% of|compared to|against a|total of|denominator|of \d)\b",
    re.I,
)

NEAR = 200  # characters counted as "near the end" / "near the start"


@dataclass
class Straddle:
    file: str
    i: int  # index of the figure-bearing chunk
    figure: str
    context_after: str


def find_straddles(base: list[OChunk]) -> list[Straddle]:
    by_file: dict[str, list[OChunk]] = {}
    for idx, c in enumerate(base):
        by_file.setdefault(c.file, []).append(c)

    found: list[Straddle] = []
    for fname, chunks in by_file.items():
        for i in range(len(chunks) - 1):
            cur, nxt = chunks[i], chunks[i + 1]
            if len(cur.text) < NEAR or len(nxt.text) < 10:
                # still test short chunks, just don't restrict the window
                pass
            tail_zone = cur.text[-NEAR:]
            head_zone = nxt.text[:NEAR]
            fig_matches = [m for m in FIGURE_RE.finditer(tail_zone) if _is_real_figure(m, tail_zone)]
            if not fig_matches:
                continue
            last_fig = fig_matches[-1]
            has_denom_word = bool(DENOM_HINT_RE.search(head_zone))
            has_second_fig = any(_is_real_figure(m, head_zone) for m in FIGURE_RE.finditer(head_zone))
            if has_denom_word or has_second_fig:
                found.append(Straddle(file=fname, i=i, figure=last_fig.group(0).strip(),
                                       context_after=head_zone[:80].replace("\n", " ")))
    return found


def straddle_repaired(base: list[OChunk], straddles: list[Straddle], v: int) -> int:
    """A straddle at (file, i) is repaired at overlap v if the figure text
    would land inside the tail carried forward into chunk i+1, i.e. within
    the last v tokens of chunk i's original text."""
    if v <= 0:
        return 0
    by_file: dict[str, list[OChunk]] = {}
    for c in base:
        by_file.setdefault(c.file, []).append(c)
    repaired = 0
    for s in straddles:
        cur = by_file[s.file][s.i]
        tail = _tail_text(cur.text, v)
        if s.figure and s.figure in tail:
            repaired += 1
    return repaired


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_bucket_sweep(log, name, base_by_v, buckets):
    for v, chunks in base_by_v.items():
        log(f"\n-- overlap={v} tokens ({name}) --")
        files_idx = build_file_index(chunks)
        vecs = encode([c.text for c in chunks], role="passage")
        total_tokens = sum(c.token_count for c in chunks)
        mean_tokens = total_tokens / len(chunks) if chunks else 0
        log(f"   chunks={len(chunks)}  total_tokens={total_tokens}  "
            f"mean_tokens/chunk={mean_tokens:.1f}  "
            f"chunks_fitting_in_cap({PASSAGE_TOKEN_CAP})={PASSAGE_TOKEN_CAP/mean_tokens:.1f}")
        for bucket, (target, query) in buckets.items():
            labels = label_array(chunks, target)
            if labels.sum() == 0:
                log(f"   [{bucket:>18}] n_pos=0, skipped")
                continue
            r = score_query(query, vecs, labels, files_idx)
            log(f"   [{bucket:>18}] {fmt(r)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlaps", default=",".join(str(v) for v in OVERLAPS_DEFAULT))
    args = ap.parse_args()
    overlaps = [int(x) for x in args.overlaps.split(",") if x.strip() != ""]

    out = []

    def log(*a):
        line = " ".join(str(x) for x in a)
        print(line, flush=True)
        out.append(line)

    log(f"CHUNK_TOKENS={CHUNK_TOKENS}  overlaps={overlaps}  PASSAGE_TOKEN_CAP={PASSAGE_TOKEN_CAP}")

    # ---------------- Actor corpus ----------------
    actor_paths = sorted(p for p in ACTORS_DIR.glob("*.md") if not p.name.startswith("_"))
    log(f"\nActor corpus: {len(actor_paths)} files")
    actor_base = build_base_chunks(actor_paths)
    log(f"Actor base chunks (overlap=0): {len(actor_base)}")

    actor_by_v = {}
    for v in overlaps:
        actor_by_v[v] = apply_overlap(actor_base, v)

    log("\n" + "=" * 70)
    log("SECTION-LEVEL BUCKET AUC -- actor corpus")
    log("=" * 70)
    run_bucket_sweep(log, "actor", actor_by_v, ACTOR_BUCKETS)

    # ---------------- Leaf corpus ----------------
    leaf_paths = sorted(
        p for p in REPO_ROOT.glob(LEAVES_GLOB)
        if not p.name.startswith(("00-summary", "_", "_scratch"))
    )
    log(f"\nLeaf corpus: {len(leaf_paths)} files: " + ", ".join(p.stem for p in leaf_paths))
    leaf_base = build_base_chunks(leaf_paths)
    log(f"Leaf base chunks (overlap=0): {len(leaf_base)}")

    leaf_by_v = {}
    for v in overlaps:
        leaf_by_v[v] = apply_overlap(leaf_base, v)

    log("\n" + "=" * 70)
    log("SECTION-LEVEL BUCKET AUC -- leaf corpus")
    log("=" * 70)
    run_bucket_sweep(log, "leaf", leaf_by_v, LEAF_BUCKETS)

    # ---------------- Straddle test ----------------
    log("\n" + "=" * 70)
    log("STRADDLE TEST -- figure/denominator split across a chunk boundary")
    log("=" * 70)

    actor_straddles = find_straddles(actor_base)
    leaf_straddles = find_straddles(leaf_base)
    log(f"\nActor corpus: {len(actor_straddles)} candidate straddle instances found")
    for s in actor_straddles[:15]:
        log(f"   {s.file} chunk#{s.i}: figure={s.figure!r}  next_head={s.context_after!r}")
    if len(actor_straddles) > 15:
        log(f"   ... and {len(actor_straddles) - 15} more")

    log(f"\nLeaf corpus: {len(leaf_straddles)} candidate straddle instances found")
    for s in leaf_straddles[:15]:
        log(f"   {s.file} chunk#{s.i}: figure={s.figure!r}  next_head={s.context_after!r}")

    log("\n-- repair rate by overlap setting --")
    total_instances = len(actor_straddles) + len(leaf_straddles)
    log(f"total straddle instances (both corpora): {total_instances}")
    for v in overlaps:
        a_rep = straddle_repaired(actor_base, actor_straddles, v)
        l_rep = straddle_repaired(leaf_base, leaf_straddles, v)
        rep = a_rep + l_rep
        frac = rep / total_instances if total_instances else 0.0
        log(f"   overlap={v:>3}: actor repaired {a_rep}/{len(actor_straddles)}   "
            f"leaf repaired {l_rep}/{len(leaf_straddles)}   "
            f"total {rep}/{total_instances} ({frac:.1%})")

    log("\n" + "=" * 70)
    log("DONE")
    log("=" * 70)

    Path(__file__).with_name("poc1d_run_output.txt").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
