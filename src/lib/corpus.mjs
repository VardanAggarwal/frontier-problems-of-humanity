// Load problems/graph.db -> validate -> resolve refs -> derive the inverse
// relations. One loader, three consumers: the Astro pages, scripts/build-index.mjs,
// and `npm run validate`. Throws on a fatal assertion; returns the punch list
// for the rest (README -> What to test: 1-4 fail the build, 5-10 warn until
// the corpus is clean).
//
// 01-minimal.md §11 item 3b ("the corpus stops being parsed twice"): needs,
// leaves, nodes and actors are no longer parsed from markdown frontmatter
// here. As of 3b-B (2026-09-13) there is no frontmatter left to parse — all
// 302 leaf/node/actor files were stripped to prose-only, and graph.db is the
// durable source of truth (worker writes and human edits via
// engine/store/edit.py both land there directly, not derived from disk on
// every build). Prose still lives on disk: `doc` names the file, and its
// body (whatever follows a frontmatter block, if any survives on an
// unmigrated file) is read and run through `parseSections`, so leaf/node/
// actor pages render the same sections they always have.
//
// Named debt (01-minimal.md §12):
//  - Frontmatter shape validation (schema.mjs's Zod schemas) has no call site
//    any more, permanently — there is no frontmatter left to validate.
//    Porting that validation forward means rewriting it against
//    engine/store/edit.py's write path, not restoring a call here.
//  - `problems/private/connections/*.md` are not migrated into graph.db and
//    are no longer loaded at all — `connections` is always `[]`. Reviving
//    this means new write support in edit.py/worker.py, not finishing a
//    partial migration (the old frontmatter path no longer exists to finish).
//  - `ccLeaves` stays `[]`: no per-axis leaf files exist on disk yet (the two
//    cross-cutting essays carry no frontmatter and are a pre-existing gap in
//    the migration itself, noted in from_corpus.py) — unchanged from before
//    this cutover, since the old loader's directory scan already found none.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';
import { parseSections, sectionIssues, parseTierFile } from './sections.mjs';
import { openGraph, tagValue, tagValues, aliasesOf, jsonArr, edgesOut, edgesIn } from './graphdb.mjs';

export const ROOT = path.resolve(fileURLToPath(new URL('../..', import.meta.url)));
const P = (...s) => path.join(ROOT, ...s);
const TFH = 'problems/tier-failure-history';

const read = (p) => fs.readFileSync(p, 'utf8');
const exists = (p) => fs.existsSync(p);
const ls = (dir, re) => (exists(dir) ? fs.readdirSync(dir).filter((f) => re.test(f)).sort() : []);
const num = (v) => (v === undefined ? undefined : Number(v));
const idsForKind = (g, kind) => g.prepare(
  "SELECT entity_id FROM tag WHERE entity_kind = 'problem' AND ns = 'kind' AND value = ?"
).all(kind).map((r) => r.entity_id);

// Strip the YAML frontmatter block, if any, and return the body — the only
// thing this loader still parses out of a markdown file by hand. No YAML.parse,
// no schema: the fields that used to come from the header now come from the DB.
function readBody(filePath) {
  if (!filePath) return '';
  const src = read(P(filePath));
  const m = src.match(/^---\r?\n[\s\S]*?\r?\n---\r?\n?([\s\S]*)$/);
  return m ? m[1] : src;
}

function attachBody(rec, filePath, kind, errors, warns, isStub) {
  const parsed = parseSections(readBody(filePath), kind);
  rec.lede = parsed.lede;
  rec.sections = parsed.sections;
  if (kind === 'leaf' && isStub) {
    // Half of assertion 7 survives without raw frontmatter: a stub cannot
    // carry a body. The other half (non-stub keys present on a stub) needed
    // the raw frontmatter dict and is part of the validation debt above.
    if (parsed.sections.length) errors.push(`${filePath}: status: stub has a body (assertion 7)`);
    return;
  }
  const sink = kind === 'leaf' ? errors : warns;
  for (const i of sectionIssues(parsed, kind, { requireAll: kind === 'leaf' && !isStub }))
    sink.push(`${filePath}: ${i} (assertion 6)`);
}

export function loadCorpus() {
  const errors = [];   // fatal — the build stops
  const warns = [];    // punch list

  const g = openGraph(P('problems/graph.db'));

  // -- registries — small lookup tables, not per-record frontmatter --------
  const needsYaml = YAML.parse(read(P(TFH, 'needs.yaml')));
  const tiers = needsYaml.tiers ?? {};

  const lensYaml = YAML.parse(read(P('problems/lenses.yaml')));
  const mechanisms = (lensYaml.mechanisms ?? []).map((m) => ({ ...m, leaves: [], url: `/lens/mechanism/${m.id}` }));
  const axes = (lensYaml.axes ?? []).map((a) => ({ ...a, leaves: [], url: `/lens/axis/${a.id}` }));

  const byId = new Map();       // slug -> record, all kinds; the ref resolver
  const aliasMap = new Map();   // former slug -> current slug

  const register = (rec) => {
    if (byId.has(rec.id)) errors.push(`${rec.path}: duplicate id "${rec.id}" (also ${byId.get(rec.id).path})`);
    byId.set(rec.id, rec);
    for (const a of rec.aliases ?? []) aliasMap.set(a, rec.id);
  };

  // -- needs -----------------------------------------------------------------
  const needs = [];
  for (const id of idsForKind(g, 'need')) {
    const row = g.prepare('SELECT title, doc FROM problem WHERE id = ?').get(id);
    const file = row.doc ? row.doc.replace(new RegExp(`^${TFH}/`), '') : null;
    if (!file) warns.push(`need/${id}: no doc path in graph.db`);
    needs.push({
      id, tier: num(tagValue(g, 'problem', id, 'tier')), title: row.title,
      order: num(tagValue(g, 'problem', id, 'order')), file,
      status: tagValue(g, 'problem', id, 'sweep'),
      leaves: [], url: `/need/${id}`,
    });
  }

  // -- leaves ------------------------------------------------------------------
  const leaves = [];
  const ccLeaves = [];   // see module-doc debt note — no per-axis files exist yet
  for (const id of idsForKind(g, 'leaf')) {
    const row = g.prepare(
      'SELECT title, one_line, status, geography, gap_note, doc, updated FROM problem WHERE id = ?'
    ).get(id);
    const file = row.doc;
    const need = tagValue(g, 'problem', id, 'need');
    const leaf = {
      kind: 'leaf', id, aliases: aliasesOf(g, 'problem', id, row.title),
      title: row.title, one_line: row.one_line, status: row.status,
      geography: jsonArr(row.geography),
      tier: num(tagValue(g, 'problem', id, 'tier')), need,
      salience: num(tagValue(g, 'problem', id, 'salience')),
      scale: num(tagValue(g, 'problem', id, 'scale')),
      channel: tagValue(g, 'problem', id, 'channel'),
      satisfier_relation: tagValue(g, 'problem', id, 'satisfier_relation'),
      onset: tagValue(g, 'problem', id, 'onset'),
      agent: tagValue(g, 'problem', id, 'agent'),
      mechanisms: tagValues(g, 'problem', id, 'mechanism'),
      cross_cutting: tagValues(g, 'problem', id, 'cross_cutting'),
      nodes: edgesOut(g, 'problem', id, 'member_of').map((e) => e.dst_id),
      gap: tagValue(g, 'problem', id, 'gap_kind'),
      gap_missing_leg: tagValues(g, 'problem', id, 'gap_missing_leg'),
      gap_note: row.gap_note,
      gap_as_of: tagValue(g, 'problem', id, 'gap_as_of'),
      last_reviewed: tagValue(g, 'problem', id, 'last_reviewed'),
      sources: edgesOut(g, 'problem', id, 'cites').map((e) => {
        const s = g.prepare('SELECT url, title, org, year FROM source WHERE id = ?').get(e.dst_id);
        return s && { url: s.url, title: s.title ?? undefined, org: s.org ?? undefined, year: s.year ?? undefined };
      }).filter(Boolean),
      updated: row.updated,
      path: file, url: `/leaf/${id}`, actors_touching: [], private: false,
    };
    if (file) {
      if (path.basename(file, '.md') !== id)
        warns.push(`${file}: filename disagrees with id "${id}"`);
      const needDir = file.split('/').slice(-2, -1)[0];
      if (need && needDir !== need)
        warns.push(`${file}: directory "${needDir}" disagrees with need "${need}"`);
    }
    attachBody(leaf, file, 'leaf', errors, warns, leaf.status === 'stub');
    leaves.push(leaf); register(leaf);
  }

  // -- nodes ---------------------------------------------------------------
  const nodes = [];
  for (const id of idsForKind(g, 'node')) {
    const row = g.prepare(
      'SELECT title, one_line, geography, doc, updated FROM problem WHERE id = ?'
    ).get(id);
    const node = {
      kind: 'node', id, aliases: aliasesOf(g, 'problem', id, row.title),
      title: row.title, one_line: row.one_line,
      type: tagValue(g, 'problem', id, 'node_type'),
      authority: tagValue(g, 'problem', id, 'authority'),
      geography: jsonArr(row.geography),
      mechanisms: tagValues(g, 'problem', id, 'mechanism'),
      needs: edgesOut(g, 'problem', id, 'part_of').map((e) => e.dst_id),
      sub_levers: tagValues(g, 'problem', id, 'sub_levers'),
      actors: edgesIn(g, 'problem', id, 'works_on').map((e) => e.src_id),
      status: tagValue(g, 'problem', id, 'node_status'),
      updated: row.updated,
      path: row.doc, url: `/node/${id}`, leaves: [], actors_on_node: [], private: false,
    };
    attachBody(node, row.doc, 'node', errors, warns, false);
    nodes.push(node); register(node);
  }

  // -- actors --------------------------------------------------------------
  const actors = [];
  for (const row of g.prepare('SELECT * FROM actor').all()) {
    const id = row.id;
    const leafRefs = [], nodeRefs = [];
    for (const e of edgesOut(g, 'actor', id, 'works_on')) {
      if (e.dst_kind !== 'problem') continue;
      const k = tagValue(g, 'problem', e.dst_id, 'kind');
      if (k === 'leaf') leafRefs.push({ id: e.dst_id, role: e.relevance === 3 ? 'primary' : 'supporting' });
      else if (k === 'node') nodeRefs.push(e.dst_id);
    }
    const asks = g.prepare(
      'SELECT direction, kind, text, as_of, source, state FROM ask WHERE actor_id = ?'
    ).all(id);
    const channels = g.prepare(
      'SELECT kind, url, handle, status, last_checked FROM channel WHERE actor_id = ?'
    ).all(id);
    const actor = {
      kind: 'actor', id, name: row.title, slug: id, path: row.doc,
      aliases: aliasesOf(g, 'actor', id, row.title),
      type: row.type, depth: row.depth,
      parent: edgesOut(g, 'actor', id, 'parent_org')[0]?.dst_id,
      superseded_by: edgesOut(g, 'actor', id, 'superseded_by')[0]?.dst_id,
      // `to` (an affiliation's end date) isn't in graph.db yet — no page reads
      // it today, so this is a silent-but-harmless part of the debt above.
      affiliations: edgesOut(g, 'actor', id, 'affiliated').map((e) => ({
        actor: e.dst_id, role: e.evidence ?? undefined, from: e.as_of ?? undefined,
      })),
      leg: jsonArr(row.legs), ecosystem_role: jsonArr(row.ecosystem_role),
      affected_led: row.affected_led, representation_unit: row.representation_unit,
      stance: row.stance, leaves: leafRefs, nodes: nodeRefs,
      geography: jsonArr(row.geography),
      lifecycle: row.lifecycle, lifecycle_as_of: row.lifecycle_as_of ?? undefined,
      needs: asks.filter((a) => a.direction === 'need').map((a) => ({
        kind: a.kind, text: a.text, as_of: a.as_of ?? undefined,
        source: a.source ?? undefined, state: a.state ?? undefined,
      })),
      offers: asks.filter((a) => a.direction === 'offer').map((a) => ({ kind: a.kind, text: a.text })),
      sources: channels.map((c) => ({
        kind: c.kind, url: c.url ?? undefined, handle: c.handle ?? undefined,
        status: c.status, last_checked: c.last_checked ?? undefined,
      })),
      contact_route: row.contact_route ?? undefined,
      followed: !!row.followed, followed_date: row.followed_date ?? undefined,
      last_checked: row.last_checked ?? undefined, updated: row.updated,
      url: `/actor/${id}`, private: false,
    };
    // §4 rule 3 — an unsourced adversarial label is the highest-harm output here
    if (actor.stance === 'organised-against-remedy' &&
        !actor.sources.some((s) => s.url && s.status !== 'none-found'))
      errors.push(`${actor.path}: stance: organised-against-remedy with no sourced channel (assertion 4)`);
    if (actor.depth !== 'excluded' &&
        actor.leaves.length === 0 && (actor.ecosystem_role ?? []).length === 0)
      warns.push(`${actor.path}: attaches to nothing — no leaves and no ecosystem_role`);
    attachBody(actor, row.doc, 'actor', errors, warns, false);
    actors.push(actor); register(actor);
  }

  // -- private -------------------------------------------------------------
  // Dropped, not migrated: problems/private/connections is neither queried
  // from graph.db (from_corpus.py doesn't migrate it) nor file-parsed any
  // more — see the module-doc debt note.
  const connections = [];

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
      warns.push(`${a.path ?? a.id}: depth: tracked with no live source row`);
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
  for (const td of ls(P(TFH), /^tier\d-/)) {
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

  g.close();

  return {
    tiers, needs, leaves, ccLeaves, allLeaves, nodes, actors, connections,
    mechanisms, axes, tierFiles, crossCuttingFiles, tierSummaries, byId, aliasMap,
    errors, warns,
  };
}

function monthsBetween(a, b) {
  const [ay, am] = a.split('-').map(Number), [by, bm] = b.split('-').map(Number);
  return (by - ay) * 12 + (bm - am);
}
