---
name: crawl
description: Crawl the social-impact sector as a network — fan out from a seed through funders, boards, cohorts, portfolios and conveners, writing an actor record with follow channels for each person and org found. Use for mapping funds, catalysts and the enterprises they back, rather than working an fph leaf. Invoked as /crawl <seed> [waves: N].
---

# /crawl — run the network crawler

Thin launcher for the `impact-network-crawler` agent. All the method lives in
`.claude/agents/impact-network-crawler.md`; this file only builds the call so the
work runs in the agent's own context and not in the user's conversation. Each
pass costs 60–115k tokens of searches and writes — that is exactly what must
stay out of here.

## Arguments

`/crawl <seed> [waves: N] [segment: <slice>]` — everything optional but the seed.

- **No seed given?** Read `problems/actors/_crawl-state.md`, show the user the
  top few LEADS with their edges, and ask which to seed from. Do not pick for
  them; the lead list is long and the choice is a judgment about what they care
  about.
- **Waves** default to 2. Above 3 needs the user to have asked for it explicitly.
- **`/crawl status`** — don't launch anything. Report from `_crawl-state.md`:
  how many leads stand, what the last pass did, and what was pruned. Cheap.

## Before launching

1. Read `problems/actors/_crawl-state.md` — the accumulated handover. It carries
   LEADS, EDGES, PORTFOLIO names, PRUNED and DEAD ENDS from every prior pass.
2. Confirm the corpus is clean: `npm run validate`. If it already has errors,
   say so and fix or report them first — otherwise the agent's own "zero errors
   is the bar" check cannot tell its mistakes from pre-existing ones.

## The call

Spawn `impact-network-crawler` via the Agent tool with a prompt that carries:

- The seed, wave count and segment.
- **`problems/actors/_crawl-state.md` as required first reading**, with the
  instruction to append its new leads, edges, prunes and dead ends there at the
  end, **and to retire in place any lead it wrote** rather than only appending a
  new section. That file is the only thing connecting one pass to the next, and
  nothing else retires a lead — three actors sat in LEADS marked "never written"
  for a day after they were written and committed, and a whole pass's top
  priority went on rediscovering them.
- The current corpus size and that it validates clean, so the agent knows any
  error it sees is its own.
- **The recurring failure modes**, restated every time — each has broken a pass:
  - `ecosystem_role:` missing. It is optional in the schema, so `npm run validate`
    will NOT catch it; the loader's "attaches to nothing" warning is the tell.
    It went missing on 30 records silently once.
  - `depth: tracked` with `needs: []` — a build error. Default `registry`;
    `tracked` is earned by a sourced, quotable ask, never by importance.
  - `kind: twitter` — the enum value is `x`.
  - `status: live` for a post whose date was not seen — use `unconfirmed`.
  - Skipping a person because their handle is unverified — write them as
    `registry` with `status: unconfirmed`. The name, affiliation and follow link
    are the deliverable.
- A reminder to check `problems/actors/_excluded.yaml` and any `depth: excluded`
  record during dedupe. Exclusions are final and must never be re-proposed.
- `npm run validate` then `npm run follow` at the end.

## After it returns

**Verify rather than relay.** Three of the first five passes misreported their
own output — one claimed all files valid against 22 errors, another reported
roles it had never written to disk. Check before telling the user anything:

```
npm run validate                                   # 0 errors is the bar
grep -L "^ecosystem_role:" problems/actors/<new>.md # must return nothing
grep -l "kind: twitter" problems/actors/*.md        # must return nothing
```

A pass that reports a record as "already existed, no action needed" is reporting
a stale lead, not doing nothing wrong — check `git log --oneline -1 -- <file>` to
see when it actually landed, and make sure the lead got retired in
`_crawl-state.md` so the next pass doesn't spend on it too.

Then report what landed, what it pruned, and what it deliberately did not write
— the PRUNED and NOT WRITTEN blocks are decisions the user should see, not
noise to trim. Offer a commit when a pass adds more than a handful of records.
