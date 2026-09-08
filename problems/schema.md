# Schema — record types

Six record types feed `catalyst-platform/00-plan.md`:

- **need** — one tiered need. Levels 1–2 of the browse tree.
- **leaf** — one documented failure instance, under a need.
- **cross-cutting leaf** — a failure that does not reduce to a single tiered need (slavery, bonded labour). Everything else the axis touches is a `cross_cutting` tag on a normal leaf, not a record.
- **node** — one concrete object (a policy lever, a sector, a hazard class) upstream of leaves in two or more needs. Acting on it moves the whole set.
- **actor** — one org or person working on one or more leaves and/or nodes.
- **connection** — one introduction between two or more actors. Private. **The project's output.**

Leaf↔actor, leaf↔node, node↔actor are all many-to-many.

This file is the prose explainer. `problems/data-model.yaml` is the formal schema — field names, types, enums, relations — and the source of truth for record shape. Instance data lives in each record's markdown frontmatter (needs are the exception: one YAML registry, not one file each); the portal build (`catalyst-platform/03-portal.md` §1) validates it and loads it into `problems/index.db`.

**Changed in v3 (2026-09-06, portal pass).** Ids are declared in frontmatter and authoritative over the path; leaf and cross-cutting-leaf ids are bare slugs with `need:` / `axis:` as fields; every record gains append-only `aliases`. Reason: identity was derived from a filename, a directory and a classification, all three mutable, so a reclassification or a `git mv` changed identity with no diff saying so. `03-portal.md` §5.

**Changed in v2 (2026-09-06, audit pass).** `need` and `connection` are new. Leaves gained `status: stub | researched | stale`, a title/one-line, geography, and dated gap fields. Actors gained typed `needs`/`offers`/`sources`, a `depth`, a `stance`, and identity fields. Private material moved out of the public records into `problems/private/`. The reasoning for each is with the field in `data-model.yaml`.

---

## Record status — why a stub is a real record

`status: stub` exists so that **goal 1 can ship ahead of goal 2**. A known failure that has been named and placed under a need is a valid, publishable record: it appears in the browse tree, it can be linked, a viewer can submit an actor against it. It carries a title, a one-line, a need, a geography and nothing else.

Without this, the first version of the model made `gap:` required on every leaf and `gap:` assignable only from a completed §D — so the only publishable unit of work was a fully researched leaf. Against a backlog on the order of a hundred-plus tier-1 India entries alone, that inverts the sensible build order: it forces depth-first when the platform's value is breadth-first-then-deepen.

`stale` is set by the build script, not by hand: a researched leaf whose `last_reviewed` is over 18 months old, or whose `gap:` was asserted before a linked actor changed lifecycle state.

---

## Need record

**File:** `problems/tier-failure-history/needs.yaml` — one registry, all 36 needs.
**ID:** the slug (`air`, `rule-of-law`, `understanding`). Unique across all five tiers — needs are referenced by bare slug from every leaf and node, with no tier qualifier.

Fields: `id`, `tier`, `order`, `title`, `file` (the tier topic file), `status`. The `definition` (one-line browse-card form) and `description` (paragraph) are not stored here — they are parsed from the tier file's lead area (a leading `>` blockquote, then prose).

`status` records how far the parent topic file has been taken, and it is a **label on epistemic class, not a quality judgment**:

- `first-sweep` — written before the current standards: no `### Where it worked`, few or no `## Sources`. Real work, thin. 26 of 36 files as of 2026-09-06 (all of tiers 3–5, plus tier-2 files 05–07).
- `standard` — meets the `CLAUDE.md` tier-file invariants. 10 files: all of tier 1, and tier-2 files 01–04.
- `leafed` — standard, and its `### India:` list has been enumerated and turned into leaf records.

The corpus holds two epistemic classes and, before this field, a reader could not tell them apart — `00-index.md` listed all 36 identically. The fix is a label, not a rewrite of 26 files.

---

## Leaf record

**File:** `problems/tier-failure-history/tierN-<tier>/<need>/<slug>.md`
**ID:** a bare slug — `cookfire-smoke`, `silicosis-sandstone-quarries`. The need is a field, not part of the id, so reclassifying a leaf is a one-field edit rather than a new id and dead inbound links. The directory stays `<need>/` for browsing; the build reads frontmatter, never the path. Slugs are globally unique across leaves and cross-cutting leaves.

**Frontmatter** (relational fields — full spec in `data-model.yaml`):
```yaml
id: cookfire-smoke
aliases: []                 # append-only; former ids, drive redirects
title: Cookfire smoke
one_line: Solid-fuel cooking loads household air far past the threshold, mostly on women and infants.
status: researched          # stub | researched | stale
tier: 1
need: air
geography: [india]          # global | india | <state> | <country>
salience: 3                 # position in the tier file's `### India:` list
channel: ambient-accidental
satisfier_relation: degraded-quality
onset: chronic
agent: daily-life
mechanisms: [primary-vs-derivative-burden]
nodes: []                   # node ids this leaf is downstream of
cross_cutting: []           # autonomy | leisure — where the axis bites
gap: coverage
gap_missing_leg: [enterprise]
gap_note: no vendor sells to a household that cannot pay
gap_as_of: 2026-09-06
sources: []
updated: 2026-09-06
actors: []                  # generated — declared on the actor record
```

A `stub` needs only `id`, `title`, `one_line`, `status`, `tier`, `need`, `geography`, `updated`.

### A · Classification
- **Channel** — `direct` (an identifiable actor/event acts) / `structural` (harm from how a system is arranged, no single actor) / `cultural-normative` (legitimising beliefs, themselves the harm) / `ambient-accidental` (hazard with a source but no intent and no system design). Galtung + one cell he lacks.
- **Satisfier relation** — `absence` / `violator` (provision damages the need or other needs over time) / `pseudo-satisfier` (felt relief that then blocks the real fix) / `maldistribution` (exists, unequally held) / `degraded-quality` (present, below threshold). Max-Neef.
- **Onset** — `acute` / `chronic` / `latent`. A latent leaf is the old "stored risk, not yet realised" — now a filter view over leaves, not a location.
- **Agent/source** — per-tier-family controlled vocabulary:
  - *Physical (t1, parts of t2):* `nature` · `climate` · `industrial-accident` · `industrial-exposure` · `industrial-pollution` · `daily-life` · `warfare` · `state-policy`.
  - *Social (t3–t5):* `market` · `state-policy` · `social-norm` · `technology-shift` · `demographic-shift` · `deliberate-exclusion`.
  - Extending the vocabulary is itself a finding — note why.

### B · Evidence
- **Magnitude + denominator** — harm size with its denominator, ratio checkable ("52M silica-exposed / <1% detected").
- **Differential vulnerability** —
  - *who is hit harder, and why* — physiological (children ⇒ lead) / circumstantial (informal miner can't not-inhale) / compounding (already deprived on another need).
  - *why they can't exit or defend* — no information (can't attribute) / no resources (can't relocate or pay) / no standing (can't sue or organise) / benefits from the cause.
  - The second line drives the representation unit in Part D: "no standing" → central-org; "benefits from the cause" → central-at-named-legitimacy-cost.
- **Measurement state** — is the harm counted? Absence of measurement is stated as a finding.

### C · Diagnosis
- **Mechanism** — one or more of the seven (`CLAUDE.md` → The mechanisms), or `unclassified`. `unclassified` is not a failure to classify: the seven were derived from tier-1 state-instrument failures, and forcing tier-4 or tier-5 material into them produces a confident wrong tag that the cross-leaf mechanism view then groups as alike. Using it obliges a paragraph here saying what the pattern actually is — which is where mechanism #8 comes from.
- **Primary vs derivative burden** — note if the visible cause is not the load-bearing one.
- **Blocker** — what keeps the known fix from happening.

### D · Who is working on this
Actor-record links grouped by leg, each with one line on what the actor does *on this leaf*.
- **Representation present?** — is there an actor at a unit that can perceive and act on this harm? Feeds the gap line. (Latent harms have no local affected party — expect central-org or enterprise or nobody.)

### E · Gap
`gap: none | coverage | representation` (`CLAUDE.md` → Catalyst method), plus three fields that turn the classification into a worklist:

- `gap_missing_leg` — **which** leg is absent. Without it, "show me every leaf with no enterprise actor" means reading every leaf.
- `gap_note` — one line on the specific shape of the gap.
- `gap_as_of` — the date the verdict was reached. A `gap: none` standing against an actor that has since shut is worse than a blank; the build script warns when this date predates a linked actor's latest lifecycle change.

### Not on the leaf
Connection opportunities and who-should-meet-whom live in `connection` records under `problems/private/`, not the public leaf. The leaf supplies the inputs (mechanism, blocker, representation present?, gap).

---

## Actor record

**File:** `problems/actors/<slug>.md` — flat registry; actors span tiers (one SEWA record, linked from many leaves).
**Private half:** `problems/private/actors/<slug>.md` — catalyst notes only. See *The private layer*.

This is the platform's differentiator (`00-plan.md` goal 3) and the thing the whole method exists to produce. In v1 its entire catalyst payload was free-text prose, which meant the only matcher between one actor's need and another's offer was the operator's memory across every file. The typed fields below exist to make the match a query.

### 1 · Identity
- `name` · `slug` · `type: org | individual`
- `depth: registry | tracked` — **the field that makes the volume survivable.** A `registry` actor is one cited in a leaf: identity, scope and leg, nothing more, and not in the monitoring rotation. A `tracked` actor is a catalyst target: `needs`, `offers`, `contact_route` required, monitored, eligible to appear in a connection. Without this split, a vendor mentioned once in a table costs the same as an org you intend to introduce.
- `aka` (former names, acronyms — the dedup key) · `parent` (chapter/programme → parent org) · `superseded_by` (merged, renamed, absorbed)
- `affiliations` — for individuals, **dated and role-bearing**: `{actor, role, from, to}`. An undated affiliation goes silently wrong the moment the person leaves.
- `leg:` `activism` / `institution` / `enterprise` — may be multiple
- `affected-led: yes | no | partial` — a tag, not a leg
- `representation unit:` `local-affected` / `central-org` / `enterprise` / `central-at-named-legitimacy-cost`
- `stance:` `works-the-remedy` / `neutral` / `organised-against-remedy` / `ambiguous`. An actor organised *against* the remedy is a first-class finding of the §D pass, not a disqualification — the model has to be able to hold one.

### 2 · Scope
- `leaves` → leaf IDs, one line each (the owning side of the relation)
- `nodes` → node IDs
- `geography` / jurisdiction

### 3 · Status
- `lifecycle:` `operating` / `scaling` / `distressed` / `dormant` / `acquired` / `shut` / `won-and-dissolved`, with `lifecycle_as_of`
- funding — source(s) + scale + latest round/grant/budget + date
- scale metric — the checkable one (members / homes financed / users-day / revenue) + date

### 4 · Catalyst fields
- **`needs`** — typed: `{kind, text, as_of, source, state}`. `source` is where the ask was seen (post URL, report, "conversation 2026-09-02"). An inferred ask is allowed but must say so in `text`. `state` tracks whether it is still open.
- **`offers`** — typed: `{kind, text}`. Capabilities, assets, reach, data, convening power.
- **`## Recent updates`** — reverse-chron, one fixed-format line each: `- YYYY-MM-DD — <one line> — <url>`. Body rather than frontmatter because it is read as a narrative and appended to indefinitely. **Under review (v3):** the portal's authority split makes this data DB-authoritative — the monitoring agent writes `update_log` rows and the section becomes a rendered view, which removes the reason for the fixed line format but also the ability to hand-write an update in a file. Open in `README.md`; decide at first monitoring-agent run.
- **`contact_route`** — how a message actually arrives (email / form / handle), plus the warm-intro path if known.

### 5 · Tracking
- **`sources`** — the monitoring agent's poll list: `{kind, url, handle, last_checked, status}`. This is what `00-plan.md`'s scheduled monitor polls; before it, handles lived only in prose and the monitor had nothing to read.
- `status: none-found` is a **recorded value, not an empty row.** In the one executed follow-list pass (`tier1-physiological/03-air.md`), 11 of 19 actors had no reachable public channel at all. That is a finding about who gets to be reachable, not an incomplete row — and the old instruction to delete the follow-list table once its rows became records would have destroyed it.
- `followed: yes/no` + date · `last_checked:` date

### 6 · Catalyst notes — private file
Lives in `problems/private/actors/<slug>.md`, not in the public record.
- `relationship:` `not-contacted` / `contacted` / `in-conversation` / `connected`
- `connections:` → connection ids. (Who they were connected *to* is a connection record, not a suffix on the relationship value — v1 wrote `connected-to-<x>` in this file and `connected` in the YAML; reconciled 2026-09-06 in favour of the record.)

---

## Connection record

**File:** `problems/private/connections/<slug>.md` — e.g. `mlpc--warrior-moms-silicosis`.
**Private, always.** Absent from the published DB — built from views that do not select these tables, rather than filtered out of a full one. Still loaded and FK-checked at build, so a rename cannot silently orphan the introduction it describes (`03-portal.md` §1).

The introduction is the project's primary output and v1 had no record for it. Four entities were formalised; the thing they exist to produce was left to prose — writable, but uncountable and un-followed-up: no pair, no date, no state, no way to distinguish a live introduction from a dead one. The consequence is the failure mode the whole design is most exposed to: **the repo can accumulate leaves and actors indefinitely, stay fully compliant with its own manual, and catalyse nothing, and nothing in the corpus would show it.**

Fields: `actors` (≥2) · `context` (the leaf or node they'd work on) · `gap_filled` (which gap or broken handoff this introduction fills — if that can't be written in one line, it isn't a connection yet) · `hypothesis` (why these two specifically) · `state` · `date_proposed` · `date_introduced` · `outcome` · `updated`.

`state:` `hypothesis` → `proposed` → `introduced` → `engaged`, or `declined` / `dead`. **A dead connection keeps its record.** It is the negative result, and the only way to learn which introductions don't work.

The procedure that produces these is `catalyst-platform/02-connect-pass.md`. Its unit is the actor pair, not the problem — which is why neither `process-tier` nor `process-leaf` could ever reach it.

---

## Node record

**File:** `problems/cross-need-nodes/<slug>.md` — flat registry, slug is the ID (no numeric prefix).

A node is a grouping *across* leaves by shared upstream cause, promoted to its own record because one intervention there moves the whole group. It sits beside the tier tree, not inside it — peer to "mechanism" (mechanism groups by an abstract *pattern*; a node groups by a concrete *object*). A node usually *exhibits* one or more mechanisms.

**Type** — one of:
- `instrument` — a single government lever with cross-need side effects (farm-power tariff, ethanol blending target). One authority, one edit.
- `sector` — a whole provision system that satisfies some needs and harms others (construction, energy). Many sub-levers, many actors. **A sector node must enumerate `sub_levers`** — without them it contradicts the register's own definition ("acting on that single object moves the whole set"), because there is no single edit. The enumerated sub-levers are what make it actionable.
- `exposure-class` — *not* a policy object: a shared hazard family recurring through one mechanism across leaves (toxic exposure: asbestos/lead/silica). Grouped because one class of remedy covers all carriers.

**Frontmatter** (full spec in `data-model.yaml`):
```yaml
id: farm-power-tariff
title: Farm power tariffs and scheduling
one_line: Free/flat farm power plus night-only feeders, set by regulators who hold neither water nor health.
type: instrument
authority: state electricity regulatory commissions + state agriculture depts
geography: [india]
mechanisms: [instrument-keyed-to-wrong-object, primary-vs-derivative-burden]
needs: [water, sleep]
actors: []                 # actors working the object itself, not any one leaf
status: fix-partial        # open | fix-known | fix-partial | fix-done
updated: 2026-09-06
```

`needs:` is **asserted, not generated** — it is the claim that this object reaches these needs, and it is written before the member leaves exist. The build script cross-checks it against the union of member leaves' needs and warns on any need claimed with no member leaf. (That check is what caught `sleep` on `toxic-exposure-class`: the only asbestos route in the sleep file is thermal, not the long-latency mechanism the node is defined by, and the node's own body omitted sleep.)

**Body** (~15 lines):
- **The object** — one paragraph.
- **Cross-need chain** — one line per need: how this single object produces failure there.
- **The one intervention** — what acting on the node looks like; where tried, result. For a `sector`, the sub-lever map instead.
- **Leaves** — *generated* from every leaf whose frontmatter `nodes:` contains this id. Never hand-maintained. Until the portal build exists, this line reads *"pending build"* — not *"(generated)"*, which claims a generator ran.
- **Actors on the node** — *generated* from actor records linking this node.

## Cross-cutting need

An axis (`autonomy`, `leisure`) that can't be lost on its own — it's a property of *how* every other need is met. Two mechanisms:

**1 · Tag.** On any tiered leaf where the axis bites: `cross_cutting: [autonomy]` in frontmatter, rendered as a one-line section on the leaf ("*Cross-cutting — autonomy: <how this failure also removes control>*"). No new record.

**2 · Thin leaf container.** Only for failures that don't reduce to a single tiered need (slavery, bonded labour, totalitarian daily-life control):
- **File:** `problems/tier-failure-history/cross-cutting/<axis>/<slug>.md`
- **ID:** a bare slug — e.g. `bonded-labour-india`, with `axis: autonomy` as a field. No `need:` parent. Same namespace as leaf slugs.
- Same leaf schema (A–E) plus `tiers: [1,2,3]` in frontmatter (containers touched — informational).

**Essay.** `cross-cutting/<NN>-<axis>.md` stays, reframed as the `00-summary`-equivalent synthesis over both the tagged leaves and the container leaves. Keeps the historical threat catalogue. Registry: `cross-cutting/00-index.md`.

Not a tier: no internal hierarchy, no override-frequency ordering, no `## How this need has been threatened` invariant, and no row in `needs.yaml`.

---

## The private layer

`problems/private/` holds everything that must not be published:

```
problems/private/
  actors/<slug>.md          catalyst notes — relationship, connection hypotheses
  connections/<slug>.md      connection records
```

**It is gitignored.** Previously, private catalyst notes were a section inside a committed actor record, stripped only by a build step that does not exist yet, in a repo whose stated direction is public. A push cannot be unmade. Moving the private half into a directory that is excluded at the filesystem level, rather than at render time, means the protection holds before the build script exists and does not depend on it.

The cost is that private material is not backed up by git — **back `problems/private/` up separately.** If you decide the repo will stay private and want the history, delete the `problems/private/` line from `.gitignore`; the directory split still keeps the publish boundary sharp.

---

## Wiring
- Per-file follow-list table → a **generated view**: "actors touching this leaf". Source of truth = actor records.
- The "Who is working on this" pass **produces** actor records; its Q1/Q4/Q5 are answered by querying actor records for the leaf.
- Leaves diagnose *that* a gap or broken handoff exists. Connection records name *the specific introduction*. Both needed for a connection.
- A node's `leaves` list and `actors_on_node` list are generated from leaf `nodes:` tags and actor `nodes:` links — declared once on those sides, never on the node.
- Nodes, mechanisms, and cross-cutting axes are all cross-leaf lenses: node groups by a concrete object, mechanism by an abstract pattern, cross-cutting by which quality is lost. Only the node is a first-class record with its own actors.
- `00-summary.md` per tier: drop the shortlist. Keep cross-need nodes, positive controls (`Where it worked`), the latent-set filter view, and connection opportunities spanning leaves.
- **Counting.** `catalyst-platform/01-scoreboard.md` is the read-out over all of this — leaves by status, actors by depth, connections by state. It is deliberately honest at zero.
