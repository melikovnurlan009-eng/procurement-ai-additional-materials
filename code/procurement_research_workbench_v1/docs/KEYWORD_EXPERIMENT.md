# Source-side keywords and contextual aliases

The existing project already contains a `keywords` field. This package does not overwrite it or assume that synonym enrichment is a proven solution.

## Isolated experiment

I0: same exported source text and existing retrieval metadata.

I1: I0 plus exact, source-supported keywords.

I2: I1 plus source-anchored abbreviations, spelling variants and contextual retrieval hints.

All three shadow indexes are built by the same function. Source text, chunk identities, candidate/query protocol and evaluated scenarios remain identical. Never compare a newly rebuilt index with a stale production result and attribute the difference to aliases alone. FTS5 document lengths and frequencies change when indexed text is added; report this intervention, not just the dictionary entries.

`prw.keywords.validate_enrichment` requires exact source quotations, limits terms, rejects introduced statutory locators and tracks the original text hash. A contextual hint is not a legal synonym: exclusion and debarment, participation and award criteria, and distinct direct-award routes must not be merged indiscriminately.

The enrichment model receives source data only, not DEV/TEST questions or relevance labels. DEV labels may select a global field-weight policy, but TEST wording cannot be mined into the alias field. Store generation model, prompt hash, all proposals and review status. Source-anchored proposals still need semantic scrutiny; an exact quote alone does not prove the suggested alias is appropriate.

## Commands

```bash
python scripts/enrich_sources.py --chunks YOUR_EXPORTED_CHUNKS.jsonl \
  --out runs/aliases --max-requests YOUR_APPROVED_CAP
```

This is a dry-run request plan until `--allow-network` is added. It uses the configured controller-model slot, but only source fields enter its payload. Export only query-eligible chunks with exact text; do not reuse stale rows or generated summaries as evidence.

```bash
python scripts/build_shadow_indexes.py --chunks YOUR_EXPORTED_CHUNKS.jsonl \
  --enrichments runs/aliases/enrichments.jsonl --out shadow/v1
```

These are research indexes, not replacements for the production FTS table. Use the search functions in `prw.shadow_fts` for a lexical-only experiment. Replacing the production lexical channel inside hybrid/adaptive evaluation needs a small explicitly versioned backend wrapper and its own tests. Dense embeddings remain unchanged unless a separate experiment changes them.

## Acceptance and reporting

Track anchor stability, precision losses on neighboring legal topics, relevance and coverage on ordinary queries as well as vocabulary mismatch. Keep the variant only if the development objective supports it; report regressions and uncertainty. Do not guarantee that adding aliases improves search.
