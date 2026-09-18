"""OpenRouter — the engine's only LLM provider — plus its retry/backoff and
JSON handling. Ported into this engine from
`/Users/vardanaggarwal/slate_v2/core/llm.py` 2026-09-13, per 01-minimal.md §7
("Lift, don't rewrite") and step 3 of the build order ("Port core/llm.py").

The port brought slate_v2's full fallback chain (openrouter -> claude -> gemini
-> local, with claude-cli slotting in under a subscription token) and the
Anthropic Batch API helpers. All of it was removed 2026-09-18; `call()`'s
docstring has the reasoning. In short: none of those rungs had ever executed,
and the one that would have — paid Claude — would have made a broken
extraction call expensive rather than correct. One provider, several models
under it, and a call that is expected to succeed on the first shot.

call() is the only entry point (used by gate 1 screening and claims
extraction). Callers pick the tier; this module picks the model.

OpenRouter's free tier caps at ~20 req/min. We stay under it two ways: a
client-side pacer (_openrouter_pace) spaces dispatches, and a 429 is caught as
RateLimitError so call() can wait out a short window before moving to the next
model.
"""
import json
import re
import threading
import time

import json_repair

from . import config

# $ per MTok (input, output). Only ever held the two Claude models, which are
# gone — kept as an empty table with its fallback rate because `estimate_cost`
# is still exported. Live OpenRouter calls do NOT use it: `_call_openrouter`
# reads the real per-call cost out of `usage.cost`, which knows OpenRouter's
# actual (and on `:free` models, zero) rates. Add a row here only for a path
# that has to estimate before the call.
_PRICES: dict[str, tuple[float, float]] = {}


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    """A provider hit its request-rate cap (HTTP 429). Carries retry_after
    (seconds) so call() can wait out the window on the same rung instead of
    falling through to a paid one."""
    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


class JSONParseError(LLMError):
    """Every attempt, across every configured provider, returned text that
    failed `json.loads` even after call()'s own retry-with-backoff — the
    model itself is emitting syntactically broken JSON (unquoted keys,
    missing commas, trailing data), not a transient network blip that a
    retry fixes. Raised distinctly from plain LLMError (2026-09-18,
    candidates 528/552/560) so a caller with a per-source rescue —
    worker.py's `retry_per_source`, §13 — can fall back to it instead of
    treating this the same as a real network/provider outage and skipping
    the whole candidate. Before this, a persistent parse failure never
    reached that rescue at all: `parse_json`'s JSONDecodeError was caught by
    call()'s generic `except Exception`, retried, and on exhaustion raised
    as a plain LLMError — indistinguishable from any other failure by the
    time it reached worker.py."""


# Serializes openrouter dispatches to keep them ≥ OPENROUTER_MIN_INTERVAL_S
# apart (client-side pacing under the free-tier req/min cap). Holding the lock
# across the sleep is intentional: it spaces concurrent callers, not just this
# thread. Uses a monotonic clock so it is immune to wall-clock jumps.
_openrouter_lock = threading.Lock()
_openrouter_last = [0.0]


def _openrouter_pace() -> None:
    interval = config.OPENROUTER_MIN_INTERVAL_S
    if interval <= 0:
        return
    with _openrouter_lock:
        wait = interval - (time.monotonic() - _openrouter_last[0])
        if wait > 0:
            time.sleep(wait)
        _openrouter_last[0] = time.monotonic()


def _retry_after_seconds(resp) -> float:
    """Seconds to wait per a 429's headers. Retry-After is seconds (or an
    HTTP-date, which we ignore); OpenRouter's X-RateLimit-Reset is a Unix epoch
    in milliseconds. Falls back to a fixed default when neither is present."""
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            return max(0.0, float(ra))
        except ValueError:
            pass  # HTTP-date form — fall through to reset header / default
    reset = resp.headers.get("X-RateLimit-Reset")
    if reset:
        try:
            return max(0.0, float(reset) / 1000.0 - time.time())
        except ValueError:
            pass
    return config.OPENROUTER_RATELIMIT_DEFAULT_WAIT


def _openrouter_models_for_tier(tier: str) -> list[str]:
    return (config.OPENROUTER_MODELS_JUDGMENT if tier == "judgment"
            else config.OPENROUTER_MODELS_MECHANICAL)


def parse_json(raw: str) -> dict:
    """Strip code fences / stray prose and parse the first JSON object."""
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"\s*```$", "", clean.strip())
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _repair_json(raw: str) -> dict | None:
    """Best-effort recovery for a response that already failed `parse_json`'s
    strict `json.loads` — the genuine syntax breaks logged 2026-09-18 even
    under JSON mode (unquoted keys, missing commas, trailing data:
    `Expecting property name enclosed in double quotes`, `Expecting ','
    delimiter`, `Extra data`). Tried once per attempt, before that attempt is
    counted as a parse failure, so a single stray comma no longer costs a
    retry or routes the whole candidate to the §13 per-source rescue.

    Returns the parsed dict on success, None on anything else (including a
    successful repair that isn't a dict — json_repair returns `''` rather
    than raising on pure prose, which must NOT be treated as a usable
    result). None is not a silent mask: the caller still raises exactly as
    before when this returns None, and a caller-visible log line marks every
    successful repair, so a model that is persistently broken remains
    visible as an anomaly even though it no longer aborts the attempt."""
    try:
        repaired = json_repair.loads(raw)
    except Exception:
        return None
    return repaired if isinstance(repaired, dict) else None


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Pre-call estimate from `_PRICES`. Prefer the `cost` field `call()`
    returns, which is OpenRouter's own measured figure for that call."""
    inp, out = _PRICES.get(model, (3.0, 15.0))
    return (input_tokens * inp + output_tokens * out) / 1_000_000


# ── Sync path ─────────────────────────────────────────────────────────────────
def _call_openrouter(prompt: str, model: str, max_tokens: int, system: str | None) -> dict:
    """OpenRouter — OpenAI-compatible chat/completions, one key routes to many
    underlying models. Primary rung: tried first, before any direct provider."""
    import requests
    _openrouter_pace()  # stay under the free-tier req/min cap
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages, "max_tokens": max_tokens,
              # Low, not zero: some free-tier backends reject temperature=0
              # outright on certain routes. 0.1 rather than higher because
              # lower sampling entropy means fewer of the formatting mistakes
              # (unquoted keys, dropped commas, duplicated objects) seen
              # 2026-09-17/18 regardless of whether response_format is
              # actually honored underneath (see require_parameters below).
              "temperature": 0.1,
              # Constrains decoding to syntactically valid JSON on models
              # that support OpenAI-style JSON mode (both configured free
              # models CLAIM to). Doesn't enforce our schema, but is meant to
              # kill the unbalanced-brace/missing-comma/unescaped-quote class
              # of malformed response outright — cheaper than any retry.
              # Considered switching to `{"type": "json_schema", ...}`
              # (NVIDIA's own Nemotron docs recommend it, and this model
              # supports it) — deferred 2026-09-18. The batched-extraction
              # shape (`worker/prompts.py::extract_prompt_batched`) has an
              # `answer` field whose type varies per question (free text,
              # enum, or a list for `geography`-style multi-answers — see
              # `parse_answers`'s own comment on that), an open `question_id`
              # enum sourced from `questions.yaml` that grows over time, and
              # several fields present only conditionally (`chunk`, `reason`,
              # `signals`). Pinning that in strict JSON Schema either forces
              # every optional/polymorphic field to `anyOf`-with-null (a
              # schema that needs editing every time a question is added) or
              # loosens `strict` enough to lose the enforcement this was for.
              # `json_repair` below (see `_repair_json`) targets the actual
              # observed failure mode — syntax breaks, not shape drift — at
              # far less maintenance cost. Revisit if the schema stabilizes.
              "response_format": {"type": "json_object"},
              # THE fix for the 2026-09-18 extraction failures (candidates
              # 528/552/560), measured not guessed. Every configured free
              # model is a reasoning model, and OpenRouter charges hidden
              # chain-of-thought against `max_tokens`. Measured on the real
              # batched prompt (8 sources, 14,981 input tokens, the budget
              # `extraction_max_tokens` picks: 10,240):
              #
              #   reasoning on  -> 8,922 of 10,240 output tokens spent on
              #                    reasoning, ~1,300 left for the answer;
              #                    finish_reason="length", content begins
              #                    "{\n{\n" (a force-closed partial), 110s,
              #                    unparseable and unrepairable.
              #   reasoning off -> 2,023 output tokens, finish_reason="stop",
              #                    26s, parses clean: 19 answers + emits +
              #                    edges, the complete expected shape.
              #
              # So the failure was never malformed JSON, and every mechanism
              # built against it (json_repair, model-level fallback,
              # require_parameters, §13's per-source rescue) was treating a
              # truncation as a syntax break — retrying a call that could not
              # fit its answer in the budget left, at the same budget, 12
              # times. Turning reasoning off makes the call a single shot
              # that succeeds, which is cheaper than any retry path and is
              # why the retry fan-out below is now deliberately small.
              #
              # This is an extraction task, not a reasoning task: the model
              # is copying spans out of supplied text into a fixed schema.
              # There is nothing for chain-of-thought to work out. If a
              # genuinely reasoning-shaped call is ever added, give it its
              # own tier rather than turning this back on globally.
              "reasoning": {"enabled": False},
              # `provider: {require_parameters: True}` was added here
              # 2026-09-17 on the theory that the syntax breaks came from
              # OpenRouter routing to a backend that silently ignored
              # `response_format`. Removed 2026-09-18: the syntax breaks were
              # truncation (see `reasoning` above), so it was never treating
              # the real cause — and it had a cost of its own. It restricts
              # routing to backends implementing EVERY parameter in this
              # request, and three of the four models then configured in
              # `.env` support neither `response_format` nor
              # `structured_outputs` at all (checked against OpenRouter's
              # live `/models` endpoint, not assumed), so for those it left
              # zero routable backends and returned a hard
              # `404 No endpoints found that can handle the requested
              # parameters` — visible in the candidate-528 run log. A 404
              # burns the model's slot in the fallback loop for a reason
              # that has nothing to do with the response.
              #
              # The measured-good configuration (reasoning off +
              # `response_format`, no `require_parameters`) parses clean, so
              # the enforcement this was meant to provide is not needed. The
              # model list in `config.py` is the right place to guarantee
              # parameter support — keep it to models that actually declare
              # `response_format`/`structured_outputs`.
              # Ask OpenRouter to report real dollar cost in usage.cost —
              # omitted, it silently reads as 0.0 even on paid models.
              "usage": {"include": True}},
        timeout=120,
    )
    if resp.status_code == 429:
        raise RateLimitError(f"openrouter 429: {resp.text[:200]}",
                             _retry_after_seconds(resp))
    if resp.status_code != 200:
        raise LLMError(f"openrouter {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError as e:
        # HTTP 200 with a body that isn't valid JSON — observed in production
        # (candidate 12, 2026-09-14/15, judgment tier, 13-source prompt,
        # max_tokens=4096) as pure keep-alive whitespace padding and nothing
        # else: OpenRouter sends periodic whitespace on a chunked response
        # while a free-tier model is slow to generate, and the free-tier
        # gateway can close the stream before real content ever arrives —
        # `resp.status_code` stays 200 because headers went out first. Plain
        # `resp.json()` surfaces this as a bare `json.JSONDecodeError:
        # Expecting value: line 1 column 1 (char 0)`, which says nothing
        # about WHY — not "rate limited", not "wrong model", not "timeout".
        # Diagnose it here once, at the only place that still holds the raw
        # response, so the next person hitting this doesn't need a manual
        # `requests.post` reproduction session to find out what `call()`'s
        # eventual "all providers failed" masks (see llm.py's `call()` for
        # the separate fix to that masking).
        body = resp.text
        shape = ("empty" if not body
                 else "whitespace-only" if not body.strip()
                 else f"{len(body)} chars, not JSON")
        raise LLMError(
            f"openrouter {model}: HTTP 200 but body is {shape} "
            f"(content-length header: {resp.headers.get('content-length', '?')}, "
            f"transfer-encoding: {resp.headers.get('transfer-encoding', '?')}) "
            f"— likely the free-tier gateway closing the stream before a slow "
            f"generation finished, not a real success; json error: {e}"
        ) from e
    choice = (data.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content", "")
    truncated = choice.get("finish_reason") == "length"
    # Reasoning models (GPT-OSS, Nemotron) can burn the whole max_tokens
    # budget on hidden chain-of-thought and return EMPTY visible content with
    # finish_reason="length" — that must flow through as truncated=True so
    # call() escalates the budget, not raise (which would retry at the same
    # budget forever via the backoff path instead).
    if not text and not truncated:
        raise LLMError(f"openrouter empty response: {str(data)[:200]}")
    # `finish_reason` under-reports truncation on some free-tier models
    # (observed 2026-09-17, worker/runs/*.log: `json.JSONDecodeError` at char
    # offsets in the 16K-22K range — right at the max_tokens=4096 character
    # budget — with finish_reason=="stop" instead of "length"). A JSON-mode
    # response that doesn't end on a closing brace/bracket almost certainly
    # got cut off mid-string/mid-array rather than malformed mid-stream —
    # treat it as truncated too, so call() escalates the budget instead of
    # retrying the same call at the same budget and failing identically each
    # time (LLM_MAX_ATTEMPTS). Only applies to non-empty text; an empty
    # truncated response was already handled above.
    if not truncated and text:
        stripped = text.strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()
        if stripped and stripped[-1] not in "}]":
            truncated = True
    usage = data.get("usage") or {}
    in_tok, out_tok = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    # The bracket check above is blind to the failure it was added for once
    # `response_format=json_object` (this function, above) is in play: a
    # grammar-constrained decoder that runs out of budget force-closes the
    # object early to stay valid JSON, so the response ends on `}` either
    # way — syntactically complete, semantically short a key (`emits`/
    # `edges` dropped), and `json.loads` never complains (2026-09-18,
    # candidate 560's "malformed extraction JSON (dict)"). completion_tokens
    # landing at (or past) the requested budget is the only signal left that
    # generation was cut off rather than finished early — a small margin
    # below max_tokens covers off-by-a-few accounting between providers.
    if not truncated and out_tok and out_tok >= max_tokens - 4:
        truncated = True
    return {
        "text": text,
        "provider": "openrouter",
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        # OpenRouter reports the real dollar cost per call (0.0 on :free
        # models) — use it directly instead of our own per-model price table,
        # which doesn't know OpenRouter's (possibly discounted) rates.
        "cost": usage.get("cost", 0.0),
        "truncated": truncated,
    }


MAX_TOKENS_CEILING = 16384  # cap for the truncation-retry escalation below


def extraction_max_tokens(n_sources: int) -> int:
    """Starting `max_tokens` budget for a batched extraction call, scaled by
    source count instead of a flat 4096 — the actual bottleneck behind
    "malformed extraction JSON (dict)" (2026-09-18). `_call_openrouter`'s
    `response_format=json_object` makes a truncated generation come back as
    a syntactically valid but incomplete dict (missing `emits`/`edges`)
    rather than a parse failure, so the truncation never trips `truncated`
    below and never reaches `call()`'s own retry/escalation loop — it
    silently parses and only fails worker.py's schema check downstream. A
    5-source batch (candidate 560, 2026-09-17 log) already tripped this at
    4096; each source can carry several `answers` (with `reason`/`chunk`)
    plus `edges` (each with a `signals` object), so per-source cost isn't
    flat. 2048 base (schema overhead, `misidentified`) + ~1024/source is a
    reasoned budget, not a measurement — capped at MAX_TOKENS_CEILING so a
    large batch doesn't request more than a configured model will honor."""
    return min(2048 + 1024 * max(1, n_sources), MAX_TOKENS_CEILING)


def call(prompt: str, tier: str = "mechanical", max_tokens: int = 2048,
         system: str | None = None, json_out: bool = True,
         models: list[str] | None = None) -> dict:
    """One provider — OpenRouter — with model-level fallback inside it.

    The claude / claude-cli / gemini / local rungs were removed 2026-09-18.
    They had been the documented safety net since the port from slate_v2, but
    in practice they were never a net at all: `anthropic` and `google-genai`
    are deliberately absent from `requirements.txt`, so both rungs raised
    ImportError on every call; `claude-cli` needed a `CLAUDE_CODE_OAUTH_TOKEN`
    that was never set, so it was skipped silently by the `configured` test
    and did not even appear in the failure message; and `local` had no branch
    in that test at all. A five-rung chain was one rung deep, and its only
    real effect was to bury OpenRouter's actual error under two expected
    "required package not installed" lines (the candidate-528 run log is the
    clean example). Installing the paid rungs would have made a bad
    extraction call cost money instead of making it work — the fix belongs
    upstream, in making the single OpenRouter call succeed first time (see
    `_call_openrouter`'s `reasoning` comment, which is what actually fixed
    it). Re-add a rung here when there is a reason to, not as insurance.

    `models` restricts this ONE call to a subset of the tier's model list.
    Per-call rather than by assigning config.OPENROUTER_MODELS_*: a concurrent
    caller mutating the module global would race, and a save/restore pair that
    interleaves can capture an already-narrowed list and leave it permanently
    narrowed, silently costing every other caller its fallback.

    Returns {json?, text, provider, model, input_tokens, output_tokens, cost}.
    Raises LLMError when every model fails — callers that have a local
    fallback catch it; others let it bubble so the run records a failed
    status and retries next time.
    """
    if not config.OPENROUTER_KEY:
        raise LLMError("openrouter: OPENROUTER_API_KEY is not set")
    model_list = models if models is not None else _openrouter_models_for_tier(tier)
    if not model_list:
        raise LLMError("openrouter: no model configured for tier " + tier)

    last_err: Exception | None = None
    # Latches True the moment any attempt's failure was a JSON parse error
    # rather than a network one — sticky across models so a later model's
    # different failure can't erase the signal. Read at the final raise below
    # to pick JSONParseError over the generic LLMError.
    json_parse_failed = False
    # One entry per model that was tried and gave up, "{model}: {err}".
    # `last_err` alone used to be the final raise's only evidence, and it gets
    # overwritten by every subsequent try — so the one model whose failure
    # actually mattered was routinely replaced by a later one's uninteresting
    # error and never seen (candidate 12, 2026-09-14/15). Every model's last
    # error is kept here, so the final message shows the whole list.
    attempts_log: list[str] = []
    attempts = max(1, config.LLM_MAX_ATTEMPTS)

    # Retry/backoff is the OUTER loop and model fallback the INNER one. The
    # nesting is the whole behaviour, so it is worth stating why:
    #
    #   models inner (this)  — a dead model costs ONE call before a live one
    #                          is tried. The common failure (one backend down,
    #                          another fine) resolves in seconds.
    #   models outer         — a dead model burns every attempt AND its
    #                          backoff sleeps before failover. Strictly worse
    #                          for the same worst case.
    #
    # Worst case either way is `attempts * len(model_list)` HTTP calls, and
    # that product is the thing to keep small. The candidate-528 run had
    # 3 x 4 = 12 calls per logical extraction at ~110s each, and not one of
    # them could have succeeded — the answer didn't fit the token budget,
    # which no retry changes. Retries are for transient network failures; the
    # model list is for a backend being down. Neither fixes a response the
    # model got wrong, and sizing them as if they did is what turned a
    # 30-second bug into a 45-minute one. The fix for a wrong response lives
    # in the request (see `_call_openrouter`'s `reasoning` comment), not here.
    cur_max_tokens = max_tokens
    attempt = 0
    rl_waits = 0  # rate-limit waits are free — they don't consume attempts
    while attempt < attempts:
        try:
            # Try each configured model once before this attempt gives up. A
            # malformed/empty response, a dead backend or an upstream-vendor
            # 429 for one model says nothing about the next, which is a
            # different backend (candidate 12, 2026-09-14/15: the sole
            # configured model returned HTTP 200 with a whitespace-only body
            # and the whole run produced nothing).
            #
            # RateLimitError is model-retried here too (revised 2026-09-15):
            # a 429 is two different things wearing one status code — the
            # account key's own request-rate cap, or an upstream vendor's
            # congestion for that one free model ("google/gemma-4-31b-it:free
            # is temporarily rate-limited upstream"). The second kind a
            # different model simply doesn't have. If EVERY model 429s,
            # `or_err` is still a RateLimitError and reaches the outer
            # wait-out-the-window handler unchanged via `raise or_err` — the
            # safety net is kept, just no longer triggered by the first
            # model's 429.
            result = None
            or_err: Exception | None = None
            for m in model_list:
                try:
                    result = _call_openrouter(prompt, m, cur_max_tokens, system)
                    break
                except Exception as e:  # try the next model
                    or_err = e
                    attempts_log.append(f"{m}: {e}")
            if result is None:  # every configured model failed
                raise or_err or LLMError("no openrouter model configured")

            if result.get("truncated") and cur_max_tokens < MAX_TOKENS_CEILING \
                    and attempt < attempts - 1:
                last_err = LLMError(
                    f"{result['model']} truncated at max_tokens={cur_max_tokens}")
                cur_max_tokens = min(cur_max_tokens * 2, MAX_TOKENS_CEILING)
                attempt += 1
                continue  # retry immediately at a bigger budget, no backoff
            if json_out:
                try:
                    result["json"] = parse_json(result["text"])
                except json.JSONDecodeError:
                    repaired = _repair_json(result["text"])
                    if repaired is None:
                        raise
                    print(f"llm: repaired malformed JSON output from "
                          f"{result['model']} (strict parse failed, "
                          f"json_repair succeeded)")
                    result["json"] = repaired
            return result
        except RateLimitError as e:
            # Every model is rate-limited. Wait out a short window and try the
            # list again; cap both the wait (a daily cap resets hours out —
            # don't block on it) and the number of waits.
            last_err = e
            if e.retry_after <= config.OPENROUTER_RATELIMIT_MAX_WAIT \
                    and rl_waits < config.OPENROUTER_RATELIMIT_MAX_RETRIES:
                rl_waits += 1
                time.sleep(e.retry_after)
                continue  # free retry: same attempt index, same budget
            break
        except Exception as e:
            last_err = e
            if isinstance(e, json.JSONDecodeError):
                json_parse_failed = True
            attempt += 1
            if attempt < attempts:
                time.sleep(config.LLM_BACKOFF_BASE * (2 ** (attempt - 1)))

    detail = "; ".join(attempts_log) if attempts_log else str(last_err)
    if json_parse_failed:
        raise JSONParseError(f"all openrouter models failed (JSON parse): {detail}")
    raise LLMError(f"all openrouter models failed: {detail}")
