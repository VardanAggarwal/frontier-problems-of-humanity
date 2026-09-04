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
  cross-need-nodes/                 register of policy objects spanning 2+ needs (farm power, construction, ethanol, toxic exposure)
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

## Social-media tracking pass — required for every need file

Every actor named anywhere in the file — by the commercial-landscape pass, the representation-unit gate, or in-text — gets tracked, not just cited. This applies equally to organisations and to named individuals (founders, spokespeople, officials), and regardless of leg (affected-led, commercial, institutional).

For each named actor:
1. **Find their active platform(s).** Twitter/X, LinkedIn, Instagram, YouTube — wherever they actually post, not every platform by default.
2. **Follow/subscribe.** Immediately, during research — not as a follow-up task after the file is written.
3. **Log it.** A follow-list table appended to the file: actor, type (org / individual), leg, platform, handle. No status column yet — this is a list to watch, not a re-verified fact each time.

Not automated yet. Revisit tooling once the list is large enough that manual scrolling stops working.

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

Register: `problems/cross-need-nodes/00-index.md`. A node is worth more than a shortlist row, because one intervention there propagates across needs.

## Frontier-problem criterion

The working filter, arrived at by the user and refined in-session: **solution at hand, plus a blocker that is identifiable and movable.** Not toll. Secondary axes: irreversibility, substrate depth, detection lag, neglect, measurement state.

**The user holds three instruments, not one.** *Superseded 2026-08-24.* The earlier framing was **capital allocation, not policy advocacy** — a single instrument, under which political movability was an irrelevant axis and politically-blocked problems ranked lowest. The user's standing frame elsewhere is the **catalyst model**: a central entity routes a problem to one of three legs — **activism, political institution-building, social enterprise** — and leads none of them. Under three instruments a political blocker is not a disqualifier; it is a routing signal to the activism/institution leg.

This resolves a contradiction that was sitting inside the criterion itself. The primary filter is *solution at hand plus an identifiable, movable blocker*, yet **solution at hand, blocked** ranked lowest on the screen. Both were correct under one instrument. The error was the instrument count, not the criterion.

**Every shortlist entry carries four questions** (was three):

1. **Who owns the object.**
2. **What the smallest sufficient actor is.**
3. **Whether a payer exists** — and if not, whether the beneficiary can be made payable (see `economics-of-change/`).
4. **Whether representation exists at the harm's correct unit.** New, and the hardest gate. From the user's Seed Savers Club conclusion: a protest must be led by the affected, an institution persists only with representation of the governed, an enterprise succeeds only against a problem its builders actually face. The catalyst's contribution compounds only where leadership on the chosen leg is genuinely representative, not nominal.

   **Amended 2026-08-24, and the amendment matters.** The gate first read *whether a locally-rooted leader exists, or is findable*, with "no leader and no route to one means the entry is not actionable." That is too strict, and wrong in the same way the single-instrument criterion was wrong one level up: it treats a routing signal as a disqualifier. **The representation unit has to match the perception unit of the harm** — can the person bearing it perceive it, attribute it, and act against the party causing it?

   - **Local affected** — harm concentrated, perceived by the sufferer, counterparty local and nameable. *Manual scavenging (SKA), silicosis (a mine), cool roofs (a roof), gig fatigue (a platform's local fleet).*
   - **Central organisation** — harm latent, invisible or statistical; attribution is a specialist function the sufferer cannot perform. *Lead (the affected are children and the injury is imperceptible), asbestos (20–40 yr latency), AMR (no individual sufferer), air source-apportionment (the harm unit is an airshed).*
   - **Enterprise** — the sufferer can perceive the harm *and* transact against it, or can be made able to. *Cool roofs, fleet fatigue, data-centre water.*
   - **Central, at a named legitimacy cost** — the sufferer perceives the harm but **benefits from its cause**. *Western Ghats slope zoning, farm power, ethanol feedstock.* This is the one cell where the catalyst model runs against its own founding principle; the cost is carried explicitly, never assumed away.

   Three rules follow. **"No local leader" routes rather than disqualifies** — only *no representation at any unit* fails the gate, which in tier 1 is one row (rental discrimination). **The unit can be wrong in the other direction too**: local representation of an airshed-scale harm is a unit mismatch, not a smaller problem than a missing unit (tier 1's instance is Warrior Moms). And **leg and unit are independent assignments** — asbestos is activism-leg with a central unit, cool roofs is enterprise-leg with a local unit.

   **Latency and local representation are structurally incompatible.** A harm nobody has felt yet cannot have an affected-led claimant, so every row in a latent set routes to a central unit or to enterprise. Expect this in every tier.

   **The organisation of the harmed is a research input, not only a scoring criterion.** In tier 1 it held facts the institutional sources did not surface and that changed two rows' classification — a DMF-funded silicosis corpus, a working $1,100–1,400 cool-roof loan. Go looking for it while researching, not while scoring.

**The mechanisms sort by instrument, not by rank.** Each names which leg can move it:

- **Solution at hand, blocked** — political by construction. Capital cannot move it; **activism → institution** can. Ranked lowest under the single-instrument screen; under three it is live, and it is the only class that satisfies the primary filter by definition.
- **Instrument keyed to the wrong object** — an unserved object exists precisely because the state's instrument was aimed elsewhere. **Enterprise**, directly. Still the strongest signal for capital.
- **Absence of measurement** / **compensation substitutes for counting** — a missing detection layer. **Enterprise** where a buyer exists; **activism** where the missing denominator is itself the contested thing, since an uncounted harm has no claimants.
- **Aggregation masks failure** — someone bears an unrepresented harm. **Enterprise** if they can pay; **institution-building** where the fix is the reporting unit itself, i.e. the harm unit needs an owner.
- **Authority mismatched to harm** — nobody holds it, so nobody blocks entry either. **Institution-building** first: the object needs an owner before either other leg has anything to attach to.
- **Spend mismatched to source** / **primary vs derivative burden** — misdirection with an owner and a budget already in place. **Institution** (redirect the spend) or **enterprise** (serve the real source directly).

**Instrument selection is a step, not an attribute.** The method selects a problem; it must also select the leg and the sequence between legs. Between shortlist and commitment: diagnose the binding constraint, choose the leg, and name the handoff to the next leg where there is one. The default failure is a leg chosen by the actor's preference rather than by the problem's mechanism — an activist chooses activism, a founder chooses enterprise, a bureaucrat chooses a scheme. Being instrument-agnostic at that fork is the catalyst's non-substitutable value, because it is the one judgment no leg-holder can make for themselves.

**The third path, which the tier files kept missing:** the choice is not state-fixes-it or market-fixes-it. The generative position is **making a non-paying beneficiary payable** — insurance, B2B2C, employer or landlord as buyer, offtake against a compliance obligation. This is a business-model frontier rather than a technical or political one, and it is what *instrument keyed to the wrong object* looks like from the other side: the object has no wallet, not no need.

**And tier 1 settles who walks it: organisation precedes payment.** In every tier-1 instance where a non-paying beneficiary became payable, an organisation of the affected built the payment mechanism, and no allocator did — Mahila Housing Trust's credit cooperative financing 20,000+ cool roofs at $1,100–1,400 each, Amul returning ~80% of the consumer rupee to producers by owning the margin, Sulabh at ~15M users/day on ₹1–2, SEWA making 21,000 exposed women the beneficiaries of a priced heat instrument. None is venture-financed, and none of the dense venture-financed categories in the six tier-1 files reaches that population at all. So the third path is not spotted by an allocator and handed to a founder; it is produced by the constituency organising first. **"Cannot pay" in tier 1 has consistently meant "is not organised."** Four existence proofs, all small against the need — treat it as the strongest available hypothesis, not as settled.

Resolved this session, previously open: the observation that seventeen of eighteen tier-1 shortlist entries are implementation rather than knowledge frontiers is **mostly an artifact of the method** — of the institutional-source preference, of a mechanism list containing only institutional failure modes, of a national unit of analysis whose only plausible owner is the state, and of a criterion that selects for political blockers. Partly, though, it is true of the world: tier 1 is the tier where provision genuinely is state-shaped (pipes, sewers, buffer stocks, feeder separation). If that holds, the conclusion for a capital allocator is that **tier 1 is a poor hunting ground and tiers 2–5 are likely better** — a real result, not a failure. Hold both readings.

**Reopened by the three-instrument amendment (2026-08-24).** That resolution was reached under the single-instrument screen, which ranked politically-blocked entries lowest — so the criterion partly manufactured the finding it reported. "Seventeen of eighteen are implementation frontiers" is a verdict about *capital's* reach, not about the problems: an implementation frontier with a political blocker is dead to capital and live to activism → institution. Re-score the tier-1 shortlist under three instruments before treating "tier 1 is a poor hunting ground" as settled. It may survive; it has not been tested against the amended screen.

**Resolved by the tier-1 rewrite (2026-08-24). The verdict is withdrawn.** Re-scored on leg plus representation unit, tier 1's five strongest rows — manual scavenging, silicosis, cool roofs, heat at work, fleet fatigue — are *all* implementation frontiers with movable blockers and existing affected-led organisations. That is the best available configuration under three instruments, not the worst. "Implementation frontier" was a verdict about capital's reach, and the tier is not a poor hunting ground. What survives from the old reading is the method bias itself: the institutional-source preference, a mechanism list containing only institutional failure modes, and a national unit of analysis whose only plausible owner is the state. That bias is real and is what the commercial and representation passes exist to counteract.

**Two findings from the rewrite to carry into every later tier.** First, **the leader gate and the payer gate are anti-correlated in tier 1** — the rows the capital screen demoted (silicosis, manual scavenging, cool roofs) are exactly the rows with decades-old affected-led organisations, while its top pick (data-centre water) has no affected party at all because the harm has not landed. If that holds in tier 2 it is the project's most consequential structural result, because it means the two screens point in opposite directions and neither can be run alone. Second, **won the law, lost the execution** — the dominant activism failure mode, present in four of four tier-1 rows where a movement actually moved the blocker (2013 Act with 714/766 districts self-declaring free; 2019 silicosis policy at 16.6% disbursal; Rajasthan gig Act under industry challenge; MHT at 20,000 homes against tens of millions). It is the leg-2 → leg-3 handoff breaking, and it is the specific judgment no leg-holder can make for themselves.

## Working with the user

- **Pace is slow and incremental by design.** One step per sitting is a complete sitting. Don't rush a tier toward a conclusion — flagged in memory as explicit feedback.
- **Consolidate only when a tier is complete.** The user deferred tier-1 consolidation mid-session precisely to finish the tier first.
- **Pattern that works:** his points → research → report what's missing → his approval → write. He asks "what else am I missing" before instructing additions; answer that question rather than editing.
- **Slate discipline:** `recall` per new topic before composing, full-paragraph verbatim queries, `mark_relevance` after. Save only his own words — never AI summaries.
- **Solution pulls get logged, never chased** (playbook ground rule).
- Answer questions as questions. Don't start editing files until asked for the change.
