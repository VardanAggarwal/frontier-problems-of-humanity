"""Track D (`04-worker-build-plan.md` §5, "Two holes found by the user", #1)
— the source-confirmation POLICY layer, as a pure function.

The hole: `worker/gate2.py`'s `confirm()` is invoked today only on the seed
URL (`worker/worker.py:495-521`, inside `if cand["url"]`). Track D produces
1-5 search-sourced URLs per candidate and none of them get a gate-2 pass.
PoC-2 fed the real recorded URL pool for one actor and found top-scoring
results including a currency converter, a mountain-bike site, Filipino
dessert recipe blogs, a Gujarat scholarship portal, support.google.com/mail
and a Japanese Wikipedia article about a large number — several of which
fetch `ok` with over a thousand words and would become `[Sn]` blocks in the
extraction prompt unfiltered.

The split (04-worker-build-plan.md §5): D ships this policy as a testable,
pure function; track E wires it against `gate2.confirm(conn, ...)`, which is
not pure (it takes a DB connection and calls the embedding model). Nothing in
this module opens a connection, fetches a URL, or calls a model — it consumes
already-computed verdicts and decides what happens to the source set.

Verdict vocabulary is `gate2.py`'s own, reused verbatim, not reinvented:
`"confirmed"`, `"uncertain"`, `"mismatch"` — plus a fourth case this module
must represent that gate2.confirm() never returns because worker.py never
calls it: no verdict at all, when there was no fetched text to confirm
against (a blocked fetch, an empty page, or — for the seed URL — no URL on
the candidate at all). `worker.py`'s own comment at the `if text:` guard
already treats that path as "skip confirmation, proceed anyway"; this module
treats it as a drop instead, because doing so is what closes the hole:
today an untextable page proceeds into extraction dark. See `NO_VERDICT`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

# Reused from worker/gate2.py verbatim — not reinvented here.
CONFIRMED = "confirmed"
UNCERTAIN = "uncertain"
MISMATCH = "mismatch"
# Not a gate2.py verdict: this module's own name for "gate2 was never able to
# run" (no fetched text). Kept visually distinct from the three above so a
# reader of a decision's `reason` can tell "gate2 said no" from "gate2 never
# got to speak."
NO_VERDICT = "no_verdict"

VERDICTS = (CONFIRMED, UNCERTAIN, MISMATCH, NO_VERDICT)

# The two classes of source this policy must be able to express (the hole is
# that today only SEED gets a confirmation pass at all).
SEED = "seed"
SEARCH = "search"
ORIGINS = (SEED, SEARCH)

# --- Unmeasured threshold, named and parked exactly as gate2.py:29-36 parks
# MISMATCH_BELOW/CONFIRMED_ABOVE: no sweep has been run correlating fetched
# text length with gate-2 confirmation reliability. A very short "confirmed"
# page (a redirect stub, a cookie-notice interstitial that happens to mention
# the candidate's name once) is plausibly less trustworthy than a long one,
# but nobody has measured where that stops mattering. Rather than invent a
# number, this module takes it as an optional caller-supplied parameter
# (`thin_page_chars`) and does nothing with text length when the caller
# leaves it unset (`None`, the default). When real-run data exists to set
# it, only the parameter's default should change, not the three-way shape
# below it (mirroring gate2.py's own instruction not to re-derive the shape
# when the numbers are calibrated).
THIN_PAGE_CHARS: Optional[int] = None


@dataclass(frozen=True)
class SourceVerdict:
    """One source's already-computed gate-2 evidence, as input to this
    policy. Everything on this record is produced upstream (fetch + the
    DB-touching `gate2.confirm()` call, both track E's job) — nothing here
    is computed by this module.

    `origin` is SEED or SEARCH — the class of URL this policy must treat
    distinctly per the hole this module fixes.

    `verdict` is one of CONFIRMED/UNCERTAIN/MISMATCH, or None when gate2 was
    never run against this source (no fetched text — a blocked or empty
    fetch, or a candidate with no URL at all).

    `text_chars` is the length of the cleaned fetched text gate2 saw, or
    None when there was none. Only consulted when the caller supplies
    `thin_page_chars` to `apply_confirmations`.
    """
    source_id: str
    url: str
    origin: str
    verdict: Optional[str]
    cosine: Optional[float] = None
    note: str = ""
    text_chars: Optional[int] = None

    def __post_init__(self):
        if self.origin not in ORIGINS:
            raise ValueError(f"unknown origin {self.origin!r}, expected one of {ORIGINS}")
        if self.verdict is not None and self.verdict not in (CONFIRMED, UNCERTAIN, MISMATCH):
            raise ValueError(
                f"unknown verdict {self.verdict!r}, expected one of "
                f"{(CONFIRMED, UNCERTAIN, MISMATCH)} or None")


@dataclass(frozen=True)
class ConfirmationDecision:
    """What the policy did with one source, and why. Every source passed in
    gets exactly one decision back — a source is never silently dropped from
    the returned list, because a silent drop before the extraction call is
    exactly the failure PoC-2 found (3/4 sources vanishing before the call,
    for three of five actors, with no record of why)."""
    source_id: str
    url: str
    origin: str
    kept: bool
    verdict: Optional[str]
    reason: str


def requires_confirmation(origin: str) -> bool:
    """Which sources need a gate-2 confirmation pass before they can enter
    the extraction prompt's source set.

    Today's behaviour (`worker/worker.py:495-521`) confirms only the seed
    URL and lets every search-sourced URL through unconfirmed — that is the
    hole this whole module exists to close. The policy is deliberately flat:
    every source, seed or search, requires confirmation. There is no origin
    for which skipping confirmation is correct; a search-sourced URL is, if
    anything, *less* trustworthy than a seed URL (the seed came from a human
    or an upstream registry; a search hit came from a ranked-retrieval
    system that PoC-2 showed returns off-topic pages that fetch cleanly).
    """
    if origin not in ORIGINS:
        raise ValueError(f"unknown origin {origin!r}, expected one of {ORIGINS}")
    return True


def apply_confirmations(
        verdicts: Sequence[SourceVerdict],
        *,
        thin_page_chars: Optional[int] = THIN_PAGE_CHARS,
) -> list[ConfirmationDecision]:
    """Decide, for a set of sources with already-computed gate-2 evidence,
    which stay in the extraction prompt's source set and which are dropped
    — and record why for every one, kept or dropped.

    What each verdict does to the source set, matching gate2.py's own
    handling at the seed URL (`worker/worker.py:508-516`) so this policy
    generalises today's single-URL behaviour rather than replacing it:

      - CONFIRMED  -> kept.
      - MISMATCH   -> dropped (mirrors worker.py's existing
                      `_settle(..., admitted=0, ...)` on mismatch).
      - UNCERTAIN  -> kept, but flagged. gate2.py's own docstring is explicit
                      that uncertain must be "kept going, but flag for
                      review... not resolved by guessing" — never a silent
                      pass and never a silent fail. This policy keeps the
                      source and carries the flag in the decision's reason
                      rather than the source's raw text; nothing renders
                      only a boolean.
      - NO_VERDICT -> dropped. This is the one place this policy diverges
                      from today's code, which lets a no-URL/no-text
                      candidate through to extraction with `text = ""`
                      (worker.py:496-499). An extraction prompt source with
                      no confirmable text is exactly the kind of block PoC-2
                      flagged as silently entering the prompt; dropping it
                      here is a decision, not an oversight, and the reason
                      says so.

    `thin_page_chars` is optional and, unset, does nothing (see
    THIN_PAGE_CHARS above — no measured threshold exists). When supplied, a
    source whose `text_chars` is below it is never treated as CONFIRMED
    outright: it is downgraded to kept-but-flagged (the same treatment as
    UNCERTAIN), on the reasoning that a short confirmed match is exactly the
    "redirect stub happens to mention the name once" case gate2's authors
    were guarding against with the uncertain band in the first place. It
    never upgrades a MISMATCH or a NO_VERDICT.
    """
    decisions = []
    for v in verdicts:
        if v.verdict == MISMATCH:
            decisions.append(ConfirmationDecision(
                source_id=v.source_id, url=v.url, origin=v.origin,
                kept=False, verdict=v.verdict,
                reason=(
                    (f"gate2 mismatch (cosine={v.cosine:.3f}): " if v.cosine is not None
                     else "gate2 mismatch: ")
                    + "fetched page does not match the candidate's identity — dropped from source set"
                ),
            ))
            continue

        if v.verdict is None:
            decisions.append(ConfirmationDecision(
                source_id=v.source_id, url=v.url, origin=v.origin,
                kept=False, verdict=None,
                reason=(
                    "no gate2 verdict: no fetched text was available to confirm "
                    "identity against (blocked fetch, empty page, or no URL) — "
                    "dropped rather than entering the extraction prompt unconfirmed"
                ),
            ))
            continue

        if v.verdict == CONFIRMED:
            if (thin_page_chars is not None and v.text_chars is not None
                    and v.text_chars < thin_page_chars):
                decisions.append(ConfirmationDecision(
                    source_id=v.source_id, url=v.url, origin=v.origin,
                    kept=True, verdict=v.verdict,
                    reason=(
                        f"gate2 confirmed (cosine={v.cosine:.3f}) but text_chars="
                        f"{v.text_chars} is below thin_page_chars={thin_page_chars} — "
                        "kept but downgraded to flagged, not treated as a clean confirm"
                    ),
                ))
                continue
            decisions.append(ConfirmationDecision(
                source_id=v.source_id, url=v.url, origin=v.origin,
                kept=True, verdict=v.verdict,
                reason=f"gate2 confirmed (cosine={v.cosine:.3f})",
            ))
            continue

        # UNCERTAIN
        decisions.append(ConfirmationDecision(
            source_id=v.source_id, url=v.url, origin=v.origin,
            kept=True, verdict=v.verdict,
            reason=(
                f"gate2 uncertain ({v.note}); kept and flagged for review, "
                "not silently resolved either way"
            ),
        ))

    return decisions
