# PoC-2d results — the enlarged schema parses; one rule is unmeasured

Run 2026-09-14, pinned fixtures, free rung, 10 calls (5 actors x 2 arms), no
HTTP. Control arm = `worker/prompts.py` at `80f1935`, read out of git and
paired with the unmarked body it was written for.

## Headline

| | live | control |
|---|---|---|
| parsed | 5/5 | 5/5 |
| answers | 49 | 63 |
| valid source ids | 46/49 | 63/63 |
| chunk markers cited | 47/49 | 0/63 |
| markers resolving to a real `chunk_ref` | 47/47 | — |
| markers naming the wrong source | 0 | — |
| problem emits | 0 | 0 |
| `claims` volunteered unasked | 0 | — |
| output tokens | 26,995 | 26,771 |

**The schema is safe.** 10/10 parsed, none truncated, no retries needed. The
four-way revision costs nothing in parse reliability, and it is token-neutral
(+0.8%) — the chunk markers are paid for by dropping `claims`.

**Rule 5 works, and it is the whole point of the revision.** 47 of 49 answers
cite a marker; every one of them resolves; none names the wrong source.
`finding.chunk_ref` goes from *never filled in the history of the project* to
96% of answers. §9's "audit a wrong answer back to the passage" works for the
first time.

## Two findings that are not the headline

**1. `signals` was being asked for somewhere the model never goes.** Zero
problem emits across all ten calls — but that is not "the model found no
problems". It found 23:

```
emits by kind : {'actor': 31}
edges by dst  : {'problem': 23, 'actor': 24, 'org': 2, 'individual': 1}
edges by kind : {'works_on': 24, 'affiliated': 13, 'funds': 9, ...}
```

Every problem arrived as a `works_on` edge destination; not one arrived as an
emit. The prompt's own two sentences produce exactly that split — `emits` is
defined as "other organisations or named individuals" with six examples, all
actors, while `edges` explicitly admits "actor or problem". The model was
doing as told. The `"kind": "problem"|"actor"` enum in the schema line is the
only hint a problem emit is permitted, and an enum does not override a prose
definition.

So §10's JSON block, which puts `signals` on the problem emit, named an
object the prompt has never elicited — and `worker.py`'s own comment
("this is the only place one turns into a candidate at all") says the edges
loop is where problems become candidates. **Acted on after this run**:
`signals` moved to the `works_on` edge in both batched prompts, and the mint
reads `signals_from_edge(edge)` again. That means the ten calls here were
made against the superseded placement and **no response in hand carries a
populated `signals` key** — the rule is still unverified end to end.

**2. A list-valued answer is silently dropped, and the prompt invites it.**
Three of `anthill-ventures__live`'s eleven answers were discarded by
`parse_answers` as "missing/empty answer text". They were not empty:

```json
{"question_id": "q3_legs",           "answer": ["enterprise"]}
{"question_id": "q5_ecosystem_role", "answer": ["funder", "convener"]}
{"question_id": "q15_ask_offer",     "answer": ["funding", "strategic insight", ...]}
```

`_ACTOR_SYSTEM` describes exactly these fields as "a JSON list from
activism/institution/enterprise/service" and "(JSON list from funder,
intermediary, …)", and then the answers schema shows `"answer": "..."` — a
string. The model followed the field description; the parser follows the
schema. This is pre-existing (it is not caused by the revision) but it is a
silent loss of real answers on the fields most likely to be lists, and the
log line misreports it as empty.

## The one number that moved, and why it should not be over-read

Answers fell 63 -> 49. That is **one cell**, not a pattern:

| actor | control answers / distinct sources | live answers / distinct sources |
|---|---|---|
| selco-foundation | 20 / 2 | 19 / 2 |
| bku-ekta-ugrahan | **23 / 3** | **11 / 1** |
| bhavreen-kandhari | 8 / 2 | 8 / 2 |
| anthill-ventures | 12 / 1 | 11 / 1 |
| jyoti-pande-lavakare | 0 / 0 | 0 / 0 |

Four of five are flat. bku's control answered nine questions from three
sources each (14 duplicate-question answers); its live call answered eleven
questions once each. The tempting story — rule 5's "the ONE chunk you read it
from" nudges the model to one source per question — is **not supported**,
because selco kept 8 duplicate-question answers in both arms. At one
observation per cell this is indistinguishable from run-to-run variance.

**This matters for 2c specifically.** Reconciliation requires the model to
consult two sources on the same question. If rule 5 does suppress
multi-source answering, 2c would measure zero reconciliation for a reason
unrelated to rules 1 and 2 — the exact confound 2d exists to catch. Before
2c runs, this needs repeats on bku: 3 live calls and 3 control, same fixture,
scoring distinct-sources-per-question. Six calls, free rung.

## What 2d settles

- The revision may stand. No parse regression, no attribution regression
  attributable to it, no token cost.
- `chunk_ref` is live. E0's column stops being empty.
- `resolve_chunk_marker`'s wrong-source refusal is **defensive, not
  load-bearing** — 0 occurrences at n=47. Keep it; do not cite it as
  load-bearing.
- 2c is not yet safe to run. One measurement stands between them.
