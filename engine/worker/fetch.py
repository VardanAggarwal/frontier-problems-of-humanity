"""The worker's fetch step (01-minimal.md §5 "fetch": canonicalize URL -> check
corpus -> strip boilerplate -> classify).

Canonicalize first so a URL already fetched (by any candidate, ever) short-
circuits to the cached row — `source.url_canonical` is unique, so this is one
indexed lookup, not a network call. That is what makes the worker cheap on a
corpus that gets re-swept: gate 0 and gate 1 already collapsed duplicate
*candidates* before this point, but two different candidates can still name
the same underlying URL, and this is the layer that catches it (§8 Layer 2).

No retries here — 01-minimal.md §12 marks retry policy explicit future work
("Retry is declared but not implemented"). `PageState.retryable` is computed
and stored so a future retry pass has what it needs, but nothing acts on it
yet. A network failure (timeout, DNS, connection reset) is not the same kind
of fact as a wall or a 404, so it gets its own `FetchResult.error` rather than
being coerced into one of pagestate's wall kinds — but it still degrades
gracefully to "no usable text" for the caller, exactly like a blocked page,
because gate 1/2/claims downstream only need to know "is there text or not."
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import requests

from text.canonical import canonicalize, url_hash
from text.clean import clean
from text.pagestate import PageState, assess
from text.simhash import is_reliable, simhash as compute_simhash

TIMEOUT_S = 5
USER_AGENT = (
    "Mozilla/5.0 (compatible; fph-engine/0.1; "
    "+https://github.com/VardanAggarwal/frontier-problems-of-humanity)"
)

# Where cached cleaned text lives. `corpus` (this module's argument, and
# `embed/guard.py`'s `--corpus`) is the REPO ROOT — the root `doc`/`path`
# columns are relative to, not `problems/` itself (guard.py: "`corpus` ... is
# NOT the root the `doc` columns are relative to"). `problems/private/` is
# already gitignored, and cached fetched text is exactly the kind of
# derived, non-authored artifact that belongs there, not in git.
CACHE_SUBDIR = Path("problems") / "private" / "sources"


@dataclass
class FetchResult:
    text: str | None          # cleaned text, or None when nothing usable
    state: PageState
    source_id: str
    cache_hit: bool


def _network_failure_state(reason: str) -> PageState:
    """A request that never got a response at all — DNS, timeout, connection
    reset. Not a wall (nothing served content to inspect) and not `missing`
    in pagestate's sense (that means a 404/410, i.e. the server spoke and
    said no) — but the caller only needs "no usable text," so shape it like
    one rather than inventing a fifth PageState.state value."""
    return PageState("missing", "missing", True, False, 0, reason)


def _row_to_result(row: sqlite3.Row, *, cache_hit: bool) -> FetchResult:
    state = PageState(
        row["page_state"] or "missing", row["page_kind"] or "",
        False, (row["page_state"] or "") in ("ok", "thin"),
        row["words"] or 0, "cached")
    text = None
    if state.usable and row["path"]:
        cached = Path(row["path"])
        if cached.exists():
            text = cached.read_text()
    return FetchResult(text=text, state=state, source_id=row["id"], cache_hit=cache_hit)


def fetch(conn: sqlite3.Connection, corpus: Path, url: str) -> FetchResult:
    """Canonicalize -> cache check -> HTTP GET -> clean -> classify -> upsert
    `source`. Never raises on a network problem; returns a FetchResult whose
    `state.usable` is False instead, so the worker loop treats "could not
    fetch" and "fetched but blocked" identically (both stop before an
    extraction call)."""
    canonical = canonicalize(url)
    sid = url_hash(url)

    cached = conn.execute(
        "SELECT * FROM source WHERE url_canonical = ? AND fetched_at IS NOT NULL",
        (canonical,)).fetchone()
    if cached is not None:
        return _row_to_result(cached, cache_hit=True)

    try:
        resp = requests.get(url, timeout=TIMEOUT_S,
                            headers={"User-Agent": USER_AGENT})
        raw, http_status = resp.text, resp.status_code
    except requests.RequestException as e:
        state = _network_failure_state(f"{type(e).__name__}: {e}")
        _upsert_source(conn, sid, url, canonical, text=None, raw="",
                       state=state, http_status=None)
        return FetchResult(text=None, state=state, source_id=sid, cache_hit=False)

    text = clean(raw, url=url)
    state = assess(text, raw=raw, http_status=http_status)
    _upsert_source(conn, sid, url, canonical, text=text, raw=raw,
                   state=state, http_status=http_status, corpus=corpus)
    return FetchResult(text=text if state.usable else None, state=state,
                       source_id=sid, cache_hit=False)


def _cache_path(corpus: Path, source_id: str) -> Path:
    return corpus / CACHE_SUBDIR / f"{source_id}.txt"


def _upsert_source(conn: sqlite3.Connection, sid: str, url: str, canonical: str, *,
                   text: str | None, raw: str, state: PageState,
                   http_status: int | None, corpus: Path | None = None) -> None:
    """Plain SQL, not `store.db.put` — `put()` only handles problem/actor
    (db.py: "put is for problem/actor, not source"). `source` is append-
    mostly and keyed on `url_canonical`, so an upsert on that unique index is
    the natural shape, matching the append-only style of `store/db.py`'s own
    writes rather than reusing machinery built for a different table."""
    path = None
    if text and state.usable and corpus is not None:
        dest = _cache_path(corpus, sid)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        path = str(dest.relative_to(corpus))

    sh = compute_simhash(text) if (text and is_reliable(text)) else None
    conn.execute(
        """
        INSERT INTO source (id, url, url_canonical, simhash, page_state,
                            page_kind, words, http_status, fetched_at, path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
        ON CONFLICT(url_canonical) DO UPDATE SET
          simhash = excluded.simhash, page_state = excluded.page_state,
          page_kind = excluded.page_kind, words = excluded.words,
          http_status = excluded.http_status, fetched_at = excluded.fetched_at,
          path = excluded.path
        """,
        (sid, url, canonical, f"{sh:x}" if sh else None, state.state,
         state.kind or None, state.words, http_status, path),
    )
    conn.commit()
