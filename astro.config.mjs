import { defineConfig } from 'astro/config';
import { fileURLToPath } from 'node:url';
import { openGraphWritable, setActorFields, lastEventValue } from './src/lib/graphdb.mjs';

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

export default defineConfig({
  site: 'https://frontier-problems.example',
  outDir: './dist',
  build: { format: 'directory' },
  markdown: { syntaxHighlight: false },
  vite: { plugins: [watchCorpus(), followWriter(), excludeWriter()] },
});
