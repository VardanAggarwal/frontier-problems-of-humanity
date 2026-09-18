-- Engine v2 store. One file is the whole graph.
--
-- Three record types (01-minimal.md §2): problem, actor, edge. Everything else
-- here is either a view layer over those (tag), a resolver aid (alias, source),
-- a catalyst payload (channel, ask), or the autonomous loop's own state
-- (candidate, population, event).
--
-- Departures from the §3 sketch, deliberate:
--   tag        split into (ns, value) instead of one "tier:1" string, so
--              "every mechanism tag" is an index range rather than a LIKE scan.
--   alias      §3 had nowhere to put `aliases:` / `aka:`. The resolver (step 3)
--              needs them, so they get a table rather than a JSON column.
--   ask        actor `needs:` / `offers:` are the connect-pass input. Dropping
--              them in migration would have lost 382 rows.
--   gap_note   gap itself stays derived (problem_gap). This column holds the
--              paragraph behind the finding, which is evidence, not state.
--
-- List-valued columns are JSON arrays, queried with json_each. They are lists
-- of closed enums with no fields of their own; a join table would buy nothing.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
) WITHOUT ROWID;

-- ---------------------------------------------------------------- problem ---
-- Recursive. A tier-level need, a cross-need node and a single documented
-- failure instance are this row at different depths; parentage is an edge.
CREATE TABLE problem (
  id         TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  one_line   TEXT,
  status     TEXT NOT NULL DEFAULT 'stub'
             CHECK (status IN ('stub', 'researched', 'stale')),
  geography  TEXT NOT NULL DEFAULT '[]'
             CHECK (json_valid(geography) AND json_type(geography) = 'array'),
  -- Which legs this problem needs covered. NULL = not yet judged, which makes
  -- the gap unknown rather than zero.
  needs_legs TEXT CHECK (needs_legs IS NULL OR
             (json_valid(needs_legs) AND json_type(needs_legs) = 'array')),
  gap_note   TEXT,
  doc        TEXT,          -- path to prose on disk; NULL means stub
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated    TEXT
);

-- ------------------------------------------------------------------ actor ---
CREATE TABLE actor (
  id                  TEXT PRIMARY KEY,
  title               TEXT NOT NULL,
  one_line            TEXT,          -- what they do, one sentence (mirrors problem.one_line)
  type                TEXT NOT NULL CHECK (type IN ('org', 'individual')),
  legs                TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(legs)),
  depth               TEXT NOT NULL DEFAULT 'registry'
                      CHECK (depth IN ('registry', 'tracked', 'excluded')),
  lifecycle           TEXT CHECK (lifecycle IS NULL OR lifecycle IN
                      ('operating', 'scaling', 'distressed', 'dormant',
                       'acquired', 'shut', 'won-and-dissolved')),
  lifecycle_as_of     TEXT,
  ecosystem_role      TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(ecosystem_role)),
  affected_led        TEXT CHECK (affected_led IS NULL OR
                      affected_led IN ('yes', 'no', 'partial')),
  representation_unit TEXT CHECK (representation_unit IS NULL OR
                      representation_unit IN ('local-affected', 'central-org',
                      'enterprise', 'central-at-named-legitimacy-cost')),
  stance              TEXT NOT NULL DEFAULT 'works-the-remedy'
                      CHECK (stance IN ('works-the-remedy', 'neutral',
                      'organised-against-remedy', 'ambiguous')),
  geography           TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(geography)),
  contact_route       TEXT,
  followed            INTEGER NOT NULL DEFAULT 0 CHECK (followed IN (0, 1)),
  followed_date       TEXT,
  last_checked        TEXT,
  funding             TEXT,          -- source + scale + latest round/grant/budget + date, one sentence
  scale_metric        TEXT,          -- the one checkable number (members/homes/users/revenue), dated
  doc                 TEXT,
  created_at          TEXT NOT NULL DEFAULT (datetime('now')),
  updated             TEXT
);

CREATE INDEX actor_depth_ix ON actor (depth) WHERE depth = 'tracked';

-- ------------------------------------------------------------------ alias ---
-- Former ids and alternate names. Read by the resolver before it creates
-- anything; append-only in practice, never rewritten on rename.
CREATE TABLE alias (
  entity_kind TEXT NOT NULL CHECK (entity_kind IN ('problem', 'actor')),
  entity_id   TEXT NOT NULL,
  alias       TEXT NOT NULL,
  norm        TEXT NOT NULL,   -- casefolded, punctuation-stripped match key
  PRIMARY KEY (entity_kind, entity_id, alias)
) WITHOUT ROWID;

CREATE INDEX alias_norm_ix ON alias (norm);

-- ----------------------------------------------------------------- source ---
-- A document. A cited-but-never-fetched URL and a fetched, cleaned, hashed
-- page are the same row at different completeness; `fetched_at IS NULL` is the
-- difference. id is url_hash so an insert is idempotent on the canonical URL.
CREATE TABLE source (
  id            TEXT PRIMARY KEY,
  url           TEXT NOT NULL,
  url_canonical TEXT NOT NULL,
  title         TEXT,
  org           TEXT,
  year          INTEGER,
  lang          TEXT,
  kind          TEXT,
  simhash       TEXT,          -- hex, NULL when below the reliability floor
  -- Two different fields, kept separate rather than collapsed into one enum:
  -- state is whether the page may be stored (text/pagestate.py PageState.state,
  -- ok|thin|blocked|missing|empty); kind is which wall it hit, i.e. which
  -- refetch strategy might help (PageState.kind, empty string stored as NULL).
  page_state    TEXT CHECK (page_state IS NULL OR page_state IN
                ('ok', 'thin', 'blocked', 'missing', 'empty')),
  -- 'too_large' (worker/fetch.py's PDF page/byte-size cap, 2026-09-19) is not
  -- a wall — nothing refused to serve the page — but it shares page_kind's
  -- "why is this not usable" job, so it lives in the same enum rather than a
  -- new column.
  page_kind     TEXT CHECK (page_kind IS NULL OR page_kind IN
                ('js', 'cookies', 'bot', 'forbidden', 'login', 'missing', 'shell',
                 'too_large')),
  words         INTEGER,
  http_status   INTEGER,
  fetched_at    TEXT,
  path          TEXT,          -- cached cleaned text on disk
  canonical_of  TEXT REFERENCES source (id),   -- set on the duplicate, not the survivor
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX source_canonical_ix ON source (url_canonical);
CREATE INDEX source_dup_ix ON source (canonical_of) WHERE canonical_of IS NOT NULL;

-- ------------------------------------------------------------------- edge ---
-- Typed, dated, evidenced. Endpoints are polymorphic, so referential integrity
-- is enforced by trigger below rather than by a foreign key.
CREATE TABLE edge (
  id         INTEGER PRIMARY KEY,
  src_kind   TEXT NOT NULL CHECK (src_kind IN ('problem', 'actor')),
  src_id     TEXT NOT NULL,
  dst_kind   TEXT NOT NULL CHECK (dst_kind IN ('problem', 'actor', 'source')),
  dst_id     TEXT NOT NULL,
  kind       TEXT NOT NULL CHECK (kind IN (
               'part_of',       -- problem  -> problem : src is a child of dst
               'member_of',     -- problem  -> problem : src belongs to node dst
               'works_on',      -- actor    -> problem
               'cites',         -- either   -> source
               'funds', 'board', 'cohort', 'convenes', 'portfolio',
               'affiliated',    -- individual -> org, evidence = role
               'parent_org',    -- actor    -> actor
               'superseded_by'  -- actor    -> actor
             )),
  -- 0 mentioned · 1 adjacent · 2 works it · 3 load-bearing.
  -- Gap derivation counts >= 2 only (01-minimal.md §3).
  relevance  INTEGER CHECK (relevance IS NULL OR relevance BETWEEN 0 AND 3),
  stance     TEXT CHECK (stance IS NULL OR stance IN ('works-the-remedy',
             'neutral', 'organised-against-remedy', 'ambiguous')),
  evidence   TEXT,
  source_id  TEXT REFERENCES source (id),
  as_of      TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (src_kind, src_id, dst_kind, dst_id, kind)
);

CREATE INDEX edge_in_ix  ON edge (dst_kind, dst_id, kind);
CREATE INDEX edge_out_ix ON edge (src_kind, src_id, kind);

CREATE TRIGGER edge_endpoints_ins BEFORE INSERT ON edge
BEGIN
  SELECT CASE
    WHEN NEW.src_kind = 'problem' AND NOT EXISTS
         (SELECT 1 FROM problem WHERE id = NEW.src_id)
      THEN RAISE(ABORT, 'edge.src_id: no such problem')
    WHEN NEW.src_kind = 'actor' AND NOT EXISTS
         (SELECT 1 FROM actor WHERE id = NEW.src_id)
      THEN RAISE(ABORT, 'edge.src_id: no such actor')
  END;
  SELECT CASE
    WHEN NEW.dst_kind = 'problem' AND NOT EXISTS
         (SELECT 1 FROM problem WHERE id = NEW.dst_id)
      THEN RAISE(ABORT, 'edge.dst_id: no such problem')
    WHEN NEW.dst_kind = 'actor' AND NOT EXISTS
         (SELECT 1 FROM actor WHERE id = NEW.dst_id)
      THEN RAISE(ABORT, 'edge.dst_id: no such actor')
    WHEN NEW.dst_kind = 'source' AND NOT EXISTS
         (SELECT 1 FROM source WHERE id = NEW.dst_id)
      THEN RAISE(ABORT, 'edge.dst_id: no such source')
  END;
  SELECT CASE
    WHEN NEW.src_kind = 'problem' AND NEW.dst_kind = 'problem'
         AND NEW.src_id = NEW.dst_id
      THEN RAISE(ABORT, 'edge: problem cannot parent itself')
  END;
END;

-- -------------------------------------------------------------------- tag ---
-- The view layer. tier / need / mechanism / onset / salience are tags, not
-- columns, which is what keeps the engine general-purpose rather than
-- instantiated on Maslow: the browse tree is a traversal, not a schema.
CREATE TABLE tag_ns (
  ns            TEXT PRIMARY KEY,
  applies_to    TEXT NOT NULL DEFAULT 'problem,actor',
  open          INTEGER NOT NULL DEFAULT 0 CHECK (open IN (0, 1)),
  required_when TEXT,          -- e.g. "status == researched"; advisory, checked by the validator
  note          TEXT
) WITHOUT ROWID;

CREATE TABLE tag_def (
  ns    TEXT NOT NULL REFERENCES tag_ns (ns),
  value TEXT NOT NULL,
  note  TEXT,
  PRIMARY KEY (ns, value)
) WITHOUT ROWID;

CREATE TABLE tag (
  entity_kind TEXT NOT NULL CHECK (entity_kind IN ('problem', 'actor')),
  entity_id   TEXT NOT NULL,
  ns          TEXT NOT NULL,
  value       TEXT NOT NULL,
  PRIMARY KEY (entity_kind, entity_id, ns, value)
) WITHOUT ROWID;

CREATE INDEX tag_lookup_ix ON tag (ns, value);

CREATE TRIGGER tag_validate_ins BEFORE INSERT ON tag
BEGIN
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM tag_ns WHERE ns = NEW.ns)
      THEN RAISE(ABORT, 'tag: unknown namespace')
    WHEN (SELECT open FROM tag_ns WHERE ns = NEW.ns) = 0
         AND NOT EXISTS (SELECT 1 FROM tag_def WHERE ns = NEW.ns AND value = NEW.value)
      THEN RAISE(ABORT, 'tag: value not in closed namespace')
    WHEN (SELECT applies_to FROM tag_ns WHERE ns = NEW.ns)
         NOT LIKE '%' || NEW.entity_kind || '%'
      THEN RAISE(ABORT, 'tag: namespace does not apply to this entity kind')
  END;
END;

-- ---------------------------------------------------------------- channel ---
CREATE TABLE channel (
  id           INTEGER PRIMARY KEY,
  actor_id     TEXT NOT NULL REFERENCES actor (id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,
  url          TEXT,
  handle       TEXT,
  status       TEXT NOT NULL DEFAULT 'unconfirmed' CHECK (status IN
               ('live', 'stale', 'dead', 'unconfirmed', 'none-found')),
  last_checked TEXT,
  UNIQUE (actor_id, kind, url, handle)
);

CREATE INDEX channel_actor_ix ON channel (actor_id);

-- -------------------------------------------------------------------- ask ---
-- needs and offers. One table, one direction column: a match query wants both
-- sides in the same shape.
CREATE TABLE ask (
  id        INTEGER PRIMARY KEY,
  actor_id  TEXT NOT NULL REFERENCES actor (id) ON DELETE CASCADE,
  direction TEXT NOT NULL CHECK (direction IN ('need', 'offer')),
  kind      TEXT NOT NULL,
  text      TEXT,
  as_of     TEXT,
  source    TEXT,
  state     TEXT CHECK (state IS NULL OR state IN
            ('open', 'partially-met', 'met', 'withdrawn', 'unknown'))
);

CREATE INDEX ask_actor_ix ON ask (actor_id, direction);
CREATE INDEX ask_match_ix ON ask (direction, kind);

-- -------------------------------------------------------- the autonomous loop
CREATE TABLE population (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  source_url  TEXT,
  total_rows  INTEGER,
  cursor      TEXT,
  last_swept  TEXT,
  done        INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1))
);

CREATE TABLE candidate (
  id             INTEGER PRIMARY KEY,
  kind           TEXT NOT NULL CHECK (kind IN ('problem', 'actor')),
  name           TEXT NOT NULL,
  url            TEXT,
  population_id  TEXT REFERENCES population (id),
  discovered_via TEXT,
  score          REAL,
  admitted       INTEGER CHECK (admitted IS NULL OR admitted IN (0, 1)),
  resolved_to    TEXT,         -- id in problem/actor once promoted
  dup_of         INTEGER REFERENCES candidate (id),
  evidence       TEXT,
  -- searched_at (schema v4, migrate/m0004_candidate_source.py): when the
  -- fetch+search+gate-2 stages last completed for this candidate. Not a
  -- timestamp for display — it is the resume flag. NULL means those stages
  -- have never run, so `candidate_source` holding no rows for this id is
  -- "not searched yet"; non-NULL means they ran and the source set below is
  -- complete, even when it is empty (a candidate whose every source was
  -- dropped is a real, reproducible outcome, not a missing cache).
  searched_at    TEXT,
  first_seen     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX candidate_queue_ix ON candidate (admitted, score DESC)
  WHERE admitted IS NULL;

-- ------------------------------------------------------- candidate_source ---
-- The resume point (05-worker-optimisations.md, "Handling failures instead
-- starting from scratch"). Extraction is the failure-prone stage and the one
-- worth retrying, but a retry used to redo the two stages above it: ~17
-- search families at a 2s throttle floor, then a local embedding pass per
-- fetched page. Half an hour, repaid to recover a call that costs seconds.
--
-- The page TEXT was never the missing piece — `source.path` has held it on
-- disk since E0. What died with `run_batch`'s frame was the *membership*:
-- which URLs search chose for THIS candidate, and what gate 2 said about
-- each. That is all this table stores; text is read back through `source`.
--
-- No text column, and no row per dropped source: a DROP is not part of the
-- set by definition, and `searched_at` above already distinguishes "searched,
-- found nothing" from "never searched".
CREATE TABLE candidate_source (
  candidate_id INTEGER NOT NULL REFERENCES candidate (id),
  source_id    TEXT NOT NULL REFERENCES source (id),
  url          TEXT NOT NULL,
  -- search/confirm_policy.py's vocabulary, verbatim — SEED/SEARCH and
  -- PROMPT/VERIFY. `route` is the field the worker branches on when it
  -- rebuilds the set: PROMPT sources go to the extraction prompt, VERIFY
  -- sources to the verify-and-extract pass, exactly as on the first run.
  origin       TEXT NOT NULL CHECK (origin IN ('seed', 'search')),
  route        TEXT NOT NULL CHECK (route IN ('prompt', 'verify')),
  -- gate 2's own verdict, so resuming never re-embeds. NULL is impossible
  -- for a routed source today (NO_VERDICT drops), but stays nullable rather
  -- than asserting a policy invariant in a storage constraint.
  verdict      TEXT CHECK (verdict IS NULL OR verdict IN ('confirmed', 'uncertain')),
  recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (candidate_id, source_id)
) WITHOUT ROWID;

-- ------------------------------------------------------- candidate_prompt ---
-- The second half of the resume point, and the larger half in wall clock.
--
-- `candidate_source` above gets a retry back to the same source set without
-- the network. It does NOT get it there without the encoder:
-- `worker/extract.py:assemble` still chunks every source and
-- `worker/passages.py:_rank_chunks` still encodes every chunk against every
-- retrieval question. That is strictly more embedding work than gate 2 does
-- (two vectors per source), and it loads the tokenizer besides
-- (`text/chunk.py:104`). Replaying whole text therefore skipped the cheap
-- embedding pass and kept the expensive one.
--
-- So the assembly output is stored too: the `[Sn]` blocks exactly as
-- `assemble` built them, per bucket — `prompt` for the main extraction call,
-- `verify` for §6a's second-opinion pass, which assembles its own set and
-- pays its own ranking. A resumed candidate reads these and goes straight to
-- prompt construction, loading the encoder only for `resolve`'s single
-- name vector.
--
-- `blocks` is a JSON array in label order. The LABEL ITSELF IS NOT STORED,
-- deliberately: `worker/extract_types.py` freezes "label is prompt-local,
-- `source_id` is durable", and persisting `S1` would break that. Labels are
-- re-derived as `S{i}` over the array on load, which reproduces the original
-- exactly because `assemble` assigns them by first appearance in this same
-- order.
--
-- Derived and disposable. Dropping every row costs one re-assembly, never a
-- fact — which is why the text is duplicated here without apology.
CREATE TABLE candidate_prompt (
  candidate_id INTEGER NOT NULL REFERENCES candidate (id),
  bucket       TEXT NOT NULL CHECK (bucket IN ('prompt', 'verify')),
  blocks       TEXT NOT NULL,   -- JSON: [{source_id, url, text, chunk_refs, chunk_texts}]
  -- `assemble`'s own counters (sources_fetched / in_prompt / never_selected
  -- / dropped_by_cap). Stored rather than recomputed so a resumed run's
  -- report reads identically to the run that built the set — E3's coverage
  -- counters are a regression detector, and a resume that silently reported
  -- zeroes would disarm it.
  coverage     TEXT,
  assembled_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (candidate_id, bucket)
) WITHOUT ROWID;

-- --------------------------------------------------- candidate_resolution ---
-- The last encoder call on a resumed candidate. `worker/resolve.py` tries the
-- free normalized alias match first and only pays an encode + kNN when that
-- misses — so this table does nothing for a `--force` refresh (the entity's
-- alias is already written, the match hits, no model loads). Where it does
-- bite is the escalation queue: an `ambiguous` candidate keeps
-- `resolved_to IS NULL`, so the CLI's queue re-selects it on every run, and
-- it paid a fresh encode + kNN every time to reach the same verdict.
--
-- Reuse is NOT blind, because this is the one cached stage whose correct
-- answer legitimately changes between runs — the graph gains entities, so a
-- candidate that was `new` an hour ago may match one now. Two guards, both
-- free, in `worker/worker.py:_load_resolution`: the alias match is re-run
-- first and a live hit beats the cached row, and a cached `entity_id` that
-- no longer exists falls through to a full resolve. Cleared with the source
-- set, since the embedding context is the seed text.
CREATE TABLE candidate_resolution (
  candidate_id INTEGER PRIMARY KEY REFERENCES candidate (id),
  decision     TEXT NOT NULL CHECK (decision IN
               ('exact', 'shortlist_top', 'ambiguous', 'new')),
  entity_id    TEXT,
  shortlist    TEXT,          -- JSON: [[entity_id, cosine], …]
  reason       TEXT,
  resolved_at  TEXT NOT NULL DEFAULT (datetime('now'))
) WITHOUT ROWID;

-- ---------------------------------------------------------------- finding ---
-- The dive loop's raw fact ledger (`worker/dive.py`, `worker/questions.py`) —
-- distinct from `claims`, which are only the final, resolved, one-value-per-
-- field writes. A `finding` is per (candidate, question, source): the model's
-- answer to one open question from one fetched page, kept even after
-- synthesis writes the final claim, so a later reviewer (or a refresh pass)
-- can see every source that spoke to a question and where they agreed or
-- disagreed — exactly the "sources disagree -> write the disagreement"
-- standard (CLAUDE.md), which a single overwritten claim value cannot show.
CREATE TABLE finding (
  id            INTEGER PRIMARY KEY,
  candidate_id  INTEGER NOT NULL REFERENCES candidate (id),
  question_id   TEXT NOT NULL,        -- key into worker/questions.py's Registry,
                                       -- loaded from engine/questions.yaml (F1)
  answer        TEXT NOT NULL,
  confidence    REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  source_url    TEXT,
  -- source_id/chunk_ref (schema v2, migrate/m0002_finding_provenance.py):
  -- close the gap 03-worker.md §9 names — source_url alone can't join a
  -- finding to the fetched page's fetched_at, or point a wrong answer back
  -- at the passage that produced it. Both nullable: pre-migration findings
  -- (there are none live) and any answer path that never resolves a source
  -- id still write. chunk_ref's format is frozen by text/chunk.py:93
  -- (`chunk_ref`) as f"{source_id}:{ordinal}" — not reconstructed here.
  source_id     TEXT REFERENCES source (id),
  chunk_ref     TEXT,
  -- reason (schema v3, migrate/m0003_finding_reason.py): the model's
  -- one-clause justification for a closed-enum classification answer
  -- (worker/extract_types.py's Answer.reason) — why this value over a
  -- neighbouring one, e.g. why `onset` is `chronic` and not `latent`.
  -- Nullable: only closed-enum classification answers carry a reason;
  -- everything else writes None.
  reason        TEXT,
  gathered_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX finding_candidate_ix ON finding (candidate_id, question_id);

-- ------------------------------------------------------------------ event ---
-- Provenance. Under autonomy git cannot do this job: nothing generates a
-- reviewed diff. Append-only, enforced.
CREATE TABLE event (
  id          INTEGER PRIMARY KEY,
  at          TEXT NOT NULL DEFAULT (datetime('now')),
  entity_kind TEXT NOT NULL,
  entity_id   TEXT NOT NULL,
  field       TEXT,
  old         TEXT,
  new         TEXT,
  by          TEXT NOT NULL,   -- 'migration' | 'human' | a pinned model id
  why         TEXT
);

CREATE INDEX event_entity_ix ON event (entity_kind, entity_id, at);

CREATE TRIGGER event_no_update BEFORE UPDATE ON event
BEGIN SELECT RAISE(ABORT, 'event is append-only'); END;

CREATE TRIGGER event_no_delete BEFORE DELETE ON event
BEGIN SELECT RAISE(ABORT, 'event is append-only'); END;

-- ------------------------------------------------------------------ views ---
-- Coverage is derived, never stored, so it cannot go stale. It is a FLOOR, not
-- the gap finding, and the difference was measured on migration day:
-- `crop-residue-burning` carries 25 enterprise actors and still records a
-- missing enterprise slot, because the empty slot is a shape inside the leg
-- ("aggregation finance that closes farm-gate economics in a 12-day window"),
-- not the leg. Nor is `representation` derivable — whether an actor sits at a
-- unit that can perceive the harm is a judgement, and 5 of the 7 migrated
-- leaves record exactly that.
--
-- So this view answers one cheap question honestly: which legs have nobody at
-- all. The recorded finding lives on as gap_kind / gap_missing_leg tags plus
-- problem.gap_note, and the two are not redundant.
--
-- Read the `service` leg with that caveat until it is backfilled: it entered
-- the taxonomy after the actor records were written, so 0 of 289 migrated
-- actors carry it and every leaf assigned all four legs reports it uncovered.
-- That is a gap in the corpus, not a finding about the world, and it is the
-- one leg whose uncovered count currently means nothing.
CREATE VIEW problem_leg AS
SELECT p.id AS problem_id,
       j.value AS leg,
       EXISTS (
         SELECT 1 FROM edge e
         JOIN actor a ON a.id = e.src_id
         WHERE e.src_kind = 'actor' AND e.dst_kind = 'problem'
           AND e.dst_id = p.id AND e.kind = 'works_on'
           AND e.relevance >= 2
           AND a.depth <> 'excluded'
           AND coalesce(e.stance, a.stance) <> 'organised-against-remedy'
           AND EXISTS (SELECT 1 FROM json_each(a.legs) l WHERE l.value = j.value)
       ) AS covered
FROM problem p, json_each(p.needs_legs) j
WHERE p.needs_legs IS NOT NULL;

CREATE VIEW problem_coverage AS
SELECT problem_id,
       count(*) - sum(covered) AS uncovered_count,
       json_group_array(leg) FILTER (WHERE covered = 0) AS uncovered_legs
FROM problem_leg
GROUP BY problem_id;

-- The browse tree, as a traversal rather than a schema.
CREATE VIEW problem_tree AS
WITH RECURSIVE walk(id, root, depth, path) AS (
  SELECT p.id, p.id, 0, p.id FROM problem p
   WHERE NOT EXISTS (SELECT 1 FROM edge e
                     WHERE e.src_kind = 'problem' AND e.src_id = p.id
                       AND e.kind = 'part_of')
  UNION ALL
  SELECT e.src_id, w.root, w.depth + 1, w.path || '/' || e.src_id
    FROM edge e JOIN walk w
      ON e.dst_kind = 'problem' AND e.dst_id = w.id AND e.kind = 'part_of'
   WHERE w.depth < 12
)
SELECT * FROM walk;
