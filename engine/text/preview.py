"""Gate 0 — dedup on search previews, before anything is fetched.

Dedup happens here rather than post-fetch for two structural reasons: it
catches URLs that cannot be fetched at all, and identifiers in the URL
match the same work rendered at different lengths by different hosts,
which no text comparison can do. Measured advantage over post-fetch
SimHash: EVIDENCE.md §preview-vs-simhash.

The catch: containment alone merges generic titles ("About us" into
"About us | Mine Labour Protection Campaign"), and no minimum-token floor
separates those from real truncations — both are short prefixes. So this
module returns a VERDICT, not a boolean:

    merge    — a shared identifier, or containment on a distinctive title
    confirm  — containment, but the shared tokens are boilerplate; needs a
               snippet, domain or fetch comparison before merging
    (absent) — no relation

Callers must not treat `confirm` as a merge. Doing so is how two different
organisations with boilerplate page titles become one actor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
import unicodedata

# --- title normalization -------------------------------------------------

# Site chrome a search engine appends. Generic shapes, not a per-site list.
_CHROME = re.compile(
    r"\s*[-|–—:·]\s*(?:PMC|PubMed|Semantic\s+Scholar|ResearchGate|"
    r"Springer(?:\s+Nature\s+Link)?|ScienceDirect|JSTOR|Academia\.edu|"
    r"Download\s+Scientific\s+Diagram|Google\s+Books|"
    r"(?:Indian\s+)?Journal\s+of\s+[\w\s]+?(?::\s*Vol\s*\d+.*)?|"
    r"[\w\s]{2,30}?(?:\.(?:com|org|in|net|gov)))\s*$", re.I)
_PDF_PREFIX = re.compile(r"^\s*(?:\(PDF\)|\[PDF\]|PDF)\s*", re.I)
_TRUNC = re.compile(r"\s*(?:\.\.\.|…)\s*")
_WORD = re.compile(r"\w+", re.UNICODE)

_STOP = {"the", "a", "an", "of", "in", "on", "for", "to", "and", "with", "by",
         "at", "from", "is", "as", "its", "how", "why", "what", "s",
         # page-chrome pronouns — "About us" must not tokenize to anything
         "about", "us", "we", "our", "you", "your", "home", "contact"}

# High-frequency English plus words that carry no topic on their own. A
# title whose shared tokens are drawn only from here is boilerplate, and
# containment on it means nothing: "Help for mine workers" is a prefix of
# a real article title AND a standalone generic page. Hand-curated rather
# than computed because genericness is a property of the language, not of
# the batch — see EVIDENCE.md, "Why `confirm` exists".
_COMMON = {
    "new", "news", "report", "reports", "annual", "update", "updates", "page",
    "site", "website", "welcome", "info", "information", "detail", "details",
    "overview", "summary", "index", "list", "search", "results", "article",
    "articles", "blog", "post", "posts", "story", "stories", "press", "release",
    "media", "download", "downloads", "pdf", "document", "documents", "file",
    "view", "read", "more", "all", "other", "others", "general", "main",
    "help", "support", "service", "services", "work", "works", "working",
    "project", "projects", "programme", "program", "team", "people", "member",
    "members", "staff", "board", "trust", "society", "foundation", "centre",
    "center", "organisation", "organization", "ngo", "group", "groups",
    "india", "indian", "state", "national", "government", "public", "private",
    "year", "years", "month", "day", "time", "today", "latest", "current",
    "man", "men", "woman", "women", "child", "children", "worker", "workers",
    "mine", "mines", "job", "jobs", "case", "cases", "issue", "issues",
    "problem", "problems", "story", "part", "one", "two", "three", "first",
    "last", "next", "top", "best", "good", "great", "big", "small", "high",
    "low", "get", "gets", "make", "makes", "take", "give", "go", "come",
    "see", "know", "think", "want", "need", "use", "used", "find", "found",
    "may", "can", "will", "would", "could", "should", "must", "not", "no",
    "yes", "who", "when", "where", "which", "that", "this", "these", "those",
    "it", "he", "she", "they", "them", "their", "his", "her", "have", "has",
    "had", "been", "being", "was", "were", "are", "am", "do", "does", "did",
    "up", "down", "out", "off", "over", "under", "after", "before", "into",
    "through", "during", "between", "against", "without", "within", "per",
    "also", "only", "just", "than", "then", "now", "here", "there", "very",
    "much", "many", "some", "any", "each", "every", "both", "few", "most",
}


def _is_distinctive(tokens: set[str]) -> bool:
    """True if the token set carries at least one topic-bearing word.

    Bare numbers do not count: "Annual Report 2023" is boilerplate on
    thousands of sites, and the year is what makes it look specific.
    """
    return any(t not in _COMMON and not t.isdigit() and len(t) > 2
               for t in tokens)


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKC", title or "")
    t = _PDF_PREFIX.sub("", t)
    for _ in range(2):          # a title can carry two chrome segments
        t = _CHROME.sub("", t)
    t = _TRUNC.sub(" ", t)
    return " ".join(_WORD.findall(t.lower()))


def content_tokens(title: str) -> set[str]:
    return {w for w in normalize_title(title).split() if w not in _STOP}


def containment(a: str, b: str) -> float:
    """Overlap as a fraction of the SHORTER title.

    Not Jaccard: search engines truncate titles, so one side is routinely
    a stem of the other, and Jaccard punishes exactly that. Measured gap:
    EVIDENCE.md, "Containment vs Jaccard".
    """
    A, B = content_tokens(a), content_tokens(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


# --- identifiers ---------------------------------------------------------

_ID_PATTERNS = (
    ("doi",   re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", re.I)),
    ("pmid",  re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|\bPMID:?\s*)(\d{6,9})", re.I)),
    ("pmc",   re.compile(r"\b(PMC\d{6,9})\b", re.I)),
    ("arxiv", re.compile(r"\barxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.I)),
)
_DOI_TRAIL = ".,;)]}'\"<>"


def extract_ids(*texts: str) -> set[str]:
    """Identifiers from any of url / title / snippet.

    Free, and it catches what no text comparison can: the same work
    rendered at different lengths by different hosts.
    """
    blob = " ".join(t for t in texts if t)
    out: set[str] = set()
    for kind, pat in _ID_PATTERNS:
        for m in pat.findall(blob):
            out.add(f"{kind}:{m.rstrip(_DOI_TRAIL).lower()}")
    return out


# --- grouping ------------------------------------------------------------

@dataclass
class Preview:
    key: str
    title: str = ""
    snippet: str = ""
    url: str = ""

    def ids(self) -> set[str]:
        return extract_ids(self.url, self.title, self.snippet)


@dataclass
class Group:
    members: list[str]
    verdict: str                 # "merge" | "confirm"
    reason: str
    evidence: list[str] = field(default_factory=list)


class _Union:
    def __init__(self, keys):
        self.p = {k: k for k in keys}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb
            return True
        return False



DEFAULT_CONTAINMENT = 0.85   # true dup pair scored 1.00 here, 0.33 on Jaccard


def group(previews: list[Preview], *,
          threshold: float = DEFAULT_CONTAINMENT) -> list[Group]:
    """Cluster previews before fetching. Returns groups of size > 1 only.

    Two passes, because they carry different confidence. Identifiers merge
    outright. Title containment merges only when the shared tokens are
    distinctive within this batch — otherwise it is reported as `confirm`
    and left unmerged for a later signal to settle.
    """
    if len(previews) < 2:
        return []
    by_key = {p.key: p for p in previews}
    uf = _Union(by_key)
    reasons: dict[str, list[str]] = {}

    # Pass 1 — identifiers. Always safe.
    seen: dict[str, str] = {}
    for p in previews:
        for ident in p.ids():
            if ident in seen:
                if uf.union(p.key, seen[ident]):
                    reasons.setdefault(uf.find(p.key), []).append(ident)
            else:
                seen[ident] = p.key

    # Pass 2 — distinctive title containment.
    pending: list[Group] = []
    keys = list(by_key)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if uf.find(a) == uf.find(b):
                continue
            pa, pb = by_key[a], by_key[b]
            c = containment(pa.title, pb.title)
            if c < threshold:
                continue
            shared = content_tokens(pa.title) & content_tokens(pb.title)
            if _is_distinctive(shared):
                if uf.union(a, b):
                    reasons.setdefault(uf.find(a), []).append(f"title~{c:.2f}")
            else:
                pending.append(Group(
                    [a, b], "confirm",
                    f"title~{c:.2f} but every shared token is boilerplate "
                    f"({', '.join(sorted(shared)) or 'none'})"))

    clusters: dict[str, list[str]] = {}
    for k in by_key:
        clusters.setdefault(uf.find(k), []).append(k)

    out = [Group(sorted(v), "merge",
                 "; ".join(reasons.get(r, [])) or "identifier",
                 reasons.get(r, []))
           for r, v in clusters.items() if len(v) > 1]
    merged = {k for g in out for k in g.members}
    out += [g for g in pending if not set(g.members) <= merged]
    return out


def fetch_list(previews: list[Preview], **kw) -> list[str]:
    """One representative key per merged group, plus every ungrouped key.

    `confirm` groups are NOT collapsed — both members still get fetched,
    because the fetch is what settles them.
    """
    groups = group(previews, **kw)
    drop = {k for g in groups if g.verdict == "merge" for k in g.members[1:]}
    return [p.key for p in previews if p.key not in drop]
