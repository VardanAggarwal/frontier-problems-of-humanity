# Engine v2 — architecture

Status: **exploratory design, not built, not stitched to the existing system.** Drafted 2026-09-12 from a single conversation. Everything below is a proposal to argue with, not a committed plan.

## Why this exists

The current pipeline (`problems/` — tier taxonomy → needs.yaml → tier files → leaves → actor records, run by `process-tier`, `process-leaf`, `actor-channel-finder`, `impact-network-crawler`) works but is bound tightly to the Maslow tier taxonomy and to me as the sole researcher and prioritizer. Stripped of the tier taxonomy, what's actually been built is a generic engine: **take a cause, research it, find what works and what doesn't, map the ecosystem already working on it, weight how relevant each actor is, and surface where the gaps are.** V2 is that engine made explicit, general-purpose, and only *instantiated* on fph rather than built into it.

A task-level audit of the current system (skills, agents, build scripts) found roughly 30 independent smallest-unit tasks across four phases (decomposition, actor discovery, matching/catalyst, infra). Most exist; the concrete missing pieces were: no back-edge from a downstream finding to its parent decomposition, no relevance *score* for actors (only a binary `depth: registry|tracked`), no learning loop that improves actor discovery over time, and no scheduled actor monitoring. This document is the redesign that came out of naming those gaps.

## Two unifying moves

**1. One bandit engine, two arm-spaces.** "Which sub-problem is worth deepening" and "which source/query is surfacing relevant actors" are the same decision under uncertainty with a cost per pull. Rather than bespoke heuristics per agent (a recursion-depth counter here, a quench/double-down rule there), there is one bandit engine — living in the Orchestrator — run over a problem-arm-space and an actor-arm-space separately, with reward normalized to one scale so both compete fairly for the same budget. A real bandit (Thompson sampling / UCB) also gets decay/re-exploration for free, avoiding calcification around whatever scored well early.

**2. Research agents emit claims, never prose.** Every research-producing agent (Problem Agent, Actor Processing Agent) outputs only typed, evidenced claims — `{entity, field, value, source, confidence}`. No agent writes a human-facing sentence until it reaches the Writing Agent, which is the only thing that turns approved structured claims into an actual document. This is the direct fix for research output currently being "a royal mess" to clean up — a much smaller surface to keep consistent than "everything anyone writes."

**Layering rule** (used repeatedly below to decide what centralizes and what stays distributed): **anything answerable from the global view alone, independent of who's asking, belongs in a shared service. Anything that depends on what the calling agent is currently chasing stays with that agent.** Query generation, extraction, and relevance judgment are context-dependent and stay distributed. Content aggregation, deduplication, and hierarchy placement are context-independent and centralize.

## The four layers

```
Orchestrator            bandit engine, budget ledger, review gate, job dispatch
    │
Agents                  Problem · Structure · Actor Processing · Actor Discovery ·
                         Writing · Matching/Gap  — sequencing and judgment
    │
Shared stateful services   Entity Resolution · Content Corpus · Provenance Ledger
    │
Text Processing primitives   Extract · Embed · Classify · Compare · Generate · Summarize
```

Each layer calls only the layer below it.

---

## Orchestrator

Owns the frontier of all pending work and decides what runs next.

- **Frontier queue** — every pending unit of work (deepen node X, run query variant Y, deep-dive actor Z, reconcile structure) is one item in one queue, not tracked separately per agent.
- **Budget ledger** — global spend cap plus per-branch caps, so one deep rabbit hole can't starve a sibling branch. Depth control is a ledger rule, not logic duplicated inside Problem Agent.
- **Bandit engine** — arm selection + reward ingestion, run per arm-space (problem-exploration, actor-discovery), reward normalized to a common scale.
- **Job dispatch** — invokes the right downstream agent for a frontier item; tracks completion, timeout, retry.
- **Review gate** (a task here, not a separate agent) — holds an item in `pending-approval` when it crosses an escalation threshold (Structure Agent's ambiguous merges, Matching/Gap Agent's future connection proposals, any low-confidence high-impact write). Presents a diff, captures approve/reject/edit, routes the decision back into the pipeline.

## Problem Agent

Input: one node (a cause, or a sub-problem awaiting deepening) + accumulated context. Recursion is *not* self-call — it emits candidate sub-problems with a priority signal (scale, uncertainty, evidence thinness) back to the Orchestrator's frontier, which decides whether and when to expand them.

Pipeline: query generation (bandit-driven, not one-shot) → fetch → **hand raw content to Structure Agent's corpus ingestion, receive back the genuinely-novel subset** → extraction → reconciliation (flag disagreement explicitly, per the existing research standard — don't silently pick a number) → entity identification + typing → confidence estimation → emit typed claims to Structure Agent.

Content aggregation and novelty-dedup were originally scoped inside this agent; both moved to Structure Agent (see below) under the layering rule — "have I seen this document before" doesn't depend on which branch is asking.

## Structure Agent

Front door for every structured claim from every other agent, and the keeper of the global view. Two speeds, plus the raw-content corpus:

- **a. Intake / type dispatch** — an incoming claim declares a type (sub-problem, mechanism-claim, blocker-claim, evidence-claim, actor-mention, relation-claim). Actor-mentions are forwarded to Actor Processing with their originating context; this agent doesn't classify actors itself.
- **b. Candidate-duplicate search** — via the shared Entity Resolution service, not bespoke logic.
- **c. Merge/split decision** — high-confidence match → auto-merge (cheap tier). Low-confidence → new node (cheap tier). Ambiguous middle band → Review Gate.
- **d. Hierarchy placement** — which parent(s) a deduped node sits under. Multi-parent by design (a graph, not a tree) — e.g. "sand mining" can sit under both a river node and a construction-sector node.
- **e. Relation/edge maintenance** — shared-mechanism, shared-node, shared-actor edges, beyond parent-child.
- **f. Mechanism registry maintenance** (costly tier) — promotes a recurring abstract pattern to a named mechanism once it crosses a frequency threshold (generalizes the existing "3+ files" rule). Requires seeing many nodes at once.
- **g. Node (concrete shared-object) registry maintenance** (costly tier) — same idea for a concrete upstream object shared by 2+ sub-problems.
- **h. Cheap real-time placement** — a–d for the unambiguous majority, run synchronously as claims stream in.
- **i. Costly batch reconciliation** — periodic sweep: global dedup, re-derive hierarchy where new siblings make an old placement look wrong, run f/g, escalate structurally significant changes to Review Gate before applying.
- **j. Staleness tracking** — flags nodes whose evidence hasn't refreshed recently; feeds the bandit's reward function via the Provenance Ledger.
- **k. Query interface** — read API: "is this already covered" (Problem Agent), "what nodes/mechanisms exist to check this actor against" (Actor Processing).
- **l. Content ingestion / corpus management** — receives raw fetched content from any exploring agent, dedupes at content level (same underlying resolution logic as entity dedup, applied to documents instead of claims — one generalized service, two granularities), stores once with source + timestamp + originating query/arm, returns the novel subset to the caller. Also emits a fast novelty-rate signal (e.g. "80% of this query's results were already in corpus") as a cheap early reward for the bandit, ahead of the slower relevance-scoring reward from Matching/Gap Agent.

## Actor Processing Agent

Input: one actor + optional context. Relevance and fit are scored **per (actor, node) pair — a matrix, not a per-actor scalar**, since the same org can be highly relevant to one sub-problem and irrelevant to a sibling.

Pipeline: context fetch (search if not given) → identity resolution (shared Entity Resolution service) → cheap candidate-node shortlist (embedding similarity against node summaries — needed once the graph is large enough that checking full relevance against every node doesn't scale) → relevance screen on the shortlist → deep-dive (raw structured claims only — who they are, what they do, what mechanisms they work, what they've achieved) → emit claims to Structure Agent → outreach/channel discovery (contact route, live channels) → per-(actor, node) relevance scoring.

**Update mode absorbs the separately-proposed "Update Actor Agent"** — same pipeline, invoked with `mode: refresh, existing_profile, new_context`, skipping stages that don't need re-running.

## Actor Discovery Agent

The actor-arm-space consumer of the Orchestrator's bandit. Input: known actors + context (a node/problem).

Pipeline: shared source/channel registry (shared with Problem Agent's — an NGO annual report is a source for both problem facts and actor facts) → query-template generation per arm → bandit arm-selection (delegated to the Orchestrator, not reimplemented here) → parallel execution → candidate extraction → quick relevance screen (Actor Processing's screen step only, not the full deep-dive, to keep the loop fast) → reward emitted back to the bandit.

## Matching/Gap Agent

**Not producing introductions right now** (connections aren't in active use) — its job today is generating the reward signal that tells both bandit arm-spaces where to look.

Pipeline: gap computation per node (which legs are under-covered, weighted by actual actor relevance scores, not binary presence) → node priority scoring (gap size × scale × staleness) → arm-value propagation (translate a node's priority into upweighted bandit arms — e.g. a node missing enterprise coverage upweights query templates likely to surface enterprises).

Connection/introduction generation (asks+offers matching, drafted introductions — today's manual `connect-pass`) stays a documented, dormant capability on this same agent, so the contract has room for it later without a redesign.

## Writing Agent

Input: approved structured claims + evidence for one target document (a leaf, an actor profile, a tier-summary section).

Pipeline: template/section selection (enforces existing invariants, e.g. the leaf A–E structure) → drafting from claims, carrying citations and explicit "sources disagree" notes rather than resolving them silently → numbers-hygiene pass (every figure dated, no figure repeated with a different value, denominators present, no unsupported trend claims, lenient-threshold comparisons flagged — the existing manual checklist, now enforced mechanically) → consistency check against linked sibling documents → emit to Review Gate.

## Shared stateful services

- **Entity Resolution** — candidate-match search, merge scoring, merge execution, split detection. One implementation, called by Structure Agent (§b) and Actor Processing Agent (identity resolution) both — not duplicated logic that would otherwise drift.
- **Content Corpus** — see Structure Agent §l.
- **Provenance Ledger** — infra, not an agent. Claim ingestion (`{entity, field, value, source, confidence, timestamp, writing_agent}`), current-state materialization (a field's "current value" is a computed view over the log, not an overwrite), disagreement flagging, staleness computation. Makes reconciliation and "why did this change" answerable instead of silently lost.

## Text Processing primitives

The layer underneath every agent and every shared service — currently implicit and reimplemented per-agent; centralizing it is the more fundamental fix for inconsistent/gibberish research output, one level below the Writing Agent split.

- **Extract(text, schema)** — structured fields out of raw text against a target schema.
- **Embed(text)** — vector representation for similarity search.
- **Classify(text, label-set)** — one value from a controlled vocabulary (every enum assignment in the data model is an instance of this).
- **Compare(claim A, claim B)** — agree / conflict / refines. Powers Provenance Ledger's disagreement detection and Entity Resolution's merge scoring.
- **Generate(prompt, context)** — drafting. Query generation and Writing Agent's prose both reduce to this with different context.
- **Summarize(entities, target)** — used by Writing Agent, and by Review Gate to render a human-readable diff.

Two side benefits of centralizing here: cache by content hash (a document fetched once by one branch gets extracted once, even if a sibling branch also wanted it), and pin model/version per primitive so "why did this mechanism tag change between passes" is answerable (model upgraded) rather than mysterious.

---

## Open questions — not yet settled

- **Should extraction also centralize?** Everything else content-independent moved to Structure Agent; extraction was deliberately left distributed (it depends on what the calling agent is currently chasing) but this boundary hasn't been stress-tested.
- **I/O contracts.** The claim schema (`{entity, field, value, source, confidence}`), the reward schema for the bandit, and each agent's exact input/output haven't been written down yet — this document describes shape, not interface.
- **Stitching to the existing system.** Nothing here has been mapped onto the current `problems/` schema, `process-tier`/`process-leaf` skills, or the two existing actor agents (`actor-channel-finder`, `impact-network-crawler`). That mapping — what survives as-is, what generalizes, what's replaced — is the next real piece of work, deferred deliberately until this shape stabilizes.
- **Pace tension.** The existing practice is deliberately slow and human-paced (one tier need per sitting, no rushing to conclusions — `CLAUDE.md` → *Working with the user*). An engine with its own bandit-driven exploration and a Structure Agent that can autonomously restructure is, by construction, faster and more autonomous than that. Whether V2 is a deliberate change of operating mode, and where exactly the Review Gate should sit to preserve the judgment calls that currently only happen because the pace is slow, hasn't been decided.
- **Connections/matching is intentionally dormant**, not designed. The Matching/Gap Agent's contract leaves room for it but the actual introduction-drafting logic (today's `02-connect-pass.md`) has not been redesigned for this architecture.

## Provenance of this document

Written from a single design conversation, 2026-09-12, that moved through: a flowchart-and-ER-diagram audit of the existing system (`catalyst-platform` artifacts), a task-level decomposition of ~30 existing units, a first agent sketch (Problem/Structure/Actor Processing/Update Actor/Actor Discovery), and four rounds of generalization (bandit unification, Matching/Gap reframed as reward source not connection-maker, aggregation moved to Structure Agent, text-processing primitives centralized).
