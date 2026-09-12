"""Is this fetched page a document at all?

Blocked pages still produce text, so without this they enter the corpus
as sources. Two things the measured sample proves, and that a status-code
check would miss:

- **HTTP status does not identify a wall.** Half the walls in the sample
  returned 2xx. So a wall phrase must outrank a success status.
- **Blocked is not the same as rejected.** A wall says nothing about the
  candidate — gate 0 had already grouped three unfetchable URLs with the
  PMC copy of the same paper, and the content came from there. Drop the
  *page*, keep the candidate.

Word count alone never condemns a page. It yields `thin`, which means
"real but short, do not treat as full text". Only a wall phrase, a
challenge fingerprint or a refusing status yields `blocked`.

The sample and the wall inventory: EVIDENCE.md §pagestate-walls.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

# Phrases that only appear when something is refusing to serve content.
# Every one of these is drawn from a page in the measured set or is the
# standard wording of a challenge vendor.
_WALL = (
    ("js",       re.compile(r"javascript is (?:disabled|required|not enabled)|"
                            r"enable javascript|requires javascript|"
                            r"please enable js\b", re.I)),
    ("cookies",  re.compile(r"cookies must be enabled|enable cookies|"
                            r"your browser (?:does not|doesn't) (?:support|accept) cookies", re.I)),
    ("bot",      re.compile(r"detected unusual (?:activity|traffic)|unusual traffic from|"
                            r"temporarily restricted|checking your browser|"
                            r"verify (?:you are|that you are) (?:a )?human|"
                            r"are you a robot|confirm you are human|"
                            r"request (?:was )?blocked|rate limit(?:ed|ing)?\b|"
                            r"too many requests|captcha", re.I)),
    ("forbidden", re.compile(r"\b(?:403|401)\b.{0,20}\bforbidden\b|^forbidden$|"
                             r"(?:don't|do not) have permission to access|"
                             r"access (?:is )?(?:denied|restricted|forbidden)|"
                             r"not authori[sz]ed", re.I | re.M)),
    ("login",    re.compile(r"log ?in or sign ?up|sign in to (?:continue|view|read)|"
                            r"subscription required|subscribers only|"
                            r"members only|purchase (?:this )?(?:article|access)|"
                            r"institutional (?:login|access) required", re.I)),
    ("missing",  re.compile(r"page (?:not found|no longer|has moved)|"
                            r"\b404\b.{0,20}not found|"
                            r"the requested (?:url|page) (?:was )?not found", re.I)),
)

# Challenge-vendor markers in the RAW html. Deliberately narrow — a bare
# "cloudflare" appears on countless pages that serve fine.
_FINGERPRINT = re.compile(
    r"\bray id\b|cf-chl|__cf_chl|cf_chl_opt|/cdn-cgi/challenge|"
    r"perimeterx|_pxhd|px-captcha|datadome|incapsula|_incap_|"
    r"g-recaptcha|hcaptcha", re.I)

REFUSING_STATUS = {401, 402, 403, 405, 406, 429, 451}
MISSING_STATUS = {404, 410}

MIN_DOCUMENT_WORDS = 120   # below this, thin — not wrong, just not full text
JS_SHELL_WORDS = 50        # tiny text from a large body, with no wall phrase
JS_SHELL_BYTES = 4000      # sized from Springer 3036B and PressReader ~10KB


@dataclass(frozen=True)
class PageState:
    state: str          # ok | thin | blocked | missing | empty
    kind: str           # "", js, cookies, bot, forbidden, login, missing, shell
    retryable: bool     # is a different fetch strategy worth trying
    usable: bool        # may this text be stored as a source
    words: int
    reason: str

    def __bool__(self) -> bool:      # `if assess(...)` reads as "is it usable"
        return self.usable


def assess(text: str, *, raw: str = "", http_status: int | None = None,
           min_words: int = MIN_DOCUMENT_WORDS) -> PageState:
    """Classify a fetched page. `text` is CLEANED text, `raw` the html.

    Order matters: a wall phrase outranks a success status, because half
    the walls in the measured set returned 2xx.
    """
    words = len((text or "").split())

    if not (text or "").strip():
        return PageState("empty", "", True, False, 0,
                         "no extractable text" if raw else "empty body")

    if http_status in MISSING_STATUS:
        return PageState("missing", "missing", False, False, words,
                         f"http {http_status}")

    # Wall phrases beat status. Only look at the head — a legitimate
    # article may discuss captchas or mention a paywall further down.
    head = text[:1200]
    for kind, pat in _WALL:
        if pat.search(head):
            return PageState(
                "missing" if kind == "missing" else "blocked", kind,
                kind not in ("login", "missing"), False, words,
                f"wall phrase ({kind})"
                + (f", http {http_status}" if http_status else ""))

    if raw and _FINGERPRINT.search(raw[:20000]):
        return PageState("blocked", "bot", True, False, words,
                         "challenge fingerprint in markup")

    if http_status in REFUSING_STATUS:
        return PageState("blocked", "forbidden", True, False, words,
                         f"http {http_status}")

    # A large body that cleans to almost nothing is a client-rendered
    # shell, not a short document.
    if words < JS_SHELL_WORDS and len(raw) > JS_SHELL_BYTES:
        return PageState("blocked", "shell", True, False, words,
                         f"{words} words from {len(raw)}B of markup")

    if words < min_words:
        return PageState("thin", "", False, True, words,
                         f"{words} words — real but not full text")

    return PageState("ok", "", False, True, words, f"{words} words")
