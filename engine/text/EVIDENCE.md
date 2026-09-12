# Engine evidence — the measurements behind the constants

Every threshold in `engine/text/` was measured, not inherited from the
literature. This file is the single record of what was measured, on what,
and what the result was. Module docstrings state the *argument*; the
numbers live here, and the assertions that re-derive them live in
`engine/tests/`.

Rule: if a number here is load-bearing for a constant, a test must
re-derive it. A number no test checks is a claim, not evidence.

---

## The sample

**`silicosis-rajasthan-2026-09`** — three search queries on
silicosis / Rajasthan, September 2026, **21 result URLs**. Ground truth
established by hand. This one sample backs both gate 0 (preview dedup) and
the page-state classifier.

Verbatim fixtures:
- titles + URLs — `tests/test_preview.py:LIVE`
- fetched wall texts + status + body size — `tests/test_pagestate.py:WALLS`
- saved HTML — `tests/fixtures/live/`

Two hand-established ground truths:
- **3 duplicate groups** among the 21 URLs (same work, different host).
- **10 of the 21 pages were not documents** — bot walls, cookie walls, JS
  shells, one Apache 403, one empty body.

---

## §preview-vs-simhash — why dedup happens before the fetch

| method | duplicate groups found (of 3) | fetches needed (of 21) |
|---|---|---|
| title-level preview grouping | **3** | **14** |
| post-fetch SimHash | 1 | 21 |

Re-derived by: `tests/test_preview.py::test_fetch_list_collapses_the_set`

Two reasons preview grouping wins, both structural rather than incidental:

1. Four of the 21 URLs **could not be fetched at all** (403 / empty body).
   Post-fetch dedup can never see these. Gate 0 grouped three of them with
   the PMC copy of the same paper, and the content came from there.
2. The DOI was sitting in the Ovid URL itself — free, and it matches the
   same work rendered at different lengths by different hosts, which no
   text comparison can do.

### Containment vs Jaccard

On the measured set, one true duplicate pair (keys `02` / `21`, the same
paper at two hosts) scored:

| measure | score |
|---|---|
| containment (overlap / shorter title) | **1.00** |
| Jaccard | 0.33 |

Search engines truncate titles, so one side is routinely a stem of the
other. `DEFAULT_CONTAINMENT = 0.85`.

Re-derived by: `tests/test_preview.py::test_containment_beats_jaccard_on_truncated_titles`

### Why `confirm` exists

Containment alone merges generic titles — "About us" is contained in
"About us | Mine Labour Protection Campaign" at 1.00, and so is
"Silicosis-An Ancient Disease" in its own full title. Both are short
prefixes; no minimum-token floor separates them. Hence the third verdict.

Genericness is a property of the **language**, not of the candidate batch.
Measuring it as batch IDF fails: in a 21-URL batch a generic phrase looks
rare. Hence the hand-curated `_COMMON` set rather than a computed score.

---

## §simhash-perturbation — why `MIN_SHINGLES = 200`

Wrapping a document in site boilerplate moves its SimHash. Below some
length the perturbation exceeds `DEFAULT_THRESHOLD = 3` and **real
duplicates are missed**, so short documents must fall through to the
embedding pass rather than be declared unique here.

Hamming distance between a document and the same document wrapped in
boilerplate, by document length and weight of wrapper
(k=4, 64-bit, measured 2026-09-12):

| words | shingles | light wrapper (6w) | medium (9w) | heavy (28w) |
|---|---|---|---|---|
| 51  | 48  | 8 | 12 | 16 |
| 102 | 99  | 4 | 8  | 9  |
| 153 | 150 | 3 | 4 | 8 |
| 204 | 201 | **2** | **2** | **3** |
| 306 | 303 | 0 | 1  | 1  |
| 408 | 405 | 0 | 0  | 0  |

Re-derived by: `tests/test_text.py` — `test_perturbation_curve` (the full
table, pinned exactly), `test_min_shingles_floor_holds_against_every_wrapper_weight`
(the guarantee), `test_just_below_the_floor_is_not_reliable` (the exclusion)

**Where the floor is set, and why there.** 201 shingles is the first row
where *every* wrapper weight stays within `DEFAULT_THRESHOLD` — light 2,
medium 2, heavy 3. That is the property the constant has to guarantee: at
or above the floor, a boilerplate-wrapped document still reads as a
duplicate no matter how heavy the chrome. Below it, the guarantee is
conditional on boilerplate being light, which is not a condition the
fetcher can enforce.

The floor was `150` until 2026-09-12. That row holds only against the
light wrapper, where it lands exactly on the threshold (3 ≤ 3); the same
153-word document under a realistic heavy wrapper — nav, share bar,
copyright line — moves **8 bits**, so `is_reliable` was returning True at
a length where a real duplicate was missed anyway. Raised to `200`.

The cost is real and was accepted deliberately: documents between ~150 and
~200 shingles (roughly 150-200 words) no longer settle at tier 0 and fall
through to the cross-lingual embedding pass, which is the expensive one.
The trade is a larger embedding bill against silent false uniques, and
false uniques are the worse failure — a missed duplicate enters the corpus
as a second source and corrupts the count.

An earlier version of this note recorded "9 bits at 53 words, 7 at 106,
1-2 from ~150 on". The shape is right; the exact figures did not
reproduce, and the 150 floor rested on them. That is why the curve is now
a parametrized test rather than prose.

### Shingle size

`k=4` separates cleanly and the choice is not delicate:

| relation | distance at k=4 |
|---|---|
| boilerplate-wrapped (long doc) | 0–1 |
| reworded version of the same story | 15 |
| unrelated document | 28 |

Re-derived by: `tests/test_text.py` — `test_boilerplate_wrapper_is_a_duplicate_once_long_enough`,
`test_reworded_article_stays_distinct`, `test_unrelated_text_is_not_a_duplicate`

### Why `BANDS = 4`

Not measured — proved. Two hashes within Hamming distance 3 must agree on
at least one of 4 bands, because 3 differing bits cannot dirty 4 disjoint
bands. Indexing every document under its 4 band keys loses nothing at the
default threshold.

### What SimHash cannot do

A Marathi article and its English translation share almost no shingles;
their distance is indistinguishable from noise. This is the limitation
that justifies the cross-lingual embedding pass, which runs only on what
survives here.

Re-derived by: `tests/test_text.py::test_translation_is_not_caught_by_simhash`

---

## §pagestate-walls — why status codes are not enough

Of the 21 fetched pages, **10 were not documents**. They still produce
text, so without a classifier they enter the corpus as sources — the three
ResearchGate walls yielded 33 words each of "We've detected unusual
activity from your network".

**Only 5 of the 10 were 4xx.** The other five returned a success status:

| host | status | what it served |
|---|---|---|
| Springer | 200 | "JavaScript is disabled in your browser" |
| PressReader | 200 | 10KB that cleans to its own site name |
| PubMed | 203 | cookie wall |
| ResearchGate ×3 | 403 | bot wall, 33 words |
| Apache (oldcollab.co.za) | 403 | 305-byte "Forbidden" |

So a wall phrase must **outrank** a success status in `assess()`. Every
phrase in `_WALL` is drawn from a page in this set or is the standard
wording of a challenge vendor.

Re-derived by: `tests/test_pagestate.py` (the `WALLS` table is these pages,
verbatim)

### Constants

- `MIN_DOCUMENT_WORDS = 120` — below this a page is `thin`: real but not
  full text. Word count alone **never** condemns a page; only a wall
  phrase, a challenge fingerprint or a refusing status yields `blocked`.
- `JS_SHELL_WORDS = 50` / `JS_SHELL_BYTES = 4000` — a large body that
  cleans to almost nothing is a client-rendered shell, not a short
  document. Sized from the Springer (3036B) and PressReader (~10KB) cases.
- Phrase check reads only `text[:1200]` — a legitimate article may discuss
  captchas or mention a paywall further down.

---

## §clean-reduction — why the strip is load-bearing twice

1. **Cost.** A raw page is ~15k tokens; the text inside it is ~3k. Nothing
   above tier 0 should ever see nav, scripts, cookie banners or footers.
2. **Dedup correctness.** SimHash on uncleaned text misses real duplicates
   outright — see §simhash-perturbation. Site boilerplate is a large share
   of a short page's features, so the strip in `clean.py` is load-bearing
   for dedup, not only for token cost.

---

## Open calls

- `_COMMON` is hand-curated and therefore English- and India-biased; a
  Marathi or Hindi title set has not been measured against it.
- The wrapper weights are three hand-built samples, not a distribution
  drawn from real sites. The heavy wrapper is a plausible worst case, not
  a measured one — if real boilerplate is routinely heavier, the floor is
  still too low.

## Changelog

- **2026-09-12** — `MIN_SHINGLES` 150 → 200. The original figures did not
  reproduce; 150 held only against light boilerplate. Curve pinned as a
  test at the same time.
