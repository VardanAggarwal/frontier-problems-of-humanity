"""What text stands for an entity.

This is the part of tier 1 that is a judgement rather than a port, so it lives
in its own module where it can be argued with.

Three rules behind the choices below:

1. **Embed what the comparison will actually see.** §8's gate 1/2 screen puts a
   problem's `title + one_line` against a candidate's `title + snippet`. So a
   problem's stored vector is `title + one_line` — not its full prose, which
   would be a vector of a different thing than the one it gets compared to.
2. **Truncate at the front, and mean nothing by it.** e5-small reads 512
   tokens. For the dedup case that matters — the same paper rendered at 3,193
   words by PMC and 2,088 by Ovid (§8 finding 2) — the shared part *is* the
   front: title, abstract, opening. Truncation is not a compromise here, it is
   the signal.
3. **Prose lives on disk (§3), so this module reads files.** An actor row has
   no one-liner column; its description is the lead paragraph of its markdown.
   Embedding the title alone would make 289 actors a bag of proper nouns.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MAX_CHARS = 2000          # ~512 e5 tokens of English, fewer of Devanagari

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
_H1 = re.compile(r"^#\s+.*$", re.M)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BOLD_LEAD = re.compile(r"^\*\*(.+?)\.?\*\*\s*", re.S)


def clip(text: str, limit: int = MAX_CHARS) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip()


def lead_paragraph(path: Path) -> str:
    """The first real paragraph of a corpus markdown file — frontmatter, H1,
    HTML comments and blockquote markers removed. `**What they do.**` keeps its
    words and loses its asterisks: the sentence is content, the emphasis isn't.
    """
    if not path.exists():
        return ""
    body = _FRONTMATTER.sub("", path.read_text(), count=1)
    body = _HTML_COMMENT.sub("", body)
    body = _H1.sub("", body)
    for block in body.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(("#", "<!--", "|", "```")):
            continue
        block = re.sub(r"^>\s?", "", block, flags=re.M).strip()
        if not block:
            continue
        return _BOLD_LEAD.sub(r"\1. ", block).strip()
    return ""


def _doc_path(corpus: Path, doc: str | None) -> Path | None:
    return None if not doc else (corpus / doc if not Path(doc).is_absolute()
                                 else Path(doc))


def problem_text(row: sqlite3.Row) -> str:
    """title + one_line — the same shape the candidate side presents (§8).

    Returns "" for a row with no words in it, rather than the bare "." that
    joining an empty list produces — which backfill would have happily embedded
    as a record."""
    parts = [p.strip().rstrip(".") for p in (row["title"], row["one_line"]) if p]
    parts = [p for p in parts if p.strip()]
    return clip(". ".join(parts) + ".") if parts else ""


def actor_text(row: sqlite3.Row, corpus: Path) -> str:
    """title + the what-they-do lead. Falls back to the title when there is no
    doc, which is what a stub actor legitimately is."""
    parts = [row["title"] or ""]
    path = _doc_path(corpus, row["doc"])
    if path is not None:
        lead = lead_paragraph(path)
        if lead:
            parts.append(lead)
    return clip(" — ".join(p.strip() for p in parts if p and p.strip()))


def source_text(row: sqlite3.Row, corpus: Path) -> str:
    """Cached cleaned text where the page was fetched; title + org + year where
    it is still a bare citation. Both are legitimate — the second is the
    preview signal of §8 finding 1, in vector form."""
    path = _doc_path(corpus, row["path"])
    if path is not None and path.exists():
        return clip(path.read_text())
    parts = [row["title"] or "", row["org"] or ""]
    if row["year"]:
        parts.append(str(row["year"]))
    return clip(" — ".join(p for p in parts if p))


def for_entity(kind: str, row: sqlite3.Row, corpus: Path) -> str:
    if kind == "problem":
        return problem_text(row)
    if kind == "actor":
        return actor_text(row, corpus)
    if kind == "source":
        return source_text(row, corpus)
    raise ValueError(f"no text rule for kind {kind!r}")
