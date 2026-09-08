# Scoreboard

Written 2026-09-06, in response to one audit finding: **nothing in this repo defines what success looks like, so the one failure mode the file layout actively rewards is invisible from inside it.**

That failure mode: the repo accumulates leaves and actors indefinitely, stays fully compliant with its own manual, and catalyses nothing. Every incentive in the method points at depth — a longer leaf is more obviously "work" than an introduction that took one email. Nothing counted the introductions, so nothing would have noticed.

The counters below are **deliberately honest at zero**. `connections engaged: 0` is the point of writing this file, not an embarrassment to fix before publishing it.

## Counters

Counted by hand until the portal build exists (`03-portal.md` §1), then generated as queries over `problems/index.db`. Counters 1, 2 and 7 read private tables, which load and FK-enforce at build but are absent from the published database — so the public scoreboard renders those three from a number written here by hand, not from the shipped file.

| # | Counter | Reads | Now (2026-09-06) |
|---|---|---|---|
| 1 | **Connections engaged** | `connection.state == engaged` | 0 |
| 2 | **Connections live** | `state in [proposed, introduced]` | 0 |
| 3 | **Actors tracked** | `actor.depth == tracked` | 0 |
| 4 | **Actors reachable** | tracked actors with ≥1 `sources[].status == live` | 0 |
| 5 | **Leaves researched / total** | `leaf.status == researched` over all leaves | 0 / 0 |
| 6 | **Needs with ≥1 leaf** | over 36 in `needs.yaml` | 0 / 36 |
| 7 | **Open asks matched** | `actor.needs[].state == open` with a candidate offer identified | 0 |
| 8 | **Stale** | leaves `status: stale` + actors `last_checked` > 6 months | 0 |

## What each counter is for

- **1 and 2 are the only ones that measure the actual job.** Everything else measures the archive. If 5 and 6 climb for six months while 1 and 2 stay at zero, the project has become a research repo with a catalyst story attached, and the response is to run `02-connect-pass.md` on what already exists — not to write more leaves.
- **3 vs 4** — the reachability ratio. In the one executed follow-list pass (`03-air.md`), 11 of 19 actors had no reachable public channel. If that ratio holds, the constraint on the catalyst role is not knowing who to connect; it is being able to reach them at all, and that is a different problem needing a different fix (fieldwork, warm intros, phone).
- **5 vs 6** — depth against breadth. 6 climbing while 5 stays flat is healthy early: stubs are real records, and goal 1 (a browsable list of problems) can ship long before goal 2.
- **7** is the leading indicator for 1. An ask with a candidate offer is a connection waiting to be written.
- **8** is the decay rate. A researched leaf asserting `gap: none` against an actor that has since shut is worse than a blank.

## Cadence

Update at the end of any sitting that changes a count. Not scheduled — the file is short enough that it costs nothing, and a scheduled review would just be another thing to defer.

## What this file deliberately does not do

No target numbers, no dates, no "N connections by Q2". A target on a counter this new would be invented, and inventing one is how a scoreboard starts driving the work instead of describing it. Revisit once counter 1 has been non-zero for three months and there is a real base rate.
