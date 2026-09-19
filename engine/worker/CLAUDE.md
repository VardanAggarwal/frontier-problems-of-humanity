# engine/worker/ — the pipeline

The shipped part of Engine v2 (see `../CLAUDE.md` for the full design status).
One candidate in, claims written or escalated out: **gate 1 → fetch → gate 2
→ search/fuse/cover → confirm → passage retrieval → extraction → resolve →
write → emit.** Design source: `../01-minimal.md` §4-§9, `../03-worker.md`
(full stage-by-stage detail), `../04-worker-build-plan.md` (build tracks
A-E, what shipped). Code comments cite these by `§N` — trace the citation,
don't guess at rationale.

Run from `engine/`: `python -m worker.worker --limit N` (see `../CLAUDE.md`
"Running things" for flags and env). `worker.py:main()`'s `--limit`/`--ids`
queue is a stopgap for the not-yet-built admission-control scheduler
(`../01-minimal.md` §9) — don't read more design intent into it than that.

## Pipeline stage → file map

| Stage | File | Design ref |
|---|---|---|
| Intake / depth-tier decision | `depth.py` | `03-worker.md` §2, `04-worker-build-plan.md` §4 (Track B) |
| Query planning | `prompts.py` (query side), `../search/families.yaml` | `03-worker.md` §3 |
| Search | `search_stage.py` | `03-worker.md` §4, Track E1 |
| Fuse + cover | `../search/fuse.py`, `../search/cover.py` (called by `search_stage.py`) | `03-worker.md` §5 |
| Fetch + confirm | `fetch.py`, `gate2.py` | `03-worker.md` §6, §6a |
| Gate 1 (pre-fetch screen) | `gate1.py` | `01-minimal.md` §5/§7, batched, tuned for recall |
| Passage retrieval | `passages.py` (Track C, pure fn — no DB/network) | `03-worker.md` §7 |
| Extraction assembly | `extract.py` (Track E3, pure fn), `extract_types.py` (Track E, frozen contract) | `03-worker.md` §8 |
| The two LLM prompts | `prompts.py` (Track E2 — pure string-building, no I/O) | `01-minimal.md` §4/§5 |
| LLM call | `llm.py` (OpenRouter only as of 2026-09-18; old Claude/Gemini fallback chain removed) | `01-minimal.md` §7 |
| Findings ledger | (in `worker.py`, Track E4) | `03-worker.md` §9 |
| Entity resolution | `resolve.py` — normalized alias/id match **first**, embedding shortlist only as fallback (measured, not a style choice: cold-encoded lookup alone gets rank-1 51.8%) | `01-minimal.md` §8 Layer 4, §9 |
| Emit (actors + problems) | `worker.py` (actor emits), `problem_emit.py` (Track A — problem-edge candidates, added because the actor path already existed and problems silently dropped) | `03-worker.md` §10 |
| Question registry | `questions.py` loads `../questions.yaml` | Track F1 |
| Config / LLM chain | `config.py` — ported from `../../slate_v2/core/config.py`, same env var names so a shared `.env` works unmodified | `01-minimal.md` §7 "lift, don't rewrite" |
| Candidate dedup (pre-admission) | `dedup_candidates.py` — two tiers, different trust levels; NOT wired into admission yet | `05-worker-optimisations.md` |
| Candidate priority scoring | `score_candidates.py` — `priority = 0.40*G + 0.25*D + 0.20*F + 0.15*S`, writes `candidate.score` + an `event` row per write; standalone, NOT wired into the worker loop yet | `05-worker-optimisations.md` |

## Key behaviors to know before touching this

- **Resume by default.** A candidate with a stored source set resumes at
  extraction rather than re-running search+fetch+gate2 (~30min round trip).
  Pass `--no-resume` only when inputs actually changed (widened
  `FPH_MAX_SOURCES_*`, fixed SearXNG, a thin first set). Shipped
  2026-09-18, `03-worker.md` §13a.
- **`--force` + `--ids` reprocesses an already-resolved candidate** by
  re-matching its name against the existing entity (via `resolve.py`) and
  refreshing claims, rather than minting a duplicate. Pair with
  `--no-resume` if the stored source set was thin.
- **Emit never recurses.** New candidate rows land in the table; `run_batch`
  returns without processing them. Depth is a budget/admission question, not
  a recursion constant (`01-minimal.md` §5).
- **`depth_tier` (registry vs tracked) is now a default, not a switch** —
  E6 converted a process-environment toggle into a `run_batch` /
  `_write_entity` / `_emit` call-site parameter; the env var only fills in
  when a caller passes `None`. If you're threading a new depth-affecting
  behavior through, follow this pattern rather than reading another env var
  mid-pipeline.
- **Frozen contracts.** `extract_types.py` types (Track E) were frozen
  before tracks A–E were built in parallel so E1/E2/E3/E4 could be built
  concurrently against a stable shape. Changing them is a cross-track
  change, not a local one — check `04-worker-build-plan.md` §5.
- **Gate 1 is tuned for recall, not precision** — it's the 50x-cheaper
  batched pre-fetch screen; false negatives here are unrecoverable (item
  never fetched), false positives just cost a fetch + gate 2. Don't
  "tighten" it without re-reading why.
- **PDF extraction is a known gap** (`../05-worker-optimisations.md`:
  37 PDFs dropped across three candidates in one run while blogspam got
  through) — check the optimisations log before assuming a missing-source
  bug is something else.
- **Candidate concurrency is not implemented.** `run_batch` is a strict
  `for cid in alive` loop; 76% of wall time is one blocking HTTP call per
  candidate. `_openrouter_pace` is thread-safe and built for concurrent
  callers but currently serves exactly one — blocked on the shared sqlite
  connection, per the optimisations log.

## Tests

`../tests/test_worker*.py` (`test_worker.py`, `test_worker_e6.py` for the
depth-tier default behavior, `test_worker_resume.py` for the resume path),
plus one `test_*.py` per stage file above. Run from `engine/`:
`pytest tests/test_worker.py -v`. Pure-function stages (`passages.py`,
`extract.py`, `prompts.py`, `extract_types.py`, `problem_emit.py`) are
tested without DB/network — keep new stage logic pure where possible for the
same reason.

## Before starting new work here

Read `../05-worker-optimisations.md` first — it's the running, dated,
most-recent-first punch list of what's broken and what's next (worker-side
and orchestrator-side). Don't duplicate a known issue as a fresh one.
