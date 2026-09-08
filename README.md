# fph — Frontier Problems of Humanity

Rederiving Maslow's hierarchy from a single drive (persist/propagate), mapping each tier to documented civilizational failures, and building a public platform that catalogues every actor working on each failure — what they need, what they can offer, how to reach them — to act as **catalyst** connecting them across the activism / institution-building / enterprise legs.

`CLAUDE.md` is the working manual (method, standards, invariants). This file is the structure map and the open-work list.

## Structure

| Path | What it is |
|------|-----------|
| `notebook.md` | verbatim working journal — who I am, the method |
| `playbook.md` | the 12-step domain loop (lived on food) |
| `catalyst-platform/00-plan.md` | the platform: browse tree, research per problem, actor list; division of labour; sequence |
| `problems/tier-taxonomy.md` | the rederivation — one drive, nested containers, 5 tiers |
| `problems/schema.md` | prose explainer for the six record types and how they wire |
| `problems/data-model.yaml` | **formal schema** — fields, types, enums, relations; source of truth for record shape |
| `problems/tier-failure-history/needs.yaml` | **need registry** — 36 rows; levels 1–2 of the browse tree; source of truth for need ids and per-file status |
| `problems/tier-failure-history/00-index.md` | human-readable view of the above + leaves; marks `first-sweep` vs `standard` files |
| `problems/tier-failure-history/tierN-*/NN-<need>.md` | per-need file: threat history, evolution, `### Where it worked` |
| `problems/tier-failure-history/tierN-*/<need>/<slug>.md` | **leaf** — one documented failure instance (A–E) |
| `problems/tier-failure-history/_leaf-template.md` | leaf frontmatter + the five A–E headings. The headings are a build invariant, not a style |
| `problems/tier-failure-history/cross-cutting/` | axes that can't be lost alone — freedom, leisure; `00-index.md` + one essay per axis |
| `problems/cross-need-nodes/00-index.md` | **node** register — concrete objects upstream of 2+ needs, typed `instrument / sector / exposure-class` |
| `problems/actors/<slug>.md` | **actor** — one org or person, spanning needs; `depth: registry \| tracked` |
| `problems/private/` | **gitignored** — catalyst notes, connection records, contact state. Not backed up by git; back up separately |
| `catalyst-platform/01-scoreboard.md` | the counters that make catalyst work visible |
| `catalyst-platform/02-connect-pass.md` | the pair-scoped procedure — asks + offers → a connection record → two drafted messages |
| `catalyst-platform/03-portal.md` | **the portal design** — build pipeline, section invariant, route map, publish boundary, build order |
| `problems/index.db` | **generated** — SQLite, public views only; the portal queries it in-browser. Files stay authoritative (`03-portal.md` §1). Not built yet |
| `problems/index.json` | generated alongside `index.db`, for anything that would rather read JSON |
| `problems/lenses.yaml` | registry for the two cross-leaf lenses that have no record — 7 mechanisms + `unclassified`, 2 axes (not written yet) |
| `economics-of-change/` | the lens for whether a change initiative's economics hold |
| `publishing/` | drafts for an outside reader |
| `.claude/skills/process-tier/` | the tier-research sequence (invoke `/process-tier`) |
| `.claude/skills/process-leaf/` | the per-failure sequence — leaf + actor records (invoke `/process-leaf`) |

### Record types (see `schema.md` / `data-model.yaml`)

- **leaf** — one documented failure instance, under a tiered need.
- **cross-cutting leaf** — a failure not reducible to a single tiered need (slavery, bonded labour). Otherwise the axis is just a `cross_cutting:` tag on a normal leaf.
- **node** — one concrete object (policy lever, sector, hazard class) upstream of leaves in 2+ needs. Peer to "mechanism": mechanism groups leaves by an abstract *pattern*, a node by a concrete *object*.
- **actor** — one org or person working on one or more leaves and/or nodes. Links declared once on the actor/leaf side; inverse views generated. `depth: registry` (cited once, cheap) vs `tracked` (a catalyst target, monitored, requires needs/offers/contact_route).
- **need** — a row in `needs.yaml`. Levels 1–2 of the browse tree; previously an H2 convention with no record.
- **connection** — a pair of actors and the introduction between them. **Private** (`problems/private/connections/`). The only record type that measures the project's actual purpose.

Every leaf carries `status: stub | researched`. A stub is a real record — it is browsable, linkable, and can receive an actor submission — so goal 1 does not wait on goal 2.

## Scope

**India-anchored.** Threat history and evolution are global; the failure record is India. `geography:` on every leaf and node makes this explicit rather than assumed. A global failure earns its own leaf only where its mechanism differs from the Indian one; otherwise it is evidence inside the India leaf.

## TODO

### Now
- [ ] **Identity deltas — do these before there are leaves to migrate.** `id:` declared in frontmatter and authoritative over the path; leaf ids become bare slugs with `need:` as a field (so a reclassification is a one-field edit, not a new id); `aliases: []` append-only on every record, driving redirects; `salience:` demoted to list-position/tiebreak, with `scale:` (base-10 order of magnitude of the exposed population, set at tier time) now the stub→researched process-order key. `03-portal.md` §5.
- [ ] **Portal step 1 — transcribe `data-model.yaml` into an Astro content-collection Zod schema loading into the SQLite schema, and run it against the current corpus.** This is the step that finds out whether the model is real: every record either validates and every FK resolves, or the disagreement between the spec and the files becomes a punch list. Nothing else in the portal can start before it.
- [x] ~~**`scripts/build-index.mjs`**~~ — superseded by `03-portal.md` §1. The Zod schema *is* the validator and *is* the loader, so there is no second artifact to keep in sync with `data-model.yaml`. Of the checks the script was specified to run, those expressible as constraints become constraints; stale detection, the node `needs:` cross-check and the gap-date-vs-actor-lifecycle warning become queries against the loaded DB.
- [ ] **`problems/lenses.yaml`** — `id` / `title` / `one_line` for the 7 mechanisms + `unclassified` and the 2 cross-cutting axes. Same shape as `needs.yaml`. Unblocks `/lens/*`; ~20 minutes, no research.
- [x] **`process-leaf` skill** — `.claude/skills/process-leaf/SKILL.md`. Sibling of `process-tier`; turns one entry in a tier file's `### India:` list into a leaf record + its actor records. Design notes below (§ Notes for `process-leaf`) fed it; three README-open questions resolved provisionally in the skill (slug convention, global-vs-India leaves, leaf ordering).

### Next
- [ ] **Ship goal 1** — `/`, `/tier/N` and `/need/<id>` render from `needs.yaml` alone, then `/leaf/*` on stubs. All four routes are live before a single researched leaf exists; do not sequence the site behind the research (`03-portal.md` §6, steps 3–4).
- [ ] **Then `/actor`, `/actors`, `/node`, `/nodes`, the lenses, `/gaps`, `/scoreboard`.** `/gaps` is the only route that produces work rather than describing it — it is the catalyst queue, and the reason the portal is worth building before the corpus is deep.
- [ ] **Enumerate `### India:` failure lists.** `process-tier` step 5 now requires a one-line-per-failure list; the existing tier-1 and tier-2 `standard` files carry India material as prose, so the tier→leaf handoff artifact doesn't exist yet. Air first — it is the retrofit target below and the list is the input to it. Research work, one file per sitting.
- [ ] **Retrofit tier-1 to leaves**, one need file per sitting, air first. Migrate `03-air.md`'s `**Who is commercially working**` / `**Who represents the affected**` / `### India: stored risk` blocks and the `## Follow-list` table into leaves + actor records.
- [ ] **First actor records** — `problems/actors/` is empty. Seed from tier-1 research already done (SEWA, MLPC, SKA, Mahila Housing Trust, BANI/IAVA, Warrior Moms, …).
- [ ] **Energy node** — extract access leaves and grid-failure leaves from the retained essay in `cross-need-nodes/energy.md`.
- [ ] **Bring the 26 `first-sweep` files to the invariant** — none has a `### Where it worked` section, so no tier past 1 can yet answer whether activism or enterprise moves its needs. Marked per-file in `tier-failure-history/00-index.md`.
- [ ] **First connect pass** — needs ≥2 `tracked` actors with an ask and an offer. Blocked on the actor seeding above, not on tooling.
- [ ] **Cross-cutting tags** — add `cross_cutting:` to existing tier-1 leaves where autonomy/leisure bites; create `cross-cutting/<axis>/` thin containers when the first irreducible failure is written.

### Later
- [ ] **`education` sector node** — research pass, then write into `cross-need-nodes/`. Currently a candidate stub in `00-index.md`.
- [ ] **Rewrite `process-tier/SKILL.md`** — currently corrected via a reframe banner; do the full rewrite when tier 2 starts.
- [ ] **Pre-commit hook** running the portal build's validate+load step once it exists — a commit that breaks a foreign key should not land.
- [x] **Superseded material marked in place** — `problems/societal-pyramid.md` (rival three-tier pyramid), `problems/tier-failure-history.md` (single-mechanism first pass) and `problems/health.md` now carry a superseded banner under the H1 pointing at the live file. Still open: whether to move them to a `superseded/` directory, and what to do with `problems/river-linking/`.
- [ ] **Tier-1 summary** still has a `## The shortlist` section ranked on the frontier criterion. Replace with the plain leaf-list + `gap:` line per `process-tier/SKILL.md` summary step 5.

### Open questions
- [x] Do **mechanisms** and **positive controls** become first-class registers? Resolved 2026-09-06 by the portal design: mechanisms and axes get `lenses.yaml` — a registry with an id/title/one-line, enough to own a page, *not* a record type (no body, no frontmatter file, no actors). Positive controls stay a **generated view** over tier files' `### Where it worked`, because they have no identity of their own to register. Only the node stays a first-class record, because only the node has actors who work it directly.
- [ ] **Does the portal publish `stance: organised-against-remedy`?** `03-portal.md` §4 says yes, with sources mandatory. This is the one published field that could do real harm to a named org if wrong, and it has not been tested against a real actor record yet — revisit at the first one.
- [ ] **Do the `<domain>/` files (`food.md`, `meal-system/`, `river-linking/`) belong in the record model at all**, or are they a parallel personal-practice track that should stay out of the record model entirely?
- [x] Trigger review for moving off flat files. Resolved 2026-09-06, and the answer was a split rather than a move: markdown stays authoritative for everything a human writes, SQLite is derived from it, and the DB is authoritative *only* for machine-appended time-series — poll results, `last_checked`, `## Recent updates`, connection state. The recorded trigger (monitoring agent needing concurrent row-writes) is the exact boundary, so it fires for that data and for nothing else. The registry passing 200–300 is no longer a trigger for anything.
- [ ] **Does `## Recent updates` survive as a body section at all?** Under the split it becomes a rendered view of `update_log`, seeded once from what is already in actor bodies. That removes the fixed-line-format constraint on the section — and also the ability to hand-write an update while offline in a file. Decide at first monitoring-agent run.

## What to test

Two kinds, and they fail differently. **Build assertions** are mechanical, cheap, and stop a bad record reaching the published database — write them alongside the Zod schema, not after. **Judgment checks** cannot be automated: each one needs a real record, a real reader or a real introduction before it can be run at all, so each carries the trigger that makes it runnable.

### Build assertions — write with the schema

Ordered by what they cost if they fail silently.

| # | Assert | If it fails silently |
|---|--------|----------------------|
| 1 | **Nothing under `problems/private/` reaches the emitter.** Path-level check, not a field-level one | A push cannot be unmade. This is the only assertion whose failure is irreversible |
| 2 | **No `needs[]` / `offers[]` row publishes without a public-URL `source`** | An inferred ask goes out attributed to a named org, sourced to nothing |
| 3 | **`contact_route` is in no published view's column list** — only derived `contact_channel_kind` | The actor registry becomes a scraped contact sheet for small orgs |
| 4 | **Every `stance: organised-against-remedy` actor has ≥1 source** | An unsourced adversarial label about a named org — the highest-harm output the site can produce |
| 5 | **No dangling refs** — every `need:`, `nodes[]`, `leaves[]`, `mechanisms[]`, `cross_cutting[]`, `parent`, `superseded_by`, `affiliations[].actor` resolves | Reverse indexes silently under-count; a node page loses leaves and reads as narrower than it is |
| 6 | **Section invariant** — required H2s present and verbatim when `status: researched`; unknown H2 is an error, not a warning | The parser drops a section and the page renders as if the work was never done |
| 7 | **Stub key discipline** — a `status: stub` leaf carries only the nine permitted keys (id, title, one_line, status, tier, need, geography, salience, scale) and no body | Half-researched leaves accumulate as stubs and the researched/total counter lies |
| 8 | **Node `needs:` ⊆ union of member leaves' needs**, warn on any need claimed with no member leaf | The check that already caught `sleep` on `toxic-exposure-class`. A node over-claims its reach |
| 9 | **`gap_as_of` is not older than any linked actor's `lifecycle_as_of`** → set `stale` | A `gap: none` stands against an org that has since shut. Worse than a blank |
| 10 | **`status: researched` implies `gap:` set, and `gap: coverage \| representation` implies `gap_missing_leg` non-empty** | `/gaps` under-reports, and `/gaps` is the queue |
| 11 | **Sources resolve** — every `sources[].url` returns 2xx; `status: none-found` is a legal row, an empty list is not | Link rot turns evidence into assertion. Run on a schedule, not per-build |
| 12 | **Slug uniqueness** across needs, leaves, actors, nodes; `aka` collisions flagged as suspected duplicate actors | Two records for one org, and the reverse index splits its leaves between them |

Assertions 1–4 should fail the build. 5–10 fail the build once the corpus is clean; until then they emit a punch list. 11–12 are scheduled, not blocking.

**Revised 2026-09-06 by the SQLite decision.** 5, 8, 10 and 12 stop being hand-written checks and become schema constraints — `REFERENCES`, `CHECK`, `UNIQUE`. 2 becomes a `CHECK` on `ask`. 1 and 3 get stronger: private tables are *absent* from the emitted file and `contact_route` is not in any published view's column list, so neither can be leaked by a forgotten `WHERE`. What stays hand-written is 4, 6, 7, 9 and 11 — everything that is a judgment about content rather than a fact about shape. Assertion 12 also loses half its job: `UNIQUE (kind, slug)` catches collisions, leaving `aka` as duplicate *detection*, which is a heuristic and always was.

### Judgment checks — each needs a trigger

- **Does the model survive first contact with the corpus?** Run the schema against every existing file. The output is a list of disagreements between `data-model.yaml` and reality; each is either a file to fix or a spec to correct, and which one it is has to be decided per row. *Trigger: portal step 1 — this is the point of it.*
- **Is a stub actually browsable?** Read `/need/air` and `/leaf/*` with only stubs rendered, as an outsider. If a stub page reads as broken rather than as a known-but-unresearched problem, goal 1 does not ship on stubs and the build order is wrong. *Trigger: portal step 4.*
- **Does §4's publish rule hold against a real record?** The `organised-against-remedy` decision was taken with zero actor records in existence. *Trigger: the first actor it would apply to.*
- **Reachability ratio.** One pass on `03-air.md` gave 11 of 19 actors with no reachable public channel. If that holds at 50+ actors, the binding constraint on the catalyst role is reaching people, not knowing whom to reach — a different problem needing fieldwork, not tooling. *Trigger: 50 actor records.*
- **Do counters 1–2 move at all?** The scoreboard's stated failure mode is 5 and 6 climbing while 1 and 2 stay at zero. That is a test with a deadline, not a metric to watch. *Trigger: six months from the first researched leaf.*
- **Does anyone submit a name?** Submissions are deliberately out of v1, so the coverage-gap claim is untested — the platform asserts someone is working these problems and that it hasn't found them. *Trigger: whenever intake is built.*
- **Does `/gaps` produce a connection?** The route exists because it should generate work. If a connect pass has never started from it, it is a view of the archive wearing a queue's name. *Trigger: after the first connect pass.*

## Notes for `process-leaf`

Superseded — the skill is written. See `.claude/skills/process-leaf/SKILL.md`; the three questions left open here (slug convention, global-vs-India leaves, leaf ordering) are resolved there and in the Scope section above.
