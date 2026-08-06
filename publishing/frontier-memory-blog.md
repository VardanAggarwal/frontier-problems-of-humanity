# The Book That Made Me Understand What I'd Been Building

*Draft — Vardan Aggarwal, July 2026*

---

Someone posted a problem last week: build an AI agent that can write long-form
content. A book.

I read it and had the uncomfortable experience of recognising five months of my
own work in a problem statement I had never written down.

---

## 1. The thing that bothered me first

Years ago I came across a project where someone tried to generate a research
thesis with an RNN. The structure came out right — sections, subsections, the
rhythm of academic prose, citations in roughly the right places. The content was
meaningless. It looked like a thesis from ten feet away and dissolved on contact.

What attention added on top of RNNs, more or less, was meaning. Local relevance:
this token, given those tokens. That was the leap.

And yet — an AI on its own will still write a bullshit book.

That gap bothered me for a long time before I could say why. It isn't a context
window problem. You can hand a model 200k tokens of the world's best prose and it
will still produce something that reads fine and says nothing. The failure isn't
that it forgot chapter two. The failure is that nothing was at stake.

Here is what I think is actually required to write a long piece of work:

1. **Personal context.** The stories only the author can know. Their opinions,
   their questions, the specific thing they got wrong in 2019 and are still
   annoyed about.
2. **Structure.** Not an outline — a process. What kind of book is this, and what
   does that oblige every chapter to do?
3. **Research and verification.** The hard facts. The claims that have to survive
   someone checking them.

Only the third is something a language model does well unsupervised. The first
lives in a human being and has to be extracted over months. The second is a
representation problem nobody has solved well.

I did not sit down five months ago intending to work on this. I want to be
precise about that, because the tidy version of this story would be a lie. What
actually happened is that I kept hitting the same wall from three different
directions, and only the book problem made me see it was one wall.

---

## 2. Slate v1 — building memory badly, on purpose

*February 21 – June 11, 2026. 46 commits.*

I started with a simple, selfish problem: I have been writing notes for a decade
and I cannot use them. Not "cannot find them" — search solves that. I cannot
*use* them. I would form an opinion in a conversation and only later realise I
had argued the opposite in 2023, in a note I no longer remembered writing.

So I built Slate: a personal memory engine. Notes go in. They get decomposed into
claims and concepts with provenance. When I'm about to say something, it surfaces
what I've already thought.

The representation was, I still think, mostly right. Fragments, concepts, links
between them, a health model where concepts decay if untouched. What was wrong
was the *process*, and the wrongness was structural:

- Every semantic decision happened **synchronously, at save time**, in one greedy
  LLM call that could see only the top five nearest neighbours. A note saved on
  Tuesday was interpreted with no knowledge of Wednesday.
- Concepts could **merge but never split**. And merges did a destructive `DELETE`
  — no history. I had built a system to track how my thinking evolved that
  discarded the evidence of it evolving.
- Claims were **never deduplicated**. No compression pressure, so no canonical
  layer, so the same idea existed forty times in forty phrasings.
- I extracted temporal "A leads to B" links and then **never read them** in
  search or ranking. Pure dead code, dutifully maintained.
- ChromaDB and SQLite as a dual store, with a hand-written rollback dance when
  they disagreed.

I want to dwell on the first one, because it's the real lesson. Save-time
decisions are greedy decisions. Every note gets interpreted in the context of a
corpus that doesn't include the notes that came after it. Memory formed that way
can only ever be the sum of first impressions.

Which is not how memory works in anything that has memory. There's a reason sleep
exists.

---

## 3. Slate v2 — the rewrite

*June 11 – July 12, 2026. 66 commits. Started the same day v1's last commit landed.*

Four months before the rewrite, I'd written a note to myself that turned out to
be the whole design:

> A smart AI agent has to actually work on top of processed information and not
> raw data. The data engineering that processes that information into actionable
> insights is where smartness really resides.

Slate v2 is that sentence, implemented. The architecture is borrowed openly from
how biological memory is thought to work — hippocampus and neocortex, with a
consolidation phase between them:

**Two stores, one transfer process.**

- The **episodic store** is append-only and immutable. Raw text, sentence
  embeddings, the novelty receipt computed at write time. This is the source of
  truth and it is never updated.
- The **semantic store** — canonical claims, concepts, typed relations — is
  *derived*. It is written only by consolidation, and only by emitting events.

**Encoding is cheap and synchronous.** Under a second. Embed locally, nearest-
neighbour against existing canonical claims, return a receipt: what this note
echoes, what's new in it, what it contradicts. No LLM graph decisions at save
time. The receipt is the immediate payoff — you save a thought and immediately
learn it contradicts something you wrote in March.

**Consolidation is a nightly batch.** Blueprint extraction, claim canonicalisation
with provenance, concept merge/split/create with *global* context, decay and
strengthening. Every decision is emitted as an event before it becomes a row.
Model-tiered — Haiku-class for the mechanical extraction work, Sonnet-class for
the one judgment-heavy merge/split pass — and run through the Batch API at half
price. About $0.03–0.05 a night. Re-consolidating the entire corpus costs $3–5,
which is deliberately cheap enough to redo whenever the models get better.

**The event log is the backbone.** The semantic store is a materialised view of
it. `rebuild` truncates the semantic tables and replays every event to reproduce
it exactly. A `MERGED` event records both concept snapshots — the loser's history
survives. This is what makes "how did my thinking change" answerable at all, and
it's the exact thing v1's destructive merge destroyed.

**Recall costs nothing.** Vector seed over claims and concepts, then spreading
activation through the relation graph — decay per hop, weighted by strength,
recency and state. Local, no API call. Two-hop activation is where the
non-obvious connections come from.

**Headless and MCP-first.** There is no UI. The MCP server *is* the product, and
Claude is the client. Which turned out to matter more than I expected, for a
reason that's worth its own section.

### Retrieval nobody asks for

The hard part of a memory system that lives inside an assistant is not retrieval
quality. It's that **the model doesn't reach for the tool.**

A perfect memory that gets queried once a week is worth nothing. So the trigger
conditions had to be engineered into the tool descriptions themselves — not
"searches your notes," but *"call this whenever the user shares an opinion, idea,
plan or draft on a topic they may have thought about before — before composing
your response."* Same for the server-level instructions.

Then two-stage retrieval, so calling it speculatively is actually cheap: `recall`
returns compact headlines, roughly 50 tokens a hit, with why-now signals — 🔁 for
a recurring claim, 🕰️ for thinking that's been dormant. `assemble_context` is the
escalation when a hit deserves the full picture with provenance.

And receipts phrased as markdown written *for the model to narrate back*, because
the echo is the product and the model won't surface it unless you make surfacing
it the path of least resistance.

None of this is retrieval research. It's interface design for a non-human user,
and it's most of what determined whether the system got used.

---

## 4. The eval, and the result that changed my mind

This is the part I'd want to be judged on.

By late June I had a working consolidation pipeline with one step I was uneasy
about. **Membership** — deciding which claim belongs to which concept — was still
owned by an LLM call. Centres and anchors felt geometrically solid. Membership
felt like I was paying a language model to do clustering.

So I asked the obvious question: can pure geometry match the LLM partition?

To answer it I had to build the thing I should have built first — an eval
harness. Coverage@B against three hand-built gold sets: narrow queries (20),
broad thematic queries (6), and paragraph-length queries (14), plus a grep
baseline so I'd know whether any of this beat `grep`.

The LLM partition scored **79 / 33 / 75**.

I then spent a session trying to beat it with geometry, and the log of that
session is more useful than any of my successes:

- **Distortion-minimising clustering is the wrong objective.** At equal rate,
  geometric vector quantisation achieved *lower* distortion than the LLM
  partition (0.476 vs 0.547) and *worse* retrieval coverage (57/33/62 vs
  79/33/75). The LLM partition is rate–distortion-suboptimal and
  retrieval-superior. Minimising distortion walks away from retrieval.
- Which reframed the whole problem: I had been doing **source coding** —
  compress, remove redundancy — when retrieval is a **channel coding** problem.
  You want *structured redundancy* so the signal survives a noisy query. That
  single reframe is the most valuable thing I got out of five months.
- **The right primitive isn't proximity, it's reconstruction.** Asking "can this
  region rebuild this claim?" instead of "which centre is nearest" moved narrow
  from 57 to 71. Half the gap to the LLM, closed by changing the question.
- **Anchor strategy was decisive and I nearly missed it.** Farthest-first
  k-center anchors seek outliers, which is pathological for thematic frames — it
  tanked broad coverage to zero and made me write "redundancy is refuted" in my
  notes. It wasn't. With density-based anchors, the same redundancy mechanism
  took broad from 17 to 50. I had run the experiment correctly and drawn exactly
  the wrong conclusion, because a confound in a different layer was doing the
  work.
- **No intrinsic geometric metric predicts retrieval quality.** Silhouette
  correlated ~0 with coverage. Davies-Bouldin *anti*-correlated. Masked
  reconstruction anti-aligned with the exact gold type it was designed for. Every
  cheap proxy I hoped would let me stop running the expensive eval was either
  useless or actively misleading. All silhouettes were negative — concepts are
  not geometrically separable, and the retrieval-best partition was the
  geometrically worst-separated one.

**And I had to kill my favourite feature.** "Bridges" — latent links between
concepts that never co-occur in a note — were the idea I was proudest of. The
trace showed they *were* being traversed: 118 edge expansions across the broad
queries, shifting the salience of 20–60 nodes. And the materialised top-12 result
set was **identical, on every single query, with and without them.**

My first explanation for why was wrong. I blamed a gating term; turning it off
changed nothing. The actual mechanism was the distinctiveness penalty —
`1/(1+ln degree)^γ`. Bridged concepts are low-distinctiveness by construction,
and adding a bridge edge raises the target's degree, which lowers its
distinctiveness further. The feature was self-defeating. Tuning retrieval to
*favour* bridges made broad coverage monotonically worse, because promoting a
vague bridged concept evicts a precise covering claim.

The suppression was correct. My feature was wrong. I deleted the generation code,
the boost constant, and the MCP tool on 2026-06-27, and wrote the corrected
mechanism into the findings doc next to my original wrong explanation, because
the wrong explanation is part of the result.

The honest verdict on the whole exercise: geometry beats the LLM on one axis,
loses on two, and is Pareto-incomparable rather than better. The remaining
ceiling is the embedding's **meaning limit** — it flattens negation, number and
scope, and no amount of clustering recovers what the features never encoded. You
cannot out-cluster a feature blindness.

One caveat I'll state before anyone else does: the broad gold set has six scored
queries. A 33→50 move is one query. I treat broad results as hints, and I wrote
that constraint into the findings doc rather than reporting the number cleanly.

---

## 5. fph — where memory stopped being enough

*July 14 onwards. 30 commits.*

Two days after the last v2 commit I started something that had nothing to do with
memory systems, or so I thought.

fph — "frontier problems of humanity" — is an attempt to rederive Maslow's
hierarchy from a single drive, map each tier to documented civilisational
failures, and use that to choose one problem to work on personally. Thirty-nine
research files across five tiers. Entirely powered by Slate underneath: recall
before writing on any topic, verbatim capture of my own thinking, provenance on
everything.

What I actually discovered is that I built something I hadn't planned to.

Every research file in fph uses **exactly the same section headers, in the same
order, verbatim**. How this need has been threatened. How humanity evolved to
deal with it. Where it worked. Where it fails today. And one rule that turned out
to matter more than the rest:

> `### Where it worked` is mandatory in every file. Writing "no positive control
> found" is an acceptable entry; omitting the section is not.

That rule exists because I drafted tier 1 claiming it contained a single positive
control. It contains at least seven. The error changed a conclusion. A framework
built only from failures cannot distinguish a hard problem from a neglected one.

Look at what that rule actually is. It is a **slot that must be filled, where an
explicit null is a valid fill and silence is not**. It is a system for
representing what the work still owes me.

I didn't design that as structure. I designed it because I know something about
myself that my own notes had already recorded before I would have admitted it:
I have a history of abandoning projects, and a habit of overlooking small wins
while fixating on large unresolved problems. fph's rules — one step per sitting
is a complete sitting; solution pulls get logged, never chased; consolidate only
when a tier is complete — are commitment infrastructure. I was building defences
against my own failure mode.

They came out looking like editorial structure. That is the finding.

---

## 6. What the book problem named

So: the post about a long-form writing agent.

Three things a book needs. Personal context — that's Slate, that's the last five
months, that's an event-sourced memory with provenance and consolidation.
Research and verification — that's a solved-enough problem and I run it daily.
Structure — I'd assumed that was the missing piece, and then realised I'd built a
hand-rolled version of it in fph without ever calling it that.

Here is the claim the book problem let me finally state:

> **Long-horizon AI work doesn't fail because context runs out. It fails because
> nothing represents what the work still owes.**

Memory is retrospective. Every memory system I know of, mine included, answers
*"what have I already thought about X?"* That is a genuinely hard problem and I
have the eval numbers to show how hard. But it is the wrong question for work
that unfolds over months.

The question long work needs is prospective: **what is still unfilled?** Which
argument has no evidence behind it. Which claim has been asserted twice and
supported zero times. Which section is empty not because it's unimportant but
because the only person who can fill it hasn't been asked the right question yet.

That's not retrieval. It's an obligation graph — a structure whose nodes are
commitments, whose slots are typed, and whose unfilled slots are *computable*.
And the moment you can compute the unfilled slots, the agent's most important
behaviour falls out for free: it knows what to ask you, and when it has earned
the right to interrupt.

That routing is the whole product. Each gap resolves to one of three things:

- Fillable from public fact → a background research task. The model does this.
- Fillable only from the author's life → a queued question. Only the human does
  this, and it's high-latency — days, not seconds.
- Not fillable by either → the structure itself is wrong. That's the most
  valuable output of the three.

An agent that writes prose for you produces a book you'll disown by chapter four,
and worse, one whose emptiness is invisible because it reads fine. An agent that
knows what your book still owes and asks you ten good questions over a month is a
different kind of thing entirely.

---

## 7. What I'd claim, and what I wouldn't

What I'd claim: I've built and shipped a personal memory engine with an
event-sourced semantic store, a consolidation pipeline, a spreading-activation
retrieval layer, an MCP interface that a language model actually reaches for, and
— the part I care about — an eval harness rigorous enough that it killed my
favourite feature and overturned two of my own conclusions. Then I used it hard
enough on a real long-horizon project to find the next wall.

What I wouldn't claim: this is n=1. One user, one corpus, and I wrote the gold
sets I'm graded against. Six scored broad queries is not a benchmark. fph has
existed for two weeks. The obligation-graph idea is a design I can argue for, not
a system I've measured.

And I'd resist the tidy version of this story. I did not set out to solve
long-horizon agent memory. I set out to be able to use my own notes, hit a wall,
rebuilt, measured, was wrong twice, and then read a job post about writing books
that told me what I'd been doing.

The thread was real. I just couldn't see it from inside.

---

*Slate: 46 commits, Feb–Jun 2026. Slate v2: 66 commits, Jun–Jul 2026. fph: 30
commits, Jul 2026 onwards.*
