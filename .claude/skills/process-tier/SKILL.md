---
name: process-tier
description: Research and write one tier of the frontier-problems failure history — per-need files plus the tier summary. Use when starting, continuing, or consolidating a tier in problems/tier-failure-history/ (e.g. "let's do tier 2", "continue safety", "summarise this tier").
---

# Process a tier

Derived from the tier-1 run (six needs, 713 lines, 2026-07), revised after the tier-1 summary rewrite (2026-08-24) and again after the catalyst reframe (2026-09-06). File conventions and research standards live in `CLAUDE.md` and are assumed here — this skill is the *sequence*.

**The most expensive lesson of tier 1: actor discovery run late changes what you conclude, and if run first would have changed what got researched.** Tier 1's summary was written three times chasing this. Actor discovery now happens at leaf time (`process-leaf`), but the *win* half of it — all-three-legs positive controls — must still be done here, while you're in the sources, or `### Where it worked` comes out state-only (it did, twice).

## Changed by the catalyst reframe (2026-09-06)

The project no longer selects a frontier problem. Everything that fed a ranking is gone, and the per-instance actor work has moved to a separate skill.

- **`process-leaf` owns the per-failure work** (`problems/tier-failure-history/tierN-<tier>/<need>/<slug>.md`, frontmatter per `data-model.yaml`): the "who is working on this" pass, the representation classification, actor records, magnitude/denominator, the `gap:` line. `process-tier` no longer does any of this. Steps 7–9 below are kept only to say *where the handoff is*. Skill not built yet — until it is, jot the raw findings under the need as a scratch list and move on; do not write them into the tier file as prose.
- **The tier file keeps** threat history, evolution, `### Where it worked` (all three legs — the only leg-symmetric obligation left in this skill), the `### India:` failure list, `### India: stored risk` as a one-line-per-leaf pointer list, and a link to its leaves.
- **Copy the skeleton from `problems/tier-failure-history/_tier-template.md`** — it carries the verbatim headings, the post-separation "holds / moved out" split, and per-section guidance. `CLAUDE.md` → *Tier file structure — invariant* is the spec; the template is what you paste.
- **The summary drops the shortlist and the frontier-criterion ordering** (step 5 below). It keeps: state-of-tier line, shape-of-failure claims, mechanism table, cross-need nodes, latent set, positive controls split by leg, carried-forward.
- **Nodes** are typed `instrument / sector / exposure-class` — `CLAUDE.md` → Cross-need nodes; register at `problems/cross-need-nodes/00-index.md`.

The research discipline below — one need per sitting, the India step, all-three-legs positive controls, numbers hygiene — is unchanged.

## Before anything

1. Read `problems/tier-failure-history/needs.yaml` — the need registry, and the source of truth for the tier's need list, ids, order and per-file `status`. (The `definition` one-liner and `description` paragraph are **not** here — they live in each tier file's lead area; see per-need step 4.) `problems/tier-taxonomy.md` carries the *derivation*; `needs.yaml` carries the *list*. `00-index.md` is the human-readable view of the same set. A need this tier researches must have a row there before you write its file; if you add or split a need, edit `needs.yaml` in the same sitting.
2. Read the previous tier's `00-summary.md`. The seven mechanisms, the node register and the latent/active split are inputs to this tier, not things to rediscover.
3. `recall` on Slate with the tier's subject matter, full-paragraph query. The user has prior thinking on most of these and it must be woven in with citation (note title + date), not paraphrased.

## Order of work

**One need per sitting.** Do not batch needs. The tier-1 files that hold up were each written in a single focused pass with the user in the loop.

Per need file:

1. **Threat history** — how the need has failed across eras. Global. Aim for distinct *mechanisms*, not a list of disasters; two entries with the same mechanism are one entry.
2. **Evolution** — what humanity built in response. Include the institution *and* the incentive machinery it left running (playbook step 3: the previous solution's side effects are usually the current problem). Close with a mandatory **`### Where it worked`** subsection: positive controls with a measured before/after. Search for these as deliberately as for failures — tier 1's first draft claimed one and the tier has at least seven (Odisha shelters, leaded petrol, Bihar PDS, Jyotirgram, polio, TB, salt iodisation). Under-counting wins makes a neglected problem look intractable, which is the single most consequential error this process can make. **Search all three legs, not just the state.** Tier 1 was drafted twice with only government programmes in this section; the six activism and institution-building wins (MKSS → RTI Act 2005, Right to Food Campaign → *PUCL v UoI* 2001 → mid-day meals, SKA → the 1993 and 2013 Acts, MLPC → Rajasthan Pneumoconiosis Policy 2019, IFAT → Rajasthan Gig Workers Act 2023, APFAMGS as a partial control) and the four non-state wins (Amul, Sulabh, SEWA heat cover, Mahila Housing Trust cool roofs) were invisible both times. A tier whose `Where it worked` section contains only state programmes cannot tell you whether activism or enterprise works on that tier's needs.
3. **Where this fails today, global** — current, dated, sourced.
4. **Write the need's `definition` and `description` in the tier file's lead area** — the block between `# Title (Tier N — …)` and the first `##`:

   ```markdown
   # <Need> (Tier N — <tier name>)

   > <one-line definition — browse-card form, the old needs.yaml `definition`>

   <description: one paragraph, ~80–120 words — what the need is, what *failing* it
   means (harm timescale and mechanism), the scope axes it spans, and anything
   treated as out of scope / handed to a cross-cutting axis or node.>

   ## How this need has been threatened
   ```

   `corpus.mjs` parses the leading `>` blockquote as the need's `definition` and the prose after it as `description`; both render on `/need/<id>` (lede + `.need-scope` block). **They are not fields in `needs.yaml`** — that file is now id/tier/order/title/file/status only. A file with no blockquote falls back to its title and the loader warns. Costs nothing here — the threat history and global-failure research are already in front of you. `air` is the worked example. Do **not** back-fill other needs' descriptions.
5. **Ask the user for his India points before researching India.** This is the step that made tier 1 work. He supplies numbered points from lived observation; you research them, then report what's *missing* from his list and wait for approval before writing.
6. **India section** — `### India: <descriptor>`. Split anything latent into `### India: stored risk, not yet realised`.

   **This section must be an enumerated list — one line per distinct failure, ordered by the user's salience judgment.** Not a flowing essay from which failures must later be inferred. This list *is* the handoff artifact to `process-leaf`: each line becomes exactly one leaf, in that order, and the position in the list becomes the leaf's `salience`. Where a tier file's India material is prose, no leaf list exists, and the tier→leaf boundary is nominal — 26 of the 36 need files are in that state (`status: first-sweep` in `needs.yaml`). Shape per line:

   > **<failure name>** — <one line: who is harmed, at what magnitude, by what arrangement.> `[scale: N]` <supporting prose, dated and sourced, as needed.>

   The bolded lead is what `process-leaf` reads as the leaf `title`; the one-liner becomes `one_line`; `[scale: N]` becomes the leaf's `scale`. Writing the list costs nothing extra at tier time — you have just done the research — and not writing it costs a full re-read later.

   **`scale` — the one impact number, set here because the magnitude is already in front of you.** N is the base-10 order of magnitude of the affected / at-risk population in the geography the leaf covers (India unless the failure is global): 52M silica-exposed → `7`, ~500M on solid cooking fuel → `8`. Three rules:
   - **Count the *exposed* population, not the diagnosed or certified count.** Asbestos is millions exposed and near-zero diagnosed — the missing count is the finding, not a reason to rank the leaf low.
   - **If even exposure is unquantified, write `[scale: ?]`** and say so in the line. It sorts last but stays visible — absence of measurement is a finding, not a blank.
   - **Per-leaf ordering key only, not additive.** Overlapping cohorts across leaves (silica-exposed ⊂ construction workforce ⊂ NCR population) are expected; don't try to reconcile them.

   This is **build order for the stub→researched upgrade, not a screen.** Every failure still becomes a leaf and stays on the platform — the catalyst reframe removed ranking-as-selection. `process-leaf` deepens stubs highest-N first.
7. **Data gap paragraph** where measurement is absent. Name it as a finding.
8. **Hand off to `process-leaf`.** Each distinct failure in the enumerated `### India:` list becomes a leaf, and the "who is working on this" pass (`CLAUDE.md`) plus the actor records are done there, not here. `process-leaf` now exists — the handoff is real, and it consists of two things: the enumerated list (step 6) and a **scratch who-works-it list jotted under the need**. Write the scratch list even when it is three names; without it `process-leaf` enters *cold mode* and re-researches §D from zero. Do not write who-works-it findings into the tier file as prose.
9. **Representation classification → also `process-leaf`.** The five-verdict scheme (present-and-moved-the-blocker / present-at-right-unit-unmoved / present-at-wrong-unit / organised-against-the-remedy / absent-at-every-unit) is leaf diagnosis and feeds the `gap:` line; it lives in `process-leaf` in full. One thing to carry *while researching the need*: **treat any affected-led org as a source, not a score.** MLPC surfaced a DMF-funded silicosis corpus and Mahila Housing Trust a working $1,100–1,400 cool-roof loan; both were absent from institutional sources and both changed a finding.
10. **Follow now, record later.** Any actor you surface while doing `### Where it worked` or the scratch list — org or named individual — gets followed on their active platform immediately (`CLAUDE.md` → Actor tracking). The actor record itself (`problems/actors/<slug>.md` per `schema.md`) is written by `process-leaf`.

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
3. **Mechanisms** — table, each found in 3+ files, with the clearest instance **and the leg that can move it**. Reuse the seven from tier 1 where they recur; only name a new one if it genuinely doesn't reduce to them. The instrument column is not decoration — it is what makes each mechanism actionable rather than merely descriptive.
   Keep separate from the table, each with its own subsection and a stated reason for being separate: **the mandate-constitutes-a-market base rate** (how a remedy industry is produced, i.e. the leg-2 → leg-3 handoff), **won the law lost the execution** (how a won remedy fails afterwards — the dominant activism failure mode in tier 1, 4 of 4 rows), and any within-tier class like tier 1's toxic-exposure trio.
4. **Leg and representation, per need** — descriptive, not a routing table. For each need state which legs are active, which are structurally absent, and at what unit the harm can be perceived (`schema.md`, actor record). Name the legitimacy cost wherever the only available unit is central-because-the-affected-benefit-from-the-cause. This is a read-out of the leaves, not a ranking input.
5. ~~**The shortlist**~~ — **dropped by the catalyst reframe.** No ranking table, no frontier-criterion ordering. Every failure gets a leaf and stays on the platform. Keep, instead, a plain list of the tier's leaves with their `gap:` line, so coverage/representation gaps are visible at a glance.
6. **Cross-need nodes** — one concrete object upstream of failures in 2+ needs, typed `instrument / sector / exposure-class` (`CLAUDE.md` → Cross-need nodes). Invisible from inside a single file and the highest-value output of the summary, because one intervention at a node propagates across needs. Still distinguish a node from a **multiplier** (a force no one in the jurisdiction controls — climate) and a **shared condition with no owner** (overcrowding) — neither is a node. Check the register (`problems/cross-need-nodes/00-index.md`) for nodes carried from earlier tiers before naming new ones; add new ones there, not in a tier file.
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
- **Don't let the previous tier's conclusions stand unretested.** A verdict reached under an older frame carries the older frame's bias. Tier 1's "poor hunting ground" verdict had to be withdrawn once the ranking screen that produced it was removed.
- **Don't let the tier become all-India.** Global material carries the threat history and the evolution; India carries the current failure. Both halves are needed for the mechanisms to generalise.
- The `AskUserQuestion` tool was rejected once in tier 1 when offering synthesis shapes prematurely. Ask in prose, and only about things that change the work.
