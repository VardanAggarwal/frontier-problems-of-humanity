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
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Claude Code subscription token (`claude setup-token`) — bills the Max/Pro
# subscription instead of the API key.
CLAUDE_CODE_OAUTH_TOKEN = os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "")

# ── Model tiering — mechanical (gate 1 screening) vs judgment (claims
# extraction, merge/split) — §7's tier-4 split. ──────────────────────────
CLAUDE_MODEL_MECHANICAL = os.getenv("CLAUDE_MODEL_MECHANICAL", "claude-haiku-4-5")
CLAUDE_MODEL_JUDGMENT = os.getenv("CLAUDE_MODEL_JUDGMENT", "claude-sonnet-4-6")

OPENROUTER_MODEL_MECHANICAL = os.getenv(
    "OPENROUTER_MODEL_MECHANICAL", "nvidia/nemotron-3-super-120b-a12b:free")
OPENROUTER_MODEL_JUDGMENT = os.getenv(
    "OPENROUTER_MODEL_JUDGMENT", "nvidia/nemotron-3-super-120b-a12b:free")

# openrouter tried first: one key, many underlying models, its own failover.
# Direct rungs (claude-cli/claude/gemini) are the fallback chain below it.
LLM_FALLBACK_ORDER = _csv("LLM_FALLBACK_ORDER", ["openrouter", "claude", "gemini", "local"])
GEMINI_MODELS = _csv("GEMINI_MODELS", ["gemini-2.5-flash", "gemini-2.5-flash-lite"])

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

# ── Track D/E1 — search stage source cap (`03-worker.md` §7 constants table:
# "Set-cover rarely needs more than 5 to exhaust the covered families"). One
# per depth tier, per `03-worker.md` §2's registry/tracked split; resolved
# from a candidate's `depth` when the caller does not pass an explicit
# `max_sources` (`worker/search_stage.py:_resolve_max_sources`). Governs
# `search.cover.cover()`'s search-sourced picks only — a candidate's own seed
# URL is fetched in addition to this cap, not counted against it.
MAX_SOURCES_TRACKED = int(os.getenv("FPH_MAX_SOURCES_TRACKED", "5"))
MAX_SOURCES_REGISTRY = int(os.getenv("FPH_MAX_SOURCES_REGISTRY", "1"))
