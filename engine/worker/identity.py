"""Candidate-identity check — a cheap, dependency-light signal for "does this
text actually talk about this actor", shared by `search_stage.py` (channel
confirmation) and `passages.py` (passage selection).

Extracted 2026-09-19 out of `worker/search_stage.py`, where it was built to
close the `tara-mani-sah` bug (`x.com/DonaldTrump` written as her channel —
see `_text_mentions_actor`'s docstring below for the full story) and reused
unchanged for the `anaemia-mukt-bharat` bug (`passages.py:select()` — a
WeTheChange job-ad chunk out-scored the ~34 genuinely on-topic sources across
nearly every bucket because it was a near-perfect semantic match for
question-shaped queries, with nothing checking it was actually about the
candidate).

No import of anything heavy — only `store.db` (stdlib `sqlite3`/`hashlib`/
`re`, no ML, no network) and stdlib. This keeps `passages.py`'s documented
"pure function, no network, no DB" contract intact when it imports from here.
"""
from __future__ import annotations

from typing import Sequence

from store import db

# Generic legal-entity / filler words that would otherwise count as a
# "distinctive" name token and match almost anything (`Foundation Trust`
# appears in hundreds of unrelated bios). Stripped before the mention check
# below; org-type suffixes only — a real given/family name never collides
# with this list.
_NAME_TOKEN_STOPWORDS = {
    "pvt", "ltd", "private", "limited", "the", "and", "of", "foundation",
    "trust", "india", "group", "inc", "llp", "co", "company", "society",
    "association", "committee", "welfare",
}


def _name_tokens(name: str) -> list[str]:
    """`name` -> its distinctive tokens for the mention check below: casefolded/
    punctuation-stripped (`store.db.norm`), 3+ chars, legal-suffix words
    dropped. Empty for a name that is nothing but stopwords/short tokens —
    the caller treats that as "can't check" rather than "never matches"."""
    return [t for t in db.norm(name).split()
            if len(t) >= 3 and t not in _NAME_TOKEN_STOPWORDS]


def _text_mentions_actor(text: str, name_tokens: Sequence[str]) -> bool:
    """Does `text` contain at least one of the actor's own distinctive name
    tokens, as a whole word? Word-boundary, not substring — `"sah"` must not
    match inside `"flash"`.

    2026-09-19: `tara-mani-sah`'s `channel:twitter` was written as
    `x.com/DonaldTrump` — gate2 embed-confirmed a thin, templated X.com
    profile shell (161 words, no page-specific content) against the
    candidate's context, and `channels_from_confirmed` trusted that verdict
    on URL pattern alone, never looking at what the page actually said. A
    genuine profile page says the actor's own name somewhere in its first
    ~500-1000 chars (bio, page title, "About"); a mismatched page fetched
    clean off a generic search hit does not. This is a second, independent
    signal on top of gate2's cosine band, not a replacement for it — cheap,
    exact-string, and catches exactly the class of failure a semantic
    embedding is worst at (a templated page with no distinguishing text)."""
    if not name_tokens:
        return True
    words = set(db.norm(text or "").split())
    return any(t in words for t in name_tokens)
