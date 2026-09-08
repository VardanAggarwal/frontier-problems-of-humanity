---
id: <slug>                 # bare slug, globally unique, authoritative over the path
aliases: []                # append-only; former ids, drive redirects
title:
one_line:
status: stub               # stub | researched   (stale is set by the build, never by hand)
tier:
need:
geography: [india]         # global | india | <state> | <country>
salience:                  # position in the tier file's `### India:` list
channel:                   # direct | structural | cultural-normative | ambient-accidental
satisfier_relation:        # absence | violator | pseudo-satisfier | maldistribution | degraded-quality
onset:                     # acute | chronic | latent
agent:                     # per-tier-family vocabulary — schema.md §A
mechanisms: []             # the seven, or [unclassified] (which obliges a paragraph in C)
nodes: []
cross_cutting: []          # autonomy | leisure
gap:                       # none | coverage | representation
gap_missing_leg: []        # activism | institution | enterprise
gap_note:
gap_as_of:
sources: []
updated: YYYY-MM-DD
actors: []                 # generated from actor records — never hand-maintained
---

<!--
STUB: frontmatter only, and only these keys —
id, title, one_line, status, tier, need, geography, updated.
Delete this comment and every H2 below. A stub renders; it is a real record.

RESEARCHED: all five H2s below are required, verbatim, in this order.
The build parses on them. An extra or renamed H2 fails the build.
-->

# <Title>

## A · Classification
Channel, satisfier relation, onset, agent — one line each, saying why this value and not the neighbouring one.

## B · Evidence
- **Magnitude** — with its denominator, so the ratio is checkable.
- **Differential vulnerability** — who is hit harder and why (physiological / circumstantial / compounding); then why they cannot exit or defend (no information / no resources / no standing / benefits from the cause). The second line drives the representation unit in D.
- **Measurement state** — is the harm counted? Absence of measurement is a finding, written as one.

Source caveats — a "which boundary" note, a source-vs-source disagreement, a "do not average" — go on their own line leading `Data note — …`, in whichever section they bear on. The loader lifts them into a *Data notes* footnote block; they do not sit in the reading line.

## C · Diagnosis
- **Mechanism** — which of the seven, or `unclassified` plus a paragraph naming what the pattern actually is.
- **Primary vs derivative burden** — if the visible cause is not the load-bearing one.
- **Blocker** — what keeps the known fix from happening.

## D · Who is working on this
One sub-block per leg, each naming actor records and what they do *on this leaf*.

**Activism** ·
**Institution** ·
**Enterprise** ·

**Representation present?** — is there an actor at a unit that can perceive and act on this harm?

## E · Gap
One paragraph behind the `gap:` line. Which leg is missing, the specific shape of it, and whether the reason is structural (harmed party cannot pay / harm latent or diffuse / no administrative unit maps the harm).

## Sources
- 
