"""Track A (`04-worker-build-plan.md` §4, `03-worker.md` §10) — pure helpers
for turning an unresolvable `works_on` problem edge into a problem candidate
instead of silently dropping it. Before this track, `worker.py:279-281`
dropped every edge whose destination didn't resolve; for actors the `emits`
loop above it is what turns a mention into a candidate, but nothing did the
equivalent for problems, so problem candidates were never minted this way at
all (measured: 8 candidates emitted on `problems/graph.db`, all actor, zero
problem, against 51 problems and 292 actors that all arrived via the corpus
migration instead).

Only the two genuinely pure pieces of the change live here — no DB, no
network, no model — per §4's "new logic should be pure functions in new
modules wherever possible, unit-testable with no network, no model, no
database." The DB-touching orchestration (running `resolve.resolve_entity`,
inserting the candidate row, writing the edge) stays in `worker.py`'s
`_emit`, which already owns that responsibility for actor emits and cannot
be split out without duplicating its transaction/logging discipline.
"""
from __future__ import annotations

# The four leafability gate signals (03-worker.md §10 / process-leaf's
# leafability gate: "three yeses of four"), captured at extraction time so
# the orchestrator can judge leafability later without re-fetching the page.
# `None` means the source didn't support the field — NOT a "no" — and
# "uncounted" in `magnitude` is a PASS (absence of measurement is a finding;
# *unbounded* is the fail). This module does not judge any of that; it only
# shapes what gets captured and carried on the candidate's `evidence` JSON.
SIGNAL_KEYS = ("harmed_population", "magnitude", "agent", "actionable")


def signals_from_edge(edge: dict) -> dict:
    """-> the four gate signals for a problem-destined edge, each `None` when
    the extraction didn't supply it.

    Reads `edge["signals"]` if present — the shape Track E's extraction-
    prompt update (`prompts.py`, out of this track's scope) is expected to
    add per §10, one `works_on` edge at a time. Until that prompt change
    ships, no edge carries a `signals` key, so this always returns four
    `None`s — which is the correct value per the spec ("`null` means the
    source didn't support it, NOT a 'no'"), not a stand-in that should be
    guessed at here.
    """
    raw = edge.get("signals")
    if not isinstance(raw, dict):
        raw = {}
    return {k: raw.get(k) for k in SIGNAL_KEYS}


def decide_problem_edge(resolution) -> str:
    """resolution: a `resolve.ResolveResult` for the edge's problem
    destination (already run through `resolve.resolve_entity`'s exact-match-
    then-embedding-shortlist order — never exact match alone, because
    problem names are descriptions, not proper nouns: "silicosis in stone
    quarries" and "quarry dust lung disease" are one problem, per
    `03-worker.md` §10).

    ->
      "resolve"  — `exact` or `shortlist_top`: an entity already exists.
                   Link the edge to it; mint nothing.
      "escalate" — `ambiguous`: `resolve.py`'s own module docstring is
                   explicit that an ambiguous merge is an escalation, never
                   an autonomous merge or a new duplicate. Mint nothing,
                   write nothing — the dedupe argument this track exists to
                   satisfy.
      "new"      — genuinely new: mint a problem candidate.
    """
    if resolution.decision in ("exact", "shortlist_top"):
        return "resolve"
    if resolution.decision == "ambiguous":
        return "escalate"
    return "new"
