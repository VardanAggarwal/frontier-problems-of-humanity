// Body parsing — 03-portal.md §2.
// Match on a KEY, never on the heading string: `## A · Classification` is a
// display string with a middot in it, and parsing on it makes typography
// load-bearing. Normalise, look up in the registry, store the heading as written.

const norm = (h) => h
  .toLowerCase()
  .replace(/^\s*(?:[a-e]|\d+)\s*[·.)\-–—:]\s*/, '')   // strip the A–E / 1. ordinal
  .replace(/[^a-z0-9]+/g, ' ')
  .trim()
  .replace(/\s+/g, '-');

// normalised heading -> section key. Several headings may resolve to one key.
export const REGISTRY = {
  leaf: {
    classification: 'classification',
    evidence: 'evidence',
    diagnosis: 'diagnosis',
    'who-is-working-on-this': 'actors',
    actors: 'actors',
    gap: 'gap',
    sources: 'sources',
  },
  actor: {
    scope: 'scope',
    status: 'status',
    'what-they-need': 'needs',
    'what-they-can-offer': 'offers',
    'how-to-reach-them': 'contact',
    'recent-updates': 'updates',
    sources: 'sources',
  },
  node: {
    'the-object': 'object',
    'cross-need-chain': 'chain',
    'the-one-intervention': 'intervention',
    'the-sub-lever-map': 'intervention',
    leaves: 'leaves',
    'actors-on-the-node': 'actors',
    sources: 'sources',
  },
};

export const REQUIRED = {
  leaf: ['classification', 'evidence', 'diagnosis', 'actors', 'gap'],
  actor: [],
  node: [],
};

// Sections the derive step overwrites: whatever the body says is ignored.
export const GENERATED = { node: ['leaves', 'actors'], leaf: [], actor: [] };

/**
 * Split a markdown body into { key, heading, ord, markdown } at H2.
 * An explicit `<!-- s:key -->` immediately above a heading wins.
 * Anything before the first H2 (the H1 and any lede) comes back as `lede`.
 */
export function parseSections(body, kind) {
  const reg = REGISTRY[kind] ?? {};
  const lines = body.split('\n');
  const out = [];
  let lede = [];
  let cur = null;
  let pendingKey = null;
  let ord = 0;

  // A standalone line leading `Data note —` / `Data caution —` (optionally a
  // bullet, optionally `*`/`_` wrapped) is a source caveat: lifted out of the
  // prose and collected on `section.notes`, rendered as a footnote block.
  const NOTE_RE = /^\s*(?:[-*]\s+)?[*_]{0,2}data\s+(?:note|caution)[*_]{0,2}\s*[—:-]\s*(.+?)\s*$/i;
  const push = () => {
    if (!cur) return;
    cur.notes = [];
    cur.lines = cur.lines.filter((ln) => {
      const m = ln.match(NOTE_RE);
      if (m) { cur.notes.push(m[1].replace(/[*_]+\s*$/, '').trim()); return false; }
      return true;
    });
    cur.markdown = cur.lines.join('\n').trim();
    delete cur.lines;
    out.push(cur);
  };

  for (const line of lines) {
    const hint = line.match(/^\s*<!--\s*s:([a-z0-9-]+)\s*-->\s*$/);
    if (hint) { pendingKey = hint[1]; continue; }
    const h2 = line.match(/^##\s+(?!#)(.*)$/);
    if (h2) {
      push();
      const heading = h2[1].trim();
      const n = norm(heading);
      cur = { key: pendingKey ?? reg[n] ?? null, raw_key: n, heading, ord: ord++, lines: [] };
      pendingKey = null;
      continue;
    }
    (cur ? cur.lines : lede).push(line);
  }
  push();

  // strip the H1 out of the lede — it is the title, rendered from frontmatter
  const ledeText = lede.join('\n').replace(/^#\s+.*$/m, '').trim();
  return { lede: ledeText, sections: out };
}

export function sectionIssues(parsed, kind, { requireAll }) {
  const issues = [];
  const seen = new Set(parsed.sections.map((s) => s.key).filter(Boolean));
  for (const s of parsed.sections)
    if (!s.key) issues.push(`unrecognised H2 "${s.heading}" (normalised: ${s.raw_key})`);
  if (requireAll)
    for (const k of REQUIRED[kind] ?? [])
      if (!seen.has(k)) issues.push(`missing required section: ${k}`);
  return issues;
}

/**
 * Tier topic files predate the section invariant (26 of 36 are `first-sweep`),
 * so these parse loosely: an H2 tree with its H3s, no key registry, no failure
 * on an unknown heading. What the portal actually addresses is two H3s —
 * `### Where it worked` (the positive controls, /lens/where-it-worked) and
 * `### India: ...` (the failure list each leaf comes from).
 */
export function parseTierFile(md) {
  const lines = md.split('\n');
  const h2s = [];
  let cur = null, sub = null, title = null, lede = [];
  for (const line of lines) {
    const h1 = line.match(/^#\s+(?!#)(.*)$/);
    if (h1 && !title) { title = h1[1].trim(); continue; }
    const m2 = line.match(/^##\s+(?!#)(.*)$/);
    if (m2) { cur = { heading: m2[1].trim(), key: norm(m2[1]), lines: [], subs: [] }; sub = null; h2s.push(cur); continue; }
    const m3 = line.match(/^###\s+(?!#)(.*)$/);
    if (m3 && cur) { sub = { heading: m3[1].trim(), key: norm(m3[1]), lines: [] }; cur.subs.push(sub); continue; }
    (sub ? sub.lines : cur ? cur.lines : lede).push(line);
  }
  const finish = (o) => { o.markdown = o.lines.join('\n').trim(); delete o.lines; return o; };
  for (const h of h2s) { finish(h); h.subs.forEach(finish); }
  const subs = h2s.flatMap((h) => h.subs);
  const ledeText = lede.join('\n').trim();
  // The lead area carries the need's own two-part self-description: a leading
  // `>` blockquote is the one-line `definition` (browse-card form); everything
  // after it, up to the first H2, is the `description` paragraph(s).
  let definition = null, description = null;
  const bq = ledeText.match(/^>[ \t]?(.*(?:\n>.*)*)/);
  if (bq) {
    definition = bq[1].replace(/\n>[ \t]?/g, ' ').trim();
    let d = ledeText.slice(bq[0].length).trim();
    // drop a stale "Tier definition:" / "Definition:" label left at the head of
    // the description prose by files written before the blockquote existed, and
    // re-case the now-leading word.
    const stripped = d.replace(/^(?:tier\s+definition|definition|tier\s+\d+\s+need)\s*:\s*/i, '');
    if (stripped !== d) d = stripped.replace(/^([a-z])/, (c) => c.toUpperCase());
    description = d || null;
  }
  return {
    title,
    lede: ledeText,
    definition,
    description,
    sections: h2s,
    where_it_worked: subs.find((s) => s.key === 'where-it-worked') ?? null,
    india: subs.filter((s) => s.key.startsWith('india')),
  };
}
