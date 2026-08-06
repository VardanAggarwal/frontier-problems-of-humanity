# fph — Frontier Problems of Humanity

Rederiving Maslow's hierarchy from a single drive (persist/propagate), mapping each tier to documented civilizational failures, in order to select one frontier problem to work on personally.

## Repo map

```
notebook.md                        verbatim working journal — who I am, the world I live in, the method
playbook.md                        the domain loop (used on food, 2026-07-11) — 12 steps, notice → conclude
problems/
  tier-taxonomy.md                 the rederivation: one drive, nested containers, tiers by override frequency
  tier-failure-history.md           superseded first pass (single-mechanism collapse) — kept for history only
  tier-failure-history/
    00-index.md                     39-file index across 5 tiers + cross-cutting
    tier1-physiological/
      00-summary.md                 what survived the six files — read before the six
      01-food.md … 06-sleep-circadian.md
    tier2-safety/ … tier5-meaning/
    cross-cutting/                  freedom, leisure, energy — instrumental, not terminal needs
  <domain>.md                       domain overview: tier mapping + status
  <domain>/<sub-problem>.md         full chain: history → mechanism → gap → requirements → experiments
meal-system/                        the food loop, lived (step 9 of the playbook)
economics-of-change/                durable, ongoing (not a one-off write) — the lens for whether a change initiative's economics hold, run alongside problems/ not nested under it
  00-index.md                       purpose + how the folder grows over time
  mechanisms-tried.md                what's been tried 2-3 decades to fund non-paying-beneficiary problems, by mechanism
  lens.md                           the working framework — verification proximity, ownership vs. payment, metric dimensionality
publishing/                         drafts written for an outside reader — essays, not working notes
  surface-efficacy.md               fixed-surface decay: four claimants on finite attention, and the KPI
  frontier-memory-blog.md           moved from ~/job-hunt, 2026-07-29
```

Two distinct processes, don't conflate them:
- **`playbook.md`** — running one *domain* through my own life (food). Notice → live it → talk → publish.
- **`.claude/skills/process-tier/`** — researching one *tier* of the failure history. Invoke `/process-tier` when starting or continuing a tier.

## Tier file structure — invariant

Every `tierN-*/NN-topic.md` file uses exactly these H2s, in this order, with these titles verbatim:

```markdown
# <Need> (Tier N — <tier name>)

Tier definition: <one line>

## How this need has been threatened
## How humanity evolved to deal with this threat
### Where it worked                           ← required, last subsection of the evolution section
## Where this fails today
### India: <descriptor>
### India: stored risk, not yet realised      ← only if latent material exists
```

Rules:
- **India is never its own H2.** It is always `### India: <descriptor>` nested under `Where this fails today`, after the global material. Fixed retroactively in `02-water.md`; don't reintroduce.
- **Global before India** within `Where this fails today`.
- **Latent ≠ active.** Anything whose harm is already incurred but not yet visible in mortality data goes in `### India: stored risk, not yet realised`, not in the active list. Asbestos, lead, silicosis, seismic exposure and fossil-aquifer depletion are the tier-1 instances.
- **`### Where it worked` is mandatory in every file**, closing the evolution section, with a measured before/after wherever one exists. A framework built only from failures cannot distinguish a hard problem from a neglected one. Writing "no positive control found" is an acceptable entry; omitting the section is not. Tier 1 was drafted once with a claim that it contained a single positive control; it contains at least seven, and the error changed a conclusion.
- **Mode granularity is bold-lead** (`**Mode name**` as a group header, or `- **Mode.**` as a bullet lead). Promote to `###` only when a section exceeds ~10 modes (`01-food.md` is the only current case).
- **Cross-need material is cross-referenced, never duplicated.** When a cause appears in more than one need, each file carries its own route and points to the others plus the node entry in the tier summary (see lead across `01`/`03`/`04`).
- One `00-summary.md` per tier, linked from `00-index.md` as read-first.

## Research standards

- **Verify before writing.** Claims get researched, reconciled and only then written into a file. If asked to add something, research it first and report findings — don't write the user's hypothesis into the doc as fact.
- **When sources disagree, write the disagreement.** Don't pick a number silently. Precedents in-file: Delhi 82.2 vs 99.6 µg/m³ (different administrative boundaries in the same IQAir report); asbestos imports as a range with the chrysotile-only vs all-asbestos caveat; sewage treatment 61% official vs ~28% independent, with the gap itself named as the finding.
- **Kill a hypothesis that doesn't survive the data, including the user's.** Mumbai-worsening failed (CSE winter 2024-25: peak daily PM2.5 down 44%) and was folded in by mechanism instead of being written as a trend.
- **Hold competing hypotheses.** Don't collapse to one frame. The small-city question resolved as *both* real inversion and detection artifact.
- **Absence of measurement is a finding, not a gap in the research.** Say so in-file. It recurred in four of six tier-1 files and became the tier's most consistent result.
- **Give the denominator** so a ratio is checkable (`419 towns with stations against ~7,900 census towns`), and flag coincidental figures (`the two counts of 23 are coincidental`).
- Prefer primary/institutional sources: IQAir, CREA, CGWB, CPCB, CSE, NFHS, UDISE+, ICMR, NITI Aayog, HLRN, UNEP, Census. Cite the report and year inline.
- **Know that the institutional-source preference biases the finding.** Institutional data is state-generated, so a harm no agency measures is invisible to this method and a harm an agency does measure arrives pre-framed as that agency's failure. This is why tier 1 drifted into a policy-failure audit. Counteract it deliberately with the commercial-landscape pass below.

## Commercial-landscape pass — required for every need file

A failure is not neglected because the state is failing at it. Establish who is *already commercially working on it* before calling anything a frontier. Every `### India:` section must carry a closing block answering:

1. **Who is commercially active** against each failure mode — named companies, funding, and status (operating / acquired / shut down / distressed). Density of *entry* is not density of *durable business*; distinguish them.
2. **Who the paying customer is.** The central question. Urban consumer, farmer buying inputs, employer, industrial emitter under a compliance mandate, municipality, state tender.
3. **Where capital deployed and failed**, and why — unit economics, distribution cost, margin.
4. **Over-served spaces.** Where commercial density is disproportionate to measured harm. The mismatch is diagnostic, not decorative: it usually means the served population is not the harmed one, and that gap is itself a finding about a missed or mis-specified problem.
5. **Failure modes with no commercial actor**, and whether the reason is that the harmed party cannot pay.

**The organising axis is payer identity, not public vs private.** Working hypothesis, held from the food case and to be tested against every need: *private capital is dense wherever the harmed party is also a paying customer, and absent wherever they aren't.* A second hypothesis to test alongside it: *capital follows the mandate, not the harm* — where a compliance obligation exists (EPR, ZLD, CEMS), regulation manufactures a customer and a market appears regardless of harm size.

Hold the counter-case rather than assuming it away: telecom and UPI both reached apparently non-paying populations profitably, so "cannot pay" often means "has not been priced right." An empty space may be an opportunity, not a void.

## The six mechanisms

Found in three or more tier-1 files each. Check every new failure against these before writing it as novel — see `problems/tier-failure-history/tier1-physiological/00-summary.md` §3.

1. **Aggregation masks failure** — reporting unit larger than harm unit
2. **Spend mismatched to source** — funded, executed, aimed wrong
3. **Instrument keyed to the wrong object** — remedy attaches adjacent to the harm, excluding a class by design
4. **Authority mismatched to harm** — the body with power doesn't contain the source, or *is* it
5. **Primary vs derivative burden** — the visible cause isn't the load-bearing one
6. **Solution at hand, blocked** — technically settled, politically stuck
7. **Compensation substitutes for counting** — the payout layer built without the detection layer, capping liability by leaving the denominator unknown

Secondary: **within-tier loops** (shelter provision degrades thermoregulation) and **the second half never built** (collection without treatment).

If a mechanism recurs unchanged in tier 2, it belongs in `cross-cutting/`, not in a tier file.

## Cross-need nodes

A **node** is one policy object producing failures in two or more needs. Nodes are invisible from inside a single file and only appear once a tier is complete — check for them during the summary, and maintain the register across tiers, not per tier.

- **Farm power tariffs and scheduling** → water (over-extraction) + sleep (night irrigation). One fix: feeder separation, done in Gujarat 2003–06.
- **Construction** → air + water + shelter + sleep + food. No single regulator holds it.
- **Ethanol blending targets** → water (sugarcane irrigation, spent wash) + food (FCI rice and maize routed to fuel). EBP schedule + FCI allocation SOP + MSP. The only node created deliberately and provisioned forward.
- **The toxic-exposure class** (asbestos, lead, silica) — not a node but a class: one mechanism, three carriers, four files. Latency, no registry, controlled elsewhere, installed into poor households as a development product.

A node is worth more than a shortlist row, because one intervention there propagates across needs.

## Frontier-problem criterion

The working filter, arrived at by the user and refined in-session: **solution at hand, plus a blocker that is identifiable and movable.** Not toll. Secondary axes: irreversibility, substrate depth, detection lag, neglect, measurement state.

**The user's prerogative is capital allocation, not policy advocacy.** He is deciding where he would deploy money and effort. A shortlist scored on political movability answers a question he did not ask. Every entry therefore needs: who owns the object, what the smallest sufficient actor is, and whether a payer exists.

**The mechanisms invert into an investability screen**, with the opposite sign to their policy ranking:

- **Solution at hand, blocked** — blocker is political by construction. Capital cannot move it. Ranks *lowest* for this purpose despite ranking highest as a policy finding.
- **Instrument keyed to the wrong object** — an unserved object exists precisely because the state's instrument was aimed elsewhere. A private actor can serve it directly. The strongest signal.
- **Absence of measurement** / **compensation substitutes for counting** — a missing detection layer is a sellable service with an identifiable buyer.
- **Aggregation masks failure** — someone is bearing an unrepresented harm; if they can pay, that is a customer.
- **Authority mismatched to harm** — nobody holds it, so nobody blocks entry either.

**The third path, which the tier files kept missing:** the choice is not state-fixes-it or market-fixes-it. The generative position is **making a non-paying beneficiary payable** — insurance, B2B2C, employer or landlord as buyer, offtake against a compliance obligation. This is a business-model frontier rather than a technical or political one, and it is what *instrument keyed to the wrong object* looks like from the other side: the object has no wallet, not no need.

Resolved this session, previously open: the observation that seventeen of eighteen tier-1 shortlist entries are implementation rather than knowledge frontiers is **mostly an artifact of the method** — of the institutional-source preference, of a mechanism list containing only institutional failure modes, of a national unit of analysis whose only plausible owner is the state, and of a criterion that selects for political blockers. Partly, though, it is true of the world: tier 1 is the tier where provision genuinely is state-shaped (pipes, sewers, buffer stocks, feeder separation). If that holds, the conclusion for a capital allocator is that **tier 1 is a poor hunting ground and tiers 2–5 are likely better** — a real result, not a failure. Hold both readings.

## Working with the user

- **Pace is slow and incremental by design.** One step per sitting is a complete sitting. Don't rush a tier toward a conclusion — flagged in memory as explicit feedback.
- **Consolidate only when a tier is complete.** The user deferred tier-1 consolidation mid-session precisely to finish the tier first.
- **Pattern that works:** his points → research → report what's missing → his approval → write. He asks "what else am I missing" before instructing additions; answer that question rather than editing.
- **Slate discipline:** `recall` per new topic before composing, full-paragraph verbatim queries, `mark_relevance` after. Save only his own words — never AI summaries.
- **Solution pulls get logged, never chased** (playbook ground rule).
- Answer questions as questions. Don't start editing files until asked for the change.
