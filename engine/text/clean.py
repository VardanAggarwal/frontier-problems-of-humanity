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


def clean(html: str, *, url: str | None = None) -> str:
    """Raw HTML (or text) in, readable text out.

    Returns "" when there is nothing extractable — callers should treat
    that as a failed fetch, not as an empty document.
    """
    if not html or not html.strip():
        return ""
    if "<" not in html:            # already text
        return tidy(html)
    if _HAS_TRAFILATURA:
        got = trafilatura.extract(
            html, url=url, include_comments=False, include_tables=True,
            no_fallback=False, favor_recall=True,
        )
        if got and got.strip():
            return tidy(got)
        # trafilatura returns None on pages it judges contentless — often
        # true, sometimes a listing page we still want. Fall through.
    return tidy(_fallback(html))


def reduction(html: str, text: str) -> float:
    """Fraction of characters removed. Sanity-check the strip, and a
    cheap alarm when a site's markup defeats it."""
    if not html:
        return 0.0
    return 1.0 - (len(text) / len(html))
