"""Boilerplate stripping — tier 0, pure, no model.

Two jobs, both load-bearing: token cost, and dedup correctness — SimHash
on uncleaned text misses real duplicates outright, because a short page's
boilerplate is a large share of its features. Figures for both:
EVIDENCE.md §clean-reduction.

trafilatura does this properly when installed; the stdlib fallback keeps
the pipeline runnable and testable without it, at lower quality.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re

from text import simhash

try:
    import trafilatura  # type: ignore
    _HAS_TRAFILATURA = True
except ImportError:  # pragma: no cover - depends on install
    _HAS_TRAFILATURA = False

# Containers whose text is chrome, never content.
_DROP = {"script", "style", "nav", "header", "footer", "aside", "noscript",
         "form", "button", "svg", "iframe", "template", "figcaption"}
_BLOCK = {"p", "div", "section", "article", "li", "tr", "br", "h1", "h2",
          "h3", "h4", "h5", "h6", "blockquote", "pre", "td"}

_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROP:
            self._skip += 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in _DROP and self._skip:
            self._skip -= 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def _fallback(html: str) -> str:
    p = _Stripper()
    try:
        p.feed(html)
        p.close()
    except Exception:
        return ""
    return "".join(p.out)


def tidy(text: str) -> str:
    """Collapse whitespace without destroying paragraph structure."""
    text = _WS.sub(" ", (text or "").replace("\xa0", " "))
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _NL.sub("\n\n", text).strip()


# Word-count floor for a block to be dedup-eligible. Below this, a repeated
# phrase is far more likely to be legitimate short boilerplate (a nav
# breadcrumb, a "read more" link, a section label) than injected feed
# content, and simhash's own reliability floor (MIN_SHINGLES, ~200 words)
# doesn't even apply at this length — dropping a matching 4-word phrase on
# every page would be a real regression for no real gain. 15 words is well
# below any real paragraph but above the boilerplate fragments _fallback's
# _DROP tags don't already catch.
_DEDUP_WORD_FLOOR = 15


def dedupe_repeated_blocks(text: str) -> str:
    """Drop a paragraph-like block that repeats an earlier block verbatim
    or near-verbatim, keeping only the first occurrence.

    Built for the anaemia-mukt-bharat/WeTheChange case, 2026-09-19: a
    LinkedIn permalink scrape (`problems/private/sources/6e9044bbc11b6537.txt`)
    captured the on-topic Anaemia Mukt Bharat post plus an unrelated
    WeTheChange "we're hiring" job ad, near-verbatim, TWICE, at two
    different points in the same file — almost certainly feed/sidebar
    bleed ("people also viewed") rather than real content, since a single
    post's own text does not normally repeat itself. That block, run
    through extraction, hijacked the whole actor profile onto the wrong
    org. Real article/post content in a single-post scrape doesn't
    duplicate a large block verbatim; a duplicated block is a cheap,
    generic tell for injected feed/sidebar/recommended-content noise on
    any feed-style page (LinkedIn, but also a news site's "related
    articles" box), not a LinkedIn-specific fix.

    Blocks are `tidy()`'s own paragraph unit (blank-line separated).
    Matching is on `simhash.normalize()`'d text — folds case, unicode and
    punctuation, so the two WeTheChange copies (which differ only by a
    trailing period before "Lead") match on exact string equality without
    needing a distance threshold. For blocks long enough that
    `simhash.is_reliable()` says a Hamming-distance comparison means
    something (this repo's own MIN_SHINGLES floor, ~200 words — see
    simhash.py), a true near-duplicate (reworded, not just
    punctuation-perturbed) is caught too via `simhash.is_duplicate()`.
    Below that floor, only the exact-after-normalization match applies —
    a short block is never long enough for a Hamming-distance comparison
    to mean anything by this module's own contract.
    """
    if not text:
        return text
    blocks = text.split("\n\n")
    seen_norm: set[str] = set()
    seen_hashes: list[int] = []
    out: list[str] = []
    for block in blocks:
        if len(block.split()) < _DEDUP_WORD_FLOOR:
            out.append(block)
            continue
        norm = simhash.normalize(block)
        is_dup = norm in seen_norm
        if not is_dup and simhash.is_reliable(block):
            h = simhash.simhash(block)
            is_dup = any(simhash.is_duplicate(h, prior) for prior in seen_hashes)
            if not is_dup:
                seen_hashes.append(h)
        if is_dup:
            continue
        seen_norm.add(norm)
        out.append(block)
    return "\n\n".join(out)


def clean(html: str, *, url: str | None = None) -> str:
    """Raw HTML (or text) in, readable text out.

    Returns "" when there is nothing extractable — callers should treat
    that as a failed fetch, not as an empty document.
    """
    if not html or not html.strip():
        return ""
    if "<" not in html:            # already text
        return dedupe_repeated_blocks(tidy(html))
    if _HAS_TRAFILATURA:
        got = trafilatura.extract(
            html, url=url, include_comments=False, include_tables=True,
            no_fallback=False, favor_recall=True,
        )
        if got and got.strip():
            return dedupe_repeated_blocks(tidy(got))
        # trafilatura returns None on pages it judges contentless — often
        # true, sometimes a listing page we still want. Fall through.
    return dedupe_repeated_blocks(tidy(_fallback(html)))


def reduction(html: str, text: str) -> float:
    """Fraction of characters removed. Sanity-check the strip, and a
    cheap alarm when a site's markup defeats it."""
    if not html:
        return 0.0
    return 1.0 - (len(text) / len(html))
