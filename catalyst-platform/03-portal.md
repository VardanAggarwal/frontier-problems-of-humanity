# Portal — design

The public web layer over `problems/`. Written 2026-09-06, after `00-plan.md` (what the platform is for), `01-scoreboard.md` (what counts as success) and `problems/schema.md` v2 (what the records are).

The data model is not re-opened here. Six record types exist and are specified in `problems/data-model.yaml`; this file designs the layer between them and a browser, and names the deltas the portal forces back onto the model.

**Three decisions taken, 2026-09-06:**
1. **Bodies are parsed into sections**, not shipped as raw markdown. Costs a strict-heading invariant on leaf, actor and node files; buys per-section rendering and cross-leaf section queries.
2. **No submission intake in v1.** A coverage gap renders as a finding, not a form. Revisit when there is traffic to submit from.
3. **Actor records are published.** They are goal 3 and the platform's differentiator. This forces a publish boundary sharper than "the private directory is gitignored" — see *Publishing actors* below.
4. **The emit target is SQLite, and identity stops being derived from paths.** Files stay authoritative for everything a human writes; the DB is derived, and authoritative only for what a machine appends. Taken after the flat-file design was found to depend on filename, directory and classification all staying still — §1 and §5.

---

## 1 · Build pipeline

```
problems/**/*.md  +  needs.yaml  +  lenses.yaml      ← authoritative: human judgment
        │  frontmatter → Zod schema (transcribed from data-model.yaml)
        │  body        → section parser (§2)
        ▼
   validate  →  load into SQLite  →  FK-enforce  →  derive views
        ▼
   problems/index.db          committed. Public view only — private tables omitted, not filtered
   problems/index.json        emitted alongside, for anything that would rather read JSON
```

**Stack: Astro, static, content collections.** The Zod schema in the content config *is* the validator and *is* the loader — one transcription of `data-model.yaml`, not a second artifact to keep in sync with it by hand.

**Emit target is SQLite, not JSON.** The portal ships `index.db` as a static asset and queries it in the browser (sql.js / WASM); no server, no API. This is what makes lens and filter routes cheap enough to keep adding — `/gaps?leg=enterprise` is a `WHERE`, not a rebuild — and it is what turns referential integrity from a list of hand-written build assertions into schema constraints. Assertions 5, 8, 10 and 12 in `README.md` → *What to test* collapse into `REFERENCES`, `UNIQUE` and `NOT NULL`.

`scripts/build-index.mjs` — specified in `data-model.yaml` and `schema.md`, never written — is superseded; those references were updated 2026-09-06. The checks it was specified to run survive: the ones expressible as constraints become constraints, and the three that are not — stale detection, the node `needs:` cross-check, the gap-date-versus-actor-lifecycle warning — become queries run at build against the loaded DB.

### The authority split

The DB is **derived** for everything a human writes, and **authoritative** for everything a machine appends. That line, not "relations in the DB / prose in files," is the one that holds.

| Data | Authoritative in | Why |
|---|---|---|
| Records, relations, classifications, gap verdicts, prose | **markdown** | Every change is a reviewable git diff, editable in an editor with no tool in the way. This is why the corpus gets written at all |
| `sources[].last_checked`, poll results, `## Recent updates` rows | **DB** | Machine-appended, high-frequency, no judgment in them. In files they make every diff unreadable and need concurrent writes the filesystem can't give |
| Connection state transitions, contact state | **DB** (private tables) | Same, plus they change on a cadence the repo shouldn't record |

The monitoring agent writes rows, never files. `## Recent updates` in an actor record becomes a **rendered view** of `update_log`, seeded from whatever is already in the body at first load — which also removes the "machine-appendable fixed line format" constraint that shaped that section.

Putting human-authored relations in the DB was considered and rejected: it makes `actor.leaves[]` invisible in the record, needs a UI or a script for every relation edit, and takes the history out of git.

### Schema sketch

Surrogate integer PKs; the human slug is a `UNIQUE` natural key beside it. That combination is what makes a rename cheap without making frontmatter unreadable.

```sql
CREATE TABLE record (                    -- one row per authored file
  id        INTEGER PRIMARY KEY,
  kind      TEXT NOT NULL CHECK (kind IN ('need','leaf','actor','node','lens','connection')),
  slug      TEXT NOT NULL,
  path      TEXT NOT NULL UNIQUE,        -- repo-relative source file
  url       TEXT NOT NULL UNIQUE,        -- public route, or NULL for private kinds
  private   INTEGER NOT NULL DEFAULT 0,
  title     TEXT NOT NULL,
  one_line  TEXT,
  updated   TEXT NOT NULL,
  UNIQUE (kind, slug)
);

CREATE TABLE alias (                     -- append-only rename ledger; drives redirects
  record_id INTEGER NOT NULL REFERENCES record(id),
  slug      TEXT NOT NULL,
  since     TEXT NOT NULL,
  PRIMARY KEY (record_id, slug)
);

CREATE TABLE leaf (
  record_id INTEGER PRIMARY KEY REFERENCES record(id),
  need_id   INTEGER NOT NULL REFERENCES record(id),   -- a field, never part of the id
  status    TEXT NOT NULL CHECK (status IN ('stub','researched','stale')),
  tier      INTEGER NOT NULL,
  channel TEXT, satisfier_relation TEXT, onset TEXT, agent TEXT,
  gap TEXT CHECK (gap IN ('none','coverage','representation')),
  gap_note TEXT, gap_as_of TEXT,
  CHECK (status <> 'researched' OR gap IS NOT NULL)
);

CREATE TABLE actor (
  record_id INTEGER PRIMARY KEY REFERENCES record(id),
  type TEXT, depth TEXT CHECK (depth IN ('registry','tracked')),
  affected_led TEXT, representation_unit TEXT,
  stance TEXT CHECK (stance IN ('works-the-remedy','neutral','organised-against-remedy','ambiguous')),
  lifecycle TEXT, lifecycle_as_of TEXT,
  contact_route TEXT,                    -- never selected by a public view
  contact_channel_kind TEXT              -- derived; this is what publishes
);

-- relations: declared on one side in markdown, both directions queryable here
CREATE TABLE actor_leaf   (actor_id INT REFERENCES actor(record_id),
                           leaf_id  INT REFERENCES leaf(record_id),
                           note TEXT, PRIMARY KEY (actor_id, leaf_id));
CREATE TABLE actor_node   (actor_id INT, node_id INT, PRIMARY KEY (actor_id, node_id));
CREATE TABLE leaf_node    (leaf_id  INT, node_id INT, PRIMARY KEY (leaf_id, node_id));
CREATE TABLE leaf_lens    (leaf_id  INT, lens_id INT, PRIMARY KEY (leaf_id, lens_id));

CREATE TABLE section (                   -- parsed bodies, §2
  record_id INTEGER REFERENCES record(id),
  key       TEXT NOT NULL,               -- classification | evidence | ... — never the display heading
  heading   TEXT NOT NULL,               -- as written, for rendering
  ord       INTEGER NOT NULL,
  markdown  TEXT NOT NULL,
  PRIMARY KEY (record_id, key)
);

CREATE TABLE ask (                       -- actor needs and offers, one shape
  actor_id INTEGER REFERENCES actor(record_id),
  side TEXT CHECK (side IN ('need','offer')),
  kind TEXT, text TEXT, as_of TEXT, source_url TEXT, state TEXT,
  CHECK (side <> 'need' OR source_url IS NOT NULL)   -- the publish predicate, as a constraint
);

CREATE TABLE monitor_source (            -- DB-authoritative below this line
  actor_id INTEGER REFERENCES actor(record_id),
  kind TEXT, url TEXT, handle TEXT,
  status TEXT NOT NULL,                  -- live | none-found — 'none-found' is a row, not an absence
  last_checked TEXT
);
CREATE TABLE update_log (actor_id INT REFERENCES actor(record_id),
                         date TEXT, text TEXT, url TEXT);

CREATE TABLE connection (                -- private
  record_id INTEGER PRIMARY KEY REFERENCES record(id),
  context_leaf INT REFERENCES leaf(record_id),
  gap_filled TEXT, hypothesis TEXT,
  state TEXT CHECK (state IN ('hypothesis','proposed','introduced','engaged','declined','dead')),
  date_proposed TEXT, date_introduced TEXT, outcome TEXT
);
CREATE TABLE connection_actor (connection_id INT, actor_id INT, PRIMARY KEY (connection_id, actor_id));
```

### Private material — validated, not published

The old strip step said *never look at `problems/private/`*. That protected the boundary and cost referential integrity on the one record type that measures the project's purpose: connection records reference public leaf and actor ids, and nothing checked them, so a rename could silently orphan the introduction it described.

Under the DB, `private/` **loads and FK-enforces like everything else**, and the published artifact is built from a view rather than a filter:

```sql
CREATE VIEW pub_record AS SELECT id, kind, slug, path, url, title, one_line, updated
                          FROM record WHERE private = 0;
CREATE VIEW pub_actor  AS SELECT record_id, type, depth, affected_led, representation_unit,
                                 stance, lifecycle, lifecycle_as_of, contact_channel_kind
                          FROM actor;                    -- contact_route is not in the column list
CREATE VIEW pub_ask    AS SELECT * FROM ask WHERE source_url IS NOT NULL;
```

`index.db` is `VACUUM INTO` over the `pub_*` views only. The private tables are **absent from the published file**, not filtered out of it — a column that is never selected cannot leak, whereas a `WHERE` clause can be forgotten. The build still fails hard if a private table is reachable from the emitted schema.

The DB itself is derived and therefore disposable; `problems/private/` remains the only unbacked-up thing in the repo, and still needs its own backup.

## 2 · Section invariant

Parsing bodies into fields requires the headings to be fixed. Verbatim H2s, in this order, per record type. A missing required section fails the build; an unrecognised H2 fails the build.

**Leaf** — `problems/tier-failure-history/tierN-<tier>/<need>/<slug>.md`
```
## A · Classification      → classification   required when status: researched
## B · Evidence            → evidence         required when status: researched
## C · Diagnosis           → diagnosis        required when status: researched
## D · Who is working on this → actors        required when status: researched
## E · Gap                 → gap              required when status: researched
## Sources                 → sources          optional
```
A `status: stub` leaf has frontmatter and no body. That is valid and it renders — the stub is a real record.

**Actor** — headings already fixed by `problems/actors/_template.md`: `Scope`, `Status`, `What they need`, `What they can offer`, `How to reach them`, `Recent updates`. `Recent updates` parses to `{date, text, url}` on the fixed line format — but only as the **seed** for `update_log`; after first load it is DB-authoritative and the section renders from rows (§1, the authority split). Whether the body section survives at all is open in `README.md`.

**Node** — `The object`, `Cross-need chain`, `The one intervention`, `Leaves`, `Actors on the node`. The last two are overwritten by the derive step; whatever is in the file body is ignored.

**Tier topic file** — the invariant in `CLAUDE.md` already, unchanged. `### Where it worked` parses out to feed `/lens/where-it-worked`; a `first-sweep` file has none and renders the absence, which is the point of the status label.

Parsed sections keep their markdown and render as markdown. Parsing is for addressing, not for restructuring prose.

**Match on a key, not on the heading string.** `## A · Classification` is a display string with a middot in it, and parsing on it makes typography load-bearing. The parser normalises a heading (lowercase, strip the `A`–`E` ordinal, strip punctuation, hyphenate) and looks it up in a section registry, so `## A · Classification`, `## A. Classification` and `## Classification` all resolve to `classification`. An explicit `<!-- s:classification -->` immediately above a heading wins where present. The heading as written is stored and rendered; the key is what everything else addresses.

---

## 3 · Route map

```
/                              the pyramid — 5 tiers + cross-cutting, counts per tier
/tier/1                        the tier's needs as cards + link to 00-summary
/need/air                      tier-file prose, status label, leaf list
/leaf/cookfire-smoke           A–E, gap banner, actors grouped by leg; need shown as breadcrumb, not path
/actor/sewa                    identity, status, needs/offers, updates, leaves worked
/actors                        registry, filter by leg / affected-led / lifecycle
/node/farm-power-tariff        the object, cross-need chain, generated leaves + actors
/nodes                         register, grouped by type
/lens/mechanism/<id>           the seven + unclassified, each with its leaves
/lens/axis/<id>                autonomy, leisure — tagged leaves + container leaves
/lens/latent                   onset: latent — stored risk, as a view not a location
/lens/where-it-worked          positive controls, from every tier file
/gaps                          gap_missing_leg worklist, filterable by leg
/scoreboard                    01-scoreboard.md, generated
/method                        schema, the seven mechanisms, the scope rule
```

Four choices in that map are deliberate:

- **`/gaps` is first-class** because it is the only page that produces work rather than describing it. It is the catalyst's queue.
- **`/lens/where-it-worked` exists so the site cannot become a failure catalogue.** Same corrective as the mandatory `### Where it worked` H2 — a framework built only from failures cannot distinguish a hard problem from a neglected one.
- **`/lens/latent` is a filter, not a folder**, per the v2 model. The stored-risk material stops being a section inside tier files.
- **`/scoreboard` is public and honest at zero.** Publishing `connections engaged: 0` is the commitment device; a private scoreboard is one the archive can quietly outgrow.

---

## 4 · Publishing actors

Decision 3 is the one with a cost, and it is worth stating rather than discovering.

Publishing `depth: tracked` actors publishes that they are being tracked, before contact, along with a machine-readable list of what they need. Three rules contain it:

- **Sourced asks only.** A published `needs[]` row must carry a public URL. Inferred asks and asks heard in conversation stay in the repo record and out of the published database. Enforced by a `CHECK` on `ask` and by `pub_ask` selecting only sourced rows — not by care.
- **Channel kind, not address.** The site says an org is reachable by form; it does not become a scraped contact sheet for small organisations. The route stays in the record for the connect pass.
- **`stance: organised-against-remedy` publishes.** It is a first-class finding of the §D pass and the model was built to hold it. What it must carry on the page is its `sources` — an unsourced adversarial label about a named org is the one thing here that could do real harm.

`depth: registry` actors publish as a name, scope and leg — a citation with a page, nothing more. The registry/tracked split is what keeps the actor volume survivable, and it is also the display rule.

---

## 5 · Model deltas the portal forces

None of these re-open the six record types. The first four are identity: today an id is *derived* from a filename, a directory and a classification, all three of which are mutable, so a reclassification or a `git mv` changes identity with no diff that says so — and under a DB that is indistinguishable from a delete plus an insert.

1. **`id:` is declared in frontmatter and is authoritative.** The build asserts the path agrees and errors naming both, but the file is the claim, not the path.
2. **Leaf ids are bare slugs.** `id: cookfire-smoke`, with `need: air` as a field. The directory stays `<need>/` for browsing, but the build reads frontmatter, never the path. A leaf that gets reclassified — the likeliest edit in a project whose research output *is* revising where things sit — becomes a one-field change instead of a new id and a set of dead inbound links.
3. **`aliases: []` on every record**, append-only. The build resolves them when linking and emits permanent redirects. A rename becomes additive rather than a repo-wide find-and-replace. This is the cheapest of the five and buys the most.
4. **`salience:` derived or dropped.** It duplicates ordering that already lives in the tier file's `### India:` list, so renumbering that list desyncs every leaf under it, silently.
5. **`lenses.yaml`** — a sibling of `needs.yaml`: the seven mechanisms plus `unclassified`, and the two cross-cutting axes, with `id` / `title` / `one_line`. Node has a record and can have a page; mechanism and axis have neither and are the other two cross-leaf lenses. A registry, not a record type.
6. **`contact_channel_kind`** — derived and published; `contact_route` stays in the record and out of every public view.
7. **Publish predicate on asks** — the existing `source` field decides it, now as a `CHECK` constraint. No new field.
8. **Section keys** — §2, enforced at build.

What deliberately does *not* change: the human slug stays the natural key (opaque ids would make every frontmatter list unreadable and move the failure point from the build to the person), relations stay declared on one side in markdown, and `aka` stays a duplicate-detection heuristic rather than part of identity.

## 6 · Build order

Breadth before depth, matching the model's own rule that a stub is a real record.

1. Zod schema transcribed from `data-model.yaml`, loading into the SQLite schema above; build fails on the current corpus until it validates and every FK resolves. This is the step that finds out whether the model is real.
2. Identity deltas 1–4 applied across the corpus; `lenses.yaml`; leaf template committed (`_leaf-template.md`). Do this before there are leaves to migrate, not after.
3. `/`, `/tier`, `/need` — shippable on `needs.yaml` alone, before a single leaf exists.
4. `/leaf` on stubs. Goal 1 is now live.
5. `/actor`, `/actors`, `/node`, `/nodes`.
6. Lenses and `/gaps`.
7. `/scoreboard`, `/method`.

Steps 3 and 4 are the whole of goal 1 and neither needs a researched leaf. Do not sequence the site behind the research.

---

## 7 · Built — 2026-09-06

Steps 1–3 of §6 shipped, plus the node, leaf, actor, lens, gap, scoreboard and
method routes. 66 pages. `npm run build` runs the emit then the site; `npm run
validate` runs the loader alone and emits nothing.

```
src/lib/schema.mjs      Zod, transcribed from data-model.yaml v3
src/lib/sections.mjs    §2 — the key registry, the normaliser, the tier-file parser
src/lib/corpus.mjs      load -> validate -> resolve refs -> derive inverse relations
src/lib/site.mjs        one corpus load per build, shared by every page
scripts/build-index.mjs emits problems/index.db + problems/index.json
src/pages/**            the route map of §3
problems/lenses.yaml    delta 5 — the mechanism and axis registries
```

**Step 1's own test — does the model survive first contact with the corpus? —
passed.** 36 needs and all 5 node records validate against v3 with no edits to
the schema and none to their frontmatter. The warnings are all consequences of
having zero leaves.

Six departures from what §1–§6 specified, each because writing it found
something the design could not have known:

1. **Plain-JS loader, not Astro content collections.** The corpus lives outside
   `src/`, and the same loader has to serve the pages, the emit script and
   `npm run validate`. One transcription of `data-model.yaml` is preserved —
   that was the reason for content collections — without making Astro a
   dependency of validating the corpus.
2. **Pages render statically at build; sql.js is not shipped to the browser.**
   `index.db` is still emitted and committed, and is what a filter route will
   query when one needs client-side filtering. At the current corpus size the
   WASM download would buy nothing, and every §3 route is a static list.
3. **Two databases, not `VACUUM INTO` over the public views.** `VACUUM INTO`
   copies the whole database, private tables included, so it could not have done
   what §1 asked of it. The work DB holds everything with foreign keys on; the
   published file is built by selecting the `pub_*` views into a fresh database,
   so the private tables are absent by construction. The build then re-opens the
   emitted file and fails if `contact_route` or a connection table is in it —
   assertions 1 and 3 checked against the artifact rather than trusted.
4. **Assertion 6 is fatal for leaves, a punch-list line for nodes and actors.**
   The section invariant is enforced from the leaf template onward; the five node
   records predate it. Enforcing it everywhere would have failed the build on
   files written before the rule existed.
5. **The four short node files were normalised to the §2 headings**, and their
   `**Leaves.**` / `**Actors on the node.**` blocks — written as "pending the
   portal build" — deleted, since both sections are now generated from the graph.
6. **`energy.md` is a tier topic file living in the node register.** It carries
   node frontmatter and validates, but its body is `How the need has been
   threatened` / `How humanity evolved` / `Where this fails today` — the tier
   invariant, from when it was `cross-cutting/03-energy-access.md`. It renders,
   with its H2s unrecognised and warned. Either it becomes a node record in the
   §2 shape and its threat history moves back under a need, or energy is a need
   and not a node. Left as found; it is a judgment, not a build failure.

Still unbuilt: submission intake (deliberately, decision 2), the monitoring
agent that writes `update_log` and `monitor_source` rows, redirect emission from
`aliases`, and `/lens/where-it-worked` counts as a scoreboard row.
