// Zod transcription of problems/data-model.yaml v3.
// ONE transcription: the portal pages, the SQLite emit and `npm run validate`
// all import this file. If this and data-model.yaml disagree, data-model.yaml
// is the spec and this is the bug.
import { z } from 'zod';

export const E = {
  tier: [1, 2, 3, 4, 5],
  record_status: ['stub', 'researched', 'stale'],
  channel: ['direct', 'structural', 'cultural-normative', 'ambient-accidental'],
  satisfier_relation: ['absence', 'violator', 'pseudo-satisfier', 'maldistribution', 'degraded-quality'],
  onset: ['acute', 'chronic', 'latent'],
  agent_physical: ['nature', 'climate', 'industrial-accident', 'industrial-exposure',
    'industrial-pollution', 'daily-life', 'warfare', 'state-policy'],
  agent_social: ['market', 'state-policy', 'social-norm', 'technology-shift',
    'demographic-shift', 'deliberate-exclusion'],
  mechanism: ['aggregation-masks-failure', 'spend-mismatched-to-source',
    'instrument-keyed-to-wrong-object', 'authority-mismatched-to-harm',
    'primary-vs-derivative-burden', 'solution-at-hand-blocked',
    'compensation-substitutes-for-counting', 'within-tier-loop',
    'second-half-never-built', 'visible-win-strands-residual', 'unclassified'],
  gap: ['none', 'coverage', 'representation'],
  cross_cutting_axis: ['autonomy', 'leisure'],
  node_type: ['instrument', 'sector', 'exposure-class'],
  node_status: ['open', 'fix-known', 'fix-partial', 'fix-done'],
  leg: ['activism', 'institution', 'enterprise'],
  affected_led: ['yes', 'no', 'partial'],
  representation_unit: ['local-affected', 'central-org', 'enterprise', 'central-at-named-legitimacy-cost'],
  actor_type: ['org', 'individual'],
  actor_depth: ['registry', 'tracked'],
  lifecycle: ['operating', 'scaling', 'distressed', 'dormant', 'acquired', 'shut', 'won-and-dissolved'],
  stance: ['works-the-remedy', 'neutral', 'organised-against-remedy', 'ambiguous'],
  source_kind: ['website', 'rss', 'newsletter', 'x', 'linkedin', 'instagram', 'youtube',
    'facebook', 'substack', 'annual-report', 'press', 'filings', 'other'],
  source_status: ['live', 'stale', 'dead', 'none-found'],
  need_kind: ['money', 'people', 'data', 'legal', 'distribution', 'introductions',
    'policy-access', 'technology', 'other'],
  offer_kind: ['reach', 'data', 'fieldwork', 'legal', 'convening', 'technology',
    'capital', 'credibility', 'other'],
  need_state: ['open', 'partially-met', 'met', 'withdrawn', 'unknown'],
  relationship: ['not-contacted', 'contacted', 'in-conversation', 'connected'],
  connection_state: ['hypothesis', 'proposed', 'introduced', 'engaged', 'declined', 'dead'],
  need_file_status: ['first-sweep', 'standard', 'leafed'],
  actor_leaf_role: ['primary', 'supporting'],
};

const en = (k) => z.enum(E[k]);

// YAML parses an empty key (`parent:`) as null. The record templates ship such
// keys, so every optional field is null-prone. Strip nulls recursively before
// validation so `.optional()` sees an absent key, not an explicit null.
export const stripNulls = (v) => {
  if (Array.isArray(v)) return v.map(stripNulls);
  if (v && typeof v === 'object' && !(v instanceof Date)) {
    const o = {};
    for (const [k, val] of Object.entries(v)) if (val !== null) o[k] = stripNulls(val);
    return o;
  }
  return v;
};
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'expected YYYY-MM-DD');
const slug = z.string().regex(/^[a-z0-9]+(-[a-z0-9]+)*$/, 'expected a kebab-case slug');
// connection ids join two actor slugs with `--` before the context slug
// (data-model.yaml: `mlpc--warrior-moms-silicosis`).
const pairSlug = z.string().regex(/^[a-z0-9]+([-]{1,2}[a-z0-9]+)*$/, 'expected a kebab-case slug (with `--` pair separator)');
const list = (t) => z.array(t).default([]);

// actor -> leaf link. A bare slug (`silicosis-stone-industry`) or an object
// (`{id: silicosis-stone-industry, role: primary}`). Normalised to {id, role},
// role defaulting to `supporting` so existing bare-slug lists keep working.
const actorLeafRef = z.array(z.union([
  slug.transform((id) => ({ id, role: 'supporting' })),
  z.object({ id: slug, role: en('actor_leaf_role').default('supporting') }).passthrough(),
])).default([]);

// `updated:` is often written unquoted in YAML and parses to a Date. Accept both.
const asDate = z.preprocess(
  (v) => (v instanceof Date ? v.toISOString().slice(0, 10) : v), date);

export const sourceRef = z.object({
  title: z.string().optional(), org: z.string().optional(),
  year: z.number().int().optional(), url: z.string().optional(),
}).passthrough();

export const needSchema = z.object({
  id: slug, tier: z.number().int().min(1).max(5), title: z.string(),
  order: z.number().int(), file: z.string(),
  status: en('need_file_status'),
  // definition + description now live in the tier file's lead area (leading `>`
  // blockquote, then prose), parsed in corpus.mjs — not fields here.
});

// A stub carries only these keys — assertion 7. Identity, placement and cheap
// classification are allowed (`nodes`, `onset`); anything that is a research
// output — `channel`, `satisfier_relation`, `agent`, `mechanisms`, `gap*`,
// `evidence`/`diagnosis` sections — is not, so a half-researched leaf cannot
// hide as a stub and make the researched/total counter lie.
export const STUB_KEYS = ['id', 'aliases', 'title', 'one_line', 'status', 'tier', 'need', 'geography', 'salience', 'scale', 'nodes', 'onset', 'updated'];

const leafBase = {
  id: slug, aliases: list(slug), title: z.string(), one_line: z.string(),
  status: en('record_status'), geography: z.array(z.string()).min(1),
  salience: z.number().int().optional(),
  scale: z.number().int().optional(),
  channel: en('channel').optional(),
  satisfier_relation: en('satisfier_relation').optional(),
  onset: en('onset').optional(),
  mechanisms: list(en('mechanism')),
  nodes: list(slug), gap: en('gap').optional(),
  gap_missing_leg: list(en('leg')), gap_note: z.string().optional(),
  gap_as_of: asDate.optional(),
  sources: list(sourceRef), updated: asDate, last_reviewed: asDate.optional(),
  actors: list(slug),
};

// `required: status == researched` — the conditional block of data-model.yaml.
const researchedRequires = (fields) => (o, ctx) => {
  if (o.status !== 'researched') return;
  for (const f of fields) {
    const v = o[f];
    if (v === undefined || (Array.isArray(v) && v.length === 0))
      ctx.addIssue({ code: 'custom', path: [f], message: `required when status: researched` });
  }
};

export const leafSchema = z.object({
  ...leafBase,
  tier: z.number().int().min(1).max(5),
  need: slug,
  agent: z.union([en('agent_physical'), en('agent_social')]).optional(),
  cross_cutting: list(en('cross_cutting_axis')),
}).superRefine(researchedRequires(
  ['channel', 'satisfier_relation', 'onset', 'agent', 'mechanisms', 'gap', 'gap_as_of']));

export const ccLeafSchema = z.object({
  ...leafBase,
  axis: en('cross_cutting_axis'),
  tiers: z.array(z.number().int().min(1).max(5)).min(1),
}).superRefine(researchedRequires(
  ['channel', 'satisfier_relation', 'onset', 'mechanisms', 'gap', 'gap_as_of']));

export const nodeSchema = z.object({
  id: slug, aliases: list(slug), title: z.string(), one_line: z.string(),
  type: en('node_type'), authority: z.string(),
  geography: z.array(z.string()).min(1),
  mechanisms: list(en('mechanism')), needs: z.array(slug).min(1),
  sub_levers: list(z.string()), actors: list(slug),
  status: en('node_status'), updated: asDate,
}).superRefine((o, ctx) => {
  if (o.type === 'sector' && o.sub_levers.length === 0)
    ctx.addIssue({ code: 'custom', path: ['sub_levers'], message: 'required when type: sector — a sector node with no enumerated sub-levers is not actionable' });
});

export const askRow = z.object({
  kind: z.string(), text: z.string(), as_of: asDate.optional(),
  source: z.string().optional(), state: en('need_state').optional(),
}).passthrough();

export const actorSchema = z.object({
  name: z.string(), slug: slug, id: slug.optional(), aliases: list(slug),
  type: en('actor_type'), depth: en('actor_depth').default('registry'),
  aka: list(z.string()), parent: slug.optional(), superseded_by: slug.optional(),
  affiliations: list(z.object({
    actor: slug, role: z.string().optional(),
    from: asDate.optional(), to: asDate.optional(),
  }).passthrough()),
  leg: z.array(en('leg')).min(1),
  affected_led: en('affected_led'),
  representation_unit: en('representation_unit'),
  stance: en('stance').default('works-the-remedy'),
  leaves: actorLeafRef, nodes: list(slug),
  geography: z.array(z.string()).min(1),
  lifecycle: en('lifecycle'), lifecycle_as_of: asDate,
  needs: list(askRow), offers: list(z.object({ kind: z.string(), text: z.string() }).passthrough()),
  sources: z.array(z.object({
    kind: en('source_kind'), url: z.string().optional(), handle: z.string().optional(),
    last_checked: asDate.optional(), status: en('source_status'),
  }).passthrough()).min(1, 'never an empty list — an actor with no reachable channel gets one row with status: none-found'),
  contact_route: z.string().optional(),
  followed: z.boolean(), followed_date: asDate.optional(),
  last_checked: asDate.optional(), updated: asDate,
}).superRefine((o, ctx) => {
  if (o.depth !== 'tracked') return;
  for (const f of ['needs', 'offers', 'contact_route']) {
    const v = o[f];
    if (v === undefined || (Array.isArray(v) && v.length === 0))
      ctx.addIssue({ code: 'custom', path: [f], message: 'required when depth: tracked' });
  }
});

export const connectionSchema = z.object({
  id: pairSlug, actors: z.array(slug).min(2), context: slug,
  gap_filled: z.string(), hypothesis: z.string(),
  state: en('connection_state'),
  date_proposed: asDate.optional(), date_introduced: asDate.optional(),
  outcome: z.string().optional(), updated: asDate,
}).superRefine((o, ctx) => {
  if (['engaged', 'declined', 'dead'].includes(o.state) && !o.outcome)
    ctx.addIssue({ code: 'custom', path: ['outcome'], message: `required when state: ${o.state}` });
});
