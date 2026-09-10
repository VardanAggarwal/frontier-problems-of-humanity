#!/usr/bin/env node
// Mark someone irrelevant — out of the follow list, never researched again.
//
//   npm run exclude -- <slug> "why"        an existing record  -> depth: excluded
//   npm run exclude -- "Some Name" "why"   a name with no record -> _excluded.yaml
//   npm run exclude -- --list              show everything currently excluded
//
// Run `npm run follow` afterwards to regenerate the list.
import { readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { parse } from 'yaml';

const ROOT = new URL('..', import.meta.url).pathname;
const DIR = join(ROOT, 'problems/actors');
const YML = join(DIR, '_excluded.yaml');
const today = new Date().toISOString().slice(0, 10);
const [target, ...rest] = process.argv.slice(2);
const why = rest.join(' ').trim();

const readYml = () => (existsSync(YML) ? parse(readFileSync(YML, 'utf8')) ?? {} : {});

if (!target || target === '--list') {
  const names = (readYml().excluded ?? []).map((e) => `  ${e.name} — ${e.why}`);
  const recs = readdirSync(DIR).filter((f) => f.endsWith('.md') && !f.startsWith('_'))
    .filter((f) => /^depth:\s*excluded\s*$/m.test(readFileSync(join(DIR, f), 'utf8')))
    .map((f) => `  ${f.slice(0, -3)} (record)`);
  console.log(`excluded names (${names.length}):\n${names.join('\n') || '  none'}`);
  console.log(`excluded records (${recs.length}):\n${recs.join('\n') || '  none'}`);
  process.exit(0);
}
if (!why) { console.error('a reason is required: npm run exclude -- <slug|name> "why"'); process.exit(1); }

const file = join(DIR, `${target}.md`);
if (existsSync(file)) {
  const src = readFileSync(file, 'utf8');
  const m = src.match(/^(---\n[\s\S]*?\n)(---\n[\s\S]*)$/);
  if (!m) { console.error(`${target}: no frontmatter`); process.exit(1); }
  if (/^depth:\s*excluded\s*$/m.test(m[1])) { console.log(`${target}: already excluded`); process.exit(0); }
  const fm = m[1].replace(/^depth:.*$/m, 'depth: excluded')
                 .replace(/^updated:.*$/m, `updated: ${today}`);
  const note = `\n<!-- excluded ${today} — ${why}\n     Out of the follow list and out of the crawl. Record and edges kept. -->\n`;
  writeFileSync(file, fm + m[2].trimEnd() + '\n' + note);
  console.log(`${target}: depth -> excluded. Run \`npm run follow\`.`);
} else {
  const y = readYml();
  const list = y.excluded ?? [];
  if (list.some((e) => e.name?.toLowerCase() === target.toLowerCase()))
    { console.log(`"${target}": already on the exclusion list`); process.exit(0); }
  const row = `  - name: ${target}\n    why: ${why}\n    as_of: ${today}\n`;
  const src = readFileSync(YML, 'utf8').trimEnd();
  writeFileSync(YML, `${src}\n${row}`);
  console.log(`"${target}": added to _excluded.yaml. No record exists, so nothing else to do.`);
}
