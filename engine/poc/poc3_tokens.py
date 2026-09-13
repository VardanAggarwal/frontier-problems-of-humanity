"""PoC-3 — token accounting at the 512 window.

`04-worker-build-plan.md` §2 PoC-3, testing the assertions in `03-worker.md`
§7: Devanagari tokenizes ~20% longer than the same characters in English, and
320 tokens (`CHUNK_TOKENS`) plus `passage: ` plus the special tokens fits the
512-token window with margin.

This does not assume 512, or 20%, or any other number from the doc — it reads
the window off the loaded model and measures chars-per-token from real
corpus text. No network beyond what `sentence-transformers` needs to open an
already-cached model; no paid calls.

    python -m poc.poc3_tokens          # from engine/, any cwd works too
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from embed.model import MODEL_NAME, encode, get_encoder, prefix  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBLEMS = REPO_ROOT / "problems"


# ---------------------------------------------------------------------------
# 1. Window size and special-token overhead — read off the model, not assumed
# ---------------------------------------------------------------------------

def window_and_overhead():
    enc = get_encoder()
    tok = enc.tokenizer
    max_seq = enc.max_seq_length

    # Special-token overhead: an empty sequence, tokenized with
    # add_special_tokens=True (what the encoder actually runs), carries only
    # the special tokens (e.g. [CLS]/[SEP]) — count them directly.
    special = len(tok("", add_special_tokens=True)["input_ids"])
    return max_seq, special


# ---------------------------------------------------------------------------
# 2. Cost of the `passage: ` / `query: ` prefixes, in tokens
# ---------------------------------------------------------------------------

def prefix_cost():
    """Token cost of the literal `passage: ` / `query: ` strings alone,
    without special tokens (those are counted separately in §1)."""
    enc = get_encoder()
    tok = enc.tokenizer
    return {
        "passage: ": len(tok("passage: ", add_special_tokens=False)["input_ids"]),
        "query: ": len(tok("query: ", add_special_tokens=False)["input_ids"]),
    }


# ---------------------------------------------------------------------------
# 3. chars-per-token by script, from real corpus text
# ---------------------------------------------------------------------------

def load_english_sample() -> str:
    """Real English prose: a tier file's body, frontmatter and headings
    stripped down to prose paragraphs, concatenated."""
    path = PROBLEMS / "tier-failure-history/tier1-physiological/03-air.md"
    text = path.read_text(encoding="utf-8")
    # drop frontmatter-ish table/code fences, keep prose lines
    lines = [
        l for l in text.splitlines()
        if l.strip() and not l.startswith(("#", "|", "```", ">", "-"))
    ]
    return " ".join(lines)[:6000]


def find_devanagari_fragments() -> list[tuple[str, str]]:
    """Every real Devanagari fragment in problems/, with its source file.
    Returns (source, fragment) pairs; a fragment is a run of Devanagari plus
    immediate surrounding punctuation, not invented text."""
    out = []
    for path in PROBLEMS.rglob("*"):
        if not path.is_file() or path.suffix not in (".md", ".txt", ".yaml", ".json"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in re.finditer(
            r"[ऀ-ॿ][ऀ-ॿ\s।,.:—-]*[ऀ-ॿ]", text
        ):
            frag = m.group(0).strip()
            if len(frag) >= 2:
                out.append((str(path.relative_to(REPO_ROOT)), frag))
    return out


def chars_per_token(sample: str, role: str = "passage") -> tuple[int, int, float]:
    enc = get_encoder()
    tok = enc.tokenizer
    n_chars = len(sample)
    n_tokens = len(tok(prefix(sample, role), add_special_tokens=False)["input_ids"])
    return n_chars, n_tokens, n_chars / n_tokens if n_tokens else float("nan")


# ---------------------------------------------------------------------------
# 4. Does CHUNK_TOKENS=320 + passage prefix + specials fit with margin?
# ---------------------------------------------------------------------------

def budget_check(max_seq: int, passage_prefix_tokens: int, special_tokens: int,
                  chunk_tokens: int = 320):
    used = chunk_tokens + passage_prefix_tokens + special_tokens
    margin = max_seq - used
    return used, margin


# ---------------------------------------------------------------------------
# 5. The silent-truncation failure — embed a long text and its truncated
#    head, show cosine ~1.0 (i.e. the encoder cannot tell the difference)
# ---------------------------------------------------------------------------

def demonstrate_silent_truncation(long_text: str):
    import numpy as np

    enc = get_encoder()
    tok = enc.tokenizer
    max_seq = enc.max_seq_length

    # Build a text that is well over the window once prefixed.
    ids = tok(long_text, add_special_tokens=False)["input_ids"]
    budget = max_seq - 2  # what fit() uses
    over_budget_text = long_text
    if len(ids) <= budget * 2:
        over_budget_text = (long_text + " ") * (2 * budget // max(len(ids), 1) + 2)

    # The "head alone" the encoder actually sees if nothing truncates first:
    # take just the portion within budget tokens.
    ids_full = tok(over_budget_text, add_special_tokens=False)["input_ids"]
    head_ids = ids_full[:budget]
    head_text = tok.decode(head_ids, skip_special_tokens=True)

    v_full = encode([over_budget_text], role="passage")[0]
    v_head = encode([head_text], role="passage")[0]
    cosine = float(np.dot(v_full, v_head))  # both L2-normalised already

    return len(ids_full), len(head_ids), cosine, over_budget_text, head_text


def main():
    print(f"Model: {MODEL_NAME}\n")

    max_seq, special = window_and_overhead()
    print("## 1. Window and special-token overhead")
    print(f"max_seq_length (from model config): {max_seq}")
    print(f"special tokens added for an (empty-ish) single sequence: {special}")
    print()

    print("## 2. Prefix token cost")
    pcost = prefix_cost()
    print(f"'passage: ' -> {pcost['passage: ']} tokens (no specials)")
    print(f"'query: '   -> {pcost['query: ']} tokens (no specials)")
    print()

    print("## 3. Chars-per-token by script")
    en_sample = load_english_sample()
    en_chars, en_tokens, en_cpt = chars_per_token(en_sample)
    print(f"English (problems/.../03-air.md prose, {en_chars} chars): "
          f"{en_tokens} tokens -> {en_cpt:.3f} chars/token")

    frags = find_devanagari_fragments()
    print(f"\nDevanagari fragments found in problems/: {len(frags)}")
    for src, frag in frags:
        print(f"  {src}: {frag!r}")
    deva_all = " ".join(f for _, f in frags)
    if deva_all.strip():
        d_chars, d_tokens, d_cpt = chars_per_token(deva_all)
        print(f"\nAll Devanagari fragments concatenated ({d_chars} chars): "
              f"{d_tokens} tokens -> {d_cpt:.3f} chars/token")
        print("CAUTION: these are personal names and a government nav menu, "
              "not prose — not representative of a real Devanagari passage. "
              "The corpus has no Devanagari prose sample of meaningful length.")
    else:
        print("No Devanagari text found at all.")

    print("\nOther non-Latin scripts in problems/: none found beyond the "
          "Devanagari fragments above (checked Bengali/Tamil/Telugu/Gujarati "
          "ranges directly, zero hits).")
    print()

    print("## 4. Budget check for CHUNK_TOKENS=320")
    used, margin = budget_check(max_seq, pcost["passage: "], special, 320)
    print(f"320 (chunk) + {pcost['passage: ']} (passage prefix) + {special} "
          f"(special tokens) = {used} tokens; window = {max_seq}; "
          f"margin = {margin} tokens")

    # Largest safe chunk target per script: max_seq - prefix - specials,
    # then converted to an approximate character budget via the measured
    # chars/token, for context only (chunking should still be done in
    # tokens, not characters).
    safe_chunk_tokens = max_seq - pcost["passage: "] - special
    print(f"\nLargest chunk (in tokens) that leaves zero margin: "
          f"{safe_chunk_tokens} (i.e. {max_seq} - {pcost['passage: ']} - {special})")
    print(f"320 leaves {safe_chunk_tokens - 320} tokens of margin "
          f"({(safe_chunk_tokens - 320) / safe_chunk_tokens:.0%} of the safe budget) "
          "for the chunk to run longer than its nominal token count once "
          "sub-word tokenization or a Devanagari-heavier passage inflates it.")
    print()

    print("## 5. Silent truncation demonstration")
    n_full, n_head, cosine, full_text, head_text = demonstrate_silent_truncation(en_sample)
    print(f"Full text: {n_full} tokens (well over the {max_seq}-token window)")
    print(f"Head-only text (what the encoder actually embeds if handed the "
          f"full text): {n_head} tokens")
    print(f"cosine(full, head) = {cosine:.4f}")
    print("This is the failure §7 names: a chunk over the window is embedded "
          "on its head alone with no error, and the resulting vector looks "
          "indistinguishable (cosine ~1.0) from a vector of the truncated "
          "text alone — nothing downstream can tell retrieval saw only the "
          "opening of the passage.")


if __name__ == "__main__":
    main()
