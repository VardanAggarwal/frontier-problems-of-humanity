"""Track B (`04-worker-build-plan.md` §4, `03-worker.md` §2) — the depth-tier
decision for an actor candidate.

Two tiers, decided at intake, before any spend, per §2's table:

|                | `registry`                  | `tracked`                    |
|----------------|------------------------------|-------------------------------|
| Share          | most candidates              | the minority worth the money |
| Questions      | identity subset (~7)         | the full set                 |
| Queries        | 1 (identity family, always)  | 4-8                           |
| Sources        | 1-2                          | 3-5                           |

Tier is a **prediction** at intake (`predict_tier`) and a **verdict** after
extraction (`verdict_tier`), once `affected_led`, `representation_unit` and
`legs` are known — applying the ground test from `CLAUDE.md` -> Actor
tracking: affected-led/local collectives, field enterprises that deploy or
service the remedy, and local regulators actually acting are `tracked`;
academics, ministers, courts, commissions and national advocacy shops stay
`registry` however influential. A candidate predicted `registry` that
verdicts `tracked` is requeued for a full pass (`needs_requeue`) —
escalation only, one-way: a `tracked` prediction that verdicts `registry` is
just the correct, cheaper-than-guessing-wrong outcome, not a demotion.

Every function here is pure — no DB, no network, no model — per §4's
contract for new modules; `worker.py` calls these at the two points in the
pipeline (candidate mint, claims write) where the two decisions belong.

Scoped to actors only. `problem` candidates carry no depth-tier concept —
`schema.sql` puts the `depth` column only on `actor` — so nothing here takes
a `kind` parameter.
"""
from __future__ import annotations

from . import questions as questions_mod

REGISTRY_TIER = "registry"
TRACKED_TIER = "tracked"

# Intake-time lexical signals — cheap, and allowed to be wrong sometimes by
# design (§2: a `registry` prediction that turns out `tracked` is requeued,
# "cheaper than running everything at full depth to avoid ever being
# wrong"). These are the same ground-test categories as `verdict_tier`,
# read off whatever text the candidate row already carries (name + hint),
# since nothing has been fetched or extracted yet.
_TRACKED_HINTS = (
    "affected-led", "affected led", "grassroots", "community-based",
    "community based", "cooperative", "collective", "self-help group",
    "field enterprise", "local regulator", "survivors' association",
    "survivors association",
)
_REGISTRY_HINTS = (
    "ministry", "government of india", "supreme court", "high court",
    "national commission", "parliamentary committee", "university",
    "professor", "research institute", "think tank", "national advocacy",
)


def predict_tier(candidate: dict) -> str:
    """candidate: whatever the row already carries at intake — `name`,
    `hint` (or `evidence`), `url`, `discovered_via`. -> `registry` or
    `tracked`. Defaults to `registry`: §2's table says most candidates are
    registry, and an unnecessary `tracked` pass costs real money (4-8
    queries, 3-5 sources) that a wrong guess cannot get back."""
    text = " ".join(
        str(candidate.get(k, "") or "")
        for k in ("name", "hint", "evidence", "url", "discovered_via")
    ).lower()
    if any(h in text for h in _TRACKED_HINTS):
        return TRACKED_TIER
    return REGISTRY_TIER


def verdict_tier(*, affected_led: str | None = None,
                 representation_unit: str | None = None,
                 legs=None) -> str:
    """The post-extraction ground test (`CLAUDE.md` -> Actor tracking),
    applied deterministically once the three inputs are known:

      - `affected_led` yes or partial -> tracked (leadership drawn from, or
        mixed with, the harmed population).
      - `representation_unit == "local-affected"` -> tracked (a local
        regulator or body actually acting on the harm, not a national one).
      - `representation_unit == "enterprise"` AND the actor also carries an
        `enterprise` leg -> tracked (a field enterprise that deploys or
        services the remedy, not a market-research consultancy cited once).
      - Otherwise `registry` — academics, ministers, courts, commissions,
        and national advocacy shops read as `central-org` /
        `central-at-named-legitimacy-cost`, which never qualifies here."""
    legs = legs or ()
    if affected_led in ("yes", "partial"):
        return TRACKED_TIER
    if representation_unit == "local-affected":
        return TRACKED_TIER
    if representation_unit == "enterprise" and "enterprise" in legs:
        return TRACKED_TIER
    return REGISTRY_TIER


def needs_requeue(predicted: str, verdict: str) -> bool:
    """True exactly when a `registry`-predicted candidate's post-extraction
    verdict comes back `tracked` (§2: "requeued for a full pass"). One-way:
    a `tracked` prediction that verdicts `registry` is not a requeue in the
    other direction — it's simply the model having enough already, and
    `registry` -> `registry` obviously never requeues either."""
    return predicted == REGISTRY_TIER and verdict == TRACKED_TIER


def questions_for_tier(tier: str):
    """-> the actor question set for one depth tier, in `questions.yaml`
    file order. `registry` is the identity subset (questions marked
    `depth_tier: registry`); `tracked` is the full set — every actor
    question regardless of its own `depth_tier`, because `full` is a
    superset of the identity subset, not a separate, disjoint bucket."""
    if tier not in (REGISTRY_TIER, TRACKED_TIER):
        raise ValueError(
            f"tier must be {REGISTRY_TIER!r} or {TRACKED_TIER!r}, got {tier!r}")
    all_actor = questions_mod.REGISTRY.all("actor")
    if tier == TRACKED_TIER:
        return all_actor
    return tuple(q for q in all_actor if q.depth_tier == REGISTRY_TIER)
