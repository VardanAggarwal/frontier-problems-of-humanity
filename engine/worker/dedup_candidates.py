"""Dedup the unadmitted `candidate` pool, per kind, before any of it is scored
or admitted (`05-worker-optimisations.md` — orchestrator step 1: "Resolving
duplicates in candidates").

Two tiers, not one pass, because they trust different signal:

Tier 1 reuses `text.preview.group()` as-is — the same containment/identifier
clustering Gate 0 already runs on search previews (§8), applied here to
candidate (name, evidence, url) instead of (title, snippet, url). It is
free (no model call) and catches exact/near-exact renames outright: the live
pool has "World Bank" x6, "FCI" x5, "CGWB" x5 as separate rows purely from
being rediscovered down different worker branches. `confirm` verdicts
(containment on boilerplate tokens only) are left unmerged in this version —
same reason gate1/resolve.py leave their own uncertain band alone rather than
guess.

Tier 2 runs only on what tier 1 could not already collapse — one row per
tier-1 cluster plus every singleton — and adds the semantic signal tier 1
cannot see: two paraphrases of the same actor's name ("Centre for Science
and Environment" vs "CSE") share no containment but do share an embedding
neighbourhood. `resolve.py` already validated the exact rule to use here
(module docstring, §8/§9): cosine alone cannot separate same-entity from
same-topic in this range, so a merge requires BOTH cosine > SAFE_MATCH_ABOVE
(imported from `resolve.py`, not re-picked) AND shared distinctive tokens
between the two names (`text.preview.content_tokens`/`_is_distinctive`,
same rescue rule, tightened as below). Below that bar, or with no lexical
overlap, nothing is merged — there is no per-candidate review surface yet,
so an uncertain tier-2 pair is left alone rather than guessed at or
escalated into a queue nothing drains.

Three corrections, all made after the first dry-run over the live pool
produced clusters no reader would accept:

**No transitive closure in tier 2.** The first version folded every accepted
pairwise edge into one global union-find, so A~B and B~C chained into A~C on
no evidence at all: a 75-row actor mega-cluster ("Haryana Government",
"Ministry of Jal Shakti", "Food Corporation of India", "ICAR", "Central
Ground Water Board"...) linked end to end through generic tokens, and a
six-member problem cluster holding blue baby syndrome, PFAS, farmer
suicides, sinkholes, microplastics and uranium at once. Tier 2 now does
star clustering against a fixed representative instead: survivors are walked
in `first_seen` order, each is compared ONLY against the established cluster
representatives, and it either joins one of them or becomes a representative
itself. A non-representative member is never compared against, so a cluster
can only ever be "things that each independently matched this one row" —
which is the claim the merge actually makes. Walking in `first_seen` order
also means the representative that emerges is the earliest-seen row, the
same rule `_pick_representative` applies at the end.

**A domain stoplist on top of `_COMMON`, not inside it.** `_COMMON` is tuned
for search-engine page-title boilerplate ("about us", "read more") and is
shared with Gate 0, where it is correct; it is not tuned for short Indian
institutional names, where "ministry", "board", "authority", "national",
"water", "development" recur across dozens of genuinely unrelated bodies.
`_DOMAIN_STOP` below is the candidate-name-specific layer, applied on top —
a token counts as distinctive for THIS module only if it clears both.

**Two shared distinctive tokens, not one.** `_is_distinctive` asks for one,
which is right for a long document title and far too weak for a two-word
org name, where a single surviving token ("ganga", "coal") is a topic, not
an identity. Both tiers require >= 2 here. `group()` itself is left alone —
it is shared — so tier 1's `merge` verdicts are re-checked against this
stricter bar afterwards and downgraded to unmerged when they miss it.

Names are compared with any trailing parenthetical stripped
(`Nitheshnirmal Sadhasivam (Virginia Tech)` -> `Nitheshnirmal Sadhasivam`).
A person carrying their affiliation in parentheses was being absorbed into
that affiliation by `group()`'s containment pass; person-in-org is an
`affiliated` edge in the schema, not the same entity. The original name is
kept for storage, logging and display — only the comparison input changes.

Encoding is batched once over tier-1 survivors only (never the full pool —
rows tier 1 already resolved don't need a vector), so the O(n^2) part of
this module is a single in-memory matrix multiply over that smaller set,
not n^2 model calls.

Representative per final cluster: earliest `first_seen` (first-discovered
instance), tiebroken by longest `evidence` (the more informative row to keep
live). `url` was considered as a tiebreak too but is populated on <1% of the
actor pool and 0% of the problem pool (checked against the live store before
writing this) — not a usable signal today.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from embed.guard import REPO, add_store_args, open_store
from embed.model import encode
from store import db
from text.preview import (_STOP, DEFAULT_CONTAINMENT, Preview, _Union,
                          _is_distinctive, containment, content_tokens, group,
                          normalize_title)

from .resolve import SAFE_MATCH_ABOVE, resolve_entity

KINDS = ("problem", "actor")

# Generic in THIS domain — Indian government, public-sector and civil-society
# naming — even though none of it is page-title boilerplate, which is all
# `text.preview._COMMON` was built to catch. Every word here recurs across
# dozens of unrelated bodies in the live pool: sharing "national" and "board"
# is not evidence that two rows are the same board. Applied ON TOP of
# `_COMMON`; `_COMMON` itself is shared with Gate 0 and stays as it is.
_DOMAIN_STOP = {
    # form of the body
    "ministry", "department", "government", "govt", "authority", "commission",
    "council", "board", "committee", "bureau", "agency", "office", "cell",
    "unit", "wing", "division", "directorate", "secretariat", "corporation",
    "corp", "company", "limited", "ltd", "institute", "institution",
    "society", "trust", "foundation", "association", "federation", "union",
    "network", "alliance", "coalition", "forum", "collective", "campaign",
    "movement", "initiative", "consortium", "panel",
    # NOT stopped, deliberately: bank, tribunal, court, university, institute's
    # proper names and the like are form words too, but they are the ONLY
    # distinctive token left in short names that are real duplicates ("World
    # Bank", "National Green Tribunal"). Stopping them cost four confirmed-good
    # clusters on the live pool; stopping the rest cost nothing.
    # what it purports to do
    "mission", "scheme", "programme", "program", "project", "plan", "policy",
    "act", "rules", "regulation", "regulations", "regulatory", "guidelines",
    "development", "management", "monitoring", "control", "protection",
    "conservation", "welfare", "empowerment", "promotion", "prevention",
    "research", "training", "education", "awareness", "action", "reform",
    "services", "service", "delivery", "support", "relief", "rehabilitation",
    "abatement", "mitigation", "assessment", "survey", "census", "planning",
    "implementation", "governance", "administration", "affairs",
    # place / scale
    "india", "indian", "bharat", "bharatiya", "national", "central", "centre",
    "center", "state", "states", "union", "regional", "district", "block",
    "local", "rural", "urban", "city", "municipal", "village", "panchayat",
    "zonal", "area", "areas", "region", "sector", "level",
    # Hindi/Sanskrit programme vocabulary that behaves the same way
    "yojana", "abhiyan", "samiti", "sabha", "parishad", "nigam",
    "vikas", "kalyan", "rashtriya", "swachh", "pradhan", "mantri",
    # domain nouns so broad they name a whole tier, not an entity
    "water", "air", "food", "land", "soil", "health", "energy", "power",
    "environment", "environmental", "forest", "climate", "pollution",
    "waste", "sanitation", "housing", "shelter", "labour", "labor",
    "agriculture", "agricultural", "farming", "farmers", "nutrition",
    "safety", "security", "quality", "resources", "resource", "system",
    "systems", "infrastructure", "supply", "sustainable", "sustainability",
    "human", "social", "community", "people", "public", "citizen", "citizens",
    "lead", "ground", "groundwater", "drinking", "rights", "justice",
}

# One trailing parenthetical only — "Name (Affiliation)". Nested or repeated
# parens are not worth handling: they do not occur in the live pool.
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

MIN_SHARED = 2   # see module docstring — one token is a topic, not an identity


@dataclass
class Cluster:
    """One decided group of candidate rows. A singleton is a real cluster —
    a row that matched nothing is still a row this pass has an opinion about,
    and a caller partitioning the pool needs it."""
    kind: str
    representative: int          # earliest first_seen; the row that survives
    members: list[int]           # representative first, then duplicates
    why: str                     # cluster-level merge reason; "" if singleton
    reasons: dict[int, str] = field(default_factory=dict)
    # ^ per duplicate id. Currently every duplicate in a cluster carries the
    #   SAME string (the cluster's accumulated tier-1/tier-2 reasons), because
    #   that is the granularity the `event` rows have always been written at.
    #   Keyed per member anyway so a future per-edge reason can land here
    #   without changing the callers.

    @property
    def duplicates(self) -> list[int]:
        return [m for m in self.members if m != self.representative]


def compare_name(name: str, kind: str = "actor") -> str:
    """The string a name is COMPARED as. Storage, logging and the chosen
    representative all keep the original — only matching sees this.

    The trailing-parenthetical strip is ACTOR-ONLY. It was added for the
    Person(Org) shape — `Nitheshnirmal Sadhasivam (Virginia Tech)` was being
    absorbed into `Virginia Tech`, which is an `affiliated` edge, not an
    identity — and on actor names a trailing parenthesis is nearly always an
    acronym or an affiliation, i.e. not the distinguishing part.

    On PROBLEM names it is the opposite: the parenthesis carries the
    substance — a contaminant list, a disease qualifier. Stripping it reduced
    `Fluorosis (skeletal and dental)` to bare `Fluorosis`, throwing away the
    only tokens (fluorosis/skeletal/dental) that could clear the two-token
    bar against `Fluorosis (dental/skeletal) from excessive fluoride in
    drinking water` — so the fix for one false merge created a missed merge
    in the other kind. Conditioning on `kind` was chosen over sniffing the
    parenthetical's content: "is this an affiliation or a qualifier" is a
    judgment call this module would get wrong silently, while `kind` is a
    column."""
    if kind != "actor":
        return name or ""
    stripped = _TRAILING_PAREN.sub("", name or "").strip()
    return stripped or (name or "")


def _acronym_swap(a: str, b: str, kind: str) -> bool:
    """One side's stem, after `compare_name` strips ITS OWN trailing
    parenthetical, is a bare single-token acronym, and the other side's stem
    is the multi-word expansion whose initials spell that same acronym.

    Live case: candidate #747 `"LEEP (Lead Exposure Elimination Project)"`
    and #751 `"Lead Exposure Elimination Project (LEEP)"` — the same org,
    filed twice from the same source with the acronym and the full name
    swapped across the parenthesis. `compare_name` strips the trailing
    parenthetical on both (that's what it's for — dropping an affiliation
    tag), which leaves `"LEEP"` on one side and the full expansion on the
    other. Those share zero tokens: `"leep"` is not a substring token of
    `"lead exposure elimination project"`, so neither the ordinary
    `>= MIN_SHARED` token-overlap bar nor `containment` (needs shared
    tokens) sees any relation, and the pair was left unmerged.

    Actor-only, same reasoning as `compare_name`'s own restriction — on
    problem names a parenthetical carries substance, not an alias."""
    if kind != "actor":
        return False
    for short, long in ((a, b), (b, a)):
        stem_short = compare_name(short, kind)
        if len(content_tokens(stem_short)) != 1:
            continue
        (tok,) = content_tokens(stem_short)
        if not tok.isalpha():
            continue
        stem_long = compare_name(long, kind)
        words = [w for w in normalize_title(stem_long).split() if w not in _STOP]
        if len(words) < 2:
            continue
        if "".join(w[0] for w in words) == tok:
            return True
    return False


def same_name(a: str, b: str, kind: str = "actor") -> bool:
    """The two names normalize to the same string once a trailing
    parenthetical is stripped.

    DEVIATION, flagged rather than hidden: the >= MIN_SHARED bar exists to
    stop PARTIAL overlap being read as identity, and on the live pool it also
    kills four clusters that are not partial overlap at all — "Food
    Corporation of India" x7, "Central Ground Water Board" x6, "World Bank"
    x6, "National Green Tribunal" x5, all byte-identical names whose every
    token is domain-generic ("food", "corporation", "india"; "central",
    "water", "board"). Counting distinctive tokens is the wrong question for
    an identical string: genericness of the words cannot make two copies of
    the same name two different entities. So string identity is its own
    sufficient condition, and MIN_SHARED applies only where the names differ.
    This is not in the agreed fix list and is up for review.

    The parenthetical cannot be dropped for free, though. Stripping it makes
    `State governments (Punjab, Haryana, Maharashtra, etc.)` and `State
    governments (forest/revenue)` identical strings, and they are not the same
    rows — the parenthesis WAS the content, and everything outside it is
    domain-generic. So identity has to hold on the full name too, unless one
    side carries no parenthetical at all: `Food Corporation of India` vs
    `Food Corporation of India (FCI)` is one name plus its own acronym, which
    is the case the strip exists for. Two DIFFERENT parentheticals on the same
    stem fall through to the ordinary >= MIN_SHARED bar instead."""
    if content_tokens(compare_name(a, kind)) != content_tokens(compare_name(b, kind)) \
            or not content_tokens(compare_name(a, kind)):
        return _acronym_swap(a, b, kind)
    both_qualified = (_TRAILING_PAREN.search(a or "")
                      and _TRAILING_PAREN.search(b or ""))
    if not both_qualified:
        return True
    return content_tokens(a) == content_tokens(b)


def distinctive_shared(a: str, b: str, kind: str = "actor") -> set[str]:
    """Shared tokens that survive both filters: `_COMMON` (via the existing
    `_is_distinctive`, token by token) and this module's `_DOMAIN_STOP`."""
    shared = (content_tokens(compare_name(a, kind))
              & content_tokens(compare_name(b, kind)))
    return {t for t in shared
            if t not in _DOMAIN_STOP and _is_distinctive({t})}


def _pool(conn, kind: str) -> list:
    return conn.execute(
        "SELECT id, name, url, evidence, first_seen FROM candidate "
        "WHERE kind = ? AND admitted IS NULL AND dup_of IS NULL "
        "ORDER BY first_seen", (kind,)).fetchall()


def _sort_key(cid: str, rows_by_id: dict):
    """Earliest `first_seen`, tiebroken by longest `evidence`, tiebroken by
    id so the order is total even when two rows were discovered in the same
    second (which happens — one worker branch writes several rows per commit,
    and `first_seen` has one-second resolution)."""
    row = rows_by_id[cid]
    return (row["first_seen"], -len(row["evidence"] or ""), int(cid))


def _pick_representative(members: list, rows_by_id: dict) -> str:
    return min(members, key=lambda cid: _sort_key(cid, rows_by_id))


def _tier1(rows: list, rows_by_id: dict, kind: str, uf: _Union, log
          ) -> dict[str, list[str]]:
    """Union tier-1 `merge` groups into `uf`. Returns {rep_key: [reason,...]}
    for logging — `group()`'s own reasons (identifier hit or containment
    score), kept separate from tier 2's so the final event `why` names which
    tier fired.

    `group()` merges on >= 1 distinctive shared token by its own `_COMMON`
    bar. That bar is too low for entity names, and `group()` is shared with
    Gate 0, so the verdict is re-checked here instead of patched there.

    `group()` is used as a CANDIDATE GENERATOR, not as the verdict. Its own
    union is transitive, so a cluster it returns is a path through the pool,
    not a set of rows that each matched one row: the first re-check pass here
    kept a whole group whenever any one pair inside it cleared the bar, and
    that let one good pair drag four bad rows with it (`Ritika Singh Thakur`
    into `Down To Earth` via a row named `Ritika Singh Thakur / Down To
    Earth`; four different ICAR institutes into one; three RESET sub-brands
    into `RESET Viral Index`; three different state-government rows into one).

    So each `group()` cluster is re-clustered here by the same star rule tier
    2 uses: members in `first_seen` order, each compared only against the
    members that have already become representatives, joining one of them or
    becoming a representative itself. The pair test is tier 1's own signal —
    a shared identifier, or containment at `group()`'s threshold — AND this
    module's stricter lexical bar (>= MIN_SHARED tokens past `_COMMON` and
    `_DOMAIN_STOP`, or identical names). Pairs that fail are logged, not
    silently dropped: a rejected pair is still the most likely duplicate in
    the pool and is what a review surface would want first."""
    previews = [Preview(key=str(r["id"]), title=compare_name(r["name"], kind),
                        snippet=r["evidence"] or "", url=r["url"] or "")
               for r in rows]
    reasons: dict[str, list[str]] = {}
    if len(previews) < 2:
        return reasons
    by_key = {p.key: p for p in previews}
    ids_by_key = {p.key: p.ids() for p in previews}

    def pair(a: str, b: str) -> tuple[str, set[str]] | None:
        """-> (reason, shared tokens) if a and b may merge, else None."""
        na, nb = rows_by_id[a]["name"], rows_by_id[b]["name"]
        shared = distinctive_shared(na, nb, kind)
        lexical_ok = len(shared) >= MIN_SHARED or same_name(na, nb, kind)
        common_ids = ids_by_key[a] & ids_by_key[b]
        if common_ids and lexical_ok:
            return f"identifier {sorted(common_ids)[0]}", shared
        c = containment(by_key[a].title, by_key[b].title)
        if c >= DEFAULT_CONTAINMENT and lexical_ok:
            return f"title~{c:.2f}", shared
        return None

    for g in group(previews):
        if g.verdict != "merge":
            continue  # `confirm` — boilerplate-only overlap, left unmerged
        order = sorted(g.members, key=lambda cid: _sort_key(cid, rows_by_id))
        reps: list[str] = []
        for cid in order:
            hit = None
            for rep_id in reps:
                hit = pair(cid, rep_id)
                if hit:
                    break
            if hit is None:
                reps.append(cid)   # a cluster of one, for now
                continue
            why, shared = hit
            uf.union(cid, rep_id)
            root = uf.find(rep_id)
            reasons.setdefault(root, []).append(
                f"tier1: {why}, shares {sorted(shared)!r} "
                f"between {cid!r} and {rep_id!r}")
        if len(reps) > 1:
            log(f"dedup: tier1 group split — group() clustered "
                f"{[rows_by_id[m]['name'] for m in g.members]!r} ({g.reason}); "
                f"star re-clustering leaves {len(reps)} separate rows: "
                f"{[rows_by_id[r]['name'] for r in reps]!r}")
    return reasons


def _tier2(rows_by_id: dict, survivor_ids: list[str], kind: str, uf: _Union,
           log) -> dict[str, list[str]]:
    """Embed the tier-1 survivors once, then STAR-cluster them: walk in
    `first_seen` order and compare each row only against the rows that have
    already become cluster representatives. A row either joins one of them or
    becomes a representative itself; it is never compared against as a
    non-representative member.

    That is what stops the transitive chain the first version produced (see
    the module docstring): every member of a cluster has independently
    cleared the bar against the SAME row, so the cluster means one claim
    rather than a path through the pool. The bar itself is `resolve.py`'s —
    cosine > SAFE_MATCH_ABOVE plus lexical overlap — with overlap raised to
    MIN_SHARED tokens past `_DOMAIN_STOP`.

    Returns {rep_key: [reason]}, same shape as `_tier1`."""
    reasons: dict[str, list[str]] = {}
    if len(survivor_ids) < 2:
        return reasons
    order = sorted(survivor_ids, key=lambda cid: _sort_key(cid, rows_by_id))
    texts = [f"{rows_by_id[i]['name']}. {rows_by_id[i]['evidence'] or ''}".strip()
            for i in order]
    vectors = encode(texts, role="query")  # peer comparison — both "query"
    sims = vectors @ vectors.T             # L2-normalized -> cosine directly

    reps: list[int] = []                   # positions in `order`, in order
    for pos, cid in enumerate(order):
        best: tuple[float, int, set[str]] | None = None
        for rpos in reps:
            cosine = float(sims[pos, rpos])
            if cosine <= SAFE_MATCH_ABOVE:
                continue
            na, nb = rows_by_id[cid]["name"], rows_by_id[order[rpos]]["name"]
            shared = distinctive_shared(na, nb, kind)
            lexical_ok = len(shared) >= MIN_SHARED or same_name(na, nb, kind)
            if not lexical_ok:
                continue  # topical closeness, not identity — resolve.py's rescue
            if best is None or cosine > best[0]:
                best = (cosine, rpos, shared)
        if best is None:
            reps.append(pos)               # a cluster of one, for now
            continue
        cosine, rpos, shared = best
        rep_id = order[rpos]
        uf.union(cid, rep_id)
        root = uf.find(rep_id)
        na, nb = rows_by_id[cid]["name"], rows_by_id[rep_id]["name"]
        lexical = (f"shares {sorted(shared)!r}" if shared
                  else f"acronym match {compare_name(na, kind)!r}/"
                       f"{compare_name(nb, kind)!r}" if _acronym_swap(na, nb, kind)
                  else "identical name")
        reasons.setdefault(root, []).append(
            f"tier2: cosine {cosine:.3f} clears {SAFE_MATCH_ABOVE}, "
            f"{lexical} between {cid!r} and {rep_id!r}")
    return reasons


def _silent(*a, **k) -> None:
    pass


def compute_clusters(conn, kind: str, *, log=_silent) -> list[Cluster]:
    """The whole dedup decision for one kind, as data. Reads the store,
    writes nothing, prints nothing unless given a `log`.

    Returns EVERY cluster in the unadmitted pool, singletons included, so a
    caller gets a complete partition of the pool rather than only the parts
    that merged — `[c.representative for c in compute_clusters(...)]` is the
    survivor set.

    Split out from `dedup_kind` so `score_candidates.py` can rank the real
    clusters instead of keeping a second, approximate duplicate detector of
    its own (it had one, grouping by slugified name, written only because
    this module was mid-repair). Two duplicate-detection implementations in
    one pipeline drift apart, and the one that is not the CLI's is the one
    nobody notices drifting.

    The caller must re-run this rather than read `candidate.dup_of`: the CLI
    has only ever been run with `--dry-run`, so `dup_of` is still NULL for
    every row in the store and a `dup_of`-based pool would silently be the
    un-deduped pool."""
    rows = _pool(conn, kind)
    rows_by_id = {str(r["id"]): r for r in rows}
    if len(rows) < 2:
        return [Cluster(kind, int(r["id"]), [int(r["id"])], "", {})
                for r in rows]

    uf = _Union(rows_by_id.keys())
    all_reasons: dict[str, list[str]] = {}

    t1_reasons = _tier1(rows, rows_by_id, kind, uf, log)
    for rep, rs in t1_reasons.items():
        all_reasons.setdefault(rep, []).extend(rs)

    # Tier-1 survivors: one row per current cluster, plus every singleton —
    # never re-embed a row tier 1 already merged away. The row that stands
    # for a cluster is its representative (earliest `first_seen`), not the
    # union-find root, which is an implementation artefact: tier 2 compares
    # and orders on this row's name and date, so it has to be the one the
    # final cluster will actually be filed under.
    clusters_after_t1: dict[str, list[str]] = {}
    for cid in rows_by_id:
        clusters_after_t1.setdefault(uf.find(cid), []).append(cid)
    survivor_ids = [_pick_representative(m, rows_by_id)
                    for m in clusters_after_t1.values()]

    t2_reasons = _tier2(rows_by_id, survivor_ids, kind, uf, log)
    for rep, rs in t2_reasons.items():
        all_reasons.setdefault(rep, []).extend(rs)

    # Final clusters, after both tiers.
    final: dict[str, list[str]] = {}
    for cid in rows_by_id:
        final.setdefault(uf.find(cid), []).append(cid)

    # Reasons were keyed by whatever the union-find root was AT THE TIME the
    # tier fired; a later tier-2 union can move that root. Re-key to the
    # final root so a cluster's `why` still carries its tier-1 reason.
    rekeyed: dict[str, list[str]] = {}
    for key, rs in all_reasons.items():
        rekeyed.setdefault(uf.find(key), []).extend(rs)
    all_reasons = rekeyed

    out: list[Cluster] = []
    for root, members in final.items():
        rep = _pick_representative(members, rows_by_id)
        dups = sorted((m for m in members if m != rep),
                      key=lambda cid: _sort_key(cid, rows_by_id))
        if dups:
            why = "; ".join(all_reasons.get(root, [])
                            or ["merged (reason not captured)"])
        else:
            why = ""
        out.append(Cluster(kind, int(rep), [int(rep)] + [int(m) for m in dups],
                           why, {int(m): why for m in dups}))
    out.sort(key=lambda c: _sort_key(str(c.representative), rows_by_id))
    return out


def resolve_against_minted(conn, corpus: Path, kind: str,
                           clusters: list[Cluster], *, dry_run: bool,
                           log=print) -> dict:
    """Third pass: check what survived candidate-vs-candidate clustering
    against the entities ALREADY MINTED in `problem`/`actor`.

    The first two tiers only ever compare candidates to each other, so a
    candidate that restates something the corpus already holds sits in the
    pool forever looking novel. Live examples, all problem-kind: "Waterborne
    diseases (cholera, dysentery, hepatitis A/E)" against the minted
    `waterborne-diseases-cholera-dysentery-hepatitis`; "Virtual water trade
    imbalance" against `virtual-water-exports-depleting-groundwater`.

    The check itself is NOT new code. `resolve.resolve_entity` already does
    exactly this — normalized alias/id match first, embedding shortlist as
    the fallback, lexical rescue below the safe band — and it is calibrated
    for this exact comparison (candidate name+context vs indexed entity
    text). It has only ever been called one candidate at a time from inside
    `worker.py` at promotion. This is the same call run in bulk over the
    pool, not a second resolver.

    One call per cluster REPRESENTATIVE, not per row: the duplicates behind
    a representative are already accounted for by `dup_of`, and re-resolving
    them would pay for the same embedding several times to reach the same
    answer.

    Decisions are honoured as `resolve.py` defines them, and only the two
    confident ones act:
      - `exact` / `shortlist_top` -> set `resolved_to` AND `admitted = 1`.
        The candidate is finished: it names something the store already has,
        so there is nothing for the deep dive to find. That is the same state
        `worker.py` would leave it in had it gone through admission and
        matched the same entity.
      - `ambiguous` -> LEFT ALONE. `resolve.py`'s §9 reasoning is that an
        ambiguous merge is an escalation, not something to settle by
        comparing two texts harder. Auto-resolving here would be exactly the
        per-record machine judgment that module refuses to make.
      - `new` -> left alone, continues to normal scoring and admission.

    A wrong `resolved_to` is the worst outcome available here — worse than a
    missed one — because the candidate stops being its own row and is
    absorbed into another problem's identity, silently. Hence: the two
    confident decisions only, no widening of the band.

    A `shortlist_top` cosine is additionally gated on the SAME lexical bar
    the two candidate-vs-candidate tiers use — >= MIN_SHARED distinctive
    shared tokens (or `same_name`) between the candidate's name and the
    matched entity's title. The first dry-run over the backfilled index is
    why: the 0.90 band is inverted for this particular comparison. `Soil
    inorganic carbon (SIC) depletion` matched `soil-organic-carbon-soc-
    depletion` at 0.911 and `Food loss in Indian supply chains` matched
    `urban-food-cost-of-living-crisis-from-supply-chain-fragmentation` at
    0.902, while `Waterborne diseases (cholera, dysentery, hepatitis A/E)`
    against the minted `Waterborne diseases (cholera, dysentery, hepatitis)`
    — five shared distinctive tokens, the same problem — sat at 0.893 and
    was refused. `resolve.py`'s docstring already flags its band as
    "unmeasured for the resolver's specific comparison"; this is that
    measurement, and the lexical signal is the cheap correction, exactly as
    it was for tier 2.

    The gate is local to this pass. `resolve_entity`'s own contract and its
    other caller (`worker.py`'s admission-time resolution) are untouched —
    that is a separate decision.

    `exact` is NOT gated: a normalized alias/id match is identity by
    construction, with no cosine in it to distrust.

    Known miss, accepted rather than patched: the SIC/SOC pair shares
    {soil, carbon, depletion} and so clears a >= 2 token bar despite
    "organic" vs "inorganic" making them different pools. Antonym-aware
    tokenizing is a rabbit hole; the pair is logged as `ambiguous` only if
    the cosine happens not to clear."""
    acted = ambiguous = fresh = 0
    for c in clusters:
        row = conn.execute(
            "SELECT name, evidence FROM candidate WHERE id = ?",
            (c.representative,)).fetchone()
        if row is None:
            continue
        name = row["name"]
        result = resolve_entity(conn, corpus, kind, name, row["evidence"] or "")
        decision, entity_id = result.decision, result.entity_id
        gate = ""
        if decision == "shortlist_top" and entity_id:
            title = db.title_of(conn, kind, entity_id) or ""
            shared = distinctive_shared(name, title, kind)
            if len(shared) >= MIN_SHARED or same_name(name, title, kind):
                gate = f"; lexical gate passed, shares {sorted(shared)!r}"
            else:
                # Cosine says yes, the names do not. Same handling as
                # resolve.py's own `ambiguous`: don't merge, don't escalate
                # anywhere new.
                decision = "ambiguous"
                result.reason = (
                    f"cosine cleared ({result.reason}) but the names share "
                    f"{sorted(shared) or 'no'} distinctive token(s) with "
                    f"{entity_id!r} ({title!r}) — under {MIN_SHARED}, so not "
                    f"auto-resolved")
                entity_id = None

        if decision in ("exact", "shortlist_top") and entity_id:
            acted += 1
            why = f"{decision}: {result.reason}{gate}"
            log(f"minted[{kind}]: {c.representative} ({name!r}) "
                f"-> resolved_to {entity_id!r}, admitted — {why}")
            if not dry_run:
                conn.execute(
                    "UPDATE candidate SET resolved_to = ?, admitted = 1 "
                    "WHERE id = ?", (entity_id, c.representative))
                db.record(conn, "candidate", str(c.representative),
                          "resolved_to", None, entity_id,
                          by="dedup_candidates", why=why)
        elif decision == "ambiguous":
            ambiguous += 1
            log(f"minted[{kind}]: {c.representative} ({name!r}) "
                f"-> ambiguous, left for review — {result.reason}")
        else:
            fresh += 1

    log(f"minted[{kind}]: checked={len(clusters)} resolved={acted} "
        f"ambiguous={ambiguous} new={fresh}"
        f"{' (dry-run, nothing written)' if dry_run else ''}")
    return dict(kind=kind, checked=len(clusters), resolved=acted,
                ambiguous=ambiguous, new=fresh)


def dedup_kind(conn, kind: str, *, dry_run: bool, corpus: Path | None = None,
               log=print) -> dict:
    rows = _pool(conn, kind)
    pool_in = len(rows)
    if pool_in < 2:
        log(f"dedup[{kind}]: pool has {pool_in} row(s) — nothing to compare")
        return dict(kind=kind, pool_in=pool_in, clusters=0, merged=0,
                    survivors=pool_in)
    names = {int(r["id"]): r["name"] for r in rows}

    merged_count = 0
    cluster_count = 0
    clusters = compute_clusters(conn, kind, log=log)
    for c in clusters:
        if len(c.members) < 2:
            continue
        cluster_count += 1
        for cid in c.duplicates:
            merged_count += 1
            log(f"dedup[{kind}]: {cid} ({names[cid]!r}) "
                f"-> dup_of {c.representative} "
                f"({names[c.representative]!r}) — {c.why}")
            if not dry_run:
                conn.execute("UPDATE candidate SET dup_of = ? WHERE id = ?",
                            (c.representative, cid))
                db.record(conn, "candidate", str(cid), "dup_of", None,
                          str(c.representative), by="dedup_candidates",
                          why=c.why)

    if not dry_run:
        conn.commit()

    survivors = pool_in - merged_count
    log(f"dedup[{kind}]: pool_in={pool_in} clusters={cluster_count} "
        f"merged={merged_count} survivors={survivors}"
        f"{' (dry-run, nothing written)' if dry_run else ''}")

    # Runs AFTER clustering, on one row per cluster — see
    # `resolve_against_minted`. Skipped only if no corpus root was passed.
    minted = None
    if corpus is not None:
        minted = resolve_against_minted(conn, corpus, kind, clusters,
                                        dry_run=dry_run, log=log)
        if not dry_run:
            conn.commit()

    return dict(kind=kind, pool_in=pool_in, clusters=cluster_count,
                merged=merged_count, survivors=survivors, minted=minted)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_store_args(ap)
    ap.add_argument("--kind", choices=KINDS, default=None,
                    help="restrict to one kind; default runs both, "
                         "problem and actor pools never compared to each other")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and log clusters, write nothing")
    ap.add_argument("--no-minted", action="store_true",
                    help="skip the minted-entity pass (candidate-vs-candidate "
                         "clustering only, as this module behaved before it "
                         "could resolve against `problem`/`actor`)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    log = (lambda *a, **k: None) if args.quiet else print
    conn = open_store(args, log=log)
    corpus = None if args.no_minted else Path(args.corpus)
    try:
        kinds = [args.kind] if args.kind else list(KINDS)
        for kind in kinds:
            dedup_kind(conn, kind, dry_run=args.dry_run, corpus=corpus,
                       log=log)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
