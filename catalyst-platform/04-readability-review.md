# Readability review — 2026-09-08

Reviewed as a stranger arriving from a link with no knowledge of the model. Research accuracy out
of scope — nothing here disputes a figure or a source. Reviewer spec: `.claude/agents/page-reviewer.md`.

**Two sections. Part 1 is code — fix once, every page benefits. Part 2 is prose — one block per
page, only what is wrong with that page's writing.**

## What a reader actually sees

Two gates hide most of the corpus by default: `global.css:175` hides `.ai-prose` unless
*Show unverified* is on, and `leaf/[id].astro:151,199` collapse sections A–E into `<details>`.

| page | on arrival | in DOM |
|---|---:|---:|
| `/` | 318 | — |
| `/tier/1` | 195 | — |
| `/need/air` | 738 | 3,879 |
| `leaf/residual-childhood-lead` | 719 | 3,262 |
| `leaf/silicosis-stone-industry` | 779 | 2,920 |
| `leaf/small-industrial-town-air` | 814 | 3,827 |
| `leaf/asbestos-import-legal` | 855 | 4,101 |
| `leaf/cookfire-smoke` | 882 | 3,661 |
| `leaf/north-india-winter-smog` | 935 | 3,885 |
| `leaf/crop-residue-burning` | 1,178 | 4,530 |
| `leaf/ambient-asbestos-demolition-dust` | 140 | 140 |

The arrival layer is already the right length. Everything in Part 2 is judged against what a reader
sees on arrival first, and what they see after one click second.

---

# PART 1 · Structure — one-time code changes

Ranked. Each fixes every page at once.

### 1. The stub branch hides a written body and prints a false claim
`src/pages/leaf/[id].astro:133-139` branches on `status: stub` and renders boilerplate — *"It has
not been researched yet — no evidence, diagnosis or gap verdict"* — **instead of** the body.
`ambient-asbestos-demolition-dust` has all three (7 Mt in the building stock, >100M people under
AC roofs, the NAAQS omission, a named enterprise actor) and renders 140 words denying it.
→ Render the body above the note; narrow the note to what is actually missing.

### 2. `00-summary.md` renders nowhere
`src/pages/tier/[n].astro` reads only `corpus.tiers` and `needsByTier`. Grep `dist/` for the
summary's opening claims: nothing. 317 lines carrying the seven mechanisms and *"every failure has
a bearer; almost none has a claimant"* are dark, and `/tier/1` is 195 words of card grid.
→ Expose the tier summary body in the loader; render §1–§2 above the cards, link the rest.

### 3. `Where it worked` is hidden by the "unverified" toggle
`src/pages/need/[id].astro:66` wraps it in `.ai-prose`, same switch as the topic essay
(`global.css:175`). The positive controls — mandatory in the invariant precisely because a
failure-only framework can't tell a hard problem from a neglected one — are invisible by default.
→ Move outside `.ai-prose`. **Underlying decision: the toggle is doing two jobs.** It hides stub
*records* and AI-drafted *prose* under one label. Split it, or change the default.

### 4. `gap_note` prints in full in the always-visible gap box
`src/pages/leaf/[id].astro:144`. 58–120 words of internal shorthand, unconditionally visible, as
one of only ~4 prose blocks on arrival — the densest text on the page in the position with the
least competition.
→ Render the first clause only, or cap at ~60 words, with §E carrying the argument. (Per-leaf
wording is in Part 2.)

### 5. `0 leaves` reads as "this need has no problems"
`src/pages/tier/[n].astro:22` — shown on Water, Shelter, Sanitation, Sleep, i.e. the exact inverse
of the truth.
→ When `leaves.length === 0`: "topic file written · not yet enumerated".

### 6. 34 of 36 need pages dead-end on internal vocabulary
`src/pages/need/[id].astro:28`: *"No leaf records yet… turning that list into records is
`process-leaf`'s job, one per sitting."* This is the reward for two clicks, on 94% of the tree.
→ "Not yet broken into individual cases — the background research below is what exists." Mark
those needs on the pyramid so the click is priced honestly.

### 7. Project vocabulary is in the chrome, unglossed
`leaf`, `0 leaves`, `1 stub leaf record hidden`, `gap: representation`, `stub`, `researched`,
`first-sweep`, `standard`, `leafed`. Only `/method` defines any of them; nothing links there.
Label strings only — files and frontmatter keep the terms.

| term | UI label |
|---|---|
| leaf | **failure** — `/` already says "8 failure records", then tier/need pages revert |
| node | **shared cause** |
| leg | **campaigners / companies / agencies** |
| gap: coverage | **we haven't found who's doing this** |
| gap: representation | **nobody is doing this** |
| stub / first-sweep / standard / leafed | four vocabularies for one axis — collapse to two |

### 8. Need pages are a directory and an essay in one route
Median 2,167 words; `need/livelihood` **9,372**, `sanitation` 6,695, `shelter` 6,670, `food` 6,451.
→ Split the topic essay to `/need/<id>/background`. This also removes the reason `.ai-prose` exists.

### 9. `/tier/N` is the need page at lower zoom
`/` → `/tier/1` → `/need/air` shows the same one-line definition three times before new content.
→ Give it the summary (fix 2) or collapse it to an anchor on `/`.

### 10. Actor pages are the largest dead end
153 pages, each linking to one leaf and back to `/actors`. Verified: `dist/actor/mlpc/index.html`
contains **zero** links to another actor. The connective tissue the project exists for is missing
from the layer that holds it.
→ "Others working the same failure" block on `src/pages/actor/[id].astro`.

### 11. No entry from anything a stranger already cares about
Every route starts from the taxonomy. Place, industry, disease and "who's working on it" are all
in `problems/index.db` and index nothing.
→ One `/browse` route with facets on place / industry / actor. Also the only thing that makes the
153 actor pages — median 514 words, the most concrete asset here — reachable other than through
one alphabetical wall.

### 12. Homepage leads with the method, not the goods
Lead: *"One drive — persist and propagate — rederived into five tiers of need…"*. The counters
(`36 needs · 8 failure records · 7 researched`) read as an admission of emptiness, and sentence two
is a caveat about internal quality labels.
→ Lead with the concrete unit — 153 actors and what each is missing — and put one real problem
above the pyramid.

### 13. Four lens pages ship with zero cards
`lens/mechanism/unclassified`, `lens/mechanism/within-tier-loop`, `lens/axis/autonomy`,
`lens/axis/leisure`. (`second-half-never-built`, `visible-win-strands-residual` and `lens/latent`
have 1 each — keep.)
→ Don't emit a lens with no members.

### 14. `/gaps` is 1,191 words for 4 findings
Each gap rendered up to three times — by kind, then again by missing leg.

### 15. Header is 7 items wide on all 229 pages, 5 of them power tools
Pyramid · Nodes · Actors · Gaps · Where it worked · Scoreboard · Method. `/scoreboard` publicly
reports 0, 0.
→ Pyramid · Problems · Actors · About.

### 16. Two validator rules the corpus needs
- **`gap:` vs `gap_missing_leg:` vs §D can disagree and nothing catches it.** `cookfire-smoke.md`
  declares `gap_missing_leg: [institution]` while §D's "Representation present?" finds the
  institution *present and holding the lever*, and separately reports "no local-affected body" on
  the activism side. The rule to add is a cross-check between the frontmatter verdict and what §D
  actually concludes per leg. (An earlier draft of this review claimed `gap:` contradicted §E on
  this leaf — it does not; §E argues *for* `coverage`, consistent with frontmatter.)
- **"Numbers hygiene" as a heading should fail.** The loader already lifts `Data note —` lines into
  a numbered apparatus block; four files carry an inline "Numbers hygiene" bullet doing the same
  job by hand.

---

# PART 2 · Content — per page

Only what is wrong with the writing. Line numbers are the source record.
**A** = on arrival · **C** = one click in (`<details>`) · **T** = behind the toggle.

## `/need/air` — `03-air.md`
Arrival layer is 738 words: definition, seven cards, two node cards, footer. Thin, not dense.

- **A** · The description is three bullets where the first is a definition restated
  (`:5-9`). Cut bullet 1; it repeats the blockquote above it verbatim in substance.
- **T** · `:108` is a note to yourself — the `process-leaf` batch of six, `§B/§C`,
  `_scratch-magnitude-prose.md` "pending deletion", "Actor records land in a following sitting".
  **Delete.**
- **T** · `:100-106` and `:112-117` re-list the seven failures the cards already rendered, in worse
  form, with slugs. Keep only the "Data gap" and source-split prose the cards don't carry.
- **T** · `:96` is a ~120-word single sentence-chain and the page's longest block. Split after
  "~81% of the total traces to fuel combustion"; cut the trailing "(folded into … not a standalone
  leaf)" parenthetical.
- **T** · `:86-92` "Vegetation as a remedy" is ~700 words on carbon sinks, albedo and Bastin vs
  Veldman — a self-contained essay about a different question. **Split to its own record**, leave:
  "Vegetation is a real carbon mechanism and near-zero for PM2.5 — see [greening-as-remedy]."
- **T** · `:70` "Where it worked" opens on lead petrol and closes pointing at a *food* leaf with no
  explanation. Add the missing clause: "the residual is ingestion, not inhalation, so it now sits
  under food."
- **T** · Every H2 names a container, not a claim. Only "Vegetation as a remedy: real mechanism,
  wrong order of magnitude" states one.

## `leaf/asbestos-import-legal`
Worst lede and worst gap box in the set.

- **A** · `:5` — 65 words, one sentence, four semicolon clauses. Replacement:
  *"India banned asbestos mining but left chrysotile import and use fully legal — a third to half
  a million tonnes a year, mostly roofing sold to poor households. With no disease registry and a
  20–40 year latency, India has reported zero mesothelioma deaths to the WHO. The wave arrives in
  the 2040s."*
- **A** · `gap_note:21` opens on *"central activist representation (BANI / IAVA / OEHNI / Gopal
  Krishna) has sat at the correct unit since ~2000"* — five undefined acronyms and "unit" in its
  project sense, in the first clause of an always-visible block. Replacement:
  *"Representation exists and has existed since 2000 — it has won court rulings and never moved
  the import trade. The blocker is the asbestos-cement lobby and India's veto at the Rotterdam
  Convention."*
- **C** · `:88` — 318-word bullet comparing Ramco / Everest / Visaka / HIL. Table (company ·
  AC-sheet share · substitute line · stance) plus one sentence: "All four run a substitute
  alongside a chrysotile line they will not exit."
- **C** · `:98` "To be logged in the private catalyst notes (not yet written), not here" — note to
  yourself, and the page's last words. Delete.
- **C** · `:78` "(also subject of a c.2009 *IJOEM* 'industry influence' dispute — recorded, not
  adjudicated)" → `Data note —`.
- **C** · `:46` justifies why this leaf uses `violator` where silicosis used `degraded-quality` —
  taxonomy bookkeeping; move behind the classification pop-out.
- **C** · `:96` opens "By the §E row…" — internal rubric citation. Delete the clause.

## `leaf/cookfire-smoke`
Strongest skim summary of any leaf; two structural problems.

- **A** · `gap_note:21` is **120 words — the longest in the corpus** — in the always-visible box,
  opening on "the binding constraint is fiscal". Cut to ~60: the payer for recurring cost is the
  empty slot; enterprise exists but collapses without one.
- **A** · `gap_missing_leg: [institution]` sits against §D concluding the institution is *present*
  and holds the lever, while the activism leg has "no local-affected body". Worth re-reading the
  leg assignment — the argument and the field may be naming different things.
- **C** · `:55` "The kerosene rung, removed" (241 words) and `:75` "Household biogas" (249 words)
  are self-contained arguments about different fuels — the leaf's most original material, and a
  skimmer sees one bold lead and a wall. **Split each to its own record**, leave a sentence + link.
- **C** · `:85-88` `### D — enterprise leads not yet mapped` — a to-do list under a public H3,
  three names and "Source: earthfit.in/about-us". Move to `problems/private/`.
- **C** · `:102` §E is 250 words repeating `gap_note` near-verbatim. One of the two goes.
- **C** · `:47` "pseudo-satisfier dynamic" / "satisfier relation — degraded-quality" → *"issuing
  the connection lets the problem be declared solved while the smoke continues."*
- **C** · `:56` ends on a 60-word parenthetical reconciling "below half" against "60–61%" →
  `Data note —`.
- **C** · Thirteen acronyms, several never expanded — HAP and MRV are the worst.
- **C** · `:47`, `:49` assume the reader came from a sibling leaf ("consistent with the silicosis
  leaf"). Link or cut.

## `leaf/crop-residue-burning`
Past a punch list. Restructure.

- **C** · `:82` is a **single 472-word bullet naming eleven companies** with location, founding
  year, tonnage and offtake each — a directory in sentence clothing. Table (actor · route · who
  pays · scale); the actor cards above §D already carry the detail.
- **C** · `:78` — 174 words listing fourteen bodies in one breath (CAQM, SC, NGT, CPCB, MoP,
  MoEFCC, ICAR-IARI, PRSC, HARSAC, NRSC, PEDA, PAU, HSRLM). Keep the three holding levers; table
  the rest.
- **C** · `:57-58` — **the satellite finding is buried as §B bullet six.** Fires down 90%, partly
  because burning moved after the overpass. This is the most quotable result in the corpus and the
  third instance of a pattern the file itself names. **Own record.**
- **C** · `:59` "Numbers hygiene" (five lines of instructions to yourself) plus the same cautions
  duplicated inline at `:52-55` — each caution is read twice. → `Data note —` lines, once.
- **C** · `:90-100` §E argues the taxonomy with itself for 300 words ("Why not `none`", "Why not
  `representation`") before four numbered findings that are the actual result. Delete both "why
  not" sections.
- **C** · `:47` "the enum does not let a leaf carry both" — schema talk, renders above the fold via
  the classification pop-out. Delete.
- **C** · `:66` explains three nodes and why two are *not* tagged — maintenance note. Delete.

## `leaf/north-india-winter-smog`
- **C** · `:69` — 233-word bullet carrying two mechanism names, a rupee audit, a cross-leaf pointer
  and a provenance note. Replacement lead: *"**Mechanism — spend-mismatched-to-source.** NCAP money
  flows to municipal corporations, which can buy sweepers but have no authority over the combustion
  sources that carry the mortality — so ~68% of ₹9,929 cr went to road dust and under 1% each to
  industry and domestic fuel."* Last two sentences → data note.
- **C** · `:71` "Node membership. None." records a grouping considered and declined. Delete — the
  meta row already shows `construction`.
- **C** · `:58` "Failed hypothesis: 'NCAP/CAQM is starting to bite'" → data note.
- **C** · `:61` "Numbers hygiene" → four `Data note —` lines, joining the one at `:63`.
- **C** · `:106` §E repeats §C's two mismatches near-verbatim. Cut to first and last sentence.
- **C** · *airshed* used 14 times, never glossed. First use: "the airshed — the body of air a region
  shares, here the whole Indo-Gangetic Plain". Also GRAP, NCAP, DSS, 15th FC, NAAQS.

## `leaf/small-industrial-town-air`
Best single detail in the set (the Byrnihat lock-in). Cold open fails on *what am I meant to take
from this*.

- **A** · `:5` — 51-word lede carrying three findings and two mechanisms before the reader has the
  word *airshed*. Replacement: *"Loni and Byrnihat — not Delhi — top the world's PM2.5 rankings.
  Their pollution is made locally, by informal factories and diesel generators too small for the
  emission rules to reach; at Byrnihat the emitters sit across a state line the local regulator
  cannot cross."*
- **C** · `:97` §E is a **single 378-word paragraph** — the longest unbroken block across all
  pages — ending on a three-way comparison to leaves the reader hasn't read. Break into
  activism / enterprise / institution; delete the comparison.
- **C** · `:87-91` `### D — enterprise leads not yet mapped`, ending "own records pending a founder
  wave" — public H3, addressed to you. Move to `problems/private/`.
- **C** · `:58` "(A case exists for `scale: 8` … kept at 7 on the narrower reading)" — adjudicating
  a frontmatter field in front of the reader. → data note.
- **C** · `:97` "The scratch pass searched for…" → *"No affected-led body was found in either town."*
- **C** · `:52`, `:54` source disagreements sit inline as parentheticals; this file has **zero**
  data notes and should have two.
- **C** · `:57` the Mumbai paragraph is a ward-level-masking claim under a town-level heading — own
  record, or two sentences under `aggregation-masks-failure`.

## `leaf/silicosis-stone-industry`
Closest to shippable. Skim summary comes out correct, which is the point.

- **A** · `gap_note` (52 words) leads on "no detection-layer actor exists" — before *detection
  layer*, *leg* or CC16 are defined anywhere on the page.
- **A/C** · `:45` "(`00-summary.md` §7 lists silicosis in the latent set; that is inconsistent…
  **Flagged, not fixed here.**)" — renders **above the fold** in the classification pop-out, so the
  first analytic sentence a stranger reads is an internal filing dispute about a file they can't
  see. Delete here; correct in `00-summary.md`.
- **C** · `:88` §E is one 210-word paragraph restating §D. Keep the first three sentences.
- **C** · `:50`, `:52` — two 120-word bullets. Split "Magnitude" at "Treat the provenance as
  broken".
- **C** · `:68-70` `affected_led: partial`, "Representation unit: local-affected",
  "Registry-depth record" — raw field syntax in prose. *"worker-based but NGO-convened"* says it.
- **C** · `:57`, `:61` bare `§C`/`§D` refs — no §-numbered headings are visible; the rendered H3s
  read "C · Diagnosis". Write "see *Who is working on this*, Enterprise".
- **C** · `00-summary.md §5`/`§7` cited three times (`:45`, `:57`, `:88`) — a file with no link.
- **C** · Undefined on first use: DGMS, DGFASLI, DMF, BOCW, ESIC, CC16, PEL, RSHRC. Drop BOCW and
  RSHRC, which carry no load.

## `leaf/residual-childhood-lead`
Best-written record in the corpus. Three changes.

- **A** · The lede says "~275 million"; the *finding*, buried at `:49`, is **"well over half of
  Indian children"** — and separately that the famous "1 in 3" ratio is global, not India's.
  Promote: *"…~275 million Indian children — well over half of them — still carry elevated blood
  lead…"*
- **C** · `:52` "The sources left after petrol" — 148-word bullet holding four unrelated carriers
  (turmeric, batteries, paint, cookware) with their own figures each. Four-row table:
  source · what the evidence shows · what rule exists. Most-consulted content, least scannable.
- **C** · `:62` — 100 words explaining why a mechanism was *not* tagged, ending "reflected now in
  the `toxic-exposure-class` node's broadened `one_line`". Cut to: *"For asbestos and silica the
  state built a payout layer without a detection layer. For lead it built neither."*
- **C** · `:55` "Numbers hygiene / disagreements" — 140 words of source reconciliation inline;
  zero data notes in the file, should be three (cost-of-GDP, death toll, the 12.1 µg/dL residual).
- **C** · `:61` cites `03-air.md` and distinguishes the mechanism from two others by name. Keep the
  quoted line — *"A win against the most visible source became a reason to stop looking"* — drop
  the taxonomy.
- **C** · Undefined: µg/dL, ULAB, EPR, FSSAI, NFHS, affected-led.

## `leaf/ambient-asbestos-demolition-dust`
Content-rich, format-poor. Body doesn't render at all (Part 1, fix 1).

- The whole body is one 11-line blockquote (`:16-26`), which the loader reads as a lede quote and
  which renders as an aside rather than a page.
- `:16` "Fails the leafability gate on Q1 … Passes Q3 and Q4" — the reader doesn't know the gate.
  Replacement: *"Nobody has measured ambient asbestos fibre in any Indian city, so there is no
  harmed population to count and no magnitude to state."*
- `:26` "Sourced to the user's Slate notes" — delete.
- **Open question:** fold into `asbestos-import-legal` as "the installed stock", keeping the slug
  as a redirect? The distinction between them is exposure route, not harmed population, and the
  parent's §C (`:67`) already carries "the stock already installed" as its load-bearing burden.

---

## House style, from the divergences above

1. **Lede:** two sentences, ≤45 words, second names the failure. Current spread: 36 / 44 / 51 / 53
   / 65. `residual-childhood-lead` is the model.
2. **`gap_note`:** ≤60 words, no acronyms, no project vocabulary. It is always visible. Current
   spread: 52 / 58 / 90 / 96 / 120.
3. **Data notes:** `Data note —` lines only. "Numbers hygiene" as a heading disappears; used in one
   file of four, while all four hand-roll the same thing.
4. **§D:** three-leg bold leads (Activism / Institution / Enterprise). No `### D — … not yet
   mapped` H3 — that material is private. Any bullet naming more than four organisations is a table.
5. **§E:** says only what §C and §D did not. No "why not `<enum value>`" arguments — the reader
   doesn't know the enum exists.
6. **No notes to yourself in the record.** Present in every researched leaf; the cheapest and
   highest-value cuts available.
