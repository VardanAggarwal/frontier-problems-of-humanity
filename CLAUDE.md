# fph — Frontier Problems of Humanity

Rederiving Maslow's hierarchy from a single drive (persist/propagate), mapping each tier to documented civilizational failures, in order to build a public platform that catalogues every actor working on each failure — what they need, what they can offer, how to reach them — and to act as catalyst connecting them across the activism / institution-building / enterprise legs. The earlier goal, *select one frontier problem to work on personally*, is superseded (2026-09-06): the catalyst role is the frontier, not the problem pick. See `catalyst-platform/00-plan.md`.

## Repo map

```
notebook.md                        verbatim working journal — who I am, the world I live in, the method
playbook.md                        the domain loop (used on food, 2026-07-11) — 12 steps, notice → conclude
problems/
  tier-taxonomy.md                 the rederivation: one drive, nested containers, tiers by override frequency
  schema.md                        prose explainer for the six record types (need, leaf, cross-cutting leaf, node, actor, connection) and how they wire
  lenses.yaml                      the mechanism + cross-cutting-axis registries — id/title/one_line, for /lens/* pages
  data-model.yaml                  formal schema — fields, types, enums, relations; source of truth for record shape; validated and loaded into problems/index.db (committed)
  actors/<slug>.md                 one file per org or named individual, spanning needs — depth, status, typed needs/offers, sources, updates, contact
  actors/_template.md              the v2 actor frontmatter template
  private/                         GITIGNORED — catalyst notes, connection records, contact state; not backed up by git
  tier-failure-history.md           superseded first pass (single-mechanism collapse) — kept for history only
  tier-failure-history/
    _tier-template.md               tier-file skeleton + per-section guidance (headings are a build invariant); canonical copy of "Tier file structure" below
    _leaf-template.md               leaf frontmatter + the A-E section template (headings are a build invariant)
    needs.yaml                      the need registry — 36 rows, levels 1-2 of the browse tree; source of truth for need ids and per-file status
    00-index.md                     human-readable view of needs.yaml + leaves, 5 tiers + cross-cutting; marks first-sweep vs standard files
    tier1-physiological/
      00-summary.md                 what survived the six files — read before the six
      01-food.md … 06-sleep-circadian.md
      <need>/<slug>.md              leaf: one documented failure instance — classification, evidence, diagnosis, who works it, gap
    tier2-safety/ … tier5-meaning/
    cross-cutting/                  axes that can't be lost alone — freedom, leisure (energy moved to a node 2026-09-06); 00-index.md + one essay per axis
  cross-need-nodes/                 register of concrete objects upstream of 2+ needs, typed instrument / sector / exposure-class (farm-power, ethanol, construction, energy, toxic-exposure)
  <domain>.md                       domain overview: tier mapping + status
  <domain>/<sub-problem>.md         full chain: history → mechanism → gap → requirements → experiments
src/                                the portal — Astro pages + the corpus loader (lib/schema.mjs, lib/sections.mjs, lib/corpus.mjs)
scripts/build-index.mjs             emits problems/index.db + problems/index.json; `npm run validate` for the loader alone
catalyst-platform/
  00-plan.md                       the platform: list problems, research each, list everyone working it; catalyst division of labour; sequence
  01-scoreboard.md                 the counters that make catalyst work visible — connections, actors reachable, leaves, stale
  02-connect-pass.md               the pair-scoped procedure: asks + offers -> a connection record -> two drafted messages
  03-portal.md                     the public web layer — build pipeline, section invariant, route map, publish boundary; §7 records what shipped 2026-09-06 and the six departures from the design
meal-system/                        the food loop, lived (step 9 of the playbook)
economics-of-change/                durable, ongoing (not a one-off write) — the lens for whether a change initiative's economics hold, run alongside problems/ not nested under it
  00-index.md                       purpose + how the folder grows over time
  mechanisms-tried.md                what's been tried 2-3 decades to fund non-paying-beneficiary problems, by mechanism
  lens.md                           the working framework — verification proximity, ownership vs. payment, metric dimensionality
publishing/                         drafts written for an outside reader — essays, not working notes
  surface-efficacy.md               fixed-surface decay: four claimants on finite attention, and the KPI
  frontier-memory-blog.md           moved from ~/job-hunt, 2026-07-29
```

## Running the portal

```
npm run validate    # load + validate the whole corpus, emit nothing. Run this after editing any record.
npm run build       # emit problems/index.db + index.json, then build the static site into dist/
npm run dev         # local server with reload
```

`npm run validate` is the fast check. Errors fail the build; warnings are the punch list (README → *What to test*). A leaf that breaks the A–E section invariant is an error; a node or actor body that does is a warning, because those five node files predate the invariant.

Two distinct processes, don't conflate them:
- **`playbook.md`** — running one *domain* through my own life (food). Notice → live it → talk → publish.
- **`.claude/skills/process-tier/`** — researching one *tier* of the failure history. Invoke `/process-tier` when starting or continuing a tier.

Both feed **`catalyst-platform/00-plan.md`** — the platform: a browse tree of problems, a leaf per failure instance, an actor record per person/org, the catalyst's connection work on top. Leaves are processed by `process-leaf` (`.claude/skills/process-leaf/`, sibling of `process-tier`).

## Tier file structure — invariant

Canonical copy with per-section guidance: `problems/tier-failure-history/_tier-template.md` (sibling of `_leaf-template.md`). The rules below are the spec; the template is the skeleton to copy. Keep the two in sync when either changes.

Every `tierN-*/NN-topic.md` file uses exactly these H2s, in this order, with these titles verbatim:

```markdown
# <Need> (Tier N — <tier name>)

> <one-line definition — browse-card form>          ← parsed as the need's `definition`

<description: one paragraph — what the need is, what failing it means,
the scope axes, what is out of scope>              ← parsed as the need's `description`

## How this need has been threatened
## How humanity evolved to deal with this threat
### Where it worked                           ← required, last subsection of the evolution section
## Where this fails today
### India: <descriptor>
### India: stored risk, not yet realised      ← only if latent material exists
```

Rules:
- **The lead area carries the need's own `definition` + `description`.** Not `needs.yaml` — that file is id/tier/order/title/file/status only. `corpus.mjs` reads the leading `>` blockquote as `definition` and the prose between it and the first `##` as `description`; both render on `/need/<id>`. A missing blockquote falls back to the title and warns. The old bare `Tier definition: <line>` form is superseded; where one remains as the first line of the description prose the loader strips the label.
- **India is never its own H2.** It is always `### India: <descriptor>` nested under `Where this fails today`, after the global material. Fixed retroactively in `02-water.md`; don't reintroduce.
- **Global before India** within `Where this fails today`.
- **Latent ≠ active.** Anything whose harm is already incurred but not yet visible in mortality data is `onset: latent` on its leaf. The tier file's `### India: stored risk, not yet realised` H2 stays, but as a **pointer list** — one line per latent leaf, no magnitude or diagnosis. Asbestos, lead, silicosis, seismic exposure and fossil-aquifer depletion are the tier-1 instances.
- **`### Where it worked` is mandatory in every file**, closing the evolution section, with a measured before/after wherever one exists. A framework built only from failures cannot distinguish a hard problem from a neglected one. Writing "no positive control found" is an acceptable entry; omitting the section is not. Tier 1 was drafted once with a claim that it contained a single positive control; it contains at least seven, and the error changed a conclusion.
- **Mode granularity is bold-lead** (`**Mode name**` as a group header, or `- **Mode.**` as a bullet lead). Promote to `###` only when a section exceeds ~10 modes (`01-food.md` is the only current case).
- **Cross-need material is cross-referenced, never duplicated.** When a cause appears in more than one need, each file carries its own route and points to the others plus the node entry in the tier summary (see lead across `01`/`03`/`04`).
- One `00-summary.md` per tier, linked from `00-index.md` as read-first.
- **Per-instance analytic content now lives in leaves.** The `### India: who is commercially working…` block, magnitude/denominator figures, and stored-risk diagnosis move to `tierN-x/<need>/<slug>.md`. The tier file keeps threat history, evolution, `### Where it worked`, the `### India:` failure list, and a pointer to its leaves. Producing the leaves is `process-leaf`'s job, not `process-tier`'s. (Retrofit is per-file, one sitting each — air first.)

## Research standards

- **Verify before writing.** Claims get researched, reconciled and only then written into a file. If asked to add something, research it first and report findings — don't write the user's hypothesis into the doc as fact.
- **When sources disagree, write the disagreement.** Don't pick a number silently. Precedents in-file: Delhi 82.2 vs 99.6 µg/m³ (different administrative boundaries in the same IQAir report); asbestos imports as a range with the chrysotile-only vs all-asbestos caveat; sewage treatment 61% official vs ~28% independent, with the gap itself named as the finding.
  - **Keep the reconciliation out of the reading line.** A source-vs-source caveat, a "which boundary" note, a "do not average" instruction — write it as a standalone line in the leaf section leading `Data note — …` (or `Data caution — …`). The loader lifts those lines out of the prose and renders them as a numbered *Data notes* block at the foot of the research disclosure. Substantive methodology that belongs in the argument (a lenient national threshold, a failed hypothesis) stays inline.
- **Kill a hypothesis that doesn't survive the data, including the user's.** Mumbai-worsening failed (CSE winter 2024-25: peak daily PM2.5 down 44%) and was folded in by mechanism instead of being written as a trend.
- **Hold competing hypotheses.** Don't collapse to one frame. The small-city question resolved as *both* real inversion and detection artifact.
- **Absence of measurement is a finding, not a gap in the research.** Say so in-file. It recurred in four of six tier-1 files and became the tier's most consistent result.
- **Give the denominator** so a ratio is checkable (`419 towns with stations against ~7,900 census towns`), and flag coincidental figures (`the two counts of 23 are coincidental`).
- Prefer primary/institutional sources: IQAir, CREA, CGWB, CPCB, CSE, NFHS, UDISE+, ICMR, NITI Aayog, HLRN, UNEP, Census. Cite the report and year inline.
- **Know that the institutional-source preference biases the finding.** Institutional data is state-generated, so a harm no agency measures is invisible to this method and a harm an agency does measure arrives pre-framed as that agency's failure. This is why tier 1 drifted into a policy-failure audit. Counteract it deliberately with the "who is working on this" pass below.

## Who is working on this — required for every leaf

Run by `process-leaf`, once per failure instance — **not at tier time**. The tier file's only leg-symmetric obligation is `### Where it worked` (positive controls). Everything below produces leaf body §D and the `gap:` line.

A failure is not neglected because the state is failing at it, and not solved because a company sells something adjacent. Before characterising any failure, establish who is *already* working it, across all three legs. One pass, three sub-blocks, same five questions:

1. **Who is active** — named actors, formation, funding source, status. → produces / updates an actor record (`problems/actors/<slug>.md`).
2. **What makes the actor viable** — the leg-specific core:
   - *Commercial:* who the paying customer is.
   - *Activism:* whether leadership represents the harmed (affected-led vs proxy / NGO-staffed).
   - *Institution:* whether the body's authority contains the source, and its reporting unit is the harm unit.
3. **Where effort deployed and failed, and why** —
   - *Commercial:* unit economics, distribution cost, margin — the capital graveyard.
   - *Activism:* won the law, lost the execution; blocker moved once vs institutionalised; movement organised *against* the remedy.
   - *Institution:* spend mismatched to source; the second half never built; disbursal rate.
4. **Over-served / over-represented / over-institutionalised** — density disproportionate to measured harm. Diagnostic: usually means the served population is not the harmed one.
5. **Failure modes with no actor of that leg** — and whether the reason is structural: harmed party cannot pay (commercial); harm latent / diffuse / the harmed benefit from the cause (activism); no administrative unit maps the harm (institution).

`affected-led` is a tag on the actor, not a leg — leg and unit are independent assignments.

## Actor tracking — runs with the pass above

Every actor named anywhere gets an actor record, not just a citation — organisations and named individuals (founders, spokespeople, officials) alike, every leg.

**`depth: tracked` follows the ground test, not influence.** `tracked` (monitored, channel-searched, connection-eligible) is for actors *operating where the harm is* — affected-led/local collectives, field enterprises that deploy or service the remedy, local regulators actually acting on the failure. Evidence-base authors, academics, ministers, courts, commissions and national advocacy/publishing NGOs stay `registry` however influential — cited, not monitored. Don't run `actor-channel-finder` for a `registry` actor. Full criteria: `process-leaf` → *Actor records — the §D sub-procedure*.

1. **Find their active platform(s)** — wherever they actually post.
2. **Follow/subscribe immediately**, during research.
3. **Create/update `problems/actors/<slug>.md`** per `schema.md` — identity, status, needs, offers, recent updates, contact, private catalyst notes. The old per-file follow-list table is now a generated view ("actors touching this leaf").
4. **Harvest the actors that researching one actor surfaces.** Every actor pass turns up others — co-petitioners, co-authors, coalition partners, named officials, the affected-led leader an NGO speaks *for*. Don't make a record for each; list the unresearched names on the leaf (§D, "coverage not yet mapped" — this also backs `gap: coverage`), then run the pass again on those worth it now. A lead becomes a record only when a wave researches it; stop when a wave yields no new names. In the silicosis sweep this is the *only* way the affected-led leader was found. `process-leaf` (§D sub-procedure) has the fan-out mechanics.

Not automated yet. Revisit tooling once the registry is large enough that manual scrolling stops working.

## The mechanisms

Seven, found in three or more tier-1 files each. Check every new failure against these before writing it as novel — see `problems/tier-failure-history/tier1-physiological/00-summary.md` §3.

1. **Aggregation masks failure** — reporting unit larger than harm unit
2. **Spend mismatched to source** — funded, executed, aimed wrong
3. **Instrument keyed to the wrong object** — remedy attaches adjacent to the harm, excluding a class by design
4. **Authority mismatched to harm** — the body with power doesn't contain the source, or *is* it
5. **Primary vs derivative burden** — the visible cause isn't the load-bearing one
6. **Solution at hand, blocked** — technically settled, politically stuck
7. **Compensation substitutes for counting** — the payout layer built without the detection layer, capping liability by leaving the denominator unknown

Secondary: **within-tier loops** (shelter provision degrades thermoregulation) and **the second half never built** (collection without treatment).

Provisional (below the "3+ tier-1 files" bar, 2 instances so far — `residual-childhood-lead`, `crop-residue-burning`): **visible win strands the residual** — a decisive win against the largest, most salient contributor drains the political attention that would have funded the diffuse remainder, which is then left to no one because the headline problem was declared solved. Promoted from an `unclassified` §C paragraph, 2026-09-07.

A mechanism that recurs unchanged across tiers is documented once, here — not re-derived in each tier file. Tag leaves with it (`mechanisms:` frontmatter); don't restate it.

**`unclassified` is a legitimate eighth value, and using it is not a failure.** All seven were derived from tier-1 *state-instrument* failures. Tiers 3–5 fail through status hierarchies, kinship arrangements and belief systems, where no instrument is keyed to anything; forcing that material into these seven produces a confident wrong tag and the cross-leaf mechanism view then groups unlike things as alike. A leaf tagged `unclassified` owes a paragraph in §C saying what the pattern actually is — that paragraph is where the eighth mechanism comes from.

## Cross-need nodes

A **node** is one concrete object — a policy lever, a provision sector, or a hazard class — upstream of leaves in two or more needs, such that acting on that single object moves the whole set. Invisible from inside one tier file; surfaces only reading a tier across — check during the summary, maintain the register across tiers.

A node is a grouping *across* leaves, peer to a mechanism: mechanism groups by an abstract *pattern* ("compensation substitutes for counting"), a node by a concrete *object* ("the ethanol blending schedule"). A node usually exhibits one or more mechanisms. It is not above or below leaves — it's a lens across them, and the only such lens that is a first-class record with its own actor links (people work the lever without working any one downstream leaf).

**Three types:** `instrument` (one government lever, one authority, one edit — farm-power tariff, ethanol blending) · `sector` (a whole provision system, many sub-levers — construction, energy) · `exposure-class` (not a policy object; a hazard family recurring via one mechanism — asbestos/lead/silica).

Register: `problems/cross-need-nodes/00-index.md`. Node membership is declared on the leaf (`nodes:` frontmatter); the node's leaf list is generated. A node is worth more than a shortlist row because one intervention there propagates across needs.

## Catalyst method

No problem is screened out. Every documented failure gets a leaf and stays on the platform. The method's job per leaf: **catalogue who is working on it, and flag what's missing.**

**Gap line** — every leaf carries one:
- `gap: none` — actors present across the legs the problem needs.
- `gap: coverage` — someone works it; the platform hasn't found them yet. Viewers can submit names.
- `gap: representation` — no actor exists at a unit that can perceive and act on the harm. Nobody to submit; filling it is fieldwork. Future state.

Keep the two distinguishable: an empty representation slot is a finding, not a stub awaiting a submit button.

**Record status** — every leaf carries `status: stub | researched` (`stale` is set by the build script). A **stub** is id + title + one_line + need, and it is a real record: it appears in the browse tree, can be linked and can receive an actor submission. Goal 1 (a browsable list of every problem) ships on stubs; goal 2 (research per problem) upgrades them one per sitting. Depth-first is the wrong build order against 36 needs.

**Scope: India-anchored, global-where-the-mechanism-is.** Not a stated decision until now, and it was silently assumed everywhere. Rule: threat history and evolution are global; the failure record is India, and `geography:` on every leaf makes the claim explicit rather than implied. A global failure gets its own leaf only when the mechanism differs from the Indian one — otherwise it is evidence inside the India leaf.

**Refreshing and retiring** — `process-leaf` → *Refreshing, correcting and retiring a record*. Records go stale (`gap_as_of` older than a linked actor's `lifecycle_as_of`), and a **solved leaf is never deleted**: it re-runs `gap:`, gains a dated note on what moved and who moved it, and becomes a positive control with a named owner — the scarcest thing in the repo.

**Connection opportunities** — where a leaf has actors on some legs but not others, or a rule was won but nobody delivers it, name the two actors who should be talking. Logged in `problems/private/`, not the public leaf. Logging is done at leaf time; **acting on them is a separate pass with its own unit — the actor pair, not the problem** — `catalyst-platform/02-connect-pass.md`. Both skills are problem-scoped, so without that pass the catalyst work has no procedure and never happens. Counted on `catalyst-platform/01-scoreboard.md`.

## Working with the user

- **Pace is slow and incremental by design.** One step per sitting is a complete sitting. Don't rush a tier toward a conclusion — flagged in memory as explicit feedback.
- **Consolidate only when a tier is complete.** The user deferred tier-1 consolidation mid-session precisely to finish the tier first.
- **Pattern that works:** his points → research → report what's missing → his approval → write. He asks "what else am I missing" before instructing additions; answer that question rather than editing.
- **Slate discipline:** `recall` per new topic before composing, full-paragraph verbatim queries, `mark_relevance` after. Save only his own words — never AI summaries.
- **Solution pulls get logged, never chased** (playbook ground rule).
- Answer questions as questions. Don't start editing files until asked for the change.
