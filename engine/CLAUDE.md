# engine/ — Engine v2

A generalized research pipeline: take a cause, research it, find what works and
what doesn't, map who's already working it, score actor relevance, surface gaps.
`problems/` (see repo-root `CLAUDE.md`) is the current fph-specific system this
is meant to eventually generalize and replace; nothing here is stitched to
`problems/` yet except read access to `problems/graph.db`.

**Status: partially built.** The full four-layer architecture (Orchestrator,
Agents, Shared services, Text primitives) in `00-architecture.md` is an
unbuilt design proposal. What's actually shipped is one piece of it: the
**worker** (`engine/worker/CLAUDE.md`) — gate → fetch → gate → claims →
resolve → write → emit, run on already-admitted candidates. No orchestrator,
no bandit, no scheduler, no Review Gate exist yet; `worker.py:main()`'s
`--limit`/`--ids` queue stands in for admission control.

## Reading order for design context

1. `01-minimal.md` — **the actual design in force.** Data model (three
   types), storage, the worker's four gates, discovery, the compute cascade,
   fetch triage/dedup layers, build order. Section numbers (`§5`, `§7`, …)
   are cited throughout the code as the source of truth for *why* — read
   this before changing worker behavior that cites a section.
2. `03-worker.md` — the worker's research design in depth: query planning,
   search (SearXNG), fusion/cover, fetch/confirm, passage retrieval,
   extraction, the findings ledger, emits, budgets, cost model, failure
   modes. Also section-cited from code.
3. `04-worker-build-plan.md` — prerequisites, PoCs (SearXNG survival,
   retrieval quality, batched extraction), build tracks (A–E), what's
   shipped, corrections found while building. `§6` ("What has shipped") is
   the fastest way to check current state without reading git log.
4. `05-worker-optimisations.md` — running punch list, most-recent-first.
   Check this first for "what's broken / next" before starting new work.
5. `02-questions.md` — narrative behind `questions.yaml` (below).
6. `00-architecture.md` — the unbuilt v2 design (bandit orchestrator, typed
   claims, Structure/Actor Processing/Matching agents). Read for where this
   is headed, not for what exists. Explicitly not yet mapped onto
   `problems/` or the current skills (`process-tier`, `process-leaf`,
   `actor-channel-finder`, `impact-network-crawler`) — see its "Open
   questions" section.

**Docs are numbered and append-only in spirit** — corrections get added as
dated sections, not silently edited over. When a doc's design and the code
disagree, check the doc's most recent dated correction before assuming the
code is wrong.

## Directory map

| Dir | What |
|---|---|
| `worker/` | The shipped pipeline. See `worker/CLAUDE.md`. |
| `store/` | SQLite schema (`schema.sql`), connection/migration helpers (`db.py`), tag helpers, `edit.py`. Backs `problems/graph.db`. |
| `embed/` | Local encoder (`model.py`, tier-1 of the compute cascade), vector index (`index.py`, sqlite-vec), backfill, calibration, `guard.py` (shared `--db`/`--corpus` CLI args + freshness check — `add_store_args`/`open_store`, used by every CLI tool here). |
| `search/` | SearXNG provider, RRF fusion (`fuse.py`), greedy set cover (`cover.py`), source-set health/confirm policy, actor/problem query-family templates (`families.yaml`). |
| `text/` | Canonicalization, chunking, cleaning (boilerplate strip), simhash dedup, page-state, preview. Tier 0 of the compute cascade — no model calls. |
| `migrate/` | One-off schema/data migrations (`m000N_*.py`), plus `from_corpus.py` (bootstrap from `problems/`), `restamp.py`, backfills. Run once, keep for history. |
| `poc/` | Proof-of-concept scripts backing `04-worker-build-plan.md` §2 (PoC-0 SearXNG, PoC-1 retrieval, PoC-2 batched extraction) plus `poc/searxng/` — the local SearXNG docker instance (`run.sh start\|stop\|logs`, port 8080). Read-only history; don't extend, PoCs are one-shot. |
| `tests/` | pytest, one `test_*.py` per module above plus worker-level tests (`test_worker.py`, `test_worker_e6.py`, `test_worker_resume.py`). `fixtures/` alongside. |
| `questions.yaml` | The ~35-question registry (id, text, claim field, tier flags) — single source of truth, loaded by `worker/questions.py`. Narrative: `02-questions.md`. |
| `requirements.txt` | Tier 0-1 local deps + pytest. Heavily commented — **read the sqlite3 load-extension caveat at the top before debugging a "cannot load sqlite-vec" error**: needs a Python whose sqlite3 wasn't built with `SQLITE_OMIT_LOAD_EXTENSION` (python.org's macOS 3.11 build has this; Homebrew python3.12 doesn't). |

## Running things

No `engine/__init__.py`, no package install. Everything is run **with
`engine/` as the working directory** — internal imports are bare
(`from embed.guard import ...`, `from store import db`, `from search import
confirm_policy`), and `worker/` is a sub-package imported as `worker.x`
(`python -m worker.worker ...` from inside `engine/`).

```
cd engine
python -m worker.worker --limit 20              # process the admitted queue
python -m worker.worker --ids 101,102 --force    # reprocess specific candidates
pytest tests/                                    # or: pytest tests/test_worker.py -k foo
```

Shared CLI flags (`embed/guard.py::add_store_args`): `--db` defaults to
`<repo>/problems/graph.db`, `--corpus` to `<repo>` — both **repo-anchored**,
not cwd-relative, specifically because past tools disagreed about whether a
bare run meant repo root or `engine/`. Every tool that touches the store
calls `open_store()`, which refuses a stale db against `problems/` (freshness
check) unless `--stale-ok` is passed.

SearXNG must be running for search-backed work: `engine/poc/searxng/run.sh
start` (docker, port 8080). `FPH_SEARXNG_URL` / `--search-url` override the
default `http://localhost:8080`; `--no-search` degrades to seed-URL-only.

## Env vars

OpenRouter is the only LLM provider (`OPENROUTER_API_KEY`; the old
Anthropic/Gemini fallback chain was removed 2026-09-18). Pipeline tuning
knobs are `FPH_*` (chunk size, top-k per bucket, passage token cap, source
caps per depth tier, SearXNG URL — see `worker/config.py` for the full,
heavily-commented list). A `.env` shared with `../slate_v2` works unmodified
by design (`worker/config.py`'s docstring) — this engine's LLM config was
ported from there, not rewritten.

## Conventions worth knowing before editing

- **Section-cite, don't restate.** Code comments cite `01-minimal.md §N` /
  `03-worker.md §N` / `04-worker-build-plan.md §N` instead of re-explaining
  design rationale inline. Keep that pattern — trace the citation before
  assuming a comment is stale.
- **Frozen contracts.** `04-worker-build-plan.md` §5 froze five interfaces
  before parallel build tracks (A–E) started; `extract_types.py` is one of
  them. Don't casually change a type that's cited as "frozen" without
  checking who else consumes it.
- **Degrade paths are load-bearing, not dead code.** Several pipeline steps
  have an explicit fallback (`search_provider=None`, thin-set escalation,
  resume-from-stored-sources) documented as a deliberate degrade in
  `03-worker.md` §13. Don't delete one because it looks unused in the happy
  path.
