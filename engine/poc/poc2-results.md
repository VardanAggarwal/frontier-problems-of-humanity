# PoC-2 — does the batched `[S1]…[Sn]` extraction call attribute and reconcile?

Run 2026-09-13. Covers PoC-2 (the designed matrix) and PoC-2b (the
reconciliation prompt variants it forced). `04-worker-build-plan.md` §2,
`03-worker.md` §8.

**Verdict in one line: attribution passed outright; reconciliation was not
measured, because the instrument planted its contradiction where no question
could surface it.** The reconciliation follow-up is specced in
`poc2c-spec.md` and has not been run.

## Run conditions — and the gap in them

- **Free rung only.** `anthropic` and `google-genai` stay commented out in
  `requirements.txt:20-21`; the decision was to record the gap rather than
  install. Every call below is `nvidia/nemotron-3-super-120b-a12b:free` via
  OpenRouter, cost $0. §2's "run it on both rungs" is therefore **not
  satisfied**, and a free-rung failure cannot be separated from a
  prompt-design failure.
- **Sources drawn live**, so the source set is not reproducible run to run —
  the same actor draws different pages as sites fetch ok once and block the
  next. Every figure here is a sample of one page set.
- Fetches went to a scratch copy of `graph.db` under `poc/poc2-scratch/`; no
  tracked database was touched.
- 10 calls: 5 actors × 2 repeats, radius 1, `json_out=False` so parsing
  happens locally, one retry on each parse failure.

## Q1 — JSON parse rate

| | |
|---|---|
| calls | 10 |
| transport failures | 1 (upstream Nvidia error, not ours) |
| single-shot parse | **8/9** |
| one retry rescued | **1/1** |

§13's per-source retry is **validated**: the one malformed response was
rescued by a single retry, which is exactly the path §13 sizes.

The failure was **not prompt-size-driven**, and an earlier reading that
framed it that way was wrong. It fired at `prompt_chars=4082`, the second
*smallest* prompt in the matrix, while a call with a larger response (10,404
chars) parsed clean. The failed response ends mid-string inside an
`"evidence"` value — cut off, not malformed sampling — after degenerating
into a 289-line repetitive `dst_name`/`edge_kind`/`evidence` list.

**Data note — whether that cut was `max_tokens` or an upstream cut is
unresolved.** `llm.py:328` escalates on `truncated` (4096→8192→16384) before
the `json_out` check, so it should have fired; 8,784 chars is ~2.5k tokens,
under the 4,096 budget. Nemotron is a reasoning model and burns hidden CoT,
which would explain it. `truncated` was not recorded on PoC-2's rows; it was
added for 2b, where it read `False` on every call.

Observed prompt range: **2,099–5,865 chars**. The ~18k band that produced the
original session's parse failure is unsampled. Given the failure above landed
at 4k, prompt size is no longer the suspected variable, so this is a note
rather than a caveat on the rate.

## Q2 — source attribution — PASSED

| | |
|---|---|
| answers | 95 |
| carrying a valid `source_id` | **95/95 (100%)** |
| unknown id | 0 |
| no id | 0 |

§8 drops answers without a valid source id. At this scale the drop rate is
nil, and the coverage metric everything else is tuned against has no hole in
it. This is the strongest result in the PoC.

Secondary: answers concentrate on few sources — 1–3 distinct sources cited of
4–5 in the prompt.

## Q3 — reconciliation — NOT MEASURED

Planted-contradiction results, both runs:

| | baseline | V1 (prose fix) | V2 (`disagreements[]` slot) |
|---|---|---|---|
| PoC-2, 8 parsed calls | marker 0/8, planted cited 1/8 | — | — |
| PoC-2b, per variant | marker 0/2 | marker 1/2 | marker 3/3 |
| PoC-2b `disagreements[]` filled | n/a | n/a | **0/3** |

**None of these numbers answers the question.** Two defects, both in the
instrument:

**1. The plant was never aimed at a question the sheet asks.** `FIGURE_RE`
(`poc2_extract.py:69`) scrapes any number-plus-unit from an arbitrary passage
sentence and doubles it. In 2b it selected `2020→4040` (a *year*, via the
`_YEAR_RE` last-resort path), `2000→4000 people` (a protest turnout) and
`3→6 billion` (loose prose). The actor question set has exactly two numeric
slots — `q10_funding` and `q11_scale_metric` — and none of those plants
corresponds to either. SELCO's V2 response answered 10 of 17 questions and
omitted both numeric ones, which rule 3 ("a question no source answers is
absent") makes correct behaviour. The model was handed a contradiction with
nowhere to land and correctly ignored it.

**2. Two of the three reconciliation metrics do not measure reconciliation.**
`marker` and `both_figures` scan `json.dumps(data)` — the whole response,
`edges[]` evidence strings included — against a list containing `"vs"`,
`"range"`, `"but "`, `"while "` (`poc2_extract.py:252`). All three V2 calls
scored `marker=True` while `disagreements[]` was empty and a rescan
restricted to `answers` found **zero** hits. The 3/3 above is a false
positive.

**What 2b did establish.** The baseline system prompt contains a genuine
self-contradiction: rule 1 forbids merging two sources into one answer and
gives each answer a single `source_id`; rule 2 requires writing a
disagreement "naming both sides and both source ids", which the schema cannot
express. V1 removed the contradiction in prose, V2 added a structural
`disagreements[]` slot. Reconciliation still did not occur — which rules out
"the schema made it impossible" as the *sole* explanation, but given defect 1
does not establish anything about whether the model would reconcile a
contradiction it could actually surface.

§8's justification for batching over per-source calls therefore stands
**untested**, not refuted. `poc2c-spec.md` is the test that can settle it.

## Q4 — what neighbour expansion costs (PoC-1d's adoption)

Radius 1 against radius 0, on the real prompt, no calls involved:

| actor | r0 chunks / tokens / chars | r1 chunks / tokens / chars | r1 ÷ r0 chars |
|---|---|---|---|
| anthill-ventures | 14 / 245 / 1,472 | 30 / 388 / 2,099 | 1.43× |
| selco-foundation | 19 / 342 / 1,554 | 48 / 981 / 4,082 | 2.63× |
| bku-ekta-ugrahan | 13 / 337 / 1,994 | 31 / 1,144 / 5,075 | 2.54× |
| jyoti-pande-lavakare | 13 / 229 / 1,479 | 32 / 661 / 3,426 | 2.32× |
| bhavreen-kandhari | 15 / 457 / 2,339 | 39 / 1,310 / 5,865 | 2.51× |

**`NEIGHBOUR_RADIUS = 1` costs 1.4–2.9× on chars, 1.6–3.4× on tokens.** All
prompts sat far under `PASSAGE_TOKEN_CAP`, so the cap never bound at this
source count.

## Q5 — sources dropped before the call

`n_sources_in_prompt` was **3/4 for three of five actors**, 4/4 for two. A
fetched source contributes no selected chunk and silently vanishes from the
prompt. §3 correction 4 asks for sources-in-prompt logged against
sources-fetched; this is that gap, visible on first measurement. Whether the
cause is `_cap_tokens` truncating or selection never picking a chunk from
that source is not yet determined.

## Instrument defects found — the sitting's main output

1. **The plant is untargeted** (Q3 defect 1). Fixed by `poc2c-spec.md`'s
   two-stage probe-then-plant design.
2. **`marker` / `both_figures` scan the whole JSON blob** (Q3 defect 2).
3. **Runs are not reproducible** — sources drawn live, so no two runs share a
   source set. This invalidated a controlled comparison twice, once after
   calls had already been spent.
4. **Prompts were never saved**, so no run can be re-examined or replayed;
   "reproduce the baseline prompt" was not achievable by refetching.
5. **The free rung is marginal for one-observation-per-cell designs** — 3
   transport failures across 19 calls (`Upstream error from Nvidia`), and in
   2b they punched holes in the baseline and V1 cells specifically.

Defects 3 and 4 are addressed by the fixture-pinning and call-envelope work
(`--pinned`, PoC-scoped, live remains the default). Defects 1, 2 and 5 are
addressed in `poc2c-spec.md`.

## What is established, and what is not

**Established:** batched extraction parses reliably (8/9 single-shot, retry
rescues the remainder) and attributes perfectly (95/95). Neighbour expansion
costs ~2.5×. Sources are being dropped before the call at a measurable rate.

**Not established:** anything about reconciliation, in either direction; the
paid rung, untouched; parse behaviour above ~6k prompt chars; whether the
one truncation was `max_tokens` or upstream.

## Open gaps — carried forward, not fixed

Left open deliberately; this was a PoC, and these get fixed when the worker
is implemented rather than in the PoC layer.

1. **Two of five fixtures captured zero sources.** `selco-foundation` and
   `bhavreen-kandhari` produced empty fixtures (`sources: []`) — every URL in
   their PoC-0b pool came back off-topic or blocked at capture time. Both
   actors had fetched fine hours earlier in the 2b run (bhavreen 4 sources,
   selco 3). This is the clearest single demonstration of defect 3 in the
   list above, and the reason pinning was built — but it also means the
   fixture set **cannot currently support `poc2c-spec.md`**, which names
   bhavreen, selco and bku. Recapture, or respec 2c onto the three usable
   fixtures (anthill 2 sources, bku 4, jyoti 4).
2. **An empty fixture SKIPs rather than failing loudly.** A `--pinned` run
   against an empty fixture hits the pre-existing `< 2 sources` skip, so a
   comparison can silently lose a cell. `--pinned` should treat an empty
   fixture as an error, the way a missing one already is.
3. **`marker` / `both_figures` still scan the whole JSON blob.** The fix is
   specced (`poc2c-spec.md` → *Scoring*) but not applied, so 2b's numbers
   remain as recorded rather than being silently restated.
4. **The truncation question is unresolved** — whether PoC-2's one cut-off
   response hit `max_tokens` or an upstream cut. `truncated` is now recorded,
   so the next occurrence answers it.
5. **The paid rung is still untouched.** §2's "run it on both rungs" remains
   unsatisfied, by decision.
6. **Sources dropped before the call** (§Q5) — cause not determined:
   `_cap_tokens` truncating versus selection never picking a chunk from that
   source. Track E owes the sources-in-prompt / sources-fetched log per §3
   correction 4.
