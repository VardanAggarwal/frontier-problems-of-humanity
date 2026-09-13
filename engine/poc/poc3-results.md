# PoC-3 results — token accounting at the 512 window

Run: `python -m poc.poc3_tokens` from `engine/`. Model
`intfloat/multilingual-e5-small`, loaded from local cache, no network calls
beyond opening it, no paid calls. Script: `engine/poc/poc3_tokens.py`.

Testing `03-worker.md` §7's claims: Devanagari tokenizes ~20% longer than the
same characters in English, and `CHUNK_TOKENS=320` plus `passage: ` plus the
special tokens fits the 512-token window with margin.

## 1. Window and overhead (read off the model, not assumed)

| Quantity | Value | Source |
|---|---|---|
| `max_seq_length` | **512** | `encoder.max_seq_length` — confirms the doc's assumed figure, not taken on faith |
| Special-token overhead | **2** tokens | empty string, `add_special_tokens=True` ([CLS]/[SEP]-equivalent pair) |
| `passage: ` prefix | **3** tokens | literal string, no specials |
| `query: ` prefix | **4** tokens | literal string, no specials |

## 2. Chars-per-token by script

| Sample | Chars | Tokens | Chars/token | Note |
|---|---|---|---|---|
| English prose (`problems/tier-failure-history/tier1-physiological/03-air.md`, prose lines only) | 2,728 | 742 | **3.677** | Real corpus text |
| Devanagari, all fragments found in `problems/` | 105 | 26 | 4.038 | See caution below |

**Devanagari fragments found (8, across 4 files):** `सिलिकोसिस पीड़ित संघ`,
`दिनेश रायसिंह` (×2, `problems/index.json` and
`problems/actors/dinesh-rai-singh.md`), `मोहन सुल्या` (×3, `index.json` and
twice in `problems/actors/mohan-sullia.md`), and `हरियाणा सरकार` / `हिन्दी`
from a scraped government-portal nav menu at
`problems/private/sources/e5824c56b2dd8ed5.txt`.

**Caution, stated explicitly per the task's instruction:** this is not a
usable Devanagari prose sample. It is eight fragments — two people's names and
two words from a site nav bar — totalling 105 characters, not sentences. The
corpus currently has **no Devanagari prose of meaningful length** anywhere
under `problems/`; a grep for Bengali, Tamil, Telugu and Gujarati unicode
ranges over the same tree returned zero hits, so no other non-Latin script is
present at all. The measured 4.038 chars/token for this fragment set is
*higher* than English, i.e. suggests Devanagari here tokenizes *shorter* per
character, which is the opposite of §7's ~20% claim — but this is almost
certainly an artefact of the sample being proper nouns (which subword-tokenize
differently from running prose) rather than a real disconfirmation. **§7's
20% figure could not be verified against this corpus** and should be treated
as an unverified assumption (consistent with published e5/mBERT tokenizer
behaviour on Devanagari, but not something this repo's own text confirms)
until a real Hindi/Marathi source is fetched by the worker.

## 3. Budget check for `CHUNK_TOKENS = 320`

```
320 (chunk) + 3 (passage prefix) + 2 (special tokens) = 325 tokens
window = 512
margin = 187 tokens (37% of the window)
```

Even under the conservative (unverified but doc-stated) assumption that a
Devanagari chunk of the same nominal token count runs ~20% longer once
re-tokenized in context, 320 × 1.2 ≈ 384 tokens, + 3 + 2 = 389, still 123
tokens under the window. **§7's assertion holds, with room to spare, on both
readings.**

Largest chunk that leaves *zero* margin: `512 − 3 − 2 = 507` tokens. 320 is
63% of that ceiling — the 37%-margin framing above says the same thing from
the other side.

## 4. Answering the task directly

- **Does 320 + prefix + specials fit with margin?** Yes — 187 tokens of
  margin (36.5% of the 512 window), confirmed against the real tokenizer, not
  assumed.
- **Largest safe chunk target per script:** the ceiling itself is
  script-independent — it's a token ceiling, not a character one (507 tokens,
  any script, per §1). What differs by script is how many *characters* that
  buys: at English's measured 3.677 chars/token, 320 tokens ≈ 1,177
  characters; if Devanagari really runs ~20% longer per §7's claim, 320 tokens
  buys only ≈ 980 characters of Devanagari text for the same token cost.
- **Cost of respecting the window vs. a naive character split:** the existing
  naive-char precedent in this repo is `texts.py`'s `MAX_CHARS = 2000`. At
  English's measured rate, 2,000 characters ≈ 544 tokens — **already over the
  512 window before any prefix or special token is added**, exactly the
  silent-truncation failure §7 warns about. A token-respecting chunk (320
  tokens ≈ 1,177 English characters) therefore needs **≈1.7×** as many chunks
  to cover the same source text as a naive 2,000-character split would assume
  it takes (2,000 / 1,177). For a hypothetical 20%-longer Devanagari passage,
  the same chunk-token target covers only ≈980 characters, so the same
  source length needs **≈2.0×** as many chunks as the naive split assumed
  (2,000 / 980). This is the real price of "respect the window when chunking"
  — more, smaller chunks — paid once, at chunk time, instead of being paid
  silently downstream as truncated retrieval.

## 5. The silent-truncation failure, demonstrated

Built a text well over the window (2,221 tokens, from the same English
sample repeated), then computed exactly what the encoder would see if handed
the whole thing versus its first 510 tokens (`max_seq_length − 2`, i.e. the
literal head that survives once specials are added):

```
full text:  2,221 tokens
head text:    510 tokens
cosine(full, head) = 1.0000
```

The two vectors are indistinguishable. Nothing in the encode call, the
returned vector, or its shape signals that ~77% of the source text (1,711 of
2,221 tokens) was silently dropped. This is exactly the failure `03-worker.md`
§7 names: `fit()` truncates correctly *when called*, but a chunk handed
straight to `encode()` over the window is embedded on its head alone, with no
error and no warning — which is the argument for enforcing `CHUNK_TOKENS` at
chunk-construction time rather than trusting `fit()` to catch an oversized
chunk later.

## Verdict

- §7's numeric claims **hold**: the window is confirmed at 512 (not assumed),
  and 320-token chunks + `passage: ` + special tokens leave 187 tokens (36.5%)
  of margin — safe even if Devanagari runs 20% longer, a figure this corpus
  could not itself verify for lack of real Devanagari prose (flagged, not
  invented).
- **Recommended chunk token target for track C: keep `CHUNK_TOKENS = 320`.**
  It is well inside the 507-token ceiling with margin to spare for both
  scripts actually present in this corpus (English; Devanagari only as
  short proper nouns). No evidence surfaced here justifies raising or
  lowering it — the number should be revisited only once the worker actually
  fetches Hindi/Marathi prose sources and a real chars-per-token figure for
  running Devanagari text can be measured, per §7's own instruction to
  "re-run when the corpus shifts language mix."
- The silent-truncation failure is real and reproducible: build the chunker
  to enforce `CHUNK_TOKENS` before `encode()` is ever called, not after.
