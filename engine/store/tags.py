"""The tag registry.

Lifted from `problems/data-model.yaml` enums on 2026-09-12 and authoritative
from that point: the engine does not read the markdown corpus at runtime.

A namespace is `open` when its values are not enumerable in advance (geography,
salience, an arbitrary population id). Everything else is closed, and the
`tag_validate_ins` trigger rejects an unknown value at the write — which is the
point of relational storage for an autonomous writer.

`required_when` is advisory: the trigger cannot see a missing tag. It is
checked by `validate()` and it carries the compulsion that produced the seven
mechanisms — a researched problem must name a mechanism, even if the answer is
`unclassified`.
"""

from __future__ import annotations

BOTH = "problem,actor"
PROBLEM = "problem"
ACTOR = "actor"

# ns -> (applies_to, open, required_when, values)
REGISTRY: dict[str, tuple[str, bool, str | None, tuple[str, ...]]] = {
    "kind": (BOTH, False, "always", (
        "need", "leaf", "node", "cross-cutting",
    )),
    "tier": (PROBLEM, False, None, ("1", "2", "3", "4", "5")),
    "need": (PROBLEM, True, None, ()),          # ids come from the graph itself
    "order": (PROBLEM, True, None, ()),         # position within a parent
    "salience": (PROBLEM, True, None, ()),      # rank in the parent's failure list
    "scale": (PROBLEM, True, None, ()),         # 1-10 magnitude judgement
    "sweep": (PROBLEM, False, None, (
        "first-sweep", "standard", "leafed",
    )),
    "channel": (PROBLEM, False, "status == researched", (
        "direct", "structural", "cultural-normative", "ambient-accidental",
    )),
    "satisfier_relation": (PROBLEM, False, "status == researched", (
        "absence", "violator", "pseudo-satisfier", "maldistribution",
        "degraded-quality",
    )),
    "onset": (PROBLEM, False, "status == researched", (
        "acute", "chronic", "latent",
    )),
    "agent": (PROBLEM, False, "status == researched", (
        "nature", "climate", "industrial-accident", "industrial-exposure",
        "industrial-pollution", "daily-life", "warfare", "state-policy",
        "market", "social-norm", "technology-shift", "demographic-shift",
        "deliberate-exclusion",
    )),
    "mechanism": (PROBLEM, False, "status == researched", (
        "aggregation-masks-failure",
        "spend-mismatched-to-source",
        "instrument-keyed-to-wrong-object",
        "authority-mismatched-to-harm",
        "primary-vs-derivative-burden",
        "solution-at-hand-blocked",
        "compensation-substitutes-for-counting",
        "within-tier-loop",
        "second-half-never-built",
        "visible-win-strands-residual",
        "unclassified",
    )),
    "cross_cutting": (PROBLEM, False, None, ("autonomy", "leisure")),
    "node_type": (PROBLEM, False, None, ("instrument", "sector", "exposure-class")),
    "node_status": (PROBLEM, False, None, (
        "open", "fix-known", "fix-partial", "fix-done",
    )),
    "gap_missing_leg": (PROBLEM, False, None, (
        "activism", "institution", "enterprise", "service",
    )),
    "gap_kind": (PROBLEM, False, None, ("none", "coverage", "representation")),
    "ecosystem_role": (ACTOR, False, None, (
        "funder", "intermediary", "capacity-builder", "convener",
        "field-builder", "researcher", "operator", "platform",
    )),
}

# Namespaces whose value set is closed but lives in the graph, not here.
NOTE = {
    "need": "value is a problem id — validated by the migration, not the trigger",
    "gap_kind": "the recorded human finding. problem_coverage derives a floor "
                "(legs with nobody at all) independently; the two are different "
                "questions and routinely disagree",
}


def seed(conn) -> None:
    """Write the registry into tag_ns / tag_def. Idempotent."""
    for ns, (applies_to, is_open, required_when, values) in REGISTRY.items():
        conn.execute(
            "INSERT OR REPLACE INTO tag_ns (ns, applies_to, open, required_when, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (ns, applies_to, int(is_open), required_when, NOTE.get(ns)),
        )
        for value in values:
            conn.execute(
                "INSERT OR REPLACE INTO tag_def (ns, value) VALUES (?, ?)",
                (ns, value),
            )


# The classification tags were derived from tier-1 state-instrument failures and
# the compulsion to pick one is where the seven mechanisms came from. They are
# owed by a documented failure instance, not by the container above it: a need
# or a node has no single onset or agent, and forcing one would produce a
# confident wrong tag that the cross-problem views then group as alike.
CLASSIFIED_KINDS = ("leaf",)


def required(status: str, kind: str | None = None) -> tuple[str, ...]:
    """Namespaces a problem owes at this status and kind."""
    out = []
    for ns, (_, _, required_when, _) in REGISTRY.items():
        if required_when == "always":
            out.append(ns)
        elif (required_when == "status == researched"
              and status == "researched" and kind in CLASSIFIED_KINDS):
            out.append(ns)
    return tuple(out)
