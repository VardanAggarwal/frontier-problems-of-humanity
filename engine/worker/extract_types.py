"""Track E — the types the extraction path's four tasks share.

They live here, in a module that imports nothing from the pipeline, for one
reason: E1 (search stage), E2 (prompt + parser), E3 (passage assembly) and
E4 (ledger) were built concurrently, and `04-worker-build-plan.md` §5's
"freeze five contracts before the tracks start" applies to sub-tasks of a
track exactly as it does to tracks. `prompts.py` and `extract.py` both need
these names; either importing the other would be a cycle.

Frozen here, not negotiable at integration:

- **`chunk_ref` is `f"{source_id}:{ordinal}"`** — `text/chunk.py:93` already
  emits that shape, so it is frozen by fact rather than by agreement.
- **`label` is prompt-local, `source_id` is durable.** The model sees `S1`,
  `S2`, … and answers in those terms (PoC-2 measured 95/95 valid labels on
  that shape); nothing downstream of the parser may use a label. `Answer`
  therefore carries the resolved `source_id`, and resolving it is the
  parser's job, not the ledger's.
"""
from __future__ import annotations

from typing import NamedTuple


class ConfirmedSource(NamedTuple):
    """One fetched, confirmation-passed page. E1's output, E3's input."""
    source_id: str          # `source.id` — durable, an FK target
    url: str
    text: str
    origin: str             # search.confirm_policy SEED | SEARCH
    verdict: str            # search.confirm_policy CONFIRMED | UNCERTAIN


class PromptSource(NamedTuple):
    """One `[Sn]` block as it will appear in the extraction prompt. E3's
    output, E2's input. `text` is already assembled — selected chunks plus
    their `NEIGHBOUR_RADIUS` neighbours, in document order, joined."""
    source_id: str
    label: str              # "S1" — prompt-local, never persisted
    url: str
    text: str
    chunk_refs: tuple[str, ...]   # every chunk in `text`, document order


class Answer(NamedTuple):
    """One parsed answer. E2's output, E4's input — and the row shape the
    `finding` table takes, minus `candidate_id` and `gathered_at`."""
    question_id: str
    answer: str
    source_id: str          # resolved from the model's label by the parser
    confidence: float | None = None
    chunk_ref: str | None = None    # None when the block held >1 chunk and
                                    # the answer cannot be narrowed to one
