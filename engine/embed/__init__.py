"""Tier 1 of the compute cascade (01-minimal.md §7) — local embeddings, no API.

`model` owns the encoder and the e5 prefix contract; `index` owns the vec0
tables inside graph.db; `texts` decides what text stands for an entity;
`backfill` is the CLI that fills the index from the store.
"""
