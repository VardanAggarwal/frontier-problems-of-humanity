"""PoC-0b — the 120-query SearXNG run (harness).

`04-worker-build-plan.md` §2 PoC-0. 20 actors x 6 families (`poc0b_families.yaml`)
against the local SearXNG instance (`searxng/run.sh`), throttled and jittered
per `03-worker.md` §4 obligation 1, recording:

  - every raw JSON response, to `poc0b-responses/<slug>__<family>.json`
    (the replay corpus track D's fixtures need, per the plan doc's third
    addition) — also what makes this runner resumable: a query whose response
    file already exists is skipped, so an interrupted run can be restarted
    with the same command;
  - `unresponsive_engines` from the JSON *and* the set of engines that
    actually contributed a result (`engines` field on each hit), because
    `poc0a-results.md`'s dated addendum found `unresponsive_engines` is only a
    lower bound — an engine (mojeek, in that run) can return nothing and not
    appear in that list at all. Comparing "configured engines" against
    "engines seen in results" is the only way to catch that silently.

Does NOT compute rank from list index (03-worker.md §4: "Fuse on `score`,
never on the JSON list index"). This file only records; `poc0b_analyse.py`
derives rank from `score` at analysis time, offline.

Usage:
    python3 poc0b_run.py                 # full 120-query run
    python3 poc0b_run.py --limit 2        # dry run: first N actors only
    python3 poc0b_run.py --limit 2 --dry-run-note "..."   # (note is just for the log)

Resumable: re-running with the same --limit (or none) skips every query whose
response file already exists in poc0b-responses/.
"""

import argparse
import datetime
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

# --- top-of-file throttle constant, per the task brief -----------------
# poc0a-results.md Addendum 2 (supersedes Addendum 1) found TWO distinct
# effects, and they must stay separable, not collapsed into one number:
#   1. A per-request spacing FLOOR: >=2.0s between requests is the confirmed
#      threshold (mojeek: 1.0s failed outright, 2.0s succeeded 8/8 isolated
#      and 10/10 inside a real run at 2.5-4.0s jitter).
#   2. A separate, ROLLING cumulative-session-volume effect on google/brave:
#      both degraded after enough total queries within one session even at
#      2.5-4.0s spacing (brave 7/10, google 2/10 in the 10-query verification
#      run) — a per-hour-budget question, explicitly left for PoC-0b's real
#      120-query run to measure, not guessed here.
# This constant sets only (1), at >=2.0s with jitter so the cadence doesn't
# itself look like a bot signature (03-worker.md §4 obligation 1). To let the
# real run's analysis separate (1) from (2), every recorded query below also
# carries a wall-clock timestamp and a running request counter — so
# poc0b_analyse.py (or whoever runs the full batch) can tell "failed because
# too close together" apart from "failed because this session already spent
# too many requests." Do not fold these into one throttle number ahead of
# that data.
THROTTLE_BASE_S = 25.0
THROTTLE_JITTER_S = 10.0  # actual sleep = uniform(BASE - JITTER/2, BASE + JITTER/2)
# -> effective range 2.0s-4.0s, matching poc0a's verified 2.5-4.0s band while
#    keeping a hard floor at 2.0s.

SEARXNG_URL = "http://localhost:8080/search"
HERE = Path(__file__).parent
SAMPLE_PATH = HERE / "poc0b-sample.json"
FAMILIES_PATH = HERE / "poc0b_families.yaml"
RESPONSES_DIR = HERE / "poc0b-responses"

# Final 4-engine set per poc0a-results.md Addendum 2 ("Final engine set — 4
# of the original 5"): brave, google, bing, mojeek. duckduckgo and qwant are
# structurally blocked and excluded; do not try to fix them. Used only to
# detect the "silently absent from unresponsive_engines too" failure mode —
# not a request parameter.
CONFIGURED_ENGINES = {"bing", "brave", "google", "mojeek"}


def load_actors(limit=None):
    data = json.loads(SAMPLE_PATH.read_text())
    actors = data["actors"]
    if limit is not None:
        actors = actors[:limit]
    return actors


def load_families():
    data = yaml.safe_load(FAMILIES_PATH.read_text())
    return data["families"]


def query_searxng(query_str):
    params = urllib.parse.urlencode({"q": query_str, "format": "json"})
    url = f"{SEARXNG_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "fph-poc0b/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read()
    return json.loads(body)


def engines_seen_in_results(raw):
    seen = set()
    for r in raw.get("results", []):
        for e in r.get("engines", []):
            seen.add(e)
        if r.get("engine"):
            seen.add(r["engine"])
    return seen


def run(limit=None):
    RESPONSES_DIR.mkdir(exist_ok=True)
    actors = load_actors(limit=limit)
    families = load_families()

    total = len(actors) * len(families)
    done = 0
    skipped = 0
    issued = 0
    run_started_at = time.time()

    print(
        f"[poc0b] {len(actors)} actors x {len(families)} families = {total} queries "
        f"(throttle base={THROTTLE_BASE_S}s jitter=+/-{THROTTLE_JITTER_S/2}s)",
        file=sys.stderr,
    )

    for actor in actors:
        slug = actor["slug"]
        name = actor["name"]
        for fam in families:
            fid = fam["id"]
            out_path = RESPONSES_DIR / f"{slug}__{fid}.json"
            done += 1

            if out_path.exists():
                skipped += 1
                print(f"[{done}/{total}] SKIP  {slug:45s} {fid:10s} (response exists)")
                continue

            query_str = fam["template"].format(name=name)

            if issued > 0:
                sleep_s = random.uniform(
                    THROTTLE_BASE_S - THROTTLE_JITTER_S / 2,
                    THROTTLE_BASE_S + THROTTLE_JITTER_S / 2,
                )
                time.sleep(max(0.0, sleep_s))

            t0 = time.time()
            issued += 1  # this query counts toward the session's cumulative
                         # request budget the moment it's sent, success or not
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            seconds_since_run_start = round(t0 - run_started_at, 1)
            try:
                raw = query_searxng(query_str)
                elapsed = time.time() - t0
            except Exception as exc:  # noqa: BLE001 — record failure, keep going
                elapsed = time.time() - t0
                print(
                    f"[{done}/{total}] ERROR {slug:45s} {fid:10s} query={query_str!r} "
                    f"({exc}) after {elapsed:.1f}s [req #{issued}, t+{seconds_since_run_start}s]"
                )
                error_record = {
                    "slug": slug,
                    "name": name,
                    "family": fid,
                    "query": query_str,
                    "error": str(exc),
                    "elapsed_s": elapsed,
                    "timestamp_utc": timestamp,
                    "request_index_this_run": issued,
                    "seconds_since_run_start": seconds_since_run_start,
                }
                out_path.write_text(json.dumps(error_record, indent=2))
                continue

            unresponsive = raw.get("unresponsive_engines", [])
            unresponsive_names = [u[0] if isinstance(u, list) else u for u in unresponsive]
            seen = engines_seen_in_results(raw)
            silently_absent = sorted(CONFIGURED_ENGINES - seen - set(unresponsive_names))

            n_results = len(raw.get("results", []))

            record = {
                "slug": slug,
                "name": name,
                "family": fid,
                "query": query_str,
                "question_ids": fam.get("question_ids", []),
                "elapsed_s": round(elapsed, 3),
                "timestamp_utc": timestamp,
                # separates "too close together" from "session budget spent" —
                # poc0a Addendum 2's two distinct effects (see THROTTLE_* above).
                "request_index_this_run": issued,
                "seconds_since_run_start": seconds_since_run_start,
                "n_results": n_results,
                "unresponsive_engines": unresponsive,
                "engines_seen_in_results": sorted(seen),
                "configured_engines": sorted(CONFIGURED_ENGINES),
                "silently_absent_engines": silently_absent,
                "raw_response": raw,
            }
            out_path.write_text(json.dumps(record, indent=2))

            flag = f" SILENT-DROP:{silently_absent}" if silently_absent else ""
            print(
                f"[{done}/{total}] OK    {slug:45s} {fid:10s} "
                f"n={n_results:3d} unresp={unresponsive_names}{flag} "
                f"({elapsed:.1f}s, req#{issued}, t+{seconds_since_run_start}s)"
            )

    print(
        f"[poc0b] done. {done - skipped} queries issued this run, {skipped} skipped "
        f"(already on disk). Responses in {RESPONSES_DIR}",
        file=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only run the first N actors (e.g. --limit 2 for the dry run)",
    )
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
