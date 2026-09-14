"""PoC-2c — reconciliation, measured where it can actually appear.

PoC-2 measured 0/8 and PoC-2b measured `disagreements[]` empty 3/3. Both
numbers are uninformative for one reason: `poc2_extract.plant` scrapes ANY
number-plus-unit out of an arbitrary passage sentence and doubles it, so the
contradiction landed on a year (2020->4040), a protest turnout and a piece of
loose prose — none of which the actor question sheet asks for. The model was
given a contradiction with nowhere to surface and correctly ignored it.

This run fixes the aim, in two stages (`poc2c-spec.md`):

* **Stage 1 — probe.** One extraction call per actor on the UNMODIFIED
  sources, baseline system prompt. Record the answers to `q10_funding` and
  `q11_scale_metric`. Pick the first that carries a plantable quantity — a
  currency amount, a count, or a capacity figure; never a year, ordinal or
  date. An actor whose probe answers neither is dropped, loudly, and a
  replacement is taken.
* **Stage 2 — targeted plant.** Restate that figure's own sentence at
  `PLANT_RATIO` (1.35, not 2.0 — the repo's own precedent for a real
  disagreement is Delhi 82.2 vs 99.6 ug/m3, a 1.21x spread), attributed to a
  different publisher, appended as one more `[Sn]` block. Three system-prompt
  variants (baseline / v1 / v2, as in 2b) fire against ONE prompt body.

Scoring is restricted to the targeted question. `target_answered=False` is a
VOID, never a negative — and since rule 4 shipped it has a third cause, so a
void is classified `declined` / `flagged` / `hole` rather than pooled.

Two departures from the spec, both deliberate, both because rule 4 shipped
after the spec was written:

1. Baseline is `worker.prompts.batched_prompt`'s live system text (rules 1-4),
   not `poc2_extract.system_prompt` (rules 1-3). The spec already records that
   the baseline is no longer byte-identical to 2b's; this makes the run
   measure what actually ships.
2. V1 and V2 therefore carry rule 4 too, so the only thing varying across the
   three cells is the reconciliation rule — which is what 2c measures.

Run from `engine/`:
    .venv/bin/python -m poc.poc2c_targeted [--pinned] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from poc.poc2_extract import (                                   # noqa: E402
    PLANTED_ID, PLANTED_URL, UnusableActor, _DROPS, _fixture_drops,
    _question_block, _response_envelope, _sentence_around, actor_name,
    entity_tokens, gather_sources, label_map, one_call,
    score_response,
)
from text.chunk import chunk                                     # noqa: E402
from worker import passages                                      # noqa: E402
from worker.prompts import _ACTOR_SYSTEM                         # noqa: E402
from worker.questions import REGISTRY                            # noqa: E402

POC = pathlib.Path(__file__).resolve().parent
OUT_RESPONSES = POC / "poc2c-responses"

ACTORS = ["selco-foundation", "bku-ekta-ugrahan", "bhavreen-kandhari"]
REPLACEMENTS = ["anthill-ventures", "jyoti-pande-lavakare"]
N_CELLS_WANTED = 3

SOURCES_WANTED = 4
CALL_RADIUS = 1
RUNGS = ["openrouter"]
REPEATS = 1
PLANT_RATIO = 1.35
MAX_TRANSPORT_RETRIES = 3

# Preference order for the plant target. q10 first because the spec lists it
# first; both are recorded either way.
TARGET_QUESTIONS = ["q10_funding", "q11_scale_metric"]


# ── which figures may be planted on ───────────────────────────────────────

_CURRENCY = r"(?:₹|Rs\.?|INR|USD|US\$|\$)"

# Counts and capacities only. A percentage is not a count and a year is not a
# quantity: planting on either produces a contradiction the sheet cannot ask
# about, which is exactly the defect 2c exists to remove.
_UNITS = (
    "million|lakh|lakhs|crore|crores|billion|thousand|"
    "kWp|MWp|kW|MW|GW|MWh|kWh|"
    "beneficiaries|health centres|health centers|hospitals|clinics|units|"
    "systems|installations|staff|employees|households|homes|villages|"
    "families|districts|states|people|persons|individuals|students|farmers|"
    "members|women|children|schools|customers|users|entrepreneurs|workers|"
    "patients|youth|jobs|acres|hectares|tonnes|tons|litres|liters"
)

PLANTABLE_RE = re.compile(
    rf"(?P<cur>{_CURRENCY})?\s?(?P<num>\d[\d,]*(?:\.\d+)?)"
    rf"(?:\s?(?P<unit>{_UNITS})\b)?",
    re.I)

_BARE_YEAR = re.compile(r"^(19|20)\d{2}$")


def _norm(s: str) -> str:
    return (s or "").replace(",", "").replace(" ", " ").lower()


def rescale(num: str, ratio: float = PLANT_RATIO) -> str:
    """Multiply, keeping the source figure's own precision and separator
    style. `2.5` -> `3.4`; `46,109` -> `62,247`; `4` -> `5`."""
    raw = num.replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return num
    scaled = value * ratio
    if "." in raw:
        dp = len(raw.split(".", 1)[1])
        out = f"{scaled:.{dp}f}"
        if _norm(out) == _norm(raw):                 # too small to move
            out = f"{scaled + 10 ** -dp:.{dp}f}"
    else:
        out = f"{round(scaled):,.0f}"
        if "," not in num:
            out = out.replace(",", "")
        if _norm(out) == _norm(raw):
            out = str(int(raw) + 1)
    return out


def plantable_figures(text: str) -> list[dict]:
    """Every currency/count/capacity quantity in a string, richest first.

    A bare number with neither a currency prefix nor a unit is rejected, and
    so is a bare 4-digit year — `_YEAR_RE`'s last-resort path is what put
    `2020 -> 4040` into the 2b run."""
    out = []
    for m in PLANTABLE_RE.finditer(text or ""):
        cur, num, unit = m.group("cur"), m.group("num"), m.group("unit")
        # A grouped number is a count even when the noun after it is not on
        # the unit list: `50,000 persons at peak` was dropped for want of
        # "persons", which is a hole in the list, not a fact about the
        # figure. A thousands separator cannot be a year or an ordinal, so
        # it stands on its own — a BARE number still does not.
        grouped = "," in num and float(num.replace(",", "")) >= 1000
        if not cur and not unit and not grouped:
            continue
        if not unit and not grouped and _BARE_YEAR.match(num.replace(",", "")):
            continue
        out.append({
            "full": m.group(0).strip(), "num": num,
            "currency": (cur or "").strip(), "unit": (unit or "").strip(),
            "start": m.start(),
        })
    # richest first: a figure with both a currency and a unit is the least
    # ambiguous thing to plant on.
    out.sort(key=lambda f: (bool(f["currency"]) + bool(f["unit"])), reverse=True)
    return out


# ── prompt variants ───────────────────────────────────────────────────────

_PROBE_SOURCE_NAME = "X"


def _live_baseline(kind: str) -> str:
    """The shipped batched system prompt, taken from the function that builds
    it rather than reassembled here.

    2c's first version reconstructed the prompt from parts so v1/v2 could be
    built from the same pieces, and asserted the reconstruction byte-equal to
    the shipped one. The assert did its job — it caught that the shipped
    prompt still said "Three additional rules" after a fourth shipped — but a
    reconstruction is a second copy that has to be maintained, and the
    2026-09-14 prompt revision (claims out, signals filled, chunk markers in)
    broke it the same day. Derive, then edit: drift becomes impossible.
    """
    from worker.extract_types import PromptSource
    from worker.prompts import extract_prompt_batched
    system, _ = extract_prompt_batched(
        kind, _PROBE_SOURCE_NAME,
        [PromptSource("s", "S1", "u", "t", ("s:0",), ("t",))])
    return system


# Rule 1's tail and rule 2, exactly as the shipped prompt writes them — the
# only thing the variants change. Asserted present before each swap, so a
# later prompt edit fails loudly here instead of silently producing a variant
# identical to the baseline.
_BASE_R1_TAIL = ("the list given, is DROPPED — never guess an id, and never "
                 "merge two sources into one answer.\n")
_BASE_R2 = ("2. If two sources disagree — a different figure, date, or status "
            "for the same thing — write the disagreement as the answer, "
            "naming both sides and both source ids. Do not silently pick "
            "one.\n")

_V1_R1_TAIL = ("the list given, is DROPPED — never guess an id. Do not merge "
               "two sources into one answer UNLESS the two sources disagree, "
               "in which case rule 2 below applies and merging is exactly "
               "what is required.\n")
_V1_R2 = ("2. If two sources disagree — a different figure, date, or status "
          "for the same thing — the disagreement itself is the correct "
          "answer. The `answer` text MUST explicitly name BOTH conflicting "
          "values AND BOTH source ids inline, in a form like: \"S1 gives 4 "
          "crore; S4 gives 8 crore.\" Put whichever source id you name first "
          "in the `source_id` field. Do not silently pick one figure and drop "
          "the other.\n")

_V2_PARA = ("Every conflicting figure, date, or status found across sources "
            "also goes into the top-level `disagreements` array below, one "
            "entry per conflict; an empty array means no conflicts were "
            "found.\n\n")
_V2_KEY = (',\n "disagreements": [{"question_id": "...", "value_a": "...", '
           '"source_id_a": "S1", "value_b": "...", "source_id_b": "S4", '
           '"note": "..."}]}')


def system_prompt_baseline(kind: str) -> str:
    return _live_baseline(kind)


def system_prompt_v1(kind: str) -> str:
    """2b's prose fix, applied to whatever the live prompt currently is.
    Rule 1's "never merge" is scoped to exclude the disagreement case; rule 2
    requires both figures AND both source ids inline, since the schema still
    gives one `source_id` field. Schema otherwise unchanged."""
    s = _live_baseline(kind)
    assert _BASE_R1_TAIL in s, "rule 1's tail has moved — v1 would be a no-op"
    assert _BASE_R2 in s, "rule 2 has moved — v1 would be a no-op"
    return s.replace(_BASE_R1_TAIL, _V1_R1_TAIL, 1).replace(_BASE_R2, _V1_R2, 1)


def system_prompt_v2(kind: str) -> str:
    """2b's structural fix. Rules verbatim from the live prompt; a top-level
    `disagreements` array is added to the schema."""
    s = _live_baseline(kind)
    marker = "QUESTIONS:\n"
    assert marker in s, "question block has moved — v2 would be a no-op"
    s = s.replace(marker, _V2_PARA + marker, 1)
    assert s.rstrip().endswith("}"), "schema no longer ends with `}`"
    return s.rstrip()[:-1].rstrip() + _V2_KEY


VARIANTS = {"baseline": system_prompt_baseline,
            "v1": system_prompt_v1,
            "v2": system_prompt_v2}


def log_prompt_provenance(log) -> None:
    """The three variants are derived from the live prompt, so there is
    nothing to verify — but the run record still owes the reader which prompt
    it measured."""
    base = system_prompt_baseline("actor")
    log(f"  baseline taken live from worker.prompts."
        f"extract_prompt_batched ({len(base)} chars); "
        f"v1 +{len(system_prompt_v1('actor')) - len(base)} chars, "
        f"v2 +{len(system_prompt_v2('actor')) - len(base)} chars")


# ── stage 1: build the unmodified prompt, probe it ────────────────────────

def build_prompt_marked(name: str, selected, urls: dict[str, str]) -> str:
    """`poc2_extract.build_prompt`'s layout, but rendered through the live
    `prompts.render_block` so each chunk carries its `\u27e8Sn.k\u27e9` marker.

    The PoC's own `build_prompt` predates rule 5. Leaving it in place would
    have 2c send a system prompt telling the model to cite chunk markers
    alongside a body that has none — measuring a prompt that does not exist.
    """
    from worker.extract_types import PromptSource
    from worker.prompts import render_block
    order: list[str] = []
    by_source: dict[str, list] = {}
    for ch in selected:
        if ch.source_id not in by_source:
            order.append(ch.source_id)
            by_source[ch.source_id] = []
        by_source[ch.source_id].append(ch)

    blocks = []
    for i, sid in enumerate(order, start=1):
        chunks = sorted(by_source[sid], key=lambda c: c.ordinal)
        blocks.append(render_block(PromptSource(
            source_id=sid, label=f"S{i}", url=urls.get(sid, sid),
            text="\n\n".join(c.text for c in chunks),
            chunk_refs=tuple(c.chunk_ref for c in chunks),
            chunk_texts=tuple(c.text for c in chunks))))
    return (f"Entity name: {name}\n\n"
            "Sources:\n\n" + "\n\n---\n\n".join(blocks))


def build_sources(slug: str, name: str, log, pinned: bool) -> dict:
    """Fetch/chunk/select ONCE. Stage 1 and stage 2 share this selection, so
    the only difference between the two prompts is the planted block."""
    log(f"\n=== {slug} ({name}) ===")
    tokens = entity_tokens(name)
    texts, urls = gather_sources(slug, SOURCES_WANTED, log, tokens,
                                 pinned=pinned)
    if len(texts) < 2:
        drops = _DROPS.get(slug) or _fixture_drops(slug)
        ledger = "\n".join(f"      - {d['reason']}: {d['url'][:80]} "
                           f"({d['detail']})" for d in drops) or "      (none)"
        raise UnusableActor(
            f"{slug}: only {len(texts)} usable source(s); need >= 2.\n"
            f"    what was fetched and dropped:\n{ledger}")

    all_chunks = []
    for sid, text in texts.items():
        all_chunks.extend(chunk(text, source_id=sid))
    selected = list(passages.select(all_chunks, list(REGISTRY.all("actor")),
                                    neighbour_radius=CALL_RADIUS))
    labels = label_map(selected)
    prompt = build_prompt_marked(name, selected, urls)
    log(f"  {len(texts)} sources, {len(all_chunks)} chunks, "
        f"{len(selected)} selected, {len(prompt)} prompt chars, "
        f"sources in prompt {len({c.source_id for c in selected})}/{len(texts)}")
    return {"slug": slug, "name": name, "texts": texts, "urls": urls,
            "all_chunks": all_chunks, "selected": selected, "labels": labels,
            "prompt": prompt, "chars": len(prompt)}


def probe_target(data: dict | None, labels: dict[str, str]) -> dict:
    """Stage 1's whole job: which numeric question did the model actually
    answer, with what figure, from which source. Returns the chosen target
    plus BOTH candidates' raw answers, so a drop is explainable."""
    out = {"target": None, "candidates": {}}
    if not isinstance(data, dict):
        return out
    answers = data.get("answers") or []
    by_q = {}
    for a in answers:
        qid = str((a or {}).get("question_id") or "")
        if qid in TARGET_QUESTIONS and qid not in by_q:
            by_q[qid] = a
    label_to_sid = {v: k for k, v in labels.items()}
    for qid in TARGET_QUESTIONS:
        a = by_q.get(qid)
        if a is None:
            out["candidates"][qid] = {"answered": False}
            continue
        text = str(a.get("answer") or "")
        figs = plantable_figures(text)
        sid_label = str(a.get("source_id") or "").strip().strip("[]")
        out["candidates"][qid] = {
            "answered": True, "answer": text, "source_label": sid_label,
            "source_id": label_to_sid.get(sid_label),
            "figures": [f["full"] for f in figs],
        }
        if figs and out["target"] is None:
            f = figs[0]
            out["target"] = {
                "question_id": qid, "answer": text,
                "source_label": sid_label,
                "source_id": label_to_sid.get(sid_label),
                "figure": f["full"], "num": f["num"],
                "currency": f["currency"], "unit": f["unit"],
                "altered_num": rescale(f["num"]),
            }
    return out


# ── stage 2: the targeted plant ───────────────────────────────────────────

def targeted_plant(built: dict, target: dict, log) -> dict:
    """A synthetic source stating the SAME quantity in the SAME unit at a
    different value, attributed to a different publisher.

    Preference is the figure's own sentence from the real source, so the
    rival claim reads like the page it contradicts. If the number cannot be
    located in the sources (the model reformatted it — `INR 46,109` for
    `46109`), fall back to restating the model's own answer sentence. The
    fallback is recorded, not hidden: a plant built from a paraphrase is a
    weaker stimulus and the results file has to say so."""
    num, altered = target["num"], target["altered_num"]
    hunt = [c for c in built["selected"] if c.source_id == target["source_id"]]
    hunt += [c for c in built["selected"] if c.source_id != target["source_id"]]
    for ch in hunt:
        idx = ch.text.find(num)
        if idx < 0:
            continue
        sentence = _sentence_around(ch.text, idx)
        if len(sentence) < 40:
            continue
        return {"sentence": sentence,
                "altered_sentence": sentence.replace(num, altered, 1),
                "from": "source", "from_chunk": ch.chunk_ref,
                "original": num, "altered": altered,
                "unit": target["unit"] or target["currency"] or "count",
                "question_id": target["question_id"]}
    log(f"  NOTE: {num!r} not found verbatim in the selected passages — "
        f"plant built from the model's own answer sentence (weaker stimulus)")
    sentence = target["answer"].strip()
    return {"sentence": sentence,
            "altered_sentence": sentence.replace(num, altered, 1),
            "from": "answer", "from_chunk": None,
            "original": num, "altered": altered,
            "unit": target["unit"] or target["currency"] or "count",
            "question_id": target["question_id"]}


def planted_text(plant: dict, name: str) -> str:
    return (f"Sector Review Panel — independent assessment, 2024.\n\n"
            f"Reviewing {name}: {plant['altered_sentence']}\n\n"
            f"This figure is the panel's own count, compiled from programme "
            f"records, and is not the figure the organisation publishes.")


def build_planted_prompt(built: dict, plant: dict) -> dict:
    planted = chunk(planted_text(plant, built["name"]), source_id=PLANTED_ID)
    selected = list(built["selected"]) + planted
    labels = label_map(selected)
    urls = dict(built["urls"])
    urls[PLANTED_ID] = PLANTED_URL
    prompt = build_prompt_marked(built["name"], selected, urls)
    return {"prompt": prompt, "labels": labels, "chars": len(prompt),
            "planted_label": labels.get(PLANTED_ID)}


# ── scoring, restricted to the targeted question ──────────────────────────

_SID_INLINE = re.compile(r"\bS\d+\b")


def score_target(data: dict | None, target: dict, plant: dict,
                 labels: dict[str, str], planted_label: str | None,
                 valid_labels: set[str]) -> dict:
    """The four primary metrics, all on the targeted `question_id` only."""
    qid = target["question_id"]
    out = {"question_id": qid, "target_answered": False,
           "target_both_values": False, "target_both_ids": False,
           "reconciled": False, "void_reason": None,
           "target_answer_text": None, "target_source_label": None,
           "ids_seen": [], "via": None}
    if not isinstance(data, dict):
        out["void_reason"] = "unparsed"
        return out

    flagged = {str((m or {}).get("source_id") or "").strip().strip("[]")
               for m in (data.get("misidentified") or [])
               if isinstance(m, dict)}
    out["misidentified_labels"] = sorted(l for l in flagged if l)
    out["planted_flagged"] = bool(planted_label and planted_label in flagged)
    out["target_source_flagged"] = bool(target.get("source_label")
                                        and target["source_label"] in flagged)

    answers = [a for a in (data.get("answers") or [])
               if str((a or {}).get("question_id") or "") == qid]
    if not answers:
        # Rule 4 made this a THREE-way void, not a binary. A flagged source is
        # a correct refusal, not a declined question.
        out["void_reason"] = ("flagged" if out["target_source_flagged"]
                              else "declined")
        return out

    out["target_answered"] = True
    text = " ".join(str(a.get("answer") or "") for a in answers)
    out["target_answer_text"] = text[:600]
    out["target_source_label"] = str(
        (answers[0] or {}).get("source_id") or "").strip().strip("[]")

    n_text = _norm(text)
    out["target_both_values"] = (_norm(plant["original"]) in n_text
                                 and _norm(plant["altered"]) in n_text)

    ids = set(_SID_INLINE.findall(text))
    for a in answers:
        sid = str((a or {}).get("source_id") or "").strip().strip("[]")
        if sid:
            ids.add(sid)
    ids = {i for i in ids if i in valid_labels}
    out["ids_seen"] = sorted(ids)
    real_label = target.get("source_label")
    if planted_label and planted_label in ids and len(ids) >= 2:
        if not real_label or real_label in ids:
            out["target_both_ids"] = True
            out["via"] = "answer"

    # V2's structural route: a disagreements[] entry may carry the pair
    # instead of the answer text.
    for d in (data.get("disagreements") or []):
        if not isinstance(d, dict):
            continue
        if str(d.get("question_id") or "") not in ("", qid):
            continue
        blob = _norm(json.dumps(d, ensure_ascii=False))
        if _norm(plant["original"]) not in blob or _norm(plant["altered"]) not in blob:
            continue
        sa = str(d.get("source_id_a") or "").strip().strip("[]")
        sb = str(d.get("source_id_b") or "").strip().strip("[]")
        if sa in valid_labels and sb in valid_labels and sa != sb:
            out["target_both_values"] = True
            out["target_both_ids"] = True
            out["via"] = out["via"] or "disagreements"

    out["reconciled"] = bool(out["target_both_values"] and out["target_both_ids"])
    return out


_LEGACY_MARKERS = (
    "disagree", "conflict", "contradict", "however", "whereas", "but ",
    "differs", "different figure", "vs", "versus", "range", "while ",
    "inconsistent", "two figures", "another source", "other source",
)


def score_scan_fixed(data: dict | None, plant: dict) -> dict:
    """2's and 2b's `marker`/`both_figures` scanned `json.dumps(data)` — the
    whole response, `edges[]` evidence strings included. All three of 2b's V2
    calls scored `marker=True` while `disagreements[]` was empty. Restrict
    the scan to `answers` + `disagreements`, and keep the whole-blob value
    under a separate key so 2b's numbers stay reproducible rather than
    silently restated."""
    if not isinstance(data, dict):
        return {"marker": False, "both_figures": False,
                "legacy_marker": False, "legacy_both_figures": False}
    # VALUES only, never the wrapper's key names: `{"disagreements": []}`
    # contains the substring "disagree", so scanning a dict that has the key
    # scores `marker=True` on an empty list. The legacy whole-blob scan has
    # the same defect and keeps it, because its job is to reproduce 2b.
    scoped = _norm(json.dumps([data.get("answers") or [],
                               data.get("disagreements") or []],
                              ensure_ascii=False))
    whole = _norm(json.dumps(data, ensure_ascii=False))
    o, a = _norm(plant["original"]), _norm(plant["altered"])
    return {
        "marker": any(w in scoped for w in _LEGACY_MARKERS),
        "both_figures": o in scoped and a in scoped,
        "legacy_marker": any(w in whole for w in _LEGACY_MARKERS),
        "legacy_both_figures": o in whole and a in whole,
    }


def call_with_retry(prompt: str, system: str, rung: str, tag: str, log):
    """Transport failure is a HOLE, not a negative — one observation per cell
    cannot absorb one. Up to `MAX_TRANSPORT_RETRIES` attempts; the free rung
    transport-failed 2 of 9 calls in 2b."""
    last = None
    for attempt in range(1, MAX_TRANSPORT_RETRIES + 1):
        try:
            return one_call(prompt, system, rung), attempt, None
        except Exception as e:                                  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            log(f"  {tag}: transport attempt {attempt}/"
                f"{MAX_TRANSPORT_RETRIES} FAILED {last[:140]}")
    return None, MAX_TRANSPORT_RETRIES, last


# ── run ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pinned", action="store_true", default=True,
                    help="load sources from fixtures, 0 HTTP (default)")
    ap.add_argument("--live", dest="pinned", action="store_false",
                    help="fetch live — NOT reproducible, breaks the design")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print prompt sizes, make no calls")
    args = ap.parse_args()

    OUT_RESPONSES.mkdir(parents=True, exist_ok=True)
    handle = (POC / "poc2c_run.log").open("w", encoding="utf-8")

    def log(*parts):
        line = " ".join(str(p) for p in parts)
        print(line)
        handle.write(line + "\n")
        handle.flush()

    log("PoC-2c — reconciliation on a targeted, credible plant")
    log(f"  pinned={args.pinned} dry_run={args.dry_run} "
        f"ratio={PLANT_RATIO} rungs={RUNGS} radius={CALL_RADIUS} "
        f"variants={list(VARIANTS)}")
    log_prompt_provenance(log)

    log("\n[1] STAGE 1 — probe the unmodified sources for a plantable figure")
    cells, drops, queue = [], [], list(ACTORS) + list(REPLACEMENTS)
    probe_rows = []
    while queue and len(cells) < N_CELLS_WANTED:
        slug = queue.pop(0)
        name = actor_name(slug)
        try:
            built = build_sources(slug, name, log, args.pinned)
        except UnusableActor as e:
            log(f"  DROPPED {slug}: {e}")
            drops.append({"slug": slug, "stage": "build", "why": str(e)})
            continue

        if args.dry_run:
            log(f"  [dry-run] stage-1 prompt {built['chars']} chars")
            cells.append({"built": built, "probe": None})
            continue

        tag = f"{slug}__probe"
        res, attempts, err = call_with_retry(
            built["prompt"], system_prompt_baseline("actor"), RUNGS[0], tag, log)
        if res is None:
            log(f"  DROPPED {slug}: probe never returned ({err})")
            drops.append({"slug": slug, "stage": "probe-transport", "why": err})
            continue
        (OUT_RESPONSES / f"{tag}.json").write_text(json.dumps(
            _response_envelope(res, built["prompt"],
                               system_prompt_baseline("actor"), None),
            ensure_ascii=False, indent=1))

        p = probe_target(res.get("json"), built["labels"])
        probe_rows.append({"slug": slug, "attempts": attempts,
                           "parsed": res.get("json") is not None,
                           "parse_error": res.get("parse_error"),
                           "n_answers": len((res.get("json") or {}).get("answers") or [])
                           if isinstance(res.get("json"), dict) else 0,
                           **p})
        for qid, c in p["candidates"].items():
            log(f"  {slug} {qid}: answered={c['answered']}"
                + (f" figures={c.get('figures')} src={c.get('source_label')}"
                   f" — {str(c.get('answer'))[:110]!r}" if c["answered"] else ""))
        if p["target"] is None:
            log(f"  DROPPED {slug}: no plantable currency/count/capacity "
                f"figure in q10 or q11 — this is the check 2 and 2b lacked")
            drops.append({"slug": slug, "stage": "probe-no-target",
                          "why": "no plantable figure in q10/q11",
                          "candidates": p["candidates"]})
            continue
        t = p["target"]
        log(f"  TARGET {slug}: {t['question_id']} {t['figure']!r} "
            f"({t['num']} -> {t['altered_num']}) from {t['source_label']}")
        cells.append({"built": built, "probe": p, "target": t})

    if len(cells) < N_CELLS_WANTED:
        log(f"\nFATAL: only {len(cells)}/{N_CELLS_WANTED} actors survived "
            f"stage 1 and the replacement queue is exhausted. Drops:")
        for d in drops:
            log(f"  - {d['slug']} ({d['stage']}): {str(d['why'])[:200]}")
        handle.close()
        return 1

    log("\n[2] STAGE 2 — targeted plant, one prompt body per actor")
    for cell in cells:
        if args.dry_run:
            continue
        plant = targeted_plant(cell["built"], cell["target"], log)
        cell["plant"] = plant
        cell["planted"] = build_planted_prompt(cell["built"], plant)
        log(f"  {cell['built']['slug']}: {plant['original']} -> "
            f"{plant['altered']} ({plant['unit']}, from={plant['from']}) "
            f"| prompt {cell['built']['chars']} -> "
            f"{cell['planted']['chars']} chars, "
            f"planted_label={cell['planted']['planted_label']}")
        log(f"      planted sentence: "
            f"{plant['altered_sentence'][:200]!r}")

    if args.dry_run:
        log("\n[dry-run] no calls made")
        handle.close()
        return 0

    log("\n[3] CALLS — 3 actors x 3 variants x 1 repeat")
    rows = []
    for cell in cells:
        built, plant, planted = cell["built"], cell["plant"], cell["planted"]
        valid = set(planted["labels"].values())
        for vname, vfunc in VARIANTS.items():
            system = vfunc("actor")
            for i in range(REPEATS):
                tag = f"{built['slug']}__{vname}__{RUNGS[0]}__{i}"
                res, attempts, err = call_with_retry(
                    planted["prompt"], system, RUNGS[0], tag, log)
                if res is None:
                    log(f"  {tag}: HOLE — transport failed "
                        f"{MAX_TRANSPORT_RETRIES}x")
                    rows.append({"slug": built["slug"], "variant": vname,
                                 "i": i, "hole": True, "parsed": False,
                                 "void_reason": "hole", "error": err,
                                 "question_id": cell["target"]["question_id"]})
                    continue
                (OUT_RESPONSES / f"{tag}.json").write_text(json.dumps(
                    _response_envelope(res, planted["prompt"], system, plant),
                    ensure_ascii=False, indent=1))

                data = res.get("json")
                row = {"slug": built["slug"], "variant": vname, "i": i,
                       "hole": False, "transport_attempts": attempts,
                       "parsed": isinstance(data, dict),
                       "parse_error": res.get("parse_error"),
                       "truncated": bool(res.get("truncated")),
                       "prompt_chars": planted["chars"],
                       "model": res.get("model"),
                       "input_tokens": res.get("input_tokens"),
                       "output_tokens": res.get("output_tokens")}
                row.update(score_target(data, cell["target"], plant,
                                        planted["labels"],
                                        planted["planted_label"], valid))
                row.update(score_scan_fixed(data, plant))
                legacy = score_response(res, valid, {"original": plant["original"],
                                                     "altered": plant["altered"]},
                                        planted["planted_label"])
                row["attribution"] = {
                    "answers": legacy.get("answers"),
                    "with_valid_id": legacy.get("with_valid_id"),
                    "with_unknown_id": legacy.get("with_unknown_id"),
                    "no_id": legacy.get("no_id"),
                    "cited_planted": legacy.get("cited_planted"),
                }
                rows.append(row)
                log(f"  {tag}: parsed={row['parsed']} "
                    f"target_answered={row['target_answered']} "
                    f"both_values={row['target_both_values']} "
                    f"both_ids={row['target_both_ids']} "
                    f"RECONCILED={row['reconciled']} "
                    f"via={row['via']} void={row['void_reason']} "
                    f"misid={row.get('misidentified_labels')} "
                    f"planted_flagged={row.get('planted_flagged')} "
                    f"| marker={row['marker']} (legacy "
                    f"{row['legacy_marker']}) "
                    f"both_figs={row['both_figures']} (legacy "
                    f"{row['legacy_both_figures']})")
                if row.get("target_answer_text"):
                    log(f"      answer: {row['target_answer_text'][:220]!r}")

    log("\n[4] SUMMARY — scored cells only; voids and holes reported apart")
    for vname in VARIANTS:
        sub = [r for r in rows if r["variant"] == vname]
        holes = [r for r in sub if r.get("hole")]
        unparsed = [r for r in sub if not r.get("hole") and not r["parsed"]]
        voids = [r for r in sub if not r.get("hole") and r["parsed"]
                 and not r["target_answered"]]
        scored = [r for r in sub if not r.get("hole") and r["parsed"]
                  and r["target_answered"]]
        rec = sum(1 for r in scored if r["reconciled"])
        bv = sum(1 for r in scored if r["target_both_values"])
        bi = sum(1 for r in scored if r["target_both_ids"])
        log(f"  {vname}: reconciled {rec}/{len(scored)} scored "
            f"(both_values {bv}, both_ids {bi}) | "
            f"voids {len(voids)} "
            f"{[r['void_reason'] for r in voids]} | "
            f"unparsed {len(unparsed)} | holes {len(holes)}")
    n_holes = sum(1 for r in rows if r.get("hole"))
    if n_holes > 2:
        log(f"  WARNING: {n_holes}/9 holes — per the spec the free rung is "
            f"not adequate for a one-observation-per-cell design; repeat on "
            f"a paid rung.")
    flagged_plant = [r["slug"] + "/" + r["variant"] for r in rows
                     if r.get("planted_flagged")]
    if flagged_plant:
        log(f"  NOTE: the plant itself was flagged misidentified in "
            f"{flagged_plant} — a meaningful result, recorded not retried.")

    (POC / "poc2c_summary.json").write_text(json.dumps(
        {"config": {"ratio": PLANT_RATIO, "radius": CALL_RADIUS,
                    "rungs": RUNGS, "repeats": REPEATS,
                    "pinned": args.pinned,
                    "target_questions": TARGET_QUESTIONS},
         "actors": [{"slug": c["built"]["slug"], "name": c["built"]["name"],
                     "target": c["target"], "plant": c["plant"],
                     "chars": c["planted"]["chars"],
                     "planted_label": c["planted"]["planted_label"]}
                    for c in cells],
         "probes": probe_rows, "drops": drops, "rows": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"\nwrote {POC / 'poc2c_summary.json'}")
    handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
