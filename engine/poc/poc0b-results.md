# PoC-0b — the 120-query SearXNG run

`04-worker-build-plan.md` §2 PoC-0, with its three additions (draw from
already-researched actors so the run has an answer key; compute set cover
against top-n; record every JSON response). This document covers the harness
build, its 2-actor dry run, and the completed full 120-query run (results
below).

## Method

**Files** (`engine/poc/`):
- `poc0b-sample.json` — 20 actors + per-actor answer key, drawn from
  `problems/actors/*.md`.
- `poc0b_families.yaml` — 6 query-family templates (throwaway PoC copy; NOT
  `engine/search/families.yaml`, which track D owns).
- `poc0b_run.py` — the runner: 20 actors x 6 families = 120 queries against
  the local SearXNG instance, throttled/jittered, resumable, one JSON response
  per query on disk.
- `poc0b_analyse.py` — offline analysis over the recorded responses: the
  `unresponsive_engines` curve, per-family predicted coverage against the
  answer key, and the set-cover-vs-top-n comparison (`03-worker.md` §5a/§5b).

**Selection rule for the 20 actors** — drawn from `problems/actors/*.md`, not
the candidate queue, per the plan doc's first addition: the candidate queue
holds only 11 rows, all unresearched, so there is no answer to check search
results against. Two groups:

- **12 "rich" actors** — every one has both a substantive `## Status`
  (funding/scale claim) and a substantive `## How to reach them` section.
  Spans the catalyst-layer ecosystem this corpus is currently richest in
  (impact VCs/accelerators/funders: Anthill Ventures, SELCO Foundation, Shell
  Foundation, Dasra, Villgro, Acumen, Rainmatter Foundation, Omnivore), one
  enterprise (A2P Energy), one named individual founder (Harish Hande), one
  government institution (Employees' State Insurance Corporation), and one
  activism collective with a disclosed funding line (Warrior Moms).
- **8 deliberately thin / affected-led / small-local actors** — per the plan
  doc's explicit question of whether these surface anything at all, and the
  risk that a sample of only well-known orgs answers the wrong question. Two
  affected-led victims' associations with **no independent channel at all**
  (Khambhat Silicosis Victims Association, India Asbestos Victims
  Association — both reachable only through an intermediary org, which the
  actor files themselves flag as a finding about who gets to be reachable);
  one affected-led collective reachable only through a proxy individual's
  stale social feed (Silicosis Peedit Sangh, via Amulya Nidhi); one large but
  informally-organised farmers' union (BKU Ekta Ugrahan) and its named
  president as an individual (Joginder Singh Ugrahan); two individual
  affected-led/citizen activists with only personal social channels, no org
  infrastructure (Bhavreen Kandhari, Jyoti Pande Lavakare); and one small
  donation-funded NGO (Care for Air).

Per-actor answer keys in `poc0b-sample.json` are extracted verbatim from each
actor's own file, grouped into six categories (`identity`, `money`, `people`,
`viability_asks`, `failure`, `reach`) that the 6 query families are checked
against. Where a file states no answer for a group (e.g. "no sourced ask
found"), the key records that explicitly rather than leaving the field
absent, so the analyser can distinguish "no ground truth to check" from "an
unchecked miss."

**The 6 query families** (`poc0b_families.yaml`), taken verbatim from
`03-worker.md` §3's "Actor families" table (all 20 sample actors are
actor-kind, so the problem-family templates in that section are out of
scope here): `identity`, `money`, `people`, `viability`, `failure`, `reach`.
The 7th family in §3 (`asks`) is dropped from this PoC to land exactly on
20 x 6 = 120; it is a candidate addition for the real `engine/search/families.yaml`
if track D wants full §3 coverage.

**Engine set and throttle**, per `poc0a-results.md` and its Addendum 2 (which
supersedes Addendum 1): the final working set is **4 engines — `bing`,
`brave`, `google`, `mojeek`** (`duckduckgo` and `qwant` are structurally
blocked and excluded; do not try to fix them). Two distinct throttle effects
were found there and are kept separable in this harness rather than
collapsed into one number:

1. A **per-request spacing floor of >=2.0s** (confirmed against mojeek's
   180s-suspension-then-recovery behaviour).
2. A separate, **rolling cumulative-session-volume effect** on google/brave —
   both degrade after enough total queries within one session even at
   2.5-4.0s spacing, independent of per-request spacing. This is explicitly
   left for the real 120-query run to measure.

`poc0b_run.py`'s `THROTTLE_BASE_S` / `THROTTLE_JITTER_S` constants (top of
file) are set to a 2.0-4.0s jittered range, matching poc0a's verified band
while enforcing the 2.0s floor. Every recorded query also carries a wall-clock
timestamp and a running request-index for this run, specifically so the
analyser (or a human) can later separate "failed because two requests were
too close together" from "failed because this session had already spent too
many requests" — the second is one of the results the real run exists to
produce, not something to guess from the dry run.

**Silent-drop detection**: per `poc0a-results.md`'s dated addendum,
`unresponsive_engines` is only a lower bound — an engine can return zero
results without appearing in that list. `poc0b_run.py` therefore also
records `engines_seen_in_results` (from each result's `engine`/`engines`
fields) and computes `silently_absent_engines = configured_engines - seen -
unresponsive`, so a silent drop-out is visible in the recorded JSON even when
SearXNG's own health signal misses it.

## Dry-run observations (2 actors, 12 queries)

Ran `python3 poc0b_run.py --limit 2` against the local instance
(`localhost:8080`, container `fph-searxng-poc0`, current 4-engine
`settings.yml`). All 12 queries completed, all 12 response files landed in
`poc0b-responses/`, and `poc0b_analyse.py` ran end-to-end over them with no
network calls, producing all three required outputs (unresponsive curve,
per-family coverage, set-cover-vs-top-n). Re-running the same command
confirmed resumability: all 12 queries were skipped as already-on-disk.

Findings from the dry run itself (12 queries is far too few to be the real
result, but the harness behaviour is worth recording):

- **The silent-drop detector fired immediately and correctly.** `mojeek`
  appeared in `silently_absent_engines` on 10 of 12 queries — present in
  neither `unresponsive_engines` nor any result's `engine`/`engines` field —
  exactly the failure mode poc0a's addendum described. This is strong early
  evidence the harness's extra field earns its keep: trusting
  `unresponsive_engines` alone here would have read as "mojeek is fine," when
  in fact it silently returned nothing on 10 of 12 queries.
  - Note on this itself as a dry-run artifact: a 12-query dry run with no
    warm-up is not the setting poc0a validated mojeek in (which needed >=2.0s
    spacing and a request past its own suspension window) — so this may be
    the suspension-window effect recurring at dry-run scale rather than a new
    finding. The real 120-query run, sustained over more wall-clock time,
    should reproduce this at scale rather than compound it once out of the
    suspension window; the curve output makes the trajectory visible whichever
    it is.
- **Visible cumulative-volume degradation of google and brave within 12
  queries** — `google` was unresponsive on all 12; `brave` answered the first
  2 queries (`n=26`, `n=30` results) then dropped to `unresponsive` for the
  remaining 10, with result counts falling to `n=10` (effectively bing alone)
  and one query returning `n=1`. This is consistent with, and at far smaller
  volume than, poc0a Addendum 2's finding that google/brave degrade with
  session volume independent of per-request spacing — the real run's
  first-third/middle-third/last-third breakdown (computed by
  `poc0b_analyse.py` §1) is what should characterise this properly; the dry
  run only confirms the effect is visible at all, immediately, at this
  scale — not that 12 queries defines its shape.
- **Per-family predicted coverage on 2 actors is not meaningful** (2
  observations per family) but ran without error: `identity` matched 2/2,
  `money` and `reach`/`viability` 1/2, `people` and `failure` 0/2 — plausible
  given `google`+`mojeek` were down for most of these queries and the
  people/failure answer-key text (founder names, "no failure stated") is
  exactly the kind of proper-noun/negative-claim text least likely to survive
  into a snippet when only `bing` is answering.
- **Set-cover beat top-n on 1 of 2 actors at both n=3 and n=5** (tied, never
  worse, on the other) in this tiny sample — directionally consistent with
  `03-worker.md` §5b's prediction, but 2 actors is not evidence either way;
  this is the comparison the real 120-query run is for.

No code changes were made to fix google/brave/mojeek's degradation — per the
task brief, this run does not touch engine config, only records what
happened, and per the coordinator's correction, the current engine set
(`bing`, `brave`, `google`, `mojeek`) and the 2.0s spacing floor are taken as
given from `poc0a-results.md` Addendum 2, not re-derived here.

## Real-run results — unresponsive_engines curve

119/120 queries (99%) recorded at least one unresponsive engine. This is flat
across the run, not climbing: first third 40/40, middle third 39/40, last
third 40/40. The one exception is `joginder-singh-ugrahan`/`identity` (`-`, no
engine reported unresponsive).

This answers the question the dry run left open (§68–89 above) and kills the
rolling cumulative-volume hypothesis at this throttle: `poc0a-results.md`
Addendum 2 predicted google/brave degrading further as a session accumulates
queries, independent of per-request spacing. At the 25s base / ±5s jitter
throttle used for this run, degradation is present from query 1 and does not
worsen with volume — every third of the run carries essentially the same rate.
Either the degradation ceiling is already reached at low volume, or the
2.0–4.0s spacing the dry run used (not the 25s spacing used here) is what
actually drives the rolling effect, and 25s spacing is generous enough to sit
below whatever budget triggers it. This run cannot distinguish those two; it
only establishes that at 25s spacing, the rate is flat.

**`mojeek` was silently absent — in neither `unresponsive_engines` nor
`engines_seen_in_results` — on nearly every query** (visible row-by-row above:
`['mojeek']` in the `silently_absent_engines` column for all but a handful of
actors, and outright absent from the `unresponsive` column too on rows like
`bhavreen-kandhari`, `care-for-air`, `jyoti-pande-lavakare`). This is the third
independent reproduction of the `03-worker.md` §4 obligation-2 defect (an
engine can return nothing without ever appearing in the health signal): first
in `poc0a-results.md`'s dated addendum, then in this run's own 12-query dry
run (§112–118 above), now confirmed at full scale. `unresponsive_engines`
alone is not a trustworthy engine-health signal for `mojeek`; any consumer of
this field needs the `silently_absent_engines` cross-check, not just this PoC.

## Real-run results — per-family predicted coverage

| family | covered/checkable | rate |
|---|---|---|
| viability | 19/20 | 95% |
| identity | 17/20 | 85% |
| people | 9/15 | 60% |
| reach | 11/20 | 55% |
| money | 5/18 | 28% |
| failure | 5/18 | 28% |

This is the more important result of the run, more important than the §5b
comparison below, because it locates the bottleneck.

`money` maps onto the `actor-status` question bucket, and PoC-1/1b measured
`actor-status` as the **best-performing retrieval bucket in the whole
pipeline** (AUC 0.977) — near-perfect at finding the funding paragraph once a
page is in hand. Here, at only 28%, search itself is failing to surface a page
that carries funding information at all, three-quarters of the time. Put the
two together and the conclusion is explicit: **the bottleneck is stages 1–2
(query planning / search), not stage 5 (passage retrieval).** PoC-1's own
stated caveat — "necessary and not sufficient... the §7 downstream-coverage
sweep still has to run on real fetched pages" (`04-worker-build-plan.md` §2) —
lands exactly where it predicted it would. Further tuning of the retrieval
encoder or chunking buys little on `money` until search coverage improves;
the two-stage view that treats poor `money`/`failure` numbers as a retrieval
problem would be diagnosing the wrong stage.

`failure` at 28% independently corroborates PoC-1c, which is a different
method entirely: there, `q13_failure_note` scored an AUC of 0.243 on
labelled-chunk retrieval, with failure vocabulary present in only ~10 of 289
corpus files. PoC-1c measured absence *within* files already collected; PoC-0b
measures absence *at the search stage*, before any file is collected. Two
unrelated methods agreeing on the same conclusion — organisations do not
publish their own failures, so there is very little to retrieve regardless of
which stage is asked to find it — is a stronger result than either alone.
Recommendation: stop treating `failure` as a retrievable search/passage
question; it is closer to a structural absence that the worker should record
as such (per `02-questions.md`'s absence rule) rather than keep querying for.

## Real-run results — set cover vs top-n

At n=3: set-cover beats top-n on 3 actors, ties on 17, never loses.
At n=5: set-cover beats top-n on 2 actors, ties on 18, never loses.

The margin is small and the honest shape is: for most of the 20 actors in this
sample, top-n and set-cover return the identical answer, because the
well-covered "rich" actors (impact VCs, funders, the enterprise, the
institution) have enough distinct high-ranking pages that top-n's homepage-
duplication failure mode (§5b's stated prediction) doesn't bite — there's
already enough diversity in the top ranks to cover most families either way.

But look at **which** actors it wins on, not just how many: `bhavreen-kandhari`
(3/6 at top-n → 6/6 with set-cover, n=3), `bku-ekta-ugrahan` (5/6 → 6/6, n=3),
and `employees-state-insurance-corporation` (5/6 → 6/6, both n=3 and n=5).
Two of these three are exactly the thin / affected-led candidates the sample
was deliberately built to include (`bhavreen-kandhari` is an individual
citizen activist with no org infrastructure; `bku-ekta-ugrahan` is an
informally-organised farmers' union) — precisely the population where a
homepage or a single dominant page is likely to crowd out the other coverage
that top-n would miss and set-cover recovers. `employees-state-insurance-corporation`
is the government institution, a different failure shape (a large official
site with duplicate-looking top results across families) but the same
qualitative fix.

**§5b survives.** Set-cover is never worse than top-n in this run, and on
average the win is thin — but the honest framing is not "set-cover barely
helps," it is "set-cover's entire measured value on this sample concentrates
on exactly the actors the platform exists to reach, and is invisible on the
well-covered ones." Recommendation: build it — not because it wins on
average, which it barely does, but because averaging across a sample weighted
toward well-covered actors is the wrong way to read this result. A production
sample skewed further toward thin/affected-led actors (the population §16
step 0 named as the reason to run this PoC at all) would likely show a larger
gap.

## Real-run results — throttle floor and cumulative-volume budget

**The throttle question is answered.** No volume-driven degradation was
observed at a 25s base / ±5s jitter spacing: 119/120 queries carried a failure
signal, flat across thirds (40/40, 39/40, 40/40). The engines were already
degraded at query 1, not progressively degrading — whatever caused the
near-universal unresponsiveness (google/brave near-blanket blocking, per the
row data above) was present from the start of the run, not something the
25s spacing accumulated into over 120 queries. The rolling cumulative-session-
volume hypothesis from `poc0a-results.md` Addendum 2 is dead **at this pace**
— it cannot be ruled out at the tighter 2.0–4.0s spacing the dry run used,
since this run deliberately used a much more conservative throttle and did not
re-test the tighter band at scale.

**A correction to §14's framing of the `unresponsive_engines` floor.** §14
frames the open decision as picking a number for a floor "above which a run is
flagged degraded." At 99% of queries (119/120) carrying at least one
unresponsive engine, a floor defined on *engines failed per query* rejects
essentially the entire run — there is no threshold on that axis that both
excludes bad data and retains any data at all, at this engine set's current
health. The floor cannot be usefully defined on engines-failed; it must be
defined on **engines that returned** (i.e., a minimum count of substantive
engines answering per query, not a maximum count failing). This run does not
pick that number — per `04-worker-build-plan.md` §2's instruction not to bring
one in advance — but it does establish which axis the number belongs on, which
§14 as written does not specify.

---

`poc0b-responses/` (120 recorded JSON responses, one per query) doubles as the
replay corpus named in `04-worker-build-plan.md` §2: track D's unit tests can
run against these fixtures with no network call, and a later SearXNG/provider
swap has a real baseline — not an invented one — to diff against.

---

## Command to launch the full run

```
cd engine/poc
python3 poc0b_run.py
```

(No `--limit` flag runs all 20 actors x 6 families = 120 queries. It is
resumable — if interrupted, re-running the identical command skips every
query whose response file already exists in `poc0b-responses/`.) Then:

```
python3 poc0b_analyse.py
```

to produce the unresponsive curve, per-family coverage, and set-cover-vs-top-n
comparison over the full run, and paste the output into the empty headings
above.
