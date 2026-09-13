"""The question registry loader — F1, `04-worker-build-plan.md` §1a / §4
contract 2.

Loads `engine/questions.yaml` — the single home for the ~35 questions'
text, stable ids, claim fields and tier flags — and exposes simple
accessors. Two consumers read the same strings from here: `prompts.py`
puts `question` in the extraction prompt, and stage 5 (not yet built)
encodes `retrieval_query` as an e5 `query:` string. Nothing here talks to
an LLM, a database, or the network — this is pure parsing plus validation,
by design (§4: "None of them knows the pipeline exists").

Validation fails loudly (`QuestionRegistryError`) on load, per §1a's
contract:
  - a duplicate question id
  - a question referencing a bucket id that doesn't exist
  - `retrieval: true` with no bucket
  - a bucket with zero questions
  - a `tag:<ns>` claim_field whose namespace is absent from
    `store/tags.py`'s REGISTRY
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from store.tags import REGISTRY as TAG_REGISTRY

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "questions.yaml"


class QuestionRegistryError(ValueError):
    """The YAML loaded but failed a structural or cross-reference check."""


@dataclass(frozen=True)
class Bucket:
    id: str
    kind: str                      # "problem" | "actor"
    questions: tuple[str, ...]     # question ids, in file order
    target_section: str | None = None
    retrieval_query: str | None = None
    retrieval_query_source: str | None = None   # "measured" | "heuristic"
    auc: float | None = None
    measured_against: str | None = None
    measured_n: int | None = None
    caveat: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Question:
    id: str
    kind: str                      # "problem" | "actor"
    question: str                  # natural-language text, feeds prompts.py
    claim_field: str
    multi: bool
    retrieval: bool
    bucket: str | None = None
    retrieval_note: str | None = None
    depth_tier: str = "full"       # "registry" | "full"
    depth_tier_resolved: str | None = None   # one-line justification, only on
                                              # the questions §4/track-B flagged


@dataclass(frozen=True)
class Registry:
    questions: tuple[Question, ...]
    buckets: tuple[Bucket, ...]
    _by_id: dict[str, Question] = field(repr=False, compare=False,
                                         default_factory=dict)
    _buckets_by_id: dict[str, Bucket] = field(repr=False, compare=False,
                                               default_factory=dict)

    # -- accessors -----------------------------------------------------
    def all(self, kind: str | None = None) -> tuple[Question, ...]:
        """Every question, optionally filtered to one kind."""
        if kind is None:
            return self.questions
        return tuple(q for q in self.questions if q.kind == kind)

    def get(self, question_id: str) -> Question:
        """Lookup by id. Raises KeyError if unknown."""
        return self._by_id[question_id]

    def bucket(self, bucket_id: str) -> Bucket:
        """Lookup a bucket by id. Raises KeyError if unknown."""
        return self._buckets_by_id[bucket_id]

    def in_bucket(self, bucket_id: str) -> tuple[Question, ...]:
        """Every question belonging to one bucket, in file order."""
        b = self.bucket(bucket_id)
        return tuple(self.get(qid) for qid in b.questions)

    def retrieval_questions(self, kind: str | None = None) -> tuple[Question, ...]:
        """Questions with `retrieval: true` — the ones stage 5 encodes."""
        return tuple(q for q in self.all(kind) if q.retrieval)

    def open_questions(self, kind: str | None = None) -> tuple[Question, ...]:
        """Alias for every question of a kind — `04-worker-build-plan.md`
        §1d leaves "open" undefined for `multi` questions; until that
        closing rule lands, every question is open, so this returns the
        same set as `all()`. Kept as a separate name so callers written
        against "open questions" don't need to change when §1d resolves."""
        return self.all(kind)

    def bucket_for(self, question_id: str) -> Bucket | None:
        """The bucket a question belongs to, or None (inference-only or
        unbucketed)."""
        q = self.get(question_id)
        return self.bucket(q.bucket) if q.bucket else None


# ------------------------------------------------------------------ load --
def _claim_field_ns(claim_field: str) -> str | None:
    """Return the `tag:<ns>` namespace of a claim field, or None if it isn't
    a tag field at all (bare column, `ask:*`, `channel:*`, `emits/edges`)."""
    if claim_field.startswith("tag:"):
        return claim_field[len("tag:"):]
    return None


def load(path: Path | str = DEFAULT_PATH) -> Registry:
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict) or "questions" not in raw or "buckets" not in raw:
        raise QuestionRegistryError(
            f"{path}: expected a mapping with `questions` and `buckets` keys")

    questions: list[Question] = []
    seen_ids: set[str] = set()
    for row in raw["questions"]:
        qid = row["id"]
        if qid in seen_ids:
            raise QuestionRegistryError(f"duplicate question id: {qid!r}")
        seen_ids.add(qid)

        claim_field = row["claim_field"]
        ns = _claim_field_ns(claim_field)
        if ns is not None and ns not in TAG_REGISTRY:
            raise QuestionRegistryError(
                f"{qid}: claim_field {claim_field!r} names tag namespace "
                f"{ns!r}, which is absent from store/tags.py's REGISTRY")

        retrieval = bool(row["retrieval"])
        bucket_id = row.get("bucket")
        if retrieval and not bucket_id:
            raise QuestionRegistryError(
                f"{qid}: retrieval: true but no bucket assigned")

        questions.append(Question(
            id=qid,
            kind=row["kind"],
            question=row["question"],
            claim_field=claim_field,
            multi=bool(row.get("multi", False)),
            retrieval=retrieval,
            bucket=bucket_id,
            retrieval_note=row.get("retrieval_note"),
            depth_tier=row.get("depth_tier", "full"),
            depth_tier_resolved=row.get("depth_tier_resolved"),
        ))

    buckets: list[Bucket] = []
    seen_bucket_ids: set[str] = set()
    for row in raw["buckets"]:
        bid = row["id"]
        if bid in seen_bucket_ids:
            raise QuestionRegistryError(f"duplicate bucket id: {bid!r}")
        seen_bucket_ids.add(bid)

        bqs = tuple(row.get("questions") or ())
        if not bqs:
            raise QuestionRegistryError(f"bucket {bid!r} has no questions")

        buckets.append(Bucket(
            id=bid,
            kind=row["kind"],
            questions=bqs,
            target_section=row.get("target_section"),
            retrieval_query=row.get("retrieval_query"),
            retrieval_query_source=row.get("retrieval_query_source"),
            auc=row.get("auc"),
            measured_against=row.get("measured_against"),
            measured_n=row.get("measured_n"),
            caveat=row.get("caveat"),
            note=row.get("note"),
        ))

    bucket_ids = {b.id for b in buckets}
    for q in questions:
        if q.bucket is not None and q.bucket not in bucket_ids:
            raise QuestionRegistryError(
                f"{q.id}: references unknown bucket {q.bucket!r}")

    by_id = {q.id: q for q in questions}
    buckets_by_id = {b.id: b for b in buckets}

    return Registry(
        questions=tuple(questions),
        buckets=tuple(buckets),
        _by_id=by_id,
        _buckets_by_id=buckets_by_id,
    )


# Module-level singleton, loaded eagerly like `store/tags.py`'s REGISTRY —
# a bad questions.yaml should fail at import time, not at first use deep in
# a run.
REGISTRY = load()
