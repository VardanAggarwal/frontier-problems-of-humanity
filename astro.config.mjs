import { defineConfig } from 'astro/config';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
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
 *  excludes resolved rows by construction). */
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

          res.statusCode = 200;
          res.setHeader('content-type', 'text/plain; charset=utf-8');
          res.write(`$ ${PYTHON_BIN} ${args.join(' ')}\n(cwd: ${ENGINE_DIR})\n\n`);

          const child = spawn(PYTHON_BIN, args, { cwd: ENGINE_DIR });
          child.stdout.on('data', (c) => res.write(c));
          child.stderr.on('data', (c) => res.write(c));
          child.on('error', (e) => { res.write(`\n[spawn failed] ${e.message}\n`); res.end(); });
          child.on('close', (code) => {
            markSelfWrite(GRAPH_DB); // a run may have written claims/edges
            res.write(`\n[exit ${code}]\n`);
            res.end();
          });
          // `req`'s own 'close' fires as soon as its body is fully read (we
          // already consumed it above), well before the client disconnects —
          // watching it here killed every run instantly. `res`'s 'close'
          // firing while we're still mid-stream (writableEnded false) is the
          // real "client went away" signal.
          res.on('close', () => {
            if (!res.writableEnded && !child.killed) child.kill();
          });
        });
      });
    },
  };
}

/** Dev-only. POST /api/worker/rerun {kind, id, noSearch?} → finds every
 *  candidate row whose resolved_to is this entity, and re-runs worker.py
 *  against them with --force, streaming stdout/stderr exactly like
 *  /api/worker/run. Convenience for a leaf/actor page's "re-run through
 *  worker" button — the alternative is hunting the same candidate ids by
 *  hand on /worker. 404s with no process spawned when no candidate row
 *  resolves to this entity (a record created outside the worker, e.g. via
 *  /triage or process-leaf, has none — nothing for --force to reprocess). */
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
          let ids;
          try {
            ids = g.prepare(
              'SELECT id FROM candidate WHERE kind = ? AND resolved_to = ? ORDER BY first_seen'
            ).all(kind, id).map((r) => r.id);
          } finally { g.close(); }

          if (ids.length === 0) {
            res.statusCode = 404;
            return res.end(`no candidate row resolves to ${kind}/${id} — nothing to re-run (seed one from /worker instead)`);
          }

          const args = ['-m', 'worker.worker', '--db', GRAPH_DB, '--corpus', REPO_ROOT,
            '--ids', ids.join(','), '--force'];
          if (noSearch) args.push('--no-search');

          res.statusCode = 200;
          res.setHeader('content-type', 'text/plain; charset=utf-8');
          res.write(`$ ${PYTHON_BIN} ${args.join(' ')}\n(cwd: ${ENGINE_DIR})\n\n`);

          const child = spawn(PYTHON_BIN, args, { cwd: ENGINE_DIR });
          child.stdout.on('data', (c) => res.write(c));
          child.stderr.on('data', (c) => res.write(c));
          child.on('error', (e) => { res.write(`\n[spawn failed] ${e.message}\n`); res.end(); });
          child.on('close', (code) => {
            markSelfWrite(GRAPH_DB); // a run may have written claims/edges
            res.write(`\n[exit ${code}]\n`);
            res.end();
          });
          res.on('close', () => {
            if (!res.writableEnded && !child.killed) child.kill();
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
    workerRunner(), workerRerunEntity(), problemOrphanLister(), needsLister(), problemPromoter()] },
});
