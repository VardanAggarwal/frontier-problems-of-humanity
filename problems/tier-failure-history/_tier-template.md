<!--
TIER-FILE TEMPLATE — the canonical copy of the "Tier file structure" invariant in CLAUDE.md.
One file per need: problems/tier-failure-history/tierN-<tier>/NN-<topic>.md

The build parses on the H2/H3 headings below. Use them verbatim, in this order.
An extra or renamed section is a build warning on a first-sweep file and an error once
the file is `status: standard` in needs.yaml.

WHAT THE TIER FILE HOLDS (after the leaf/actor separation, 2026-09-06):
  - the need's `definition` + `description` in the lead area (see below) — NOT in needs.yaml
  - threat history (global)
  - evolution (global), closing with `### Where it worked` — positive controls, all three legs
  - `Where this fails today` — global first, then `### India:` as an ENUMERATED LEAF LIST + a pointer
  - `### India: stored risk` — one line per latent leaf, pointer only

WHAT MOVED OUT TO THE LEAF (problems/tier-failure-history/tierN-x/<need>/<slug>.md, via process-leaf):
  - the "who is working on this" pass (activism / institution / enterprise sub-blocks)
  - representation classification and the `gap:` line
  - magnitude / denominator / stored-risk diagnosis per instance
  - actor records (problems/actors/<slug>.md) and any follow-list
  Do NOT write these into the tier file as prose. If process-leaf hasn't run yet,
  jot raw who-works-it findings as a scratch list under the need and move on.

Delete this comment block when you write a real file.
-->

# <Need> (Tier N — <tier name>)

> <one-line definition — the need in browse-card form>

<description: one paragraph, ~80–120 words — what the need is, what *failing* it
means (harm timescale and mechanism), the scope axes it spans, and anything
treated as out of scope / handed to a cross-cutting axis or node. The loader
reads the blockquote above as `definition` and this prose as `description`; both
render on /need/<id>. Not fields in needs.yaml.>

## How this need has been threatened

Global. How the need has failed across eras. Aim for distinct *mechanisms*, not a
list of disasters — two entries with the same mechanism are one entry. Group with
bold leads (`**Mode name**`), promote to `###` only if the section exceeds ~10 modes.

## How humanity evolved to deal with this threat

Global. What humanity built in response — the institution *and* the incentive
machinery it left running (the previous solution's side effects are usually the
current problem).

### Where it worked

Required. Last subsection of the evolution section. Positive controls with a
measured before/after wherever one exists, searched across all three legs — state
programmes, activism / institution-building, non-state / enterprise — not just the
state. "No positive control found" is an acceptable entry; omitting the section is
not. Under-counting wins makes a neglected problem look intractable.

## Where this fails today

Global before India. Current, dated, sourced.

### India: <descriptor>

India is never its own H2 — always `### India: <descriptor>` nested here, after the
global material.

This section is an **enumerated list — one line per distinct failure**, ordered by
the user's salience judgment. Each line becomes exactly one leaf; its position
becomes the leaf `salience`. Per line:

> **<failure name>** — <one line: who is harmed, at what magnitude, by what arrangement.> `[scale: N]` — `<need>/<slug>.md` (node: <node-id>, if any)

- `scale` = base-10 order of magnitude of the *exposed* (not diagnosed/certified)
  population in the leaf's geography. If even exposure is unquantified, write
  `[scale: ?]` and say so — it sorts last but stays visible.
- Follow the list with a short pointer paragraph: that prose figures are retained
  only until each leaf reaches `researched`, then move into the leaf.
- Add a data-gap paragraph where measurement is absent — name it as a finding.

### India: stored risk, not yet realised

Only if latent material exists (`onset: latent` — harm incurred, not yet in
mortality data). **Pointer list only** — one line per latent leaf, continuing the
numbering from the section above. No magnitude, no diagnosis; that lives in the leaf.

> N. **<failure name>** `[scale: N]` — `<need>/<slug>.md` (node: <node-id>, if any) — <one clause if the absence of measurement is itself the point>
