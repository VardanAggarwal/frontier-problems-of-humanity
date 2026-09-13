# PoC-0a — SearXNG infrastructure + shape verification

Scope: infra stand-up and JSON shape check only, per `04-worker-build-plan.md`
§2 PoC-0. The 120-query experiment (engine curve, coverage, set-cover-vs-top-n)
is a **separate later task**, not run here.

## Start / stop

```
cd /Users/vardanaggarwal/fph/engine/poc/searxng
./run.sh start   # docker run -d, port 8080
./run.sh logs    # follow container logs
./run.sh stop    # docker stop + rm
```

**Why a `run.sh` script and not `docker-compose.yml`:** this colima docker
context has neither the `docker compose` plugin nor a standalone
`docker-compose` binary (`docker compose up -d` failed with `unknown
shorthand flag: 'd'` — it silently fell through to the base `docker` CLI).
A plain `docker run` script needs no extra tooling and is one file.

Instance is currently **running**: `curl http://localhost:8080/search?q=x&format=json`
returns 200.

## Files

- `settings.yml` — the only override file, merged over SearXNG's shipped
  defaults via `use_default_settings`. Confirmed by pulling and diffing the
  image's own `settings.yml` (`default-settings.yml`, `engines-section.yml` —
  kept alongside for reference, not consumed at runtime).
- `run.sh` — start/stop/logs.
- `sample-response.json` — one full captured response (money-family query
  against Anthill Ventures), pretty-printed.

## Engine set (general category, ~5)

Cut via `use_default_settings.engines.keep_only`, then re-enabled the three
that ship `disabled: true`/`inactive: true` upstream:

| Engine | No API key | Why chosen |
|---|---|---|
| `duckduckgo` | yes | enabled by default upstream; broad general index |
| `brave` | yes | enabled by default upstream; independent index, not a Bing/Google reskin |
| `google` | yes | ships `disabled: true` upstream (churn risk on public instances); broadest index, best odds of surfacing a small org's own site |
| `bing` | yes | ships `disabled: true` upstream; complements google's crawl gaps, esp. `.in` domains and Indian press |
| `mojeek` | yes | ships `disabled: true` upstream; small independent index — kept over `qwant`/`startpage`, which ship disabled/inactive specifically for CAPTCHA churn |

Rate limiter: `server.limiter: false` (explicit — also the shipped default;
this is a private local instance, never exposed).

## JSON field map — verified against real captured responses

1. **`score` per result: present, and monotone with rank/agreement, not the
   list index.** Sample money-family query: scores `1.0, 1.0, 0.682, 0.5,
   0.333, …` in list order — descending, ties at the top for two
   single-engine hits, and the *dip-then-recover* pattern (`0.682` at
   position 3 having `positions: [4, 11]`, i.e. it ranked lower in its own
   engine but scored on an amalgam) confirms `score` is SearXNG's fused
   ranking signal, not a copy of the JSON array position. Confirms
   `03-worker.md` §4's rule directly: `rank` must derive from `score`.
2. **`unresponsive_engines`: present, shape is a list of `[engine_name,
   reason_string]` pairs**, e.g.
   `[["bing", "HTTP connection error"], ["duckduckgo", "CAPTCHA"]]`. Reason
   strings seen this session: `"HTTP connection error"`, `"Suspended: HTTP
   connection error"`, `"CAPTCHA"`, `"access denied"`, `"Suspended: access
   denied"` — i.e. the reason string itself already distinguishes "blocked"
   failure modes from each other, which is exactly the distinction §4
   obligation 2 needs recorded per query.
3. **Result fields**: `url`, `title`, `content` (snippet), plus `engine`
   (single, the "winning"/first-seen engine), `engines` (list — SearXNG can
   report multiple engines converging on one URL), `score`, `positions`
   (list — this URL's rank *within* each contributing engine), `category`,
   `template`, and several always-empty-here fields (`img_src`,
   `publishedDate`, etc.). Top-level payload also carries `answers`,
   `corrections`, `infoboxes`, `suggestions` alongside `results` and
   `unresponsive_engines`.
4. Nothing above required guessing — all four answered from
   `sample-response.json`, a real captured payload.

## Smoke queries (5, real family shapes from `03-worker.md` §3, actor:
Anthill Ventures — `problems/actors/anthill-ventures.md`, one of the richer
`## Status` files)

| Family | Query | Results | Unresponsive |
|---|---|---|---|
| identity | `"Anthill Ventures"` | 22 | bing (HTTP connection error), duckduckgo (CAPTCHA) |
| money | `"Anthill Ventures" funding raised grant crore` | 30 | bing (suspended), duckduckgo (CAPTCHA) |
| people | `"Anthill Ventures" founder director leadership` | 24 | bing (suspended), duckduckgo (CAPTCHA) |
| asks | `"Anthill Ventures" partnership hiring seeking support` | 27 | bing (suspended), duckduckgo (CAPTCHA), mojeek (access denied) |
| reach | `"Anthill Ventures" contact twitter newsletter` | 24 | bing (suspended), duckduckgo (CAPTCHA), mojeek (suspended: access denied) |

**Qualitative verdict: useful.** The people-family query surfaced "Prasad
Vanga - Founder & CEO at Anthill - LinkedIn" at score 1.0 and a
LeadIQ/contact-scraper page at score 0.5 — both consistent with the actor
file's own claim (`founded 2015 by Prasad Vanga (Founder & CEO)`), so the
comparison-against-answer-key idea in the plan doc is workable. The
money-family query surfaced a real, specific funding data point (CureousLabs'
₹1.66cr seed round with Anthill as a participant) not otherwise in the actor
file — i.e. genuinely new signal, not just an echo of what's already written.

**What actually returned, in this environment: only `google` and `brave`.**
`bing` failed at the HTTP layer on every single query this session (not a
soft block — a connection error, suggesting the colima network path or a
hard IP-level block, not query-shape-triggered throttling). `duckduckgo`
CAPTCHA'd on every query from the first request — SearXNG's DDG scraper is
known to be fragile and this confirms it's unusable here without further
work (a resid, referer, or backend change). `mojeek` started fine (present
early) but flipped to `access denied` then `Suspended: access denided` after
~3-4 requests in quick succession — i.e. it *is* throttle-sensitive in exactly
the way §4's "throttle and jitter" obligation predicts, just at a very low
request count.

## What will bite the real PoC-0 run

- **Effective engine count is 2, not 5, until bing/duckduckgo/mojeek are
  fixed or replaced.** The 120-query run as currently configured would
  really be a 2-engine (google+brave) experiment. Before that run: either (a)
  accept 2 engines and drop the "~5" framing, (b) debug bing's connection
  error and duckduckgo's CAPTCHA (may not be fixable — DDG scraping is a
  known SearXNG pain point), or (c) swap in different upstream-disabled
  engines (e.g. `qwant`, `startpage` — both also carry known CAPTCHA/PoW
  issues per their own upstream comments, so may not help) or an
  API-key-gated one if the "no API key" constraint is relaxed.
- **`mojeek` suspends after ~3-4 rapid requests with no throttling.** Direct
  confirmation that §4's jitter/throttle obligation is not optional — it's
  the difference between mojeek being a live 5th engine and a dead one, at
  the query volumes PoC-0 (120 queries × several families) will actually
  generate.
- **`bing`'s failure is a connection error, not a query-shape response** —
  worth checking early in the real run whether it is transient (retry once)
  or structural (e.g. colima's network stack, IPv6, a persistent IP-level
  block) before spending the whole 120-query budget assuming it will recover.
- **Do not guess the `unresponsive_engines` floor** (plan doc is explicit on
  this) — this session's ad hoc numbers (2-3 of 5 engines down per query) are
  from 5 uncontrolled smoke queries with no throttling, not a real curve; the
  real PoC-0 run needs its own measurement under the throttle/jitter the
  worker will actually use.

---

## Addendum — engine-set verification, 2026-09-13

Run directly against the container after the settings fixes, 10 realistic
actor queries at a 5s throttle plus per-engine probes. Log:
`searxng/verify-10q.log`.

**Final working set: 3 of 5 — `bing`, `brave`, `google`.**

| Engine | Result | Diagnosis |
|---|---|---|
| `bing` | 10/10 | **Fixed.** Root cause was HTTP/3 (QUIC) failing under the colima/Docker network (`curl` error 56, ngtcp2 `ERR_DRAINING`), with no automatic downgrade to HTTP/2. `enable_http3: false` in `settings.yml` resolves it. An artefact of this Docker setup, not an IP block — it would not necessarily recur elsewhere. |
| `brave` | 10/10 | Reliable throughout, no intervention. |
| `google` | 3/10, then recovered | Went unresponsive from query 4 onward at a 5s throttle, and came back after the restart. Rate-limited, not blocked — the throttle needs to be higher than 5s, or jittered. Not pinned to a number here; PoC-0b's data should set it. |
| `qwant` | 0/10 | **Blocked.** Two separate problems: it ships `disabled` in this build (`keep_only` alone does not enable it — verified via `/config`), and once enabled it returns `SearxEngineAccessDeniedException('Access denied (suspended_time=180)')` on every query. Same class of failure as duckduckgo, which it was brought in to replace. |
| `mojeek` | 0/10 | Enabled and loaded, returns nothing. Probed in isolation it reports itself unresponsive even on a generic query (`climate change`, n=0). Not a config problem we control. |

### Finding: `unresponsive_engines` is not a complete account of what ran

In the 10-query group search, `mojeek` returned no results **and did not appear
in `unresponsive_engines`**. Queried alone, the same engine on the same query
*does* appear there. So an engine can be silently absent from both lists.

This matters for `03-worker.md` §4 obligation 2, which records
`unresponsive_engines` per query as the health signal. That list is a lower
bound on failure, not the failure set. Anything reading it — the floor in §14,
the health check in track D — has to compare against the *configured* engine
list to detect silent drop-outs, not trust the reported one.

### Throttle

5s is demonstrably too fast for google. No figure is recorded here: the plan
doc forbids guessing constants ahead of the data, and this applies to the
throttle as much as to the `unresponsive_engines` floor. PoC-0b sets it.

---

## Addendum 2 — mojeek reconciliation + final engine set, 2026-09-13 (session 2)

The addendum above and this one appear to be two independent diagnostic
passes over the same container in close succession (the earlier one's
`verify-10q.log` was written by a script that errored — `declare -A` is
invalid on macOS's default bash 3.2 — and its printed "23/10" counts are not
valid out of 10 queries; that log has been overwritten with this session's
clean run, see below). The two passes **agree on bing and qwant, disagree on
mojeek**. Reconciled here with root causes, not just outcomes.

### `bing` — confirmed fixed, same root cause as the first addendum

`docker logs` showed `curl_cffi.requests.exceptions.ConnectionError` /
`"the server has disconnected, retrying"` on every bing query. Reproduced
directly against bing.com from inside the container using the exact
mechanism SearXNG's client uses (`curl_cffi`, `impersonate="chrome"`):

- Forcing HTTP/3 (`CurlHttpVersion.V3`, matching `bing.py`'s module-level
  `enable_http3 = True`): **4/4 failed**, `curl error 56:
  ngtcp2_conn_writev_stream returned error: ERR_DRAINING` — QUIC breaking
  under this colima/Docker network.
- Same requests with no explicit version (HTTP/2): **6/6 succeeded**.

This is a config problem we control, not an IP block. Fix applied in
`settings.yml`: an `engines: - name: bing / enable_http3: false` block.
SearXNG's `load_engine()` (`searx/engines/__init__.py`) applies every
settings.yml key onto the loaded engine module via `setattr` — the same
mechanism `disabled: false` already used — so this is a supported override,
not a hack. Verified end to end: bing answered 10/10 in the 10-query
verification run below.

### `duckduckgo` — confirmed blocked, dropped

Unchanged from the first pass: `SearxEngineCaptchaException` on the very
first request, every time, this session. No config lever tried changes this
(the failure fires before any per-engine setting in `settings.yml` would
apply — it's DDG's bot page itself). Dropped.

### Replacement engine tried and also rejected: `qwant`

Per the task's candidate list, `qwant` was tried as duckduckgo's
replacement (also independently tried in the first addendum, same
conclusion). `qwant.py` calls `api.qwant.com/v3/search/` behind a
`datadome` anti-bot cookie the engine has no working way to prime from a
cold session. Raw requests to the plain `www.qwant.com` HTML front end
succeed fine (200, real HTML) — the block is specific to the API path
SearXNG's engine implementation actually uses, confirmed by hitting the
container's real `/search` endpoint with qwant enabled: `Suspended: access
denied` on every one of 5 consecutive probes, 3s apart. Structurally
blocked from this environment via the only code path SearXNG has for it.
Dropped, no substitute found (see rejected candidates below) — final set is
4 engines, not 5.

### `mojeek` — reconciled: throttle-fixable, not blocked

The first addendum found mojeek "enabled and loaded, returns nothing" and
called it "not a config problem we control." This session found the
opposite under controlled testing:

- Isolated, direct requests to mojeek.com from inside the container (same
  `curl_cffi`/`impersonate="chrome"` mechanism): 4 rapid requests with no
  delay succeed, the 5th gets `403` (`suspended_time=180` in the response
  body) — matching PoC-0a's original "~3-4 requests" observation exactly.
- After letting that 180s suspension actually clear (verified with a fresh
  probe returning 200 before proceeding — 403 the first time otherwise),
  8 requests at **1.0s** spacing: 8/8 failed (403) — but this ran
  immediately after a prior burst had already re-tripped the suspension, so
  it is not read as a clean 1.0s data point.
- 8 requests at **2.0s** spacing, from a confirmed-clear state: **8/8
  succeeded**.
- Real `/search` endpoint, 10-query verification (families/actors below) at
  2.5-4.0s jitter: **mojeek 10/10**.

Conclusion: mojeek's block is a request-rate suspension exactly as
documented in the first pass, not a persistent one — it was still in its
180s suspension window when the earlier pass tested it "in isolation" and
got zero. Once past that window and kept to >=2s between mojeek requests,
it is fully reliable. Kept in the final set.

### `google` / `brave` — volume-sensitive within a single diagnostic session, not fixed here

Across this session's cumulative testing (settings changes needed several
container restarts and re-probes, on top of the 10-query run — roughly
15-20 total queries to google over ~20 minutes), google degraded from
answering the first 2 queries cleanly to `CAPTCHA` / `Suspended: CAPTCHA`
on the rest; brave held for 7 of 10 before `too many requests` /
`Suspended: too many requests`. Both reason strings are rate-limit
responses, not IP bans. This matches the first addendum's independent
finding that "5s is too fast for google" — but note our spacing here
(2.5-4.0s, *tighter* than their 5s) still eventually tripped both engines
after enough cumulative volume, which points at a rolling request-budget
per hour rather than a pure per-request-interval threshold. Per the task's
own constraint, no floor or safe interval is guessed here — this is exactly
what PoC-0b's real 120-query run under sustained throttle needs to measure.
Both engines stay in the set: they answered every query in PoC-0a's
original smoke test and the first 2-7 queries here, i.e. they are usable,
just not inexhaustibly so within one continuous diagnostic burst.

### Rejected replacement candidates, not tried live (per task's "no API key" constraint)

- `startpage`: ships inactive upstream behind an "Anubis" proof-of-work
  challenge page (confirmed: a raw request returns the challenge HTML, not
  results) — CPU-bound, not a simple fetch.
- `marginalia`: its public API now requires a signup API key (`400 Missing
  API-Key header` on a raw request) — excluded per the task's "do not sign
  up for anything" constraint.
- `wikipedia`, `openalex`, `crossref`: not general web indexes (encyclopedia
  / academic-only) — a poor swap for an engine meant to surface small
  Indian NGO/news sites, per the task's own bias instruction. Not tried.

### Final engine set — 4 of the original 5

`settings.yml` `keep_only`: **`brave`, `google`, `bing`, `mojeek`**.
`duckduckgo` and `qwant` (its attempted replacement) are both dropped —
structurally blocked from this environment via the only request path
SearXNG's engine implementations have for them, independent of any setting
this file controls. This is the acceptance criterion's "3 is acceptable,
4+ is good" band, landing at **4**.

### 10-query verification (full log: `searxng/verify-10q.log`)

10 queries, 5 families (identity/money/people/asks/reach) across 5 actors
(Anthill Ventures, Aavishkaar Group, Acumen, Accion, Action for India),
2.5-4.0s jittered throttle, run against the finalized 4-engine set:

| Engine | Success | Note |
|---|---|---|
| `bing` | 10/10 | Fully recovered post-fix. |
| `mojeek` | 10/10 | Fully reliable once past its own suspension window. |
| `brave` | 7/10 | Degraded after cumulative session volume — see above. |
| `google` | 2/10 | Same. |

### Throttle — the number this file's first addendum left open

**>=2.0s between requests to the same engine is the concrete floor found
this session** — mojeek: 1.0s (contaminated sample) failed outright, 2.0s
succeeded 8/8 in isolation and 10/10 inside the real 10-query run at
2.5-4.0s jitter. This is the figure for `03-worker.md` §4 obligation 1 and
for PoC-0b/track D to start from. It is **not** a complete answer: google
and brave show a separate, rolling volume sensitivity across a session that
2.5-4.0s jitter did not prevent (both degraded after several minutes of
cumulative querying at that spacing) — this is a per-hour-budget question,
distinct from per-request spacing, and is left for PoC-0b's real 120-query
run to measure rather than guessed here.

### Instance state

Container `fph-searxng-poc0` left **running** with the final 4-engine
`settings.yml` in place.
