# Gate-2 band sweep — 2026-09-14

Not a planned PoC. Run to answer "can the worker filter wrong URLs before the
extraction call", using the five PoC-2 fixtures' full URL pools against the now-
working fetch cache (~200 URLs, zero HTTP, local encoder only).

Method: `worker/gate2.confirm(name, context, cleaned_text)` on every pooled URL
that has cached text, once with `context=""` and once with the actor record's
own one-line description. Bands as shipped: `MISMATCH_BELOW=0.55`,
`CONFIRMED_ABOVE=0.80`.

## Result 1 — the mismatch band is dead code

Lowest cosine observed across ~200 URLs: **0.712**. Nothing reaches 0.55. No
source has ever been dropped by a `mismatch` verdict, and none can be under
these constants. `e5-small` compressing similarity into a narrow high band
(§8, AUC 0.923 on 0.041 mean separation) is exactly what this shows.

## Result 2 — `uncertain` is where all the junk is, and `uncertain` is KEPT

`confirm_policy.apply_confirmations` keeps UNCERTAIN (correctly, per gate2's
"never a silent fail"). But keeping it means it enters the extraction prompt,
which resolves it as a pass. The 0.55-0.80 band in this sweep holds: AED→PHP
currency converters (8 of them), Filipino dessert recipe blogs (9),
"how to get help in Windows" (7), sanitary-pad product listings (6),
`360.cn` portal pages (6), trophy shops (5), `jiosaavn.com`,
`github.com/0xk1h0/ChatGPT_DAN`. Roughly 60 of ~200 URLs, essentially all junk.

**This is the leak.** Not a missing filter — a filter whose reject bucket is
wired to "keep".

## Result 3 — `CONFIRMED_ABOVE = 0.80` is well calibrated, but only with context

Empty context inverts on name collisions. With the actor's one-line context:

| actor | genuine pages | junk | verdict |
|---|---|---|---|
| `bku-ekta-ugrahan` | 14 confirmed, min **0.811** | max **0.797** | clean separation |
| `selco-foundation` | 10 confirmed, min 0.848 | max 0.775 | clean separation |
| `anthill-ventures` | 29 confirmed, min 0.831 | max 0.796 | clean separation |
| `jyoti-pande-lavakare` | overlap 0.789-0.813 | — | **fails** |

The deltas carry the signal, not the absolute number. Adding context *lowers*
the score of a wrong-entity name collision (`jyoti.co.in` -0.034, `360.cn`
-0.024) and *raises* a genuine topical page (+0.03 to +0.10).

`jyoti-pande-lavakare` is the hard case and the reason not to over-fit: four
wrong-entity pages (`jyoti.com` 0.813, `screener.in/company/JYOTICNC` 0.804,
`jyoti.co.in` 0.803, `jyotiindia.com` 0.801 — a water heater manufacturer)
score above her own LinkedIn post (0.789) and her own book (0.790). A common
Indian given name defeats a 500-char cosine at any single threshold.

## Result 4 — every remaining false positive is a thin page

`vnrvjietexams.net` 86w (0.818), `music.youtube.com` 24w (0.815),
`support.google.com/mail` (0.831). `THIN_PAGE_CHARS`, parked unset in
`confirm_policy.py:66` awaiting exactly this data, would catch all three.

## What this does not establish

Five actors, one encoder, one 500-char preview window, and the "genuine vs
junk" labels are the author's eye, not an independent ground truth. It is
enough to show the band is misplaced and the reject bucket is miswired. It is
not enough to fix a number to three decimal places — and `jyoti` shows a
single global threshold cannot be right for both an org and a common personal
name.

## What was changed on the strength of this (2026-09-14)

- `worker/gate2.py`: `MISMATCH_BELOW` 0.55 -> 0.78. `CONFIRMED_ABOVE` left at
  0.80 — the sweep supports it.
- `search/confirm_policy.py`: `THIN_PAGE_CHARS` None -> 700; a third route
  (`PROMPT` / `VERIFY` / `DROP`) so `uncertain` can be kept without being put
  in the prompt; `prompt_set_is_thin()` as the fallback trigger.
- `worker/prompts.py`: `verify_and_extract_prompt_batched` +
  `parse_verified_answers` — the pass that reads the bucket.
- `worker/worker.py`: the pass wired into `run_batch`, including the seed URL,
  which bypassed the policy entirely.
- `03-worker.md` §6a, and §14 item 6.

The `jyoti-pande-lavakare` case is the one this sweep could not fix with a
number, and it is the reason the verify pass exists rather than a stricter
threshold.
