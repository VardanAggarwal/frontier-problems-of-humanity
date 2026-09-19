## 2026-09-18b — post-drop thin check, trailing fallbacks, log wording

**Still open, in priority order.** 
- Candidate concurrency (76% of wall time is
one blocking HTTP call per candidate and `run_batch` is a strict `for cid in
alive:`; `_openrouter_pace` is already a thread-safe lock built for concurrent
callers and serves exactly one — blocked on the shared sqlite conn).

- Gate 2 band precision (0.78/0.80, labelled
"provisional, not measured" in their own log line; 528 measures them). Why 552
put all 19 findings on 1 of 7 sources with zero misidentified flags, while 560
spread across 6 of 6.



Next steps for worker:
- Actors & Actor channels -> Need proper testing
  - None of the actors are mapped to problems that emitted them.
What to build first for orchestrator:
- Merging 2 actors/problems already minted
- Figure out early on whether actors are worth scraping
- Consider slow but always on type approach
- Link existing items together
  - Handle hierarchy better? Or build networks? Drop existing hierarchichal structure?
    - Can't capture what covers multiple needs
  - also solve topic-overlap as part of hierarchy solution