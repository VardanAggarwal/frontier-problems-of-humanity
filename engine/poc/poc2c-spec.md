# PoC-2c — reconciliation, measured where it can actually appear

Spec only. Not run. Supersedes PoC-2's and PoC-2b's reconciliation question;
leaves their attribution and parse results standing.

## Why 2 and 2b could not answer the question

PoC-2 asked whether a batched `[S1]…[Sn]` call reconciles a planted
contradiction. It measured 0/8. PoC-2b removed the baseline prompt's schema
contradiction (rule 1 forbade merging sources; rule 2 required naming two
source ids in one answer, which the schema had no slot for) via two variants,
and measured `disagreements[]` empty 3/3.

Both numbers are uninformative, for one reason: **the plant was never aimed at
a question the sheet asks.** `FIGURE_RE` (`poc2_extract.py:69`) scrapes any
number-plus-unit from an arbitrary passage sentence and doubles it. In the 2b
run it selected `2020→4040` (a *year*, via the `_YEAR_RE` last-resort path),
`2000→4000 people` (a protest turnout) and `3→6 billion` (loose prose). The
actor question set has exactly two numeric slots — `q10_funding` and
`q11_scale_metric` — and none of those three plants corresponds to either.
SELCO's V2 response answered 10 of 17 questions and omitted both numeric ones,
which rule 3 ("a question no source answers is absent") makes correct.

So the model was given a contradiction with nowhere to surface, and correctly
ignored it. The prompt variants were never the binding constraint.

A second defect compounds it: `marker` and `both_figures` scan
`json.dumps(data)` — the whole response, `edges[]` evidence strings included —
against a list containing `"vs"`, `"range"`, `"but "`, `"while "`
(`poc2_extract.py:252`). In 2b all three V2 calls scored `marker=True` while
`disagreements[]` was empty and a scan restricted to `answers` found zero
hits. Two of the three reconciliation metrics do not measure reconciliation.

## The design

**Two stages, so the planted figure is provably one the model reports.**

*Stage 1 — probe.* One extraction call per actor on the unmodified sources.
Record the answer to `q10_funding` and `q11_scale_metric`: its text, its
`source_id`, and the chunk it came from. If neither is answered, that actor is
**unusable for this PoC** — drop it and pick another, recording the drop. This
is the step 2 and 2b lacked: it establishes that a contradiction on this figure
has somewhere to land before spending a call on it.

*Stage 2 — targeted plant.* Take the stage-1 figure. Build a synthetic source
that states the same quantity, same unit, at a different value, attributed to a
different publisher, and append it as one more `[Sn]` block exactly as today.

**Plausibility, not absurdity.** Multiply by 1.35, not 2.0 (configurable
`PLANT_RATIO`). The repo's own precedent for a real disagreement is Delhi
82.2 vs 99.6 µg/m³ — a 1.21× spread between two administrative boundaries in
one report. A doubled value reads as a typo; the question is whether the model
flags a *credible* rival claim. Round to the source figure's own precision.
Never plant on a year, an ordinal, or a date: restrict the target to
`q10`/`q11` answers carrying a currency, a count, or a capacity unit.

**Variants.** Baseline / V1 / V2 as in 2b, unchanged, so 2c is comparable to it.

**Matrix.** 3 actors × 3 variants × 1 repeat = 9 scored calls, plus 3 probe
calls. Free rung.

## Scoring — only on the targeted question

Primary, all restricted to the answer for the stage-1 question id:

| metric | definition |
|---|---|
| `target_answered` | that `question_id` appears in `answers` at all |
| `target_both_values` | both the real and planted value appear **in that answer's text** |
| `target_both_ids` | that answer names both source ids (V1) — or a `disagreements[]` entry carries `value_a`/`value_b` matching the pair with both ids valid (V2) |
| `reconciled` | `target_both_values AND target_both_ids` |

`target_answered=False` is a **void cell, not a negative** — the model declined
the question, so reconciliation was never reachable. Report voids separately;
never pool them into the denominator.

Secondary, retained as diagnostics and **explicitly labelled unreliable** in any
results file: the legacy whole-blob `marker` and `both_figures`.

**Fix the scan while here.** Restrict `marker`/`both_figures` to `answers` plus
`disagreements`, not `json.dumps(data)`. Keep the old whole-blob value under a
separate key so 2b's numbers stay reproducible rather than silently restated.

## Run conditions

- **Pinned sources** (`--pinned`, per the fixture work): stage 1 and stage 2
  must see identical source text, and all three variants must share one prompt
  body. Live fetch makes that impossible — it broke a 2b run already.
- **Record the full call envelope** per call: system prompt, prompt body, raw
  response, parse error, model, input/output tokens, `truncated`, the stage-1
  target figure, and the planted value.
- **Cell-level retry.** The free rung transport-failed 2 of 9 calls in 2b
  (`Upstream error from Nvidia`). Retry a transport-failed cell up to 3 times
  before recording it as a hole; a hole is a void, not a negative. If holes
  exceed 2 of 9, the free rung is not adequate for a one-observation-per-cell
  design and the run should be repeated on a paid rung — cents at these prompt
  sizes.
- Foreground, single run, stdout to a scratch file.

## What each outcome means

- **V2 reconciles, baseline doesn't** → disagreement needs a structural slot.
  §8's batching justification holds, with a schema change attached.
- **V1 and V2 both reconcile** → the rule 1/rule 2 contradiction was the whole
  bug; prose fix is sufficient and no schema change is owed.
- **None reconciles, on a credible targeted plant with `target_answered=True`**
  → this is the result that falsifies §8. Batching over per-source calls was
  justified by reconciliation; if it does not happen when the contradiction is
  answerable, credible and instructed, the justification is gone and per-source
  calls with a reconciliation pass downstream become the cheaper design.

That third outcome is the one worth running the PoC for, and neither 2 nor 2b
could produce it.
