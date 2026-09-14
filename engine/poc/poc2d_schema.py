"""PoC-2d — does the enlarged schema still parse? (`poc2d-spec.md`)

Runs BEFORE 2c. The 2026-09-14 revision changed the batched schema in four
ways at once and the only evidence the batched prompt works is PoC-2's 95/95
attribution, measured before any of them. 2c scores one targeted question per
cell, where a parse failure and a declined question both read as
`target_answered=False` — the confound that made 2 and 2b uninformative
twice. So the schema is measured on its own first.

Five pinned fixtures, radius 1, free rung, no HTTP. Each actor twice:

* **live** — the shipped prompt, with a chunk-marked body.
* **control** — the prompt as of the commit before the revision, with the
  unmarked body it was written for. Read out of git rather than remembered,
  so the comparison cannot drift the way a hand-copied baseline does.

Run from `engine/`:  .venv/bin/python -m poc.poc2d_schema [--live-only]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from poc.poc2_extract import (                                   # noqa: E402
    UnusableActor, actor_name, build_prompt, entity_tokens, gather_sources,
    label_map, one_call, _response_envelope,
)
from poc.poc2c_targeted import (                                 # noqa: E402
    ACTORS, REPLACEMENTS, CALL_RADIUS, RUNGS, SOURCES_WANTED,
    build_prompt_marked, call_with_retry,
)
from text.chunk import chunk                                     # noqa: E402
from worker import passages                                      # noqa: E402
from worker.extract_types import PromptSource                    # noqa: E402
from worker.prompts import (                                     # noqa: E402
    extract_prompt_batched, parse_answers, resolve_chunk_marker,
)
from worker.questions import REGISTRY                            # noqa: E402

POC = pathlib.Path(__file__).resolve().parent
OUT = POC / "poc2d-responses"

# The commit BEFORE "One prompt revision". Pinned rather than HEAD~1 so this
# keeps naming the right prompt after further commits land.
CONTROL_REV = "80f1935"
SIGNAL_KEYS = ("harmed_population", "magnitude", "agent", "actionable")
ALL_ACTORS = list(ACTORS) + list(REPLACEMENTS)


def load_control_prompts():
    """`worker/prompts.py` as of `CONTROL_REV`, imported under its own name.

    Reading it out of git is the point: a control typed from memory is how a
    baseline silently stops being the thing it claims to compare against —
    2c's first version reconstructed the shipped prompt by hand and was
    wrong about it within a day.
    """
    src = subprocess.run(
        ["git", "show", f"{CONTROL_REV}:engine/worker/prompts.py"],
        capture_output=True, text=True, check=True,
        cwd=pathlib.Path(__file__).resolve().parents[2]).stdout
    path = POC / "poc2-scratch" / "prompts_control.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("prompts_control", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["prompts_control"] = mod
    spec.loader.exec_module(mod)
    return mod


def build(slug: str, name: str, log, control_mod) -> dict | None:
    tokens = entity_tokens(name)
    texts, urls = gather_sources(slug, SOURCES_WANTED, log, tokens, pinned=True)
    if len(texts) < 2:
        raise UnusableActor(f"{slug}: {len(texts)} usable source(s)")
    all_chunks = []
    for sid, text in texts.items():
        all_chunks.extend(chunk(text, source_id=sid))
    selected = list(passages.select(all_chunks, list(REGISTRY.all("actor")),
                                    neighbour_radius=CALL_RADIUS))
    labels = label_map(selected)

    order, by_source = [], {}
    for ch in selected:
        by_source.setdefault(ch.source_id, []) or order.append(ch.source_id)
        by_source.setdefault(ch.source_id, []).append(ch)
    sources = []
    for i, sid in enumerate(order, start=1):
        g = sorted(by_source[sid], key=lambda c: c.ordinal)
        sources.append(PromptSource(
            source_id=sid, label=f"S{i}", url=urls.get(sid, sid),
            text="\n\n".join(c.text for c in g),
            chunk_refs=tuple(c.chunk_ref for c in g),
            chunk_texts=tuple(c.text for c in g)))

    live_system, _ = extract_prompt_batched("actor", name, sources)
    control_system, _ = control_mod.extract_prompt_batched(
        "actor", name, [s._replace(chunk_texts=()) for s in sources])
    return {
        "slug": slug, "name": name, "labels": labels, "sources": sources,
        # Each prompt gets the body it was written for: the control predates
        # rule 5, so marking its chunks would measure a prompt that never
        # existed.
        "live": {"system": live_system,
                 "body": build_prompt_marked(name, selected, urls)},
        "control": {"system": control_system,
                    "body": build_prompt(name, selected, urls)},
    }


def score(data, sources, arm: str) -> dict:
    out = {"parsed": isinstance(data, dict), "answers": 0, "valid_ids": 0,
           "chunk_cited": 0, "chunk_resolved": 0, "chunk_wrong_source": 0,
           "signals_emits": 0, "signals_filled": 0, "signals_uncounted": 0,
           "claims_volunteered": 0, "emits": 0, "edges": 0}
    if not isinstance(data, dict):
        return out
    answers, _problems = parse_answers(data, sources)
    raw = data.get("answers") or []
    by_label = {s.label: s for s in sources}
    out["answers"] = len(raw)
    out["valid_ids"] = len(answers)
    for i, a in enumerate(raw):
        if not isinstance(a, dict):
            continue
        marker = a.get("chunk")
        if marker in (None, ""):
            continue
        out["chunk_cited"] += 1
        src = by_label.get(str(a.get("source_id") or "").strip().strip("[]"))
        if src is None:
            continue
        problems: list[str] = []
        if resolve_chunk_marker(marker, src, "q", i, problems) is not None:
            out["chunk_resolved"] += 1
        elif any("names" in p for p in problems):
            out["chunk_wrong_source"] += 1

    for e in (data.get("emits") or []):
        if not isinstance(e, dict):
            continue
        out["emits"] += 1
        if e.get("kind") != "problem":
            continue
        out["signals_emits"] += 1
        sig = e.get("signals")
        if isinstance(sig, dict):
            if any(sig.get(k) not in (None, "", {}) for k in SIGNAL_KEYS):
                out["signals_filled"] += 1
            if str(sig.get("magnitude") or "").strip().lower() == "uncounted":
                out["signals_uncounted"] += 1
    out["edges"] = len(data.get("edges") or [])
    # The live prompt no longer asks for `claims`. A non-zero count is the
    # model volunteering a key it was not shown — worth seeing, not routine.
    out["claims_volunteered"] = (len(data.get("claims") or [])
                                 if arm == "live" else 0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-only", action="store_true",
                    help="skip the control arm (5 calls instead of 10)")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    handle = (POC / "poc2d_run.log").open("w", encoding="utf-8")

    def log(*parts):
        line = " ".join(str(p) for p in parts)
        print(line)
        handle.write(line + "\n")
        handle.flush()

    control_mod = load_control_prompts()
    arms = ["live"] if args.live_only else ["live", "control"]
    log("PoC-2d — does the enlarged schema still parse?")
    log(f"  actors={ALL_ACTORS} arms={arms} rung={RUNGS[0]} "
        f"radius={CALL_RADIUS} control_rev={CONTROL_REV}")

    built, rows = [], []
    for slug in ALL_ACTORS:
        try:
            b = build(slug, actor_name(slug), log, control_mod)
        except UnusableActor as e:
            log(f"  DROPPED {slug}: {e}")
            continue
        log(f"  {slug}: {len(b['sources'])} blocks, chunks/block="
            f"{[len(s.chunk_refs) for s in b['sources']]} | "
            f"live sys={len(b['live']['system'])} body={len(b['live']['body'])}"
            f" | control sys={len(b['control']['system'])} "
            f"body={len(b['control']['body'])}")
        built.append(b)

    log("\n[calls]")
    for b in built:
        for arm in arms:
            tag = f"{b['slug']}__{arm}"
            res, attempts, err = call_with_retry(
                b[arm]["body"], b[arm]["system"], RUNGS[0], tag, log)
            if res is None:
                log(f"  {tag}: HOLE — {err}")
                rows.append({"slug": b["slug"], "arm": arm, "hole": True})
                continue
            (OUT / f"{tag}.json").write_text(json.dumps(
                _response_envelope(res, b[arm]["body"], b[arm]["system"], None),
                ensure_ascii=False, indent=1), encoding="utf-8")
            row = {"slug": b["slug"], "arm": arm, "hole": False,
                   "transport_attempts": attempts,
                   "parse_error": res.get("parse_error"),
                   "truncated": bool(res.get("truncated")),
                   "output_tokens": res.get("output_tokens"),
                   "input_tokens": res.get("input_tokens")}
            row.update(score(res.get("json"), b["sources"], arm))
            rows.append(row)
            log(f"  {tag}: parsed={row['parsed']} answers={row['answers']} "
                f"valid_ids={row['valid_ids']} "
                f"chunk_cited={row['chunk_cited']} "
                f"resolved={row['chunk_resolved']} "
                f"wrong_source={row['chunk_wrong_source']} "
                f"problem_emits={row['signals_emits']} "
                f"signals_filled={row['signals_filled']} "
                f"uncounted={row['signals_uncounted']} "
                f"claims_volunteered={row['claims_volunteered']} "
                f"out_tokens={row['output_tokens']}")
            if row["parse_error"]:
                log(f"      parse_error: {str(row['parse_error'])[:200]}")

    log("\n[summary]")
    for arm in arms:
        sub = [r for r in rows if r.get("arm") == arm and not r.get("hole")]
        if not sub:
            continue
        ok = [r for r in sub if r["parsed"]]
        tot = lambda k: sum(r.get(k) or 0 for r in ok)      # noqa: E731
        log(f"  {arm}: parsed {len(ok)}/{len(sub)} | answers {tot('answers')} "
            f"| valid_ids {tot('valid_ids')}/{tot('answers')} "
            f"| chunk_cited {tot('chunk_cited')}/{tot('answers')} "
            f"(resolved {tot('chunk_resolved')}, "
            f"wrong_source {tot('chunk_wrong_source')}) "
            f"| problem_emits {tot('signals_emits')} "
            f"(filled {tot('signals_filled')}, "
            f"uncounted {tot('signals_uncounted')}) "
            f"| claims_volunteered {tot('claims_volunteered')} "
            f"| out_tokens {tot('output_tokens')}")

    (POC / "poc2d_summary.json").write_text(json.dumps(
        {"control_rev": CONTROL_REV, "arms": arms, "rows": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"\nwrote {POC / 'poc2d_summary.json'}")
    handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
