import { defineConfig } from 'astro/config';
import { fileURLToPath } from 'node:url';
import { existsSync, mkdirSync, createWriteStream } from 'node:fs';
import { spawn } from 'node:child_process';
import { openGraphWritable, setActorFields, lastEventValue, tagWrite, linkEdge } from './src/lib/graphdb.mjs';

// The corpus lives in problems/, outside src/. It is loaded by src/lib/corpus.mjs
// at build time (plain node, no content collections), so the same loader serves
// the pages, scripts/build-index.mjs and `npm run validate` — one transcription
// of data-model.yaml, per 03-portal.md §1.

const CORPUS_DIR = fileURLToPath(new URL('./problems', import.meta.url));
// The loader chain: reading these with fs (not import) is why Vite can't see the
// corpus. Dropping them from the module graph forces loadCorpus() to re-run.
const LOADER_FILES = ['src/lib/corpus.mjs', 'src/lib/site.mjs', 'src/lib/sections.mjs', 'src/lib/schema.mjs']
  .map((p) => fileURLToPath(new URL(`./${p}`, import.meta.url)));

// Writes made by our own dev endpoints must not bounce the page: the tick would
// reload the browser and throw away the active filter. Record the path here so
// the watcher can still invalidate the corpus but skip the reload.
const SELF_WRITES = new Map();
function isSelfWrite(file) {
  const t = SELF_WRITES.get(file);
  return t !== undefined && Date.now() - t < 3000;
}
function markSelfWrite(file) {
  SELF_WRITES.set(file, Date.now());
}

/** Dev-only. Watch problems/** explicitly and, on any .md/.yaml/graph.db
 *  change, invalidate the loader modules and force a full page reload.
 *  graph.db is included since 01-minimal.md §11 item 3b-B: it is the data
 *  source now, not the .md frontmatter that used to trigger this. */
function watchCorpus() {
  return {
    name: 'fph:watch-corpus',
    apply: 'serve',
    configureServer(server) {
      server.watcher.add(CORPUS_DIR);
      const bust = (file) => {
        if (!file.startsWith(CORPUS_DIR) || !/\.(md|ya?ml)$|graph\.db$/.test(file)) return;
        // Always drop the cached corpus, so the next request re-reads from disk.
        for (const f of LOADER_FILES)
          for (const m of server.moduleGraph.getModulesByFile(f) ?? [])
            server.moduleGraph.invalidateModule(m);
        // …but a write we made ourselves must not bounce the browser: the page
        // already reflects it, and a reload would cost the active filter.
        if (isSelfWrite(file)) return;
        server.ws.send({ type: 'full-reload', path: '*' });
      };
      server.watcher.on('add', bust);
      server.watcher.on('change', bust);
      server.watcher.on('unlink', bust);
    },
  };
}

const GRAPH_DB = fileURLToPath(new URL('./problems/graph.db', import.meta.url));
const today = () => new Date().toISOString().slice(0, 10);

/** Dev-only. POST /api/follow {slug, followed} → sets followed / followed_date
 *  / updated on the actor row in graph.db. 01-minimal.md §11 item 3b-B: this
 *  used to patch frontmatter; the corpus no longer carries any, so this is a
 *  DB write like any other, through the same setActorFields as the CLI. */
function followWriter() {
  return {
    name: 'fph:follow-writer',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/follow', (req, res, next) => {
        if (req.method !== 'POST') return next();
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          const done = (code, obj) => {
            res.statusCode = code;
            res.setHeader('content-type', 'application/json');
            res.end(JSON.stringify(obj));
          };
          try {
            const { slug, followed } = JSON.parse(body || '{}');
            if (!/^[a-z0-9-]+$/.test(slug ?? '')) return done(400, { error: 'bad slug' });
            const d = today();
            const g = openGraphWritable(GRAPH_DB);
            try {
              const ok = setActorFields(g, slug, {
                followed: followed ? 1 : 0,
                followed_date: followed ? d : null,
                updated: d,
              }, { by: 'human:dev-follow-ui' });
              if (!ok) return done(404, { error: 'no such actor' });
            } finally { g.close(); }
            markSelfWrite(GRAPH_DB);
            done(200, { ok: true, followed: !!followed, followed_date: followed ? d : null });
          } catch (e) {
            done(500, { error: String(e && e.message || e) });
          }
        });
      });
    },
  };
}

/** Dev-only. POST /api/exclude {slug, excluded, why} → flips `depth` to
 *  `excluded` on the actor row (remembering the prior value via the `event`
 *  audit trail, not a markdown comment) or restores it. */
function excludeWriter() {
  return {
    name: 'fph:exclude-writer',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/exclude', (req, res, next) => {
        if (req.method !== 'POST') return next();
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          const done = (code, obj) => {
            res.statusCode = code;
            res.setHeader('content-type', 'application/json');
            res.end(JSON.stringify(obj));
          };
          try {
            const { slug, excluded = true, why } = JSON.parse(body || '{}');
            if (!/^[a-z0-9-]+$/.test(slug ?? '')) return done(400, { error: 'bad slug' });
            const d = today();
            const g = openGraphWritable(GRAPH_DB);
            let was;
            try {
              const row = g.prepare('SELECT depth FROM actor WHERE id = ?').get(slug);
              if (!row) return done(404, { error: 'no such actor' });
              was = row.depth;
              const nextDepth = excluded
                ? 'excluded'
                : (lastEventValue(g, 'actor', slug, 'depth') ?? 'registry');
              setActorFields(g, slug, { depth: nextDepth, updated: d },
                { by: 'human:dev-follow-ui', why: excluded ? (why || 'no reason given') : 'exclude undo' });
            } finally { g.close(); }
            markSelfWrite(GRAPH_DB);
            done(200, { ok: true, excluded: !!excluded, was });
          } catch (e) {
            done(500, { error: String((e && e.message) || e) });
          }
        });
      });
    },
  };
}

const REPO_ROOT = fileURLToPath(new URL('./', import.meta.url));
const ENGINE_DIR = fileURLToPath(new URL('./engine', import.meta.url));
const WORKER_RUNS_DIR = fileURLToPath(new URL('./engine/worker/runs', import.meta.url));
const PYTHON_BIN = ['./engine/.venv/bin/python', './engine/.venv312/bin/python']
  .map((p) => fileURLToPath(new URL(p, import.meta.url)))
  .find((p) => existsSync(p)) || 'python3';

/** Dev-only. POST /api/candidates/seed {kind, name, url?} → inserts a row into
 *  `candidate` (engine/store/schema.sql) with admitted = 1, so it lands on
 *  `worker.py`'s next-batch queue (`admitted = 1 AND resolved_to IS NULL`)
 *  same as any crawler/migration-sourced candidate. No `event` row: `db.put`
 *  only audits `problem`/`actor`, and a still-unresolved candidate isn't
 *  either yet. */
function candidateSeeder() {
  return {
    name: 'fph:candidate-seeder',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/candidates/seed', (req, res, next) => {
        if (req.method !== 'POST') return next();
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          const done = (code, obj) => {
            res.statusCode = code;
            res.setHeader('content-type', 'application/json');
            res.end(JSON.stringify(obj));
          };
          try {
            const { kind, name, url } = JSON.parse(body || '{}');
            if (kind !== 'problem' && kind !== 'actor') return done(400, { error: 'kind must be "problem" or "actor"' });
            const trimmed = (name ?? '').trim();
            if (!trimmed) return done(400, { error: 'name is required' });
            const g = openGraphWritable(GRAPH_DB);
            let id, queueDepth;
            try {
              const ins = g.prepare(
                'INSERT INTO candidate (kind, name, url, discovered_via, admitted) VALUES (?, ?, ?, ?, 1)'
              );
              const info = ins.run(kind, trimmed, (url ?? '').trim() || null, 'human:dev-seed-ui');
              id = info.lastInsertRowid;
              queueDepth = g.prepare(
                'SELECT COUNT(*) AS n FROM candidate WHERE admitted = 1 AND resolved_to IS NULL'
              ).get().n;
            } finally { g.close(); }
            markSelfWrite(GRAPH_DB);
            done(200, { ok: true, id: Number(id), queueDepth });
          } catch (e) {
            done(500, { error: String((e && e.message) || e) });
          }
        });
      });
    },
  };
}

/** Dev-only. GET /api/problems/orphans → `problem` rows with no `kind` tag —
 *  worker.py mints these (`_write_entity`/`_mint_or_resolve_problem`) but
 *  never tags them `leaf`/`need`/etc (engine/store/tags.py's REGISTRY makes
 *  `kind` a required-always, closed namespace; nothing in worker.py writes
 *  it), so they're invisible to corpus.mjs's `idsForKind(g, 'leaf')` and
 *  flagged as orphans by engine/store/db.py:validate(). This is the /triage
 *  page's input list. */
function problemOrphanLister() {
  return {
    name: 'fph:problem-orphan-lister',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/problems/orphans', (req, res, next) => {
        if (req.method !== 'GET') return next();
        const done = (code, obj) => {
          res.statusCode = code;
          res.setHeader('content-type', 'application/json');
          res.end(JSON.stringify(obj));
        };
        try {
          const g = openGraphWritable(GRAPH_DB);
          let rows;
          try {
            rows = g.prepare(`
              SELECT id, title, one_line, status, created_at FROM problem
              WHERE id NOT IN (SELECT entity_id FROM tag WHERE entity_kind = 'problem' AND ns = 'kind')
              ORDER BY created_at DESC LIMIT 300
            `).all();
          } finally { g.close(); }
          done(200, { ok: true, problems: rows });
        } catch (e) {
          done(500, { error: String((e && e.message) || e) });
        }
      });
    },
  };
}

/** Dev-only. GET /api/needs/list → every need id/title, for the /triage
 *  page's "which need does this belong under" picker. */
function needsLister() {
  return {
    name: 'fph:needs-lister',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/needs/list', (req, res, next) => {
        if (req.method !== 'GET') return next();
        const done = (code, obj) => {
          res.statusCode = code;
          res.setHeader('content-type', 'application/json');
          res.end(JSON.stringify(obj));
        };
        try {
          const g = openGraphWritable(GRAPH_DB);
          let rows;
          try {
            rows = g.prepare(`
              SELECT p.id, p.title FROM problem p
              JOIN tag t ON t.entity_kind = 'problem' AND t.entity_id = p.id
                AND t.ns = 'kind' AND t.value = 'need'
              ORDER BY p.title
            `).all();
          } finally { g.close(); }
          done(200, { ok: true, needs: rows });
        } catch (e) {
          done(500, { error: String((e && e.message) || e) });
        }
      });
    },
  };
}

/** Dev-only. POST /api/problems/promote {id, need, one_line?} → turns an
 *  orphaned problem row into a real leaf: tags it `kind: leaf`, tags it
 *  `need: <needId>`, and links a `part_of` edge to that need (the two things
 *  `idsForKind` and `db.py:validate()`'s orphan check respectively require).
 *  Refuses a row that already carries a `kind` tag — this only ever mints,
 *  never reclassifies. */
function problemPromoter() {
  return {
    name: 'fph:problem-promoter',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/problems/promote', (req, res, next) => {
        if (req.method !== 'POST') return next();
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          const done = (code, obj) => {
            res.statusCode = code;
            res.setHeader('content-type', 'application/json');
            res.end(JSON.stringify(obj));
          };
          try {
            const { id, need, one_line } = JSON.parse(body || '{}');
            if (!id || !need) return done(400, { error: 'id and need are required' });
            const g = openGraphWritable(GRAPH_DB);
            try {
              const row = g.prepare('SELECT id FROM problem WHERE id = ?').get(id);
              if (!row) return done(404, { error: 'no such problem row' });
              const already = g.prepare(
                "SELECT value FROM tag WHERE entity_kind = 'problem' AND entity_id = ? AND ns = 'kind'"
              ).get(id);
              if (already) return done(409, { error: `already tagged kind: ${already.value}` });
              const needRow = g.prepare('SELECT id FROM problem WHERE id = ?').get(need);
              if (!needRow) return done(400, { error: `no such need id: ${need}` });

              tagWrite(g, 'problem', id, 'kind', 'leaf', { by: 'human:dev-triage-ui' });
              tagWrite(g, 'problem', id, 'need', need, { by: 'human:dev-triage-ui' });
              linkEdge(g, ['problem', id], 'part_of', ['problem', need], { by: 'human:dev-triage-ui' });
              if (typeof one_line === 'string' && one_line.trim()) {
                g.prepare('UPDATE problem SET one_line = ?, updated = ? WHERE id = ?')
                  .run(one_line.trim(), today(), id);
              }
            } finally { g.close(); }
            markSelfWrite(GRAPH_DB);
            done(200, { ok: true, id, url: `/leaf/${id}` });
          } catch (e) {
            done(500, { error: String((e && e.message) || e) });
          }
        });
      });
    },
  };
}

/** Dev-only. GET /api/candidates/list?scope=queue|all → rows from `candidate`
 *  for the /worker page's picker. `queue` (default) is worker.py's own
 *  selection (admitted = 1 AND resolved_to IS NULL, oldest first) — the same
 *  set --limit would drain; `all` adds already-resolved/rejected rows too,
 *  for re-running or just seeing what happened to something. */
function candidateLister() {
  return {
    name: 'fph:candidate-lister',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/candidates/list', (req, res, next) => {
        if (req.method !== 'GET') return next();
        const done = (code, obj) => {
          res.statusCode = code;
          res.setHeader('content-type', 'application/json');
          res.end(JSON.stringify(obj));
        };
        try {
          const url = new URL(req.url, 'http://localhost');
          const scope = url.searchParams.get('scope') === 'all' ? 'all' : 'queue';
          // resolved_kind_tag: for a resolved problem, whatever 'kind' tag it
          // landed with (NULL until /triage promotes it, or for actors —
          // that tag namespace never applies to actor rows) — lets the
          // /worker page link straight to /leaf/<id> once it's a real leaf,
          // or to /triage while it's still an orphaned problem row.
          const cols = 'c.id, c.kind, c.name, c.url, c.admitted, c.resolved_to, c.score, c.first_seen, ' +
            "(SELECT value FROM tag WHERE entity_kind = 'problem' AND entity_id = c.resolved_to " +
            "AND ns = 'kind') AS resolved_kind_tag";
          const g = openGraphWritable(GRAPH_DB); // read-only use; avoids a second connection mode
          let rows;
          try {
            rows = scope === 'all'
              ? g.prepare(`SELECT ${cols} FROM candidate c ORDER BY first_seen DESC LIMIT 300`).all()
              : g.prepare(
                  `SELECT ${cols} FROM candidate c WHERE admitted = 1 AND resolved_to IS NULL ORDER BY first_seen`
                ).all();
          } finally { g.close(); }
          done(200, { ok: true, scope, candidates: rows });
        } catch (e) {
          done(500, { error: String((e && e.message) || e) });
        }
      });
    },
  };
}

/** Dev-only. POST /api/worker/run {ids?: number[], limit?, noSearch?, force?} →
 *  spawns `python -m worker.worker` (cwd engine/) against problems/graph.db
 *  and streams its stdout/stderr straight through as the process runs — a
 *  real batch does real fetches and real LLM calls, so the caller sees it
 *  happening rather than staring at a spinner for however long that takes.
 *  `ids` (from the picker) maps to worker.py's `--ids` and runs exactly
 *  those rows, ignoring `limit`; without `ids` it drains the oldest-first
 *  admitted queue up to `limit`, same as the CLI's default. `--no-search`
 *  maps to run_batch's seed-URL-only degrade (worker.py's
 *  `_build_search_provider`); omitting it requires a reachable SearXNG
 *  (`engine/poc/searxng/run.sh start`) or the batch raises immediately.
 *  `force` maps to worker.py's `--ids`-only `--force`: reprocesses ids that
 *  already have `resolved_to` set instead of skipping them (the CLI ignores
 *  `--force` without `--ids`, so it's silently dropped here too when `ids`
 *  is empty — nothing to force-rerun in the --limit queue, which already
 *  excludes resolved rows by construction).
 *
 *  The child OUTLIVES the HTTP connection. A reload/navigate away used to
 *  kill it (`res`'s 'close' firing mid-stream), which — because worker.py
 *  only commits per-candidate state at gate/settle checkpoints — could burn
 *  real LLM calls on a candidate and leave zero DB trace of them. Every run
 *  is teed to `engine/worker/runs/<timestamp>-<pid>.log` regardless of
 *  client connection, so a disconnected run is still inspectable and its
 *  candidates aren't silently re-queued as untouched. */
function workerRunner() {
  return {
    name: 'fph:worker-runner',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/worker/run', (req, res, next) => {
        if (req.method !== 'POST') return next();
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          let parsed;
          try { parsed = JSON.parse(body || '{}'); } catch (e) {
            res.statusCode = 400; return res.end('bad JSON body: ' + e.message);
          }
          const args = ['-m', 'worker.worker', '--db', GRAPH_DB, '--corpus', REPO_ROOT];
          const ids = Array.isArray(parsed.ids)
            ? parsed.ids.map(Number).filter(Number.isInteger)
            : [];
          if (ids.length) {
            args.push('--ids', ids.join(','));
            if (parsed.force) args.push('--force');
          } else {
            const limit = Number.isInteger(parsed.limit) && parsed.limit > 0 ? parsed.limit : 5;
            args.push('--limit', String(limit));
          }
          if (parsed.noSearch) args.push('--no-search');
          // Resume is the default (03-worker.md §13a): a candidate that has
          // already been searched re-enters at extraction. This is the
          // opt-out, for when the search stage's inputs changed.
          if (parsed.noResume) args.push('--no-resume');

          mkdirSync(WORKER_RUNS_DIR, { recursive: true });
          const stamp = new Date().toISOString().replace(/[:.]/g, '-');
          const child = spawn(PYTHON_BIN, args, { cwd: ENGINE_DIR });
          const logPath = `${WORKER_RUNS_DIR}/${stamp}-${child.pid}.log`;
          const logStream = createWriteStream(logPath);
          const header = `$ ${PYTHON_BIN} ${args.join(' ')}\n(cwd: ${ENGINE_DIR})\n(log: ${logPath})\n\n`;
          logStream.write(header);

          res.statusCode = 200;
          res.setHeader('content-type', 'text/plain; charset=utf-8');
          res.write(header);

          // Both the response (if still connected) and the on-disk log get
          // every chunk — the log is the one that survives a reload.
          child.stdout.on('data', (c) => { if (!res.writableEnded) res.write(c); logStream.write(c); });
          child.stderr.on('data', (c) => { if (!res.writableEnded) res.write(c); logStream.write(c); });
          child.on('error', (e) => {
            const msg = `\n[spawn failed] ${e.message}\n`;
            if (!res.writableEnded) res.write(msg);
            logStream.write(msg);
            if (!res.writableEnded) res.end();
            logStream.end();
          });
          child.on('close', (code) => {
            markSelfWrite(GRAPH_DB); // a run may have written claims/edges
            const footer = `\n[exit ${code}]\n`;
            if (!res.writableEnded) res.write(footer);
            logStream.write(footer);
            if (!res.writableEnded) res.end();
            logStream.end();
          });
          // Deliberately no res.on('close', () => child.kill()) — a
          // disconnect (reload/navigate) used to kill an in-flight batch,
          // wasting whatever LLM calls it had already made with no DB
          // commit to show for it (see the comment above the function). The
          // child now runs to completion regardless of whether anyone's
          // still watching; the log file above is how you check on it after
          // the fact, and the queue naturally reflects the outcome once it
          // finishes (resolved_to / admitted=0 / still-queued).
        });
      });
    },
  };
}

/** Dev-only. POST /api/worker/rerun {kind, id, noSearch?} → finds every
 *  candidate row whose resolved_to is this entity, and re-runs worker.py
 *  against them with --force --no-resume, streaming stdout/stderr exactly
 *  like /api/worker/run (log-teed to WORKER_RUNS_DIR, survives a
 *  disconnect, same reasoning as that function's own comment). --no-resume
 *  is always on, not a caller option: a deliberate re-run click means
 *  discard whatever stale search/gate-2 state resume-at-extraction would
 *  otherwise reuse, not compound it. Convenience for a leaf/actor page's
 *  "re-run through worker" button — the alternative is hunting the same
 *  candidate ids by hand on /worker.
 *
 *  When NO candidate resolves to this entity — a record minted outside the
 *  worker (process-leaf, /triage, a hand-written actor file) has none —
 *  one is seeded instead of refusing: `INSERT INTO candidate` with
 *  `kind`/`name = <the entity's own id>`/`admitted = 1`. `name` is
 *  deliberately the id, not the title: `worker/resolve.py:resolve_entity`
 *  tries `store/db.py:resolve` FIRST, and that function's first check is a
 *  literal `SELECT id FROM <table> WHERE id = ?` against whatever name it's
 *  given — so passing the id itself is an exact primary-key hit,
 *  independent of title drift, alias-table gaps or the embedding
 *  shortlist's cosine noise (fuzzy match is a fallback ONLY on a miss, per
 *  that module's docstring). This is the one case where the row does not
 *  need `--force`: it starts with `resolved_to` NULL, so run_batch takes
 *  its normal first-time path, and `_write_entity`'s `exact`/`shortlist_top`
 *  branches both write matched columns onto the existing row rather than
 *  minting a duplicate. */
function workerRerunEntity() {
  return {
    name: 'fph:worker-rerun-entity',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/worker/rerun', (req, res, next) => {
        if (req.method !== 'POST') return next();
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          let parsed;
          try { parsed = JSON.parse(body || '{}'); } catch (e) {
            res.statusCode = 400; return res.end('bad JSON body: ' + e.message);
          }
          const { kind, id, noSearch } = parsed;
          if (kind !== 'problem' && kind !== 'actor') {
            res.statusCode = 400; return res.end('kind must be "problem" or "actor"');
          }
          if (!id) { res.statusCode = 400; return res.end('id is required'); }

          const g = openGraphWritable(GRAPH_DB);
          let ids, seeded = false, force = true;
          try {
            ids = g.prepare(
              'SELECT id FROM candidate WHERE kind = ? AND resolved_to = ? ORDER BY first_seen'
            ).all(kind, id).map((r) => r.id);

            if (ids.length === 0) {
              const table = kind; // validated above to 'problem' | 'actor'
              const entity = g.prepare(`SELECT id, title, one_line FROM ${table} WHERE id = ?`).get(id);
              if (!entity) {
                res.statusCode = 404;
                return res.end(`no such ${kind}: ${id}`);
              }
              const ins = g.prepare(
                'INSERT INTO candidate (kind, name, url, discovered_via, evidence, admitted) '
                + 'VALUES (?, ?, NULL, ?, ?, 1)'
              );
              const info = ins.run(kind, entity.id, 'human:dev-rerun-ui', entity.one_line || entity.title || '');
              ids = [Number(info.lastInsertRowid)];
              seeded = true;
              force = false; // fresh row, resolved_to already NULL — nothing to force past
            }
          } finally { g.close(); }

          const args = ['-m', 'worker.worker', '--db', GRAPH_DB, '--corpus', REPO_ROOT, '--ids', ids.join(',')];
          if (force) args.push('--force');
          if (noSearch) args.push('--no-search');
          // Always, not conditionally: resume-at-extraction (worker.py's
          // default, 03-worker.md §13a) skips straight past search/gate 2
          // for a candidate that was already searched — exactly the stale
          // state a deliberate "re-run through worker" click means to
          // discard. --no-search still short-circuits the search stage
          // entirely when both are set; the two aren't mutually exclusive.
          args.push('--no-resume');

          mkdirSync(WORKER_RUNS_DIR, { recursive: true });
          const stamp = new Date().toISOString().replace(/[:.]/g, '-');
          const child = spawn(PYTHON_BIN, args, { cwd: ENGINE_DIR });
          const logPath = `${WORKER_RUNS_DIR}/${stamp}-${child.pid}.log`;
          const logStream = createWriteStream(logPath);
          const header = (seeded
            ? `seeded candidate #${ids[0]} for ${kind}/${id} (name=${id}, no prior candidate row)\n`
            : `re-running ${ids.length} existing candidate(s) resolved to ${kind}/${id}: ${ids.join(', ')}\n`)
            + `$ ${PYTHON_BIN} ${args.join(' ')}\n(cwd: ${ENGINE_DIR})\n(log: ${logPath})\n\n`;
          logStream.write(header);

          res.statusCode = 200;
          res.setHeader('content-type', 'text/plain; charset=utf-8');
          res.write(header);

          child.stdout.on('data', (c) => { if (!res.writableEnded) res.write(c); logStream.write(c); });
          child.stderr.on('data', (c) => { if (!res.writableEnded) res.write(c); logStream.write(c); });
          child.on('error', (e) => {
            const msg = `\n[spawn failed] ${e.message}\n`;
            if (!res.writableEnded) res.write(msg);
            logStream.write(msg);
            if (!res.writableEnded) res.end();
            logStream.end();
          });
          child.on('close', (code) => {
            markSelfWrite(GRAPH_DB); // a run may have written claims/edges
            // Verify the seed actually landed back on THIS entity — the
            // exact-id-match guarantee holds for `resolve_entity`, but a
            // catastrophic write failure (`_write_entity`'s `_safe_put`
            // fallback) or an LLM/extraction error that skips the candidate
            // entirely could still leave `resolved_to` NULL. Surface that
            // rather than let the button silently claim success.
            let verify = '';
            try {
              const g2 = openGraphWritable(GRAPH_DB);
              try {
                const row = g2.prepare('SELECT resolved_to, admitted FROM candidate WHERE id = ?').get(ids[0]);
                if (row && row.resolved_to === id) verify = `\n[verified] candidate #${ids[0]} resolved_to ${id} ✓\n`;
                else if (row) verify = `\n[check] candidate #${ids[0]} resolved_to=${row.resolved_to ?? 'NULL'} admitted=${row.admitted ?? 'NULL'} (expected resolved_to=${id}) — see /worker\n`;
              } finally { g2.close(); }
            } catch { /* best-effort — don't let the verify step mask the run's own exit code */ }
            const footer = `\n[exit ${code}]\n` + verify;
            if (!res.writableEnded) res.write(footer);
            logStream.write(footer);
            if (!res.writableEnded) res.end();
            logStream.end();
          });
        });
      });
    },
  };
}

/** Dev-only. GET /api/candidates/pool?kind=problem|actor&limit=50 → the
 *  UPSTREAM discovery pool, which is a different population from
 *  `candidateLister`'s queue: `admitted IS NULL` (never promoted) rather than
 *  `admitted = 1 AND resolved_to IS NULL` (promoted, awaiting the deep dive).
 *  Duplicates (`dup_of` set) are excluded outright — that is the whole point
 *  of the dedup pass, and showing both copies of a row is what the pass
 *  exists to stop.
 *
 *  `cluster_size` is 1 + however many rows point their `dup_of` at this one,
 *  so a representative shows what it stands for. It reads 1 for everything
 *  until the dedup pass has actually run and written `dup_of`.
 *
 *  ONE QUERY PER KIND, each with its own LIMIT — never a single combined
 *  query capped across both kinds and split afterwards. Actor rows outnumber
 *  problem rows roughly 3:1 here and score higher on average, so a shared cap
 *  would crowd problems out of the list before the kinds were ever separated.
 *  A kind's `total` is counted unfiltered by the cap, so the page can say how
 *  much it is not showing.
 *
 *  `score` is NULL for anything the scoring pass has not seen (never run, or
 *  the row arrived after the last run). Those sort last rather than erroring
 *  or being dropped: unscored is a state worth seeing. */
function candidatePoolLister() {
  return {
    name: 'fph:candidate-pool-lister',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/candidates/pool', (req, res, next) => {
        if (req.method !== 'GET') return next();
        const done = (code, obj) => {
          res.statusCode = code;
          res.setHeader('content-type', 'application/json');
          res.end(JSON.stringify(obj));
        };
        try {
          const url = new URL(req.url, 'http://localhost');
          const asked = url.searchParams.get('kind');
          const kinds = (asked === 'problem' || asked === 'actor') ? [asked] : ['problem', 'actor'];
          const limit = Math.min(500, Math.max(1, Number(url.searchParams.get('limit')) || 50));
          const g = openGraphWritable(GRAPH_DB); // read-only use; avoids a second connection mode
          const pools = {};
          try {
            const rows = g.prepare(
              'SELECT c.id, c.kind, c.name, c.score, c.first_seen, ' +
              '1 + (SELECT COUNT(*) FROM candidate d WHERE d.dup_of = c.id) AS cluster_size ' +
              'FROM candidate c ' +
              'WHERE c.kind = ? AND c.admitted IS NULL AND c.dup_of IS NULL ' +
              'ORDER BY c.score IS NULL, c.score DESC, c.first_seen LIMIT ?'
            );
            const total = g.prepare(
              'SELECT COUNT(*) AS n FROM candidate WHERE kind = ? AND admitted IS NULL AND dup_of IS NULL'
            );
            for (const kind of kinds) {
              pools[kind] = { rows: rows.all(kind, limit), total: total.get(kind).n };
            }
          } finally { g.close(); }
          done(200, { ok: true, limit, pools });
        } catch (e) {
          done(500, { error: String((e && e.message) || e) });
        }
      });
    },
  };
}

/** Dev-only. POST /api/candidates/dedup-score → runs
 *  `python -m worker.dedup_candidates` and then
 *  `python -m worker.score_candidates` over problems/graph.db, in that order,
 *  streaming both processes' output through one response.
 *
 *  Order is load-bearing, not cosmetic. `score_candidates` scores one row per
 *  dedup cluster and its D term counts distinct `discovered_via` across a
 *  cluster's members, so running it first would rank a pool it has not yet
 *  collapsed. (It calls `dedup_candidates.compute_clusters` itself, so it is
 *  correct either way — but only dedup writes `dup_of`, and this endpoint's
 *  whole job is to leave the store in a state the pool list can read.)
 *
 *  Both scripts write by default; `--dry-run` is their opt-in preview and is
 *  deliberately NOT passed here. Unlike `/api/worker/run` this makes no
 *  network calls and no LLM calls — it is local and cheap (one sentence-
 *  transformer encode over the pool) — but it is a real write to `dup_of` and
 *  `score`. If dedup exits non-zero, scoring is skipped rather than run
 *  against a half-deduped pool. */
function dedupScoreRunner() {
  return {
    name: 'fph:dedup-score-runner',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/candidates/dedup-score', (req, res, next) => {
        if (req.method !== 'POST') return next();
        let body = '';
        req.on('data', (c) => (body += c));
        req.on('end', () => {
          try { JSON.parse(body || '{}'); } catch (e) {
            res.statusCode = 400; return res.end('bad JSON body: ' + e.message);
          }
          const steps = [
            ['dedup', ['-m', 'worker.dedup_candidates', '--db', GRAPH_DB, '--corpus', REPO_ROOT]],
            ['score', ['-m', 'worker.score_candidates', '--db', GRAPH_DB, '--corpus', REPO_ROOT]],
          ];

          res.statusCode = 200;
          res.setHeader('content-type', 'text/plain; charset=utf-8');

          let child = null;
          let aborted = false;
          const finish = () => {
            if (res.writableEnded) return;
            markSelfWrite(GRAPH_DB); // dup_of / score / event rows just landed
            res.end();
          };
          const runStep = (i) => {
            if (aborted || res.writableEnded) return;
            if (i >= steps.length) return finish();
            const [label, args] = steps[i];
            res.write(`=== ${label} ===\n$ ${PYTHON_BIN} ${args.join(' ')}\n(cwd: ${ENGINE_DIR})\n\n`);
            child = spawn(PYTHON_BIN, args, { cwd: ENGINE_DIR });
            child.stdout.on('data', (c) => res.write(c));
            child.stderr.on('data', (c) => res.write(c));
            child.on('error', (e) => { res.write(`\n[spawn failed] ${e.message}\n`); finish(); });
            child.on('close', (code) => {
              if (aborted || res.writableEnded) return;
              res.write(`\n[${label} exit ${code}]\n\n`);
              if (code !== 0) {
                res.write(`[stopped — ${label} did not exit clean, later steps skipped]\n`);
                return finish();
              }
              runStep(i + 1);
            });
          };
          runStep(0);
          // Same reasoning as workerRunner: `req`'s 'close' fires once its
          // body is read, not when the client goes away. `res` closing
          // mid-stream is the real disconnect.
          res.on('close', () => {
            if (!res.writableEnded) {
              aborted = true;
              if (child && !child.killed) child.kill();
            }
          });
        });
      });
    },
  };
}

export default defineConfig({
  site: 'https://frontier-problems.example',
  outDir: './dist',
  build: { format: 'directory' },
  markdown: { syntaxHighlight: false },
  vite: { plugins: [watchCorpus(), followWriter(), excludeWriter(), candidateSeeder(), candidateLister(),
    candidatePoolLister(), dedupScoreRunner(),
    workerRunner(), workerRerunEntity(), problemOrphanLister(), needsLister(), problemPromoter()] },
});
