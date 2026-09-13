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

**Corrected 2026-09-13, on the same labels.** The sentence above was a
hypothesis and tier 1 falsifies half of it. Run against these 21 fixtures, the
11 usable documents give 2 same-work pairs and 53 different-work pairs, and
they **overlap**: the lowest same-work pair scores 0.943 (04~06, the PMC/Ovid
renderings SimHash missed at distance 17 — so embeddings do see that case) and
the highest different-work pair scores 0.953 (13~16, two distinct articles
about one settlement). No cutoff catches both true pairs without merging the
pair `test_two_articles_on_one_event_stay_distinct` exists to keep apart. The
true pair is still ranked first overall, so the *ordering* is good and the
*decision* is not available from the vector alone. Embeddings are therefore a
**shortlist**, and the merge verdict stays with gate 0, identifiers and the
number/proper-noun check below. n=2 positive pairs is thin — but it is the
same evidence the original claim was made on, so it is at least as good. Pinned
as a failing-if-it-changes test (`test_embeddings_alone_do_not_separate_
same_work_from_same_topic`).

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

   **Measured 2026-09-13** over the whole store (`embed/calibrate.py`, 53 problems · 286 actors · 89 sources), the band is narrower than even that warning suggests:

   | population | p1 | p50 | p99 | max |
   |---|---|---|---|---|
   | problem × problem, all pairs (n=1,275) | 0.761 | 0.817 | 0.875 | 0.917 |
   | actor × actor, all pairs (n=40,755) | 0.795 | 0.841 | 0.897 | 0.971 |
   | full documents, all pairs (n=55) | 0.841 | 0.897 | — | 0.976 |

   Two unrelated actors sit at **0.841 median**. The entire usable range is roughly 0.76–0.98, so a threshold expressed to two decimals is a threshold with about twenty distinguishable settings, and the first decimal carries no information at all.

   **The gate-1 screen ranks well and thresholds badly**, and the distinction is the whole finding. Scored on the 292 `works_on` edges as positives against 20,000 random (actor, problem) pairs: **AUC 0.923**, but the means are only **+0.041** apart, and the positives' median (0.842) is indistinguishable from the actor-pair median above. The cutoff table says the rest:

   | cutoff | recall | kept |
   |---|---|---|
   | 0.80 | 98.6% | 50.1% |
   | 0.82 | 82.9% | 15.9% |
   | 0.84 | 53.4% | 3.3% |
   | 0.86 | 18.8% | 0.5% |

   There is no setting that is both safe and useful: 0.80 discards half the sweep and keeps almost every true pair, 0.84 discards the sweep and half the true pairs with it. **So gate 1 takes top-*k* per problem, not a global cutoff** — a per-query rank is exactly what an AUC of 0.923 with a 0.041 separation supports, and a global cutoff is exactly what it does not. A single number tuned on one sweep would not transfer to the next one.

   **Entity resolution must not be embedding-first as written.** §*Layer 4* below says "embedding-first, or it dominates everything". Measured on the 228 aliases that differ from their actor's title, cold-encoded and looked up: **rank-1 51.8%, top-5 75.4%**, and the cosine at rank 1 does not tell you which you got — 0.844 median when right, 0.815 when wrong. The existing `alias.norm` exact match is already correct on these. So the order is normalized-string match first, vectors as the *fallback shortlist* that feeds the LLM compare, and the LLM band is wide rather than narrow. Layer 4's cost argument survives intact — it is about avoiding O(N) LLM calls, and a top-5 shortlist at 75.4% does that — but "embedding-first" overstated what the vector decides.

   **Subtracting the common context was tried, and it costs more than it pays.** The obvious response to a 0.10-wide band is that every record shares a topic, so compare the residual: subtract the corpus mean, optionally remove the top-*d* principal directions (`all-but-the-top`), renormalize. Measured 2026-09-13 across all three tasks at once — `embed/calibrate.py --centre --drop N`:

   | | actor band p50 | spread (p99−p1) | gate-1 AUC | alias rank-1 |
   |---|---|---|---|---|
   | baseline | 0.841 | 0.102 | **0.9234** | **51.8%** |
   | centred | −0.004 | 0.492 | 0.9017 | 47.8% |
   | centred, drop top-1 | −0.009 | 0.442 | 0.8162 | 43.0% |
   | centred, drop top-4 | −0.007 | 0.373 | 0.6095 | 46.9% |
   | centred, drop top-12 | −0.005 | 0.325 | 0.5047 | 50.0% |

   It does everything it promises to the *numbers* — the band stops being a strip at 0.84 and spreads five-fold across zero — and every actual answer gets worse, monotonically. **The common component is not noise; it is the topic, and the topic is a third of what `works_on` means.** Two actors both working Indian environmental health share that because it is true. Strip it and the residual is dominated by genre — funder blurb versus field-org blurb — which is not the question being asked.

   Tested again on the single-topic fixture set, which is the strongest case for the idea because there the shared component really is just "silicosis in Rajasthan": still no separation at any setting, and the true pairs fall from ranks 1 and 4 to 32 and 54 by `drop top-3`. Plain centring happened to preserve the ranking there and still did not separate — **because the overlap is an ordering failure, not a calibration one.** 13~16 genuinely sits closer in this space than 04~06 does, and no rescaling of an axis changes which pair is nearer.

   Which is the argument for top-*k* restated from the other side: reading ranks instead of absolutes is invariant to every rescaling, so it gets the benefit this transform was reaching for without paying the rotation. **The version of the instinct that does work is subtracting the common context in the text, not in the vector** — and that is already the design: the number and proper-noun overlap check below is exactly a residual comparison, run in a discrete space where the residual discriminates instead of dissolving.

   **The nearest-neighbour tail is relationships, not duplicates.** The top actor pairs are `aavishkaar-group ~ intellecap` (0.971), `icmr-nioh ~ icmr-niv` (0.970), `ajaita-shah ~ frontier-markets` (0.964), `indus-action ~ tarun-cherukuri` (0.961). Not one is a duplicate: they are parent/subsidiary, sibling institutes, and founder/organisation — every one of them already an edge in the graph. A dedup pass that trusted rank order would destroy exactly the structure the engine exists to record. **Pairs that already carry an edge must be excluded from dedup candidacy before scoring**, and `prayas-goel ~ prerak-goel` (0.954, two different people with near-identical names) is the reminder that the name channel is not safe on its own either.

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
2. **DONE — tier 1 embeddings** (`engine/embed/`, 48 tests, 173 in the suite).
   `model.py` the encoder, with the e5 prefix as an enforced contract rather
   than a convention — `role` is keyword-only, and empty or already-prefixed
   text raises · `index.py` `vec0` tables inside `graph.db`, keyed
   `"{role}:{id}"` with `role` a partition key, plus an `embedding` table
   carrying `model` + `text_hash` so backfill is incremental and a model swap
   is detectable instead of silently mixing two vector spaces · `texts.py` what
   text stands for an entity, in its own module because it is a judgement and
   not a port · `backfill.py` one direction, re-runnable · `calibrate.py` the
   measurement, because a threshold is not allowed to be inherited.
   **Indexed:** 51 problems, 286 actors (3 `excluded` skipped), 89 sources —
   426 vectors, 1.0 MB → 5.9 MB. Warm throughput ~66 records/s; the whole
   corpus re-embeds in about eight seconds.
   **What the measurement changed** (§8): the "primary dedup path" claim is
   half wrong — embeddings rank well and decide badly, so they are a shortlist
   and the merge verdict stays at gate 0; gate 1 takes top-*k* per problem
   rather than a global cutoff; and "embedding-first" entity resolution is
   demoted to a fallback behind the existing `alias.norm` exact match.
   **The store went stale under us, and nothing was watching.** `problems/graph.db`
   was migrated 45 minutes before the migration code was finalised, so it carried
   two problems the corpus had already retired — and a whole session of vectors,
   an all-pairs sweep and a set of reported thresholds were built on it before
   anyone re-ran anything. Every headline number survived (AUC 0.9242 → 0.9234,
   the actor band and alias resolution unchanged); one reported dedup candidate
   did not, being a pair of phantoms. The fix is not the re-migration, it is
   `embed/guard.py`: the migration now stamps `meta.corpus_fingerprint` — content
   hashes over the 359 files it reads, so a checkout that moves every mtime says
   nothing — and `backfill` and `calibrate` refuse to run against a store that
   does not match, or that carries no stamp at all, which is the case that
   actually occurred. `--stale-ok` makes measuring an old store a choice rather
   than an accident. `validate()` now returns clean for the first time.
   **A cold review caught eight real defects**, and the two that mattered were
   both invisible from inside: `put` was two writes, so a rejected vector left a
   bookkeeping row claiming the entity was current — `stale` said no, `knn`
   returned nothing, permanently; and `backfill` never dropped, so an actor set
   to `depth: excluded` kept answering kNN and a source given a `canonical_of`
   stayed in the index beside its own survivor, which is the exact failure the
   index exists to prevent. Both are now one savepoint and a `prune` pass, with
   a regression test each. The other six: a role typo that wrote half a row, a
   char budget (2,000) against a token limit (512) that silently dropped ~16% of
   every long Devanagari record, an AUC that scored ties as losses, a rejection
   sampler that hung when there were no negatives to find, an `n²` dense
   `nearest` (~28 GB at 50k), and a blank problem that embedded as `query: .`.
   **The interpreter moved**, which was not optional: the python.org macOS
   3.11 build compiles `sqlite3` with `SQLITE_OMIT_LOAD_EXTENSION`, so
   `sqlite-vec` could never have loaded on the old venv. Homebrew's 3.12.13
   has it — the same interpreter `slate_v2` runs on. `requirements.txt` carries
   the one-line check, because this fails at import in a way that reads like a
   packaging problem.
   **A second review, after the guard**, caught five more, of which three were
   real costs already being paid. `plan()` token-fitted every row before
   checking its hash, so the documented cheap case — a re-run with nothing
   changed — loaded a 470 MB model to conclude it had nothing to do: 21.6s for
   what is now 0.30s, fixed by keying `text_hash` on the text before truncation
   (sound, because truncation is a pure function of text and tokenizer, and the
   tokenizer moves only with `model`, which `stale` already compares). The
   fingerprint glob was 18 files wider than what the migration actually reads,
   and one of the 18 was `follow-list.md`, which `npm run follow` regenerates
   inside every build — so a routine build would have made the store look stale,
   and a guard that cries wolf is answered with `--stale-ok` until it means
   nothing; `corpus_files` now mirrors the reader (the needs registry names the
   tier files, `CROSS_CUTTING` names the axis essays), and the test guarding it
   instruments a real migration and fails if the two sets differ **in either
   direction**, because under-coverage is the worse failure and a hand-kept glob
   drifts toward both. The two CLIs had disagreed about whether a bare run meant
   `engine/` or the repo root, which is a wrong-store bug wearing a
   working-command costume; the store flags and the freshness check are now one
   shared helper, so a tool cannot accept `--stale-ok` and forget to check it.
   The fifth was latent: `fit` sliced the joint tokenization and dropped
   `len(tokenize(prefix))` tokens off the front, which assumes a sub-word
   tokenizer cannot merge across the prefix boundary — it can, and the result is
   a record quietly embedded starting mid-word. It now binary-searches the body,
   measuring the whole prefixed string, which is the only length the model sees.
   **0 of 426 records currently reach the limit**, so nothing measured moved —
   every figure in §8 reproduced exactly. The 2,000-char clip is what keeps it
   at zero, and only in English.
3. **Worker with all four gates + resolver.** Port `core/llm.py`. Two prompts, one loop. Replaces `process-leaf`, `actor-channel-finder`, `impact-network-crawler`.
   **DONE, first pass** (`engine/worker/`, 31 tests) — gate0 preview dedup, gate1
   batched screen, fetch, gate2 confirm, claims extraction, resolve, write,
   emit, all wired into one loop (`worker.run_batch`). `llm.py` lifts the
   provider fallback chain from `../slate_v2` per §7.
   **Two gaps found on a live sweep, 2026-09-13, not yet closed:**
   - **Channel discovery is not actually replaced.** The claim above overstates
     what got built: claims extraction on one fetched page finds a channel
     only if the model happens to restate one in the body text. Live test —
     RESET Air (`reset.build/standard/air`), GBCI/USGBC LEED Arc
     (`arc.gbci.org/arc-leed`), GMDA (`gmda.gov.in`) — wrote zero `channel`
     rows across all three; none of the three landing pages mention a social
     handle or contact link in their body text, and GMDA's fetch pulled nav
     chrome, not content. `actor-channel-finder`'s actual method (hunt across
     several pages — about/contact, social platforms — ranked by which
     actually update) is a distinct step from "extract claims from whatever
     page gate1 admitted," not a side-effect of it. Worse: not even the
     candidate's OWN seed URL — a known-good website for the entity by
     construction — gets written as `channel:website` automatically; nothing
     in `worker.py` does this, it's claims-extraction-or-nothing. Needed: (a)
     auto-write the fetched URL as a `channel:website` claim unconditionally
     on a confirmed actor fetch, free and zero-risk; (b) a real
     channel-discovery step for actors — a dedicated pass or prompt that
     hunts rather than incidentally extracts, closer to what
     `actor-channel-finder` already does by hand. Neither exists yet; this
     line's "replaces actor-channel-finder" is aspirational until they do.
   - **`doc` (prose) is never written.** §4's "Writing Agent is a step" implied
     this was accounted for; only two prompts got built (screen, extract), and
     `prompts.py`'s extraction prompt explicitly forbids prose as a claim
     value ("a claim graph that stores paragraphs is a second corpus with no
     schema"). So every worker-written record — new or enriched — has
     `doc IS NULL` forever, by construction, with no path to a filled-in page
     body. A third pass (or a deliberate decision that prose stays
     human-written) is still open.
3b. **Portal cutover — the corpus stops being parsed twice.** Numbered out of
   band because it is parallel to step 3, not after it, and because §10 already
   refers to step 4 by number. Today `src/lib/corpus.mjs` parses the same
   markdown the migration parses, `scripts/build-index.mjs` emits a second
   database, and the two loaders can disagree — which is exactly what item 1
   above looks like from the outside. Two phases, and the first does not wait
   for the worker:
   - **A — DONE 2026-09-13, the portal reads `graph.db`.** `build-index.mjs` and
     the frontmatter half of `corpus.mjs` are replaced by queries (new
     `src/lib/graphdb.mjs`); `node:sqlite`'s `DatabaseSync`, already in use at
     `scripts/build-index.mjs:13`, is the only thing either file opens the
     store with, so no new dependency. Prose stays on disk and is read through
     `doc` — `sections.mjs`'s `parseSections`/`parseTierFile` are unchanged and
     still run at portal-build time. `build-index.mjs` now regenerates
     `graph.db` fresh (`from_corpus.py --force`) at the top of every
     `npm run index` / `validate` / `build`, rather than trusting a checked-in
     file that could drift from the corpus on disk. Verified: `npm run build`
     emits the same 400 pages: `36 needs · 7 leaves · 6 nodes · 289 actors`
     match build-order step 1's migration counts exactly, and `npm run
     validate`'s punch list is unchanged except for 4 warnings that moved
     leg (§12). The A–E section invariant is NOT lost — `sectionIssues` still
     runs on every leaf/node/actor's parsed body, unchanged, because prose
     parsing never moved. Three debts accepted rather than closed — detailed
     in §12, not vanished quietly.
   - **B — DONE 2026-09-13, the db is the source.** `graph.db` is now durable
     and committed (§12, reversing the 3b-A decision), not regenerated on
     build — `build-index.mjs`'s `--force` call is gone, so nothing can
     silently overwrite a worker or human write with stale frontmatter.
     `from_corpus.py` ran one final time against the frontmatter-bearing
     corpus, then all 302 frontmatter blocks (7 leaves, 6 nodes, 289 actors —
     the 36 need tier-files and 2 cross-cutting essays never carried
     frontmatter) were stripped, leaving markdown as pure prose read through
     `doc`, unchanged from 3b-A's `readBody`, which already tolerated a
     frontmatter-less file. "Where tier-file bodies live" (§12) resolved as
     the status quo — `doc` already pointed the DB row at its file — so
     nothing moved there. The open half of that question was the write path,
     not the read path: a human write now goes through `engine/store/edit.py`
     (new), the same `db.put`/`tag`/`alias`/`link` primitives `worker.py`'s
     `_write_entity` already used — one write path, both audited in `event`.
     Two more direct-frontmatter writers surfaced and were ported the same
     way: `scripts/follow-list.mjs` (now calls `loadCorpus()` instead of its
     own frontmatter scan) and `astro.config.mjs`'s dev-only `/api/follow` +
     `/api/exclude` routes (now write `graph.db` via `setActorFields`, and
     restore a pre-exclude `depth` from the `event` log instead of a
     markdown comment). `engine/tests/test_migrate.py`'s 14
     live-corpus-dependent assertions now correctly skip — they test
     `from_corpus.py` against a corpus that no longer has frontmatter to
     migrate, and asserting on that is not this phase's job; a frozen
     pre-strip fixture snapshot is unstarted (§12).
3c. **Actor channel discovery — a real step, not a side-effect of extraction.**
   Numbered out of band, same reason as 3b: it corrects step 3's own claim to
   "replace `actor-channel-finder`," which live-sweep testing (2026-09-13, §12)
   showed is not yet true. Two parts:
   - Auto-write the candidate's own fetched URL as `channel:website` on any
     confirmed actor fetch (gate2 `confirmed`), unconditionally — it is free,
     always true by construction, and today it doesn't happen at all unless
     the model happens to restate the URL in the page body.
   - A dedicated channel-discovery pass for actors: hunt across an entity's
     likely pages (about/contact, known social platforms) and rank what
     actually updates, the way `actor-channel-finder` does by hand — not a
     one-shot claims extraction off whatever single page gate1 admitted. Live
     test: RESET Air, GBCI/USGBC LEED Arc and GMDA each got a real fetch and
     confirmed gate2, and all three still wrote zero `channel` rows, because
     none of the three landing pages restate a handle or contact link in body
     text.
3d. **A writing pass — `doc` is currently never written.** Numbered out of
   band, same reason as 3b/3c. §4 lists "Writing Agent is a step" as if
   accounted for; only two prompts were built (gate1 screen, claims extract),
   and the claims prompt explicitly forbids prose as a claim value. Every
   worker-written record — new or enriched — therefore has `doc IS NULL`
   permanently, with no path to a filled-in page body, unless either this pass
   gets built or the corpus deliberately keeps prose human-written and says so.
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
- ~~**Decided 2026-09-13: `graph.db` is not committed.**~~ Reversed 2026-09-13, same day, by 3b-B: once corpus markdown lost its frontmatter it stopped being derivable from `problems/` at all, so "regenerates in two seconds" no longer holds — the WAL/SHM files stay gitignored, the DB itself is committed. `sqlite3 problems/graph.db .dump` is still how you get a readable diff of it.
- **Every vector in the store is of short text.** Problems average 145 characters, actors 459, sources 116 — the last because no source has been fetched yet, so 89 of 89 are title + org + year. The §8 bands are therefore bands *for short text*, which embeds into a tighter cone than documents do. The full-document measurement on the fixtures is narrower still, so the direction holds, but neither number should be quoted at a document-scale corpus without re-measuring.
- **`texts.py` is the least-tested judgement in tier 1.** What text stands for an entity determines every cosine downstream, and the rules — title + one_line for a problem, title + lead paragraph for an actor, front-truncation at 2,000 characters — were chosen from the shape of the comparison, not measured against an alternative. Embedding an actor's full record instead of its lead is a one-line change and nobody knows which is better.
- **`--centre` has no query-side transform.** The alias half of the sweep is deliberately left untransformed, so `--centre` measures a residual index against untouched queries. Fine for the rejection it recorded, wrong for any future attempt — the query would have to be projected through the same basis, which means storing the basis.
- **`calibrate` uses numpy, not `vec0`, and that is only true of sqlite-vec 0.1.9.** Measured: `vec0` has no ANN index in 0.1.9 — query time is linear in row count (0.30 ms at n=2,000, 1.17 ms at n=8,000) — so an all-pairs sweep is O(n²) either way, and numpy does it ~13× faster (12,000 entities: 1.5 s against 19.9 s) because it is one BLAS call per chunk instead of n SQL statements with per-row deserialization. Same answers, verified. **The day sqlite-vec ships an ANN index this flips**, because `nearest` becomes sub-quadratic through the index while numpy stays quadratic — so it is a revisit condition, not a settled choice. The band percentiles never move: they need the whole distribution, including the far tail, which is not a kNN question.
- **Nothing yet consumes a vector.** The index exists, is measured and is correct; the gates that would read it are step 3. Until then the vectors are 5.9 MB of unexercised state, and the top-*k* decision above is a design conclusion rather than a running one.
- **The A–E section invariant loses its hook** when the leaf type collapses. It survives as a validator rule keyed on `status: researched` — but deliberately, or it disappears quietly.
- **Whether classification tags are compulsory when researched.** As required enums they forced a judgment per leaf, and that forced choice is where the seven mechanisms came from. `required_when: status == researched` in the tag registry keeps the compulsion with none of the structure; probably right.
- ~~**Where the tier files land**~~ Resolved 2026-09-13 by 3b-B: root-problem bodies, unchanged — `doc` already pointed the DB row at the file, this just stopped being ambiguous once the alternative (a human write path bypassing the worker's DB writes) was decided against. See item 3b-B.
- **Calibration drift.** The sample review is both gate and training set, so a reviewer's changing standard silently retunes admission. Model pinning covers model drift, not human drift.
- **Phase 3b-A shipped 2026-09-13 with three named debts, accepted rather than closed.** `src/lib/corpus.mjs` now queries `problems/graph.db` instead of re-parsing frontmatter; `scripts/build-index.mjs` regenerates it fresh (via `from_corpus.py --force`) on every `npm run index`/`validate`/`build`, so the second parser is gone. What didn't come with it: (1) **frontmatter shape validation** — `src/lib/schema.mjs`'s Zod schemas are unwired (kept, unused, for the eventual port into the migration); a malformed field is now only whatever `from_corpus.py`'s non-fatal `report.note()` catches, which is weaker — measured concretely: `npm run validate` lost 4 "dangling actor (affiliation) ref" warnings because `resolve_deferred()` drops an edge to a nonexistent actor silently rather than the portal seeing the dangling reference. (2) **`problems/private/connections`** isn't migrated into `graph.db` at all and is no longer loaded by any path (dropped, not file-parsed) — `corpus.mjs`'s `connections` is always `[]`, and the scoreboard's connection counts read zero until a connection migration exists. (3) Two small **migration gaps closed in passing** rather than left broken: node `authority`/`sub_levers` and leaf `gap_as_of`/`last_reviewed` had no column or tag at all before this phase (nodes and the staleness check (assertion 9) would have silently gone blank) — added as four open `problem`-scoped tag namespaces in `engine/store/tags.py` and populated in `from_corpus.py`.
- **Phase 3b-B shipped 2026-09-13** (see item 3b-B). Debts it inherits or adds, not closed: (1) **frontmatter shape validation** (3b-A's debt above) is now more final, not less — with frontmatter gone entirely, porting `schema.mjs`'s Zod schemas "into the migration" means writing them against `engine/store/edit.py`'s write path instead, since that migration only ever runs once more on a future corpus import. `schema.mjs` stays unused, historical documentation of the field shapes. (2) **`problems/private/connections`** is now permanently dropped, not just phase-A-deferred — there is no markdown-frontmatter path left to revive, so a connections migration means designing new `edit.py`/`worker.py` write support from scratch, not finishing a partial one. (3) **`engine/tests/test_migrate.py`'s 14 corpus-dependent tests are skipped**, not deleted — they assert real counts/shapes against `problems/`, which no longer has frontmatter to produce them. A frozen pre-2026-09-13 fixture snapshot (a handful of representative leaf/node/actor files, frontmatter intact, checked into `engine/tests/fixtures/`) would let them run again against something other than the live corpus. (4) **No tooling ports `problems/actors/_excluded.yaml`'s dedupe check or `impact-network-crawler`'s frontmatter-reading habits** — that agent (and `actor-channel-finder`) may still assume actor records are markdown-with-frontmatter; unverified this session, out of scope, worth checking before the next crawl.
- **The worker does not discover actor channels — it only extracts what a fetched page happens to restate.** Found live 2026-09-13, item 3 above has the full account. Two concrete fixes named there and still open: auto-write the fetched URL itself as `channel:website` on any confirmed actor fetch (free, always true, never done today), and a real hunt-across-several-pages channel-discovery step for actors, closer to what `actor-channel-finder` already does by hand than to one-shot claims extraction off whatever gate1 admitted.
- **The worker never writes `doc`.** Found live 2026-09-13, item 3 above. `prompts.py`'s extraction prompt deliberately forbids prose as a claim value, and no third "writing" pass was ever built to fill it in some other way — every worker-written record has an empty page body, permanently, until this is either built or the corpus accepts that `doc` stays human-written.
