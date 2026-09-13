"""PoC-2b — does better prompting fix the reconciliation failure PoC-2 found?

PoC-2 found: 0/8 calls flagged the planted disagreement while 95/95 answers
carried a valid single `source_id`. The diagnosis: `system_prompt()`'s rule 1
("never merge two sources into one answer") plus a schema giving each answer
exactly ONE `source_id` structurally forecloses rule 2's ask ("write the
disagreement, naming both sides and both source ids") — there is no field to
put a second source id in.

WITHIN-RUN COMPARISON (not a rerun of PoC-2's baseline). PoC-2 never saved
its prompts, and this run's own source fetch draws a live, order-sensitive
set from the URL pool that is not reproducible against an old run's numbers
— trying to match PoC-2's recorded `prompt_chars` by refetching is not
achievable and this file does not attempt it. Instead: for each actor, build
ONE prompt body (fetch, select at radius 1, plant, `build_prompt`), then fire
THREE calls against that *same* prompt body, varying ONLY the system prompt:

* baseline — `poc2_extract.system_prompt()`, unchanged.
* V1 — prose fix, schema unchanged. Rule 1's prohibition is reworded to
  explicitly exclude the disagreement case; rule 2 is sharpened to require
  the answer text to name both figures AND both source ids inline (since the
  schema still gives only one `source_id` field).
* V2 — structural. Rules 1-3 unchanged from baseline; a new top-level
  `disagreements` array is added to the schema for conflicting figures.

Three actors, one repeat each, radius 1, openrouter only. 3 actors x 3
variants x 1 repeat = 9 calls.

Run from `engine/`:  python -m poc.poc2b_reconcile > poc/poc2b-stdout.log 2>&1
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from poc.poc2_extract import (                                   # noqa: E402
    PLANTED_ID, actor_name, build_for_actor, one_call, score_response,
    system_prompt as system_prompt_baseline, _question_block,
)
from worker.prompts import _ACTOR_SYSTEM                          # noqa: E402

POC = pathlib.Path(__file__).resolve().parent
OUT_RESPONSES = POC / "poc2b-responses"

ACTORS = ["bhavreen-kandhari", "selco-foundation", "bku-ekta-ugrahan"]
SOURCES_WANTED = 4          # matches poc2_extract's default --sources
CALL_RADIUS = 1
RUNGS = ["openrouter"]
REPEATS = 1


# ── prompt variants ────────────────────────────────────────────────────────

_SCHEMA_BASELINE = (
    "Respond with strict JSON only, no prose, no markdown fences:\n"
    '{"answers": [{"question_id": "...", "source_id": "S2", '
    '"answer": "...", "confidence": 0.0}],\n'
    ' "claims":  [{"field": "...", "value": "...", "confidence": 0.0}],\n'
    ' "emits":   [{"kind": "problem"|"actor", "name": "...", '
    '"hint": "...", "signals": {}}],\n'
    ' "edges":   [{"dst_name": "...", "dst_kind": "...", '
    '"edge_kind": "...", "relevance": 0, "stance": null, '
    '"evidence": "..."}]}'
)


def system_prompt_v1(kind: str) -> str:
    """Prose fix only. Schema byte-identical to baseline. Rule 1's "never
    merge" prohibition is scoped to exclude the disagreement case; rule 2 is
    sharpened to require both figures AND both source ids inline in the
    answer text (the schema still has only one `source_id` field, so this is
    the only place two ids can go)."""
    return (
        _ACTOR_SYSTEM + "\n\n"
        "SEVERAL SOURCES ARE GIVEN AT ONCE, each opening with a marker line "
        "`[Sn] <url>`. Three additional rules follow from that:\n\n"
        "1. Answer the numbered questions below. Every answer carries the "
        "`question_id` it answers and the `source_id` (`S1`, `S2`, …) of the "
        "source it came from. An answer with no source id, or an id not in "
        "the list given, is DROPPED — never guess an id. Do not merge two "
        "sources into one answer UNLESS the two sources disagree, in which "
        "case rule 2 below applies and merging is exactly what is required.\n"
        "2. If two sources disagree — a different figure, date, or status for "
        "the same thing — the disagreement itself is the correct answer. The "
        "`answer` text MUST explicitly name BOTH conflicting values AND BOTH "
        "source ids inline, in a form like: \"S1 gives 4 crore; S4 gives 8 "
        "crore.\" Put whichever source id you name first in the `source_id` "
        "field. Do not silently pick one figure and drop the other.\n"
        "3. A question no source answers is simply absent from `answers`.\n\n"
        "QUESTIONS:\n" + _question_block(kind) + "\n\n"
        + _SCHEMA_BASELINE
    )


def system_prompt_v2(kind: str) -> str:
    """Structural fix. Rules 1-3 unchanged from baseline, verbatim. A new
    top-level `disagreements` array is added to the schema."""
    return (
        _ACTOR_SYSTEM + "\n\n"
        "SEVERAL SOURCES ARE GIVEN AT ONCE, each opening with a marker line "
        "`[Sn] <url>`. Three additional rules follow from that:\n\n"
        "1. Answer the numbered questions below. Every answer carries the "
        "`question_id` it answers and the `source_id` (`S1`, `S2`, …) of the "
        "source it came from. An answer with no source id, or an id not in "
        "the list given, is DROPPED — never guess an id, and never merge two "
        "sources into one answer.\n"
        "2. If two sources disagree — a different figure, date, or status for "
        "the same thing — write the disagreement as the answer, naming both "
        "sides and both source ids. Do not silently pick one.\n"
        "3. A question no source answers is simply absent from `answers`.\n\n"
        "Every conflicting figure, date, or status found across sources also "
        "goes into the top-level `disagreements` array below, one entry per "
        "conflict; an empty array means no conflicts were found.\n\n"
        "QUESTIONS:\n" + _question_block(kind) + "\n\n"
        "Respond with strict JSON only, no prose, no markdown fences:\n"
        '{"answers": [{"question_id": "...", "source_id": "S2", '
        '"answer": "...", "confidence": 0.0}],\n'
        ' "claims":  [{"field": "...", "value": "...", "confidence": 0.0}],\n'
        ' "emits":   [{"kind": "problem"|"actor", "name": "...", '
        '"hint": "...", "signals": {}}],\n'
        ' "edges":   [{"dst_name": "...", "dst_kind": "...", '
        '"edge_kind": "...", "relevance": 0, "stance": null, '
        '"evidence": "..."}],\n'
        ' "disagreements": [{"question_id": "...", "value_a": "...", '
        '"source_id_a": "S1", "value_b": "...", "source_id_b": "S4", '
        '"note": "..."}]}'
    )


VARIANTS = {
    "baseline": lambda kind: system_prompt_baseline(kind),
    "v1": system_prompt_v1,
    "v2": system_prompt_v2,
}


def score_v2_extra(data: dict | None, plant_info: dict | None,
                   valid_labels: set[str]) -> dict:
    if not isinstance(data, dict):
        return {"n_disagreements": 0, "disagreement_names_both": False,
                "disagreement_ids_valid": False, "disagreements": []}
    disagreements = data.get("disagreements") or []
    names_both = False
    ids_valid = False
    if plant_info:
        orig = plant_info["original"].lower()
        altered = plant_info["altered"].lower()
        for d in disagreements:
            blob = json.dumps(d, ensure_ascii=False).lower()
            if orig in blob and altered in blob:
                names_both = True
                sa = str((d or {}).get("source_id_a") or "").strip().strip("[]")
                sb = str((d or {}).get("source_id_b") or "").strip().strip("[]")
                if sa in valid_labels and sb in valid_labels:
                    ids_valid = True
    return {"n_disagreements": len(disagreements),
            "disagreement_names_both": names_both,
            "disagreement_ids_valid": ids_valid,
            "disagreements": disagreements}


def main() -> int:
    OUT_RESPONSES.mkdir(parents=True, exist_ok=True)
    handle = (POC / "poc2b_run.log").open("w", encoding="utf-8")

    def log(*parts):
        line = " ".join(str(p) for p in parts)
        print(line)
        handle.write(line + "\n")
        handle.flush()

    log("PoC-2b — does better prompting fix reconciliation? "
        "(within-run comparison: one prompt body per actor, three system "
        "prompts fired against it)")
    log(f"  actors={ACTORS} variants={list(VARIANTS)} rungs={RUNGS} "
        f"repeats={REPEATS} radius={CALL_RADIUS}")

    log("\n[1] fetch, select, plant, build — per actor (ONE build, radius 1)")
    actors = []
    for slug in ACTORS:
        built = build_for_actor(slug, actor_name(slug), SOURCES_WANTED,
                                [CALL_RADIUS], log)
        if built is None:
            log(f"FATAL: {slug} produced no usable prompt")
            handle.close()
            return 1
        spec = built["built"][CALL_RADIUS]
        if spec["plant"] is None:
            log(f"FATAL: no plant for {slug}")
            handle.close()
            return 1
        log(f"  {slug}: prompt_chars={spec['chars']} planted="
            f"{spec['plant']['original']}->{spec['plant']['altered']} "
            f"({spec['plant']['unit']})")
        actors.append(built)

    log("\n[2] calls — same prompt body per actor, 3 system-prompt variants")
    rows = []
    for actor in actors:
        spec = actor["built"][CALL_RADIUS]
        valid = set(spec["labels"].values())
        planted_label = spec["labels"].get(PLANTED_ID)
        for vname, vfunc in VARIANTS.items():
            system = vfunc("actor")
            for rung in RUNGS:
                for i in range(REPEATS):
                    tag = f"{actor['slug']}__{vname}__{rung}__{i}"
                    try:
                        res = one_call(spec["prompt"], system, rung)
                    except Exception as e:                        # noqa: BLE001
                        log(f"  {tag}: TRANSPORT FAILED {type(e).__name__}: "
                            f"{str(e)[:160]}")
                        rows.append({"slug": actor["slug"], "variant": vname,
                                    "rung": rung, "i": i, "parsed": False,
                                    "call_failed": True,
                                    "error": f"{type(e).__name__}: {e}"})
                        continue

                    (OUT_RESPONSES / f"{tag}.json").write_text(
                        json.dumps({"raw": res.get("text"),
                                    "json": res.get("json"),
                                    "parse_error": res.get("parse_error"),
                                    "truncated": res.get("truncated")},
                                   ensure_ascii=False, indent=1))

                    scored = score_response(res, valid, spec["plant"],
                                            planted_label)
                    scored["truncated"] = bool(res.get("truncated"))

                    if not scored["parsed"]:
                        try:
                            again = one_call(spec["prompt"], system, rung)
                            (OUT_RESPONSES / f"{tag}__retry.json").write_text(
                                json.dumps({"raw": again.get("text"),
                                            "json": again.get("json"),
                                            "parse_error": again.get("parse_error"),
                                            "truncated": again.get("truncated")},
                                           ensure_ascii=False, indent=1))
                            if again.get("json") is not None:
                                res = again
                                scored = score_response(res, valid,
                                                        spec["plant"],
                                                        planted_label)
                                scored["truncated"] = bool(res.get("truncated"))
                                scored["retry_rescued"] = True
                            else:
                                scored["retry_rescued"] = False
                        except Exception as e:                    # noqa: BLE001
                            scored["retry_rescued"] = False
                            scored["retry_error"] = f"{type(e).__name__}: {e}"
                    else:
                        scored["retry_rescued"] = None

                    if vname == "v2":
                        scored.update(score_v2_extra(res.get("json"),
                                                      spec["plant"], valid))

                    scored.update(slug=actor["slug"], variant=vname,
                                  rung=rung, i=i, call_failed=False,
                                  parse_error=res.get("parse_error"),
                                  prompt_chars=spec["chars"])
                    rows.append(scored)

                    log(f"  {tag}: parsed={scored['parsed']} "
                        f"answers={scored.get('answers')} "
                        f"valid_id={scored.get('with_valid_id')} "
                        f"planted_cited={scored.get('cited_planted')} "
                        f"both_figs={scored.get('both_figures')} "
                        f"marker={scored.get('marker')} "
                        f"truncated={scored.get('truncated')} "
                        f"retry_rescued={scored.get('retry_rescued')}"
                        + (f" n_disagreements={scored.get('n_disagreements')} "
                           f"disagreement_names_both="
                           f"{scored.get('disagreement_names_both')} "
                           f"disagreement_ids_valid="
                           f"{scored.get('disagreement_ids_valid')}"
                           if vname == "v2" else ""))
                    if scored.get("parse_error"):
                        log(f"      parse_error: "
                            f"{str(scored['parse_error'])[:160]}")

    log("\n[3] summary — per variant, pooled across actors")
    for vname in VARIANTS:
        sub = [r for r in rows if r.get("variant") == vname]
        ok = [r for r in sub if not r.get("call_failed")]
        parsed = [r for r in ok if r.get("parsed")]
        log(f"  {vname}: calls {len(sub)} (transport-failed "
            f"{len(sub) - len(ok)}) | parsed {len(parsed)}/{len(ok)} "
            f"| both_figures {sum(1 for r in parsed if r.get('both_figures'))}"
            f"/{len(parsed)} "
            f"| marker {sum(1 for r in parsed if r.get('marker'))}"
            f"/{len(parsed)} "
            f"| planted_cited "
            f"{sum(1 for r in parsed if r.get('cited_planted'))}/{len(parsed)}")

    (POC / "poc2b_summary.json").write_text(json.dumps(
        {"rows": rows,
         "actors": [{"slug": a["slug"], "name": a["name"],
                     "chars": a["built"][CALL_RADIUS]["chars"],
                     "plant": a["built"][CALL_RADIUS]["plant"]}
                    for a in actors]},
        ensure_ascii=False, indent=1))
    handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
