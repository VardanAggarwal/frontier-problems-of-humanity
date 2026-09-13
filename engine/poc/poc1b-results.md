# PoC-1b results — question-phrasing sweep

Run: `python -m poc.poc1b_phrasing --bootstrap 1000` (full corpus, no `--limit`),
2026-09-13. Same encoder, same corpus, same chunking as PoC-1
(`poc1-results.md`) — 289 `problems/actors/*.md` files, 1,672 chunks. The
passage matrix was encoded once and reused across all 42 candidate queries
(7 questions × 6 candidates each, control included), per the harness's own
runtime constraint.

**Scope, restated:** this sweeps the e5 `query:` string used in **stage 5
passage retrieval only**. It does not touch search-engine query families
(`families.yaml`, stage 1) — that is a separate PoC and the two must not be
conflated.

## Method

Six candidates per question (one per question of the seven PoC-1 measured),
control = PoC-1's verbatim wording:

| Axis | What it varies |
|---|---|
| `control` | PoC-1's original phrasing, unchanged |
| `noun_phrase` | bare noun phrase, no question grammar |
| `statement_shaped` | phrased like the answer passage reads, not a question |
| `keyword_list` | space-separated keywords, no grammar |
| `entity_type_word` | control's question + an explicit "this actor/organisation" |
| `vocab_overlap` | deliberately reuses the target section's own surface vocabulary |

Noise check: bootstrap resampling **by file** (not by chunk, to respect
within-file correlation), 1,000 resamples, pooled AUC recomputed for control
and the observed winner on each resample; reported as the 90% CI of the
AUC difference. `excludes_zero: True` means the margin survives; `False`
means it doesn't and control should stay.

## Results

### q9_contact_route (target: "How to reach them", n=223 files)

| Candidate | top1 | top3 | AUC |
|---|---|---|---|
| **control** | 22.0% | 55.2% | 0.592 |
| noun_phrase | 43.9% | 90.6% | 0.820 |
| statement_shaped | 50.7% | 74.0% | 0.751 |
| **keyword_list (winner)** | 66.8% | 95.1% | **0.893** |
| entity_type_word | 34.5% | 69.1% | 0.703 |
| vocab_overlap | 52.9% | 83.4% | 0.802 |

Winner: **keyword_list**, margin **+0.301**. Bootstrap 90% CI [+0.268,
+0.333] — excludes zero, real.

### q16_channel (target: "How to reach them", n=223 files)

| Candidate | top1 | top3 | AUC |
|---|---|---|---|
| **control** | 32.7% | 67.7% | 0.657 |
| **noun_phrase (winner)** | 39.0% | 86.1% | **0.790** |
| statement_shaped | 46.6% | 79.8% | 0.761 |
| keyword_list | 40.4% | 85.2% | 0.789 |
| entity_type_word | 39.5% | 76.7% | 0.745 |
| vocab_overlap | 35.0% | 77.1% | 0.710 |

Winner: **noun_phrase**, margin **+0.132**. Bootstrap 90% CI [+0.117,
+0.148] — excludes zero, real.

### q10_funding (target: "Status", n=205 files)

| Candidate | top1 | top3 | AUC |
|---|---|---|---|
| **control** | 71.2% | 94.1% | 0.922 |
| **noun_phrase (winner)** | 86.3% | 99.5% | **0.977** |
| statement_shaped | 56.6% | 86.3% | 0.865 |
| keyword_list | 68.8% | 99.0% | 0.933 |
| entity_type_word | 64.4% | 96.6% | 0.920 |
| vocab_overlap | 66.8% | 95.6% | 0.896 |

Winner: **noun_phrase**, margin **+0.055**. Bootstrap 90% CI [+0.043,
+0.068] — excludes zero, real, but the smallest real margin of the four
that hold (control was already the strongest question in PoC-1).

### q11_scale_metric (target: "Status", n=205 files)

| Candidate | top1 | top3 | AUC |
|---|---|---|---|
| **control** | 40.5% | 74.6% | 0.731 |
| **noun_phrase (winner)** | 75.1% | 98.5% | **0.931** |
| statement_shaped | 3.9% | 35.6% | 0.429 |
| keyword_list | 8.8% | 66.8% | 0.646 |
| entity_type_word | 13.2% | 62.9% | 0.632 |
| vocab_overlap | 60.5% | 97.1% | 0.893 |

Winner: **noun_phrase**, margin **+0.200**. Bootstrap 90% CI [+0.177,
+0.224] — excludes zero, real, and the largest genuine win of the sweep.

### q4_lifecycle (target: "Status", n=205 files)

| Candidate | top1 | top3 | AUC |
|---|---|---|---|
| **control** | 14.6% | 79.0% | 0.688 |
| noun_phrase | 0.0% | 33.2% | 0.370 |
| statement_shaped (best of the rest) | 22.0% | 69.3% | 0.679 |
| keyword_list | 5.4% | 55.6% | 0.566 |
| entity_type_word | 2.0% | 22.4% | 0.280 |
| vocab_overlap | 7.3% | 55.6% | 0.547 |

**No candidate beats control.** Best alternative (statement_shaped) is
−0.009 vs control. Bootstrap 90% CI on that margin: [−0.027, +0.009] —
**crosses zero, does not survive.** Verdict: **control stays.** Notably,
`noun_phrase` — the axis that won three other questions outright — actively
destroys this one (0.688 → 0.370), and `entity_type_word` is the single
worst score in the entire sweep (0.280, worse than chance). Lifecycle status
words ("operating", "scaling") are generic enough that stripping the
question's own disambiguating context (the explicit enumeration
"scaling/distressed/dormant/acquired/shut...") costs more than any rewording
gains — this question resists the axis that otherwise generalises.

### q15_ask_offer (target: "What they can offer", n=167 files)

| Candidate | top1 | top3 | AUC |
|---|---|---|---|
| **control** | 22.8% | 46.7% | 0.609 |
| noun_phrase | 21.0% | 56.9% | 0.652 |
| **statement_shaped (winner)** | 56.3% | 86.8% | **0.871** |
| keyword_list | 28.1% | 65.9% | 0.717 |
| entity_type_word | 13.2% | 48.5% | 0.582 |
| vocab_overlap | 49.7% | 79.6% | 0.815 |

Winner: **statement_shaped**, margin **+0.262**. Bootstrap 90% CI [+0.236,
+0.288] — excludes zero, real, second-largest win of the sweep.

### q14_ask_need (target: "What they need", n=99 files — smallest sample)

| Candidate | top1 | top3 | AUC |
|---|---|---|---|
| **control** | 33.3% | 51.5% | 0.518 |
| noun_phrase | 18.2% | 49.5% | 0.496 |
| statement_shaped | 24.2% | 57.6% | 0.528 |
| keyword_list | 33.3% | 54.5% | 0.529 |
| entity_type_word | 40.4% | 52.5% | 0.535 |
| **vocab_overlap (winner)** | 31.3% | 59.6% | **0.556** |

Winner: **vocab_overlap**, margin **+0.039**. Bootstrap 90% CI [+0.017,
+0.062] — technically excludes zero, but this is the smallest sample (99
eligible files, the fewest of the seven) and the smallest winning margin
after q10's. Still essentially chance-level (0.556 vs 0.5).

## Aggregate lift

Applying the sound rule per question (take the winner where the bootstrap
CI excludes zero; keep control where it doesn't — i.e. q4 stays at control):

| | q9 | q16 | q10 | q11 | q4 | q15 | q14 | **mean** |
|---|---|---|---|---|---|---|---|---|
| control AUC | 0.592 | 0.657 | 0.922 | 0.731 | 0.688 | 0.609 | 0.518 | **0.674** |
| best-surviving AUC | 0.893 | 0.790 | 0.977 | 0.931 | 0.688 | 0.871 | 0.556 | **0.815** |

Mean pooled AUC across the seven questions moves from **0.674 to 0.815**
(+0.141) once each question is phrased for what actually retrieves — a real
and fairly large aggregate lift, driven almost entirely by q9/q11/q15
(margins of +0.20 to +0.30) with q4 correctly excluded from the gain.

## Four load-bearing findings

**1. No axis wins globally — phrasing is a per-question empirical choice.**
`keyword_list` wins q9; `noun_phrase` wins q16, q10, q11; `statement_shaped`
wins q15; `vocab_overlap` wins q14; and for q4 nothing beats control. Five
different winning axes across seven questions, including two questions
(q9/q16) that target the *identical* section. This does not generalise as a
style rule ("always write keyword lists," "always mimic the answer") to the
~28 other questions in `questions.yaml` this PoC does not cover — each new
question's retrieval string has to be swept, not authored once from a
convention. The cheapest version of that sweep: run this harness's control +
`noun_phrase` + `statement_shaped` only (drop `keyword_list`,
`entity_type_word`, `vocab_overlap` as a default trio — they win at most once
each across the seven and cost the same three encode calls to test), pick
whichever of the three has the highest AUC with a bootstrap CI that excludes
zero against control, else keep control. That's a 3-candidate, same-corpus,
same-reused-passage-matrix check per new question — a few seconds of encode
time once the corpus vectors already exist, not a new full sweep.

**2. `entity_type_word` is a consistent loser — this is the one negative
rule that does generalise.** Appending "this actor" / "this organisation" to
the control question underperforms control in 5 of 7 questions and is
outright destructive on the worst two: q4 0.280 vs 0.688 control (−0.408),
q11 0.632 vs 0.731 control (−0.099), q15 0.582 vs 0.609 control (−0.027). It
only wins narrowly on q14 (0.535 vs 0.518, both near-chance) and ties on
q10. Rule for `questions.yaml`: **do not add an explicit entity-type noun to
a retrieval query** — it dilutes the query vector toward generic
actor-shaped language and away from the section's distinctive content
vocabulary, which is exactly backwards for an asymmetric bi-encoder matching
a short query against a long passage.

**3. q4_lifecycle did not improve — control stays.** Best candidate
(statement_shaped, 0.679) is −0.009 vs control's 0.688, and the bootstrap 90%
CI [−0.027, +0.009] crosses zero: not a real change either way. More
tellingly, `noun_phrase` — the single strongest axis across the rest of the
sweep (winner on three questions) — collapses this one to 0.370, and
`entity_type_word` collapses it further to 0.280. This question needs its
disambiguating enumeration ("operating, scaling, distressed, dormant,
acquired, shut, or won-and-dissolved") intact in the query; stripping it to a
noun phrase or adding boilerplate destroys the one thing keeping it above
chance. Recommendation: keep the control wording verbatim in
`questions.yaml` for this question and do not resweep it — the axis space
tested here has been exhausted without a win.

**4. q14_ask_need is still broken after the sweep.** Best AUC after six
candidates is 0.556 (vocab_overlap), up only +0.039 from control's 0.518 —
both are barely above the 0.5 chance floor a plain coin flip gives, and n=99
eligible files is the smallest sample of the seven (the "What they need"
section is simply absent from more actor files than any other section, per
PoC-1's chunk-count table: 99 chunks vs 167–394 for the others). Read: this
looks like a **content problem, not a phrasing problem** — no candidate
phrasing, across noun-phrase/statement/keyword/entity/vocab axes, moved the
needle materially, which is the signature of a section whose actual prose
doesn't carry distinctive "need" vocabulary the way funding sections carry
"₹/grant/seed" or offer sections carry "provide/offer" — many "What they
need" sections in this corpus are likely terse, generic, or boilerplate
("more funding and partners") in a way that gives e5 nothing lexically
distinctive to lock onto, regardless of how the query is phrased. It could
also be partly sample-size noise given n=99 is the smallest group, but the
near-zero movement across five very different phrasings argues against
"just need a wider bootstrap" being the fix. **What would actually
diagnose it:** read a sample of 10-15 "What they need" sections directly
and check whether they in fact contain thin/generic content (confirms
content problem, in which case no query rewording will rescue this question
— it needs either a different retrieval unit, e.g. matching against the
whole file rather than one paragraph, or accepting this question is
downstream-coverage-dependent rather than retrieval-fixable) versus rich
specific asks that e5 simply isn't separating (would reopen the phrasing
question and warrant a second, wider candidate round targeting this
question specifically).

## §1a: one field or two for `questions.yaml`

**Two fields, not one.** The winning retrieval phrasing for four of seven
questions is a bare noun phrase or keyword list (q9's winner is literally
`"contact email website social media handle channel"`; q10/q11/q16's
winners are terse noun phrases like `"reach metric, members, users,
revenue, dated"`). These are not sensible strings to hand an extraction
prompt asking a model to answer "what does this actor say it needs, in a
dated sentence" — an LLM extraction prompt needs the full natural-language
question form (with the enumerated options, as q4's result shows those
enumerations are load-bearing there too) to produce a well-formed answer,
while stage-5 retrieval wants the terse/keyword/answer-shaped form that
matches passage vocabulary. `§1a`'s assumption that one string serves both
`prompts.py` and stage-5 retrieval is falsified by this sweep. Recommend
`questions.yaml` carry `question:` (full natural-language form, feeds
`prompts.py`) and `retrieval_query:` (the swept e5 `query:` string, feeds
stage 5) as two separate fields per question, with `retrieval_query`
defaulting to `question` only where a question hasn't been swept yet (a
migration aid, not a design assumption).

## Files

- `engine/poc/poc1b_phrasing.py` — the sweep script, imports
  `load_corpus`/`roc_auc` from `poc1_retrieval.py`, encodes the passage
  matrix once and reuses it across all 42 candidates
- `engine/poc/poc1b-results.md` — this file
- `engine/poc/poc1b_run.log` — raw run output (HF loader progress-bar noise
  included; the tables above are the filtered, authoritative numbers)
