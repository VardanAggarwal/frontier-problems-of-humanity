"""PoC-2 — does the batched `[S1]…[Sn]` extraction call attribute and reconcile?

`04-worker-build-plan.md` §2 (PoC-2) and `03-worker.md` §8. Three questions,
plus one added by PoC-1d's adoption:

  1. JSON parse success rate  — §13 mitigates failure with a per-source retry;
     how often that path fires decides whether it is worth writing.
  2. Share of answers carrying a valid `source_id` — §8 *requires* it and drops
     answers without it. An unmeasured drop rate is an unmeasured hole in the
     coverage metric everything else is tuned against.
  3. Whether a planted contradiction is reconciled — the entire justification
     for batching over per-source calls.
  4. (added) What neighbour expansion costs against `PASSAGE_TOKEN_CAP` —
     radius 1 vs radius 0, measured on the real prompt this builds.

Run from `engine/`:  python -m poc.poc2_extract [--repeats 5] [...]

Deliberate setup choices, each of which the results file has to carry:

* **Sources come from PoC-0b's recorded search responses**, not hand-picked:
  the URL pool for one actor, ranked by best SearXNG `score`, deduped by
  domain. That is the input stage 2 would really hand stage 6.
* **`04` §2 assumed "the 92 rows already in `source` mean this costs no
  HTTP". That premise is false** — 89 of the 92 rows have no cached text on
  disk (`path` NULL or file absent), and of the 3 that do, two are ~1.5 KB.
  So this PoC fetches. It fetches into a *copy* of `problems/graph.db` under
  the scratch dir, with its own cache directory, so a PoC run leaves no diff
  in a tracked database.
* **The contradiction is planted, not found.** A synthetic extra source
  repeats one real figure from the real passages with the number changed and
  a different publisher attached. Reconciliation is *instructed* in the
  system prompt (the repo's own "when sources disagree, write the
  disagreement" standard, which track E will ship), so what is measured is
  compliance, not spontaneity — the weaker claim, and the honest one.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from text.chunk import chunk                                  # noqa: E402
from worker import llm, passages                              # noqa: E402
from worker.fetch import fetch                                # noqa: E402
from worker.prompts import _ACTOR_SYSTEM                      # noqa: E402
from worker.questions import REGISTRY                         # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
POC = pathlib.Path(__file__).resolve().parent
RESPONSES = POC / "poc0b-responses"
SCRATCH = POC / "poc2-scratch"
OUT_RESPONSES = POC / "poc2-responses"
FIXTURES = POC / "fixtures"

PLANTED_ID = "PLANTED"
PLANTED_URL = "https://review.example.org/annual-review-2024"

FIGURE_RE = re.compile(
    r"\b(?:(?:₹|Rs\.?|INR|USD|\$)\s?)?(\d[\d,]*(?:\.\d+)?)\s?"
    r"(%|per cent|percent|million|lakh|crore|billion|thousand|"
    r"kWp|MWp|kW|MW|beneficiaries|health centres|health centers|"
    r"hospitals|clinics|units|systems|installations|staff|employees|"
    r"households|villages|families|districts|states|people)\b",
    re.I)

# 4-digit years, tried ONLY if nothing above matched (module docstring's
# "last resort" — a bare year is a weak "figure" but better than none).
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

DISAGREEMENT_MARKERS = (
    "disagree", "conflict", "contradict", "however", "whereas", "but ",
    "differs", "different figure", "vs", "versus", "range", "while ",
    "inconsistent", "two figures", "another source", "other source",
)


# ── the batched prompt (`03-worker.md` §8) ────────────────────────────────

def _question_block(kind: str) -> str:
    lines = []
    for q in REGISTRY.all(kind):
        flag = " [multiple answers allowed]" if q.multi else ""
        lines.append(f"- {q.id}: {q.question}{flag}")
    return "\n".join(lines)


def system_prompt(kind: str) -> str:
    """The shipped per-source system prompt (`worker/prompts.py`) plus exactly
    what batching adds: source ids, the question ids the ledger keys on, and
    the reconciliation instruction."""
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
        "QUESTIONS:\n" + _question_block(kind) + "\n\n"
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


def build_prompt(entity_name: str, selected, urls: dict[str, str]) -> str:
    """`[Sn] url` blocks, chunks under each in document order — the layout
    `03-worker.md` §8 draws. Source order follows first appearance in the
    ranked selection, so `S1` is the source retrieval liked most."""
    order: list[str] = []
    by_source: dict[str, list] = defaultdict(list)
    for ch in selected:
        if ch.source_id not in by_source:
            order.append(ch.source_id)
        by_source[ch.source_id].append(ch)

    blocks = []
    for i, sid in enumerate(order, start=1):
        chunks = sorted(by_source[sid], key=lambda c: c.ordinal)
        body = "\n\n".join(c.text for c in chunks)
        blocks.append(f"[S{i}] {urls.get(sid, sid)}\n{body}")
    return (f"Entity name: {entity_name}\n\n"
            "Sources:\n\n" + "\n\n---\n\n".join(blocks))


def label_map(selected) -> dict[str, str]:
    """`S1`… label per source id, in the same first-appearance order
    `build_prompt` uses — so metrics can check a cited id against reality."""
    order = []
    for ch in selected:
        if ch.source_id not in order:
            order.append(ch.source_id)
    return {sid: f"S{i}" for i, sid in enumerate(order, start=1)}


# ── the planted contradiction ─────────────────────────────────────────────

def plant(selected) -> tuple[list, dict | None]:
    """Find a real figure in the selected passages, restate its sentence with
    the number changed and a different publisher, and append it as one more
    source. Returns (chunks_with_planted, plant_info)."""
    for pattern, is_year in ((FIGURE_RE, False), (_YEAR_RE, True)):
        for ch in selected:
            if ch.source_id == PLANTED_ID:
                continue
            m = pattern.search(ch.text)
            if not m:
                continue
            sentence = _sentence_around(ch.text, m.start())
            if len(sentence) < 40:
                continue
            original = m.group(0) if is_year else m.group(1)
            unit = "year" if is_year else m.group(2)
            altered = _alter(original)
            info = {"original": original, "altered": altered, "unit": unit,
                    "sentence": sentence,
                    "altered_sentence": sentence.replace(original, altered, 1),
                    "from_chunk": ch.chunk_ref, "last_resort": is_year}
            return list(selected), info
    return list(selected), None


def _planted_text(info: dict) -> str:
    return (f"Annual Review 2024 — independent assessment.\n\n"
            f"{info['altered_sentence']}\n\n"
            f"This figure is the reviewers' own count and is not the same as "
            f"the one the organisation publishes.")


def _sentence_around(text: str, idx: int) -> str:
    start = max(text.rfind(". ", 0, idx), text.rfind("\n", 0, idx))
    start = 0 if start < 0 else start + 1
    end = text.find(". ", idx)
    end = len(text) if end < 0 else end + 1
    return text[start:end].strip()


def _alter(original: str) -> str:
    """Double it, keeping the thousands-separator style of the original — a
    value no reader could mistake for a rounding difference."""
    try:
        value = float(original.replace(",", ""))
    except ValueError:
        return original + "0"
    doubled = value * 2
    if doubled >= 1000:
        out = f"{doubled:,.0f}"
        return out if "," in original else out.replace(",", "")
    return f"{doubled:g}"


# ── metrics on one response ───────────────────────────────────────────────

def score_response(result: dict, valid_labels: set[str], plant_info: dict | None,
                   planted_label: str | None = None) -> dict:
    data = result.get("json")
    text = result.get("text") or ""
    out = {
        "parsed": isinstance(data, dict),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "cost": result.get("cost"),
    }
    if not isinstance(data, dict):
        out.update(answers=0, with_valid_id=0, with_unknown_id=0, no_id=0,
                   distinct_sources=0, cited_planted=False,
                   reconciled=False, both_figures=False, marker=False)
        return out

    answers = data.get("answers") or []
    valid = unknown = missing = 0
    cited: set[str] = set()
    for a in answers:
        sid = (a or {}).get("source_id")
        if not sid:
            missing += 1
            continue
        sid = str(sid).strip().strip("[]")
        if sid in valid_labels:
            valid += 1
            cited.add(sid)
        else:
            unknown += 1
    out.update(answers=len(answers), with_valid_id=valid,
               with_unknown_id=unknown, no_id=missing,
               distinct_sources=len(cited),
               claims=len(data.get("claims") or []),
               emits=len(data.get("emits") or []),
               edges=len(data.get("edges") or []))

    blob = json.dumps(data, ensure_ascii=False).lower()
    both = marker = False
    if plant_info:
        both = (plant_info["original"].lower() in blob
                and plant_info["altered"].lower() in blob)
        marker = any(w in blob for w in DISAGREEMENT_MARKERS)
    out.update(cited_planted=bool(planted_label) and planted_label in cited,
               both_figures=both, marker=marker,
               reconciled=bool(both and marker))
    _ = text
    return out


# ── run ───────────────────────────────────────────────────────────────────

def url_pool(slug: str) -> list[str]:
    best: dict[str, float] = {}
    for path in sorted(RESPONSES.glob(f"{slug}__*.json")):
        payload = json.loads(path.read_text())
        for r in payload["raw_response"].get("results", []):
            url = r.get("url")
            if not url:
                continue
            best[url] = max(best.get(url, 0.0), float(r.get("score") or 0.0))
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    seen_domains: set[str] = set()
    out = []
    for url, _score in ranked:
        domain = urlparse(url).netloc.lower()
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        out.append(url)
    return out


_GENERIC = {"foundation", "trust", "india", "society", "ventures", "capital",
            "association", "network", "group", "council", "centre", "center"}


def entity_tokens(name: str) -> list[str]:
    """Distinctive tokens of the entity name — the crude stand-in for gate 2
    this PoC turned out to need (see the module docstring's addendum)."""
    toks = [t.lower().strip(".,()") for t in name.split()]
    distinctive = [t for t in toks if len(t) >= 4 and t not in _GENERIC]
    return distinctive or [t for t in toks if len(t) >= 4] or toks


def about_entity(text: str, tokens: list[str]) -> bool:
    low = text.lower()
    return any(t in low for t in tokens)


def fixture_path(slug: str) -> pathlib.Path:
    return FIXTURES / f"{slug}.json"


def _fixture_drops(slug: str) -> list[dict]:
    """The drop ledger recorded at capture time, if the fixture has one.
    Fixtures captured before the ledger existed carry no `dropped` key; say
    so rather than implying nothing was dropped."""
    path = fixture_path(slug)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "dropped" not in payload:
        return [{"reason": "unrecorded", "url": "",
                 "detail": f"fixture {path.name} predates the drop ledger; "
                           f"recapture to find out why it is empty"}]
    return payload["dropped"]


def load_fixture_sources(slug: str, want: int) -> tuple[dict[str, str], dict[str, str]]:
    """`--pinned`: load a previously captured source set instead of fetching
    live — zero HTTP. Fails loudly naming the actor when no fixture exists;
    never silently falls back to a live fetch. Truncated to `want` sources,
    in the order they were captured, so a smaller `--sources` on the pinned
    run still exercises the same downstream code deterministically."""
    path = fixture_path(slug)
    if not path.exists():
        raise RuntimeError(
            f"--pinned: no fixture for actor {slug!r} at {path} — run with "
            f"--capture-fixtures for this actor first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = (payload.get("sources") or [])[:want]
    texts = {s["source_id"]: s["text"] for s in sources}
    urls = {s["source_id"]: s.get("url", "") for s in sources}
    return texts, urls


def write_fixture(slug: str, texts: dict[str, str], urls: dict[str, str]) -> None:
    """`--capture-fixtures`: freeze the just-fetched, already-filtered
    (words>=150, on-topic) source set to disk so a later `--pinned` run feeds
    the exact same texts into chunking/selection/planting — pinning the
    source set at the FETCH boundary, not the prompt boundary."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    payload = {
        "slug": slug,
        "captured_utc": _dt.datetime.now(_dt.timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": [{"source_id": sid, "url": urls.get(sid, ""), "text": text}
                    for sid, text in texts.items()],
        # what was fetched and NOT kept, with the reason — a zero-source
        # fixture must explain itself rather than look like an absence
        "dropped": _DROPS.get(slug, []),
    }
    fixture_path(slug).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


# Every source the gather step declines, with why. Nothing is discarded on an
# unconfirmable read: a drop is a recorded decision here, written into the
# fixture alongside the sources that survived, so a zero-source capture can be
# explained afterwards instead of guessed at. MIN_WORDS is named rather than
# inlined so the threshold appears in the drop reason.
MIN_WORDS = 150
_DROPS: dict[str, list[dict]] = {}


class UnusableActor(RuntimeError):
    """An actor that cannot support the test, raised rather than returned.

    This used to be `return None`, which the runner turned into a silent skip
    — and a one-observation-per-cell design cannot absorb a silent skip: the
    cell is simply absent from the matrix and the results file reads as if it
    were never specified. Two fixtures (`selco-foundation`,
    `bhavreen-kandhari`) captured zero sources and skipped this way, and the
    cause went undiagnosed for a day. Fail loudly, and carry the drop ledger
    in the message so the failure explains itself."""



def _drop(slug: str, url: str, reason: str, detail: str, *, words: int = 0,
          source_id: str = "", text: str | None = None) -> None:
    _DROPS.setdefault(slug, []).append({
        "url": url, "reason": reason, "detail": detail, "words": words,
        "source_id": source_id,
        # keep a head of the text when there was any, so an "off-topic" or
        # "too-thin" call can be reviewed without refetching
        "text_head": (text or "")[:400],
    })


def gather_sources(slug: str, want: int, log, tokens: list[str],
                   pinned: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    """Fetch down the ranked pool until `want` sources come back usable AND
    about the entity. Returns (source_id -> text, source_id -> url).

    `pinned=True` skips HTTP entirely and loads from the actor's fixture
    (see `load_fixture_sources`) — everything downstream of this function
    (chunking, selection, planting) still runs live on whatever it returns.
    """
    if pinned:
        texts, urls = load_fixture_sources(slug, want)
        log(f"  [pinned] {len(texts)} sources loaded from fixture, 0 HTTP")
        return texts, urls

    SCRATCH.mkdir(parents=True, exist_ok=True)
    db = SCRATCH / "graph.db"
    if not db.exists():
        shutil.copy(ROOT / "problems" / "graph.db", db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    texts: dict[str, str] = {}
    urls: dict[str, str] = {}
    for url in url_pool(slug):
        if len(texts) >= want:
            break
        try:
            res = fetch(conn, SCRATCH, url)
        except Exception as e:                                  # noqa: BLE001
            _drop(slug, url, "fetch-raised", f"{type(e).__name__}: {e}")
            log(f"  fetch ERROR {type(e).__name__} {url[:70]}")
            continue
        conn.commit()
        state = getattr(res.state, "state", "?")
        words = len((res.text or "").split())

        # Name the ACTUAL reason. This used to print "OFF-TOPIC (gate-2
        # stand-in)" for every text-less result, which meant a cache hit
        # returning no text (the `worker/fetch.py` relative-path bug, fixed
        # 2026-09-14) was logged as a judgment about the page's subject. Two
        # whole fixtures captured zero sources that way and the log said the
        # pages were off-topic. Check the cheap, certain reasons first and
        # only call something off-topic when there is text to judge.
        if res.error:
            reason, detail = "fetch-error", res.error
        elif not res.text:
            reason, detail = "no-text", f"state={state}"
        elif words < MIN_WORDS:
            reason, detail = "too-thin", f"{words}w < {MIN_WORDS}"
        elif not about_entity(res.text, tokens):
            reason, detail = "off-topic", f"none of {tokens} in text"
        else:
            reason, detail = None, ""

        log(f"  {state:8} {words:6}w cache={int(res.cache_hit)} "
            f"{url[:70]}" + (f"  DROPPED {reason}: {detail}" if reason else ""))
        if reason:
            _drop(slug, url, reason, detail, words=words,
                  source_id=res.source_id, text=res.text)
        else:
            texts[res.source_id] = res.text
            urls[res.source_id] = url
        time.sleep(1.0)
    conn.close()
    return texts, urls


def actor_name(slug: str) -> str:
    """Human-readable name from the actor record's H1, falling back to a
    title-cased slug. The name is what the prompt calls the entity, so it has
    to match what the pages call it."""
    path = ROOT / "problems" / "actors" / f"{slug}.md"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return slug.replace("-", " ").title()


def build_for_actor(slug: str, name: str, want_sources: int, radii: list[int],
                    log, pinned: bool = False,
                    capture_fixtures: bool = False) -> dict:
    """Fetch, chunk, select, plant, build — everything up to the call, for one
    actor. Raises `UnusableActor` when the actor cannot support the test at
    all — never returns None, so a cell is never silently absent."""
    log(f"\n=== {slug} ({name}) ===")
    tokens = entity_tokens(name)
    texts, urls = gather_sources(slug, want_sources, log, tokens, pinned=pinned)
    if capture_fixtures and not pinned:
        write_fixture(slug, texts, urls)
        log(f"  [capture-fixtures] wrote fixture for {slug}: "
            f"{len(texts)} sources -> {fixture_path(slug)}")
    if len(texts) < 2:
        drops = _DROPS.get(slug) or _fixture_drops(slug)
        ledger = "\n".join(f"      - {d['reason']}: {d['url'][:80]} "
                            f"({d['detail']})" for d in drops) or "      (none recorded)"
        raise UnusableActor(
            f"{slug}: only {len(texts)} usable source(s); need >= 2 to test "
            f"attribution at all.\n    what was fetched and dropped:\n{ledger}")

    all_chunks = []
    for sid, text in texts.items():
        all_chunks.extend(chunk(text, source_id=sid))
    _, plant_info = plant(all_chunks)
    planted_chunks = (chunk(_planted_text(plant_info), source_id=PLANTED_ID)
                      if plant_info else [])
    log(f"  {len(texts)} sources, {len(all_chunks)} chunks, planted="
        + (f"{plant_info['original']}->{plant_info['altered']} "
           f"({plant_info['unit']})" if plant_info else "NONE"))

    actor_questions = list(REGISTRY.all("actor"))
    built: dict[int, dict] = {}
    for radius in radii:
        selected = passages.select(all_chunks, actor_questions,
                                   neighbour_radius=radius)
        real_sids = {c.source_id for c in selected}
        selected = list(selected) + planted_chunks
        labels = label_map(selected)
        url_by_id = dict(urls)
        url_by_id[PLANTED_ID] = PLANTED_URL
        prompt = build_prompt(name, selected, url_by_id)
        built[radius] = {
            "prompt": prompt, "labels": labels, "plant": plant_info,
            "n_chunks": len(selected),
            "passage_tokens": sum(max(c.token_count, 0) for c in selected),
            "chars": len(prompt),
            "n_sources_fetched": len(texts),
            "n_sources_in_prompt": len(real_sids),
        }
        log(f"  radius={radius}: {built[radius]['n_chunks']} chunks, "
            f"{built[radius]['passage_tokens']} passage tokens, "
            f"{built[radius]['chars']} chars, source coverage "
            f"{len(real_sids)}/{len(texts)}")
    return {"slug": slug, "name": name, "built": built}


def one_call(prompt: str, system: str, rung: str) -> dict:
    """One call, parsed HERE rather than inside `llm.call`.

    `json_out=True` makes `llm.py` treat a malformed response as a retryable
    error and spend its whole attempt ladder on it — so the parse rate it
    yields is "parse rate after up to six retries", which is not the number
    §13 needs to size its per-source retry. `json_out=False` returns the raw
    text whatever it is; we parse it once, and keep the malformed string.
    Transport retries (5xx, 429) stay inside `llm.call`, where they belong.
    """
    res = llm.call(prompt, tier="mechanical", max_tokens=4096, system=system,
                   json_out=False, providers=[rung])
    raw = res.get("text") or ""
    try:
        res["json"] = llm.parse_json(raw)
        res["parse_error"] = None
    except Exception as e:                                      # noqa: BLE001
        res["json"] = None
        res["parse_error"] = f"{type(e).__name__}: {e}"
    return res


def _response_envelope(res: dict, prompt: str, system: str,
                       plant_info: dict | None) -> dict:
    """The full call envelope every saved response file carries (additive:
    keeps the original `raw`/`json`/`parse_error` keys), so a saved response
    can be re-examined without the run that produced it."""
    return {
        "raw": res.get("text"),
        "json": res.get("json"),
        "parse_error": res.get("parse_error"),
        "system_prompt": system,
        "prompt": prompt,
        "model": res.get("model"),
        "provider": res.get("provider"),
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "truncated": res.get("truncated"),
        "plant": plant_info,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slugs", default="anthill-ventures,selco-foundation,"
                                       "bku-ekta-ugrahan,jyoti-pande-lavakare,"
                                       "bhavreen-kandhari")
    ap.add_argument("--sources", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--rungs", default="openrouter,claude")
    ap.add_argument("--call-radius", type=int, default=1)
    ap.add_argument("--radii", default="1,0",
                    help="radii to BUILD and measure token cost for; only "
                         "--call-radius is actually called")
    ap.add_argument("--retry-parse-failures", action="store_true", default=True)
    ap.add_argument("--pinned", action="store_true", default=False,
                    help="skip HTTP entirely; load each actor's sources from "
                         "engine/poc/fixtures/<slug>.json instead of fetching "
                         "live (default: live fetch)")
    ap.add_argument("--capture-fixtures", action="store_true", default=False,
                    help="after the normal live fetch, write each actor's "
                         "fetched source texts to engine/poc/fixtures/<slug>.json")
    ap.add_argument("--no-calls", action="store_true", default=False,
                    help="build prompts (fetch/chunk/select/plant) but make "
                         "no LLM calls and write no response files")
    args = ap.parse_args()
    if args.pinned and args.capture_fixtures:
        ap.error("--pinned and --capture-fixtures are mutually exclusive "
                 "(pinned loads a fixture; capture writes one from a live fetch)")

    OUT_RESPONSES.mkdir(parents=True, exist_ok=True)
    handle = (POC / "poc2_run.log").open("w", encoding="utf-8")

    def log(*parts):
        line = " ".join(str(p) for p in parts)
        print(line)
        handle.write(line + "\n")
        handle.flush()

    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
    radii = [int(r) for r in args.radii.split(",") if r.strip()]
    rungs = [r.strip() for r in args.rungs.split(",") if r.strip()]

    log("PoC-2 — batched extraction")
    log(f"  actors={slugs}")
    log(f"  calls: {args.repeats} repeats x {len(rungs)} rungs x "
        f"{len(slugs)} actors at radius {args.call_radius} "
        f"= {args.repeats * len(rungs) * len(slugs)} calls")
    log("  the radius comparison is BUILD-TIME only — prompt size is "
        "deterministic and needs no call")

    log("\n[1-2] fetch, select, plant, build — per actor")
    actors = []
    for slug in slugs:
        # No `if built:` guard — build_for_actor raises UnusableActor now, so
        # an actor that cannot support the test stops the run instead of
        # quietly shrinking the matrix.
        actors.append(build_for_actor(
            slug, actor_name(slug), args.sources, radii, log,
            pinned=args.pinned, capture_fixtures=args.capture_fixtures))
    if not actors:
        log("FATAL: no actor produced a usable prompt")
        return 1

    system = system_prompt("actor")
    rows = []
    if args.no_calls:
        log("\n[3] calls — skipped (--no-calls); no LLM calls made")
    else:
        log(f"\n[3] calls — radius {args.call_radius} only")
    for actor in ([] if args.no_calls else actors):
        spec = actor["built"].get(args.call_radius)
        if spec is None:
            continue
        valid = set(spec["labels"].values())
        for rung in rungs:
            for i in range(args.repeats):
                tag = f"{actor['slug']}__{rung}__{i}"
                try:
                    res = one_call(spec["prompt"], system, rung)
                except Exception as e:                          # noqa: BLE001
                    log(f"  {tag}: TRANSPORT FAILED {type(e).__name__}: "
                        f"{str(e)[:140]} prompt_chars={len(spec['prompt'])}")
                    rows.append({"slug": actor["slug"], "rung": rung, "i": i,
                                 "parsed": False, "call_failed": True,
                                 "prompt_chars": len(spec["prompt"]),
                                 "system_chars": len(system),
                                 "passage_tokens": spec["passage_tokens"],
                                 "n_sources_in_prompt": spec["n_sources_in_prompt"]})
                    continue
                (OUT_RESPONSES / f"{tag}.json").write_text(
                    json.dumps(_response_envelope(res, spec["prompt"], system,
                                                  spec["plant"]),
                               ensure_ascii=False, indent=1))
                scored = score_response(res, valid, spec["plant"],
                                        spec["labels"].get(PLANTED_ID))
                scored.update(slug=actor["slug"], rung=rung, i=i,
                              call_failed=False,
                              parse_error=res.get("parse_error"),
                              retry_rescued=None,
                              prompt_chars=len(spec["prompt"]),
                              system_chars=len(system),
                              passage_tokens=spec["passage_tokens"],
                              n_sources_in_prompt=spec["n_sources_in_prompt"])

                # §13's actual question: does ONE retry rescue a malformed
                # response? Only fires on a failure, so it costs nothing when
                # the rung is well behaved.
                if not scored["parsed"] and args.retry_parse_failures:
                    try:
                        again = one_call(spec["prompt"], system, rung)
                        scored["retry_rescued"] = again.get("json") is not None
                        (OUT_RESPONSES / f"{tag}__retry.json").write_text(
                            json.dumps(_response_envelope(again, spec["prompt"],
                                                          system, spec["plant"]),
                                       ensure_ascii=False, indent=1))
                    except Exception as e:                      # noqa: BLE001
                        scored["retry_rescued"] = False
                        scored["retry_error"] = f"{type(e).__name__}: {e}"

                rows.append(scored)
                log(f"  {tag}: parsed={scored['parsed']} "
                    f"answers={scored.get('answers')} "
                    f"valid_id={scored.get('with_valid_id')} "
                    f"unknown={scored.get('with_unknown_id')} "
                    f"no_id={scored.get('no_id')} "
                    f"srcs={scored.get('distinct_sources')}/{len(valid)} "
                    f"planted_cited={scored.get('cited_planted')} "
                    f"both_figs={scored.get('both_figures')} "
                    f"marker={scored.get('marker')} "
                    f"retry_rescued={scored.get('retry_rescued')} "
                    f"in={scored.get('input_tokens')} "
                    f"prompt_chars={scored.get('prompt_chars')} "
                    f"model={str(scored.get('model'))[:30]}")
                if scored.get("parse_error"):
                    log(f"      parse_error: {str(scored['parse_error'])[:120]}")

    log("\n[4] summary — per rung, pooled across actors")
    for rung in rungs:
        sub = [r for r in rows if r.get("rung") == rung]
        ok = [r for r in sub if not r.get("call_failed")]
        parsed = [r for r in ok if r.get("parsed")]
        tot_ans = sum(r.get("answers", 0) for r in parsed)
        tot_valid = sum(r.get("with_valid_id", 0) for r in parsed)
        rescued = [r for r in ok if r.get("retry_rescued") is True]
        if not sub:
            continue
        log(f"  {rung}: calls {len(sub)} (transport-failed "
            f"{len(sub) - len(ok)}) | single-shot parse {len(parsed)}/{len(ok)}"
            f" | one retry rescued {len(rescued)}/{len(ok) - len(parsed)}"
            f" | answers {tot_ans}"
            f" | valid source_id {tot_valid}/{tot_ans}"
            f" ({(tot_valid / tot_ans * 100) if tot_ans else 0:.0f}%)"
            f" unknown {sum(r.get('with_unknown_id', 0) for r in parsed)}"
            f" none {sum(r.get('no_id', 0) for r in parsed)}"
            f" | both figures {sum(1 for r in parsed if r.get('both_figures'))}"
            f"/{len(parsed)}"
            f" | planted cited {sum(1 for r in parsed if r.get('cited_planted'))}"
            f"/{len(parsed)}")

    log("\n[5] per actor — source coverage and neighbour-expansion cost "
        "(no calls involved)")
    for actor in actors:
        for radius, spec in sorted(actor["built"].items()):
            log(f"  {actor['slug']:24} radius={radius}: "
                f"{spec['n_chunks']:3} chunks, "
                f"{spec['passage_tokens']:6} passage tokens, "
                f"{spec['chars']:6} chars, sources in prompt "
                f"{spec['n_sources_in_prompt']}/{spec['n_sources_fetched']}")

    (POC / "poc2_summary.json").write_text(json.dumps(
        {"rows": rows,
         "actors": [{"slug": a["slug"], "name": a["name"],
                     "built": {str(k): {kk: vv for kk, vv in v.items()
                                        if kk != "prompt"}
                               for k, v in a["built"].items()}}
                    for a in actors]},
        ensure_ascii=False, indent=1))
    handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
