import { defineConfig } from 'astro/config';
import { fileURLToPath } from 'node:url';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';

// The corpus lives in problems/, outside src/. It is loaded by src/lib/corpus.mjs
// at build time (plain node, no content collections), so the same loader serves
// the pages, scripts/build-index.mjs and `npm run validate` — one transcription
// of data-model.yaml, per 03-portal.md §1.

const CORPUS_DIR = fileURLToPath(new URL('./problems', import.meta.url));
// The loader chain: reading these with fs (not import) is why Vite can't see the
// corpus. Dropping them from the module graph forces loadCorpus() to re-run.
const LOADER_FILES = ['src/lib/corpus.mjs', 'src/lib/site.mjs', 'src/lib/sections.mjs', 'src/lib/schema.mjs']
  .map((p) => fileURLToPath(new URL(`./${p}`, import.meta.url)));

/** Dev-only. Watch problems/** explicitly and, on any .md/.yaml change,
 *  invalidate the loader modules and force a full page reload. */
function watchCorpus() {
  return {
    name: 'fph:watch-corpus',
    apply: 'serve',
    configureServer(server) {
      server.watcher.add(CORPUS_DIR);
      const bust = (file) => {
        if (!file.startsWith(CORPUS_DIR) || !/\.(md|ya?ml)$/.test(file)) return;
        for (const f of LOADER_FILES)
          for (const m of server.moduleGraph.getModulesByFile(f) ?? [])
            server.moduleGraph.invalidateModule(m);
        server.ws.send({ type: 'full-reload', path: '*' });
      };
      server.watcher.on('add', bust);
      server.watcher.on('change', bust);
      server.watcher.on('unlink', bust);
    },
  };
}

const ACTORS_DIR = fileURLToPath(new URL('./problems/actors', import.meta.url));
const today = () => new Date().toISOString().slice(0, 10);

/** Patch one key's value line inside the frontmatter block only. */
function setFm(fm, key, value) {
  const re = new RegExp(`^${key}:[ \\t]*.*$`, 'm');
  const line = `${key}: ${value}`.trimEnd();
  if (re.test(fm)) return fm.replace(re, line);
  if (value === '') return fm;
  return fm.replace(/^followed:.*$/m, (l) => `${l}\n${line}`);
}

/** Dev-only. POST /api/follow {slug, followed} → rewrites followed / followed_date
 *  / updated in problems/actors/<slug>.md. Never runs in the static build. */
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
            const file = `${ACTORS_DIR}/${slug}.md`;
            if (!existsSync(file)) return done(404, { error: 'no such actor' });
            const src = readFileSync(file, 'utf8');
            const m = src.match(/^(---\n[\s\S]*?\n)(---\n[\s\S]*)$/);
            if (!m) return done(500, { error: 'no frontmatter' });
            const d = today();
            let fm = setFm(m[1], 'followed', followed ? 'true' : 'false');
            fm = setFm(fm, 'followed_date', followed ? d : '');
            fm = setFm(fm, 'updated', d);
            writeFileSync(file, fm + m[2]);
            done(200, { ok: true, followed: !!followed, followed_date: followed ? d : null });
          } catch (e) {
            done(500, { error: String(e && e.message || e) });
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
  vite: { plugins: [watchCorpus(), followWriter()] },
});
