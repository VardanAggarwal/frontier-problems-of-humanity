---
name: process-tier
description: Research and write one tier of the frontier-problems failure history — per-need files plus the tier summary. Use when starting, continuing, or consolidating a tier in problems/tier-failure-history/ (e.g. "let's do tier 2", "continue safety", "summarise this tier").
---

# Process a tier

Derived from the tier-1 run (six needs, 713 lines, 2026-07). File conventions and research standards live in `CLAUDE.md` and are assumed here — this skill is the *sequence*.

## Before anything

1. Read `problems/tier-taxonomy.md` for the tier's need list, and `problems/tier-failure-history/00-index.md` for the file set.
2. Read the previous tier's `00-summary.md`. The six mechanisms and the latent/active split are inputs to this tier, not things to rediscover.
3. `recall` on Slate with the tier's subject matter, full-paragraph query. The user has prior thinking on most of these and it must be woven in with citation (note title + date), not paraphrased.

## Order of work

**One need per sitting.** Do not batch needs. The tier-1 files that hold up were each written in a single focused pass with the user in the loop.

Per need file:

1. **Threat history** — how the need has failed across eras. Global. Aim for distinct *mechanisms*, not a list of disasters; two entries with the same mechanism are one entry.
2. **Evolution** — what humanity built in response. Include the institution *and* the incentive machinery it left running (playbook step 3: the previous solution's side effects are usually the current problem). Close with a mandatory **`### Where it worked`** subsection: positive controls with a measured before/after. Search for these as deliberately as for failures — tier 1's first draft claimed one and the tier has at least seven (Odisha shelters, leaded petrol, Bihar PDS, Jyotirgram, polio, TB, salt iodisation). Under-counting wins makes a neglected problem look intractable, which is the single most consequential error this process can make.
3. **Where this fails today, global** — current, dated, sourced.
4. **Ask the user for his India points before researching India.** This is the step that made tier 1 work. He supplies numbered points from lived observation; you research them, then report what's *missing* from his list and wait for approval before writing.
5. **India section** — `### India: <descriptor>`. Split anything latent into `### India: stored risk, not yet realised`.
6. **Data gap paragraph** where measurement is absent. Name it as a finding.

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

It is **not a digest**. Structure, as settled in tier 1:

1. **State of the tier in one line** — the single finding all needs produced independently.
2. **The shape of the failure** — 2–4 claims that hold across all files and are *not* visible from the death tolls.
3. **Mechanisms** — table, each found in 3+ files, with the clearest instance. Reuse the seven from tier 1 where they recur; only name a new one if it genuinely doesn't reduce to them.
3b. **Cross-need nodes** — one policy object causing failures in 2+ needs. These are invisible from inside a single file and are the highest-value output of the summary, because one intervention at a node propagates across needs. Tier 1's are farm power (water + sleep) and construction (five needs). Check the register in `CLAUDE.md` for nodes carried from earlier tiers before naming new ones.
4. **The shortlist** — table of problems × solution known / blocker / irreversible / measured / toll. Ordered by the frontier criterion, not by toll. Follow with 2–3 reads of the table.
5. **The latent set** — harms already incurred, not yet visible.
6. **The one thing that worked** — positive controls, own section, however few.
7. **What this tier does not contain** — absences stated as findings, including limits of the method.
8. **Carried forward** — what tier N+1 should start with.

Then link it from `00-index.md` as read-first.

## Guardrails

- **Don't rush to conclusions.** The user's explicit standing feedback. A tier takes as long as it takes.
- **Don't consolidate mid-tier.** If synthesis feels ready before the needs are done, note it and continue.
- **Don't write his hypothesis as fact.** Research first, report, then write.
- **Don't drop a finding because it's negative.** A hypothesis that failed against the data is a result — write the mechanism it revealed instead.
- **Don't let the tier become all-India.** Global material carries the threat history and the evolution; India carries the current failure. Both halves are needed for the mechanisms to generalise.
- The `AskUserQuestion` tool was rejected once in tier 1 when offering synthesis shapes prematurely. Ask in prose, and only about things that change the work.
