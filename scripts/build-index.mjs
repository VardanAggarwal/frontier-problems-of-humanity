#!/usr/bin/env node
// Emit problems/index.db + problems/index.json — 03-portal.md §1.
//
// Two databases, deliberately. The WORK db holds everything, private records
// included, with foreign keys on: that is where referential integrity is
// enforced, and it is why connection records can reference leaf and actor ids
// and have the reference checked. The PUBLISHED db is built by selecting the
// public views into a fresh file, so private tables and `contact_route` are
// ABSENT from it rather than filtered out of it. A column that is never
// selected cannot leak; a WHERE clause can be forgotten.
import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { loadCorpus, ROOT } from '../src/lib/corpus.mjs';

const DRY = process.argv.includes('--dry-run');
const OUT_DB = path.join(ROOT, 'problems/index.db');
const OUT_JSON = path.join(ROOT, 'problems/index.json');

const c = loadCorpus();

// Fix 16a (catalyst-platform/04-readability-review.md PART 1 item 16) — a
// leaf's `gap:` frontmatter can contradict its own §C/§E prose and nothing
// catches it. Conservative heuristic, warning only: a claiming construction
// ("this is X, not Y") naming a gap enum value in the leaf's diagnosis/gap
// sections. False positives are worse than misses here, so this only fires
// on that specific construction, not on any mention of the enum values.
const GAP_CLAIM_RE = /\b(?:this|it)\s+is\s+`?(none|coverage|representation)`?\s*[,;]?\s*not\s+`?(none|coverage|representation)`?/gi;
for (const l of c.allLeaves) {
  if (!l.gap) continue;
  for (const s of l.sections ?? []) {
    if (!['gap', 'diagnosis'].includes(s.key)) continue;
    for (const m of s.markdown.matchAll(GAP_CLAIM_RE)) {
      const claimed = m[1].toLowerCase();
      if (claimed !== l.gap)
        c.warns.push(`${l.path}: section '${s.key}' argues "this is ${claimed}, not ${m[2].toLowerCase()}" against frontmatter gap: ${l.gap} (fix 16a)`);
    }
  }
}

// Fix 16b — "Numbers hygiene" as a heading or bold-lead hand-rolls what
// `Data note —` lines already do (sections.mjs lifts those into a numbered
// apparatus block). Warn wherever the literal still appears in a leaf, node
// or actor body so it gets converted.
const NUMBERS_HYGIENE_RE = /numbers hygiene/i;
for (const r of [...c.allLeaves, ...c.nodes, ...c.actors])
  for (const s of r.sections ?? [])
    if (NUMBERS_HYGIENE_RE.test(s.heading) || NUMBERS_HYGIENE_RE.test(s.markdown))
      c.warns.push(`${r.path}: "Numbers hygiene" found in section '${s.key ?? s.raw_key}' — convert to Data note — lines (fix 16b)`);

for (const w of c.warns) console.warn(`warn  ${w}`);
if (c.errors.length) {
  for (const e of c.errors) console.error(`ERROR ${e}`);
  console.error(`\n${c.errors.length} error(s) — nothing emitted.`);
  process.exit(1);
}

const SCHEMA = `
PRAGMA foreign_keys = ON;
CREATE TABLE record (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL
    CHECK (kind IN ('need','leaf','cc_leaf','actor','node','connection')),
  slug TEXT NOT NULL, path TEXT NOT NULL UNIQUE, url TEXT UNIQUE,
  private INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL, one_line TEXT, updated TEXT,
  UNIQUE (kind, slug)
);
CREATE TABLE alias (record_id INTEGER NOT NULL REFERENCES record(id),
                    slug TEXT NOT NULL, PRIMARY KEY (record_id, slug));
CREATE TABLE need (record_id INTEGER PRIMARY KEY REFERENCES record(id),
                   tier INTEGER NOT NULL, ord INTEGER NOT NULL,
                   definition TEXT NOT NULL, file TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE leaf (
  record_id INTEGER PRIMARY KEY REFERENCES record(id),
  need_id INTEGER REFERENCES record(id), axis TEXT,
  status TEXT NOT NULL CHECK (status IN ('stub','researched','stale')),
  tier INTEGER, geography TEXT, salience INTEGER, scale INTEGER,
  channel TEXT, satisfier_relation TEXT, onset TEXT, agent TEXT,
  gap TEXT CHECK (gap IN ('none','coverage','representation')),
  gap_missing_leg TEXT, gap_note TEXT, gap_as_of TEXT, last_reviewed TEXT,
  CHECK (status = 'stub' OR gap IS NOT NULL)
);
CREATE TABLE node (record_id INTEGER PRIMARY KEY REFERENCES record(id),
                   type TEXT NOT NULL, authority TEXT NOT NULL, geography TEXT,
                   sub_levers TEXT, status TEXT NOT NULL);
CREATE TABLE actor (
  record_id INTEGER PRIMARY KEY REFERENCES record(id),
  name TEXT NOT NULL, type TEXT, depth TEXT CHECK (depth IN ('registry','tracked')),
  legs TEXT, affected_led TEXT, representation_unit TEXT,
  stance TEXT CHECK (stance IN ('works-the-remedy','neutral','organised-against-remedy','ambiguous')),
  geography TEXT, lifecycle TEXT, lifecycle_as_of TEXT,
  parent_id INTEGER REFERENCES record(id), superseded_by_id INTEGER REFERENCES record(id),
  contact_route TEXT,          -- never in a published view's column list
  contact_channel_kind TEXT    -- derived; this is what publishes
);
CREATE TABLE actor_leaf (actor_id INT REFERENCES actor(record_id), leaf_id INT REFERENCES leaf(record_id), PRIMARY KEY (actor_id, leaf_id));
CREATE TABLE actor_node (actor_id INT REFERENCES actor(record_id), node_id INT REFERENCES node(record_id), PRIMARY KEY (actor_id, node_id));
CREATE TABLE leaf_node  (leaf_id INT REFERENCES leaf(record_id), node_id INT REFERENCES node(record_id), PRIMARY KEY (leaf_id, node_id));
CREATE TABLE leaf_lens  (leaf_id INT REFERENCES leaf(record_id), lens_kind TEXT, lens_id TEXT, PRIMARY KEY (leaf_id, lens_kind, lens_id));
CREATE TABLE node_need  (node_id INT REFERENCES node(record_id), need_id INT REFERENCES record(id), PRIMARY KEY (node_id, need_id));
CREATE TABLE section (record_id INTEGER REFERENCES record(id), key TEXT NOT NULL,
                      heading TEXT NOT NULL, ord INTEGER NOT NULL, markdown TEXT NOT NULL,
                      PRIMARY KEY (record_id, key));
CREATE TABLE ask (actor_id INTEGER REFERENCES actor(record_id),
                  side TEXT CHECK (side IN ('need','offer')), kind TEXT, text TEXT,
                  as_of TEXT, source_url TEXT, state TEXT,
                  CHECK (side <> 'need' OR source_url IS NOT NULL));
CREATE TABLE monitor_source (actor_id INTEGER REFERENCES actor(record_id), kind TEXT,
                             url TEXT, handle TEXT, status TEXT NOT NULL, last_checked TEXT);
CREATE TABLE update_log (actor_id INT REFERENCES actor(record_id), date TEXT, text TEXT, url TEXT);
CREATE TABLE connection (record_id INTEGER PRIMARY KEY REFERENCES record(id),
                         context_id INT REFERENCES record(id), gap_filled TEXT, hypothesis TEXT,
                         state TEXT, date_proposed TEXT, date_introduced TEXT, outcome TEXT);
CREATE TABLE connection_actor (connection_id INT REFERENCES connection(record_id),
                               actor_id INT REFERENCES actor(record_id),
                               PRIMARY KEY (connection_id, actor_id));

CREATE VIEW pub_record AS SELECT id, kind, slug, path, url, title, one_line, updated
                          FROM record WHERE private = 0;
CREATE VIEW pub_actor AS SELECT record_id, name, type, depth, legs, affected_led,
                                representation_unit, stance, geography, lifecycle,
                                lifecycle_as_of, parent_id, superseded_by_id,
                                contact_channel_kind
                         FROM actor;                       -- contact_route is not in the column list
CREATE VIEW pub_ask AS SELECT * FROM ask WHERE source_url IS NOT NULL;
`;

const db = new DatabaseSync(':memory:');
db.exec(SCHEMA);

const J = (v) => (v == null ? null : JSON.stringify(v));
const ins = (sql) => db.prepare(sql);
const rid = new Map();   // slug -> record.id
let nextId = 1;

const iRecord = ins('INSERT INTO record (id,kind,slug,path,url,private,title,one_line,updated) VALUES (?,?,?,?,?,?,?,?,?)');
const iAlias = ins('INSERT INTO alias (record_id,slug) VALUES (?,?)');
function addRecord(kind, slug, { path: p, url, private: priv = 0, title, one_line = null, updated = null, aliases = [] }) {
  const id = nextId++;
  iRecord.run(id, kind, slug, p, url ?? null, priv ? 1 : 0, title, one_line, updated);
  for (const a of aliases) iAlias.run(id, a);
  rid.set(slug, id);
  return id;
}

// needs first — leaves reference them
for (const n of c.needs)
  addRecord('need', n.id, { path: `problems/tier-failure-history/${n.file}`, url: n.url, title: n.title, one_line: n.definition, updated: null });
const iNeed = ins('INSERT INTO need (record_id,tier,ord,definition,file,status) VALUES (?,?,?,?,?,?)');
for (const n of c.needs) iNeed.run(rid.get(n.id), n.tier, n.order, n.definition, n.file, n.status);

for (const r of [...c.allLeaves, ...c.nodes, ...c.actors, ...c.connections])
  addRecord(r.kind, r.id, {
    path: r.path, url: r.url, private: r.private,
    title: r.title ?? r.name ?? r.id, one_line: r.one_line ?? null,
    updated: r.updated, aliases: r.aliases ?? [],
  });

const iLeaf = ins(`INSERT INTO leaf (record_id,need_id,axis,status,tier,geography,salience,scale,channel,
  satisfier_relation,onset,agent,gap,gap_missing_leg,gap_note,gap_as_of,last_reviewed)
  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`);
for (const l of c.allLeaves)
  iLeaf.run(rid.get(l.id), l.need ? rid.get(l.need) : null, l.axis ?? null, l.status,
    l.tier ?? null, J(l.geography), l.salience ?? null, l.scale ?? null, l.channel ?? null,
    l.satisfier_relation ?? null, l.onset ?? null, l.agent ?? null, l.gap ?? null,
    J(l.gap_missing_leg), l.gap_note ?? null, l.gap_as_of ?? null, l.last_reviewed ?? null);

const iNode = ins('INSERT INTO node (record_id,type,authority,geography,sub_levers,status) VALUES (?,?,?,?,?,?)');
const iNodeNeed = ins('INSERT INTO node_need (node_id,need_id) VALUES (?,?)');
for (const n of c.nodes) {
  iNode.run(rid.get(n.id), n.type, n.authority, J(n.geography), J(n.sub_levers), n.status);
  for (const nd of n.needs) iNodeNeed.run(rid.get(n.id), rid.get(nd));
}

const iActor = ins(`INSERT INTO actor (record_id,name,type,depth,legs,affected_led,representation_unit,
  stance,geography,lifecycle,lifecycle_as_of,parent_id,superseded_by_id,contact_route,contact_channel_kind)
  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`);
const iAsk = ins('INSERT INTO ask (actor_id,side,kind,text,as_of,source_url,state) VALUES (?,?,?,?,?,?,?)');
const iMon = ins('INSERT INTO monitor_source (actor_id,kind,url,handle,status,last_checked) VALUES (?,?,?,?,?,?)');
const iUpd = ins('INSERT INTO update_log (actor_id,date,text,url) VALUES (?,?,?,?)');
const channelKind = (route) => {
  if (!route) return null;
  const r = route.toLowerCase();
  if (r.includes('@') && !r.startsWith('http')) return 'email';
  if (r.includes('form')) return 'form';
  if (r.includes('twitter') || r.includes('x.com') || r.startsWith('@')) return 'social';
  if (r.startsWith('http')) return 'web';
  return 'other';
};
for (const a of c.actors) {
  const id = rid.get(a.id);
  iActor.run(id, a.name, a.type, a.depth, J(a.leg), a.affected_led, a.representation_unit,
    a.stance, J(a.geography), a.lifecycle, a.lifecycle_as_of,
    a.parent ? rid.get(a.parent) : null, a.superseded_by ? rid.get(a.superseded_by) : null,
    a.contact_route ?? null, channelKind(a.contact_route));
  // A published need row must carry a public URL — the publish predicate, as a
  // constraint. An unsourced ask stays in the markdown record and never reaches
  // the emitted file.
  for (const n of a.needs) {
    const url = /^https?:\/\//.test(n.source ?? '') ? n.source : null;
    if (!url) { console.warn(`warn  ${a.path}: unsourced need "${n.text?.slice(0, 40)}" — held back from the published DB (assertion 2)`); continue; }
    iAsk.run(id, 'need', n.kind, n.text, n.as_of ?? null, url, n.state ?? null);
  }
  for (const o of a.offers) iAsk.run(id, 'offer', o.kind, o.text, null, null, null);
  for (const s of a.sources) iMon.run(id, s.kind, s.url ?? null, s.handle ?? null, s.status, s.last_checked ?? null);
  const updates = (a.sections.find((s) => s.key === 'updates')?.markdown ?? '')
    .split('\n').map((l) => l.match(/^-\s*(\d{4}-\d{2}-\d{2})\s*—\s*(.*?)(?:\s*—\s*(\S+))?\s*$/)).filter(Boolean);
  for (const u of updates) iUpd.run(id, u[1], u[2], u[3] ?? null);
  for (const l of a.leaves) if (rid.has(l)) db.prepare('INSERT OR IGNORE INTO actor_leaf VALUES (?,?)').run(id, rid.get(l));
  for (const n of a.nodes) if (rid.has(n)) db.prepare('INSERT OR IGNORE INTO actor_node VALUES (?,?)').run(id, rid.get(n));
}

const iLeafNode = ins('INSERT OR IGNORE INTO leaf_node VALUES (?,?)');
const iLeafLens = ins('INSERT OR IGNORE INTO leaf_lens VALUES (?,?,?)');
for (const l of c.allLeaves) {
  for (const n of l.nodes) if (rid.has(n)) iLeafNode.run(rid.get(l.id), rid.get(n));
  for (const m of l.mechanisms) iLeafLens.run(rid.get(l.id), 'mechanism', m);
  for (const x of l.cross_cutting ?? []) iLeafLens.run(rid.get(l.id), 'axis', x);
  if (l.axis) iLeafLens.run(rid.get(l.id), 'axis', l.axis);
}

const iSection = ins('INSERT OR REPLACE INTO section (record_id,key,heading,ord,markdown) VALUES (?,?,?,?,?)');
for (const r of [...c.allLeaves, ...c.nodes, ...c.actors])
  for (const s of r.sections ?? [])
    if (s.key) iSection.run(rid.get(r.id), s.key, s.heading, s.ord, s.markdown);

const iConn = ins('INSERT INTO connection (record_id,context_id,gap_filled,hypothesis,state,date_proposed,date_introduced,outcome) VALUES (?,?,?,?,?,?,?,?)');
for (const cn of c.connections) {
  iConn.run(rid.get(cn.id), rid.get(cn.context) ?? null, cn.gap_filled, cn.hypothesis,
    cn.state, cn.date_proposed ?? null, cn.date_introduced ?? null, cn.outcome ?? null);
  for (const a of cn.actors) db.prepare('INSERT OR IGNORE INTO connection_actor VALUES (?,?)').run(rid.get(cn.id), rid.get(a));
}

// ---- publish -------------------------------------------------------------
if (DRY) {
  console.log(`\nvalidated: ${c.needs.length} needs · ${c.allLeaves.length} leaves · ${c.nodes.length} nodes · ${c.actors.length} actors · ${c.connections.length} connections (private)`);
  console.log(`${c.warns.length} warning(s), 0 errors. Nothing emitted (--dry-run).`);
  process.exit(0);
}

fs.rmSync(OUT_DB, { force: true });
db.exec(`ATTACH DATABASE '${OUT_DB.replace(/'/g, "''")}' AS pub`);
const PUBLIC_TABLES = ['need', 'leaf', 'node', 'node_need', 'actor_leaf', 'actor_node',
  'leaf_node', 'leaf_lens', 'section', 'monitor_source', 'update_log', 'alias'];
db.exec(`CREATE TABLE pub.record AS SELECT * FROM pub_record`);
db.exec(`CREATE TABLE pub.actor  AS SELECT * FROM pub_actor WHERE record_id IN (SELECT id FROM pub_record)`);
db.exec(`CREATE TABLE pub.ask    AS SELECT * FROM pub_ask   WHERE actor_id  IN (SELECT id FROM pub_record)`);
for (const t of PUBLIC_TABLES) {
  const idcol = ['need', 'leaf', 'node'].includes(t) ? 'record_id'
    : t === 'alias' ? 'record_id' : t === 'section' ? 'record_id'
    : t.startsWith('actor_') || t === 'monitor_source' || t === 'update_log' ? 'actor_id'
    : t.startsWith('leaf_') ? 'leaf_id' : 'node_id';
  db.exec(`CREATE TABLE pub.${t} AS SELECT * FROM main.${t} WHERE ${idcol} IN (SELECT id FROM pub_record)`);
}

// Assertion 1 + 3, checked against the emitted file rather than trusted.
const emitted = db.prepare(`SELECT name FROM pub.sqlite_master WHERE type='table'`).all().map((r) => r.name);
const leaked = emitted.filter((n) => ['connection', 'connection_actor'].includes(n));
if (leaked.length) { console.error(`ERROR private table(s) reached the emitted file: ${leaked}`); process.exit(1); }
db.exec('DETACH DATABASE pub');

const check = new DatabaseSync(OUT_DB, { readOnly: true });
const cols = check.prepare(`SELECT name FROM pragma_table_info('actor')`).all().map((r) => r.name);
if (cols.includes('contact_route')) { console.error('ERROR contact_route reached the published DB (assertion 3)'); process.exit(1); }
const tables = check.prepare(`SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`).all().map((r) => r.name);
const counts = Object.fromEntries(tables.map((t) => [t, check.prepare(`SELECT count(*) n FROM "${t}"`).get().n]));
check.close();

fs.writeFileSync(OUT_JSON, JSON.stringify({
  generated: new Date().toISOString().slice(0, 10),
  tiers: c.tiers,
  needs: c.needs.map(({ leaves, ...n }) => ({ ...n, leaves: leaves.map((l) => l.id) })),
  leaves: c.allLeaves.map(({ sections, lede, actors_touching, ...l }) => ({ ...l, actors: actors_touching.map((a) => a.id) })),
  nodes: c.nodes.map(({ sections, lede, leaves, actors_on_node, ...n }) => ({ ...n, leaves: leaves.map((l) => l.id), actors: actors_on_node.map((a) => a.id) })),
  actors: c.actors.map(({ sections, lede, contact_route, needs, ...a }) => ({
    ...a, needs: needs.filter((n) => /^https?:\/\//.test(n.source ?? '')),
  })),
  mechanisms: c.mechanisms.map(({ leaves, ...m }) => ({ ...m, leaves: leaves.map((l) => l.id) })),
  axes: c.axes.map(({ leaves, ...a }) => ({ ...a, leaves: leaves.map((l) => l.id) })),
}, null, 2) + '\n');

console.log(`\nemitted problems/index.db  (${tables.length} tables: ${tables.join(', ')})`);
console.log(`         problems/index.json`);
console.log(Object.entries(counts).filter(([, n]) => n).map(([t, n]) => `  ${t}: ${n}`).join('\n'));
console.log(`${c.warns.length} warning(s), 0 errors.`);
