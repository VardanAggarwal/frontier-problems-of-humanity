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

    Reads `obj["signals"]` — named for the edge because that was its only
    caller, but the shape is the spec's and the prompt puts it on the EMIT
    (§10). `signals_for_problem` below is what an edge-minted problem goes
    through; this stays the shaping primitive for both.

    The prompt began asking for the four fields on 2026-09-14. Before that
    it showed the model an empty `"signals": {}` placeholder with no
    instruction anywhere saying what belonged in it, so `{}` was the
    compliant answer and this returned four `None`s on every real response.
    Four `None`s remains the correct value when the source was silent
    ("`null` means the source didn't support it, NOT a 'no'") — it is not a
    stand-in to be guessed at here.
    """
    raw = edge.get("signals")
    if not isinstance(raw, dict):
        raw = {}
    return {k: raw.get(k) for k in SIGNAL_KEYS}


def signals_for_problem(emits, name: str, norm) -> dict:
    """-> the four gate signals for a problem named by a `works_on` EDGE,
    read off the matching `emits` entry.

    Why the lookup exists. `03-worker.md` §10 puts `signals` on the problem
    EMIT — one place in the response where the model describes a problem.
    The worker's only mint site for a problem, though, is the edges loop: a
    `works_on` destination that doesn't resolve. Those are two different
    objects in the same response, so `signals_from_edge(edge)` returned four
    `None`s even from a perfectly cooperative model — the key was never on
    the edge and the prompt never asked for it there.

    Asking for the four fields a second time, on the edge, would have the
    model describe the same problem twice in one response. Matching by name
    instead keeps the prompt asking once. A miss (the model wrote the edge
    but no emit for it) is four `None`s, which is the spec's value for "the
    source didn't support it" and costs nothing.
    """
    target = norm(name or "")
    if not target:
        return {k: None for k in SIGNAL_KEYS}
    for e in emits or []:
        if not isinstance(e, dict) or e.get("kind") != "problem":
            continue
        if norm(e.get("name") or "") == target:
            return signals_from_edge(e)
    return {k: None for k in SIGNAL_KEYS}


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
