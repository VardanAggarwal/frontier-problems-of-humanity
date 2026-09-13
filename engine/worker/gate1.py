"""Gate 1 — the pre-fetch batched screen (01-minimal.md §5, §7 tier 4).

"The highest-leverage paid piece" (§5): batching 50 decisions into one prompt
is roughly a 50x reduction against per-candidate calls, and it saves the
fetch, the boilerplate strip and the extraction for everything discarded
here. Tuned for recall (`prompts.screen_prompt` says so to the model
directly) — the cost of a false discard here is invisible (you never see
what you dropped), so every default in this module leans toward keeping a
candidate rather than dropping it.

Two failure shapes are both handled by defaulting to keep, never to discard:
a response that names fewer ids than were sent (partial JSON, model
skipped some), and a response that never arrives at all (`LLMError` — a
transport or provider failure looks nothing like "the model looked at this
and rejected it," and treating it as a rejection would silently turn every
outage into a mass discard with no record of why).
"""
from __future__ import annotations

from . import llm
from .prompts import BATCH_SIZE, screen_prompt


def _chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def screen(candidates: list[dict], *, log=print
          ) -> tuple[dict[str, tuple[bool, str]], float]:
    """candidates: dicts each carrying at least `id` (str or int — stringified
    for the return key). -> ({id_str: (keep, reason)}, cost), one decision per
    input covering every input id even when the model's response does not, and
    the summed dollar cost of every `llm.call` made — §5 calls this "the
    highest-leverage paid piece", so a caller that drops this figure cannot
    ever see what gate 1 spent (it was previously discarded here entirely)."""
    decisions: dict[str, tuple[bool, str]] = {}
    cost = 0.0
    for batch in _chunks(candidates, BATCH_SIZE):
        ids = {str(item["id"]) for item in batch}
        system, prompt = screen_prompt(batch)
        try:
            result = llm.call(prompt, system=system, tier="mechanical", max_tokens=4096)
        except llm.LLMError as e:
            # Infra failure must not look like a rejection (module docstring).
            reason = f"gate1 unavailable: {e}"
            log(f"gate1: batch of {len(batch)} failed ({e}) — keeping all, recall-biased")
            for cid in ids:
                decisions[cid] = (True, reason)
            continue

        cost += result.get("cost", 0.0)
        payload = result.get("json")
        if not isinstance(payload, dict):
            # A model returning a bare JSON array (or any non-object) has no
            # `.get` — treat it the same as "nothing named" rather than crash
            # a whole batch on one malformed response.
            log(f"gate1: batch of {len(batch)} returned non-object JSON "
                f"({type(payload).__name__}) — keeping all, recall-biased")
            for cid in ids:
                decisions[cid] = (True, "gate1: malformed response")
            continue

        seen: set[str] = set()
        for d in payload.get("decisions", []):
            cid = str(d.get("id"))
            if cid not in ids:
                continue  # model hallucinated an id outside this batch
            decisions[cid] = (bool(d.get("keep", True)), str(d.get("reason", "")))
            seen.add(cid)
        missing = ids - seen
        if missing:
            log(f"gate1: {len(missing)} candidate(s) missing from the response "
                f"— defaulting to keep (recall-biased)")
            for cid in missing:
                decisions[cid] = (True, "gate1: missing from model response")
    return decisions, cost
