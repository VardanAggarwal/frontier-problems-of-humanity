"""ported from ../slate_v2/core/config.py; only the LLM chain, this engine has
no other config surface yet.

Same env var names and defaults as slate_v2, so a `.env` shared between the
two repos works unmodified — this is deliberate, not an accident of copying:
`01-minimal.md` §7 says tiers 1-3 of the compute cascade are already built in
`../slate_v2` and should be lifted, not rewritten, and the model tiering /
provider chain is the one piece of that lift this engine needs for tier 4
(paid extraction). Everything else in slate_v2's config.py — echo thresholds,
health scores, the MCP server block, the write-refine pass — belongs to
slate's own note-taking loop and has no analogue here.
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _csv(var: str, default: list[str]) -> list[str]:
    raw = os.getenv(var, "")
    return [m.strip() for m in raw.split(",") if m.strip()] if raw else default


# ── API keys ──────────────────────────────────────────────────────────────
# OpenRouter is the only provider (2026-09-18). `ANTHROPIC_API_KEY`,
# `GEMINI_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_MODEL_*`,
# `GEMINI_MODELS` and `LLM_FALLBACK_ORDER` were all removed with the fallback
# chain — see `worker/llm.py::call`. The keys can stay in `.env`; nothing
# reads them.
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ── Models, in try order. `call()` walks this list, moving to the next entry
# when one fails outright (dead backend, persistent 429, unparseable
# response). It is a list for backend redundancy, NOT a quality ladder and
# NOT a retry budget — every entry must be able to do the job alone, because
# entry 0 is what almost every call actually uses.
#
# Two hard requirements for anything added here, both checkable against
# OpenRouter's live `/models` endpoint (`supported_parameters`) rather than
# assumed:
#
#  1. It must declare `response_format` (or `structured_outputs`). Three of
#     the four models configured in `.env` on 2026-09-18 declared neither,
#     which is how the candidate-528 run earned a hard `404 No endpoints
#     found that can handle the requested parameters`.
#  2. If it is a reasoning model — and on the free tier they all are — it
#     must honour `reasoning: {enabled: false}`, which `_call_openrouter`
#     sends. Unhonoured, hidden chain-of-thought eats the `max_tokens` budget
#     and the answer comes back truncated; that was the whole of the
#     2026-09-18 extraction failure.
#
# Every `:free` model OpenRouter listed on 2026-09-18 that was worth trying,
# run against the REAL 8-source batched extraction prompt (14,981 input
# tokens, max_tokens=10,240) with reasoning off. Not a paper comparison of
# `supported_parameters` — several models that declare the right parameters
# fail the actual call:
#
#   nvidia/nemotron-3-super-120b-a12b:free  PASS  26s, 2,023 output tokens
#   deepseek/deepseek-v4-flash-0731:free    PASS  57s, 1,832 output tokens
#   google/gemma-4-31b-it:free              429   rate-limited upstream (1s)
#   google/gemma-4-26b-a4b-it:free          429   rate-limited upstream (1s)
#   qwen/qwen3.8-27b:free                   429   rate-limited upstream (1s)
#   thinkingmachines/inkling:free           403   "only available on agentic
#   thinkingmachines/inkling-small:free     403    harnesses" — never usable
#   liquid/lfm-2.5-2.6b:free                400   "Reasoning is mandatory for
#                                                  this endpoint and cannot be
#                                                  disabled"
#
# PASS means the complete expected shape: 19 answers + misidentified + emits
# + edges. Nemotron-super leads on latency; deepseek is a different vendor's
# backend, which is the entire point of a second entry.
#
# Three things that table settles and a `/models` query does not:
#   - `inkling-small` was configured in `.env` and had been 403-ing on every
#     call since it was added. A model in the list is not a model that works.
#   - `lfm-2.5-2.6b` REJECTS `reasoning: {enabled: false}` with a hard 400.
#     Requirement 2 above is not a preference; a model that cannot honour it
#     fails 100% of calls instantly.
#   - The three 429s fail in ~1s, so they are cheap to carry as trailing
#     entries if the two above are ever both down — but they are congested
#     often enough that they are not in the default list.
#
# The singular `OPENROUTER_MODEL_MECHANICAL`/`_JUDGMENT` overrides still set
# element 0, so an existing `.env` is not silently ignored; the plural
# `OPENROUTER_MODELS_*` replace the whole list.
_DEFAULT_MODELS = ["nvidia/nemotron-3-super-120b-a12b:free",
                   "deepseek/deepseek-v4-flash-0731:free"]
OPENROUTER_MODELS_MECHANICAL = _csv(
    "OPENROUTER_MODELS_MECHANICAL",
    [os.getenv("OPENROUTER_MODEL_MECHANICAL", _DEFAULT_MODELS[0])] + _DEFAULT_MODELS[1:])
OPENROUTER_MODELS_JUDGMENT = _csv(
    "OPENROUTER_MODELS_JUDGMENT",
    [os.getenv("OPENROUTER_MODEL_JUDGMENT", _DEFAULT_MODELS[0])] + _DEFAULT_MODELS[1:])

# ── LLM retry/backoff (absorb transient 503/429/overload within a run) ────
LLM_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "3"))
LLM_BACKOFF_BASE = float(os.getenv("LLM_BACKOFF_BASE", "2.0"))  # seconds

# ── OpenRouter rate-limit handling (free tier ~20 req/min) ────────────────
OPENROUTER_MIN_INTERVAL_S = float(os.getenv("OPENROUTER_MIN_INTERVAL_S", "3.0"))
OPENROUTER_RATELIMIT_MAX_WAIT = float(os.getenv("OPENROUTER_RATELIMIT_MAX_WAIT", "90"))
OPENROUTER_RATELIMIT_MAX_RETRIES = int(os.getenv("OPENROUTER_RATELIMIT_MAX_RETRIES", "6"))
OPENROUTER_RATELIMIT_DEFAULT_WAIT = float(os.getenv("OPENROUTER_RATELIMIT_DEFAULT_WAIT", "6.0"))

# ── Track C — chunking and passage selection (`03-worker.md` §7, starting
# values, not findings; measured/checked in `engine/poc/poc3-results.md`). ──
# Encoder window (512) minus special tokens (2) minus the `passage: ` prefix
# (3) leaves 507 tokens of hard ceiling; 320 leaves 187 tokens of margin,
# confirmed against the real tokenizer by PoC-3, not assumed.
CHUNK_TOKENS = int(os.getenv("FPH_CHUNK_TOKENS", "320"))
# top-k chunks kept per retrieval bucket (§7 "Selection: top-k per question,
# never a threshold" — applied per bucket per PoC-1c, not per question; see
# `worker/passages.py`).
TOP_K_PER_BUCKET = int(os.getenv("FPH_TOP_K_PER_BUCKET", "3"))
# Bounds the one extraction call (§7); overflow drops lowest-scoring chunks,
# never a source's last chunk.
PASSAGE_TOKEN_CAP = int(os.getenv("FPH_PASSAGE_TOKEN_CAP", "9000"))
# The degrade path when the encoder is unavailable (§13): first-N-chars per
# source, capped. Character count, not tokens — no tokenizer on this path.
DEGRADE_CHUNK_CHARS = int(os.getenv("FPH_DEGRADE_CHUNK_CHARS", "2000"))
# Chunk overlap is 0 — `03-worker.md` §7's `CHUNK_OVERLAP = 48` is superseded
# by PoC-1d (`engine/poc/poc1d-results.md`), which measured overlap costing
# the three strongest buckets most of their AUC (reach 0.893→0.649, status
# 0.977→0.837) and a third of the passage budget's source diversity. There is
# deliberately no CHUNK_OVERLAP constant: overlap is not a tunable that got
# set to zero, it is a technique this build does not use. The straddled
# figure/denominator it existed to repair (284 real instances) is repaired
# instead at selection time, by including each selected chunk's neighbours in
# the extraction prompt — contaminated context never enters an embedding.
# Radius in chunks, each side; 0 disables expansion entirely.
NEIGHBOUR_RADIUS = int(os.getenv("FPH_NEIGHBOUR_RADIUS", "1"))
# A dense list of proper names ("co-signed by the X Collective, funded by the
# Y Foundation...") doesn't read as similar to a question-shaped retrieval
# query, so it can miss every bucket's top-k and never reach the prompt even
# though it's exactly the emits/edges source material. This many extra
# chunks, ranked by a cheap capitalized-run count (`_entity_density`) and not
# already caught by any bucket, ride in alongside the bucketed selection.
# Default on (not 0) because catching what ranking misses is the whole point;
# small enough that a false-positive-heavy chunk barely dents the token cap.
ENTITY_DENSITY_TOP_N = int(os.getenv("FPH_ENTITY_DENSITY_TOP_N", "2"))

# Same top-up mechanism, different miss: a chunk naming India/an Indian
# institution can still lose every bucket to a denser global/other-country
# source (measured on `cookfire-smoke` 2026-09-14 — a WHO fact sheet entered
# the fetched pool once `search/families.yaml` got an India-biased query but
# never won a single bucket's top-k against a Nature global-projection paper
# and a Frontiers China cohort study). `problem-core`'s retrieval_query was
# reworded the same day to name "occurrence in India" explicitly — the
# primary fix — but that is one bucket's ranking signal, not a guarantee for
# every bucket, so this top-up is the same belt-and-suspenders role
# `ENTITY_DENSITY_TOP_N` plays for name-dense chunks. `kind: problem` only
# (`worker/passages.py`'s `geography_bias` flag) — actors are legitimately
# global (a funder need not be Indian), so this must not run on actor
# selection. 0 disables it.
INDIA_ANCHOR_TOP_N = int(os.getenv("FPH_INDIA_ANCHOR_TOP_N", "2"))

# ── Track D/E1 — search stage source cap (`03-worker.md` §7 constants table:
# "Set-cover rarely needs more than 5 to exhaust the covered families"). One
# per depth tier, per `03-worker.md` §2's registry/tracked split; resolved
# from a candidate's `depth` when the caller does not pass an explicit
# `max_sources` (`worker/search_stage.py:_resolve_max_sources`). Governs
# `search.cover.cover()`'s search-sourced picks only — a candidate's own seed
# URL is fetched in addition to this cap, not counted against it.
MAX_SOURCES_TRACKED = int(os.getenv("FPH_MAX_SOURCES_TRACKED", "5"))
MAX_SOURCES_REGISTRY = int(os.getenv("FPH_MAX_SOURCES_REGISTRY", "1"))

# ── One-round escalation budget (`worker/search_stage.py`'s `escalate=True`
# path). Added on top of the depth cap above, not counted against it — a
# candidate whose confirmed set came back thin (`confirm_policy.
# prompt_set_is_thin`) gets one further `cover()` pass over the full fused
# pool at `cap + MAX_SOURCES_ESCALATE`, so the first budget having proved
# insufficient doesn't shrink the second. groundwater-depletion-from-
# irrigation (candidate 12, 2026-09-14) is the motivating case: 1 usable
# source out of 5 fetched, all from one narrow Kerala domain family, with
# the rest of the fused pool never fetched at all.
MAX_SOURCES_ESCALATE = int(os.getenv("FPH_MAX_SOURCES_ESCALATE", "20"))

# ── Track D — the local SearXNG instance the CLI's `--search-url` defaults
# to (`engine/poc/searxng/run.sh start`, CLAUDE.md's "once per session" —
# it does not autostart the container). Wired into `worker/worker.py:main`
# 2026-09-14; `--no-search` is the explicit escape hatch back to
# `run_batch`'s `search_provider=None` seed-URL-only degrade (§13). An
# unreachable URL is NOT a degrade path — `SearxngProvider.query` calls
# `resp.raise_for_status()`/`requests.get` with no retry, so a down
# instance raises and stops the batch rather than silently falling back;
# start it first (`engine/poc/searxng/run.sh start`) or pass `--no-search`.
SEARXNG_URL = os.getenv("FPH_SEARXNG_URL", "http://localhost:8080")
