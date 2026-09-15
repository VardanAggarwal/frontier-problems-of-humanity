"""Layer 4 entity resolution (01-minimal.md §8 "Layer 4 — entities", §9).

Order is prescribed, not a choice: normalized alias/id match FIRST, the
embedding shortlist as a fallback ONLY. §8 measured this the other way round
and it lost — cold-encoded lookup against the 228 aliases that differ from
their actor's title gets rank-1 51.8%, top-5 75.4%, and the cosine at rank 1
does not even tell you which you got (0.844 median when right, 0.815 when
wrong). `store.db.resolve`'s exact/alias match is already correct on exactly
these cases, for free. So: try that first; only pay for an encode + kNN when
it misses.

No third LLM prompt exists here on purpose. §9 draws the line: "Per-record
review is arithmetically impossible, so judgment moves" to policy / sample /
escalation, and an ambiguous merge is explicitly an **escalation** case, not
something resolved autonomously by comparing two texts with a model. Building
an "LLM, is this the same entity?" prompt here would quietly re-introduce
per-record human-grade judgment at machine volume with no reviewer in the
loop — the opposite of what §9 argues for. The `event` table (an `event` row
naming the shortlist, `candidate.resolved_to` left NULL) IS the escalation
queue, until build-order step 6 ("Review surface") gives it a real front end.

The cutoff for `shortlist_top` vs `ambiguous` is deliberately ABOVE every
measured "two unrelated entities" band in §8, not a guess at a round number:
actor-pair p99 is 0.897-0.971 and problem-pair p99 is 0.875 — meaning even
the 99th percentile of *unrelated* pairs can score above 0.87. Setting the
safe cutoff at 0.90 accepts that some true matches will fall into
`ambiguous` (a false negative, caught by escalation) rather than risk
auto-merging two unrelated actors sitting in that already-crowded high band
(a false positive, which corrupts the graph). This is unmeasured for the
resolver's specific comparison (candidate name+context vs indexed entity
text) and should be revisited once that comparison has its own calibration
sweep, same caveat as `gate2.py`.

Below 0.90, cosine alone cannot separate "new" from "same, but nothing
alias/id already caught" — that IS the §8 finding. But a shortlist is never
actually empty once the store holds any real number of entities, so treating
"empty shortlist" as the only route to `new` means every genuinely new
entity escalates forever, and the review surface (build step 6, not yet
built) becomes load-bearing for the corpus to grow at all. Fixed 2026-09-13,
found live: a real sweep on a real page named three real actors none of
which are in the store, and all three came back `ambiguous` against
neighbours that share nothing but topic (RESET Air / GBCI-LEED-Arc / GMDA,
top hits 0.83-0.85 against unrelated Delhi air-quality orgs). The rescue:
lexical overlap (`text.preview.content_tokens`/`_is_distinctive`, already
validated in §8 for the identical narrow-band problem on document pairs) —
a candidate name sharing no distinctive token with its top hit's title is
topically close, not the same identity, and gets `new` instead of a
permanent escalation. Only a shortlist hit with SOME lexical overlap stays
`ambiguous`.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from embed import index
from embed.model import EmbedTimeout, encode_one, fit, with_timeout
from store import db
from text.preview import content_tokens, _is_distinctive

# Above every measured unrelated-pair p99 in §8 (actor 0.897-0.971, problem
# 0.875) — see module docstring for why this is a deliberately conservative
# choice, not a round number.
SAFE_MATCH_ABOVE = 0.90

SHORTLIST_K = 5

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_SLUG_EDGE = re.compile(r"^-+|-+$")


@dataclass
class ResolveResult:
    decision: str                              # exact | shortlist_top | ambiguous | new
    entity_id: str | None = None
    shortlist: list[tuple[str, float]] = field(default_factory=list)
    reason: str = ""


def resolve_entity(conn: sqlite3.Connection, corpus: Path, kind: str,
                   name: str, context: str) -> ResolveResult:
    """kind is "problem" or "actor". `context` is whatever surrounding text
    the caller has (candidate evidence, snippet, extracted claims) — used
    only as embedding context, never for the exact-match step."""
    exact = db.resolve(conn, kind, name)
    if exact is not None:
        return ResolveResult("exact", entity_id=exact,
                             reason="normalized alias/id match")

    # `context` — "candidate evidence, snippet, extracted claims" per the
    # docstring above — can be the full fetched/extracted text, unbounded.
    # `fit()` does token-exact truncation, ahead of it a cheap char pre-clip
    # (`_FIT_PRECLIP_CHARS` in embed/model.py), and `with_timeout` bounds the
    # pair by wall-clock — see gate2.py's confirm() for the fuller history:
    # `fit()` alone (replacing `clip()`) still hung this call chain on
    # candidate 71 (2026-09-15T07:54) after already having hung it once on
    # candidate 28 (2026-09-14T22:45), because bounding the *output* size
    # doesn't bound the cost of getting there. On timeout, treat it the same
    # as an unreadable/empty context: don't guess, surface it as needing a
    # human look rather than silently resolving to "new". Closure over the
    # module's own `fit`/`encode_one` (not a fixed helper) so tests can still
    # monkeypatch `resolve.fit`/`resolve.encode_one` directly.
    text = f"{name} {context}".strip() or name
    try:
        vector = with_timeout(lambda: encode_one(fit(text, role="query"), role="query"),
                              label="resolve embed")
    except EmbedTimeout as exc:
        return ResolveResult("ambiguous", shortlist=[],
                             reason=f"embedding timed out, resolution deferred: {exc}")
    shortlist = index.knn(conn, kind, vector, k=SHORTLIST_K)

    if not shortlist:
        return ResolveResult("new", reason="no alias match, empty embedding shortlist")

    top_id, top_cosine = shortlist[0]
    if top_cosine > SAFE_MATCH_ABOVE:
        return ResolveResult("shortlist_top", entity_id=top_id, shortlist=shortlist,
                             reason=f"top shortlist hit {top_cosine:.3f} clears "
                                    f"the {SAFE_MATCH_ABOVE} safe-match band")

    # Below the safe band, cosine alone cannot decide (§8: the whole usable
    # range is ~0.76-0.98 and unrelated actor pairs already sit at a 0.841
    # median — "new" can never come from a non-empty shortlist on cosine
    # alone, and with any real corpus size the shortlist is never empty, so
    # every genuinely new entity would escalate forever). Add the lexical
    # signal §8's dedup layer already validated for exactly this narrow-band
    # problem (Layer 1 preview containment, Layer 3 "false-merge risk, and
    # the cheap fix"): if the candidate name shares no distinctive token with
    # the top hit's title, the semantic closeness is topical, not identity —
    # rescue it as `new` instead of an unresolvable escalation.
    top_title = db.title_of(conn, kind, top_id)
    shared = content_tokens(name) & content_tokens(top_title or "")
    if not _is_distinctive(shared):
        return ResolveResult(
            "new", shortlist=shortlist,
            reason=f"top shortlist hit {top_cosine:.3f} does not clear "
                   f"{SAFE_MATCH_ABOVE}, and shares no distinctive token with "
                   f"{top_id!r} ({top_title!r}) — topical closeness, not identity")

    # Non-empty shortlist, nothing clears the safe band, AND some lexical
    # overlap with the top hit: this is the genuinely hard case (§9) — an
    # escalation, not a merge or a rejection — see module docstring.
    return ResolveResult(
        "ambiguous", shortlist=shortlist,
        reason=f"top shortlist hit {top_cosine:.3f} does not clear "
               f"{SAFE_MATCH_ABOVE}, and shares {shared!r} with {top_id!r} "
               f"({top_title!r}) — routed to human review, per §9")


def _slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    s = _SLUG_STRIP.sub("-", s.lower())
    s = re.sub(r"-{2,}", "-", s)
    return _SLUG_EDGE.sub("", s) or "entity"


def new_id(conn: sqlite3.Connection, kind: str, title: str) -> str:
    """A fresh id for a resolved-as-new entity. Checks both the live table
    and `alias` (a former id can be a slug nothing currently holds, and
    handing it out again would silently reattach history to the wrong
    entity)."""
    if kind not in ("problem", "actor"):
        raise ValueError(f"new_id is for problem/actor, not {kind}")
    base = _slugify(title)

    def taken(candidate: str) -> bool:
        if conn.execute(f"SELECT 1 FROM {kind} WHERE id = ?", (candidate,)).fetchone():
            return True
        return bool(conn.execute(
            "SELECT 1 FROM alias WHERE entity_kind = ? AND alias = ?",
            (kind, candidate)).fetchone())

    if not taken(base):
        return base
    n = 2
    while taken(f"{base}-{n}"):
        n += 1
    return f"{base}-{n}"
