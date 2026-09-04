---
name: process-tier
description: Research and write one tier of the frontier-problems failure history — per-need files plus the tier summary. Use when starting, continuing, or consolidating a tier in problems/tier-failure-history/ (e.g. "let's do tier 2", "continue safety", "summarise this tier").
---

# Process a tier

Derived from the tier-1 run (six needs, 713 lines, 2026-07) and revised after the tier-1 summary was rewritten under the three-instrument frame (2026-08-24). File conventions and research standards live in `CLAUDE.md` and are assumed here — this skill is the *sequence*.

**The most expensive lesson of tier 1: the passes you run last change the ranking, and if they had been run first they would have changed what got researched.** Tier 1's summary was written three times because the commercial pass came after the shortlist and the representation pass after that. Both are now per-need steps below, not summary steps.

## Before anything

1. Read `problems/tier-taxonomy.md` for the tier's need list, and `problems/tier-failure-history/00-index.md` for the file set.
2. Read the previous tier's `00-summary.md`. The seven mechanisms with their instrument assignments, the representation-unit table, the node register and the latent/active split are inputs to this tier, not things to rediscover.
3. `recall` on Slate with the tier's subject matter, full-paragraph query. The user has prior thinking on most of these and it must be woven in with citation (note title + date), not paraphrased.

## Order of work

**One need per sitting.** Do not batch needs. The tier-1 files that hold up were each written in a single focused pass with the user in the loop.

Per need file:

1. **Threat history** — how the need has failed across eras. Global. Aim for distinct *mechanisms*, not a list of disasters; two entries with the same mechanism are one entry.
2. **Evolution** — what humanity built in response. Include the institution *and* the incentive machinery it left running (playbook step 3: the previous solution's side effects are usually the current problem). Close with a mandatory **`### Where it worked`** subsection: positive controls with a measured before/after. Search for these as deliberately as for failures — tier 1's first draft claimed one and the tier has at least seven (Odisha shelters, leaded petrol, Bihar PDS, Jyotirgram, polio, TB, salt iodisation). Under-counting wins makes a neglected problem look intractable, which is the single most consequential error this process can make. **Search all three legs, not just the state.** Tier 1 was drafted twice with only government programmes in this section; the six activism and institution-building wins (MKSS → RTI Act 2005, Right to Food Campaign → *PUCL v UoI* 2001 → mid-day meals, SKA → the 1993 and 2013 Acts, MLPC → Rajasthan Pneumoconiosis Policy 2019, IFAT → Rajasthan Gig Workers Act 2023, APFAMGS as a partial control) and the four non-state wins (Amul, Sulabh, SEWA heat cover, Mahila Housing Trust cool roofs) were invisible both times. A tier whose `Where it worked` section contains only state programmes cannot tell you whether activism or enterprise works on that tier's needs.
3. **Where this fails today, global** — current, dated, sourced.
4. **Ask the user for his India points before researching India.** This is the step that made tier 1 work. He supplies numbered points from lived observation; you research them, then report what's *missing* from his list and wait for approval before writing.
5. **India section** — `### India: <descriptor>`. Split anything latent into `### India: stored risk, not yet realised`.
6. **Data gap paragraph** where measurement is absent. Name it as a finding.
7. **Commercial-landscape pass** — the closing block `CLAUDE.md` requires in every `### India:` section. Run it here, inside the need, not later at the summary.
8. **Representation pass** — new, and it belongs in the *research*, not the scoring. For each failure mode, find whether an organisation of the harmed exists, and at what unit (local affected / central org / enterprise / central-at-a-legitimacy-cost — see gate 4 in `CLAUDE.md`). Then classify the answer into one of five verdicts, because "yes/no" loses the diagnosis:
   - **Present and has moved the blocker once** — then the residual problem is execution, not mobilisation (tier 1: SKA, MLPC, SEWA-MHT, IFAT).
   - **Present at the right unit and unmoved for decades** — representation is eliminated as the explanation, which isolates the blocker (tier 1: BANI + IAVA on asbestos, 22 years, no ban).
   - **Present but at the wrong unit** — local representation of an airshed-scale harm, or vice versa (tier 1: Warrior Moms).
   - **Present and organised against the remedy** — the affected benefit from the cause (tier 1: Western Ghats, farm power, ethanol).
   - **Absent at every unit** — the only verdict that actually fails the gate, and it means constructing a claimant is the first step (tier 1: rental discrimination).

   **Treat these organisations as sources, not only as scores.** MLPC surfaced a DMF-funded silicosis corpus and Mahila Housing Trust a working $1,100–1,400 cool-roof loan; both facts were absent from the institutional sources and both reclassified their row. Search them while researching the need.

9. **Social-media tracking pass** — the closing block `CLAUDE.md` requires for every named actor. Every organisation and individual surfaced by steps 7 and 8 (commercial actors, affected-led orgs, institutional bodies, named leaders/spokespeople) gets followed on their active platform(s) as you find them — not deferred to a later cleanup pass — and logged in a follow-list table at the end of the file: actor, type, leg, platform, handle. No verification-status column yet; this is a watch-list, not a re-scored claim.

## The India step, in detail

This is where the value is, and it has a fixed shape:

- His points arrive as a numbered list. Research each one — figures, sources, whether it holds.
- Then report back in three parts: (a) what the data says about each of his points, including any that don't survive; (b) what's missing that he didn't name; (c) which of the missing ones you rate highest and why.
- He replies "add everything" or selects. Then write.
- **Preserve his own distinctions in the file.** Example: he separated lethal thermal failure (`04`) from sub-lethal sleep disruption (`06`) — that split is load-bearing and appears in both files. His Slate note on public sense became the causal argument in `05` (externalising cleaning onto a caste removes everyone else's incentive not to mess).
- Where his framing is sharper than the sourced literature, use his framing and cite the note.

## Numbers hygiene

Run a dedicated cleanup pass per file before calling it done. The tier-1 pass found six problems in one file: a stale baseline, a duplicated death toll, an unreconcilable ratio, two coincidental figures reading as one, a false trend built from incompatible sources, and an overstated peak. Specifically check:

- Is every figure's year stated, and is it the latest?
- Is any figure repeated in two places with different values?
- Does any ratio lack a denominator?
- Does any series imply a trend its sources can't support?
- Is any threshold being compared against a lenient national standard without saying so (India's PM2.5 NAAQS is 8× WHO)?

## Tier summary

Write `00-summary.md` only when every need file is complete — the user will defer it otherwise, and correctly.

It is **not a digest**. Structure, as settled by the tier-1 rewrite of 2026-08-24 — read that file (`tier1-physiological/00-summary.md`) as the worked example before writing a new one:

1. **State of the tier in one line** — the single finding all needs produced independently.
2. **The shape of the failure** — 3–4 claims that hold across all files and are *not* visible from the death tolls. One of them should be about who bears the harm versus who can claim against it; in tier 1 that claim was *every failure has a bearer, almost none has a claimant*.
3. **Mechanisms** — table, each found in 3+ files, with the clearest instance **and the leg that can move it**. Reuse the seven from tier 1 where they recur; only name a new one if it genuinely doesn't reduce to them. The instrument column is not decoration — it is what makes the mechanism actionable, and in tier 1 it reversed the ranking.
   Keep separate from the table, each with its own subsection and a stated reason for being separate: **the mandate-constitutes-a-market base rate** (how a remedy industry is produced, i.e. the leg-2 → leg-3 handoff), **won the law lost the execution** (how a won remedy fails afterwards — the dominant activism failure mode in tier 1, 4 of 4 rows), and any within-tier class like tier 1's toxic-exposure trio.
4. **Instrument and representation** — the routing section. Every row carries **two independent assignments**: which leg (from the mechanism) and which representation unit (from the harm's perception unit — gate 4 in `CLAUDE.md`). State the legitimacy cost explicitly wherever the unit is central-because-the-affected-benefit-from-the-cause.
5. **The shortlist** — **one** table: problem × blocker × leg × representation unit × payer × irreversible. Ordered by the frontier criterion. Follow with 3–5 reads. Solution-known is usually uniform, so state it in prose rather than as a column.
6. **Cross-need nodes** — one policy object causing failures in 2+ needs. Invisible from inside a single file and the highest-value output of the summary, because one intervention at a node propagates across needs. Distinguish nodes (a policy object someone controls) from **multipliers** (a force no one in the jurisdiction controls — climate) and from **shared conditions with no owner** (overcrowding). Check the register in `CLAUDE.md` for nodes carried from earlier tiers before naming new ones.
7. **The latent set** — harms already incurred, not yet visible. Note that latency and local representation are structurally incompatible, so every latent row routes to a central unit or to enterprise.
8. **What worked** — positive controls, own section, however few, split by leg: state programmes, activism and institution-building, non-state/enterprise. All three sub-tables or the section cannot answer the question it exists to answer.
9. **What this tier does not contain** — absences stated as findings, including limits of the method. Withdraw explicitly any earlier verdict the new passes overturn, and say what produced it.
10. **Carried forward** — what tier N+1 should start with, including which hypotheses were tested and which survived.

Then link it from `00-index.md` as read-first.

## Guardrails

- **Don't rush to conclusions.** The user's explicit standing feedback. A tier takes as long as it takes.
- **Don't consolidate mid-tier.** If synthesis feels ready before the needs are done, note it and continue.
- **Don't write his hypothesis as fact.** Research first, report, then write.
- **Don't drop a finding because it's negative.** A hypothesis that failed against the data is a result — write the mechanism it revealed instead.
- **Don't write two rival shortlists.** Tier 1 ended up with one table ranked on political movability and a second ranked on payer identity, with the second declared to be the real question. That was the single-instrument screen showing through. One table, two assignment columns.
- **Don't score representation as pass/fail.** Five verdicts, per step 8 above. "No local leader" routes an entry to a different unit; it does not kill it. Only *absent at every unit* fails the gate.
- **Don't let the previous tier's conclusions stand unretested.** A verdict reached under an older frame carries the older frame's bias. Tier 1's "poor hunting ground" conclusion had to be withdrawn because the screen that produced it ranked politically-blocked entries lowest.
- **Don't let the tier become all-India.** Global material carries the threat history and the evolution; India carries the current failure. Both halves are needed for the mechanisms to generalise.
- The `AskUserQuestion` tool was rejected once in tier 1 when offering synthesis shapes prematurely. Ask in prose, and only about things that change the work.
