# The question set — what a `problem` and an `actor` record must answer

Companion to `01-minimal.md`. That file is the pipeline (gates, fetch, resolve,
write); this one is the **field set** — the list of things a research pass is
trying to find out about one entity, and the claim each answer resolves to.

Written 2026-09-13, when the first dive-loop implementation was rolled back.
The loop was the wrong shape (see *Why this is a doc and not code*, below); the
question set it was built around was not, and is the part worth keeping. It is
lifted from `process-leaf`'s A–E structure (`.claude/skills/process-leaf/SKILL.md`),
the leaf template (`problems/tier-failure-history/_leaf-template.md`) and the
actor template (`problems/actors/_template.md`), so a worker that answers all of
these produces a record with the same field coverage a hand-written one has.

## Conventions

- **Claim field** is where an answer lands, per `prompts.py`'s field-name
  convention: a bare name is a column on `problem`/`actor` (via `store.db.put`);
  `tag:<ns>` is a classification tag (via `store.db.tag`, namespace must be in
  `store/tags.py`'s REGISTRY); `ask:need:<kind>` / `ask:offer:<kind>` is a row in
  `ask`; `channel:<kind>` is a row in `channel`.
- **Multi** means the question can legitimately be answered more than once
  (more than one mechanism, more than one missing leg, more than one channel).
  A single-valued question is answered once and closed.
- **An answer is one specific, checkable sentence** — carrying a number, a name,
  a date or a reason. Not a bare label, and not a paragraph. "Short" does not
  mean shallow: `tag:magnitude` is one sentence, but it must contain the figure
  *and* its denominator.
- **No answer is better than a guessed one.** A question the source does not
  address is omitted, not answered "not mentioned".
- **Absence is sometimes the answer.** For `measurement_state` especially, "the
  harm is counted nowhere" is the finding, and must be stated rather than left
  blank (`CLAUDE.md` → Research standards).
- **Sources disagree → write the disagreement** in the answer itself, with both
  figures and their sources. Never average, never silently pick a side.

## `problem` — 19 questions

### Core

| # | Question | Claim field | Multi |
|---|---|---|---|
| 1 | In one sentence: what is the failure, stated as a browse-card definition? | `one_line` | |
| 2 | Is this documented enough to call `researched`, or still a `stub`? | `status` | |
| 3 | Where does this failure occur — place names or scopes? | `geography` | |
| 4 | Which response types does it need — activism, institution, enterprise, service? | `needs_legs` | |

### A · Classification — each with the one-clause reason for *this* value and not the neighbouring one

| # | Question | Claim field | Multi |
|---|---|---|---|
| 5 | Is the harm acute, chronic, or latent (already incurred, not yet in mortality data)? | `tag:onset` | |
| 6 | What triggers the harm — the agent category? | `tag:agent` | |
| 7 | Is the harm direct, structural, cultural-normative, or ambient-accidental? | `tag:channel` | |
| 8 | Is the satisfier absent, a violator, a pseudo-satisfier, maldistributed, or degraded-quality? | `tag:satisfier_relation` | |

### B · Evidence

| # | Question | Claim field | Multi |
|---|---|---|---|
| 9 | Magnitude **with its denominator**, dated and sourced — a number alone is not an answer, it needs what it is a fraction of. | `tag:magnitude` | |
| 10 | Who is hit harder and why, **and** why they can't exit or defend (no information / no resources / no standing / benefits from the cause)? | `tag:differential_vulnerability` | |
| 11 | Is the harm counted anywhere? If not, say so explicitly — that absence is the finding. | `tag:measurement_state` | |

### C · Diagnosis

| # | Question | Claim field | Multi |
|---|---|---|---|
| 12 | Which of the seven mechanisms does this show — or is it `unclassified` (then say what the pattern actually is)? | `tag:mechanism` | ✓ |
| 13 | Is the visible, reported cause different from the load-bearing one? Which is which. | `tag:burden_note` | |
| 14 | What specifically keeps the known fix from happening — the actual constraint (fiscal, political, technical, organisational), not "lack of will". | `tag:blocker` | |

Mechanism vocabulary: `aggregation-masks-failure`, `spend-mismatched-to-source`,
`instrument-keyed-to-wrong-object`, `authority-mismatched-to-harm`,
`primary-vs-derivative-burden`, `solution-at-hand-blocked`,
`compensation-substitutes-for-counting`, `within-tier-loop`,
`second-half-never-built`, `visible-win-strands-residual`, `unclassified`.
`unclassified` is a legitimate value — a leaf tagged `unclassified` with a
paragraph on what the pattern really is beats one tagged wrong
(`CLAUDE.md` → The mechanisms).

### D/E · Who works it, and the gap

| # | Question | Claim field | Multi |
|---|---|---|---|
| 15 | Is there an actor at a unit that can perceive **and** act on this specific harm — not an adjacent or merely national body? | `tag:representation_verdict` | |
| 16 | Is the gap `none`, `coverage` (someone works it, unfound), or `representation` (no actor at the right unit)? | `tag:gap_kind` | |
| 17 | Which leg(s) have nobody working them at all? | `tag:gap_missing_leg` | ✓ |
| 18 | One paragraph on the specific shape of what's missing. | `gap_note` | |
| 19 | Who is actively working this, on any leg — every actor the text supports, with what they specifically do. | drives `emits`/`edges` | ✓ |

Also: `tag:cross_cutting` (`autonomy` \| `leisure`) only where the axis
measurably bites, not by default. Use an `edge_kind: member_of` edge to link a
problem to a cross-need node **only when the text names one** — never infer a
node from the mechanism alone. Never invent a tier or need id; those come from
the browse tree.

## `actor` — 17 questions

### Identity

| # | Question | Claim field | Multi |
|---|---|---|---|
| 1 | In one concrete sentence: what does this actor actually do — not a category label. | `one_line` | |
| 2 | Org or individual? | `type` | |
| 3 | Which leg(s) — activism, institution, enterprise (**market-payer only**), service (**donor-funded, no earned revenue**)? | `legs` | |
| 4 | Operating, scaling, distressed, dormant, acquired, shut, or won-and-dissolved — and current as of what date? | `lifecycle` (+ `lifecycle_as_of`) | |
| 5 | Funder, intermediary, capacity-builder, convener, field-builder, researcher, operator, or platform? | `ecosystem_role` | |
| 6 | Is leadership drawn from the harmed population (yes), an NGO/proxy speaking for them (no), or a mix (partial)? | `affected_led` | |
| 7 | `local-affected`, `central-org`, `enterprise`, or `central-at-named-legitimacy-cost`? | `representation_unit` | |
| 8 | Where do they operate? | `geography` | |
| 9 | How would you actually reach them? | `contact_route` | |

A hybrid org (BRAC, Aravind) carries **both** enterprise and service legs, one
per revenue stream — not one leg with a footnote.

`depth` is not asked of the model — it follows the **ground test**
(`CLAUDE.md` → Actor tracking): `tracked` for actors operating where the harm is
(affected-led/local collectives, field enterprises that deploy or service the
remedy, local regulators actually acting); `registry` for everyone cited but not
monitored, however influential — academics, ministers, courts, commissions,
national advocacy shops.

### Status — specific, checkable, dated; never a vague impression

| # | Question | Claim field | Multi |
|---|---|---|---|
| 10 | At what financial scale do they operate — corpus, budget, or latest round/grant — and as of when? One dated sentence. | `funding` | |
| 10b | Who funds them — the named funders, each as its own entry. | drives `emits`/`edges` | ✓ |
| 11 | The **one** checkable number showing actual reach (members, homes, users, revenue, units), dated — flag if self-reported. | `scale_metric` | |

**q10 was split on 2026-09-13, and the two halves are not peers.** *Scale*
sizes the offer, which is what makes a match legible — a ₹50L need introduced
to a fund writing $5M cheques is a bad introduction — so it stays a retrieved
field. *Funder identity* is a relation between two entities, not a property of
one, and relations arrive as edges through the emit path rather than by
retrieving a sentence; `impact-network-crawler` already traverses exactly this
edge. So 10b carries `retrieval: false` in `questions.yaml` — not because the
fact is unfindable, but because retrieval is the wrong instrument for it.

PoC-0b measured the old bundled question at 3/12 (25%) search coverage among
actors for which funding demonstrably applies. That is not an argument for
trying harder: funds do not reliably publish their own funders, and the
catalyst act does not depend on knowing them.

### Leg viability — §D q2/q3

| # | Question | Claim field | Multi |
|---|---|---|---|
| 12 | What makes them viable **on their leg specifically** — the paying customer (enterprise), whether donor funding survives donor exit (service), affected-led-ness (activism), whether their authority contains the harm's source and its reporting unit matches the harm unit (institution)? | `tag:viability_note` | |
| 13 | Where has this actor deployed effort and had it fail, and why? Omit if the source shows no failure — don't invent one. | `tag:failure_note` | |

### Catalyst surface

| # | Question | Claim field | Multi |
|---|---|---|---|
| 14 | What does this actor say it needs (funding, partners, data, policy access)? | `ask:need:<kind>` | ✓ |
| 15 | What can it offer (funding, a channel, a service, distribution)? | `ask:offer:<kind>` | ✓ |
| 16 | What are its live follow channels? | `channel:<kind>` | ✓ |

Always emit `channel:website` for the entity's own primary URL when the source
text *is* that entity's own site — the page existing at that URL is the
evidence, even with no "follow us" line.

An actor with **no reachable public channel** gets one row with
`status: none-found`, never an empty list: who gets to be reachable is itself a
finding.

## Fan-out, on every pass

Independent of the questions above, every read also yields:

- **`emits`** — other orgs and named individuals worth a candidate record of
  their own: co-petitioners, funders, grantees, officials, affected-led leaders
  an NGO speaks for, coalition partners, competing or adjacent ventures,
  founders. Name founders and officials as `kind: actor` individuals in their
  own right, not folded into the org. This is the engine's analogue of
  `process-leaf`'s recursive actor fan-out, and it is the cheaper one: an
  emitted name re-enters through gate 0 (preview dedup) and gate 1 before
  anything is paid for it.
- **`edges`** — typed relations: `part_of`, `member_of`, `works_on`, `cites`,
  `funds`, `board`, `cohort`, `convenes`, `portfolio`, `affiliated`,
  `parent_org`, `superseded_by`. A `works_on` edge carries `relevance`
  (0 mentioned / 1 adjacent / 2 works it / 3 load-bearing), `stance`
  (`works-the-remedy` \| `neutral` \| `organised-against-remedy` \| `ambiguous`)
  and one sentence of `evidence` saying what the actor specifically does. Omit
  any of the three the text doesn't support — never guess a stance.

## Why this is a doc and not code

The first implementation (`worker/questions.py` + `worker/dive.py`, reverted
2026-09-13) hung a research loop off this list: ask the open questions of a
page, follow same-domain outlinks toward whatever stayed open, synthesize at the
end. Four findings from reviewing it, which any second attempt should start from:

1. **`multi` questions never retire**, so the open set is never empty, the
   "stop when everything is answered" exit is dead code, and every candidate —
   including a one-paragraph registry stub — burns the full budget.
2. **Page text was uncapped.** The whole cleaned page went into every prompt,
   several times per candidate. Cap it (~12k chars) before anything else.
3. **Same-domain outlinks can't answer most of these questions.** A magnitude
   with a denominator, a capital graveyard, an affected-led leader — none are on
   the entity's own `/about` page. Source diversity is the binding constraint on
   depth, not the number of passes. A search step is worth more than the whole
   remaining budget.
4. **The right shape is two calls, not five.** Call 1 reads the seed page,
   answers what it can, and — seeing the anchor text — nominates which outlinks
   look likely to answer what's still open. Fetch the top few (HTTP, free,
   parallel). Call 2 reads them together and writes the final claims, which also
   makes a separate synthesis call redundant, because reconciling two sources
   requires seeing both at once. Batching costs attribution: each answer must
   self-report which labelled source it came from, or the `finding` ledger's
   provenance is lost.

And the depth tier that `process-leaf` already uses should be ported before any
of it: `registry` actors get one cheap pass, `tracked` actors get the dive.
Most candidates are `registry`.
