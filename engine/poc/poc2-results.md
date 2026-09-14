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

---

## Item 6 answered by track E3 (2026-09-14)

`worker/extract.py`'s `assemble()` returns the counters §3 correction 4 asked
for, and they separate the two candidate causes rather than reporting one
number: `sources_fetched`, `sources_in_prompt`, `sources_never_selected`
(selection ranked no chunk from that source) and `sources_dropped_by_cap`
(selected, then evicted by `PASSAGE_TOKEN_CAP`).

Run against the captured fixtures, with the actor question set:

| fixture | fetched | in prompt | never selected | dropped by cap |
|---|---|---|---|---|
| `bku-ekta-ugrahan` | 4 | 3 | **1** | 0 |
| `anthill-ventures` | 2 | 2 | 0 | 0 |
| `jyoti-pande-lavakare` | 4 | 4 | 0 | 0 |

**The cause is selection, not the cap.** `bku` reproduces the 3-of-4 exactly,
and the source that never reached the prompt was one no bucket's top-k ever
ranked — `_cap_tokens` evicted nothing. That matters for what the fix would
be: raising `PASSAGE_TOKEN_CAP` would not have recovered the source, and set
cover buying a source that selection then never reads is the waste §3
correction 4 was written to detect.

Two limits on this result, both load-bearing:

- **It is three actors, not five.** `selco-foundation` and `bhavreen-kandhari`
  captured zero sources, so the two fixtures that would have completed the
  comparison do not exist. Two of the three original 3/4 observations remain
  unexamined.
- **`sources_dropped_by_cap` is provably 0, not measured as 0.**
  `_cap_tokens` never drops a source's last chunk, so the counter cannot fire
  under the current rule. It is kept as a regression detector for that
  guarantee, and must not be read as evidence the cap is harmless.

Neighbour expansion (`NEIGHBOUR_RADIUS = 1`) measured 2.34-3.65x tokens and
2.29-4.04x chars across the three fixtures — consistent with the 1.6-3.4x /
1.4-2.9x recorded above, and above it at the top end on `bku`.

---

## Addendum, 2026-09-14 — the two "zero-source" fixtures were a cache bug

The limit recorded just above ("It is three actors, not five") is **withdrawn**.
`selco-foundation` and `bhavreen-kandhari` did not capture zero sources because
their pages were unavailable, off-topic or thin. They captured zero because
`worker/fetch.py` could not read its own cache.

**The bug.** `_upsert_source` writes `source.path` *relative to `corpus`*
(`str(dest.relative_to(corpus))`), and `_row_to_result` resolved it with a bare
`Path(row["path"])` — against the process CWD. Every one of the 151 cached rows
in `poc/poc2-scratch/graph.db` pointed at a file that did not exist from where
the PoC runs, while the 148 text files sat on disk under
`poc/poc2-scratch/problems/private/sources/`. So **every cache hit returned
`text=None`**, with the row still reporting its word count.

**How it hid.** The PoC's gather step printed one label for every text-less
result: `OFF-TOPIC (gate-2 stand-in)`. The signature is unmistakable in
`poc2b_run.log` once you look for it — `cache=1` lines are all `0w`, `cache=0`
lines carry real word counts — but the log *said* the pages were off-topic, so
the reading was that SELCO's and Bhavreen's coverage was bad. It was not:
SELCO's own site (661w), Skoll (797w), Yale (718w), Lemelson (554w) and
LinkedIn (2,788w) were all sitting in the cache the whole time. The two
fixtures were captured at 18:36 and 18:40, by which point everything was
cached, while `anthill`/`bku`/`jyoti` had been fetched cold minutes earlier.
That is the entire difference between the three fixtures that worked and the
two that did not.

**Recaptured.** Both now carry 4 sources, from cache, zero HTTP:

| fixture | sources | dropped | q10/q11-shaped figure present |
|---|---|---|---|
| `selco-foundation` | 4 | 17 | yes — `2.5 lakh students`, `INR 46,109` |
| `bhavreen-kandhari` | 4 | 4 | no — the crore figures are budget lines in a court document, not her funding |

So PoC-2c's original actor list is usable again for SELCO; Bhavreen remains a
likely stage-1 probe drop, which is now a loud failure rather than a silent
skip.

**Scope beyond the PoC.** This is an engine bug, not a harness bug. The cache
has been write-only since it shipped: the worker refetches every page over HTTP
forever, and any page that *is* cached is treated as unusable. Fixed in
`worker/fetch.py` with three regression tests; the existing cache-hit test
inserted `path=NULL`, which is why it passed throughout.

**One more thing the drop ledger exposed.** The URL pool for both actors
contains unrelated pages — `pinkbike.com`, `30rates.com/aed-php`, `amazon.fr`,
a Japanese Wikipedia article on 10^12. Those come from the PoC-0b search
responses, not from fetching. Unexamined here; it belongs with §4's search
quality, and it means `url_pool`'s ranked list is weaker than the ranking
implies.
