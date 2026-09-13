# The worker — search-first research on one candidate

Third engine doc. `01-minimal.md` is the pipeline skeleton (gates, fetch,
resolve, write). `02-questions.md` is the field set — *what* a `problem` or
`actor` record must answer. This is *how* one candidate gets answered.

Written 2026-09-13, replacing the reverted dive loop. The dive walked
same-domain outlinks from a seed URL and spent five LLM calls doing it; its
ceiling was source diversity, not passes. This design leads with search,
selects sources by predicted question coverage, selects *paragraphs* by local
embedding, and spends one LLM call on what survives.

Two standing constraints from `01-minimal.md` carry over unchanged: gate 1 is
tuned for recall (nothing recovers a candidate discarded there), and every
claim is one field, one value, one confidence — never a prose blob.

---

## 1. The unit and the shape

**Unit of work: one candidate.** In, a `candidate` row (`kind`, `name`,
optional `url`, `evidence`). Out, a written entity plus its findings, emits and
edges — the same `{"claims", "emits", "edges"}` contract `run_batch` already
writes, so nothing downstream of extraction changes.

```
candidate
   │
   ├─ 0  intake            depth tier: registry (cheap) or tracked (full)
   ├─ 1  query planning    open questions → 4-8 query families
   ├─ 2  search            parallel, one query per thread          [$ external]
   ├─ 3  fuse + select     RRF over ranks, then greedy set cover
   ├─ 4  fetch + confirm   HTTP, clean, gate 2 per source          [free]
   ├─ 5  passage retrieval e5 query:/passage:, top-k per question  [free, local]
   ├─ 6  extract           ONE call over selected passages         [$ model]
   ├─ 7  ledger            finding rows, then claims
   └─ 8  emit              candidates + edges, problems included
```

Stages 2 and 6 are the only ones that cost money. Everything between them
exists to make stage 6 read less and answer more.

---

## 2. Stage 0 — intake and the depth tier

**Not every candidate deserves the full pipeline.** This is `process-leaf`'s
rule, ported: *"one-file-per-actor at full depth does not survive the volume: a
consumer-purifier vendor mentioned in passing costs the same as an affected-led
org you intend to introduce to someone"* (`process-leaf/SKILL.md`). It also
forbids the expensive step for the cheap tier outright — *"Don't dispatch
[`actor-channel-finder`] for a `depth: registry` actor cited once in a table."*

Two tiers, decided at intake, before any spend:

| | `registry` | `tracked` |
|---|---|---|
| Share of candidates | most | the minority worth the money |
| Questions asked | identity subset (~7) | the full set (`02-questions.md`) |
| Queries issued | **1** — the identity family, always, even with a URL | 4–8 |
| Sources read | the seed, or one search hit | 3–5 |
| Extraction calls | 1 | 1 |

A `registry` candidate gets one search rather than none even when it arrives
with a URL. The URL a candidate was emitted with is whatever page happened to
name it — a directory row, a co-signatory list — and is frequently not the
entity's own site. One identity query costs nothing on a self-hosted index and
is often the only way the real homepage is found at all.

Tier is a **prediction** at intake and a **verdict** after extraction. Predict
from what the candidate row already carries — the emitting context, the hint,
the URL's shape. Then, once `affected_led`, `representation_unit` and `legs`
are extracted, apply the ground test properly (`CLAUDE.md` → Actor tracking:
affected-led/local collectives, field enterprises that deploy or service the
remedy, local regulators actually acting; academics, ministers, courts,
commissions and national advocacy shops stay `registry` however influential).
A candidate that comes back looking `tracked` after a `registry` pass is
**requeued for a full pass** — cheaper than running everything at full depth to
avoid ever being wrong.

Escalation is one-way and logged. A `registry` record that never escalates is
a finished record, not a stub.

---

## 3. Stage 1 — query planning

### The rule: never one query per question

19 problem questions × one query each is the cost centre this design would
otherwise create, and most of those queries would return the same pages.
Questions collapse into **query families** — sets a single search resolves.
Target 4–8 families per candidate, not 16–19 queries.

### Actor families

| Family | Questions it aims at | Query shape |
|---|---|---|
| identity | `one_line`, `type`, `legs`, `geography` | `"<name>"` |
| money | `funding`, `scale_metric`, `lifecycle` | `"<name>" funding raised grant crore` |
| people | `affected_led`, `representation_unit`, founders | `"<name>" founder director leadership` |
| viability | `tag:viability_note`, `legs` | `"<name>" revenue customers model` |
| failure | `tag:failure_note`, `lifecycle` | `"<name>" shut down closed pivot losses` |
| reach | `contact_route`, `channel:*` | `"<name>" contact twitter newsletter` |
| asks | `ask:need:*`, `ask:offer:*` | `"<name>" partnership hiring seeking support` |

### Problem families

A problem candidate has **no proper noun to anchor on** — the name *is* the
failure ("silicosis in stone quarries"). Query planning is therefore a
different job, not the actor planner with a different string.

| Family | Questions it aims at | Query shape |
|---|---|---|
| magnitude | `tag:magnitude`, `tag:measurement_state` | `<failure> India number of workers affected estimate` |
| who is hit | `tag:differential_vulnerability`, `geography` | `<failure> India who is affected caste migrant informal` |
| counting | `tag:measurement_state` | `<failure> India surveillance registry data absent` |
| remedy blocked | `tag:blocker`, `tag:mechanism` | `<failure> India rules notified not implemented` |
| who works it | `who_works_it`, `tag:gap_*` | `<failure> India NGO union campaign petition` |
| enterprise | `who_works_it`, `needs_legs` | `<constraint as a spec>` — see below |
| institution | `tag:representation_verdict` | `<failure> India board scheme compensation fund` |

The **enterprise family is seeded with the binding constraint stated as a
spec**, not with the failure name — `process-leaf` §D: *"non-asbestos roofing
at AC-sheet price"*, *"sub-₹500 wet-cutting rig for informal quarries"*,
*"point-of-care blood-lead test under ₹100"*. The stock verdict "structurally
absent, the harmed can't pay" has been written from the armchair more than
once. It is the one family whose query the model should compose rather than a
template fill.

### Learning the templates

Query framing improves with iteration, but **not per candidate at runtime** —
that is where this design would quietly become expensive. Learn it once, per
`(kind, family)`, offline, and store the winning template. This is already the
plan: `00-architecture.md:83` specifies *"query-template generation per arm →
bandit arm-selection (delegated to the Orchestrator, not reimplemented here)"*.
The worker consumes templates; it does not tune them.

Reward signal for the bandit: **realised coverage** — how many of the family's
questions the extraction actually answered from sources that query surfaced.
Not click-through, not result count. A run whose `unresponsive_engines` rate
breached the §4 floor is **excluded from the reward**: a template that scored
badly because Google was blocking us has not been shown to be a bad template.

### Where templates live

Split by mutability, following the pattern the repo already uses for
`problems/data-model.yaml` → `problems/index.db` (YAML is the source of truth,
the database is derived and mutable):

- **`engine/search/families.yaml`** — the definitions. One entry per
  `(kind, family)`: `id`, the question ids it targets, one or more query
  templates with `{name}` / `{failure}` / `{constraint}` slots, and
  `enabled`. Git-tracked, diffable, reviewable — a query template is a research
  decision and belongs in version control, not in a table nobody reads.
- **`query_template` / `template_trial` tables in `graph.db`** — the runtime
  stats the bandit writes: trials, realised coverage, last-used, current arm
  weights, keyed by the YAML `id`. Mutable, per-run, never hand-edited.

The worker **reads both and writes neither**: it resolves a family to its
current best template and records the trial. Tuning is the Orchestrator's
(`00-architecture.md:83`). A template id that appears in the database but not
in the YAML is a stale arm and is ignored, not resurrected — same rule as an
unrecognised claim field.

`engine/search/` is also the natural home for stages 1–3 generally: the
provider adapters (`providers/searxng.py` and whatever follows), query planning,
and the fusion + set-cover code. Nothing in there touches the model.

---

## 4. Stage 2 — search

**Provider: self-hosted SearXNG** (decision recorded in §14, pending the spike
in §16 step 0). One thread per query family, issued in parallel.

The worker treats search as an interface returning
`[(rank, url, title, snippet, native_score?)]` per query, so the provider is a
swappable adapter and stages 3–8 never learn which one ran.

Cap: `max_results` ≈ 10 per query. Beyond that RRF contributes noise.

Record every query issued and its result list against the candidate. Without
that, the bandit has nothing to learn from and a re-run cannot be diffed.

### SearXNG specifics

`GET /search?q=…&format=json`. `json` must be enabled under `search.formats` in
`settings.yml` or the request 403s — which is why most public instances refuse
it, and why this must be self-hosted rather than borrowed.

Each result carries `url`, `title`, `content` (snippet), `publishedDate`, plus
`engines`, `positions` (its rank in each engine) and `score`.

**Fuse on `score`, never on the JSON list index.** `get_ordered_results`
(`searx/results.py:191`) sorts by score and *then* runs a second pass that
regroups by category and template (`max_count = 8`, `max_distance = 20`), so
list position is deliberately not score order. Taking `rank = index` would feed
a display heuristic into stage 3's fusion.

### Deployment and sizing

Stateless: no index, no crawler, no database, nothing retained between queries.
Disk is the container image. Optional Valkey/Redis exists only for the inbound
limiter, which is off for a localhost-only caller — so one container, not two.

Cost is outbound fan-out and lxml parsing, per query. Shipped defaults
(`searx/settings.yml`): `request_timeout: 3.0`, `pool_connections: 100`,
`enable_http2: true`. Engines are queried in parallel, so wall-clock per query
is the slowest engine, not the sum.

**Cut the enabled engine set to ~5** (Google, Bing, DDG, Brave, Startpage) out
of the 347 defined. That cuts CPU, wall-clock and — the part that matters —
blocking exposure, roughly proportionally. Read the live set off `/config`
rather than counting the YAML; list-form `categories:` makes it easy to
miscount.

Resource draw is a rounding error next to the LLM calls: one small always-on
container, comfortably inside a core.

### The operational tax: upstream blocking

The real risk is not resources — it is that SearXNG scrapes engines that
rate-limit and block, and **its degradation is quiet**. `ban_time_on_fail: 5`
escalating to `max_ban_time_on_fail: 120` auto-suspends an erroring engine.
That is self-healing for a human user and a silent failure mode for a batch
worker: engines drop out, results thin, and nothing notices.

Two obligations follow, and neither is optional:

1. **Throttle and jitter the worker's query rate.** Six families × hundreds of
   candidates × five engines is a few thousand outbound requests per run from
   one IP. That burst shape is what bot detection exists to catch. If throttling
   is not enough, `outgoing.proxies` and `outgoing.source_ips` are both
   first-class in `settings.yml`.
2. **Read `unresponsive_engines` from every JSON response and record it against
   the query.** A family that returned nothing *because Google blocked us* is a
   different finding from one that returned nothing *because nothing exists*.
   Conflating them corrupts the §3 bandit — it will drop a good query template
   or keep a bad one on the strength of a blocking event. A run whose
   unresponsive rate climbs past a floor should raise an operational alarm, not
   quietly produce thin records.

### Licensing

AGPL-3.0. The network clause binds *modified* versions that users interact with
over a network. Unmodified SearXNG as an internal build-time service, never
exposed to portal visitors, carries no obligation. `settings.yml` configuration
is not modification. What would change this: patching SearXNG's own source
**and** exposing the instance publicly.

---

## 5. Stage 3 — fuse, then cover

Two distinct steps. Conflating them is the trap.

### 5a. Fusion — Reciprocal Rank Fusion

```
score(url) = Σ over queries q that returned it:  1 / (k + rank_q(url))     k = 60
```

RRF is rank-only, so it needs no score normalisation across heterogeneous
queries — which is fortunate, because search APIs don't expose comparable
scores anyway. Dedupe by canonical URL first (`text/canonical.py`), so
`?utm_source=` variants fuse into one row rather than splitting a URL's rank
mass across duplicates.

Alongside the score, keep the **coverage set**: which query families returned
this URL, at what rank. That set, not the score, drives selection.

### 5b. Selection — greedy set cover, not top-n

Top-n by RRF is the wrong pick and it fails in a specific, predictable way: the
organisation's own homepage ranks for every query, so the top 5 are often five
pages covering the same three families. What you want is the smallest set of
links whose coverage sets **union** to everything covered.

```
selected = []
uncovered = set(families that returned any result)
while uncovered and len(selected) < MAX_SOURCES:
    pick the url maximising |coverage(url) ∩ uncovered|,
      tie-broken by RRF score
    if it adds nothing, stop
    selected.append(url); uncovered -= coverage(url)
```

`MAX_SOURCES` = 1 for `registry`, 3–5 for `tracked`.

**Coverage here is predicted, not proven.** A URL ranking for the money query
is not evidence it names a funder — see §6 on why the same caveat applies again
one stage down. Realised coverage is only known after stage 6, and it is what
gates a second iteration (§11) and what the bandit learns from.

A family that returned nothing stays uncovered and simply never gets answered.
That is a legitimate outcome and `02-questions.md`'s rule holds: absence is
recorded, never guessed at.

---

## 6. Stage 4 — fetch and confirm

Unchanged from `worker/fetch.py`: canonicalize → cache check → GET → `clean` →
`assess` → upsert `source`. Fetches are HTTP, not model calls; they are free
and parallelisable, and they never consume the LLM budget.

**Run gate 2 on every source, not just the seed.** Today `worker.py:395` only
confirms the candidate's own URL. `gate2.confirm` is local embeddings — free —
and a search hit is exactly the case where a wrong-entity page (a namesake, a
directory listing, a different org with a similar name) gets through. Same
three-way verdict: `mismatch` drops the source, `uncertain` keeps it and logs,
`confirmed` proceeds.

A `mismatch` drops that source only, never the candidate — the candidate has
other sources, which is the point of searching.

---

## 7. Stage 5 — passage retrieval

The step that replaces "cap the page at N characters" with "select what's
relevant". Local, free, and the first asymmetric use of the encoder in this
engine (`embed/model.py:12-15`: *"`passage:` is for the long side of an
asymmetric retrieval... nothing in the engine does that yet"*).

### What the encoder does, precisely

`intfloat/multilingual-e5-small` — 384 dims, 512-token window, outputs
L2-normalised so cosine is a dot product. `prefix(text, role)`
(`embed/model.py:47`) prepends the literal string `"query: "` or
`"passage: "`. That is the whole mechanism: e5 was contrastively trained on
(query, passage) pairs carrying those literal prefixes, so the prefix moves the
text within one shared space. There is no second model and no cross-attention.

**It scores retrieval relevance, not answerhood.** A paragraph about funding
scores high against *"who funds them?"* whether or not it names a funder. The
encoder cannot separate "discusses the topic" from "answers the question".
Therefore:

- it is a **recall filter** — it decides what the LLM reads, never what is true;
- a high cosine is never recorded as evidence a question was answered;
- the LLM in stage 6 does all the answering, and may answer nothing from a
  chunk that scored 0.9.

### Chunking

Chunk to **300–400 tokens with ~15% overlap**, split on paragraph boundaries
where possible. The window is 512 and `fit()` (`embed/model.py:60`) truncates
correctly — by binary search in the tokenizer's own units, precisely so a
Devanagari record isn't silently clipped at a character bound — but a chunk
over the window is still embedded on its head alone. Respect the window when
chunking rather than relying on `fit()` to rescue it.

### Selection: top-k per question, never a threshold

```
for each open question:   encode(question, role="query")
for each chunk:           encode(chunk,    role="passage")
keep the top k=3 chunks per question; union across questions; dedupe
```

### What "open" means, which is not yet settled

`open question` is used here, in §11b and in §11c, and for 6 of the 35 questions
it is **not a well-defined predicate**. `02-questions.md`'s first finding from
the reverted dive says why:

> **`multi` questions never retire**, so the open set is never empty, the "stop
> when everything is answered" exit is dead code, and every candidate —
> including a one-paragraph registry stub — burns the full budget.

The `multi` questions are problem q12 `tag:mechanism`, q17
`tag:gap_missing_leg`, q19 who-works-it, and actor q14 `ask:need:*`, q15
`ask:offer:*`, q16 `channel:*`. Each can legitimately be answered again, so
"answered at least once" does not close it.

Here that costs passages rather than LLM calls — the 6 stay in the encode set
every pass, so their top-k always enters the union and inflates the one paid
call. It is not free, and in §11c it is worse than not free (see the note
there).

A `multi` question needs a closing rule that is not "answered at least once".
The repo already has the right shape and this design quotes it one section
later for the yield gate — `process-leaf`'s *"stop when a wave yields no new
names"*. Applied per question rather than per candidate, **closed when a pass
adds no new value** makes a `multi` question closable without capping how many
answers it may have. Recorded as open in §14 rather than decided here.

**No absolute cosine cutoff**, for the measured reason in `gate2.py:29-36` —
e5-small compresses similarity into a narrow high band (AUC 0.923 on 0.041
mean separation on the gate-1 pairing), so no global threshold is both safe and
useful. Relative selection is immune to that; thresholding is not.

### The starting values, and how to move them

All four live together in `worker/config.py`, not scattered as literals:

| Constant | Start | Why this number |
|---|---|---|
| `CHUNK_TOKENS` | 320 | The encoder window is 512 and `fit()` measures the *prefixed* string; 320 leaves room for `passage: ` and the special tokens with margin for a Devanagari chunk, which tokenizes ~20% longer than the same characters in English |
| `CHUNK_OVERLAP` | 48 (15%) | A figure and its denominator, or a name and its role, routinely straddle a paragraph break; 15% is the cheapest insurance against splitting one |
| `TOP_K_PER_QUESTION` | 3 | One chunk is a single point of failure; beyond ~3 the marginal chunk is usually the same paragraph's neighbour |
| `MAX_SOURCES` | 5 `tracked` / 1 `registry` | Set-cover rarely needs more than 5 to exhaust the covered families |
| `PASSAGE_TOKEN_CAP` | 9,000 | Bounds the one extraction call; overflow drops lowest-scoring chunks, but never a source's last chunk |

**These are starting values, not findings.** Write them as such in code
comments, the way `gate2.py` does for its bands.

**How they get measured is different from every other sweep in this repo, and
that difference matters.** `embed/calibrate.py` could measure gate 1 against
*labels the corpus already carries* — 303 `works_on` edges as positives, 532
aliases for resolution. **No such label exists for "does this chunk answer this
question."** Producing one means hand-annotating chunks, which is the work this
engine exists to avoid.

So tune against the **downstream outcome** instead, and say so rather than
implying an AUC was computed:

1. Freeze a set of ~20 candidates and their fetched sources, so retrieval is
   the only thing varying.
2. Sweep one constant at a time. Record **realised coverage** (non-null answers
   ÷ questions asked) and **input tokens spent**.
3. Move the constant while marginal coverage per 1,000 extra tokens stays above
   a floor; stop at the knee. Raising `k` from 3 to 6 that buys two more answers
   for double the tokens is a loss, not a win.
4. Re-run when the corpus shifts language mix or the encoder changes — neither
   of these numbers survives a model swap.

Coverage is measured against **questions asked of a candidate that had at least
one source**, not against the full registry; otherwise a thin candidate makes
retrieval look broken when it was the search that found nothing.

Cap the union at a token budget (~8–10k) and, if it overflows, drop the
lowest-scoring chunks — while guaranteeing **at least one chunk per source**,
so a source that made it through set cover is never silently unread.

---

## 8. Stage 6 — one extraction call

All selected passages, from all sources, in **one** call.

```
[S1] https://…            [S2] https://…            [S3] https://…
  <passage> <passage>       <passage>                 <passage> <passage>
```

Why one call rather than one per source:

- The system prompt and question list are sent once, not n times.
- One round trip, which matters more than tokens under the OpenRouter free-tier
  pacing lock (`llm.py:57`).
- **Reconciliation requires seeing both sides at once.** `02-questions.md`'s
  "sources disagree → write the disagreement" rule is unimplementable across
  separate calls without a second synthesis call. Batching makes synthesis free.

What it costs, and the mitigations:

| Cost | Mitigation |
|---|---|
| Attribution now depends on the model self-reporting `[Sn]` | `source_id` is **required** on every answer; answers with an absent or unknown id are dropped, not guessed |
| One malformed response loses all sources | On JSON parse failure, retry once per source separately before giving up |
| Long-context dilution across n sources | This is what `MAX_SOURCES` bounds; raise it only against measured realised coverage |

The response shape is `02-questions.md`'s contract plus the source id:

```json
{"answers": [{"question_id": "...", "source_id": "S2", "answer": "...", "confidence": 0.0}],
 "claims":  [{"field": "...", "value": "...", "confidence": 0.0}],
 "emits":   [{"kind": "problem"|"actor", "name": "...", "hint": "...", "signals": {...}}],
 "edges":   [{"dst_name": "...", "dst_kind": "...", "edge_kind": "...",
              "relevance": 0|1|2|3|null, "stance": "..."|null, "evidence": "..."}]}
```

---

## 9. Stage 7 — the findings ledger

Every answer is written to `finding` (`store/schema.sql:308`) —
`candidate_id`, `question_id`, `answer`, `confidence`, `source_url`,
`gathered_at` — **before** claims are resolved. This is provenance
`process-leaf` itself doesn't keep: a leaf records the reconciled claim, the
ledger records every input to it and where each came from.

Two schema additions this design wants:

- `finding.source_id` → FK to `source`, so a finding joins to the fetched page
  and its `fetched_at`, not just a URL string.
- `finding.chunk_ref` (nullable) — which passage produced it, for auditing a
  wrong answer back to the text that caused it.

Claims are then derived from findings, not written independently:

- one finding for a question → claim from it directly;
- multiple, consistent → claim from the most specific, not a concatenation;
- multiple, **conflicting** → one claim whose value states the disagreement and
  both figures with their sources. Never average, never silently drop a side;
- zero → no claim. Not a guess, not "unknown".

---

## 10. Stage 8 — emits, and problem emission

### The hole to close first

`worker.py:279-281` drops any edge whose destination doesn't resolve, with the
comment *"the emits loop above is responsible for it turning into one."* For
actors it is. For problems it never has been, because `_EXTRACT_COMMON`
describes emits as *"other organisations or named individuals"* and gives only
actor examples. Measured on `problems/graph.db`: **8 candidates emitted, all
actor, zero problem**, against 51 problems and 292 actors that all arrived via
the corpus migration.

So: **an unresolvable `works_on` destination is a problem candidate.** That is
the natural source — the failures an actor says it works on — and closing it is
the smallest high-value change in the pipeline.

### Problem emits need signals, not just a name

Leafability is the **orchestrator's** decision, not the worker's — it is a
scheduling judgment (is this worth a research budget) and keeping it out of the
worker preserves the worker's recall bias, consistent with gate 1. But the
orchestrator can only judge from what the worker emitted, and re-fetching to
decide would defeat the split.

So a problem emit carries the four gate signals, captured while the model still
has the page open (`process-leaf` → the leafability gate; three yeses of four):

```json
{"kind": "problem", "name": "...", "hint": "...",
 "signals": {
   "harmed_population": "<bounded and nameable? who?>"        | null,
   "magnitude":         "<figure, or 'uncounted', or null>",
   "agent":             "<what triggers the harm>"            | null,
   "actionable":        "<is there a thing to be done, by whom>" | null }}
```

`null` means the source didn't support it — not a "no". "Uncounted" in the
magnitude slot is a **pass**, per the gate: absence of measurement is a
finding; *unbounded* is the fail.

### Dedupe is harder for problems than actors

Actor names are proper nouns, so `db.norm` exact-match works. Failure names are
descriptions — "silicosis in stone quarries" and "quarry dust lung disease" are
one problem — so a problem emit **must** go through `resolve.py`'s embedding
shortlist rather than exact match, and `ambiguous` must route to the human
queue rather than minting a duplicate. Against 51 existing problems this is
cheap; it is also the difference between a browse tree and a pile.

### Actor emits — unchanged, and still the cheap recursion

Every read yields co-petitioners, funders, grantees, officials, coalition
partners, competing ventures, and founders named as individuals in their own
right. This is the engine's analogue of `process-leaf`'s recursive
`actor-channel-finder` fan-out and it is the cheaper one: an emitted name
re-enters through gate 0 (preview dedup) and gate 1 before anything is paid for
it, whereas parallel subagents don't dedupe against each other. The difference
is latency, not depth — an emitted actor is worked on a later batch.

---

## 11. Budgets and stopping

Per candidate, per tier:

| | `registry` | `tracked` |
|---|---|---|
| Search queries | 1 | 4–8 |
| Sources fetched | ≤1 | ≤5 |
| LLM calls | 1 | 1 (+1 only if §11b earns it) |

**One pass is the default, and may well be the only pass.**

### 11a. Why a naive second pass is worthless

Re-running the same query families against the same index returns the same
URLs, and set cover already took the best-covering ones — the sources it left
behind were left behind *because they added no coverage*. A second pass built
that way is a retry, not an iteration: same queries, same results, same
answers, double the cost. It should not be built.

Two things a second pass genuinely has that the first did not:

1. **The unread remainder of a pool already paid for.** Six queries × ~10
   results dedupes to perhaps 30–40 URLs; set cover read 5. The other ~30 are
   search results **already bought**. Reading one costs a fetch and an
   extraction call — no search, no query planning.
2. **Extracted entities as new query seeds.** Pass 1 surfaces the registered
   legal name (searching *Mahila Housing SEWA Trust* is not searching *Mahila
   Housing Trust*), founder names, the parent org, named funders, the actual
   district. Those are query material the candidate row never had. A query
   seeded from them is a **different query**, not the same one again.

Anything that is neither of those is a retry.

### 11b. What a second pass may do, if the numbers justify it

Strictly narrower than the first, and never a repeat of it:

- only questions **still open after extraction**, and only high-value ones —
  magnitude, who-works-it, funding, affected-led. Note that who-works-it is
  problem q19, which is `multi` and therefore never closes under today's
  definition of open (§7) — so this list cannot be evaluated until the closing
  rule exists;
- **cheap route first**: exhaust the leftover RRF pool for those questions
  before issuing any new search;
- **new searches only when re-seeded** from an entity pass 1 extracted, and
  only where that seed is materially different from the candidate name;
- hard stop at two passes. Depth past that is a human sitting.

And the yield gate stays, because it is the rule the reverted dive lacked and
`process-leaf`'s own (*"stop when a wave yields no new names"*): a first pass
whose realised coverage was near zero means the framing was wrong, and paying
again buys the same failure. That candidate goes to the human queue, not round
the loop. A pass whose `unresponsive_engines` breached the §4 floor is the
other case — that is a blocked run, requeue it whole rather than treating thin
results as a finding about the entity.

### 11c. Measure the trigger before building the branch

**Do not build §11b on the strength of this argument.** Instrument pass 1 to
answer, from real runs, whether the branch would ever fire usefully — three
counters written per candidate, costing nothing:

| Counter | Answers |
|---|---|
| High-value questions still open after pass 1 | How often anything would trigger at all |
| Unread URLs left in the RRF pool covering those questions | Whether the cheap route has material — if this is usually 0, only re-seeding is left |
| New query seeds extracted that differ from the candidate name | Whether re-seeding has material — if usually 0, §11b is dead and should be deleted |

**Counter 1 cannot read 0 as specified, and that breaks the decision rule
below.** §11b's high-value set names who-works-it, which is problem q19, a
`multi` question (§7). A `multi` question never closes, so counter 1 reads ≥1
for every candidate, forever. The counter built to settle whether §11b is worth
building is then structurally incapable of returning "no" — which is worse than
an unmeasured trigger, because it is a trigger that always reads yes and looks
like evidence. The counters are only meaningful once §7's closing rule lands;
until then do not read counter 1 as a signal about §11b.

If the first counter is usually 0, there is no branch to build. If it is high
but the other two are 0, the answer is not a second pass — it is that the
questions are unanswerable from open sources, which is a **finding about the
entity** (`02-questions.md`: absence is recorded, never guessed) and belongs in
the record rather than in more spend.

That ordering is the point: the counters are three integers in pass 1, and they
settle a design question that would otherwise be settled by building the thing
and hoping.

---

## 12. Cost model

Per `tracked` candidate, 6 queries, 4 sources, ~9k tokens of selected passages
in, ~2k out:

| Line | SearXNG (chosen) | Anthropic `web_search` | Brave / Serper |
|---|---|---|---|
| Search | **$0** — one container; cost is operational, not metered | $0.06 (6 × $10/1,000) **+ tokens for results in context** | single-digit $ per 1,000 queries — *verify with the provider* |
| Extraction (Sonnet 5, $2/$10 per MTok) | ~$0.04 | ~$0.04 | ~$0.04 |
| Extraction (OpenRouter `:free` rung) | $0 | $0 | $0 |
| Embedding, fetch, fusion, set cover | $0 (local) | $0 (local) | $0 (local) |

A `registry` candidate is roughly a tenth of that, which is why the tier split
is the first thing to build and not the last.

The non-dollar budget is **throughput**: the OpenRouter free rung paces to
~20 req/min (`llm.py:57`). At one extraction call per candidate that ceiling is
~20 candidates/min rather than the dive's ~4.

---

## 13. Failure modes, and what each degrades to

| Failure | Degrades to |
|---|---|
| Search returns nothing for a family | That family's questions stay unanswered; recorded as absent, never guessed |
| Search provider down | Fall back to the candidate's own URL as the single source — the old single-page path |
| Upstream engines blocking (`unresponsive_engines` climbing) | Results thin **silently**. Record the rate per query, alarm past a floor, and do not let the bandit learn from a blocked run |
| One engine auto-suspended (`ban_time_on_fail`) | Remaining engines still answer; the query is flagged degraded, not failed |
| All sources gate-2 `mismatch` | No extraction call, candidate flagged for the human queue. Don't spend on a wrong-entity read |
| Extraction JSON malformed | Retry once per source separately; then write nothing and log |
| Model omits `source_id` | Drop that answer. Never attribute by guess |
| Encoder unavailable | Fall back to first-N-chars per source, capped. Degraded, not broken |
| Emitted problem is unbounded/trend-shaped | Emitted anyway with `signals`; the orchestrator's gate rejects or stubs it |

---

## 14. Open decisions

1. ~~**Search provider.**~~ **Decided 2026-09-13: self-hosted SearXNG**,
   pending the §16 step 0 spike. Operational detail is in §4.

   *Why.* It is the only option with both properties this design needs:
   **exactly the queries we ask for** (no model choosing them) and **no
   per-query meter** (so 6 families × hundreds of candidates is not a budget
   conversation). Multi-engine coverage is also better recall for the
   long-tail affected-led orgs this corpus exists to find — the same argument
   gate 1 already makes for biasing toward recall.

   *What would reverse it.* Not resources. If Google and Bing refuse a
   datacenter IP at our query rate, the recall advantage inverts and a paid
   index wins. Unknown until measured; that is what the spike is for. Because
   stage 2 is an adapter behind a fixed interface, reversing costs a provider
   module, not a redesign.

   *Rejected, with the reason:*

   - **Google Web Search Service** (`websearchservice.googleapis.com/v1:search`)
     — partner-gated. Beyond an `X-Goog-Api-Key`, every request needs a
     `client_id` issued under a partner agreement; pricing, quotas and the
     response schema are all undisclosed publicly. Not designable-against
     without an agreement in hand. Distinct from the older Custom Search JSON
     API, which is self-serve but capped and search-engine-scoped.
   - **Anthropic `web_search_20260318`** — $10/1,000 searches plus token cost
     for results entering context, and model-mediated: Claude picks the
     queries. `max_uses` plus an explicit instruction can pin them and all n
     searches run in one turn, so it stays the best fallback if self-hosting
     becomes a burden. Its **dynamic filtering** is a server-side stage 5 —
     costs tokens where e5 is free, and takes the k/chunking control away.
   - **Brave / Serper** — the boring paid fallback, same shape as SearXNG
     minus the operational tax. Keep behind the same adapter for families
     where blocking bites.
   - **The `claude -p` CLI rung** (`llm.py:170`) — already wired,
     subscription-billed at `0.0` marginal. Throughput-limited and
     model-mediated, but hard to argue with for nightly batch if the above
     all fail.

2. ~~**`k`, chunk size, and `MAX_SOURCES`.**~~ **Decided 2026-09-13:** start
   at 320 / 48 / 3 / 5 / 9,000, all in `worker/config.py`, tuned against
   realised coverage per token rather than an AUC — there are no chunk-level
   relevance labels and manufacturing them is the work this engine avoids.
   Method and rationale in §7.

3. ~~**Where query templates live.**~~ **Decided 2026-09-13:** definitions in
   `engine/search/families.yaml` (git-tracked, the source of truth), runtime
   arm statistics in `query_template` / `template_trial` in `graph.db`. The
   worker reads both, writes only trials; the Orchestrator tunes. Detail in §3.

4. ~~**Whether `registry` candidates get a search.**~~ **Decided 2026-09-13:**
   yes — exactly one, the identity family, even when the candidate already
   carries a URL, because that URL is usually the page that *named* the entity
   rather than the entity's own. Never the full family set. Detail in §2.

**Still open:**

- **The `unresponsive_engines` floor** (§4) above which a run is flagged
  degraded and withheld from bandit reward. Needs the §16 step 0 spike to pick
  a number; guessing one now would be the same error `gate2.py` refuses to make.
- **The closing rule for a `multi` question** (§7) — what makes one "no longer
  open" when "answered at least once" does not. Blocks §11b's trigger list and
  §11c's counter 1 from meaning anything, and inflates stage 5's passage union
  until it exists. `process-leaf`'s *"stop when a wave yields no new names"*,
  applied per question, is the candidate shape; it is not yet a decision.
- **Whether a second pass (§11b) is worth building at all.** Specified, but
  deliberately not committed: a naive one is a retry that re-reads the same
  URLs. Three counters in pass 1 (§11c) settle it from real runs — if the
  high-value-open counter is usually 0, or the two material counters are,
  §11b gets deleted rather than built.

---

## 15. What this deliberately does not do

Not `process-leaf`. No numbers-hygiene pass, no human date verification, no
Slate recall, no leafability gate (the orchestrator's), no following of
channels, no connection logging. This is the mechanical floor a worker runs
unattended: search where the answer might be, read only the relevant
paragraphs, record every fact with its source, and never claim more certainty
than the sources support.

---

## 16. Build order

0. **Spike SearXNG before anything depends on it.** Docker instance, `json`
   enabled, general category cut to ~5 engines, limiter off. Take 20 real
   candidates from `graph.db` — a mix of `actor` and `problem`, including
   several thin affected-led ones — and issue their query families for real
   (~120 queries) at the throttle the worker would actually use. Measure three
   things: the **`unresponsive_engines` rate and whether it climbs** over the
   run (the blocking curve); **predicted coverage**, i.e. whether each family
   returns plausible URLs for the questions it targets; and **whether the thin
   affected-led candidates surface anything at all** — the paid APIs' known
   weak spot and the main reason to prefer metasearch. If Google and Bing
   survive 120 throttled queries, ship it; if they collapse, swap the adapter
   to Brave and carry on, having spent an afternoon.
1. **Close the problem-emission hole** — unresolvable `works_on` dst → problem
   candidate, with `signals`. Independent of everything else, smallest diff,
   unblocks the browse tree growing on its own.
2. **The depth tier** — biggest cost saving, no new dependencies, and it is the
   repo's own rule rather than a new one.
3. **Stage 5 (passage retrieval)** — free, local, and it removes the uncapped-
   text problem whether or not search ever lands.
4. **Stage 6 (one batched call with `source_id`)** — needs 5 to be worth it.
5. **Stages 1–3 (query planning, search, fusion, set cover)** — gated on
   step 0. Lands `engine/search/`: the SearXNG adapter, `families.yaml`, and
   the fuse + set-cover code.
6. **The §11c counters** — three integers written during pass 1, costing
   nothing, landing with stage 6. They are what decides step 7.
7. **The bandit reward signal, and §11b only if the counters justify it** —
   last, because both need realised-coverage numbers that exist only once 1–6
   have run against real candidates.
