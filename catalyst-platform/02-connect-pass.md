# The connect pass

**Unit of work: the actor pair.** Not the problem.

This is the procedure the method was missing. `process-tier` researches a need. `process-leaf` researches a failure. Both are problem-scoped, so both stop at the leaf — and the introduction, which `00-plan.md` names as the whole point of the catalyst role, had no procedure whose unit could ever reach it. `process-leaf`'s "connection opportunities are logged, never chased" is a guardrail against chasing an introduction *mid-leaf*, when actor research is half-done. It was never a prohibition on making them. This file is where they get chased.

**Input:** the actor registry (`problems/actors/`), not a leaf.
**Output:** `problems/private/connections/<slug>.md`, one per pair.
**Cadence:** one pass per sitting, whenever the registry has grown — not tied to any tier or leaf.

---

## Before anything

1. Read `catalyst-platform/01-scoreboard.md`. Counters 1, 2 and 7 say whether this pass is overdue.
2. Read `catalyst-platform/00-plan.md` → *Division of labour*. Steps 3 and 5 below are non-delegable: judging whose ask is real, and every word that actually goes to a person.

## The pass

**1 · Load the asks.** Every `actor.needs[]` row with `state: open`, across all actors. Sort by `as_of` — an ask from 2024 is a question ("is this still live?"), not an input.

**2 · Load the offers.** Every `actor.offers[]` row. Match on `kind` first (an actor needing `legal` against actors offering `legal`), then read for whether the match is real.

**3 · Filter to real asks.** *Non-delegable.* An ask is real if the actor would act on it being met — not if it is a line in a funding deck. Inferred asks (marked as inferred in `text`) need one piece of corroboration before they enter a connection. Kill the rest; a killed ask gets `state: withdrawn` with a dated note, not deletion.

**4 · Write the connection record.** For each surviving pair, from `problems/private/_connection-template.md`. The test is `gap_filled`: **if you cannot write in one line which gap or broken handoff the introduction fills, it is not a connection yet** — it is two organisations that sound compatible. Leave it at `state: hypothesis` and move on.

State starts at `hypothesis`. It becomes `proposed` only when a message has actually gone out.

**5 · Draft the two messages.** One per side, each saying what *that* side gets. Agent-drafted, per `00-plan.md`; **sent only by the user.** Nothing goes out of this repo without him reading it.

**6 · Record the outcome, especially when it fails.** `declined` and `dead` keep their records. A dead connection is the negative result — the only way to learn which kinds of introduction don't work, and the only defence against repeating one.

**7 · Update the scoreboard.**

---

## Where connections come from, besides asks

Three sources, in descending yield:

- **A leaf with a leg gap.** `gap_missing_leg: [enterprise]` on a leaf with two activism actors is a stated shape for the missing third party. Query leaves by `gap_missing_leg`, not by reading them.
- **Won the law, lost the execution.** The dominant activism failure mode in tier 1 (4 of 4 rows). The rule exists; nobody delivers it. The introduction pairs whoever won the rule with whoever could deliver against it.
- **A node, not a leaf.** Actors working the same lever from different legs — `node.actors_on_node` — without knowing about each other. Node-level introductions are the highest-leverage the platform can make, because one intervention there propagates across needs. Check the node register before the leaves.

## Guardrails

- **Never introduce without both sides' consent.** Ask each separately; a forwarded email is not consent.
- **An actor with `stance: organised-against-remedy` is a finding, not a connection candidate.** Do not broker it.
- **`depth: registry` actors are not connection candidates.** Promote to `tracked` — which means writing `needs`, `offers` and `contact_route` first — or leave them out.
- **Don't manufacture a pair to move counter 1.** A connection with a weak `gap_filled` burns the relationship that the non-delegable half of this project runs on.
- **Volume is not the goal.** One introduction that becomes `engaged` is worth twenty at `hypothesis`.
