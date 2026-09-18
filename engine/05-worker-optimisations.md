## 2026-09-18b — post-drop thin check, trailing fallbacks, log wording

**Still open, in priority order.** Candidate concurrency (76% of wall time is
one blocking HTTP call per candidate and `run_batch` is a strict `for cid in
alive:`; `_openrouter_pace` is already a thread-safe lock built for concurrent
callers and serves exactly one — blocked on the shared sqlite conn). PDF
extraction (37 PDFs dropped across three candidates while openai.com and
urbanacres.in blogspam got through). Gate 2 band precision (0.78/0.80, labelled
"provisional, not measured" in their own log line; 528 measures them). Why 552
put all 19 findings on 1 of 7 sources with zero misidentified flags, while 560
spread across 6 of 6.



Next steps for worker:
- Figure out how to tune research back to India if digressing
  - engine/worker/runs/2026-09-15T10-19-47-201Z-68881.log
- Handle PDFs
- Actors & Actor channels -> Need proper testing
What to build first for orchestrator:
- Resolving duplicates in candidates
  - Merging 2 actors/problems already minted
- Identifying which candidates are worth looking into - some sort of ranking?
- Consider slow but always on type approach
- Link existing items together
  - Handle hierarchy better? Or build networks? Drop existing hierarchichal structure?
