"""The local encoder. Ported from ../slate_v2/core/encode.py, with one
substantive change and one contract that MiniLM did not have.

The change: `multilingual-e5-small` rather than `all-MiniLM-L6-v2`. §8 finding 2
promoted embeddings from a cross-lingual special case to the primary dedup path
for roughly half the corpus, and a corpus that will draw on Hindi, Marathi and
Tamil sources cannot have its dedup path be English-only. Same 384 dimensions,
so the vec0 column width is unchanged.

The contract: **e5 requires a prefix on every input, and the prefix marks the
input's role in the comparison, not the kind of text.** Two texts compared as
peers are both `query: ` — a problem's one-liner against a candidate's snippet
is symmetric, however document-shaped the candidate looks. `passage: ` is for
the long side of an asymmetric retrieval, where a short query is matched
against full documents; nothing in the engine does that yet (§8).

Omitting the prefix does not error. It silently degrades the vectors, which is
why `encode` takes `role` as a keyword with no default that can be gotten wrong
by accident, and refuses text that already carries a prefix.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Sequence

MODEL_NAME = os.getenv("FPH_EMBED_MODEL", "intfloat/multilingual-e5-small")
EMBED_DIM = 384

ROLES = ("query", "passage")
_PREFIXED = re.compile(r"^\s*(query|passage)\s*:\s", re.I)

# Cheap, script-blind pre-bound on `fit()`'s input, applied before the
# token-exact search runs. `fit()` alone does not bound the cost of *getting*
# to a truncated string: its first step (`length(body)`) tokenizes the whole,
# uncapped `body` once just to check whether truncation is even needed
# (model.py:83, below). Candidate 28 (4464 tokens, 8.7x the 512 budget) and
# candidate 71 (2922 tokens) both hung inside that call chain on genuinely
# unbounded input — `gate2.confirm()`'s `candidate_context` and
# `resolve.resolve_entity()`'s `context` are both documented as "may be the
# full fetched/extracted text." This does not fix the hang (a timeout does,
# see `EmbedTimeout` below) — it shrinks the worst case a pathological/slow
# tokenizer call has to chew through, on every `fit()` caller at once, rather
# than each site clipping for itself.
_FIT_PRECLIP_CHARS = 8000  # ~4x the 2000-char budget in embed/texts.py — far
                            # more headroom than any legitimate 512-token
                            # string needs, in any script.

_encoder = None


class EmbedTimeout(TimeoutError):
    """`fit()`/`encode_one()` did not return within the allotted time.

    Both candidate 28 (2026-09-14T22:45) and candidate 71 (2026-09-15T07:54)
    hung here indefinitely with no exception — the process sat idle,
    blocked, until killed externally. Truncating the input tighter
    (`_FIT_PRECLIP_CHARS` above) narrows the worst case but does not prove
    there is no still-slow path left, so this is the backstop: callers get a
    catchable error back instead of a dead process.
    """


def get_encoder():
    """Singleton. First call downloads the model (~470 MB) and is slow; every
    call after is warm — but "warm" is per-process, and each worker run
    (`python -m worker.worker --ids N`) is a fresh process, so this runs
    once per candidate. Tried `local_files_only=True` first: once the model
    is cached, that skips the HF Hub network round-trip (the "unauthenticated
    requests" warning) `SentenceTransformer(MODEL_NAME)` does by default to
    check for updates — measured 2s vs. 15s cold-start on this machine with
    the model already on disk. Falls back to the network path so a machine
    without the cache still works, just slower.

    `device="cpu"` — deliberately, not left to auto-select. On Apple Silicon
    `SentenceTransformer` defaults to `mps:0` (the Metal/GPU backend), and
    that is the actual root of the "hang" this module's `EmbedTimeout`
    machinery was built to catch: `lldb -p <pid> -o "bt all"` on a genuinely
    stuck worker (2026-09-15, candidate 78 "Amit Doshi") showed the main
    thread wedged inside `at::mps::MPSStream::synchronize` ->
    `-[_MTLCommandBuffer waitUntilCompleted]` — a Metal command buffer that
    never signalled completion. Not a tokenizer issue at all; the earlier
    "Token indices sequence length..." warning was a correlated red herring
    (both fire on long text) rather than the cause. The `with_timeout` wrap
    around `fit()`+`encode_one()` stays as a backstop, but a GPU
    driver-level wait is not reliably interruptible the way CPU/Python code
    is, so it cannot be trusted alone. Cost of forcing CPU is negligible: a
    384-dim model encoding one short string per call has nothing for a GPU
    to meaningfully accelerate.
    """
    global _encoder
    if _encoder is None:
        # A live worker (candidate 20/22, 2026-09-15T09:48) hung again after
        # the device=cpu fix. `lldb -p <pid> -o "bt all"` showed the *main*
        # thread blocked in `_ssl__SSLSocket_read` -> `PySSL_select` ->
        # `poll` — a live network read, not MPS. `local_files_only=True`
        # (a prior fix) is a kwarg to `SentenceTransformer`'s own loader; it
        # does not reliably reach every internal `huggingface_hub` call some
        # versions make. `HF_HUB_OFFLINE=1` (harder switch) doesn't fully
        # hold either: tested against a blackholed network, this dependency
        # version still retries live HTTP HEAD requests for optional config
        # files even after cached weights load. So this doesn't try to be
        # clever about avoiding the network — it sets the env var anyway
        # (harmless, may help on other dependency versions) and relies on
        # `with_timeout` to bound the wait.
        #
        # First attempt at that bound only wrapped `SentenceTransformer(...)`
        # construction, not the `from sentence_transformers import ...` line
        # above it — and the hang recurred identically (candidate 21,
        # 2026-09-15T10-06), same stack, because the import itself makes a
        # network call: confirmed live, `import sentence_transformers` alone
        # against a blackholed network took 9.5s instead of being instant.
        # So the import has to be *inside* the timeout too — anything that
        # can touch the network before the model is usable belongs inside
        # the one call this function makes to `with_timeout`, not split
        # across an unguarded line and a guarded one.
        import os
        os.environ.setdefault("HF_HUB_OFFLINE", "1")

        def _load():
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer(MODEL_NAME, device="cpu")

        _encoder = with_timeout(_load, timeout_s=45.0, label="get_encoder")
    return _encoder


def prefix(text: str, role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    text = (text or "").strip()
    if not text:
        raise ValueError("refusing to embed empty text")
    if _PREFIXED.match(text):
        raise ValueError(
            f"text already carries an e5 prefix: {text[:40]!r} — pass the bare "
            "text and let `role` decide")
    return f"{role}: {text}"


def fit(text: str, *, role: str = "query") -> str:
    """Truncate `text` so that, once prefixed, it survives the encoder whole.

    `texts.clip` bounds by characters, which is cheap and script-blind: 2,000
    characters is ~504 tokens of English but ~610 of Devanagari, so on the very
    corpus that motivated a multilingual encoder about a sixth of each long
    record was being dropped by the tokenizer with nothing said. Clipping in the
    tokenizer's own units makes the loss explicit.

    Every measurement below is taken on the *prefixed* string. The one-step
    version — tokenize `prefix + body`, drop `len(tokenize(prefix))` tokens off
    the front, keep the rest — assumes the joint tokenization begins with the
    prefix's own tokens, and a sub-word tokenizer gives no such guarantee: it
    may merge across the boundary, in which case the slice starts mid-word and
    the record is quietly embedded as something else. Nothing would have
    flagged it, since the result is still a valid string of the right length.
    """
    encoder = get_encoder()
    budget = getattr(encoder, "max_seq_length", 512) - 2   # the special tokens
    tok = encoder.tokenizer
    body = (text or "").strip()[:_FIT_PRECLIP_CHARS]

    def length(s: str) -> int:
        return len(tok(prefix(s, role), add_special_tokens=False)["input_ids"])

    if length(body) <= budget:
        return body
    # Binary search on the body's own tokens for the longest prefix of it that
    # still fits once the role prefix is attached. ~9 tokenizations, and only
    # for a record that is actually over the limit.
    ids = tok(body, add_special_tokens=False)["input_ids"]
    lo, hi, best = 1, min(len(ids), budget), ""
    while lo <= hi:
        mid = (lo + hi) // 2
        cut = tok.decode(ids[:mid], skip_special_tokens=True).strip()
        if cut and length(cut) <= budget:
            best, lo = cut, mid + 1
        else:
            hi = mid - 1
    return best


def encode(texts: Sequence[str] | Iterable[str], *, role: str, batch_size: int = 32):
    """-> float32 (n, EMBED_DIM), L2-normalized, so cosine is a dot product."""
    if role not in ROLES:      # checked here too: an empty input never reaches
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    items = [prefix(t, role) for t in texts]
    if not items:              # `prefix`, and would have returned a valid shape
        import numpy as np
        return np.zeros((0, EMBED_DIM), dtype="float32")
    vectors = get_encoder().encode(
        items, batch_size=batch_size, normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False)
    return vectors.astype("float32")


def encode_one(text: str, *, role: str):
    """-> float32 (EMBED_DIM,)"""
    return encode([text], role=role)[0]


def with_timeout(fn, *, timeout_s: float = 45.0, label: str = "embed call"):
    """Run `fn()` on a fresh daemon thread, bounded by a wall-clock timeout —
    raises `EmbedTimeout` instead of hanging forever.

    A callable, not a fixed `fit`+`encode_one` pipeline: callers pass a
    closure over their own (possibly test-patched) `fit`/`encode_one`, so
    `gate2.py`/`resolve.py` keep those names importable and monkeypatchable
    at the module level — this only adds the timeout around whatever they
    call.

    Runs on a fresh thread rather than a shared pool: a stuck call must not
    wedge every call after it, and Python cannot force-kill a thread, so on
    timeout the thread is abandoned, not stopped, and keeps running in the
    background. `daemon=True` means an abandoned thread cannot block process
    exit even if it never returns — both known hangs (candidate 28,
    candidate 71) sat idle/blocked rather than spinning CPU, so leaking a
    blocked thread is a safe trade against wedging the worker. 45s clears
    cold-start (measured ~2-15s: `get_encoder()`'s first call per process,
    even from the local cache) with headroom, while still catching the
    candidate-28/71 class of hang (6+ minutes and counting, not a slow load).
    """
    import threading
    result: dict = {}

    def _run():
        try:
            result["value"] = fn()
        except Exception as exc:                      # noqa: BLE001 — reraised below
            result["error"] = exc

    t = threading.Thread(target=_run, daemon=True, name="embed-timeout")
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise EmbedTimeout(f"{label} did not return within {timeout_s}s")
    if "error" in result:
        raise result["error"]
    return result["value"]
