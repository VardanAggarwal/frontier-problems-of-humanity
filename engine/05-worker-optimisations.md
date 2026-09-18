## 2026-09-18 — extraction failure: hidden reasoning tokens, not malformed JSON

Candidates 528/552/560 had been failing extraction for two days. Every fix
shipped against it (json_object, json_repair, require_parameters, the §13
per-source rescue, scaling `extraction_max_tokens`) treated the symptom —
"malformed JSON" — and none touched the cause.

**Cause.** Every configured `:free` model is a reasoning model, and OpenRouter
charges hidden chain-of-thought against `max_tokens`. Measured on the real
8-source batched prompt (14,981 input tokens, max_tokens=10,240):

| config | wall | reasoning tokens | result |
|---|---|---|---|
| as shipped | 110s | 8,922 of 10,240 | `finish=length`, content begins `{\n{\n`, unparseable |
| `reasoning: {enabled: false}` | 26s | 0 | parses clean — 19 answers + emits + edges |

87% of the output budget went to chain-of-thought, leaving ~1,300 tokens for a
7,200-character answer. The response was truncated, not malformed. Extraction
copies spans out of supplied text into a fixed schema — there is nothing for
reasoning to work out.

**Changes.**
- `reasoning: {enabled: False}` on every OpenRouter request. This is the fix;
  everything else below is cleanup it made possible.
- Removed `provider: {require_parameters: True}` (shipped the day before). It
  never addressed the real cause, and three of the four models then in `.env`
  declare neither `response_format` nor `structured_outputs`, so it left them
  with zero routable backends and a hard `404 No endpoints found` — three of
  the five §13 rescue calls in the 15-30-27 run died that way.
- Removed the claude / claude-cli / gemini / local rungs. A five-rung chain
  was one rung deep: `anthropic` and `google-genai` are deliberately absent
  from `requirements.txt`, `CLAUDE_CODE_OAUTH_TOKEN` was never set (so
  claude-cli was skipped silently, not even named in the failure message), and
  `local` had no branch in the `configured` test at all. Their only real
  effect was burying OpenRouter's actual error under two expected "package not
  installed" lines. Installing the paid rung would have made a broken call
  expensive rather than correct.
- `call()` is now OpenRouter-only, retry-outer / model-inner. A dead model
  costs one call before failover instead of three plus backoff sleeps.
- `.env` model list cut 4 → 2, both measured end to end. `inkling-small` had
  been in the list and 403-ing on every call since it was added.
- §13 rescue gets a circuit breaker: two consecutive provider failures and it
  stops. It exists for a prompt-shaped failure (one oversized batch), and is
  useless against a provider-shaped one — in the 15-30-27 run it made 8
  identical doomed calls at ~5 minutes each.

**Model bench** — real prompt, reasoning off. `supported_parameters` from
`/models` does not predict this; several models that declare the right
parameters fail the call.

| model | result |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | PASS 26s |
| `deepseek/deepseek-v4-flash-0731:free` | PASS 57s |
| `google/gemma-4-31b-it:free` | 429 upstream (fails in 1s) |
| `google/gemma-4-26b-a4b-it:free` | 429 upstream (fails in 1s) |
| `qwen/qwen3.8-27b:free` | 429 upstream (fails in 1s) |
| `thinkingmachines/inkling{,-small}:free` | 403 "only available on agentic harnesses" |
| `liquid/lfm-2.5-2.6b:free` | 400 "Reasoning is mandatory and cannot be disabled" |

**Result.** 528/552/560 end to end in **5m03s**, all three extracted, 57
findings written, `retry_per_source_calls=0`, cost 0.0. The previous run spent
22+ minutes on 528 alone and produced nothing.

**Opened by this, not closed.** With extraction working, candidate 528 flagged
**7 of its 8 sources as misidentified** — urbandictionary.com, openai.com, a UK
cost-of-living article, a Nigerian logistics LinkedIn post, a Hindi UP-government
page. The query decomposed to the bare word "urban" and gate2 *confirmed*
urbandictionary.com at cosine 0.812 and openai.com at 0.811. The 0.78/0.80
bands are labelled "provisional, not measured" in their own log line; this is
the case that measures them. Search precision is now the top item, above.

Next steps for worker:
- Now sources we are getting are good. Just need to solve for better content writing.
  - Need to track all sources - only a few are being finally saved from what is used or verified
  - Sources in prose are mismatched with what is saved
  - Need to generate prose by matching relevant paragraphs from sources with findings
- Figure out how to tune research back to India if digressing
  - engine/worker/runs/2026-09-15T10-19-47-201Z-68881.log
- Handling failures instead starting from scratch
  - Extraction fails, restart -> another half an hour gone. Instead just continue from extraction?
- Load faster
  - Still takes a lot of time to load -> may be cache HF model considering it is still running locally?
  - What takes forever after model loads? better loggeers with time?
- Handle PDFs
- Link existing items together
What to build first for orchestrator:
- Resolving duplicates in candidates
  - Merging 2 actors/problems already minted
- Identifying which candidates are worth looking into - some sort of ranking?
- Consider slow but always on type approach
- Link existing items together
  - Handle hierarchy better? Or build networks? Drop existing hierarchichal structure?
