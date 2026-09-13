// Read-only query primitives over problems/graph.db (engine/store/schema.sql).
//
// 01-minimal.md §11 item 3b-A: corpus.mjs's "frontmatter half" is replaced by
// queries against this store — engine/migrate/from_corpus.py is now the sole
// parser of needs/leaves/nodes/actors frontmatter. Prose (sections, lede)
// still comes from disk, read through `doc` — this module never reads
// markdown, only the engine's structured graph.
import { DatabaseSync } from 'node:sqlite';

export function openGraph(dbPath) {
  return new DatabaseSync(dbPath, { readOnly: true });
}

// Writable handle — 01-minimal.md §11 item 3b-B. Actor `depth`/`followed`
// flip on the dev-only /follow and /exclude routes (astro.config.mjs), and
// on `npm run exclude`, mirror engine/store/db.py's `put`: only changed
// columns are written, and each one gets an `event` row, so a JS-side edit
// carries the same audit trail as a Python-side one (there is one `event`
// table, not two conventions for it).
export function openGraphWritable(dbPath) {
  return new DatabaseSync(dbPath);
}

export function setActorFields(g, id, fields, { by, why = null }) {
  const before = g.prepare('SELECT * FROM actor WHERE id = ?').get(id);
  if (!before) return false;
  const changed = Object.entries(fields).filter(([k, v]) => before[k] !== v);
  if (!changed.length) return true;
  const assignments = changed.map(([k]) => `${k} = ?`).join(', ');
  g.prepare(`UPDATE actor SET ${assignments} WHERE id = ?`).run(...changed.map(([, v]) => v), id);
  const ins = g.prepare(
    'INSERT INTO event (entity_kind, entity_id, field, old, new, by, why) VALUES (?, ?, ?, ?, ?, ?, ?)'
  );
  for (const [k, v] of changed) ins.run('actor', id, k, before[k] ?? null, v ?? null, by, why);
  return true;
}

// Most recent prior value of a column, from the audit trail — used to
// restore `depth` on an exclude undo without a markdown-comment hack.
export function lastEventValue(g, entityKind, id, field) {
  const row = g.prepare(
    'SELECT old FROM event WHERE entity_kind = ? AND entity_id = ? AND field = ? ' +
    'ORDER BY id DESC LIMIT 1'
  ).get(entityKind, id, field);
  return row ? row.old : undefined;
}

export function idsForKind(g, kind) {
  return g.prepare(
    "SELECT entity_id FROM tag WHERE entity_kind = 'problem' AND ns = 'kind' AND value = ?"
  ).all(kind).map((r) => r.entity_id);
}

export function tagValues(g, entityKind, id, ns) {
  return g.prepare(
    'SELECT value FROM tag WHERE entity_kind = ? AND entity_id = ? AND ns = ?'
  ).all(entityKind, id, ns).map((r) => r.value);
}

export function tagValue(g, entityKind, id, ns) {
  const v = tagValues(g, entityKind, id, ns);
  return v.length ? v[0] : undefined;
}

// Every alias EXCEPT the auto-inserted title/name alias the migration always
// writes alongside real `aliases:` / `aka:` entries (from_corpus.py's
// `db.alias(conn, kind, id, data.get("title") or id, by=BY)`).
export function aliasesOf(g, entityKind, id, title) {
  return g.prepare(
    'SELECT alias FROM alias WHERE entity_kind = ? AND entity_id = ? AND alias <> ?'
  ).all(entityKind, id, title ?? '').map((r) => r.alias);
}

export function jsonArr(v) {
  if (v == null) return [];
  try { const a = JSON.parse(v); return Array.isArray(a) ? a : []; } catch { return []; }
}

export function edgesOut(g, srcKind, srcId, kind) {
  return g.prepare(
    'SELECT dst_kind, dst_id, relevance, stance, evidence, as_of FROM edge ' +
    'WHERE src_kind = ? AND src_id = ? AND kind = ?'
  ).all(srcKind, srcId, kind);
}

export function edgesIn(g, dstKind, dstId, kind) {
  return g.prepare(
    'SELECT src_kind, src_id, relevance, stance, evidence, as_of FROM edge ' +
    'WHERE dst_kind = ? AND dst_id = ? AND kind = ?'
  ).all(dstKind, dstId, kind);
}
