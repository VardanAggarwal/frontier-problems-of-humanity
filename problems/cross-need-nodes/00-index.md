# Cross-Need Nodes — Register

A **node** is one concrete object — a policy lever, a provision sector, or a hazard class — sitting upstream of leaves in two or more needs, such that acting on that single object moves the whole set. Nodes are invisible from inside one tier file and surface only when a tier is read across — check during the tier summary, maintain this register across tiers.

A node is a grouping *across* leaves, peer to "mechanism": mechanism groups by an abstract *pattern*, a node by a concrete *object*. A node usually exhibits one or more mechanisms. See `../schema.md` → Node record, `../data-model.yaml`, and `CLAUDE.md` → Cross-need nodes.

Membership (which leaves sit under a node) is declared on the leaf (`nodes:` frontmatter) and the node's leaf list is generated — never hand-maintained here.

The node's own `needs:` field is different: it is an **assertion made when the node is written**, from the tier files, before any leaf exists. It is a claim to be checked, not a generated view. Until the portal build exists nothing catches an over-claim — `toxic-exposure-class` carried `sleep` for two weeks with no sleep leaf and no route to one, and was corrected 2026-09-06. When the portal build lands, a `needs:` entry with no member leaf is a warning.

## Types

- **instrument** — one government lever with cross-need side effects. One authority, one edit.
- **sector** — a whole provision system that satisfies some needs and harms others. Many sub-levers, many actors, and **no single edit**: a sector node is not actionable as one lever, so it must enumerate `sub_levers:` in its frontmatter — the list of instrument-shaped things inside it that *are* actionable. A sector without that list is a category label, not a node.
- **exposure-class** — not a policy object: a shared hazard family recurring through one mechanism across leaves. Grouped because one class of remedy covers all carriers.

## Register

| Node | Type | Needs | Status |
|------|------|-------|--------|
| [farm-power-tariff](farm-power-tariff.md) | instrument | water, sleep | fix-partial (Gujarat feeder separation) |
| [ethanol-blending](ethanol-blending.md) | instrument | water, food | open — deliberate policy trade-off |
| [construction](construction.md) | sector | air, water, shelter, sleep, food | open — no single regulator |
| [energy](energy.md) | sector | water, air, shelter, food, sleep | open — reclassified from cross-cutting 2026-09-06 |
| [toxic-exposure-class](toxic-exposure-class.md) | exposure-class | air, water, shelter | open — no exposure/compensation registry |
| [paddy-procurement-complex](paddy-procurement-complex.md) | sector | air, water, food, sleep | open — diversification schemes stalled; only `air` has a member leaf so far |

## Candidates, not yet written

- **education** — sector node. Not a tiered need, fails the cross-cutting test. Upstream of livelihood + epistemic security (t2), intergenerational transmission (t3), skill status (t4), understanding (t5). Needs a research pass before it goes in.
