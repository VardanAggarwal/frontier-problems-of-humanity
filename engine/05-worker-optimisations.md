## 2026-09-19c — write-time check: does the cited chunk even mention the candidate

Third, defense-in-depth layer on the same `anaemia-mukt-bharat` bug, below.
The other two narrow how often the WeTheChange chunk gets selected
(`passages.py`'s gate) or survives chunking at all (`clean.py`'s dedupe) —
neither guarantees zero, and a candidate whose `_name_tokens` come back
empty (too short/generic) skips both gates outright. This one checks the
literal passage backing each answer, at write time, regardless of how it
got selected.

Added `flag_unmentioned_answers()` next to `parse_misidentified`/
`drop_misidentified` in `worker/prompts.py` — same shape, chunk granularity
instead of source: for each answer with a resolvable `chunk_ref`, does that
one chunk's text contain the candidate's own `_name_tokens`
(`worker/identity.py`, reused unchanged)? If not, drop the answer. Empty
`name_tokens` is a no-op (can't check, same degrade as `passages.py`'s own
gate); if literally every checkable answer fails — an acronym-only name
never spelled out in body text — nothing is dropped and one summary problem
is logged instead, the same non-zero-recall safety valve as the other two
fixes.

Wired into `worker/worker.py`'s `elif batched:` branch, right after the
Rule-4 `flagged`/`drop_misidentified` block and before `report["extracted"]
+= 1`: builds `chunk_texts` from `prompt_sources` + `verify_sources` (the
same dict `write_findings` needs a few lines later — that call site now
reuses it when `batched`, rebuilds it fresh otherwise). New counter
`report["answers_dropped_unmentioned"]`. Tests in
`tests/test_prompts_batched.py` (dropped-chunk shape, unresolvable
`chunk_ref` passes through, safety valve, empty `name_tokens`).

## 2026-09-19b — passages.py candidate-identity gate

Same `anaemia-mukt-bharat` bug as the entry below, independent fix in
`worker/passages.py:select()`: nothing in `select()`'s bucket ranking checked
that a chunk was actually about the candidate — a WeTheChange job-ad
paragraph (feed/sidebar bleed inside a LinkedIn scrape that also mentioned
"Anaemia Mukt Bharat" once) out-scored ~34 genuinely on-topic chunks across
nearly every bucket on pure topical similarity.

Extracted `_name_tokens`/`_text_mentions_actor`/`_NAME_TOKEN_STOPWORDS` out
of `worker/search_stage.py` (built for the structurally identical
`tara-mani-sah` channel-mismatch bug) into a new `worker/identity.py` — no
heavy deps, keeps `passages.py`'s "pure, no network, no DB" contract.
`select()` gained `candidate_name`: if given and ≥1 fetched chunk mentions
the candidate's own name tokens, narrow to just those chunks before ranking;
if none do (abbreviation-only source set), no-op rather than wipe the pool —
degrade, not a crash, same as the encoder-unavailable path. Threaded through
`extract.py:assemble()` and both `worker.py` call sites (`candidate_name=name`).
Tests: `tests/test_passages.py` (regression on the bug shape, backward-compat
with no `candidate_name`, degrade-path no-op).

## 2026-09-19 — clean.py drops verbatim/near-verbatim repeated blocks

Bug: `anaemia-mukt-bharat` extraction got hijacked onto an unrelated org
("WeTheChange") because a single LinkedIn permalink scrape
(`problems/private/sources/6e9044bbc11b6537.txt`) carried the on-topic post
plus an unrelated "we're hiring" job ad, near-verbatim, TWICE — almost
certainly feed/sidebar bleed, not real content (a single post doesn't
normally repeat itself). Independent of the parallel identity-based
passage-filtering fix in `worker/passages.py` — this one is in
`text/clean.py`, tier 0.

Added `dedupe_repeated_blocks()`: splits cleaned text on `tidy()`'s own
paragraph unit (`\n\n`), drops any block ≥15 words that matches an earlier
block — exact match after `simhash.normalize()` (catches the WeTheChange
case, which differs only by a trailing period), plus `simhash.is_duplicate()`
for blocks long enough (`simhash.is_reliable()`, ~200 words) for a
Hamming-distance comparison to mean anything. Reuses `text/simhash.py`
entirely, no new hashing logic. Wired into all three `clean()` return paths,
including the already-text branch. Tests in `tests/test_text.py`
(`test_repeated_substantial_block_is_collapsed_to_first_occurrence`,
`test_short_repeated_phrase_is_not_touched`).

## 2026-09-18b — post-drop thin check, trailing fallbacks, log wording

**Still open, in priority order.** 
- Candidate concurrency (76% of wall time is
one blocking HTTP call per candidate and `run_batch` is a strict `for cid in
alive:`; `_openrouter_pace` is already a thread-safe lock built for concurrent
callers and serves exactly one — blocked on the shared sqlite conn).

- Gate 2 band precision (0.78/0.80, labelled
"provisional, not measured" in their own log line; 528 measures them). Why 552
put all 19 findings on 1 of 7 sources with zero misidentified flags, while 560
spread across 6 of 6.



Next steps for worker:
- Actors & Actor channels -> Need proper testing
  - None of the actors are mapped to problems that emitted them.
What to build first for orchestrator:
- Merging 2 actors/problems already minted
- Figure out early on whether actors are worth scraping
- Consider slow but always on type approach
- Link existing items together
  - Handle hierarchy better? Or build networks? Drop existing hierarchichal structure?
    - Can't capture what covers multiple needs
  - also solve topic-overlap as part of hierarchy solution