// One corpus load per build, shared by every page.
import { marked } from 'marked';
import { loadCorpus } from './corpus.mjs';

export const corpus = loadCorpus();
if (corpus.errors.length) {
  for (const e of corpus.errors) console.error(`ERROR ${e}`);
  throw new Error(`${corpus.errors.length} corpus error(s) — refusing to build the site.`);
}

marked.setOptions({ mangle: false, headerIds: false });
// `~` is used throughout the corpus as "approximately". GFM reads a lone `~` as
// a strikethrough delimiter, so two of them in a paragraph strike the text
// between. Escape single tildes; leave real `~~strikethrough~~` intact.
const deTilde = (s) => s.replace(/(^|[^~])~(?!~)/g, '$1\\~');
export const md = (s) => (s ? marked.parse(deTilde(s)) : '');
export const mdInline = (s) => (s ? marked.parseInline(deTilde(s)) : '');

export const TIER_NAME = corpus.tiers;
export const needsByTier = (t) => corpus.needs.filter((n) => n.tier === t);
export const leaf = (id) => corpus.allLeaves.find((l) => l.id === id);
export const actor = (id) => corpus.actors.find((a) => a.id === id);

export const statusTag = (s) =>
  ({ stub: 'warn', researched: 'ok', stale: 'alarm' })[s] ?? '';
export const gapTag = (g) =>
  ({ none: 'ok', coverage: 'warn', representation: 'alarm' })[g] ?? '';

// Verified surface — what the default (filtered) view shows. A leaf is verified
// once it is off `stub`; a need once its topic file is past `first-sweep`. A
// tier counts as having verified content if any of its needs qualifies either way.
export const isVerifiedNeed = (n) => n.status !== 'first-sweep';
export const isVerifiedLeaf = (l) => l.status !== 'stub';
export const needShown = (n) => isVerifiedNeed(n) || n.leaves.some(isVerifiedLeaf);
export const tierHasVerified = (t) => needsByTier(t).some(needShown);

// Every leaf missing at least one leg — /gaps, the catalyst's queue.
export const gapQueue = () => corpus.allLeaves
  .filter((l) => l.gap && l.gap !== 'none')
  .sort((a, b) => (a.gap === b.gap ? 0 : a.gap === 'representation' ? -1 : 1));
