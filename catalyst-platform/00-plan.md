# Catalyst platform — plan

Model, agreed 2026-09-05: I can't commit to one frontier problem. My role is catalyst across three legs (activism, institution-building, enterprise). To be a catalyst I need awareness — following people/orgs working each sector, understanding what they need and can offer, and reaching out to connect them to the right help. The output is a bigger Seed Savers Club: a platform listing every frontier problem, the research behind it, and everyone working on it — what they need, what they can offer, how to reach them. Built for myself first, made public/detailed enough to be useful, with more of me hopefully joining.

Platform must have:
1. A list of problems — easy to discover & browse.
2. Detailed research per problem — ever-expanding.
3. A list of people & orgs working the problem — recent updates, what they need, what they can offer.

## Representation gaps

Focusing on people close to the ground brings the under-represented into focus. Two different kinds of "gap," not one:
- **Coverage gap** — someone's working it, platform hasn't found them yet. A viewer can submit a name/org to fill this.
- **Representation gap** — no actor exists at the right unit yet (e.g. rental discrimination in tier 1 — no representation at any unit). Nobody can be submitted because nobody exists. Filling this means asking people if they're facing the problem, then asking one of them to represent it — fieldwork, not a form. **Future state**, not in the initial build.

The two must stay distinguishable in the data model — an empty representation-gap slot is a finding, not a stub waiting for a submit button.

## Division of labor

**Stays with me — non-delegable**
- Outreach conversations, trust-building (the lived-experience/local-connect gap from Seed Savers Club).
- Frontier-problem judgment: what's a real finding, hypothesis survival, leg/routing selection, the four-question gate.
- Deciding whose ask is real vs. noise, which relationships to invest in.
- Public voice on anything published as synthesis.

**Agent-suited**
1. **Tier research drafting** — already codified in `process-tier` skill (history → mechanism → gap → requirements).
2. **Commercial-landscape + social-media-tracking passes** — find named actors, funding/status, active platform, log to follow-list. A "scout" agent per problem file.
3. **Actor monitoring** — scheduled agent checks tracked actors' public output for stated needs/asks, flags them. Keeps research "ever-expanding" without manual re-reading.
4. **Outreach drafting (not sending)** — agent drafts first-contact from known actor context; I review and send.
5. **Site/platform build** — converts repo markdown into the public browsable structure. One-time-ish engineering task.

## Sequence

1. Close one problem end-to-end first (research → scout → monitor → draft outreach) as the pilot — starting point TBD, not yet locked to a specific need file.
2. Once that loop is proven, build and publish the website from it.

Pace: one step per sitting, per fph's working-with-the-user discipline. Don't rush past step 1 to get to the website.
