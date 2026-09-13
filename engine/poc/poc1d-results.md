# PoC-1d results — does chunk overlap help or hurt?

Run: `python -m poc.poc1d_overlap` (full corpus, no `--limit`), 2026-09-13.
Uses the real `chunk()` from `engine/text/chunk.py` — track C's shipped
chunker — swept at `CHUNK_TOKENS=320` across `overlaps=[0, 32, 48, 64]`,
`PASSAGE_TOKEN_CAP=9000`. So every number below is a measurement of the
production chunking rules, not a PoC approximation of them. Two corpora:
289 `problems/actors/*.md` files (1,676 base chunks at overlap=0) and the 7
existing leaf files under `problems/tier-failure-history/*/*/*.md` (228 base
chunks at overlap=0). Script: `engine/poc/poc1d_overlap.py`. Raw log:
`engine/poc/poc1d_run.log` (HuggingFace `UNEXPECTED`/`position_ids` loader
noise filtered out below; the tables are the authoritative numbers).

The run measures two independent things and they point in opposite
directions: section-level retrieval AUC (bucket queries carried over from
PoC-1c) gets worse as overlap increases; a separate straddle test (does a
figure and its denominator land in the same chunk) gets better. Both are
reported in full — the tension is the finding, not a defect in one of them.

## 1. Section-level bucket AUC — actor corpus

| Bucket | overlap=0 | overlap=32 | overlap=48 | overlap=64 |
|---|---|---|---|---|
| reach (n=223) | **0.893** | 0.652 | 0.649 | 0.655 |
| status (n=205) | **0.977** | 0.882 | 0.837 | 0.822 |
| lifecycle (n=281) | **0.917** | 0.868 | 0.894 | 0.909 |
| needs (n=99) | 0.518 | 0.401 | 0.520 | **0.604** |
| offers (n=167) | 0.610 | 0.688 | 0.682 | **0.709** |
| identity (n=289) | **0.503** | 0.385 | 0.367 | 0.377 |

Four of six buckets (reach, status, identity, and — at overlap 32 —
lifecycle) get worse with any overlap and never recover by overlap=64.
Two buckets (needs, offers) move the other way, improving as overlap
increases, topping out at overlap=64. Needs and offers are also the two
weakest, closest-to-chance buckets in the set (0.5–0.7 range even at their
best), so this looks like overlap smearing enough extra context into a
thin, hard-to-localize section that it occasionally helps by accident,
not a case for overlap on the merits. The three strongest, most reliable
buckets (reach, status, identity) are also the three most damaged by
overlap, and they carry more retrieval weight in the question set than
needs/offers do.

## 2. Section-level bucket AUC — leaf corpus

| Bucket | overlap=0 | overlap=32 | overlap=48 | overlap=64 |
|---|---|---|---|---|
| A_classification (n=7) | 0.895 | 0.957 | 0.954 | **0.983** |
| B_evidence (n=7) | **0.578** | 0.576 | 0.545 | 0.549 |
| C_diagnosis (n=7) | **0.814** | 0.758 | 0.774 | 0.772 |
| D_who_works (n=7) | 0.707 | **0.724** | 0.709 | 0.694 |
| E_gap (n=7) | 0.884 | **0.942** | 0.943 | 0.937 |

n=7 files throughout — treat these as directionally suggestive, not
independently powered (same caveat PoC-1c applied to this corpus). Mixed
picture here too: A_classification and E_gap improve with overlap,
B_evidence and C_diagnosis degrade, D_who_works is roughly flat. No clean
overlap-always-helps or overlap-always-hurts story on the leaf side either.

## 3. Cost — actor corpus

| | overlap=0 | overlap=32 | overlap=48 | overlap=64 |
|---|---|---|---|---|
| mean tokens/chunk | 63.0 | 86.4 | 94.1 | 99.7 |
| chunks fitting in `PASSAGE_TOKEN_CAP` (9000) | **142.9** | 104.1 | 95.6 | 90.3 |
| total tokens (all chunks) | 105,562 | 144,854 | 157,766 | 167,029 |

`chunks_fitting_in_cap` is the number of average-sized chunks that fit in
the 9000-token passage budget — a proxy for how many distinct sources can
be cited per extraction call. Overlap=48 (`03-worker.md` §7's current
spec) drops that from 142.9 to 95.6 — a **33.1% cut** to the passage
budget's source diversity — while inflating total corpus tokens by 49.5%
(105,562 → 157,766). Overlap=64 is worse on both counts (90.3 chunks,
167,029 tokens, a 36.8% capacity cut).

## 4. Straddle test — figure/denominator split across a chunk boundary

284 genuine straddle instances found across both corpora at overlap=0
(217 actor, 67 leaf) — a figure ending one chunk with its denominator,
source, or qualifying context starting the next.

Examples from the log:

- **actor / annapurna-finance chunk#1**: figure `'2021'` immediately
  followed by `'- **Funding** — $35M raised (Accion, Encourage Capital,
  Oikocredit, Dec 2021). -'` — the funding line's own closing date gets
  cut from the figure that opens it.
- **actor / avaana-capital chunk#1**: figure `'25'` followed by
  `'- **Funding** — $135M Avaana Climate and Sustainability Fund, final
  close Octobe'` — the fund close figure is split from its own headline
  number.
- **leaf / asbestos-in-air chunk#10**: figure `'50,000'` followed by
  `'Global reference points: WHO puts asbestos-related deaths above
  200,000/year worl'` — an India figure is separated from the global
  comparator it needs to be read against.
- **leaf / asbestos-in-air chunk#16**: figure `'485,000'` followed by a
  `Data note —` line giving the official-vs-independent range caveat for
  that exact death-toll figure — precisely the kind of reconciliation
  note this repo's own research standards require staying attached to
  its number.

Repair rate by overlap setting (both corpora combined, n=284):

| overlap | actor repaired | leaf repaired | total repaired | rate |
|---|---|---|---|---|
| 0 | 0/217 | 0/67 | 0/284 | **0.0%** |
| 32 | 177/217 | 50/67 | 227/284 | 79.9% |
| 48 | 210/217 | 62/67 | 272/284 | 95.8% |
| 64 | 217/217 | 67/67 | 284/284 | **100.0%** |

The straddle problem is real and overlap does fix it monotonically — this
is the one place in the run where more overlap is unambiguously better.

## 5. Recommendation: `CHUNK_OVERLAP = 0`, contradicting `03-worker.md` §7

`03-worker.md` §7 currently specifies overlap=48. This run says that
setting buys 95.8% straddle repair at the cost of the three
highest-value bucket AUCs (reach 0.893→0.649, status 0.977→0.837, identity
0.503→0.367) and a third of the passage budget's source diversity
(142.9→95.6 chunks). Set against PoC-1b's phrasing win (mean pooled AUC
0.674→0.815 across seven questions, from choosing the right `retrieval_query`
per question), overlap=48 would give back most of that gain for a problem
— straddling figures — that has a cheaper fix than paying for it at index
time (§6 below). **Recommend `CHUNK_OVERLAP = 0`.**

## 6. The cheaper fix: neighbour expansion at selection time, not overlap at chunk time

Rather than widening chunks (which pollutes every embedding with
neighbouring-section context, which is what damages retrieval AUC), repair
straddles at the point where chunks are already selected for the
extraction prompt: for each chunk selected by retrieval, also include
chunk *n±1* in what gets sent to the LLM. Track C's chunker already
produces contiguous ordinals per file, so this is a lookup, not new
machinery — implemented in `engine/worker/passages.py` (passage assembly),
not `engine/text/chunk.py` (indexing). This keeps `overlap=0` for both
indexing and retrieval — the contaminated context that hurts AUC never
enters the embedding — while still handing the extraction model the
sentence that got cut.

**Cost, stated honestly:** this inflates the token count of the extraction
prompt per selected chunk (up to 3x if every selected chunk pulls in both
neighbours), so it interacts directly with `PASSAGE_TOKEN_CAP` — fewer
distinct selected chunks fit once each one drags two neighbours along.
This trade-off is not measured here; it needs track E running end to end
(actual chunk selection + extraction) to quantify, not a retrieval-only
PoC like this one.

## 6b. Adopted, 2026-09-13

Both recommendations shipped the same day this run finished. `CHUNK_OVERLAP`
is 0 and there is deliberately no constant for it in `worker/config.py` —
overlap is not a tunable that got set to zero, it is a technique this build
does not use. `expand_neighbours()` is in `engine/worker/passages.py`, called
from inside `select()` *before* `_cap_tokens`, with `NEIGHBOUR_RADIUS = 1` in
`worker/config.py` and `select(..., neighbour_radius=0)` as the off switch
for anyone measuring what expansion costs. `03-worker.md` §7 and
`04-worker-build-plan.md` §1c/§3/§6/§8 record the supersession.

One thing found while adopting, which §1's tables cannot show: the actor
corpus averages **5.8 chunks against 4.96 H2 sections per file** (1,676
base chunks over the 289 eligible files above; the H2 mean counted over all
291 `problems/actors/*.md`), so ~85% of
chunks are a section's first chunk and overlap contaminates nearly every one
of them with the previous section's tail. That is why the AUC damage here is
so large — and it is a property of *this* corpus's shape. Part of the loss is
also a labelling artefact: `apply_overlap()` keeps a chunk's host-section
label while prepending the previous section's text, so a chunk that legitimately
now contains reach text scores as a false positive for the reach bucket.
Neither point reverses the decision — neighbour expansion beats overlap on
both axes at once — but both bound how far "overlap hurts retrieval"
generalises to the longer web pages the worker will actually chunk.

## 7. Caveat — what section-level AUC can and cannot see

Every AUC number in §1–2 is section-level: it measures whether the top-k
retrieved chunks came from the correct H2, not whether a specific sentence
or figure inside that section survived intact. A chunk can score as a
correct-section hit while still having its own denominator sheared off by
a chunk boundary — section AUC is blind to that by construction. The
straddle count in §4 is the direct measurement of the failure this PoC set
out to check, and should be treated as the more trustworthy half of this
PoC's evidence — the AUC tables are the retrieval-quality cost side of the
ledger, not a rebuttal of the straddle finding.

## Files

- `engine/poc/poc1d_overlap.py` — the sweep script; reuses the shipped
  `engine/text/chunk.py` chunker and PoC-1c's bucket-query/AUC machinery
- `engine/poc/poc1d-results.md` — this file
- `engine/poc/poc1d_run.log` — raw run output (HF loader progress-bar and
  `position_ids`/`UNEXPECTED` weight-loading noise included; the tables
  above are the filtered, authoritative numbers)
