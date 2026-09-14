# PoC-2d — does the enlarged schema still parse?

Spec + runner (`poc2d_schema.py`). Runs before PoC-2c, and 2c's result is
uninterpretable without it.

## Why this runs first

The 2026-09-14 prompt revision changed the batched schema in four ways at
once (commit "One prompt revision"): `claims` removed, `signals` filled on
problem emits, rule 5 and per-chunk `⟨Sn.k⟩` markers added, and the duplicate
schema block removed from `_EXTRACT_COMMON`. The only evidence the batched
prompt works at all is PoC-2's 95/95 attribution, measured on the prompt as
it stood before any of that.

2c is a one-observation-per-cell design scoring a single targeted question.
In it, a parse failure and a declined question are indistinguishable: both
produce `target_answered=False`. That ambiguity is exactly what made PoC-2
and PoC-2b uninformative, twice. So the schema gets measured on its own,
where a parse failure is the result rather than a confound.

## What it measures

Same five pinned fixtures, radius 1, free rung, no HTTP. One call per actor
on the baseline (live) system prompt — 5 calls — plus the same 5 on the
pre-revision prompt as a within-run control, reconstructed from git rather
than remembered.

| metric | definition | prior |
|---|---|---|
| `parsed` | response is a JSON object | PoC-2: 8/8 after one retry |
| `valid_ids` | answers carrying a source label in the given map | PoC-2: 95/95 |
| `answers` | count per call | PoC-2b: SELCO 10 of 17 |
| `chunk_cited` | answers carrying a parseable `chunk` marker | new, no prior |
| `chunk_resolved` | of those, ones resolving to a real `chunk_ref` | new |
| `chunk_wrong_source` | markers naming a source other than the answer's own | new — the failure rule 5's parser refuses |
| `signals_filled` | problem emits with ≥1 non-null of the four | new |
| `signals_uncounted` | emits using `uncounted` in magnitude | new — tests whether the "real value, not a null" rule reads |
| `claims_volunteered` | responses still emitting `claims` unasked | should be 0 |
| `output_tokens` | per call | the revision's token cost, measured |

## Read

- **`parsed` or `valid_ids` below the control** → the enlarged schema costs
  parse reliability, and 2c must not run until that is understood. This is
  the result the PoC exists to catch.
- **`chunk_cited` near zero with `parsed` intact** → rule 5 is ignored rather
  than harmful. `chunk_ref` stays null, which is where it already was, and
  the rule should be reconsidered rather than kept as decoration.
- **`chunk_wrong_source` non-zero** → the refusal path in
  `resolve_chunk_marker` is load-bearing, not defensive.
- **`signals_filled` zero** → §10's capture-while-the-page-is-open argument
  does not survive contact, and the orchestrator will have to refetch after
  all. That is worth knowing before an orchestrator is built on the
  assumption.

## Conditions

Pinned fixtures, free rung, cell-level transport retry x3, foreground, one
run. Full call envelope saved per call, as 2c does.
