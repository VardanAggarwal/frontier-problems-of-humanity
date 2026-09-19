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

import re
from typing import Sequence
from urllib.parse import urlsplit

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


def _url_is_own_domain(url: str, name_tokens: Sequence[str]) -> bool:
    """Does `url`'s hostname itself spell the candidate's name (minus
    generic parts)? `jjspices.in` for "JJ Spices", `niehs.nih.gov` for
    "NIEHS" — an own-domain page is trustworthy on its whole self by
    construction, independent of what any single chunk or fetch happens to
    say. A third-party host (linkedin.com, a news site, a directory) never
    matches this.

    2026-09-19d: added for `worker/prompts.py:flag_unmentioned_answers`'s
    `jj-spices` fix (a same-domain chunk is trusted even when it's silent on
    the brand name — see that function's docstring for why source-level
    trust was rejected in favour of this narrower, deterministic check) and
    reused by `worker/search_stage.py:website_and_feed_channels` (the
    confirmed own-domain source becomes the `website` channel, and its root
    is where feed-path candidates get probed from).
    """
    if not url or not name_tokens:
        return False
    host = urlsplit(url).netloc.lower().split(":")[0]
    host = re.sub(r"^www\.", "", host)
    host_norm = re.sub(r"[^a-z0-9]", "", host)
    if not host_norm:
        return False
    # Require the FULL concatenated name (not just any one token) to appear
    # in the hostname — "spices" alone would match half the internet's
    # spice retailers; "jjspices" is distinctive.
    joined = "".join(name_tokens)
    return len(joined) >= 4 and joined in host_norm
