---
name:
slug:
type: org                  # org | individual
depth: registry            # registry (cited in a leaf; identity+scope only) | tracked (catalyst target)
aka: []
parent:
superseded_by:
affiliations: []           # individuals: [{actor: <slug>, role: , from: , to: }]
leg: []                    # activism | institution | enterprise
affected_led: no           # yes | no | partial
representation_unit:       # local-affected | central-org | enterprise | central-at-named-legitimacy-cost
stance: works-the-remedy   # works-the-remedy | neutral | organised-against-remedy | ambiguous
leaves: []   # bare slug = supporting; {id: <leaf>, role: primary} to mark load-bearing
nodes: []
geography: []
lifecycle: operating
lifecycle_as_of: YYYY-MM-DD
needs: []                  # tracked only: [{kind: , text: , as_of: , source: , state: open}]
offers: []                 # tracked only: [{kind: , text: }]
sources: []                # [{kind: , url: , handle: , last_checked: , status: live}]
                           # NO reachable channel → one row with status: none-found. Never an empty list.
contact_route:             # tracked only
followed: false
followed_date:
last_checked:
updated: YYYY-MM-DD
---

# <Name>

**What they do.** One paragraph.

## Scope
- `<leaf-id>` — what they do on this leaf, one line.

## Status
- **Funding** — source, scale, latest round/grant/budget, date.
- **Scale metric** — the one checkable number (members / homes financed / users-day / revenue), dated.

## What they need
Prose only where the typed `needs:` rows need context. The rows are the source of truth.

## What they can offer
Same — prose supplements the typed `offers:` rows.

## How to reach them
Route, and the warm-intro path if known.

## Recent updates
<!-- reverse-chron, fixed format, appended by the monitoring agent -->
- YYYY-MM-DD — one line — url

<!-- Catalyst notes live in problems/private/actors/<slug>.md — NOT here. -->
