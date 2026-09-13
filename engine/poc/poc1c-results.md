# PoC-1c results — can question-level retrieval be merged into per-bucket queries?

Run: `python -m poc.poc1c_buckets --bootstrap 1000` (full corpus, no `--limit`),
2026-09-13. Reuses `poc1_retrieval.py`'s chunking/AUC and `poc1b_phrasing.py`'s
candidate-phrasing + file-level bootstrap machinery, unmodified. Raw run
output: `engine/poc/poc1c_run_output.txt`. Script: `engine/poc/poc1c_buckets.py`.

Two corpora: 289 `problems/actors/*.md` files (1,672 chunks, six real H2
labels: Scope 290, How to reach them 285, Recent updates 282, Status 206,
What they can offer 168, What they need 151), and the 7 existing leaf files
under `problems/tier-failure-history/*/*/*.md` (129 chunks, `## A · Classification`
… `## E · Gap`).

**Sign convention, stated once:** in every table below, "shared beats
dedicated by X" / "shared loses X to dedicated" is written from the shared
query's point of view — a positive "beats" means the merge is free or better,
a "loses" means the merge costs AUC.

## 1. q4_lifecycle was scored against the wrong section

| Target | control AUC | best alt (axis) | best alt AUC | margin vs control | 90% CI | survives? |
|---|---|---|---|---|---|---|
| Status (PoC-1/1b's target) | 0.688 | statement_shaped | 0.679 | −0.009 | [−0.028, +0.010] | no — control stays, but low ceiling |
| **Recent updates** | 0.881 | **noun_phrase** | **0.919** | **+0.037** | **[+0.023, +0.052]** | **yes** |
| Status ∪ Recent updates | 0.887 | keyword_list | 0.856 | −0.031 | [−0.040, −0.022] | no — control best, but below Recent-updates-alone's winner |

Reading a handful of real sections confirmed the hypothesis before trusting
the number: `## Status` in this corpus is almost entirely two fixed bullets
(**Funding**, **Scale metric** — i.e. exactly q10/q11's content) and rarely
says anything about operating/scaling/dormant state. `## Recent updates` is a
reverse-chron dated log, and it is where record-creation, channel-search and
status-change notes actually live — including phrases close to the
enumeration itself.

**Verdict: q4 belongs to `Recent updates`, not `Status`.** The union target is
a red herring — it dilutes rather than helps, because it forces the query to
also match `Status`'s funding/scale vocabulary. Best result overall: retarget
q4 to `Recent updates` **and** rephrase to `noun_phrase` ("lifecycle status
and as-of date") — AUC 0.688 → 0.919, +0.231, from fixing the target and the
phrasing together. **The proposed `status` bucket (q4, q10, q11) is wrong as
specified** — q4 moves out, leaving `status` as {q10, q11} against `Status`.

## 2. Cross-apply test: reach and status (post-relabel)

Every candidate from every question in the bucket was scored against the
bucket's section; the bucket's shared query is simply the best-scoring
candidate across that whole pool. Because the shared query is chosen this
way, it can only tie or beat each question's own dedicated best on the
section it was measured on — the number below is how much it **beats** the
weaker question, not a cost.

| Bucket | target | shared query | shared AUC | q9/q16 or q10/q11 dedicated best | shared vs dedicated |
|---|---|---|---|---|---|
| **reach** (q9, q16) | How to reach them | `keyword_list`: "contact email website social media handle channel" (= q9's own winner) | 0.893 | q9 dedicated 0.893 / q16 dedicated 0.790 | ties q9, **beats q16 by +0.103** |
| **status** (q10, q11) | Status | `noun_phrase`: "funding source, scale, latest round or grant, date" (= q10's own winner) | 0.977 | q10 dedicated 0.977 / q11 dedicated 0.931 | ties q10, **beats q11 by +0.046** |

**Both mergers are free.** One query per bucket loses nothing against either
question's dedicated best, and for the weaker of each pair (q16, q11) the
shared query is actually *better* than that question's own dedicated query
was in isolation — the bucket-wide search over candidates found a stronger
query than the single-question sweep had tried for that particular question.

## 3. Buckets with no single H2 — identity and viability

### Identity (q1, q2, q3, q5, q6, q7, q8)

Ground-truthed by inspection first: the lead **"What they do."** paragraph
(chunk label `""`, before any H2) carries what the actor does, org/individual
framing, founding, and often geography and role. `## Scope` is *not* clean
identity prose — it's mostly typed relationship edges (`funds →`,
`board ←`, `funded-by →`) or leaf-specific notes, which is why every
candidate's AUC on Scope-only is near or below chance for the descriptive
questions (q1 control: preamble 0.917 vs Scope-only 0.335).

| Question | preamble-only AUC | Scope-only AUC | preamble∪Scope AUC |
|---|---|---|---|
| q1_one_line | **0.917** | 0.335 | 0.659 |
| q2_type | 0.516 | 0.466 | 0.489 |
| q3_legs | 0.586 | 0.451 | 0.523 |
| q5_ecosystem_role | 0.539 | 0.552 | 0.557 |
| q6_affected_led | **0.777** | 0.477 | 0.661 |
| q7_representation_unit | 0.430 | 0.493 | 0.451 |
| q8_geography | **0.959** | 0.316 | 0.674 |

Preamble is unambiguously the right target region where the question is
answerable at all, and the union only dilutes it. But **q2, q3, q5, and q7
sit at or below chance (0.43–0.59) against every one of the three targets
tested, and no bucket-shared phrasing rescues them either** (the
shared-candidate sweep's best score across the three was 0.657, still
chance-adjacent). This is the most important result in this PoC and it is
**not a bucketing failure**: these four are enum classifications inferred by
reading the *whole record* (type, legs, ecosystem role, representation unit
are judgment calls synthesizing funding, scope, and scale — not facts stated
in one localized passage). No `query:` string retrieves a passage for a
judgment that isn't written down anywhere as a passage.

**Design conclusion:** split the actor question set into **retrieval
questions** (q1, q6, q8 — content genuinely localized in the preamble, share
one query, AUC 0.78–0.96) and **inference questions** (q2, q3, q5, q7 —
skip retrieval; answer them from whatever passages the retrieval questions
already pulled, including the preamble). This is a `questions.yaml` schema
consequence beyond the `question:`/`retrieval_query:` split PoC-1b already
established: some questions need a third property, e.g. `retrieval: false`,
that routes them to inference-over-context instead of a dedicated (or even
shared) retrieval call.

### Viability (q12, q13)

No dedicated H2 exists for viability/failure content at all — a direct grep
found viability vocabulary (unit economics, donor exit, "distressed") in only
~20/289 files and failure vocabulary in only ~10/289. Testing against
`Status` as the closest available proxy:

| Question | AUC vs Status | Read |
|---|---|---|
| q12_viability_note | 0.835 (control), 0.873 (noun_phrase) | Genuinely high — funding/scale-metric prose in `Status` substantively overlaps what "what makes them viable" asks, so this is a real signal, not an artifact. **q12 can fold into the `status` bucket** (retrieval-relevant, targets `Status`). |
| q13_failure_note | **0.243** | Below chance. Confirms the grep: failure content is not in `Status`, and per the corpus-wide search, barely exists anywhere in this corpus (~10/289 files). This is a **content/coverage gap, not a phrasing or bucketing problem** — treat q13 as inference-only (or, more honestly, currently unanswerable from this corpus) rather than giving it a dedicated retrieval. |

## 4. Problem side (7 leaf files) — directionally consistent, wide CIs

n=7 files throughout; every bucket's shared query (chosen as the bucket-wide
best) ties or beats every dedicated query, same pattern as the actor side,
but the bootstrap CIs are wide and in three cases (bucket A/p7, C/p12, D/p19,
E/p16, E/p18) narrow enough to include a genuine tie rather than a clear win.
**Report as directionally consistent with the actor-side result, not as
independent confirmation** — 7 files cannot carry that weight on their own.

| Bucket | target | shared question (query) | shared AUC | weakest dedicated in bucket | shared vs weakest |
|---|---|---|---|---|---|
| A Classification | q5–8 | p7_channel | 0.957 | p8_satisfier_relation 0.818 | beats by +0.138 (CI excludes 0) |
| B Evidence | q9–11 | p9_magnitude | 0.644 | p10_diff_vuln 0.225 | beats by +0.419 (CI excludes 0) — but p10 itself is a broken question here, not just a bucketing artifact |
| C Diagnosis | q12–14 | p14_blocker | 0.833 | p13_burden_note 0.575 | beats by +0.258 (CI excludes 0) |
| D Who works it | q15,19 | p19_who_working | 0.740 | p15_representation_verdict 0.628 | beats by +0.112 (CI excludes 0) |
| E Gap | q16–18 | p16_gap_kind | 0.875 | p17_gap_missing_leg 0.710 | beats by +0.165 (CI excludes 0) |

## 5. Revised bucket list and the headline retrieval count

**Buckets that survive as proposed:** `reach` (q9,q16), `offers` (q15, alone),
`needs` (q14, alone — still chance-level per PoC-1b, a content problem not
fixed by bucketing), and problem-side A–E.

**Buckets that changed:**
- `status` becomes {q10, q11, **q12**} against `Status` — q4 moves out, q12
  (viability) moves in.
- q4 becomes its own single-question bucket against **`Recent updates`**
  (retargeted from `Status`), phrased as `noun_phrase`.
- `identity` splits: **identity-retrieval** {q1, q6, q8} against the preamble
  (shares one query), and **identity-inference** {q2, q3, q5, q7} — no
  retrieval, answered from context already fetched.
- q13 (failure_note) is inference-only / flagged as a corpus coverage gap,
  not given a dedicated retrieval.
- Problem-side `core` questions (one_line, status, geography, needs_legs —
  outside A–E) were not tested here; by the same logic as actor identity they
  are almost certainly inference-only (lead prose + title), not retrieval
  targets, but that is untested, not assumed.

**Headline count**, actor side (16 questions): 6 retrievals — reach, status
{q10,q11,q12}, q4/Recent-updates, needs, offers, identity-retrieval — cover
11 questions; 5 questions (q2,q3,q5,q7,q13) are inference-only, 0 retrievals.
Problem side (19 questions, 15 tested): 5 retrievals (A–E) cover all 15
A–E questions; the 4 untested core questions are presumptively inference-only.

**Total: ~35 per-question retrievals → 11 per-bucket retrievals**, matching
the number the task hypothesized, but reached with a different bucket
composition than proposed (q4 relabeled, viability split across two fates,
identity split into retrieval vs inference) rather than the original six
buckets taken at face value.

**Recommendation: bucket — but encode `retrieval: true/false` per question in
`questions.yaml` before merging anything**, so the merge only ever happens
within the subset of questions the corpus can actually answer by retrieval.
Merging a genuinely inference-shaped question into a bucket (as the original
proposal would have done for q2/q3/q5/q7/q13) would have hidden a coverage
gap behind a bucket that "worked" on its retrievable members.

## Files

- `engine/poc/poc1c_buckets.py` — the script (imports `poc1_retrieval` and
  `poc1b_phrasing` directly, encodes each corpus's passage matrix once)
- `engine/poc/poc1c-results.md` — this file
- `engine/poc/poc1c_run_output.txt` — full raw run output (authoritative
  numbers; `poc1c_run.log` has the same content plus HF loader progress-bar
  noise)
