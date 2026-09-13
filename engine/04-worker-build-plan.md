# Building the worker — prerequisites, PoCs, and parallel tracks

Fourth engine doc, and the only one that is not a design. `03-worker.md`
specifies the search-first worker; this says what to prove before building it,
what the build order in `03-worker.md` §16 is missing, and how the work splits
across tracks that can fail independently.

Written 2026-09-13, immediately after `03-worker.md`, against the tree at
`f91c1b5` (engine v2 step 3b — graph.db is the source of truth, corpus markdown
is prose-only).

**Updated later the same day, after all four PoCs ran (plus two added
mid-run) and F1 plus tracks A/B/C shipped.** This file is no longer only a
pre-build plan — §2, §5 and §6 are now a record of what those runs decided.
Where a subsection has been superseded, the reasoning that led to the decision
is kept and marked, not deleted; only §3's numbers were pure prediction and
those are now measured.

Nothing here changes a decision in `03-worker.md`. Three things correct it: a
prerequisite its build order omits (§1a), a defect in how §7/§11 define an "open
question" (§1d, written up in `03-worker.md` itself), and a claim in its §7 that
this corpus falsifies (§2, PoC-1). §3 below adds three more corrections, found
while running the PoCs.

---

## 1. Four prerequisites missing from §16

Not PoCs. Nothing in the build order can start without the first of these; the
other three are unresolved decisions that surface the moment stage 5 is touched.

### 1a. The question text has no home in code

**This is narrower than "build a question registry", and the difference
matters.** The question set needs no new authority: every claim field already
has one — `store/tags.py`'s REGISTRY for `tag:*`, the `problem`/`actor` columns
for bare field names, rows in `ask` and `channel`, all stated in
`02-questions.md`'s Conventions. The tables there are already id'd (`#`), typed
(`Claim field`) and flagged (`Multi`). Nothing about the *set* is missing.

What exists nowhere in code is three things: the **question text**, its
**stable id**, and **which tier asks it**. `prompts.py:112,135` carries a prose
*field list* inside `_PROBLEM_SYSTEM` / `_ACTOR_SYSTEM` — not the 35 questions,
and no ids at all.

Question ids are the join key for four of the eight stages:

| Stage | What keys on a question id |
|---|---|
| 1 query planning | `families.yaml`'s `targets:` list |
| 5 passage retrieval | one encoded `query:` string per open question |
| 6 extraction | `answers[].question_id` in the response contract |
| 7 ledger | `finding.question_id` |

Ids are also what "realised coverage" counts over — the bandit's reward signal
(§3), the metric the §7 constant sweep moves against, and the yield gate in
§11b. Every number in `03-worker.md` is denominated in questions answered.

Two consumers need the *same* strings: `prompts.py` puts the question text in
the extraction prompt, and stage 5 encodes it as a `query:`. So they have to
live once, somewhere both read. That is the whole requirement — a single home
for ~35 strings plus their ids and tier flags, not a new source of truth.

**Form: YAML, by this repo's own precedent.** `03-worker.md` §3 puts query
templates in git-tracked `engine/search/families.yaml` because *"a query
template is a research decision and belongs in version control, not in a table
nobody reads"*. A question is more of a research decision than a query
template, so `engine/questions.yaml` follows, with `families.yaml` referencing
its ids.

**Not an oversight in §16 — a revert.** `02-questions.md`'s *"Why this is a doc
and not code"* records that `worker/questions.py` + `worker/dive.py` existed and
were reverted on 2026-09-13. What that section rejects is the *loop* hung off
the list, explicitly keeping the list: *"the question set it was built around
was not [the wrong shape], and is the part worth keeping."* So §16 omits
scheduling the re-implementation, rather than overlooking a dependency.

One consequence: the `finding` table's column comment
(`store/schema.sql:311`) — *"key into `worker/questions.py`'s registry"* — is a
**stale reference to the reverted file**, not a pointer at something missing. It
survived the revert and should be repointed when the YAML lands.

Small, and first, alone, before any track.

**Status: SHIPPED.** `engine/questions.yaml` + `engine/worker/questions.py` +
`engine/tests/test_questions.py`; `store/schema.sql:311`'s comment now reads
"loaded from `engine/questions.yaml` (F1)" instead of pointing at the reverted
file. But this section *understated* what F1 turned into: the file is not "~35
strings plus ids and tier flags." Per PoC-1b/1c it also carries, per question,
a swept `retrieval_query:` string distinct from the extraction `question:`
text (PoC-1b found one string cannot serve both consumers), a `retrieval:
true|false` flag routing five actor questions and several problem questions to
inference-over-context instead of a dedicated retrieval call (PoC-1c), a
`bucket:` grouping the ~35 questions into the 11 retrievals PoC-1c found are
actually needed, and a measured-vs-heuristic provenance field recording
whether a `retrieval_query` and its `bucket` came from a real sweep or is
still the un-swept default. `02-questions.md` was split out of this same work
today as the human-readable field-set authority; `questions.yaml` is its join
key, not a duplicate of it.

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

**Status: DECIDED — ephemeral, no `vec_chunk` kind.** Settled by PoC-1
(`poc1-results.md` §1b), on three grounds visible from running it: chunk
params (`CHUNK_TOKENS`/`CHUNK_OVERLAP`) are still moving, so a stored vector is
invalidated by the next sweep; a chunk vector is compared once, for one
candidate's one retrieval pass, never re-queried afterward, unlike
`vec_problem`/`vec_candidate`'s repeated-comparison use case; and encoding cost
is not the bottleneck (1,672 chunks × 7 questions encoded in well under model
load time). `chunk_ref` stays available as `source_id:ordinal` without
persisting a vector — if a future audit trail is needed, log the chosen chunk
*text*, not the embedding, which is not human-legible evidence anyway.

### 1c. No chunker exists

`text/` holds `clean`, `canonical`, `pagestate`, `preview`, `simhash`. Nothing
chunks. Token-aware paragraph chunking against the encoder's own tokenizer is
greenfield, and it is the one piece PoC-3 exists to de-risk.

**Status: SHIPPED, as track C.** `engine/text/chunk.py` + `worker/passages.py`,
tested (`tests/test_chunk.py`, `tests/test_passages.py`). `CHUNK_TOKENS = 320`
per PoC-3's measurement (§2 below); `CHUNK_OVERLAP` was never enforced by the
shipped code and now never will be — **settled at 0 by PoC-1d**, with the
straddle repair it existed for moved to selection time as `NEIGHBOUR_RADIUS`
(§3 correction 3).

### 1d. `open question` is undefined for 6 of the 35

Written up where it belongs, in `03-worker.md` §7 (*What "open" means*), §11b and
§11c, since the defect is in that design rather than in this plan. In short:
`02-questions.md` diagnosed during the revert that **`multi` questions never
retire**, and `03-worker.md` reintroduced a dependency on "open question" in
three places without re-solving it. The sharp end is that §11c's counter 1 can
never read 0 — §11b's high-value set names who-works-it, which is `multi` — so
the counter built to decide whether to build §11b always reads yes.

It belongs in this list because of what it blocks at build time:

- **track C** cannot define its encode set without it (stage 5 iterates open
  questions), though it degrades safely: with no closing rule, C simply encodes
  all 35 and the passage union is larger than it needs to be;
- **track E** can write counter 1, but nobody may read it as a signal until the
  rule lands. Writing it is still correct — counters 2 and 3 are unaffected.

So it does not block the build, only the *conclusion* the build is meant to
support. Decide it before reading §11c's output, not before writing it.

**Status: still open, but narrower than when this was written.** PoC-1c found
that 5 of the 35 questions (q2 `type` 0.516, q3 `legs` 0.586, q5
`ecosystem_role` 0.539, q7 `representation_unit` 0.430, q13 `failure_note`
0.243) are not retrieval questions at all — whole-record enum inferences with
no localised passage, rescued by no phrasing or target. Those five drop out of
the "open question" bookkeeping entirely rather than needing a closing rule:
an inference question is never "open" in the retrieval sense, so the `multi`
non-retirement defect this section describes only has to be solved for the
remaining, genuinely-retrieved `multi` questions. The closing rule itself is
still undecided.

---

## 2. The PoCs

Four ran, ordered by what each could kill, plus two added mid-run when PoC-1's
results raised questions PoC-1 itself couldn't answer. PoC-0 and PoC-2 were the
two that could force a redesign rather than a parameter change; neither did.

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

**Results — PoC-0a (infra + shape, `poc0a-results.md` + two addenda).** JSON
contract verified against real captured responses: `score` present and
monotone with agreement (not the list index) — §4's "rank from score, never
list index" is implementable as stated. `unresponsive_engines` present, shape
`[[engine, reason]]`. Final working engine set, after two rounds of live
diagnosis: **4 of the original 5 — `brave`, `google`, `bing`, `mojeek`**.
`duckduckgo` and its attempted replacement `qwant` are both structurally
blocked (CAPTCHA / anti-bot cookie) from this environment, independent of any
setting this repo controls — dropped for good, no viable 5th found without an
API key (`startpage` behind a PoW challenge, `marginalia` requires a signup
key, `wikipedia`/`openalex`/`crossref` are not general web indexes). `bing`'s
failure was HTTP/3 (QUIC) breaking under colima's Docker network, not an IP
block — `enable_http3: false` fixed it to 10/10. `mojeek` suspends
(`suspended_time=180`) after ~3-4 rapid requests but is fully reliable once
past that window at ≥2.0s spacing — the throttle floor this PoC set for
`03-worker.md` §4 obligation 1.

**Finding: `unresponsive_engines` is a lower bound, not the failure set.**
`mojeek` returned zero results while appearing in *neither* `unresponsive_engines`
nor the results' `engine`/`engines` fields, reproduced independently three
times (PoC-0a's addendum, PoC-0b's dry run, and PoC-0b's full 120-query run).
Any consumer of that field — the §14 floor, track D's health check — has to
diff against the *configured* engine list to catch a silent drop-out; the
reported list alone will read "fine" when an engine has gone dark. Carried
forward as correction 1 in §3 below.

**Results — PoC-0b (the real 120-query run, `poc0b-results.md`).** 20 actors ×
6 families (`identity`, `money`, `people`, `viability`, `failure`, `reach` —
`asks` dropped to land on 20×6), drawn from already-researched actor files per
the addition above, so per-family coverage could be checked against a real
answer key. Selection deliberately included 8 thin/affected-led actors
alongside 12 well-covered ones.

- **`unresponsive_engines` curve: flat, not climbing.** 119/120 queries (99%)
  carried ≥1 unresponsive engine, at essentially the same rate across all
  three thirds of the run (40/40, 39/40, 40/40) at a 25s base / ±5s jitter
  throttle. This kills the rolling cumulative-volume-degradation hypothesis
  from PoC-0a's addendum **at this pace** — engines were already degraded from
  query 1, not progressively degrading. It was not retested at the tighter
  2.0-4.0s band the addendum's own dry run used, so the hypothesis is dead at
  25s spacing specifically, not disproven in general.
- **Per-family predicted coverage**: viability 19/20 (95%), identity 17/20
  (85%), people 9/15 (60%), reach 11/20 (55%), money 5/18 (28%), failure 5/18
  (28%).
- **The bottleneck is search, not retrieval.** `money` maps to the
  `actor-status` bucket, which PoC-1/1b measured as the *best*-performing
  retrieval bucket in the whole pipeline (AUC 0.977 — near-perfect at finding
  the funding paragraph once a page is in hand). At only 28% search coverage,
  the page carrying that information usually never gets fetched in the first
  place. Stages 1-2 (query planning / search), not stage 5, are where `money`'s
  poor number actually lives.
- **`failure` at 28% independently corroborates PoC-1c** (a different method:
  `q13_failure_note` scored AUC 0.243 on labelled-chunk retrieval, with failure
  vocabulary present in only ~10 of 289 corpus files). Two unrelated methods
  agreeing that organisations don't publish their own failures is stronger than
  either alone. Recommendation: stop treating `failure` as retrievable; record
  its absence per `02-questions.md`'s absence rule instead.
- **Set cover vs top-n**: at n=3, set-cover beats top-n on 3 actors, ties on 17,
  never loses; at n=5, beats on 2, ties on 18, never loses. **§7's §5b
  survives** — but the honest reading is not "barely helps on average," it is
  that the entire measured value concentrates on exactly the actors the
  platform exists to reach: `bhavreen-kandhari` (individual citizen activist,
  3/6 → 6/6 at n=3), `bku-ekta-ugrahan` (informal farmers' union, 5/6 → 6/6),
  `employees-state-insurance-corporation` (5/6 → 6/6, both n). Two of three are
  the thin/affected-led population the sample was built to include. Build
  set-cover for that reason, not for the average margin, which is thin because
  well-covered "rich" actors already have enough top-rank diversity that
  top-n's homepage-duplication failure mode doesn't bite them.
- **Throttle floor answered at this pace, not fully.** No volume-driven
  degradation at 25s/±5s spacing — flat 40/40, 39/40, 40/40. Cannot rule out
  the rolling-budget effect at the tighter 2.0-4.0s band; not retested here.
- **Correction to §14's framing of the floor.** At 99% of queries carrying ≥1
  unresponsive engine, a floor defined on *engines failed* rejects essentially
  the whole run — there is no threshold on that axis that both excludes bad
  data and keeps any data. The floor has to be defined on **engines that
  returned** (a minimum count answering), not engines that failed. This run
  does not pick the number — deliberately, per this doc's own instruction —
  but it does settle which axis it belongs on. Carried forward as correction 2
  in §3.

120 recorded JSON responses (`poc0b-responses/`) double as the replay corpus
this section's third addition asked for.

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

**Results (`poc1-results.md`, full corpus, 289 files / 1,672 chunks).** Stage 5
survives, weakly and unevenly. Pooled AUC **0.620**, mean top-1 **33.9%**, mean
top-3 **67.0%** across the seven question groups. Per question:

| Question | top-1 | top-3 | AUC |
|---|---|---|---|
| q10 funding | 71.2% | 94.1% | **0.922** |
| q11 scale_metric | 40.5% | 74.6% | 0.731 |
| q4 lifecycle | 14.6% | 79.0% | 0.688 |
| q16 channel | 32.7% | 67.7% | 0.657 |
| q15 ask:offer | 22.8% | 46.7% | 0.609 |
| q9 contact_route | 22.0% | 55.2% | 0.592 |
| q14 ask:need | 33.3% | 51.5% | 0.518 |

Only `funding` (0.922) is a clean signal — funding vocabulary ("₹", "$",
"seed", "grant") is lexically distinctive enough that almost any embedding
separates it. `ask:need` (0.518) is barely above chance. Every question beats
0.5, but the margin is thin for q9/q15/q14. Surprise: contact/channel and
offer/need questions are the *weakest* four of seven, not the funding/status
ones — inverted from the pre-registered expectation, because "how to reach
them" prose is often a bare URL/handle string with little natural-language
context for e5 to match against a full-sentence query, while funding
paragraphs are dense in exactly the vocabulary the query itself uses.

The caveat this section names going in turned out to matter as much as
predicted: this is our own clean, one-topic-per-section, single-author corpus
— necessary-and-not-sufficient evidence, mechanics proven, downstream-coverage
sweep on real fetched pages still outstanding. §1b above records PoC-1's
`vec_chunk` decision.

### PoC-1b — question-phrasing sweep (added after PoC-1)

Not in the original plan. PoC-1 used one phrasing per question (its own
question text, verbatim, as the `query:` string) and left open whether a
different phrasing would retrieve better. `poc1b_phrasing.py` swept 6 phrasing
candidates per question (control + `noun_phrase` + `statement_shaped` +
`keyword_list` + `entity_type_word` + `vocab_overlap`) across the same 7
questions, same corpus, with file-level bootstrap (1,000 resamples, 90% CI) to
tell a real margin from noise.

**Mean pooled AUC moved from 0.674 (this PoC's own re-measured control) to
0.815** once each question is phrased for what actually retrieves. Four load-
bearing findings:

1. **No axis wins globally.** `keyword_list` wins q9, `noun_phrase` wins
   q16/q10/q11, `statement_shaped` wins q15, `vocab_overlap` wins q14 — five
   different winning axes across seven questions, including two (q9/q16) that
   target the *identical* section. A question's retrieval string is an
   empirical result per question, not a house style. Cheapest sweep for a new
   question: control + `noun_phrase` + `statement_shaped` (3 candidates),
   which produced the winner in 5 of 7 cases here.
2. **`entity_type_word` is a consistent loser — the one rule that does
   generalise.** Appending "this actor"/"this organisation" underperforms
   control in 5 of 7 questions and is outright destructive on the worst two
   (q4 0.280 vs 0.688 control, q11 0.632 vs 0.731 control). Do not add an
   explicit entity-type noun to a retrieval query.
3. **q4 lifecycle: control stays.** Best alternative is −0.009 vs control,
   bootstrap CI crosses zero. The question's enumeration ("operating, scaling,
   distressed...") is load-bearing and stripping it to a noun phrase collapses
   the score (0.688 → 0.370).
4. **q14 ask:need is still broken after the sweep** — best AUC 0.556
   (`vocab_overlap`), barely above chance, on the smallest sample (n=99). Read
   as a content problem, not a phrasing problem: "What they need" sections are
   often terse/generic and give e5 nothing lexically distinctive to lock onto,
   regardless of query wording.

**§1a consequence:** one field cannot serve both consumers. The winning
retrieval phrasing for four of seven questions is a bare noun phrase or
keyword list (e.g. q9's winner is literally `"contact email website social
media handle channel"`) — not a sensible string for an extraction prompt,
which needs the full natural-language form (including q4's enumeration).
`questions.yaml` carries `question:` (extraction) and `retrieval_query:`
(stage 5) as two separate fields, folded into F1 as shipped (§1a above).

### PoC-1c — can question-level retrieval merge into per-bucket queries? (added after PoC-1b)

Also not in the original plan. `03-worker.md` §7 implies one retrieval per
open question (~35 encode calls per candidate); this tests whether questions
sharing a target section can share one query instead. Reused PoC-1b's
phrasing-candidate + bootstrap machinery, plus a second corpus (7 existing
leaf files, 129 chunks, the A-E section labels) to check the same question on
the problem side.

**The merge is a gain, not a cost.** For every co-located bucket tested, the
bucket-wide shared query ties or *beats* every question's own dedicated best:
`reach` (q9,q16) ties q9's dedicated best (0.893) and beats q16's by +0.103;
`status` (q10,q11) ties q10 (0.977) and beats q11's by +0.046; problem-side
buckets A-E show the same pattern (margins +0.11 to +0.42, though n=7 files
means wide CIs — directionally consistent, not independent confirmation).

Three further findings that changed the bucket design from what was proposed:

1. **q4 `lifecycle` was scored against the wrong section all along.** Reading
   real sections showed `## Status` is almost entirely two fixed bullets
   (funding, scale — exactly q10/q11's content) and rarely discusses
   operating/scaling/dormant state; `## Recent updates` is where lifecycle
   language actually lives. Retargeting q4 to `Recent updates` and rephrasing
   to `noun_phrase` moves AUC **0.688 → 0.919**. The union of Status ∪ Recent
   updates is worse than Recent-updates alone (0.887 vs 0.919) — a red
   herring, not a safety net. q4 becomes its own single-question bucket
   against `Recent updates`, not part of `status`.
2. **Five questions are not retrieval questions at all**: q2 `type` (AUC
   0.516), q3 `legs` (0.586), q5 `ecosystem_role` (0.539), q7
   `representation_unit` (0.430), q13 `failure_note` (0.243) — whole-record
   enum inferences with no localised passage. No phrasing or target rescues
   any of them (best shared-candidate score across the identity trio's three
   targets: 0.657, still chance-adjacent). These get `retrieval: false` and
   are answered by inference over whatever context the retrieval questions
   already pulled — this is the §1d narrowing recorded above.
3. **35 → 12 retrievals** (stated as ~11-12 depending on how the untested
   4 problem-`core` questions are eventually classified): `reach` (q9,q16),
   `status` {q10,q11,q12 — q12 viability folds in, genuinely overlaps Status
   prose at AUC 0.835-0.873}, q4/`Recent updates` (alone), `needs` (q14,
   alone — still chance-level, a content gap not fixed by bucketing),
   `offers` (q15, alone), `identity-retrieval` {q1,q6,q8 against the preamble,
   AUC 0.78-0.96}, plus problem-side A-E (5 buckets covering 15 questions).
   `identity-inference` {q2,q3,q5,q7} and q13 get no retrieval at all.

Recommendation, carried into `questions.yaml`: encode `retrieval: true|false`
and `bucket:` per question before merging anything, so a bucket only ever
contains questions the corpus can actually answer by retrieval — merging an
inference-shaped question into a bucket would have hidden its coverage gap
behind a bucket that "worked" on its retrievable members. Both fields shipped
in F1.

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

**Status: running, 2026-09-13.** `engine/poc/poc2_extract.py`. It has track
C's real chunker and its shipped passage selection to draw from, rather than
the placeholder assumed when this doc was first written, and it measures the
neighbour-expansion token cost (§3 correction 3) on the same prompt while it
is there — radius 1 against radius 0.

**Status correction, later the same day: the instrument is built and the run
is not done.** `engine/poc/poc2_extract.py` exists and works end to end up to
the call. No results file exists and none should be written until calls land.
Four things were learned anyway, three of them before any model produced
output, and they change how the run should be executed.

**Two things this section got wrong about its own setup, both found before a
single call was made:**

1. **"The 92 rows already in `source` mean this costs no HTTP" is false.**
   89 of the 92 rows have no cached text on disk — `path` NULL, or the file
   absent — and of the three that remain, two are ~1.5 KB. There was never a
   corpus of stored pages to build the prompt from. PoC-2 therefore fetches,
   down the ranked URL pool PoC-0b already recorded for one actor, into a
   **copy** of `problems/graph.db` under a scratch directory with its own
   cache dir, so a PoC run leaves no diff in a tracked database. (The wider
   point for track E: `source` rows and cached page text are not the same
   thing, and code that assumes a row implies readable text is wrong today.)
2. **A search-sourced URL pool cannot be fed to extraction unfiltered.** The
   recorded pool for `selco-foundation`, ranked by SearXNG `score`, puts
   `30rates.com/aed-php`, `remitly.com/currency-converter`, `pinkbike.com`,
   `music.youtube.com` and a Japanese Wikipedia article about the number
   1,000,000,000,000 among the top results. Several fetch `ok` with 1,000+
   words. Without a filter they enter the prompt as `[Sn]` blocks and the
   model is asked to extract an actor's funding from a currency converter.
   PoC-2 added a crude entity-name check as a stand-in. That is *not* the
   fix — it is evidence, arriving a track early, for the gate-2 hole in §5
   below.

**And four more, found while trying to run it:**

3. **`llm.call(json_out=True)` cannot measure a parse rate, because it
   retries.** The first real call — `nemotron-3-super-120b-a12b:free`, ~18k
   prompt chars, 17 actor questions — came back malformed (`Expecting ','
   delimiter: line 281 column 89`). `llm.py` treats that as retryable and
   spends its whole attempt ladder (up to 6, exponential backoff) before
   raising `LLMError`, so one bad response costs several minutes and the
   surviving number is "parse rate after up to six retries" — not the
   single-shot rate §13 needs to size its per-source retry. The instrument
   now calls with `json_out=False` and parses in the PoC, keeping the
   malformed string; transport retries (5xx, 429) stay inside `llm.call`,
   where they belong. **The one datapoint that exists says the free rung
   fails strict JSON on a prompt this size**, which is exactly what would
   falsify §12's `:free` column — but n=1, and one malformed response is not
   a rate.
4. **Only the `openrouter` rung can run at all.** `anthropic` (the `claude`
   rung) and `google-genai` (the `gemini` rung) are commented out in
   `engine/requirements.txt:20-21` and not installed; `claude-cli` is gated
   on `CLAUDE_CODE_OAUTH_TOKEN`, which is not in `engine/.env`. Decision
   taken 2026-09-13: **run PoC-2 on the free rung only and record the gap**
   rather than install a dependency for a PoC. Consequence to carry: this
   section's "run it on both rungs" is not satisfied, so a free-rung failure
   cannot be separated from a prompt-design failure — if the free rung
   cannot hold `[Sn]` discipline, PoC-2 alone will not say whether a paid
   model could.
5. **The source set for a given actor is not reproducible run to run.** Two
   runs of `anthill-ventures` against the same ranked pool drew different
   pages (tracxn/pitchbook/outlook/linkedin, then
   capboard/cbinsights/superscout/vccircle), because sites that fetch `ok`
   once fetch `blocked` or `thin` the next time. Fine for a live worker;
   awkward for a PoC, whose numbers then move for reasons unrelated to what
   it is measuring. Any conclusion drawn from one actor's run should be
   treated as a sample of one *page set*, not of one actor.
6. **The 20-call design was wrong and was abandoned before spending it.**
   5 repeats × 2 radii × 2 rungs, all on one actor's prompt. Two of those
   three factors don't earn calls: the radius comparison is **build-time
   only** (finding 7 below — prompt size is deterministic and needs no
   model), and 5 repeats of a *fixed* prompt measures the small variance
   precisely while leaving the large one — across actors and page sets —
   unmeasured. The `source_id` validity metric is also per-*answer*, so one
   call with fifteen answers is already fifteen observations. Replaced by:
   **5 actors × 2 repeats × radius 1**, parse failures retried once (which
   is the actual §13 question), same budget, parse rate estimated over five
   different prompts instead of one.
7. **Neighbour expansion costs ~2× prompt tokens, and this is now measured.**
   On the real built prompt, `anthill-ventures`: radius 0 → 14 chunks, 2,886
   passage tokens, 11,502 chars; radius 1 → 24 chunks, 5,804 passage tokens,
   23,214 chars — **2.01×**. An earlier run of the same actor on a different
   page set gave 2,167 → 5,049 tokens, **2.33×**. So the real cost sits at
   the bottom of PoC-1d §6's "up to 3×" estimate, and it took no LLM call to
   find out — prompt size is a deterministic function of selection. §3
   correction 3 and §8 are updated.

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

**Results (`poc3-results.md`).** Window confirmed at 512 (read off
`encoder.max_seq_length`, not assumed). Overhead: 2 special tokens, `passage: `
is 3 tokens. Budget: `320 + 3 + 2 = 325`, margin **187 tokens (37% of the
window)** — **§7's claim HOLDS**, with margin even under the conservative
20%-longer-Devanagari assumption (320×1.2 ≈ 384, +3+2 = 389, still 123 tokens
under the window).

**But §7's "Devanagari ~20% longer" itself is unverified, not confirmed.** The
corpus has ~105 characters of Devanagari total, across 8 fragments in 4 files
— two people's names and two nav-menu words, not running prose. Measured
chars/token on that fragment set (4.038) is actually *higher* than English's
measured rate (3.677), the opposite direction from §7's claim — read as an
artefact of the sample being proper nouns, not a real disconfirmation, since
no Hindi/Marathi prose of any length exists anywhere under `problems/` to test
against (checked; also zero hits for Bengali/Tamil/Telugu/Gujarati). Re-run
against the real tokenizer once the worker actually fetches non-English prose.

**Also corrected here: `embed/texts.py:28`'s `MAX_CHARS=2000` is a character
pre-bound, not a window guard.** An earlier working assumption treated it as a
live truncation bug; it is not — `fit()` (`embed/model.py:60`, invoked via
`backfill.py:83`) is the actual window guard. `MAX_CHARS=2000` is a *looser*
character cap that sits upstream of `fit()` and does not by itself prevent the
silent-truncation failure this PoC demonstrates (2,000 English characters ≈
544 tokens, already over the 512 window before any prefix). The chunker
(track C, §1c) is what has to respect the window at construction time, not
`fit()` or `MAX_CHARS`. `CHUNK_TOKENS = 320` is the recommended and shipped
value.

### Deliberately not a PoC: the second pass

`03-worker.md` §11c already has the right shape — three integer counters written
during pass 1 settle whether §11b would ever fire usefully. Do not build a spike
for it, and do not build §11b. A PoC here would be the same error as building
the branch: spending to answer a question that real runs answer for free.

---

## 3. Corrections to `03-worker.md`, found while running the PoCs

Three corrections the build must carry, beyond §1d's already-documented defect.

1. **§4 obligation 2 is wrong: `unresponsive_engines` is a lower bound on
   failure, not the failure set.** `mojeek` returned nothing while appearing
   in neither the results nor that list, reproduced on three independent runs
   (PoC-0a's addendum, PoC-0b's dry run, PoC-0b's full run). Any consumer must
   diff against the *configured* engine list, not trust the reported one.
2. **§14's floor is posed on the wrong axis.** At 99% of queries carrying ≥1
   unresponsive engine (PoC-0b, full run), a floor defined on *engines
   failed* rejects essentially everything. It must be defined on **engines
   that returned** (a minimum count answering). Still do not pick the number
   — that stays open, on the corrected axis.
3. **§7's `CHUNK_OVERLAP = 48` is wrong, and the fix is not a smaller
   overlap — it is no overlap plus neighbour expansion at selection time.**
   Track C never implemented it; PoC-1d then measured it and it should not be.
   Overlap repairs the straddle it was specified for (95.8% of 284 real
   figure/denominator splits at 48, 100% at 64) but pays for it inside the
   *embedding* of every chunk: reach 0.893→0.649, status 0.977→0.837,
   identity 0.503→0.367, and 33% of the passage budget's source diversity
   (142.9→95.6 chunks fitting the cap). Two buckets move the other way
   (`needs`, `offers`) and both are the weakest in the set, near chance even
   at their best — read as smearing, not as a case for overlap.

   **Why the damage is this large is a property of the corpus, not of overlap
   in general, and that is worth writing down:** actor files average 5.8
   chunks against 4.96 H2 sections (1,676 chunks over 289 eligible files;
   4.96 H2s counted over all 291 `problems/actors/*.md`), so ~85% of chunks are a section's *first*
   chunk and overlap contaminates nearly all of them with the previous
   section's tail. Part of the measured AUC loss is also a labelling artefact
   — an overlapped chunk keeps its host section's label while genuinely
   containing the previous section's text, so retrieving it scores as a false
   positive even though an extraction model would be right to read it.
   Neither correction changes the decision: neighbour expansion dominates
   overlap on both axes (100% straddle repair, zero embedding contamination).
   They matter only for not over-generalising "overlap is bad" to a
   differently-shaped corpus — the fetched web pages the worker will really
   chunk are longer than these actor files and may not have this property.

   **Shipped** as `worker/passages.py:expand_neighbours()` +
   `NEIGHBOUR_RADIUS = 1` (`worker/config.py`), called inside `select()`
   *before* `_cap_tokens` — the cap has to see the expanded set or neighbour
   tokens overrun `PASSAGE_TOKEN_CAP` silently. `03-worker.md` §7's prose and
   constants table are updated in place, marked superseded rather than
   rewritten. **Measured since, by PoC-2's prompt builder: 2.01× and 2.33×
   passage tokens on two real page sets** (§2 finding 7) — the bottom of
   PoC-1d's "up to 3×", and obtainable with no LLM call, since prompt size
   is a deterministic function of selection. What that costs in *reading* —
   whether fewer distinct chunks fitting the cap loses source diversity or
   answers — still needs track E end to end. `select()` takes
   `neighbour_radius=0` so that comparison has a baseline.

4. **§7's "a source that made it through set cover is never silently
   unread" does not hold, because it is a rule about the cap, not about
   selection.** `worker/passages.py:_cap_tokens` implements it exactly as
   written — over the chunks selection already chose. But top-k per bucket
   ranks the whole pool globally, so a source whose chunks never reach any
   bucket's top-k is in the prompt zero times, having been dropped by
   nothing. PoC-2's setup run selected chunks from 2 of 4 fetched sources,
   before any LLM call — this is a property of `select()`, observable without
   the model. Set cover can hand stage 5 five sources and stage 6 see two.

   Whether that is a defect is genuinely open: retrieval may be right that
   those pages say nothing about any question. What is not open is that the
   outcome is currently unstated and unmeasured while §7 reads as though it
   cannot happen. Two consequences for the build: `MAX_SOURCES` is an upper
   bound on sources *offered*, not sources *read*, so the §12 cost model and
   any "n sources agreed" reading of the `finding` table are both denominated
   in the wrong number; and track D's set-cover work is partly wasted effort
   if stage 5 silently discards what cover bought. Track E should log
   sources-in-prompt against sources-fetched per candidate — one integer,
   written during pass 1, in the same spirit as §11c's counters — before
   anyone decides to force per-source coverage. `03-worker.md` §7 is
   annotated in place.

---

## 4. One correction to the cost model

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

## 5. Build tracks

`F1` is the spine (§1a). Everything else waits on it, and it is small enough
that waiting is cheap.

| Track | New files | Touches | Needs | Degrades to | Status |
|---|---|---|---|---|---|
| **F1** question registry | `worker/questions.py` | — | — | — (blocking) | **SHIPPED** |
| **A** problem emission | — | `worker.py` `_emit`, `resolve.py` | — | today's behaviour: unresolvable edge dropped | **SHIPPED, inert** |
| **B** depth tier | `worker/depth.py` | `worker.py` intake | F1 | everything `tracked` | **SHIPPED, inert** |
| **C** chunk + passage | `text/chunk.py`, `worker/passages.py` | `worker/config.py` | F1, PoC-1, PoC-3 | first-N-chars per source, capped (§13) | **SHIPPED, inert (not wired)** |
| **D** search | `engine/search/` — provider adapter, `families.yaml`, `fuse.py`, `cover.py` | — | F1, PoC-0 | the candidate's own URL as single source (§13) | not started |
| **E** extract + ledger + counters | `worker/extract.py` | `prompts.py`, `worker.py` `run_batch` | F1, C, D, PoC-2 | — | not started |

A, C and D are genuinely concurrent once F1 lands. B is small enough to ride
with A. A is also the one track with no dependency at all — `03-worker.md` §16
puts it first for that reason, and it stays first here.

### Two holes found by the user, not covered by any track above

1. **Gate 2 runs only on the seed URL** (`worker/worker.py:504-521`, inside
   `if cand["url"]`). Track D produces 1-5 search-sourced URLs and none of them
   get a gate-2 confirmation pass. **PoC-2 hit this from the other end**
   (§2): fed the real recorded pool for one actor, the top-scoring results
   include a currency converter, a mountain-bike site and a Japanese
   Wikipedia article about a large number, several of which fetch `ok` with
   over a thousand words. Unfiltered, they become `[Sn]` blocks in the
   extraction prompt. The hole is not theoretical and it is not rare. This got no track of its own because the
   fix site is `run_batch`, which the rule below reserves for E — so the split
   is: **D ships the source-confirmation policy as a testable, pure function;
   E wires it.** `gate2.confirm(conn, ...)` takes a connection, so it is not
   pure as it stands; D's part is the policy layer — which sources to confirm,
   what each verdict does to the source set — not the DB-touching call itself.
2. **`finding` lacks `source_id` and `chunk_ref`** (`store/schema.sql:308-317`).
   Its own preceding comment states the table exists so a later reviewer can
   see "every source that spoke to a question and where they agreed or
   disagreed" — a bare `source_url` string cannot support that once a page has
   multiple chunks. This is the table failing its stated purpose, not a
   missing §9 feature. Assigned to track E as a schema migration, explicitly.

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

### Freeze five contracts before the tracks start

Concurrent tracks that share a type and not a definition of it diverge, and the
divergence surfaces at integration, which is the worst place for it.

1. **`SearchResult`** — `(rank, url, title, snippet, native_score | None)`, plus
   `unresponsive_engines` recorded per query (§4 obligation 2). `rank` derives
   from SearXNG's `score`, never the JSON list index (§4).
2. **The `questions.py` registry shape** — id, kind (`problem` / `actor`), the
   question text used as the `query:` string, and which depth tier asks it (the
   `registry` identity subset vs. the full set). Shipped shape (§1a) is richer
   than this: `question:` and `retrieval_query:` as separate fields, plus
   `retrieval:` and `bucket:` — E should read `questions.yaml` directly rather
   than re-deriving this contract.
3. **`Chunk`** — text, source id, ordinal, token count. The ordinal is what
   makes `chunk_ref` (§9) possible without persisting a vector (§1b).
4. **The stage-6 response JSON** (§8 verbatim), with `source_id` required on
   every answer.
5. **The `chunk_ref` format.** Track C shipped `f"{source_id}:{ordinal}"` —
   frozen by fact, not by prior agreement. E must conform to this rather than
   choose its own when it does the `finding` migration above.

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

## 6. What has shipped

**F1** (`engine/questions.yaml`, `engine/worker/questions.py`,
`engine/tests/test_questions.py`), **track A** (`engine/worker/problem_emit.py`),
**track B** (`engine/worker/depth.py`), **track C**
(`engine/text/chunk.py`, `engine/worker/passages.py`) — plus track C's
follow-up, **neighbour expansion** (`expand_neighbours()` +
`NEIGHBOUR_RADIUS`, §3 correction 3), which settles `CHUNK_OVERLAP` at 0 and
closes the last open parameter in the chunking stage. 283 tests passing, 14
skipped.

**The important caveat: A, B and C are all tested but INERT.** None of them is
reachable from a real run yet.

- **A**'s gate signals read an `edge["signals"]` key that `prompts.py` does
  not emit yet — `worker/problem_emit.py`'s `signals_from_edge()` always
  returns four `None`s against real data today, by construction, until E's
  extraction prompt starts writing that key.
- **B**'s requeue logic has no call site — nothing in `run_batch` invokes it.
- **C** is not wired into the pipeline at all — nothing calls `chunk()` or
  `select()` from `worker.py`.

All three wait on E, so **E carries more integration risk than the track table
in §5 implies** — it is not just "the extract+ledger+counters track," it is
the point where three already-shipped, already-tested tracks first meet real
data.

Also: A and B's feature flags became environment variables
(`WORKER_PROBLEM_EMISSION`, `WORKER_DEPTH_TIER` — both in `worker/worker.py`,
default on) rather than `run_batch` parameters, because `run_batch` was
off-limits per the rule in §5 (*only track E edits `run_batch`*). This is a
workaround, not the final shape — E should convert both to call-site
parameters when it does its integration pass, rather than leaving pipeline
behaviour toggled by process environment.

---

## 7. Sequence

```
PoC-0  ‖  PoC-1  ‖  PoC-3          mutually independent, no shared code
            ↓
       PoC-1b  ‖  PoC-1c            added after PoC-1: phrasing, then bucketing
            ↓
           F1                       engine/questions.yaml — SHIPPED
            ↓
  (A + B)  ‖   C   ‖   D            three tracks, pure functions only
   SHIPPED   SHIPPED  not started
            ↓
          PoC-2                     instrument built (poc2_extract.py), not
                                       yet run; free rung only, by decision
            ↓
            E                       the only edit to run_batch — wires A, B, C, D together
            ↓
     counters run on real candidates
            ↓
   the multi closing rule (§1d)       gates *reading* counter 1, not writing it —
                                       narrower now: 5 of 35 questions are inference-
                                       only and never enter this bookkeeping (PoC-1c)
            ↓
  §7 constant sweep, then the bandit
```

The last line is last for the reason §16 already gives: both need
realised-coverage numbers that do not exist until the pipeline has run against
real candidates. Tuning before then is tuning against a guess.

PoC-1b and PoC-1c were not anticipated when this plan was first written; they
sit between PoC-1 and F1 because PoC-1's own results (phrasing sensitivity,
question groups sharing a section) raised questions cheap enough to answer
before committing F1's schema, and F1 shipped with both PoCs' findings already
folded in (`retrieval_query:`, `retrieval:`, `bucket:`).

The closing rule sits where it does for a different reason: it is cheap to
decide and nothing is blocked by deferring it, but counter 1 is **misleading**
rather than merely absent until it lands (§1d). Deciding it late is fine;
reading the counter early is not.

---

## 8. What this plan does not settle

Settled since this was first written, removed from this list: §1a (SHIPPED),
§1b (DECIDED — ephemeral), whether the chunker is real (SHIPPED, track C),
§7's numeric budget claim (PoC-3: holds), whether set cover survives (PoC-0:
yes, survives, build it).

Still open:

- **§1d / `03-worker.md` §14** — the closing rule for a `multi` question.
  Needed before §11c's counter 1 is read, not before it is written. Narrowed
  by PoC-1c: 5 of 35 questions are inference-only and never enter this
  bookkeeping at all.
- **The `unresponsive_engines` floor** — still open, and now correctly posed:
  §3 correction 2 establishes it must be defined on engines *answering*, not
  engines failing, since 99% of PoC-0b's queries carried ≥1 failure. The
  number itself is still deliberately not guessed here.
- **Whether §11b exists at all** — the counters decide, after E.
- **What neighbour expansion costs in answers** — narrowed. The *token* half
  is measured: 2.01× and 2.33× on two real prompts (§2 finding 7), not the
  3× PoC-1d feared. What stays open is whether that loses anything worth
  having — fewer distinct chunks fit `PASSAGE_TOKEN_CAP`, and only track E
  running selection plus extraction end to end can say whether source
  diversity or answered questions drop for it. `NEIGHBOUR_RADIUS` is the
  dial and `select(..., neighbour_radius=0)` the baseline.
- **Whether the free rung can hold `[Sn]` discipline** — PoC-2's central
  question, still unanswered, and now knowingly answerable only for that one
  rung (§2 finding 4). One malformed response on one call is the entire
  evidence base.
- **The `money`-family search-coverage gap (28%, PoC-0b) is accepted, not
  fixed.** Unlike `failure` (28%, recommended as a structural absence to stop
  querying for), `money` is a question whose answer the platform genuinely
  wants — funds and orgs simply don't reliably publish their own funding
  figures in a way general web search surfaces. No track above addresses this;
  it is a known ceiling on stage 1-2 coverage for that one family, carried
  forward rather than solved.
