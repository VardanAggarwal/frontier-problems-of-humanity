## 2026-09-19f — actor->actor emits now resolve to the ancestor problem, not dropped

Same `raghubar-das`/`saryu-roy` chain as `2026-09-19e` below, a different
bug on it: `raghubar-das` (candidate 1102, minted off `saryu-roy`/candidate
1075 — both `kind: actor`) ended with zero `works_on` edges, confirmed live
via `problems/graph.db`. `_emit`'s implicit-works_on synthesis
(`worker/worker.py`) only fires for `(source_candidate.kind, ekind)` in
`{("problem", "actor"), ("actor", "problem")}` — an actor emitting another
actor was silently dropped, no implicit edge and no reliable explicit one
either. Writing an actor->actor `works_on` edge instead would be
semantically wrong: the schema's `works_on` is `actor -> problem` only
(`store/schema.sql`'s `edge.kind` CHECK comment), and nothing downstream
reads it — `problem_leg`'s view requires `src_kind = 'actor' AND dst_kind =
'problem'`. Also found systemic: of 182 actors with zero `works_on` edges,
9 (of 49 otherwise backfillable via `from_candidate`) were skipped from
today's manual backfill specifically because their parent candidate was
`kind: actor`, not `kind: problem` — this fix is what makes that class
self-healing going forward; the 9 already-skipped actors are a separate,
explicitly-deferred backfill pass, not touched here.

Fix: new `_ancestor_problem(conn, candidate_row, ...)` in `worker/worker.py`
walks `from_candidate` up from an actor candidate until it finds an
ancestor whose `kind == 'problem'` and is resolved, capped at 10 hops with
cycle detection (log-and-bail, no forced/wrong edge on a malformed chain).
Wired at both points that can hit this case: `_emit`'s emits-loop, for an
actor naming an already-resolved existing actor (writes the ancestor edge
immediately); and `_backfill_trigger_edge`, for an actor naming a
not-yet-resolved one (flags `ancestor_problem_check` on the minted
candidate's payload at mint time, re-walks at promotion — deliberately
re-derived rather than cached, since the ancestor problem can resolve
*after* the source, which is what actually happened here: 1102 resolved
after 1075). Tests: `tests/test_worker.py`, ten new cases covering the walk
itself (resolved ancestor, dead-end chain, cyclic chain) and both call
sites (existing-entity immediate write, mint-then-backfill, no-ancestor
no-op).

## 2026-09-19e — hint-anchor top-up in `search_stage.py`, one stage before `passages.py`'s

Same shape as `2026-09-19b` below, one pipeline stage earlier: source
selection, not passage selection. `raghubar-das` (candidate 1102) was seeded
with a narrow `evidence.hint` — the Aadhaar-directive conflict tied to
Santoshi Kumari's death — and `render_queries` already issues a `("hint",
...)` query anchored on it. But all ~34 fetched sources were generic
political-bio coverage (hunger strikes, elections, his governorship, an
unrelated exam-scandal): `search/cover.py:cover()`'s greedy max-coverage
selection treats every query family id as equal weight, and for a famous
public figure dozens of URLs each satisfy a generic family id and fill
`max_sources` before the hint-unique URL is ever reached. Extracted profile
ended up entirely about the wrong story.

Fix, purely additive at the `cover()` call site in `worker/search_stage.py`
(`cover()` itself is the frozen contract, untouched): `_hint_anchor_top_up(
covered_urls, fused)` checks whether any URL `fuse()` marked as covering the
`hint` family already made it into `covered_urls`; if not, adds the single
top-`rrf_score` hint-covered URL, growing the set by at most one and
evicting nothing. No-op when no `hint` family was queried at all. Tests:
`tests/test_search_stage.py` — direct unit tests reproducing the actual
crowd-out shape (one URL covering every generic family vs. one uniquely
covering `hint`), the already-covered no-op, the no-hint-queried no-op, and
an end-to-end `search_sources()` regression.

## 2026-09-19d — `_write_entity` now clears an actor's ask/channel before rewrite

Different bug from the three below, though it surfaced on the same two
actors that day: not extraction contamination, append-only writes.
`_apply_other_claims`'s `ask:`/`channel:` branches (`worker/worker.py`)
`INSERT` unconditionally, no unique key tying a row to "the current claim
set" — unlike `tag` (upserts) and unlike `finding` (the per-candidate ledger
is explicitly `DELETE`d before rewrite). A reprocess that resolves `exact`/
`shortlist_top` to an existing actor re-derives the same claims and calls
`_apply_other_claims` again, appending a second set alongside the first.
Confirmed live: candidate 839 (`anaemia-mukt-bharat`) and candidate 823
(`poshan-abhiyaan`) were each reprocessed (`searched_at` moved past
`first_seen`), each resolved `exact` to the same actor, and each run
appended fresh rows on top of the stale ones — `/actor/<id>` showed a
duplicate need differing only in capitalization (poshan-abhiyaan) and a
stale, unrelated hiring ask plus email channel from a superseded first run
(anaemia-mukt-bharat).

Fix: `worker/worker.py`'s `_write_entity()`, right before its one call to
`_apply_other_claims()` — `if kind == "actor": DELETE FROM ask/channel WHERE
actor_id = ?`, once per `_write_entity` call, mirroring the `finding` clear's
rationale. Scoped to `kind == "actor"` because `ask`/`channel` are
actor-only tables (`store/schema.sql`), same guard both claim branches
already use. Safe on a brand-new entity too — nothing to delete. Tests:
`tests/test_worker.py::test_write_entity_replaces_ask_and_channel_rows_on_reprocess`,
`::test_write_entity_first_write_still_works_with_no_prior_ask_or_channel`.
Existing corrupted rows in `problems/graph.db` are not cleaned up by this
change — that's a separate, explicitly-authorized pass.

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