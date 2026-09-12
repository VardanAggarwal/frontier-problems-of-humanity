# Engine v2 — the minimal autonomous design

Status: **proposal, 2026-09-12.** Supersedes two earlier drafts of this file. The first assumed a human dispatches each unit of work; that assumption was doing all the work and it is wrong (§1). The second kept a bandit at the centre; exhaustive registry enumeration mostly removes the need for one (§6).

Relationship to `00-architecture.md`: not a smaller alternative. Most of what that document proposes is correct and load-bearing once exploration is automatic. This document adds the data model it lacks, collapses its fifteen components into four processes, replaces sampling with enumeration, and specifies the compute cascade — which is local-first, and largely already written in `../slate_v2`.

---

## 1. What the first draft got wrong

It argued that the bandit, budget ledger, Entity Resolution service, Content Corpus, Provenance Ledger and Review Gate in `00-architecture.md` were over-built for 291 actors and 9 leaves — that a hand-sorted queue beats Thompson sampling at ~30 pulls a month.

True, and irrelevant, because it smuggles in the conclusion. **Truncating exploration to what a person can dispatch is what made the rest look unnecessary.** Each unit of work emits *k* candidates; with *k* ≈ 5 the frontier after *n* iterations is ~5ⁿ, so manual dispatch fails at the third iteration, not at some distant threshold. Once exploration is automatic: budget caps become the only stopping rule, dedup becomes a service rather than grep over 291 files, provenance has no git diff to live in, per-record review becomes arithmetically impossible, and cost per call starts to dominate total cost.

So: build it. What follows is the shape and the order.

## 2. The data model — three types

`00-architecture.md` describes processes and never says what a record is. Today's schema has six types — `need`, `leaf`, `cross-cutting leaf`, `node`, `actor`, `connection`. Three are one thing at different depths; `cross-cutting` is the fact of having more than one parent; `connection` is an edge whose endpoints are both actors.

- **problem** — recursive. A tier-level need and a single documented failure instance are the same record at different depths.
- **actor** — an org or a named individual.
- **edge** — typed, dated, evidenced. actor→problem, problem→problem, actor→actor.

## 3. Storage — relational, prose on disk

SQLite is the source of truth. Prose lives in files, referenced by a nullable `doc` column.

The DDL below was the sketch; `engine/store/schema.sql` is now the real thing (353 lines) and differs in four places, each forced by the migration: `tag` splits into `(ns, value)` so "every mechanism tag" is an index range; `alias` exists because the resolver needs former ids and the sketch had nowhere to put them; `ask` exists because actor `needs:`/`offers:` are the connect-pass input and 382 rows would otherwise have been dropped; `gap_note` is a column because the paragraph behind a gap is evidence even though the gap is not.

```sql
problem    (id PK, title, one_line, status, geography, needs_legs, gap_note, doc, updated)
actor      (id PK, title, type, legs, depth, lifecycle, ecosystem_role, doc, updated)
edge       (id PK, src_kind, src_id, dst_kind, dst_id, kind, relevance, stance,
            evidence, source_id, as_of)
tag        (entity_kind, entity_id, tag)        -- tier:1 · need:air · mechanism:* · onset:latent
source     (id PK, url_canonical, url_hash, simhash, lang, kind, fetched_at, path,
            canonical_of)                       -- path → cached text on disk
channel    (actor_id, kind, url, handle, status, last_checked)
candidate  (id PK, kind, name, population, discovered_via, score, admitted,
            first_seen, evidence, dup_of)
population (id PK, name, source_url, total_rows, cursor, last_swept, done)
event      (id PK, at, entity_kind, entity_id, field, old, new, by, why)   -- append-only
```

Why relational rather than markdown-primary:

- **A stub is a row with `doc IS NULL`.** Goal 1 ships on stubs and enumeration produces them by the thousand. A stub as a file containing only frontmatter is a file that exists to hold nothing.
- **The schema is written once.** Markdown-primary needs zod validators *plus* emitted DDL *plus* a parser to bridge them — `src/lib/schema.mjs` + the frontmatter half of `corpus.mjs` + `build-index.mjs`, ~600 lines whose whole job is moving typed data into a table you then query.
- **Edges are many-to-many with their own fields.** In frontmatter they need a reverse index built at load (`src/lib/corpus.mjs:162-238`); in a table they don't.
- **Constraints at write.** An autonomous writer must be rejected at the bad write, not at the next build.
- **`event` is easier here than in git** — a trigger and a table. This is `00-architecture.md`'s Provenance Ledger, and under autonomy git cannot do the job because nothing generates a reviewed diff.

Build back the two things git gave free: `sqlite3 .dump` on commit for readable history (one pre-commit line, deterministic with fixed row ordering), and a diff renderer for review (§9). `node:sqlite`'s `DatabaseSync` is already in use at `scripts/build-index.mjs:13` on Node 25 — no new dependency.

**Tags are the view layer.** `tier`, `need`, `salience`, `channel`, `satisfier_relation`, `onset`, `agent`, `mechanisms`, `nodes`, `cross_cutting` all become validated tags; the Maslow tree becomes a traversal. This is what lets the engine be general-purpose rather than instantiated-on-Maslow — the stated goal of `00-architecture.md`, which it then undercuts by keeping those as structural fields.

**Gap is derived, never stored — but the derivation is a floor, not the finding.** Written as `needs_legs` minus the legs present on inbound edges at `relevance >= 2`; measured against the seven researched leaves on migration day, it reproduced one of them. `crop-residue-burning` carries **25 enterprise actors** and still records a missing enterprise slot, because the empty slot is a shape *inside* the leg — "an aggregation-finance entity that closes farm-gate economics for a smallholder in a 12-day window" — not the leg. And `representation`, which is 5 of the 7, is not derivable at all: whether an actor sits at a unit that can perceive the harm is a judgement.

So the view (`problem_coverage`) answers the one question it can stand behind — which legs have nobody on them at all — and the recorded finding survives alongside it as `gap_kind` / `gap_missing_leg` tags plus `problem.gap_note`. They are different questions, and the design was wrong to treat one as replacing the other.

**Language split.** The engine is Python (to reuse `../slate_v2`, §7); the portal stays Astro. SQLite is the interface between them — the portal reads, the engine writes. No shared code, no ORM, no service.

## 4. Four processes

`00-architecture.md` specifies six agents, three services and six primitives across four layers. Most of its agents are prompts against one loop: Problem Agent and Actor Processing differ only in target table and prompt; Writing Agent is a step; Matching/Gap is a SQL query; Actor Discovery is the worker in sweep mode.

```
scheduler   cursor advance · budget ledger · admission control · dispatch
worker      gate → fetch → gate → claims → resolve → write → emit      (N parallel)
resolver    link · content · entity dedup — one service, three granularities
store       sqlite + docs + cached sources
```

Plus one module (not a layer) for text primitives: extract / embed / classify / compare / generate, cached by content hash and pinned to a model id. Model pinning is what makes "why did this tag change between passes" answerable.

## 5. The worker — four gates

The expensive thing is reading. Every gate exists to avoid the next one.

```
gate 0  preview dedup          title + snippet + URL identifiers, no model, no network.
                               Collapses duplicate candidates before anything is fetched.
gate 1  pre-fetch, batched     50 candidates per call, judged on title + snippet + URL path
                               (~60 tokens per decision). Most candidates die here without
                               ever being fetched.
fetch                          canonicalize URL → check corpus → strip boilerplate
gate 2  post-fetch, cheap      first ~500 cleaned chars: is this the entity we thought?
claims                         {entity, field, value, source, confidence} — never prose
resolve                        entity dedup against the graph
write                          rows + optional doc
emit                           candidate children · candidate actors · edges → admission
```

**Gate 0 comes first because it makes every later gate smaller, and it is free.** Measured on a real three-query result set (§8): 21 URLs collapse to 14 fetches, so gate 1 has 33% fewer candidates to judge. It also groups URLs that *cannot be fetched at all* — a 403 or an empty JS shell still has a title — which no post-fetch dedup can reach.

**Gate 1 is the highest-leverage paid piece.** Deciding before fetching, and batching 50 decisions into one prompt, is roughly a 50× reduction against per-candidate calls — and it saves the fetch, the boilerplate strip and the extraction as well.

**Gate 1 is tuned for recall, not precision.** An affected-led collective with a thin Facebook presence and no website looks identical to noise in a title-and-snippet screen. A gate that is 95% precise and quietly drops them would make the long-tail argument decorative, and the loss would be invisible — you never see what you discarded. Let tier 4 do the rejecting.

**Boilerplate stripping is second.** Nav, footers, scripts, cookie banners, for zero model cost. **Measured on 19 real fetched pages: 95% median reduction, range 84–99%** — against the 80% this design assumed. The cost model in §7 is conservative, not optimistic. It is also load-bearing for dedup correctness, not only cost: see §8.

Step `emit` never self-calls. It writes candidates and returns; whether a child is worked is an admission decision (§8). That is what keeps depth a budget question rather than a recursion constant.

**Termination is data-driven:** stop decomposing a problem when actors attach to it rather than to a child of it. A problem you can name an operator for is specific enough. The current fixed three levels (need → leaf → nothing) come from the taxonomy, not from the work.

## 6. Discovery — two modes, only one of which needs a policy

**Mode A — edge-crawl (exploit).** Today's `impact-network-crawler`: funder → grantee → cohort peer → co-petitioner. High precision, and **structurally blind to the disconnected**. An affected-led collective with no funder, no accelerator cohort and no English website is unreachable from any seed at any depth, forever.

**Mode B — exhaustive registry enumeration (explore).** Take a registry and walk every row. Not sampling, not a bandit over populations: **a cursor, not a policy.** Nothing chooses.

```sql
population (id, name, source_url, total_rows, cursor, last_swept, done)
```

This is the single most consequential simplification in the document. If you *enumerate* the actor space rather than *sample* it, the long tail is not something you hunt — it is something you walk past. Deterministic, resumable, auditable, and it produces a real denominator ("14,000 rows swept, 300 admitted, 40 reached relevance ≥ 2") that no sampling method can.

**It also makes `gap: representation` falsifiable.** Today the platform cannot distinguish "no actor exists at a unit that can perceive this harm" from "no actor reachable by edge-crawl." Those are different findings and the method currently conflates them. A completed sweep converts the second into the first.

Candidate populations for the India scope — **counts and access unverified; verifying one is step 4 of the build order**:

| population | why it reaches the tail |
|---|---|
| NGO Darpan (NITI Aayog) | registration is near-universal and free — being in it implies nothing about funding or visibility |
| FCRA registry + quarterly receipts (MHA) | names orgs by money actually received, not by profile |
| MCA CSR disclosures | names the *implementing agency* per project — the operator layer portfolio pages omit |
| MCA21 Section 8 companies | non-profits outside the NGO registries |
| NGT / eCourts / High Court orders | environmental and labour petitioners are affected-led by construction — the best single source for `affected_led` |
| Registrar of Trade Unions, state-wise | worker organisations no philanthropy graph touches |

**Mode B is cheaper per useful actor than Mode A**, which inverts the usual defer-the-expensive-thing instinct. Mode B's funnel head is a structured row — name, state, sector, registration number, a few hundred tokens — filterable by local embeddings at zero cost. Mode A's candidates arrive as unstructured pages needing a fetch and a read just to decide whether they are worth anything. Mode A has no cheap tier 0.

**Query hacks for Mode A**, ranked by expected yield against the popularity filter that search engines impose:

- **Negative queries** — exclude the known head by name (`-"CSE" -"CPCB"`). The most direct attack on the bias, and free.
- **Local-language queries** — Hindi, Marathi, Tamil, Bengali. Probably the highest-yield single hack for Indian affected-led groups, most of which have no English presence.
- **Search for lists, not actors** — petition co-signatories, court party lists, conference attendee lists, annual-report acknowledgements, RTI response tables. One document yields fifty actors.
- **Search the harm in the victims' words** — "silicosis muavza", not "occupational health intervention".
- **Alternative indexes** — Marginalia is explicitly built for non-commercial long-tail pages; Brave and Bing hold materially different indexes.
- **Model diversity** — the same input through two models, candidates unioned. This is the real use for OpenRouter.

**The bandit, demoted.** With Mode B exhaustive, arm selection has almost nothing left to decide. What remains is problem-expansion ordering, and Mode A edge-following — which matters much less once the registries are being walked. UCB1 over problem-expansion is ~40 lines if it earns its place; it is not a prerequisite for anything. If it is ever built, **reward graph distance, not just relevance** — a plain relevance reward re-converges on the dense core, because head actors are easier to verify.

## 7. The compute cascade — local first

Everything that can run locally does. Paid calls happen only at the precision tier.

| tier | what | where | cost |
|---|---|---|---|
| 0 | URL canonicalization, boilerplate strip, SimHash, number/entity extraction | deterministic code | **0** |
| 1 | embeddings — dedup, shortlist, novelty, relevance pre-screen | local SentenceTransformer | **0** |
| 2 | batched screen (gate 1), classification, stance | local small LLM (Ollama) | **0** |
| 3 | overflow when local throughput binds | OpenRouter free rung | **0**, capped |
| 4 | extraction, claims, merge/split judgment, writing | Haiku / Sonnet / Opus, batched | paid |

**`../slate_v2` already implements tiers 1–3.** Lift, don't rewrite:

- **`core/llm.py`** (396 lines) — multi-provider router with `LLM_FALLBACK_ORDER=openrouter,claude-cli,claude,gemini`, a `mechanical` / `judgment` tier split, `estimate_cost()`, `parse_json()`, and truncation-retry with budget escalation.
- **`core/encode.py`** (511 lines) — local `all-MiniLM-L6-v2` (384-dim, L2-normalized) plus local NLI and stance classifiers.
- **`core/config.py`** — `OPENROUTER_MIN_INTERVAL_S=3.0`, which is exactly the documented 20 RPM cap; `OPENROUTER_RATELIMIT_MAX_WAIT=90`.

Its rate-limit handling is already correct for this workload and easy to get wrong: rate-limit waits are tracked separately from retry attempts so they don't consume them, and a `retry_after` beyond 90s falls through to the next rung rather than blocking — which is the right response to a daily cap whose reset is hours away.

**Expectation-setting on the free rung.** OpenRouter free is 20 RPM and 1,000 requests/day with $10+ credits ever purchased (50/day without). On a 45,000-call registry sweep that covers ~2%. Its value is that the sweep *continues* past the cap instead of stalling — resilience, not savings. Since tiers 0–2 are local and free anyway, the free rung is a convenience, not a strategy. Verify its data-retention policy before sending anything; their limits page does not state one.

**Local trades money for wall-clock — but has no cap, so it finishes.** That is the whole argument over the free rung, which trades money for wall-clock *and* caps out. Batching gate 1 at 50 candidates per prompt keeps local throughput tractable: 3,000 candidates become ~60 calls, an evening rather than a week.

**Paid-tier discipline**, for when tier 4 is reached: batch API (50% off, and the engine is non-interactive by construction); prompt caching on the fixed prefix — schema, tag registry, instructions are byte-identical across calls, cache reads at ~0.1×, so keep per-candidate content strictly after the last breakpoint and assert `usage.cache_read_input_tokens` is non-zero; `effort: "low"` on screening routes (not `thinking: disabled`, which on Opus 5 can leak tool calls into visible text); claims as compact JSON, since output bills at 5× input.

**Worked cost, one 10,000-row sweep.** Assumes 15k raw / 3k cleaned tokens per page and 70% / 85% discard rates at gates 1 and 2:

| | naive — everything to Opus 5 on raw pages | this cascade |
|---|---|---|
| tiers 0–2 | — | local · **$0**, 10,000 → 450 |
| tier 4 | 10,000 × (15k in + 2k out) · **~$1,250** | 450 × (5k in + 2k out), batched · **~$17** |

Opus 5 is $5/$25 per MTok, Sonnet 5 $2/$10, Haiku 4.5 $1/$5. Routing mechanical extraction to Sonnet and reserving Opus for merge/split judgment — the `slate_v2` split — takes the sweep under $10.

## 8. Fetch triage and dedup — five layers, measured

Everything below was measured, not assumed. Three searches on silicosis /
Rajasthan (September 2026) returned 21 URLs; all were fetched and run through
the real pipeline. Ground truth established by hand: **three groups of URLs
that are the same work** — a paper at six URLs, and two papers at two each.

| layer | caught | cost | note |
|---|---|---|---|
| URL canonicalization | 0 of 3 | free | wrong experiment for it — see below |
| **preview (title + ids)** | **3 of 3, exact, 0 false** | free | pre-fetch; reaches unfetchable URLs |
| identifier (DOI/PMID/PMC) | 2 of 3 | free | catches what SimHash structurally cannot |
| SimHash on cleaned text | 1 of 3 | free | only 11 of 20 pages were long enough |

Three findings changed the design:

**1. Preview dedup belongs ahead of everything, and it is free.** Titles alone
grouped all three sets exactly, with no false clusters, before a byte was
fetched — 21 URLs down to 14. Four of the six URLs for one paper were
*unfetchable* (ResearchGate 403, LWW 403, Semantic Scholar empty); post-fetch
dedup can never see those, gate 0 handles them. Use **containment, not
Jaccard**: search engines truncate titles, so one side is routinely a stem of
the other, and a true pair scored Jaccard 0.33 against containment 1.00.

**2. SimHash cannot catch "same work, different rendering", and covers less of
the corpus than assumed.** PMC's copy of one paper is 3,193 words with
references; Ovid's is 2,088, truncated — distance 17, same document. And only
**11 of 20 fetched pages cleared the 150-shingle reliability floor**: the rest
were paywalled abstracts, block pages and stubs. This inverts the original
plan. SimHash covers the long-document minority; **embeddings are the primary
dedup path for roughly half the corpus**, not a cross-lingual special case.

**3. Identifiers are free and catch the case text comparison cannot.** The DOI
was sitting in the Ovid URL itself. Union-find across DOI / PMID / PMC merges
renderings of one work regardless of length. Run before any text comparison.

**What was not tested.** URL canonicalization caught nothing here, but this was
a cross-search result set — its value is repeat-crawl (tracking params, session
ids on re-fetch), which this experiment does not exercise. And per-result
snippets were unavailable from the search tool used, so only titles were
measured; snippets are the natural confirmation signal (below) and remain
unquantified.

**Fetch yield is worse than the status codes suggest: 10 of 21 pages (48%)
were not documents at all.** Only 5 of those 10 were 4xx. Springer returned
**HTTP 200** with "JavaScript is disabled in your browser"; PressReader
returned 200 and 10KB that clean to its own site name; PubMed returned **203**
with a cookie wall. A status-code check would have stored five walls as
sources — including ~33 words of "We've detected unusual activity from your
network" from each of the three ResearchGate URLs.

This is what `pagestate.py` (§*Layer 0*) exists for, and it sets the real Mode
A throughput expectation: **roughly half of what a search returns yields no
text**, before relevance is considered at all.

### Layer 0 — is this a document at all?

Runs on every fetch, before dedup. Three rules, in this order, because half
the walls returned 2xx:

1. **Wall phrases beat status** — JS, cookie, bot, forbidden, login and
   missing families, matched against the first 1200 characters only.
2. **Challenge fingerprints in raw markup** — Cloudflare `Ray ID` / `cf-chl`,
   PerimeterX, DataDome, Incapsula, reCAPTCHA. Deliberately narrow: a bare
   "cloudflare" appears on countless pages that serve fine.
3. **A refusing status**, then the shell rule — tiny text out of a large body.

**Word count never condemns a page.** It yields `thin`: real but not full
text, usable as a source, nothing to retry. Only a phrase, fingerprint or
refusing status yields `blocked`.

Two distinctions the detector has to carry:

- **`retryable` vs not.** A bot wall or JS shell may yield to a renderer, a
  delay or a different agent. A login wall or a 404 will not — the URL is
  still evidence the document exists, but the bytes are not coming.
- **Blocked is not rejected.** A wall says nothing about the *candidate*. Gate
  0 had already grouped three unfetchable URLs with the PMC copy of the same
  paper, and the content came from there. Drop the page, keep the candidate.

Measured: **10 of 10 non-documents caught, zero false positives**, all 11 real
documents passing. One honest limit, recorded as a test: an article whose lede
is *about* bot walls trips the phrase check. Rare here, and cheaper than
missing ten real walls.

### Layer 1 — preview, pre-fetch

Strip site chrome generically (` - PMC`, ` | Semantic Scholar`, ` : Indian
Journal of…`, a leading `(PDF)`, `…` truncation markers), take content tokens,
and group on containment ≥ 0.85.

**Containment alone is a blocking key, not a decision.** It merges "About us"
into "About us | Mine Labour Protection Campaign", and no minimum-token floor
separates that from the real truncation "Silicosis–An Ancient Disease" into its
full title — both are short prefixes. Batch IDF does not separate them either:
in a small candidate set a generic phrase looks rare. What works is testing the
shared tokens against a **common-word list**, since genericness is a property
of the language, not of the batch. So the layer returns a verdict:

- `merge` — a shared identifier, or containment on topic-bearing tokens.
- `confirm` — containment, but every shared token is boilerplate. Not merged;
  both are still fetched, and the fetch settles it.
- no signal — the title tokenizes to nothing ("About us"), which is different
  from evidence that needs confirming.

Treating `confirm` as a merge is how two different organisations with
boilerplate page titles become one actor.

### Layer 2 — links, pre-fetch, no model

**Links, pre-fetch, no model.** Canonicalize: lowercase host, strip `www`, drop `utm_*`/`fbclid`/`gclid`, drop fragment, sort query params, normalize trailing slash, collapse http/https, resolve shorteners and redirect chains. Store `url_canonical` + `url_hash`. Kills most re-fetching before it costs anything.

### Layer 3 — content

Exact hashing catches almost nothing — timestamps, session ids and rotating banners defeat it.

1. **Lexical near-dup — SimHash** (64-bit, Hamming ≤ 3) over normalized text. Catches the same press release syndicated across twenty sites. Cheap, deterministic, handles the bulk.
2. **Cross-lingual semantic dup — multilingual embeddings.** SimHash fails completely here: a Marathi article and its English translation share essentially no shingles. **The existing `all-MiniLM-L6-v2` also fails — it is English-only.**

   **Decided 2026-09-13: `multilingual-e5-small` for everything, one encoder, no English-only tier.** LaBSE (768-dim, ~1.8GB) is the better translation-pair finder — that is literally its training objective — but the choice is not between two dedup models, it is between one model and two. e5-small is **384-dim, the same as `all-MiniLM-L6-v2`**, so `EMBED_DIM` (`core/config.py:22`), the sqlite-vec column and everything downstream are unchanged, and `EMBED_MODEL` is already an env override (`core/config.py:21`). Running one encoder over the whole corpus from the start is worth more than a better score on a case that has not arrived yet, because the alternative is re-embedding everything at step 7 — and the corpus only grows.

   **The gotcha that will be silent if missed:** e5 models require a `query: ` or `passage: ` prefix on every input. Omitting it does not error; it degrades the vectors. This is a real difference from MiniLM, which takes bare text, so the port is not purely a config change.

   **The prefix marks role in the comparison, not type of text.** There are two valid pairings and a comparison must honour one of them end to end:

   | pairing | task | our uses |
   |---|---|---|
   | `(query, query)` | symmetric — the two sides are peers | content dedup (doc ↔ doc) · gate 1/2 relevance screen (problem `title + one_line` vs candidate `title + snippet`) · entity resolution |
   | `(query, passage)` | asymmetric retrieval — short query, long document | none yet |

   Mixing them — a `query:`-prefixed document against a `passage:`-prefixed one — produces uncalibrated cosines with no error. **Every embedding use the engine has today is symmetric**, including the relevance screen: a sentence against a sentence or two is peers, not MS MARCO's five words against five hundred. So `query: ` on both sides is the model card's own instruction for this class of task, not a shortcut past the prefix.

   **The asymmetric case is real but not yet ours.** Two things would introduce it: a keyword search over the cached corpus (the portal's search box), and Mode B matching a registry row's short name or one-line description against full documents. Both are genuinely short-query-against-long-document. **One stored vector commits to one pairing**, so either of those needs a *second* vector per document prefixed `passage: ` — 384 floats is ~1.5 KB, so the copy is cheap; it just should not be paid before there is a query side to spend it on. What is not an option is reusing the symmetric vector and hoping: that is the silent-miscalibration case above, one table row later.

   **Thresholds get measured here, not inherited.** e5 compresses similarity into a narrow high band — unrelated text still scores around 0.7 — so a cutoff lifted from a paper will be wrong in a way that looks like it is working. Same discipline that moved `MIN_SHINGLES` from a guessed 16 to a measured 150.

   Run SimHash first and embed only the survivors — but note finding 2 above:
   on real search output nearly half the pages never clear the SimHash floor at
   all, so the embedding pass carries more of this than originally scoped.

**The false-merge risk, and the cheap fix.** Semantic similarity is not duplication. Two different press releases about the same silicosis ruling embed very close but are distinct sources naming possibly different actors, and the repo's "when sources disagree, write the disagreement" standard depends on distinct sources staying distinct. Confirm a suspected translation pair with **number and proper-noun overlap** — figures, dates and transliterated org names survive translation nearly intact, and the check is language-independent and free. Same cosine *and* same numeric set → translation. Same cosine, different figures → two documents about one event; keep both. Only the ambiguous band needs an LLM compare.

**Link translations, don't delete them.** Store both, set `canonical_of`, keep `lang` on the row. A report existing in Marathi is itself evidence of local circulation and an affected-led audience — exactly the signal §6 is hunting. Discarding it as a duplicate throws away the thing you are looking for.

### Layer 4 — entities

**Embedding-first, or it dominates everything.** Built as "LLM-compare this candidate against existing actors," resolution is O(N) calls per candidate and at N = 3,000 exceeds the entire worker budget. Built as local vector search plus blocking heuristics (name normalization, registration number, domain), with an LLM only on the ambiguous band, it is ~2 calls per candidate regardless of N. This is the single biggest way to get the cost model wrong.

## 9. Admission control and the human

Candidates are not automatically admitted. Every emission is scored by tier 0–2 and written to `candidate`, admitted or not.

Admission rate *a* × branching factor *k* is the knob: `a·k < 1` and the frontier converges, `a·k > 1` and it grows. Neither is right in general — you want growth while sweeping a new population, bounded by the budget ledger rather than by convergence, and contraction while consolidating. **The un-admitted pool is not waste; it is counted, and the count is a denominator** the current method has never had for actor coverage.

Per-record review is arithmetically impossible, so judgment moves:

- **Policy** — budget allocation, which registries to sweep, admission thresholds, stopping conditions. Set deliberately, changed rarely, versioned in the run ledger.
- **Sample** — a fixed number of records a day, reviewed as a diff. This is the governance gate *and* the label set: reviewed decisions calibrate the tier-2 screen. Twenty human decisions a day calibrate a filter making ten thousand.
- **Escalation** — ambiguous merges, low-confidence high-impact writes, structural changes. Queued, not blocking.

This is where `00-architecture.md`'s *Pace tension* resolves. `CLAUDE.md`'s one-step-per-sitting rule is judgment per *record*, and that does not survive exponential fan-out. What survives, and is higher-leverage, is judgment per *class* of record.

## 10. Scope decision, 2026-09-12 — Mode B deferred

**Registry enumeration is not being built yet.** Everything else is. The consequence to hold in view: with no sweep, `gap: representation` stays unfalsifiable (§6) — the built system cannot distinguish "no actor exists at this unit" from "no actor reachable by edge-crawl," and Mode A alone scales the corpus *within* its existing connected component.

Build so Mode B drops in later as a **producer**, not a redesign:

- Keep `population` and `candidate` in the schema now, empty. Retrofitting a candidate pool later means rewriting the worker's emit step.
- **The worker's input is a `candidate` row, never a URL or a seed.** Mode A writes candidates; Mode B later writes candidates into the same table. One pipe, two producers.
- **Gate 1 takes a field map, not a snippet.** Mode A supplies title / snippet / URL path; a registry row supplies name / state / sector / registration id. Same interface, different mapping.
- **Tune gate 1 for recall regardless** — the constraint is independent of which producer is feeding it.

## 11. Build order

0. **DONE — tier 0 text primitives** (`engine/text/`, 44 tests, offline).
   `canonical.py` URL canonicalization + dedup key · `clean.py` boilerplate
   strip (trafilatura, stdlib fallback) · `simhash.py` near-dup with a
   *measured* 150-shingle reliability floor · `preview.py` gate 0 grouping with
   identifier extraction and the merge/confirm verdict · `pagestate.py`
   blocked/thin/shell detection (10 of 10 non-documents caught on the measured
   set, no false positives). Two calibrations came
   from tests, not judgement: the default-port rule was collapsing `:80` wrong,
   and `MIN_SHINGLES` was an order of magnitude too low (boilerplate moves a
   53-word document by 9 bits, a 150-word one by 1).

1. **DONE — schema + store + migration** (`engine/store/`, `engine/migrate/`, 116 tests).
   `schema.sql` 12 tables, 5 triggers, 3 views · `db.py` every write emits a
   field-level `event` · `tags.py` the registry, closed namespaces rejected at
   the write · `from_corpus.py` one direction, re-runnable, reads `problems/`
   and writes nothing back.
   **Migrated:** 36 needs → roots, 7 leaves → children, 6 nodes → 22 parent
   edges (multi-parent is why parentage is an edge), 2 cross-cutting axes,
   289 actors, 303 `works_on` edges, 104 actor↔actor edges, 655 channels,
   382 asks, 532 aliases, 89 sources from 91 citations, 894 events.
   53 problems, 525 edges, 285 tags in 1.0 MB.
   The estimate in this line was wrong on three of five counts before the
   migration corrected it — 7 leaves not 9, 6 nodes not 5, 289 actors not 291.
2. **Tier 1 embeddings** — port `core/encode.py`, store vectors with
   `sqlite-vec` (already a `slate_v2` dependency, so they live in the same file
   as the graph). Promoted by §8 finding 2 from "an optimization" to the
   primary dedup path for roughly half the corpus. Model settled 2026-09-13:
   `multilingual-e5-small`, 384-dim, one encoder for every language — see §8
   finding 2 for why, and for the `query: ` prefix it requires.
3. **Worker with all four gates + resolver.** Port `core/llm.py`. Two prompts, one loop. Replaces `process-leaf`, `actor-channel-finder`, `impact-network-crawler`.
4. **~~One registry, enumerated end to end~~ — DEFERRED (§10).** Its role, proving funnel economics on real data before a budget is pointed at it, moves to a labelled fixture set built from Mode A output plus known-hard positives.
5. **Scheduler + budget ledger.** Autonomy starts.
6. **Review surface** — sample queue, diff renderer, escalation inbox. Can lag step 5 slightly, not more.
7. **Cross-lingual dedup**, when the first non-English source arrives — local-language Mode A queries (§6) produce these without any registry. ~~Remaining registries~~ deferred.
8. **Bandit over problem-expansion**, if it earns its place.

Deferrable without truncating exploration: mechanism and cross-need-node promotion (a periodic query a person runs), writing quality beyond templates, and connection generation — dormant in `00-architecture.md`, still dormant here.

## 12. Open

- **Population access is unverified.** Every row in §6 is a hypothesis about access, rate limits, format and completeness. One must be proven end to end before the design is real; that is step 4.
- **Local throughput at gate 1** is a hardware question nobody has measured here. Batching 50 per prompt is the lever; if it doesn't hold, tier 3 and tier 4 absorb the overflow and the cost model shifts.
- **Gate 0's `confirm` band is unquantified.** The common-word test separates the cases we have, but the list is hand-made and the real confirmation signal — snippet overlap — was never measured, because the search tool used returns snippets only as a merged summary. First thing to check against a search API that returns them per result.
- **The 48% non-document rate is one sample on one topic.** Academic-publisher blocking may be unrepresentative of the NGO and news sources most of the corpus will draw on, in either direction.
- **The `thin` band is untested.** In the measured set every short page turned out to be a wall — 10 for 10 — so "real but short" has no real example behind it yet, and `MIN_DOCUMENT_WORDS = 120` is a guess rather than a measurement.
- **Retry is declared but not implemented.** `retryable` marks bot walls and JS shells as worth a renderer or a delay; nothing acts on it yet, and whether a headless renderer is worth its cost against a ~48% wall rate is unmeasured.
- **The `service` leg has zero actors.** Not one of 289 records carries it, against 176 enterprise, 72 institution and 51 activism. `CLAUDE.md` defines it as a first-class distinction — donor-funded direct delivery, no earned revenue — and holds that a hybrid carries both legs, one per revenue stream. Either the distinction is not being made when records are written, or it is real and 176 enterprise records absorb it silently. The coverage floor reports `service` missing on all seven researched leaves, which is the same fact wearing a different hat.
- **The two cross-cutting essays carry no frontmatter at all.** They migrated with a title and a doc path and nothing else — no classification, no gap, no sources. They predate the record schema and nothing since has forced the issue.
- ~~**Two leaf ids are referenced by an actor and have no file.**~~ Resolved 2026-09-13. `asbestos-import-legal` and `ambient-asbestos-demolition-dust` were merged into `asbestos-in-air` on 2026-09-09; `actor/gopal-krishna` was the last file still naming them, and its `leaves:` now points at the merged leaf. Both ids stay live as aliases. `validate()` returns empty, and the migration creates no stubs — the mechanism is now covered by a constructed test rather than by standing corpus debt.
- **Whether `graph.db` is committed, or only its `.dump`.** The file is 1.0 MB of binary and regenerates from the corpus in two seconds; the dump is readable in a diff. Not yet decided, and `.gitignore` does not mention it.
- **The A–E section invariant loses its hook** when the leaf type collapses. It survives as a validator rule keyed on `status: researched` — but deliberately, or it disappears quietly.
- **Whether classification tags are compulsory when researched.** As required enums they forced a judgment per leaf, and that forced choice is where the seven mechanisms came from. `required_when: status == researched` in the tag registry keeps the compulsion with none of the structure; probably right.
- **Where the tier files land** — root-problem bodies, or a separate prose layer the graph links to.
- **Calibration drift.** The sample review is both gate and training set, so a reviewer's changing standard silently retunes admission. Model pinning covers model drift, not human drift.
