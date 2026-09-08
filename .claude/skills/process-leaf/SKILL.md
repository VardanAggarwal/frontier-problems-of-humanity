---
name: process-leaf
description: Turn one documented failure instance into a leaf record — classification, evidence, diagnosis, the leg-symmetric "who is working on this" pass, actor records, and the gap line. Use when processing an entry from a tier file's `### India:` failure list, or retrofitting an already-written tier file to leaves (e.g. "do the silicosis leaf", "process cookfire smoke", "retrofit air to leaves").
---

# Process a leaf

Sibling of `process-tier`. `process-tier` researches the *tier* (threat history, evolution, `### Where it worked`, the `### India:` failure list). `process-leaf` turns **one entry in that failure list** into one leaf record, and produces the actor records that entry surfaces.

The boundary was set 2026-09-06 by the catalyst reframe: the "who is working on this" pass and the representation classification — `process-tier`'s old steps 7–8 — moved here. File conventions and research standards live in `CLAUDE.md` and are assumed. This skill is the *sequence*.

**The lesson `process-tier` paid for and this skill inherits:** actor discovery run late changes what you conclude. Here it is not late — it *is* the work. Do §D before writing §E, and let §D rewrite §A–C if the actors on the ground contradict the institutional framing (they did for cool-roof loans and the DMF silicosis corpus in tier 1).

## What this owns vs `process-tier`

| `process-tier` (the tier file) | `process-leaf` (the leaf + actors) |
|---|---|
| threat history, evolution, `### Where it worked` | per-failure classification, magnitude + denominator, diagnosis |
| the `### India:` failure list (one line per failure) | one leaf record per line in that list |
| `### India: stored risk` as a one-line pointer list | the latent leaf itself (`onset: latent`) |
| scratch who-works-it notes jotted under the need | the full 5-question leg-symmetric pass → `problems/actors/<slug>.md` |
| — | the `gap:` line and the representation verdict |

Do not re-open threat history or evolution here. If the leaf work reveals the tier file is wrong, note it and raise it — don't fix it inside a leaf.

## Before anything

1. Read the parent tier file's `### India:` section and its `### Where it worked` — the leaf must not contradict the positive control, and often depends on it (the air lead leaf only makes sense against the leaded-petrol win).
2. Read the scratch who-works-it findings `process-tier` left under the need. **Three input modes, and you must establish which one you are in before starting** — the mode changes how much of §D is extraction and how much is original research:
   - **Handoff mode** — `process-tier` left scratch who-works-it notes under the need. Extract, verify every date.
   - **Retrofit mode** — an already-written tier file carries `**Who is commercially working**` / `**Who represents the affected**` / `### India: stored risk` prose. Extract from it, verify every date, don't re-research from zero.
   - **Cold mode** — *neither exists.* This is the common case, not the exception: `**Who is commercially working**` appears in exactly three files (`03-air.md`, `05-sanitation-disease.md`, `06-sleep-circadian.md`) and `**Who represents the affected**` in one, and no scratch notes exist anywhere in the repo. Every other need — including `01-food`, `02-water`, `04-shelter` and all of tier 2 — looks ready for extraction and is not. In cold mode §D is **original research across all three legs**, budgeted as such. Silently writing §D as if extracting is the exact "actor discovery run late" failure both skills exist to prevent.
3. Re-read `CLAUDE.md` → **The mechanisms** (the seven; check before calling anything novel), **Who is working on this** (the five questions), **Catalyst method** (the gap line), **Actor tracking**.
4. Read `problems/data-model.yaml` → `entities.leaf` and `entities.actor` for the current frontmatter spec and enums. The YAML is the source of truth, not this file's template below.
5. `recall` on Slate with the specific failure, full-paragraph query. The user's own framing of a failure often outranks the sourced literature (his public-sense argument became the causal spine of `05-sanitation`); weave it in with citation, don't paraphrase.

## The leafability gate — run before §A

Not every entry in a `### India:` list is a leaf. Tiers 3–5 in particular hold **trend-shaped** material — "the meaning crisis", "the friendship recession", "AI-driven cognitive offloading" — and the leaf schema demands a magnitude with a denominator, a closed-enum agent, and a `gap:` that carries information. Forced through it, a trend produces a leaf whose gap defaults to `representation` and says nothing.

Four questions. **Three yeses or it is not a leaf yet:**

1. **Is there a bounded harmed population?** Nameable, countable in principle — not "young people".
2. **Is there a magnitude with a denominator**, even a contested or absent one? (Absent is a pass: absence of measurement is a finding. *Unbounded* is a fail — nothing to measure.)
3. **Is there an identifiable source or arrangement** that fits `agent` and `channel` without distortion?
4. **Could an actor plausibly work it** — is there a thing to be done, by someone, at some unit?

If it fails: write it as a **`status: stub`** with the one-line and a note saying which questions it failed. That is a real record — it appears in the browse tree, it can be linked, an actor can be submitted against it — and it is honest about being unresearched. Do not force it. If a whole need's material fails, that is a finding about the need, and it belongs in the tier summary.

## Slug and file

- **File:** `problems/tier-failure-history/tierN-<tier>/<need>/<slug>.md` — the `<need>/` subdirectory, created on first leaf for that need.
- **Slug convention:** kebab-case, 2–4 words, **names the failure, not the need** (the need is the parent directory). No numeric prefix — unlike tier files, like nodes. Prefer the mechanism-bearing noun: `silicosis-stone-quarries`, `cookfire-smoke`, `residual-lead-non-petrol`, `asbestos-import-legal`, not `air-problem-3` or a date.
- **ID:** a bare slug (e.g. `silicosis-stone-quarries`), globally unique across all leaves. The need is a field, not part of the id — `data-model.yaml` v3.
- **One failure = one leaf.** Two entries with the same mechanism *and* the same actor set are one leaf; two with the same mechanism but different actors (silicosis vs asbestos — both `solution-at-hand-blocked`, disjoint actors) are two.

## Order of work

**One leaf per sitting.** Same discipline as one-need-per-sitting in `process-tier`. A leaf with a thin §D is not a finished leaf — better to hold it open than to write "no actor found" without having run all three legs.

**Stub the whole list first, then deepen.** When a need's `### India:` list is first enumerated, write every entry as a `status: stub` in one sitting — id, title, one_line, need, geography, salience, scale (the `[scale: N]` tag from the tier file's list line). That is cheap, it makes the browse tree real for that need immediately, and it means goal 1 (a browsable list of problems) ships without waiting on goal 2. Then take one stub to `researched` per sitting, **in `scale` order — highest N first** (§B may correct the tier file's estimate; a `[scale: ?]` sorts last). Depth-first from an empty directory is the wrong build order against a backlog this size.

Ordering of leaves within a need: **process in `scale` order, highest N first**; the tier file's `### India:` list position (`salience`) is the tiebreak. Not alphabetical.

## The record — frontmatter

Template — **validate against `data-model.yaml`, not this block**:

```yaml
id: silicosis-stone-quarries        # bare slug, globally unique, authoritative over the path
aliases: []                         # append-only; former ids, drive redirects
title: Silicosis in stone quarries
one_line: Dry stone cutting exposes millions to silica with no exposure registry and no detection layer.
status: researched                  # stub | researched  (`stale` is set by the build script)
tier: 1
need: air                           # must resolve in ../needs.yaml
geography: [india, rajasthan]       # global | india | <state> | <country>
salience: 2                         # position in the tier file's `### India:` list (tiebreak only)
scale: 7                            # base-10 order of magnitude of the exposed/at-risk population;
                                    # `[scale: N]` from the tier file's list line. Process order: highest first.
channel: ambient-accidental        # direct | structural | cultural-normative | ambient-accidental
satisfier_relation: degraded-quality
onset: chronic                      # acute | chronic | latent
agent: industrial-exposure          # agent_physical for t1–t2, agent_social for t3–t5
mechanisms: [solution-at-hand-blocked, compensation-substitutes-for-counting]
                                    # `unclassified` is a legitimate value — see below
nodes: [toxic-exposure-class]        # node ids this leaf sits downstream of; regenerates that node's leaf list
cross_cutting: []                    # autonomy | leisure — only where the axis measurably bites
gap: representation
gap_missing_leg: [institution]       # WHICH leg is absent — this is what makes gaps queryable
gap_note: no body's reporting unit is the exposed person
gap_as_of: 2026-09-06
sources: []                          # [{title, org, year, url}]
updated: 2026-09-06
last_reviewed:
actors: []                           # actor slugs; reciprocal list is generated — see note below
```

`actors:` is declared **on the actor record** (`actor.leaves`), per `data-model.yaml` relations — the leaf's `actors:` is the generated inverse. In practice: write the actor records, list this leaf's id in each; leave the leaf's `actors:` for the build script. Until the build script exists, hand-maintain it and mark it `# generated`.

Extending an enum (a new `agent`, a new `mechanism`) is itself a finding — note why in §C, don't do it silently.

## Body — A to E

### A · Classification
The failure in one line. Then `channel` / `satisfier_relation` / `onset`, each with the one-clause reason for the value chosen (`CLAUDE.md`, `schema.md` §Leaf A). `onset: latent` = harm already incurred, not yet in mortality data — these leaves have no local affected party by construction; expect §D to route central or enterprise or nobody.

### B · Evidence
- **Magnitude with its denominator**, ratio checkable (`52M silica-exposed / <1% detected`). Every figure dated, every source named inline.
- **Differential vulnerability** — two lines: (a) who is hit harder and why (physiological / circumstantial / compounding on another need); (b) why they can't exit or defend (no information / no resources / no standing / benefits from the cause). Line (b) drives the representation unit in §D: "no standing" → central-org; "benefits from the cause" → central-at-named-legitimacy-cost.
- **Measurement state** — is the harm counted? Absence of measurement is written as the finding, not left as a gap in the research (it was tier 1's most consistent result).
- Numbers hygiene pass (below) before calling §B done. Sources disagree → **write the disagreement**, don't pick silently.

### C · Diagnosis
- **Mechanism(s)** — one or more of the seven. Check against `CLAUDE.md` → The mechanisms before naming a new one; a mechanism that recurs unchanged is tagged, not re-derived.
  **`unclassified` is a legitimate value and sometimes the correct one.** The seven were derived entirely from tier-1 state-instrument failures. Forcing tier-4 or tier-5 material into them produces a confident wrong tag, and the cross-leaf mechanism view then groups unlike things as alike. Using `unclassified` obliges a paragraph here saying what the pattern actually is — that paragraph is where mechanism #8 comes from. A leaf tagged `unclassified` is more useful than one tagged wrong.
- **Primary vs derivative burden** — if the visible cause isn't the load-bearing one, say which is.
- **Node membership** — if this failure is downstream of a concrete object already in `problems/cross-need-nodes/00-index.md` (or one this leaf newly reveals), set `nodes:` and say in one line how the node produces this failure. A new node is registered in `00-index.md`, not described in full here.
- **Blocker** — what keeps the known fix from happening.

### D · Who is working on this
The full leg-symmetric pass from `CLAUDE.md` → *Who is working on this*. One pass, three legs (activism / institution / enterprise), same five questions:

1. **Who is active** — named actors, formation, funding source, status → an actor record each (next section).
2. **What makes the actor viable** — commercial: who the paying customer is · activism: affected-led vs proxy/NGO-staffed · institution: whether the body's authority contains the source and its reporting unit is the harm unit.
3. **Where effort deployed and failed, and why** — commercial: the capital graveyard (unit economics, distribution cost, margin) · activism: won the law lost the execution; blocker moved once vs institutionalised; movement organised *against* the remedy · institution: spend mismatched to source; the second half never built; disbursal rate.
4. **Over-served / over-represented / over-institutionalised** — density disproportionate to measured harm. Usually means the served population is not the harmed one (tier 1: consumer air purifiers vs 52M silica-exposed).
5. **Failure modes with no actor of that leg** — and whether the reason is structural: harmed can't pay (commercial) · harm latent/diffuse or the harmed benefit from the cause (activism) · no administrative unit maps the harm (institution).

Counteract the institutional-source bias here deliberately via the commercial and affected-led sub-blocks — treat any affected-led org as a **source, not a score** (MLPC surfaced a DMF-funded corpus; Mahila Housing Trust a working cool-roof loan — both absent from institutional sources, both changed a tier-1 finding).

**Enterprise-discovery sub-pass — go and look, don't infer it.** Questions 1–5 ask *whether* an enterprise actor exists; the leg's stock verdict ("structurally absent, the harmed can't pay") has been written from the armchair more than once, and SHERA / EPSCO only entered the corpus because the user named them. Run this as its own search. Two enterprise questions, and the leaf answers **both**:

- **(a) enterprise serving the harm as framed** — the abatement contractor, the substitute-product maker, the compensation-scheme processor. Often exists; often serves a customer segment that is *not* the harmed population (EPSCO sells asbestos removal to airports and data centres, not to the households under AC roofs). When this is the finding, the verdict is the question-4 over-served pattern and `gap_missing_leg` still carries `enterprise` — the leg is present at the wrong unit, which is a `representation` gap, not `none`.
- **(b) enterprise attacking the binding constraint** — whoever is trying to change the *unit economics* of the remedy: cost-down manufacturers, frugal-hardware startups, point-of-care diagnostics, materials substitution, fuel-as-a-service. This is where the frontier sits and it is mostly unmapped. Seed the search with the constraint itself, stated as a spec — "non-asbestos roofing at AC-sheet price", "sub-₹500 wet-cutting rig for informal quarries", "point-of-care blood-lead test under ₹100", "PAYGo LPG refill" — and name the ventures you find **even at sub-scale or shut down**. The capital graveyard (who tried, what the unit economics were, who acquired or killed them) is the data that distinguishes a hard market from a neglected one.

Recursive, like the actor fan-out: each venture names adjacent ones — competitors, the incubator or impact fund behind it, the corporate that acquired or shelved it, the standards body. Carry unresearched names in a `### D — enterprise leads not yet mapped` list under §D (one line each: name, what they build, source); a lead becomes a record only when a wave researches it. `depth: registry` unless the venture deploys or services the remedy where the harm is — then `tracked`, per the ground test.

**For every enterprise actor, track the founder(s) too** — a `type: individual` record each, at the same `depth:` as the org, `affiliations: [{actor: <org-slug>, role: founder, from: <year>}]`. A startup's reachable surface is a person, not a company handle: the founder posts, the org account reposts. Name them in §D, dispatch `actor-channel-finder` per founder alongside the org (it already biases person-over-org), and make the founder's personal feed the primary one in both records. Applies to the CEO/founding team of a venture; not to every employee, and a listed-company CMD stays `registry` with the org. Each venture is also a datapoint for the `economics-of-change` lens: does a beneficiary become a paying customer here, or does this need a mandate to constitute the market first (the leg-2 → leg-3 handoff, `00-summary.md` §"when a mandate constitutes a market")?

Then: **representation present?** — is there an actor at a unit that can perceive *and* act on this harm? One line. This feeds §E.

### E · Gap
One line — `gap: none | coverage | representation` — chosen by the five-verdict scheme:

| Verdict from §D | `gap:` | Note in the leaf |
|---|---|---|
| present, and moved the blocker once | `none` | residual problem is execution |
| present at the right unit, unmoved for decades | `none` | representation eliminated as the explanation — name the isolated blocker |
| present but at the wrong unit (unit mismatch) | `representation` | harm unit vs representation unit, both named |
| present and organised *against* the remedy | `none` | coverage exists — name the legitimacy cost |
| absent at every unit | `representation` | constructing a claimant is step one |
| someone works it, the platform just hasn't found them | `coverage` | what kind of actor is missing from the registry |

Keep `coverage` and `representation` distinct: an empty representation slot is a finding (nobody to submit — filling it is fieldwork), not a stub awaiting a submit button.

Three frontmatter fields go with the verdict, and they are what turn a classification into a worklist:

- **`gap_missing_leg`** — which leg is absent. Without it, "show me every leaf with no enterprise actor" means reading every leaf.
- **`gap_note`** — one line on the specific shape.
- **`gap_as_of`** — the date the verdict was reached. A `gap: none` still asserted against an actor that has since gone `shut` claims coverage that no longer exists, which is worse than a blank.

**Not on the leaf:** which two actors should talk, and why. That goes in the actor records' private *Catalyst notes*, never the public leaf. The leaf supplies the inputs (mechanism, blocker, representation present?, gap); the actor records name the introduction.

### Cross-cutting tag
Add `cross_cutting: [autonomy]` (or `leisure`) only where the axis **measurably** bites on this specific failure, rendered as a one-line section: *Cross-cutting — autonomy: <how this failure also removes control>*. A failure that doesn't reduce to a single tiered need at all (bonded labour, slavery) is the container variant below, not a tag.

## Actor records — the §D sub-procedure

Every actor named in §D — organisation **and** named individual (founder, spokesperson, official), every leg — gets a record. Not a citation, a record.

**But not every record costs the same.** Set `depth:` first:

- **`registry`** (the default) — identity, scope, leg, `sources`, `lifecycle`. A vendor cited once in a table. Not in the monitoring rotation, not a connection candidate. Ten minutes.
- **`tracked`** — a catalyst target. Adds required `needs`, `offers`, `contact_route`, and enters the monitoring rotation. Half a sitting each.

Without this split, one-file-per-actor at full depth does not survive the volume: a consumer-purifier vendor mentioned in passing costs the same as an affected-led org you intend to introduce to someone. Promote `registry` → `tracked` when the actor first looks like one half of a connection.

**The ground test decides `tracked` (set 2026-09-07, after a sweep put channel-search effort on the wrong tier of actors).** `tracked` is for actors *working on the ground* — physically operating where the harm is. Assign it at creation, don't wait for a promotion, when the actor is:
- **affected-led / local** — a victims' association, union local, citizen chapter organising the harmed population in its own name;
- **a field enterprise** — one that deploys, sells or services the remedy in the field (aggregators, stove/monitor makers, recyclers), not one that only produces data or analysis about it;
- **a local regulator actually acting** — a state board issuing notices, verifying, levying, on this specific failure.

Keep at `registry` — cited, never monitored — even when influential or frequently quoted:
- evidence-base authors and academics (a `Nature`/`npj` co-author, a think-tank analyst whose report the leaf rests on);
- ministers, courts, commissions, finance commissions — national policy/adjudication bodies;
- national advocacy shops and pan-India NGOs that lobby or publish rather than deliver.
The test is *operates where the harm is*, not *matters to the problem*. A minister matters; they are not on the ground. Run `actor-channel-finder` only for `tracked` actors and genuine connection halves — not for a `registry` academic or official whose feed is a Google Scholar page.

1. **Find their active platform(s)** — wherever they actually post. **Dispatch the `actor-channel-finder` sub-agent, one per actor**, and let them run in parallel — one `Agent` call each in a single message once §D has named the actor set. Each returns proposed `sources:` rows (`{kind, url, handle, last_checked, status}`), a `contact_route:`, dead/dormant feeds already ruled out, and — for any org — a list of **named individuals to spin out as their own `type: individual` records**, with their personal handles. The agent biases to the person over the org channel; honour that when picking the primary feed. It does not write files — you fold its output into the records in step 3. In cold mode this replaces hand-searching for handles; in retrofit/handoff mode, run it to re-verify the `## Follow-list` rows and fill the gaps.
   - **Don't dispatch for a `depth: registry` actor cited once in a table** — a ten-minute record doesn't need a channel hunt. Run the agent for `tracked` actors and any actor that looks like half a connection.
   - **Actor discovery is recursive — run a second wave.** Each `actor-channel-finder` return names other actors it turned up (its `PEOPLE TO SPIN OUT` list, plus a `research next:` line in its catalyst notes — co-petitioners, co-authors, coalition partners, named officials, the affected-led leader an NGO speaks *for*). This is not a side effect: in the silicosis sweep one wave of 7 agents surfaced Sharafat Azad, Dinesh Rai Singh, Mohan Sullia, Amulya Nidhi and more, none previously in the DB, and the affected-led leader appeared *only* this way. **Don't eagerly create a record for every lead.** Instead, carry the unresearched names in the leaf itself — a `### D — coverage not yet mapped` list under §D (one line each: name, relation, source), which is also what backs a `gap: coverage` verdict. Then **fan out a wave 2** of `actor-channel-finder` against the leads worth researching now (affected-led leaders always are); a lead becomes an actor record only when a wave actually researches it. Stop when a wave yields no new names.
2. **Follow/subscribe immediately**, during research — not deferred. The sub-agent only *finds* the feed; following is yours to do, per actor, as its result comes back. (`CLAUDE.md` → Actor tracking.)
3. **Create/update `problems/actors/<slug>.md`** per `schema.md` §Actor record and `data-model.yaml` `entities.actor` — merging each `actor-channel-finder` return into the matching record, and creating the individual records it proposed (`affiliations:` back to the org):
   - **Identity** — name, slug, `type: org|individual`, `affiliations` (individuals → org records), `leg[]`, `affected_led: yes|no|partial`, `representation_unit`.
   - **Scope** — `leaves[]` (list this leaf's id here — this is the owning side of the relation), `geography`.
   - **Status** — `lifecycle`, funding (source + scale + latest round/grant/budget + date), the one checkable scale metric + date.
   - **Catalyst fields** — what they need (dated, sourced), what they can offer, recent updates (reverse-chron, dated, one line + link — the monitoring agent appends here), how to reach them (+ warm-intro path).
   - **Tracking** — `sources[]` (`{kind, url, handle, last_checked, status}`) — the poll list the monitoring agent reads. An actor with **no reachable public channel gets one row with `status: none-found`, never an empty list**: in the one executed follow-list pass, 11 of 19 actors were unreachable, and that is a finding about who gets to be reachable, not an incomplete row. Then `followed`, `followed_date`, `last_checked`.
   - **Catalyst notes — PRIVATE, and in a different file** — `problems/private/actors/<slug>.md`, not a section of the public record. `relationship:` (`not-contacted` default) and connection hypotheses go there. `problems/private/` is gitignored, so the publish boundary holds without waiting on a build script that strips sections.

One record per actor across all needs (one SEWA record, linked from many leaves) — update the existing file, don't fork it.

## Retrofit mode

First real use of this skill is migrating tier-1 files (air first) into leaves. In retrofit mode:

**Target shape for the stripped tier file: `problems/tier-failure-history/_tier-template.md`.** Retrofit is done when the file matches that skeleton — nothing under "moved out to the leaf" left as prose.

- The who-works-it research is **already in the tier file** — the `**Who is commercially working**`, `**Who represents the affected**` and `### India: stored risk` blocks, plus the `## Follow-list` table. Lift it into §D and actor records; re-verify every date and figure against a current source; follow every actor in the Follow-list now.
- Each distinct failure in `### India:` becomes one leaf. The tier file keeps threat history, evolution, `### Where it worked`, the `### India:` list (compressed to one line per leaf + a pointer), and `### India: stored risk` as a one-line-per-latent-leaf pointer list.
- Move magnitude/denominator figures and the stored-risk diagnosis **out** of the tier file into the leaves. **Do not delete the `## Follow-list` table** — replace it with a pointer to the actor records *and keep any row whose actor had no reachable channel*, or carry that fact into the actor record as `sources: [{status: none-found}]` first. The unreachable rows are a finding (11 of 19 in `03-air.md`); deleting the table destroys it.
- Do one need per sitting, as with fresh work.

## Refreshing, correcting and retiring a record

The skills covered writing a record and nothing else — no procedure for a record that has gone stale, is wrong, or describes a problem that has since moved. All three happen, and all three are cheaper than a rewrite.

**Refresh** (a `researched` leaf, or any `tracked` actor, older than ~18 months, or flagged `stale` by the build script):
- Re-verify the top three figures in §B and their dates. Update or write the disagreement.
- Re-check every linked actor's `lifecycle` — an actor gone `shut` or `dormant` may invalidate the `gap:` line above it.
- Re-run §E. Set `gap_as_of` to today even if the verdict is unchanged: an unchanged verdict re-confirmed is information; an undated one is not.
- Set `last_reviewed`. This is a refresh, not a rewrite — one sitting covers several leaves.

**Correct** (two records disagree, or a record is wrong):
- The leaf is authoritative on the failure; the actor record is authoritative on the actor. Where they conflict on a figure, fix the one that is not authoritative and note the correction inline with its date.
- A correction is written into the record, dated, **never silently overwritten** — the same standard as writing a source disagreement. A reader must be able to see that the claim changed.
- If the tier file above is what's wrong, note it and raise it. Don't fix a tier file from inside a leaf.

**Retire** (the blocker moved; the problem is largely solved):
- **A solved leaf is not deleted.** It keeps its record, re-runs `gap:`, and gains a dated note saying what moved and who moved it. A solved problem with a named actor who solved it is one of the most useful records the platform can hold — it is a positive control with an owner, and `### Where it worked` is chronically under-populated.
- If the leaf sits under a node, check whether the node's `status:` should move (`open` → `fix-partial` → `fix-done`). A node going `fix-done` does **not** retire its member leaves automatically; each is re-run on its own.

## Numbers hygiene

Dedicated pass per leaf before done (same as `process-tier`):
- Every figure's year stated, and the latest?
- Any figure repeated with different values across leaf and tier file?
- Any ratio without a denominator?
- Any series implying a trend its sources can't support?
- Any threshold compared against a lenient national standard without saying so (India PM2.5 NAAQS is 8× WHO)?

## Cross-cutting leaf variant

For a failure that does **not** reduce to a single tiered need (slavery, bonded labour, totalitarian daily-life control):
- **File:** `problems/tier-failure-history/cross-cutting/<axis>/<slug>.md`
- **ID:** a bare slug (e.g. `bonded-labour-india`), with `axis: autonomy` as a field. No `need:` parent. Same namespace as leaf slugs — `data-model.yaml` v3.
- Same body A–E. Frontmatter swaps `need` for `axis: autonomy|leisure` and adds `tiers: [1,2,3]` (containers touched — informational). See `data-model.yaml` `entities.cross_cutting_leaf` and `problems/tier-failure-history/cross-cutting/00-index.md`.

## Provisionally resolved here (were open in README §Notes)

Decided to let the skill be usable; raise with the user if any is wrong:

- **Slug convention** — resolved above (kebab, 2–4 words, names the failure, no numeric prefix).
- **Global vs India leaves** — a global (non-India) failure gets its own leaf whenever it is a distinct failure with its own evidence, actors and gap. No artificial gate. Where a failure has both a global and an India instance of the *same* mechanism and actor set, that's one leaf, India-anchored, with the global instance in §B; where they diverge (different actors, different blocker), that's two. The platform catalogues every documented failure — India is where the catalyst can act, not a filter on what's recorded.
- **Leaf ordering within a need** — process order is `scale` (base-10 order of magnitude of the exposed population), highest first; `salience` (list position) is the tiebreak. Not alphabetical.

## Guardrails

- **One leaf per sitting.** Don't batch. The user's pace is slow by design (memory: explicit feedback).
- **§D before §E, and §D can rewrite §A–C.** Actor reality outranks institutional framing.
- **Channel-hunting is delegated, following is not.** Fan out `actor-channel-finder` per `tracked` actor once §D names the set; you still follow/subscribe each feed yourself as results return, and you still write the records. Prefer a named individual's feed over the org's.
- **Don't write his hypothesis as fact.** Research first, report what's missing, get approval, then write.
- **A failed hypothesis is a result** — write the mechanism it revealed.
- **Absence of measurement is the finding.** Say so in §B.
- **Sources disagree → write the disagreement.** Precedents in `CLAUDE.md` → Research standards.
- **Connection opportunities are not chased *mid-leaf*** — log them in `problems/private/`, finish the leaf. They are chased in the **connect pass** (`catalyst-platform/02-connect-pass.md`), whose unit is the actor pair rather than the problem. This guardrail protects the leaf from being abandoned half-researched; it is not a prohibition on making introductions, which is the point of the project.
- Answer the user's questions as questions; don't start editing until asked for the change.
