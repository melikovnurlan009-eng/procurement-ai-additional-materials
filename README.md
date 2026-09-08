# Additional Materials (Final)

## 1. What is this bundle?

The reproducibility companion to an MSc extended research project on retrieval-augmented
question answering over UK public procurement law: a hybrid lexical/dense/graph retriever, four
compared retrieval systems (`hybrid`, `legal_static`, `planned_multisearch`, `adaptive`), and a
two-track evaluation (a standalone 6-configuration static-retrieval benchmark, and a matched
DEV/TEST comparison of the four production systems). This is the *finalized* package,
audited and corrected against the earlier draft bundle (`ADDITIONAL_MATERIALS_BUNDLE_2026-09-07.zip`,
preserved unmodified) -- see `provenance/CHANGELOG_FINALIZATION.md` for exactly what changed.

## 2. What thesis system does it support?

The UK public procurement AI assistant described in the thesis report: corpus construction over
legislation/guidance sources, a legal-structural chunking and reference-graph pipeline, and a
retrieval/evaluation harness comparing static and LLM-controller-driven retrieval strategies.

## 3. What can be reproduced exactly?

- All aggregate metrics, tables, and figures from the already-saved per-scenario raw outputs
  (`results/`), offline, with no external API or database. See "Reproducibility Levels" below,
  Level 1-2.
- All frozen-code/config integrity (hash verification against `prw_freeze_record.json`).
- The full unit/integration test suite (60/60 passing).
- **The live retrieval application's `/search` and `/health` endpoints, rebuilt from the
  included corpus export** (2026-09-08: `code/corpus_export/data/*.jsonl` ships the actual final
  chunk/document/edge data, and `scripts/rebuild_search_index.py` reconstructs a working search
  index from it using the already-included `build_chunk_index.py` -- see item 10 and
  `TECHNICAL_APPENDIX.md` section 0.5 for the exact, tested sequence, including a real gap found
  and fixed while testing it). No pre-built database or vector-index binary is shipped -- you
  build the index yourself, once, from the included data.

## 4. What cannot be reproduced exactly?

- LLM-driven steps (controller planning/observation, judging, some corpus chunking) are not
  seeded; a fresh run will not produce byte-identical output, only architecturally comparable
  output under the same validated contract. See `environment/environment_notes.md`.
- The final Procurement Pathway *curation/refinement* step (raw crawl -> final annotated
  manifest) -- the discovery crawl itself is included and reproducible
  (`code/scrapers/procurement_doc_counter/`). See `provenance/missing_artifacts.md` section 1.
- The exact historical build environment for the corpus itself (no `pip freeze` was captured at
  build time). See `environment/environment_notes.md`.
- Independent (non-self-authoring) execution of the TEST split -- this was not done in the
  underlying research and cannot be retrofitted by this packaging pass. Disclosed in
  `results/final_reports/FINAL_FREEZE.json` and `TEST_FINAL_REPORT.md`.

## 5. Major directories

- **`code/`** -- all source, laid out to mirror the original repository's relative directory
  depths (so frozen import paths resolve without modification): corpus scrapers, chunking/
  ingestion scripts, the graph package (`procurement_kg/`), the production retriever
  (`chunk_retrieval.py`), the standalone benchmark
  (`evaluation/final_retrieval_benchmark/`, code *and* its data co-located, matching the
  original repo convention), the frozen evaluation package
  (`procurement_research_workbench_v1/`, including `prw/`, its tests, data, schemas, and
  configs), and **the deployed application layer**: `chunk_api.py` (the FastAPI service --
  `/health`, `/search`, `/answer`, `/refine`, `/chunk/{chunk_id}`, plus its own built-in minimal
  HTML page), its required siblings `answer_query.py`, `refine_query.py`, `query_expansion.py`
  (corrected in this pass -- an earlier version of this bundle mislabeled these as an unused
  demo and mis-placed them where `chunk_api.py`'s imports could not find them; see
  `TECHNICAL_APPENDIX.md` section 0.5), and `streamlit_app.py` (the fuller "Procurement KG
  Assistant" UI, talking to the same backend via `code/procurement_kg/ui.py`).
- **`corpus_manifests/`** -- the final, curated Procurement Pathway URL manifest (1,690 URLs).
  The discovery crawler that produced this source family's raw output is included separately at
  `code/scrapers/procurement_doc_counter/` -- see item 4 above.
- **`corpus_audit/`** -- independent audit of the corpus itself: exact snapshot counts, source
  inventory, lifecycle-coverage mapping, benchmark corpus-sufficiency check, and a corpus-
  construction manual/agent-QA audit (distinct from `results/final_reports/
  MANUAL_EVALUATION_AUDIT.md`, which covers the DEV/TEST evaluation stage).
- **`results/`** -- raw and derived DEV/TEST run/judgment artifacts (`runs/`, `judgments/`,
  `pool/`, `evaluate_output/`) and the final thesis-facing reports/tables/figures
  (`final_reports/`).
- **`environment/`** -- package versions, Python/OS, embedding/LLM model identifiers, and an
  explicit historical-vs-current distinction.
- **`scripts/`** -- `verify_freeze.py`, `verify_bundle.py`, `generate_manifests.py`.
- **`provenance/`** -- `artifact_manifest.csv`, `missing_artifacts.md`,
  `CHANGELOG_FINALIZATION.md`, `FINAL_VALIDATION_REPORT.md`, and
  `PAPER_CLAIMS_CROSSWALK.md` (every major numeric claim in the submitted thesis PDF,
  cross-checked directly against the artifacts in this bundle -- including one correction that
  still needs to be applied to the thesis report text itself, not only to this package).

## 6. What command verifies integrity?

```bash
python3 scripts/verify_freeze.py     # frozen code/config hashes vs prw_freeze_record.json
python3 scripts/verify_bundle.py     # full static validator (paths, secrets, manifests, tests, syntax)
```

## 7. What command runs tests?

```bash
cd code/procurement_research_workbench_v1
python3 -m pytest -q
```
60 passed, 0 failed (verified during this finalization pass).

## 8. What command recomputes reported tables?

```bash
cd code/evaluation/final_retrieval_benchmark
python3 candidate_ceiling.py              # reproduces the submitted PDF's own numbers exactly (15/40/5) -- kept unmodified on purpose, see below
python3 candidate_ceiling_CORRECTED.py    # corrected candidate-generation/ranking classification (24/31/5)
python3 build_final_tables.py             # FINAL_RESULTS_TABLE.csv, PER_SUITE_RESULTS.csv, PAIRWISE_STATISTICS.csv
python3 strict_target_recall.py           # judge-independent strict recall
```
All are pure functions of the already-saved retrieval-run/judgment JSONL files included in this
bundle; none calls an external API. **Note**: `candidate_ceiling.py` and
`candidate_ceiling_CORRECTED.py` deliberately produce *different* numbers from each other --
the first reproduces exactly what the submitted thesis PDF currently states (which is now known
to be wrong, per `provenance/PAPER_CLAIMS_CROSSWALK.md`); the second produces the corrected
figures that should replace them. This is not a bug in the bundle -- both are kept so the
report's own numbers stay independently verifiable.

## 9. What command recreates figures?

```bash
cd code/evaluation/final_retrieval_benchmark && python3 make_figures.py
cd ../../procurement_research_workbench_v1 && python3 scripts/make_final_figures.py  # if present
```

## 10. What external services are required (and for what)?

- **Qdrant** -- a *local Docker container you start yourself* (`docker compose up -d qdrant`),
  then populated by running `scripts/rebuild_search_index.py` against the included corpus
  export (`code/corpus_export/data/`). No pre-built database or vector-index snapshot is
  shipped; see `TECHNICAL_APPENDIX.md` section 0.5 for the exact, tested rebuild sequence
  (including real observed timing for the one genuinely slow step, embedding all 22,042 chunks
  on CPU).
- **OpenAI API key** -- still required, and still never included (a real credential cannot ship
  in a distributed package). Needed only for `/answer` and `/refine` (generation + verification);
  `/search`, `/health`, and everything in Levels 1-2 need no key at all. Copy `.env.example` to
  `.env` and fill in your own key.

## 11. What artifacts were deliberately omitted?

Per-scenario checkpoint caches and per-candidate judge-request caches, fully redundant with the
consolidated JSONL files that are included. Exact sizes, reasons, and restoration notes:
`provenance/missing_artifacts.md` section 4.

## 12. Where are known limitations documented?

`provenance/missing_artifacts.md` (artifact-level), `TECHNICAL_APPENDIX.md` section 17
(methodology-level), `provenance/CHANGELOG_FINALIZATION.md` (what was found and corrected during
this finalization pass).

## Reproducibility levels

**Level 1: Exact artifact verification.** Fully offline, using `MANIFEST.sha256` and
`scripts/verify_freeze.py` against the frozen code/config and already-saved outputs.

**Level 2: Result-table reproduction.** Fully offline, from the included raw scenario-level
outputs (`results/runs/`, `results/judgments/`) via `scripts/` in
`code/evaluation/final_retrieval_benchmark/` and `code/procurement_research_workbench_v1/prw`'s
own CLI (`python -m prw evaluate ...`). No external API calls.

**Level 3: Retrieval rerun.** Achievable directly from this bundle without the original corpus
database: `code/corpus_export/data/` ships the actual final chunk/document/edge data, and
`scripts/rebuild_search_index.py` rebuilds a working SQLite FTS5 + Qdrant index from it using the
already-included `build_chunk_index.py` (see item 10 above and `TECHNICAL_APPENDIX.md` section
0.5 for the exact sequence). You supply a local Docker install and, only for `/answer`/`/refine`,
your own OpenAI API key. **Run to completion and verified, not just tested on a sample**: all
three stages were run against the complete 22,042-chunk corpus (lexical + graph stages: exact
match to the documented counts; dense/embedding stage: 24m38s on CPU alone, producing exactly
22,042 vectors), and a real `/search` call against the finished, full-scale index returned the
correct result. See `TECHNICAL_APPENDIX.md` section 0.5 for the full timing data and the one
nuance found along the way (a genuinely missing schema column, found and fixed by testing).

**Level 4: End-to-end corpus rebuild.** Possible for every source family whose acquisition
scripts survive in this bundle (`code/scrapers/`), which now includes the Procurement Pathway
discovery crawl itself (`code/scrapers/procurement_doc_counter/`). The one remaining gap is
narrower: the curation/refinement step that turned that crawl's raw output into the final
annotated manifest is not reproducible this way (see `provenance/missing_artifacts.md`
section 1).

## Scientific language note

This package avoids "proves," "guarantees," "fully reproducible," "independently confirmed," and
"identical conditions" unless literally true for the specific claim at hand. Where a result
replicates on a second sample, or a metric is reproducible from included artifacts without being
independently executed, that distinction is stated explicitly throughout
`results/final_reports/` and this README.
