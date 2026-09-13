# Building the worker — prerequisites, PoCs, and parallel tracks

Fourth engine doc, and the only one that is not a design. `03-worker.md`
specifies the search-first worker; this says what to prove before building it,
what the build order in `03-worker.md` §16 is missing, and how the work splits
across tracks that can fail independently.

Written 2026-09-13, immediately after `03-worker.md`, against the tree at
`f91c1b5` (engine v2 step 3b — graph.db is the source of truth, corpus markdown
is prose-only).

Nothing here changes a decision in `03-worker.md`. Two things correct it: a
prerequisite its build order omits (§1), and a claim in its §7 that this corpus
falsifies (§2, PoC-1).

---

## 1. Three prerequisites missing from §16

Not PoCs. Nothing in the build order can start without the first of these, and
two others are unresolved decisions that surface the moment stage 5 is touched.

### 1a. `worker/questions.py` does not exist

`02-questions.md` is a specification with no implementation. Question ids are
the join key for four of the eight stages:

| Stage | What keys on a question id |
|---|---|
| 1 query planning | `families.yaml`'s `targets:` list |
| 5 passage retrieval | one encoded `query:` string per open question |
| 6 extraction | `answers[].question_id` in the response contract |
| 7 ledger | `finding.question_id` |

It is also what "realised coverage" counts over — the reward signal for the
bandit (§3), the metric the §7 constant sweep moves against, and the yield gate
in §11b. Every number in `03-worker.md` is denominated in questions answered.

`f91c1b5` added the `finding` table (`store/schema.sql:308`) whose column
comment reads *"key into `worker/questions.py`'s registry"* — pointing at a
file that is not in the tree. `03-worker.md` §16 lists it at no step.

It is the spine and it is small. Build it first, alone, before any track.

### 1b. Chunk vectors have no home

`embed/index.py:27` — `KINDS = ("problem", "actor", "source")`. Stage 5 produces
chunk-level vectors and there is no kind for them. Two options, and the choice
is not obvious enough to leave to whoever gets there first:

- **Ephemeral, in-memory, per run.** Simplest. Local encoding is free, so
  recomputing costs wall-clock only. Nothing persists, so nothing goes stale.
- **A `vec_chunk` kind.** Buys the `chunk_ref` column `03-worker.md` §9 asks
  for — auditing a wrong answer back to the text that caused it — at the price
  of a cache-invalidation story (a refetched page's chunks must be dropped) and
  a table that grows per source, not per entity.

Note the dependency: §9 wants `finding.chunk_ref` for auditing, which implies a
stable chunk identity. Ephemeral vectors can still carry a deterministic
`chunk_ref` (source id + ordinal) without persisting the vector, so the two
questions are separable — decide them separately rather than letting §9 force
a table.

### 1c. No chunker exists

`text/` holds `clean`, `canonical`, `pagestate`, `preview`, `simhash`. Nothing
chunks. Token-aware paragraph chunking against the encoder's own tokenizer is
greenfield, and it is the one piece PoC-3 exists to de-risk.

---

## 2. The PoCs

Four, ordered by what each can kill. PoC-0 and PoC-2 are the two that can force
a redesign rather than a parameter change.

### PoC-0 — SearXNG survives our query shape

`03-worker.md` §16 step 0, unchanged in substance. Docker instance, `json`
enabled, general category cut to ~5 engines, limiter off, 20 candidates × ~6
families at the throttle the worker would really use. Measure the
`unresponsive_engines` curve, predicted coverage per family, and whether thin
affected-led candidates surface anything at all.

Two additions, both free.

**Draw the 20 from already-researched actors, not from the candidate queue.**
The queue holds 11 rows (8 unadmitted, 3 admitted) — too few, and worse,
unresearched, so "did the money family return a page naming the funder" has no
answer to check against. The corpus already carries the answer key: 206 actor
files have a written `## Status` (funding and scale), 285 a
`## How to reach them`, 151 a `## What they need`. Sampling candidates whose
answers are already on file turns predicted coverage from a judgment call into
a comparison.

**Compute set cover against top-n on the same 120 queries.** `03-worker.md` §5b
argues that top-n by RRF fails because the organisation's homepage ranks for
every query, so the top 5 cover three families between them. That is a
prediction. The run buys the data to test it at zero extra cost: fuse once,
then select both ways offline and compare union coverage. If greedy set cover
does not beat top-n on real RRF data, §5b is complexity with no payoff and
should not be built.

**Record every JSON response to disk.** The run is also a replay corpus: track
D's unit tests then need no network, and a later provider swap has a baseline to
diff against. This costs a directory and makes the difference between fixtures
that are real and fixtures that are invented.

**Do not bring a number for the `unresponsive_engines` floor.** Pick it from
the curve. Guessing it in advance is the error `gate2.py:29-36` refuses to make
about its own bands, and §14 already lists the floor as open for exactly this
reason.

### PoC-1 — e5 can find the right paragraph

`03-worker.md` §7 says: *"No such label exists for 'does this chunk answer this
question.' Producing one means hand-annotating chunks, which is the work this
engine exists to avoid."* That is true of arbitrary web pages and **false of
this corpus.** The actor files' H2s are a question-labelled chunk set, already
written, already in the repo:

| Heading | Files carrying it | Question group |
|---|---|---|
| `## How to reach them` | 285 | `contact_route`, `channel:*` |
| `## Status` | 206 | `funding`, `scale_metric`, `lifecycle` |
| `## What they can offer` | 168 | `ask:offer:*` |
| `## What they need` | 151 | `ask:need:*` |

~810 labelled sections across four question groups, at an annotation cost of
zero.

The test: chunk each file **ignoring its headings**, encode the question as
`query:` and every chunk as `passage:`, and ask whether the top-3 chunks came
from the labelled section. That is a real AUC, computable in an afternoon,
measuring exactly the thing §7 says cannot be measured — whether the asymmetric
prefix buys discrimination at paragraph granularity.

**The caveat belongs in the result, not in a footnote.** These files are our own
summaries: short, clean, one topic per section, written by a model that knew
what question each section answered. A 5,000-word annual report with the funding
figure in a footnote is a different problem. So PoC-1 is **necessary and not
sufficient** — failing it kills stage 5 outright, and passing it proves the
mechanics only. The §7 downstream-coverage sweep still has to run on real
fetched pages afterwards.

It is worth the afternoon anyway, for a reason that has nothing to do with the
AUC: it is the difference between debugging retrieval against labels and
debugging it through a paid extraction call.

### PoC-2 — the batched call attributes and reconciles

`03-worker.md` §8 rests on two untested assumptions, and §13 mitigates one of
them by dropping answers without any estimate of how many.

The 92 rows already in `source` mean this costs no HTTP. Build the
`[S1]…[S4]` prompt over four stored pages and measure three things:

1. **JSON parse success rate.** §13's mitigation is a per-source retry; how
   often it fires decides whether that path is worth writing.
2. **Share of answers carrying a valid `source_id`.** §8 requires it and drops
   answers without it. An unmeasured drop rate is an unmeasured hole in
   coverage — and coverage is the metric everything else is tuned against.
3. **Whether a planted contradiction is reconciled.** Put two sources into the
   prompt that disagree on a figure and check the model writes the disagreement
   rather than silently picking a side. This is the entire justification for
   batching over per-source calls: §8 claims reconciliation becomes free once
   both sides are in one context. Nobody has checked that it happens rather
   than that it *could*.

Run it on both rungs. The 2026-09-13 01:50 run that wrote `reset-air`,
`gbci-usgbc-leed-arc` and `gmda` used `nemotron-3-super-120b-a12b:free`. If the
free rung cannot hold `[Sn]` discipline across ~9k tokens of passages, the
`:free` column in §12's cost table stops being real and the cost model changes.

### PoC-3 — token accounting at the 512 window

Mechanical, roughly twenty minutes, and it corrupts everything silently if
wrong. §7 asserts that Devanagari tokenizes ~20% longer than the same characters
in English and that 320 tokens plus `passage: ` plus the special tokens fits the
window with margin. Check it against the real tokenizer on real multilingual
text from the corpus.

The failure is silent by construction: `fit()` (`embed/model.py:60`) truncates
correctly when called, but a chunk handed straight to the encoder over the
window is embedded **on its head alone**, with no error and no warning. §7 says
to respect the window when chunking rather than relying on `fit()` to rescue it;
this measures what respecting it costs.

### Deliberately not a PoC: the second pass

`03-worker.md` §11c already has the right shape — three integer counters written
during pass 1 settle whether §11b would ever fire usefully. Do not build a spike
for it, and do not build §11b. A PoC here would be the same error as building
the branch: spending to answer a question that real runs answer for free.

---

## 3. One correction to the cost model

`llm.py:53` — `_openrouter_lock` is a module-global `threading.Lock`, and the
pace function holds it **across the sleep**, deliberately, so that it spaces
concurrent callers rather than one thread. §12 states the consequence correctly:
~20 req/min is the ceiling, so ~20 candidates/min at one extraction call each.

What §12 does not state is the corollary, and it is an orchestration
constraint: **the lock is per process.** Shard candidates across processes to go
faster and each process gets its own lock, the interval collapses to nothing,
and the run buys 429s instead of throughput. Runtime parallelism has to be
threads inside one process — or the pacing has to move somewhere shared before
any multi-process runner is written.

Worth knowing now because it bounds what runtime parallelism is for. Above ~20
in-flight candidates on the openrouter rung, concurrency buys nothing on the
stage that costs money; it still buys plenty on stages 2 and 4, which are HTTP
and are throttled for a different reason (§4 obligation 1).

---

## 4. Build tracks

`F1` is the spine (§1a). Everything else waits on it, and it is small enough
that waiting is cheap.

| Track | New files | Touches | Needs | Degrades to |
|---|---|---|---|---|
| **F1** question registry | `worker/questions.py` | — | — | — (blocking) |
| **A** problem emission | — | `worker.py` `_emit`, `resolve.py` | — | today's behaviour: unresolvable edge dropped |
| **B** depth tier | `worker/depth.py` | `worker.py` intake | F1 | everything `tracked` |
| **C** chunk + passage | `text/chunk.py`, `worker/passages.py` | `worker/config.py` | F1, PoC-1, PoC-3 | first-N-chars per source, capped (§13) |
| **D** search | `engine/search/` — provider adapter, `families.yaml`, `fuse.py`, `cover.py` | — | F1, PoC-0 | the candidate's own URL as single source (§13) |
| **E** extract + ledger + counters | `worker/extract.py` | `prompts.py`, `worker.py` `run_batch` | F1, C, D, PoC-2 | — |

A, C and D are genuinely concurrent once F1 lands. B is small enough to ride
with A. A is also the one track with no dependency at all — `03-worker.md` §16
puts it first for that reason, and it stays first here.

### The rule that makes a failed track survivable

**Only track E edits `run_batch`.** That function is the one file every track
wants, and it is where a merge becomes a rewrite. A, C and D ship **new modules
exposing pure functions**:

```
fuse(results_by_query)        -> [(url, rrf_score, coverage_set)]
cover(ranked, max_sources)    -> [url]
chunk(text)                   -> [Chunk]
select(chunks, questions, k)  -> [Chunk]
```

None of them knows the pipeline exists. All of them are unit-testable with no
network, no model and no database. E is the only integration point, done once,
by one worker, after the others land.

### Freeze four contracts before the tracks start

Concurrent tracks that share a type and not a definition of it diverge, and the
divergence surfaces at integration, which is the worst place for it.

1. **`SearchResult`** — `(rank, url, title, snippet, native_score | None)`, plus
   `unresponsive_engines` recorded per query (§4 obligation 2). `rank` derives
   from SearXNG's `score`, never the JSON list index (§4).
2. **The `questions.py` registry shape** — id, kind (`problem` / `actor`), the
   question text used as the `query:` string, and which depth tier asks it (the
   `registry` identity subset vs. the full set).
3. **`Chunk`** — text, source id, ordinal, token count. The ordinal is what
   makes `chunk_ref` (§9) possible without persisting a vector (§1b).
4. **The stage-6 response JSON** (§8 verbatim), with `source_id` required on
   every answer.

### Land each degrade path before the code that degrades to it

`03-worker.md` §13 reads as a runtime spec. It is also the build's fault
isolation: if D cannot ship, stage 2 falls back to the candidate's own URL and
the worker still runs — it just runs like today. That property only holds if the
fallback exists *before* the track does, so write the fallback first and let the
track be the revertible part. The pipeline stays runnable at every commit.

### Fixtures

Each track owns its own under `engine/tests/fixtures/`; no shared golden file,
because a shared golden file is a serialisation point between tracks that were
split to avoid one. D's fixtures are PoC-0's recorded responses (§2), which is
the whole reason to record them.

---

## 5. Sequence

```
PoC-0  ‖  PoC-1  ‖  PoC-3          mutually independent, no shared code
            ↓
           F1                       the question registry, alone
            ↓
  (A + B)  ‖   C   ‖   D            three tracks, pure functions only
            ↓
          PoC-2                     wants C's chunker to be realistic
            ↓
            E                       the only edit to run_batch
            ↓
     counters run on real candidates
            ↓
  §7 constant sweep, then the bandit
```

The last line is last for the reason §16 already gives: both need
realised-coverage numbers that do not exist until the pipeline has run against
real candidates. Tuning before then is tuning against a guess.

---

## 6. What this plan does not settle

- **§1b** — ephemeral chunk vectors or a `vec_chunk` kind. Needs deciding before
  track C writes a line, and PoC-1 will have an opinion about it.
- **The `unresponsive_engines` floor** — still open, still waiting on PoC-0, and
  deliberately not guessed here.
- **Whether §11b exists at all** — the counters decide, after E.
- **Whether set cover survives** — PoC-0 decides, and §5b should be deleted
  rather than defended if it does not.
