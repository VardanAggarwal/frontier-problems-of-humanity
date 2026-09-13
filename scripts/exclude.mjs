#!/usr/bin/env node
// Mark someone irrelevant — out of the follow list, never researched again.
//
//   npm run exclude -- <slug> "why"        an existing record  -> depth: excluded
//   npm run exclude -- "Some Name" "why"   a name with no record -> _excluded.yaml
//   npm run exclude -- --list              show everything currently excluded
//
// Run `npm run follow` afterwards to regenerate the list.
//
// 01-minimal.md §11 item 3b-B: the existing-record branch used to patch
// frontmatter directly; graph.db is the only place `depth` lives now, so it
// goes through the same setActorFields the dev /api/exclude route uses —
// one write path, not two conventions for the same field.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { parse } from 'yaml';
import { openGraphWritable, setActorFields } from '../src/lib/graphdb.mjs';

const ROOT = new URL('..', import.meta.url).pathname;
const DIR = join(ROOT, 'problems/actors');
const YML = join(DIR, '_excluded.yaml');
const GRAPH_DB = join(ROOT, 'problems/graph.db');
const today = new Date().toISOString().slice(0, 10);
const [target, ...rest] = process.argv.slice(2);
const why = rest.join(' ').trim();

const readYml = () => (existsSync(YML) ? parse(readFileSync(YML, 'utf8')) ?? {} : {});

if (!target || target === '--list') {
  const names = (readYml().excluded ?? []).map((e) => `  ${e.name} — ${e.why}`);
  const g = openGraphWritable(GRAPH_DB);
  let recs;
  try {
    recs = g.prepare("SELECT id FROM actor WHERE depth = 'excluded'").all()
      .map((r) => `  ${r.id} (record)`);
  } finally { g.close(); }
  console.log(`excluded names (${names.length}):\n${names.join('\n') || '  none'}`);
  console.log(`excluded records (${recs.length}):\n${recs.join('\n') || '  none'}`);
  process.exit(0);
}
if (!why) { console.error('a reason is required: npm run exclude -- <slug|name> "why"'); process.exit(1); }

const g = openGraphWritable(GRAPH_DB);
let row;
try {
  row = g.prepare('SELECT depth FROM actor WHERE id = ?').get(target);
  if (row) {
    if (row.depth === 'excluded') { console.log(`${target}: already excluded`); process.exit(0); }
    setActorFields(g, target, { depth: 'excluded', updated: today },
      { by: 'human:exclude-cli', why });
    console.log(`${target}: depth -> excluded. Run \`npm run follow\`.`);
  }
} finally { g.close(); }

if (!row) {
  const y = readYml();
  const list = y.excluded ?? [];
  if (list.some((e) => e.name?.toLowerCase() === target.toLowerCase()))
    { console.log(`"${target}": already on the exclusion list`); process.exit(0); }
  const row2 = `  - name: ${target}\n    why: ${why}\n    as_of: ${today}\n`;
  const src = readFileSync(YML, 'utf8').trimEnd();
  writeFileSync(YML, `${src}\n${row2}`);
  console.log(`"${target}": added to _excluded.yaml. No record exists, so nothing else to do.`);
}
