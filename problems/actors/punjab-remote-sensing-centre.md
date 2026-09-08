---
name: Punjab Remote Sensing Centre
slug: punjab-remote-sensing-centre
type: org
depth: tracked
aka: [PRSC]
parent:
superseded_by:
affiliations: []
leg: [institution]
affected_led: no
representation_unit: central-org
stance: works-the-remedy
leaves: [crop-residue-burning]
nodes: []
geography: [india, punjab]
lifecycle: operating
lifecycle_as_of: 2026-09-08
needs:
  - {kind: technology, text: "a fire-detection feed robust to post-satellite-overpass burning — >90% of large Punjab fires are now lit after the polar-orbiting overpass, so the alert layer it runs systematically under-counts", as_of: 2026-09-08, source: "https://theprint.in/environment/farmers-outwitting-satellite-detection-images-show-stubble-burning-peak-post-afternoon-hours/2359525/", state: open}
  - {kind: data, text: "reconciliation protocol for the recurring gap between its fire alerts and nodal-officer ground verification (e.g. 6 of 23 confirmed in Malerkotla)", as_of: 2026-09-08, source: "https://www.tribuneindia.com/news/punjab/only-6-out-of-23-stubble-fires-confirmed-in-punjabs-malerkotla/amp", state: open}
offers:
  - {kind: data, text: "site-level daily farm-fire alerts for Punjab that trigger the SDM → nodal-officer → verification → challan/environmental-compensation pipeline"}
  - {kind: data, text: "state remote-sensing capacity for crop-area and burnt-area mapping"}
sources:
  - {kind: website, url: "https://prsc.gov.in/", handle: "the only checkable channel; update cadence not established", last_checked: 2026-09-09, status: stale}
  - {kind: facebook, url: "https://www.facebook.com/Punjab-Remote-Sensing-Centre-Ludhiana-1549030372045452/", handle: "page exists; no post confirmed within 6 months", last_checked: 2026-09-09, status: stale}
  - {kind: other, url: "", handle: "none-found — no X, no YouTube", last_checked: 2026-09-09, status: none-found}
contact_route: "Punjab Remote Sensing Centre, PAU campus, Ludhiana — under the Punjab Dept of Science, Technology & Environment. No live social feed found — poll prsc.gov.in directly, phone +91-161-2303484. Works in tandem with the Punjab Pollution Control Board (see punjab-pollution-control-board)."
followed: false
followed_date:
last_checked: 2026-09-09
updated: 2026-09-09
---

# Punjab Remote Sensing Centre

**What they do.** Punjab's state remote-sensing agency (Ludhiana). During the paddy season it processes satellite fire data and issues site-level burn alerts to the Punjab Pollution Control Board and the district administration; those alerts drive physical verification by nodal/cluster officers and the resulting challans and environmental-compensation recoveries. Punjab appointed ~10,500 field functionaries for the 2025 season to act on these alerts.

## Scope
- `crop-residue-burning` — the operational monitor whose output *is* the reporting unit of the whole penalty regime in Punjab. Two documented weaknesses: (1) the polar-orbiting series it relies on misses the now-dominant post-3 p.m. burns, so the headline decline is entangled with a shift in burn timing; (2) its alerts frequently disagree with ground verification. This is the `aggregation-masks-failure` / contested-proxy problem named in the leaf's §B measurement-state paragraph.

## Status
- **Funding** — Government of Punjab (Dept of Science, Technology & Environment).
- **Scale metric** — issues the state fire-alert series; ~10,500 field functionaries mobilised off it in 2025.

## What they need
A detection feed robust to after-overpass burning and an alert-vs-ground reconciliation protocol — see typed `needs:`.

## What they can offer
The Punjab daily fire-alert series and state remote-sensing capacity — see typed `offers:`.

## How to reach them
PRSC, Ludhiana, under the Punjab Dept of Science, Technology & Environment. Channel not yet verified.

## Recent updates
- 2026-09-08 — Record created from the `crop-residue-burning` actor-discovery pass (satellite-monitoring institutions). — https://theprint.in/environment/farmers-outwitting-satellite-detection-images-show-stubble-burning-peak-post-afternoon-hours/2359525/
