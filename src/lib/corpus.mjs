// Load problems/ -> validate -> resolve refs -> derive the inverse relations.
// One loader, three consumers: the Astro pages, scripts/build-index.mjs, and
// `npm run validate`. Throws on a fatal assertion; returns the punch list for
// the rest (README -> What to test: 1-4 fail the build, 5-10 warn until the
// corpus is clean).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';
import {
  needSchema, leafSchema, ccLeafSchema, nodeSchema, actorSchema,
  connectionSchema, STUB_KEYS, stripNulls,
} from './schema.mjs';
import { parseSections, sectionIssues, parseTierFile } from './sections.mjs';

export const ROOT = path.resolve(fileURLToPath(new URL('../..', import.meta.url)));
const P = (...s) => path.join(ROOT, ...s);
const TFH = 'problems/tier-failure-history';

const read = (p) => fs.readFileSync(p, 'utf8');
const exists = (p) => fs.existsSync(p);
const ls = (dir, re) => (exists(dir) ? fs.readdirSync(dir).filter((f) => re.test(f)).sort() : []);

function splitFrontmatter(src, file) {
  const m = src.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) throw new Error(`${file}: no YAML frontmatter`);
  return { data: stripNulls(YAML.parse(m[1]) ?? {}), body: m[2] };
}

const zIssues = (file, r) =>
  r.error.issues.map((i) => `${file}: ${i.path.join('.') || '(root)'} — ${i.message}`);

export function loadCorpus({ includePrivate = true } = {}) {
  const errors = [];   // fatal — the build stops
  const warns = [];    // punch list
  const rel = (p) => path.relative(ROOT, p);

  // -- registries ----------------------------------------------------------
  const needsYaml = YAML.parse(read(P(TFH, 'needs.yaml')));
  const needs = [];
  for (const raw of needsYaml.needs ?? []) {
    const r = needSchema.safeParse(raw);
    if (!r.success) { errors.push(...zIssues('needs.yaml', r)); continue; }
    needs.push({ ...r.data, leaves: [], url: `/need/${r.data.id}` });
  }
  const tiers = needsYaml.tiers ?? {};

  const lensYaml = YAML.parse(read(P('problems/lenses.yaml')));
  const mechanisms = (lensYaml.mechanisms ?? []).map((m) => ({ ...m, leaves: [], url: `/lens/mechanism/${m.id}` }));
  const axes = (lensYaml.axes ?? []).map((a) => ({ ...a, leaves: [], url: `/lens/axis/${a.id}` }));

  const byId = new Map();       // slug -> record, all kinds; the ref resolver
  const aliasMap = new Map();   // former slug -> current slug

  const register = (rec, file) => {
    if (byId.has(rec.id)) errors.push(`${file}: duplicate id "${rec.id}" (also ${byId.get(rec.id).path})`);
    byId.set(rec.id, rec);
    for (const a of rec.aliases ?? []) aliasMap.set(a, rec.id);
  };

  // -- leaves --------------------------------------------------------------
  const leaves = [];
  const ccLeaves = [];
  const tierDirs = ls(P(TFH), /^tier\d-/);
  for (const td of tierDirs) {
    for (const needDir of ls(P(TFH, td), /^[^.]+$/).filter((d) => fs.statSync(P(TFH, td, d)).isDirectory())) {
      for (const f of ls(P(TFH, td, needDir), /\.md$/)) {
        if (f.startsWith('_') || f.startsWith('00-')) continue;
        const file = rel(P(TFH, td, needDir, f));
        const { data, body } = splitFrontmatter(read(P(TFH, td, needDir, f)), file);
        const r = leafSchema.safeParse(data);
        if (!r.success) { errors.push(...zIssues(file, r)); continue; }
        const leaf = { kind: 'leaf', ...r.data, path: file, url: `/leaf/${r.data.id}`,
          actors_touching: [], private: false };
        // delta 1: the frontmatter is the claim, the path only has to agree
        if (path.basename(f, '.md') !== leaf.id)
          warns.push(`${file}: filename disagrees with id "${leaf.id}"`);
        if (needDir !== leaf.need)
          warns.push(`${file}: directory "${needDir}" disagrees with need "${leaf.need}"`);
        attachBody(leaf, body, 'leaf', errors, warns, file, data);
        leaves.push(leaf); register(leaf, file);
      }
    }
  }
  for (const axisDir of ls(P(TFH, 'cross-cutting'), /^[a-z-]+$/).filter((d) => fs.statSync(P(TFH, 'cross-cutting', d)).isDirectory())) {
    for (const f of ls(P(TFH, 'cross-cutting', axisDir), /\.md$/)) {
      if (f.startsWith('_') || f.startsWith('00-')) continue;
      const file = rel(P(TFH, 'cross-cutting', axisDir, f));
      const { data, body } = splitFrontmatter(read(P(TFH, 'cross-cutting', axisDir, f)), file);
      const r = ccLeafSchema.safeParse(data);
      if (!r.success) { errors.push(...zIssues(file, r)); continue; }
      const leaf = { kind: 'cc_leaf', ...r.data, path: file, url: `/leaf/${r.data.id}`,
        actors_touching: [], private: false };
      attachBody(leaf, body, 'leaf', errors, warns, file, data);
      ccLeaves.push(leaf); register(leaf, file);
    }
  }

  // -- nodes ---------------------------------------------------------------
  const nodes = [];
  for (const f of ls(P('problems/cross-need-nodes'), /\.md$/)) {
    if (f.startsWith('_') || f.startsWith('00-')) continue;
    const file = rel(P('problems/cross-need-nodes', f));
    const { data, body } = splitFrontmatter(read(P('problems/cross-need-nodes', f)), file);
    const r = nodeSchema.safeParse(data);
    if (!r.success) { errors.push(...zIssues(file, r)); continue; }
    const node = { kind: 'node', ...r.data, path: file, url: `/node/${r.data.id}`,
      leaves: [], actors_on_node: [], private: false };
    attachBody(node, body, 'node', errors, warns, file, data);
    nodes.push(node); register(node, file);
  }

  // -- actors --------------------------------------------------------------
  const actors = [];
  for (const f of ls(P('problems/actors'), /\.md$/)) {
    if (f.startsWith('_') || f.startsWith('00-')) continue;
    const file = rel(P('problems/actors', f));
    const { data, body } = splitFrontmatter(read(P('problems/actors', f)), file);
    const r = actorSchema.safeParse(data);
    if (!r.success) { errors.push(...zIssues(file, r)); continue; }
    const a = r.data;
    const actor = { kind: 'actor', ...a, id: a.id ?? a.slug, path: file,
      url: `/actor/${a.id ?? a.slug}`, private: false };
    // §4 rule 3 — an unsourced adversarial label is the highest-harm output here
    if (actor.stance === 'organised-against-remedy' &&
        !actor.sources.some((s) => s.url && s.status !== 'none-found'))
      errors.push(`${file}: stance: organised-against-remedy with no sourced channel (assertion 4)`);
    attachBody(actor, body, 'actor', errors, warns, file, data);
    actors.push(actor); register(actor, file);
  }

  // -- private -------------------------------------------------------------
  // Loaded and FK-checked like everything else; absent from the emitted DB.
  const connections = [];
  if (includePrivate) {
    for (const f of ls(P('problems/private/connections'), /\.md$/)) {
      if (f.startsWith('_')) continue;
      const file = rel(P('problems/private/connections', f));
      const { data, body } = splitFrontmatter(read(P('problems/private/connections', f)), file);
      const r = connectionSchema.safeParse(data);
      if (!r.success) { errors.push(...zIssues(file, r)); continue; }
      const c = { kind: 'connection', ...r.data, path: file, url: null, private: true, body };
      connections.push(c); register(c, file);
    }
  }

  // -- ref resolution + inverse relations ----------------------------------
  const resolve = (id) => byId.get(id) ?? byId.get(aliasMap.get(id));
  const needIds = new Set(needs.map((n) => n.id));
  const mechIds = new Set(mechanisms.map((m) => m.id));
  const axisIds = new Set(axes.map((a) => a.id));

  const refErr = (where, kind, id) => warns.push(`${where}: dangling ${kind} ref "${id}" (assertion 5)`);

  const allLeaves = [...leaves, ...ccLeaves];
  for (const l of allLeaves) {
    if (l.kind === 'leaf') {
      const n = needs.find((x) => x.id === l.need);
      if (!n) refErr(l.path, 'need', l.need);
      else { n.leaves.push(l); if (n.tier !== l.tier) warns.push(`${l.path}: tier ${l.tier} disagrees with need "${l.need}" (tier ${n.tier})`); }
    }
    for (const m of l.mechanisms) {
      if (!mechIds.has(m)) refErr(l.path, 'mechanism', m);
      else mechanisms.find((x) => x.id === m).leaves.push(l);
    }
    for (const a of l.cross_cutting ?? []) {
      if (!axisIds.has(a)) refErr(l.path, 'axis', a);
      else axes.find((x) => x.id === a).leaves.push(l);
    }
    if (l.kind === 'cc_leaf') axes.find((x) => x.id === l.axis)?.leaves.push(l);
    for (const nid of l.nodes) {
      const n = resolve(nid);
      if (!n || n.kind !== 'node') refErr(l.path, 'node', nid);
      else n.leaves.push(l);
    }
  }
  for (const a of actors) {
    for (const { id: lid, role } of a.leaves) {
      const l = resolve(lid);
      if (!l || !['leaf', 'cc_leaf'].includes(l.kind)) refErr(a.path, 'leaf', lid);
      else { l.actors_touching.push(a); (l.actor_roles ??= new Map()).set(a.id, role); }
    }
    for (const nid of a.nodes) {
      const n = resolve(nid);
      if (!n || n.kind !== 'node') refErr(a.path, 'node', nid);
      else n.actors_on_node.push(a);
    }
    for (const f of ['parent', 'superseded_by']) {
      if (a[f] && resolve(a[f])?.kind !== 'actor') refErr(a.path, `actor (${f})`, a[f]);
    }
    for (const af of a.affiliations) if (resolve(af.actor)?.kind !== 'actor') refErr(a.path, 'actor (affiliation)', af.actor);
  }
  for (const c of connections) {
    for (const aid of c.actors) if (resolve(aid)?.kind !== 'actor') refErr(c.path, 'actor', aid);
    const ctx = resolve(c.context);
    if (!ctx || !['leaf', 'cc_leaf', 'node'].includes(ctx.kind)) refErr(c.path, 'context', c.context);
  }

  // assertion 8 — a node claiming a need with no member leaf over-states its reach
  for (const n of nodes) {
    for (const nid of n.needs) {
      if (!needIds.has(nid)) { refErr(n.path, 'need', nid); continue; }
      if (!n.leaves.some((l) => l.need === nid))
        warns.push(`${n.path}: node claims need "${nid}" with no member leaf (assertion 8)`);
    }
    for (const aid of n.actors) if (resolve(aid)?.kind !== 'actor') refErr(n.path, 'actor', aid);
  }

  // assertion 9 — a gap verdict standing against an actor that has since moved
  const today = new Date().toISOString().slice(0, 10);
  for (const l of allLeaves) {
    if (l.status !== 'researched') continue;
    for (const a of l.actors_touching) {
      if (l.gap_as_of && a.lifecycle_as_of > l.gap_as_of) {
        l.status = 'stale';
        warns.push(`${l.path}: gap_as_of ${l.gap_as_of} predates ${a.id} lifecycle_as_of ${a.lifecycle_as_of} -> stale (assertion 9)`);
      }
    }
    const reviewed = l.last_reviewed ?? l.updated;
    if (monthsBetween(reviewed, today) > 18) {
      l.status = 'stale';
      warns.push(`${l.path}: last reviewed ${reviewed}, over 18 months -> stale`);
    }
  }
  // assertion 10 — /gaps is the queue; an unqualified gap under-reports it
  for (const l of allLeaves) {
    if (l.status === 'stub') continue;
    if (l.gap && l.gap !== 'none' && l.gap_missing_leg.length === 0)
      warns.push(`${l.path}: gap: ${l.gap} with empty gap_missing_leg (assertion 10)`);
  }
  for (const n of needs) if (n.leaves.length === 0) warns.push(`needs.yaml: "${n.id}" has zero leaves`);
  for (const a of actors) {
    if (a.depth === 'tracked' && !a.sources.some((s) => s.status === 'live'))
      warns.push(`${a.path}: depth: tracked with no live source row`);
  }

  // -- tier topic files ----------------------------------------------------
  const tierFiles = new Map();
  for (const n of needs) {
    const p = P(TFH, n.file);
    if (!exists(p)) { warns.push(`needs.yaml: "${n.id}" points at missing file ${n.file}`); continue; }
    const parsed = parseTierFile(read(p));
    tierFiles.set(n.id, parsed);
    // definition + description are owned by the tier file's lead area (a leading
    // `>` blockquote, then prose), not by needs.yaml.
    if (parsed.definition) n.definition = parsed.definition;
    else warns.push(`${n.file}: no leading > blockquote — need "${n.id}" has no definition, falling back to its title`);
    n.definition ??= n.title;
    n.description = parsed.description ?? null;
  }
  const crossCuttingFiles = axes.map((a) => ({
    ...a, parsed: exists(P('problems', a.file)) ? parseTierFile(read(P('problems', a.file))) : null,
  }));

  // -- tier summaries -------------------------------------------------------
  // 00-summary.md per tier ("what survived the six [need] files"), currently
  // written for tier 1 only — others render without it until written.
  const tierSummaries = new Map();
  for (const td of tierDirs) {
    const m = td.match(/^tier(\d+)-/);
    if (!m) continue;
    const p = P(TFH, td, '00-summary.md');
    if (!exists(p)) continue;
    tierSummaries.set(Number(m[1]), parseTierFile(read(p)));
  }

  // process order: scale (order of magnitude of exposed population) descending, then
  // the tier file's list position (salience) as tiebreak, then title. A missing scale sorts last.
  const orderLeaves = (arr) => arr.sort((a, b) =>
    (b.scale ?? -1) - (a.scale ?? -1)
    || (a.salience ?? 99) - (b.salience ?? 99)
    || a.title.localeCompare(b.title));
  needs.forEach((n) => orderLeaves(n.leaves));
  nodes.forEach((n) => orderLeaves(n.leaves));
  needs.sort((a, b) => a.tier - b.tier || a.order - b.order);

  // Actor lists have no magnitude the way leaves do. Rank by a composite of the
  // enums already on the record: role on this leaf (primary first, where given),
  // then still-active, engaged (tracked), affected-led, works-the-remedy, breadth.
  const LIFECYCLE_RANK = { operating: 0, scaling: 0, distressed: 1, dormant: 2, acquired: 2, shut: 3, 'won-and-dissolved': 3 };
  const AFFECTED_RANK = { yes: 0, partial: 1, no: 2 };
  const ROLE_RANK = { primary: 0, supporting: 1 };
  const actorRank = (a) => [
    LIFECYCLE_RANK[a.lifecycle] ?? 9,
    a.depth === 'tracked' ? 0 : 1,
    AFFECTED_RANK[a.affected_led] ?? 9,
    a.stance === 'organised-against-remedy' ? 1 : 0,
  ];
  const orderActors = (arr, roleOf) => arr.sort((x, y) => {
    if (roleOf) {
      const r = (ROLE_RANK[roleOf.get(x.id)] ?? 1) - (ROLE_RANK[roleOf.get(y.id)] ?? 1);
      if (r) return r;
    }
    const rx = actorRank(x), ry = actorRank(y);
    for (let i = 0; i < rx.length; i++) if (rx[i] !== ry[i]) return rx[i] - ry[i];
    return (y.leaves.length - x.leaves.length) || x.name.localeCompare(y.name);
  });
  allLeaves.forEach((l) => orderActors(l.actors_touching, l.actor_roles));
  nodes.forEach((n) => orderActors(n.actors_on_node));
  orderActors(actors);

  return {
    tiers, needs, leaves, ccLeaves, allLeaves, nodes, actors, connections,
    mechanisms, axes, tierFiles, crossCuttingFiles, tierSummaries, byId, aliasMap,
    errors, warns,
  };
}

function attachBody(rec, body, kind, errors, warns, file, raw) {
  const parsed = parseSections(body, kind);
  rec.lede = parsed.lede;
  rec.sections = parsed.sections;
  const isStub = rec.status === 'stub';
  if (kind === 'leaf' && isStub) {
    // assertion 7 — stub key discipline (see STUB_KEYS). Identity, placement and
    // cheap classification are fine on a stub; research outputs are not, so a
    // half-researched leaf can't park as a stub and make the counter lie.
    const extra = Object.keys(raw).filter((k) => !STUB_KEYS.includes(k));
    if (extra.length) errors.push(`${file}: status: stub carries non-stub keys [${extra.join(', ')}] (assertion 7)`);
    if (parsed.sections.length) errors.push(`${file}: status: stub has a body (assertion 7)`);
    return;
  }
  // Assertion 6 is fatal for leaves, where the invariant is enforced from the
  // template onward. Node and actor bodies predate it (the five nodes use
  // bold-lead paragraphs, not H2s), so there it is a punch-list line.
  const sink = kind === 'leaf' ? errors : warns;
  for (const i of sectionIssues(parsed, kind, { requireAll: kind === 'leaf' && !isStub }))
    sink.push(`${file}: ${i} (assertion 6)`);
}

function monthsBetween(a, b) {
  const [ay, am] = a.split('-').map(Number), [by, bm] = b.split('-').map(Number);
  return (by - ay) * 12 + (bm - am);
}
