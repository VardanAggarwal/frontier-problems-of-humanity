# PoC-1 results — e5 can find the right paragraph

Run: `python -m poc.poc1_retrieval` (full corpus, no `--limit`), 2026-09-13.
Encoder: `intfloat/multilingual-e5-small`, already cached locally
(`~/.cache/huggingface/hub/models--intfloat--multilingual-e5-small`) — no
download, run offline (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`).

Corpus: 289 `problems/actors/*.md` files (all non-`_`-prefixed files), 1,672
chunks total.

## Chunking used

**Headings are stripped out of the text entirely**, then the remaining body
is split into chunks on blank-line paragraph boundaries alone — the same
split that would result if the `##` lines were never there. A chunk's
ground-truth label (which H2 it "belongs to") is recovered separately, by
tracking the most recent H2 seen while walking the file *before* the heading
line is dropped — the label is never used to decide where a chunk boundary
falls.

No YAML frontmatter exists in this corpus to strip (checked directly: 0 of
289 actor files carry a `---` block), so that step of the plan is a no-op
here; the code still calls a `strip_frontmatter()` that is a no-op if none is
found, in case that changes later.

In practice this produces close to one chunk per H2 section, because these
files already write one paragraph (or one bullet block) per section — a fact
about the corpus's writing style, not something the chunker enforces. Chunk
counts by heading, full corpus:

| Heading | Chunks |
|---|---|
| Recent updates | 394 |
| Scope | 292 |
| (preamble / no H2, i.e. the lead "What they do" paragraph) | 291 |
| How to reach them | 224 |
| Status | 205 |
| What they can offer | 167 |
| What they need | 99 |

## Metric

Per file, per question: **top-1** and **top-3 hit rate** — did the top-1 /
any of the top-3 chunks *within that file* (cosine, `query:` vs `passage:`)
carry the target label. Only files that actually contain the target section
are counted (a file missing "What they need" has nothing to hit). Per
question: **ROC AUC**, computed on the chunk-level binary label pooled across
every file's chunks (rank-based Mann-Whitney U form, no sklearn dependency).

## Results (full corpus, 289 files / 1,672 chunks)

| Group | Question | n files | top-1 | top-3 | AUC |
|---|---|---|---|---|---|
| contact_route/channel:* | q9 "How would you actually reach them?" | 223 | 22.0% | 55.2% | 0.592 |
| contact_route/channel:* | q16 "What are its live follow channels?" | 223 | 32.7% | 67.7% | 0.657 |
| funding/scale_metric/lifecycle | q10 "Who funds them, at what scale…" | 205 | 71.2% | 94.1% | 0.922 |
| funding/scale_metric/lifecycle | q11 "The one checkable number showing actual reach…" | 205 | 40.5% | 74.6% | 0.731 |
| funding/scale_metric/lifecycle | q4 "Operating, scaling, distressed…and current as of what date?" | 205 | 14.6% | 79.0% | 0.688 |
| ask:offer:* | q15 "What can it offer…" | 167 | 22.8% | 46.7% | 0.609 |
| ask:need:* | q14 "What does this actor say it needs…" | 99 | 33.3% | 51.5% | 0.518 |
| **Overall (pooled)** | — | — | mean 33.9% | mean 67.0% | pooled 0.620 |

## Verdict

**Stage 5 survives, weakly and unevenly, with the caveat below carrying most
of the weight.** Every question beats chance (0.5 AUC) and top-3 hit rate is
comfortably above what a 1-in-4-to-7-sections guess would give, but the
margin is thin for three of the seven questions (q9, q15, q14: AUC 0.52–0.61)
— e5's asymmetric prefix is not confidently separating "which section talks
about contact/offers/needs" at paragraph grain for those three. `q10` funding
(AUC 0.92, top-1 71%) is the one clean pass — funding language ("₹", "$",
"seed", "grant", named funders) is lexically distinctive enough that almost
any embedding would separate it. `q4` lifecycle is the worst top-1 (14.6%)
despite a respectable top-3 (79%): lifecycle status words ("operating",
"scaling") are generic enough to also appear inside Scope/Recent-updates
prose, so the retrieval keeps the right chunk in the k=3 window but rarely
ranks it first — this is exactly the `TOP_K_PER_QUESTION=3` design in
`03-worker.md` §7 earning its keep, not a case where k=1 would do.

**The caveat the plan names is real and is doing most of the explanatory
work here.** These files are our own clean summaries — short, one topic per
section, written by a model that already knew which question each section
answered. That is a best-case corpus for a retrieval test: sections don't
bleed into each other much, so "chunk while ignoring headings" still mostly
recovers one-chunk-per-section boundaries, and vocabulary is fairly
consistent actor-to-actor because one author (Claude, per `process-leaf`)
wrote all of it in the same idiom. A messy 5,000-word annual report with the
funding figure buried in a footnote, or a press article that discusses
contact info and funding in the same paragraph, is a harder and more
realistic test that this PoC does not run. **So: PoC-1 is necessary and not
sufficient.** Failing it would have killed stage 5 outright (it did not
fail). Passing it proves the mechanics work — the prefix + cosine + top-k
pipeline is wired correctly and finds *something* real — not that it will
hold up on real fetched sources. The §7 downstream-coverage sweep on actual
fetched pages is still the test that matters before shipping stage 5.

**Surprise:** contact/channel questions (q9, q16) and offer/need questions
(q15, q14) are the weakest four of seven, not the funding/status ones — the
opposite of what I'd have guessed going in (I expected "who funds them" to be
the hard, needle-in-haystack case and "how to reach them" — often a bare URL
or platform name — to be the easy lexical give-away). It inverted because
"How to reach them" paragraphs are often just a URL/handle string with little
surrounding natural-language context for e5 to match against a full-sentence
query, while funding paragraphs are dense in the exact vocabulary ("funding",
"grant", amounts) the query itself uses. Also notable: q9 and q16 target the
*same* section but score very differently (top-3 55% vs 68%, AUC 0.59 vs
0.66) purely from question phrasing — "what are its live follow channels"
matches the URL/handle-heavy prose better than "how would you actually reach
them," which is the kind of phrasing sensitivity `03-worker.md`'s design will
need to account for when questions.yaml (§1a) is drafted.

## §1b opinion — ephemeral chunk vectors vs a `vec_chunk` kind

**Ephemeral, not a stored `vec_chunk` kind.** Three reasons, all visible from
running this PoC:

1. **Chunk vectors are a function of chunking parameters that are still
   moving.** `CHUNK_TOKENS`/`CHUNK_OVERLAP` are explicitly flagged in
   `03-worker.md` §7 as "starting values, not findings," to be swept against
   downstream coverage. A stored `vec_chunk` row is invalidated by any such
   sweep — either it goes stale silently or every sweep needs a
   migration/cleanup pass. Recomputing per-run instead makes staleness
   structurally impossible.
2. **The vectors have no life beyond one candidate's one retrieval pass.**
   Gate 1/2 vectors (`vec_problem`, `vec_candidate` etc., per `embed/*.py`)
   earn a stored kind because they are compared repeatedly across many
   candidates over time — that's the whole point of a dedup index. A chunk
   vector is compared against ~35 questions once, for one candidate, and then
   the candidate is either kept or dropped; nothing downstream ever re-queries
   "which chunks did source X have" outside that single pass.
3. **Storage cost buys nothing here.** This run encoded 1,672 chunks × 7
   questions in well under the runtime of the process itself (the model load
   dominates); re-encoding chunks per source at stage-5 time is not the
   bottleneck anything in `03-worker.md` is trying to solve. A `vec_chunk`
   table would add schema, a migration path, and a staleness question for a
   cost the profiling here shows isn't being paid.

If a future need arises to *audit* what stage 5 actually retrieved for a
given finding (debugging, or a "why did the model say this" trail), that is
better served by logging the chosen chunk *text* (or a content hash + offset)
into the existing finding/source trail than by persisting the embedding
itself — the vector is not human-legible evidence, the text is.

## Files

- `engine/poc/poc1_retrieval.py` — the script (`--limit N` for quick iteration)
- `engine/poc/poc1-results.md` — this file
