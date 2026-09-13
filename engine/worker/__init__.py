"""Build step 3 (01-minimal.md §5, §11) — the worker with all four gates, plus
entity resolution.

`config` + `llm` are the ported compute-cascade tier-4 client (§7 — the paid
rung; tiers 0-3 are `text/` and `embed/`, already built). `prompts` is the
"two prompts, one loop" contract (§4): screening (gate 1) and claims
extraction, kind-conditioned but otherwise shared between problem and actor
processing. `fetch` is tier 0's network step. `gate1` and `gate2` are the
pre-fetch and post-fetch screens (§5, §8). `resolve` is Layer 4 entity
resolution (§8 Layer 4, §9). `worker` is the loop that wires them together
over one batch of already-admitted `candidate` rows.

Replaces `process-leaf`, `actor-channel-finder`, `impact-network-crawler` as
prompts against this one loop, per §4: "Problem Agent and Actor Processing
differ only in target table and prompt."
"""
