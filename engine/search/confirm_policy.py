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

# --- Where a source goes, decided 2026-09-14 -------------------------------
# `kept: bool` was too coarse. It had only two states, so `uncertain` — which
# gate2 requires be "kept going, but flagged for review, never a silent pass
# and never a silent fail" — could only be expressed as kept, and kept meant
# "enters the extraction prompt". Putting an unconfirmed page into the prompt
# IS silently resolving it as a pass, which is the thing that rule forbids.
#
# `poc/gate2-band-sweep.md` measured what that cost: the uncertain band holds
# roughly 60 of ~200 pooled URLs and is essentially all junk — eight currency
# converters, nine recipe blogs, seven "how to get help in Windows", six
# `360.cn` portal pages, trophy shops, `jiosaavn.com`. All of it was reaching
# the extraction prompt.
#
# Three routes instead of two. Nothing is discarded for being unconfirmable:
# VERIFY is a real destination with its own pass, not a bin.
PROMPT = "prompt"    # clean confirm -> straight into the extraction prompt
VERIFY = "verify"    # unconfirmed or thin -> the verify-and-extract pass
DROP = "drop"        # positively rejected, or nothing to confirm against
ROUTES = (PROMPT, VERIFY, DROP)

# The two classes of source this policy must be able to express (the hole is
# that today only SEED gets a confirmation pass at all).
SEED = "seed"
SEARCH = "search"
ORIGINS = (SEED, SEARCH)

# --- Measured 2026-09-14; was parked unset. The reasoning it was parked on
# stands and is kept: a very short "confirmed" page (a redirect stub, a cookie
# notice that happens to mention the candidate's name once) is less
# trustworthy than a long one, and nobody had measured where that stops
# mattering. Now somebody has. It remains a caller-supplied parameter, so a
# caller can still pass `thin_page_chars=None` to switch the rule off.
THIN_PAGE_CHARS: Optional[int] = 700
# Set 2026-09-14 from `poc/gate2-band-sweep.md`. Every false positive left
# above CONFIRMED_ABOVE in that sweep was a thin page: `vnrvjietexams.net` 86w
# (~600 chars, cosine 0.818 against a Punjabi farmers' union),
# `music.youtube.com` 24w (~170 chars, 0.815 against SELCO Foundation), and
# `support.google.com/mail` against a VC firm. 700 chars clears all three.
#
# What it costs, stated rather than discovered later: genuine author-index
# stubs sit in the same range (`thequint.com/author/...` 51w,
# `science.thewire.in/author/...` 66w, a `timesofindia` topic page 80w). Those
# are downgraded too. That is judged acceptable because an index stub carries
# almost no extractable claim — but it IS a real recall cost, and it is the
# reason this stays a downgrade to VERIFY rather than a DROP: a thin page now
# routes to the verify-and-extract pass instead of being discarded.


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
    for three of five actors, with no record of why).

    `kept` answers "did this survive the policy at all". `route` answers
    "where does it go", and it is the field callers must branch on: a source
    that is `kept` but routed to VERIFY must NOT be placed in the main
    extraction prompt."""
    source_id: str
    url: str
    origin: str
    kept: bool
    verdict: Optional[str]
    reason: str
    route: str = PROMPT

    def __post_init__(self):
        if self.route not in ROUTES:
            raise ValueError(f"unknown route {self.route!r}, expected one of {ROUTES}")
        if self.kept != (self.route != DROP):
            raise ValueError(
                f"kept={self.kept} contradicts route={self.route!r}; `kept` means "
                f"'survived the policy', i.e. route is not DROP")


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

      - CONFIRMED  -> kept, route=PROMPT.
      - MISMATCH   -> route=DROP (mirrors worker.py's existing
                      `_settle(..., admitted=0, ...)` on mismatch).
      - UNCERTAIN  -> kept, route=VERIFY. gate2.py's own docstring is
                      explicit that uncertain must be "kept going, but flag
                      for review... not resolved by guessing" — never a
                      silent pass and never a silent fail. Until 2026-09-14
                      this module honoured that with `kept=True`, which put
                      the source straight into the extraction prompt — and
                      putting an unconfirmed page in the prompt IS resolving
                      it as a pass. It now routes to VERIFY: a real second
                      pass whose prompt re-checks identity per source before
                      it will extract from it (`prompts.verify_and_extract_
                      prompt_batched`). Flagged, and acted on.
      - NO_VERDICT -> route=DROP. This is the one place this policy diverges
                      from today's code, which lets a no-URL/no-text
                      candidate through to extraction with `text = ""`
                      (worker.py:496-499). An extraction prompt source with
                      no confirmable text is exactly the kind of block PoC-2
                      flagged as silently entering the prompt; dropping it
                      here is a decision, not an oversight, and the reason
                      says so.

    `thin_page_chars` defaults to THIN_PAGE_CHARS (measured; pass None to
    switch the rule off). A CONFIRMED source whose `text_chars` is below it is
    never treated as a clean confirm: it is downgraded to route=VERIFY, the
    same destination as UNCERTAIN, on the reasoning that a short confirmed
    match is exactly the "redirect stub happens to mention the name once" case
    gate2's authors were guarding against with the uncertain band in the first
    place. It never upgrades a MISMATCH or a NO_VERDICT.
    """
    decisions = []
    for v in verdicts:
        if v.verdict == MISMATCH:
            decisions.append(ConfirmationDecision(
                source_id=v.source_id, url=v.url, origin=v.origin,
                kept=False, verdict=v.verdict, route=DROP,
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
                kept=False, verdict=None, route=DROP,
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
                    kept=True, verdict=v.verdict, route=VERIFY,
                    reason=(
                        f"gate2 confirmed (cosine={v.cosine:.3f}) but text_chars="
                        f"{v.text_chars} is below thin_page_chars={thin_page_chars} — "
                        "routed to the verify-and-extract pass, not treated as a "
                        "clean confirm"
                    ),
                ))
                continue
            decisions.append(ConfirmationDecision(
                source_id=v.source_id, url=v.url, origin=v.origin,
                kept=True, verdict=v.verdict, route=PROMPT,
                reason=f"gate2 confirmed (cosine={v.cosine:.3f})",
            ))
            continue

        # UNCERTAIN
        decisions.append(ConfirmationDecision(
            source_id=v.source_id, url=v.url, origin=v.origin,
            kept=True, verdict=v.verdict, route=VERIFY,
            reason=(
                f"gate2 uncertain ({v.note}); routed to the verify-and-extract "
                "pass rather than into the main prompt — flagged and acted on, "
                "not silently resolved either way"
            ),
        ))

    return decisions


# --- Is the confirmed set enough on its own? ------------------------------
# Two thresholds, and unlike THIN_PAGE_CHARS and gate2's bands these are NOT
# measured — no run has yet produced a distribution of "confirmed sources per
# candidate" or "chars of confirmed text per candidate", because until
# 2026-09-14 the uncertain band was in the prompt and every count was
# inflated by junk. They are therefore set to the weakest values that still
# express the rule, in the manner gate2.py:29-36 requires: MIN_PROMPT_SOURCES
# is 1 (fire the fallback only when the prompt would otherwise have a single
# witness or none — a set of 2 can at least disagree with itself) and
# MIN_PROMPT_CHARS is 2,000 (roughly one substantive page).
#
# §14 owes both real values from a production run. Until then the fallback is
# deliberately reluctant: it costs a second paid call, and a candidate whose
# confirmed set is adequate must never buy one.
MIN_PROMPT_SOURCES = 2
MIN_PROMPT_CHARS = 2000


def prompt_set_is_thin(
        texts: Sequence[str],
        *,
        min_sources: int = MIN_PROMPT_SOURCES,
        min_chars: int = MIN_PROMPT_CHARS,
) -> tuple[bool, str]:
    """Does the confirmed set need the verify pass to back it up?

    -> `(is_thin, reason)`. `reason` is always populated, including when the
    answer is no, so a caller can log why it did *not* spend a second call —
    the decision not to escalate is as much a decision as the decision to.

    Counts only what actually reaches the prompt. A candidate with six
    confirmed sources does not buy a second call; one with a single 400-word
    page does, because that is the case where the uncertain bucket is likely
    to hold the only other witness — and the sweep showed the uncertain bucket
    is not uniformly junk (a real LinkedIn post and a real book page sat in
    it, below four wrong-entity pages).
    """
    n = len(texts)
    chars = sum(len(t or "") for t in texts)
    if n < min_sources:
        return True, (f"confirmed set has {n} source(s), below "
                      f"min_sources={min_sources}")
    if chars < min_chars:
        return True, (f"confirmed set has {chars} chars across {n} sources, "
                      f"below min_chars={min_chars}")
    return False, (f"confirmed set is adequate: {n} sources, {chars} chars "
                   f"(>= {min_sources} / {min_chars}) — no verify pass")
