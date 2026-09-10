# Additional Materials

Reproducibility companion for the MSc thesis *A Legal-Structure-Aware Retrieval System for a UK
Public Procurement AI Assistant* (student 14322782, CSDI pathway): a hybrid lexical/dense/graph
retriever, four compared retrieval systems, and a two-track evaluation (a standalone
6-configuration static-retrieval benchmark, and a matched DEV/TEST comparison of the four
production systems). See `TECHNICAL_APPENDIX.md` for the full pipeline diagram and methodology.

## Prerequisites

- **Python 3.10 or later.** Check with `python3 --version`. If your default `python3` is older
  (e.g. macOS ships 3.9.x by default), install a newer one first -- `brew install python@3.12`
  (macOS/Homebrew) or `pyenv install 3.12 && pyenv local 3.12` -- then use that interpreter (e.g.
  `python3.12`) in place of `python3` below. Also upgrade pip first
  (`python3 -m pip install --upgrade pip`): an old bundled pip cannot editable-install a
  pure-`pyproject.toml` package at all.
- **git**, to have cloned this repository.
- **Docker**, only if you rebuild and run the live retrieval application (last section below).
- **An OpenAI API key**, only for the live application's `/answer`/`/refine` endpoints, or to
  rerun any LLM-driven step yourself (chunking, controller, judging).

Run every command below from the repository root (the directory this file is in).

## What this supports

The UK public procurement AI assistant described in the thesis report: corpus construction over
legislation/guidance sources, a legal-structural chunking and reference-graph pipeline, and a
retrieval/evaluation harness comparing static and LLM-controller-driven retrieval strategies. The
four compared retrieval systems: `hybrid` (lexical+dense fusion only), `legal_static` (`hybrid`
plus legal-authority priors and one-hop graph expansion, still no LLM call), `planned_multisearch`
(an LLM decomposes the query into sub-queries once, with no inspection of retrieved evidence), and
`adaptive` (an LLM decomposes the query and iteratively inspects retrieved evidence, bounded to 3
retrieval operations).

## Directory layout

- **`code/`** -- all source, laid out to mirror the original repository's relative directory
  depths: corpus scrapers, chunking/ingestion scripts, the graph package (`procurement_kg/`),
  the production retriever (`chunk_retrieval.py`), the deployed application layer
  (`chunk_api.py`, `answer_query.py`, `refine_query.py`, `query_expansion.py`,
  `streamlit_app.py`), the standalone benchmark (`evaluation/final_retrieval_benchmark/`), the
  evaluation package (`procurement_research_workbench_v1/`, including `prw/`, its tests, data,
  schemas, and configs), and `code/corpus_export/data/` (the actual final chunk/document/edge
  data exported from the evaluated corpus).
- **`corpus_manifests/`** -- the curated Procurement Pathway URL manifest.
- **`results/`** -- raw DEV/TEST run and judgment artifacts (`runs/`, `judgments/`, `pool/`,
  `evaluate_output/`) needed to regenerate the reported tables and figures.
- **`environment/`** -- package versions, Python/OS, embedding/LLM model identifiers.
- **`scripts/`** -- `verify_freeze.py`, `verify_bundle.py`, `generate_manifests.py`,
  `rebuild_search_index.py`.
- **`provenance/`** -- `artifact_manifest.csv`, `missing_artifacts.md`.

## Verify integrity

```bash
python3 scripts/verify_freeze.py     # frozen code/config hashes vs prw_freeze_record.json
python3 scripts/verify_bundle.py     # static validator (paths, secrets, manifests, syntax)
```

## Run tests

```bash
cd code/procurement_research_workbench_v1
python3 -m pip install -e ".[dev]"   # pytest + jsonschema; add ",diagnostics" for the scipy-based test too, ",plots" for matplotlib
python3 -m pytest -q
```

Expect all tests to pass. With only the `dev` extra installed, one test is `SKIPPED` (it imports
`scipy`, which is in the optional `diagnostics` extra) -- that skip is expected, not a problem.

## Reach the reported tables and figures

This reproduces the standalone 6-configuration static-retrieval benchmark (configs A-F: lexical,
dense, hybrid, hybrid+priors, hybrid+graph, two-lane final fusion) reported in the thesis's Table
1 and its associated figures. It is a separate pipeline from the four-system (`hybrid`/
`legal_static`/`planned_multisearch`/`adaptive`) DEV/TEST comparison in
`code/procurement_research_workbench_v1`; that comparison's own retrieval/judging steps call an
LLM with no fixed seed and are not re-run here (see "Reproducibility scope" in
`TECHNICAL_APPENDIX.md`) -- its code is instead exercised via the test suite above, and its actual
recorded outputs are the JSONL files under `results/`.

```bash
cd code/evaluation/final_retrieval_benchmark
python3 candidate_ceiling_CORRECTED.py    # candidate-generation/ranking classification
python3 build_final_tables.py             # FINAL_RESULTS_TABLE.csv, PAIRWISE_STATISTICS.csv
python3 strict_target_recall.py           # judge-independent strict recall
python3 make_figures.py                   # figures/*.png
```

All of these are pure functions of the already-saved retrieval-run/judgment JSONL files in
`results/`; none calls an external API.

`candidate_ceiling.py` (without `_CORRECTED`) is also included, unmodified, and produces a
different classification split than `_CORRECTED.py` -- both are kept so either can be checked
against the frozen source data directly.

## Rebuild and run the live retrieval application

Requires a local Docker install and, only for two endpoints, your own OpenAI API key.

```bash
docker compose up -d qdrant
cd code && pip install -r requirements.txt && cd ..   # rebuild_search_index.py needs these installed first
python3 scripts/rebuild_search_index.py     # ~20-40 min on CPU; builds the search index from code/corpus_export/data/
cp .env.example .env                         # add your own OPENAI_API_KEY
cd code && python chunk_api.py               # serves on :8899
```

`/search` and `/health` need no API key. `/answer` and `/refine` do.

## External services required

- **Qdrant**: a local Docker container you start yourself (`docker compose up -d qdrant`),
  populated by `scripts/rebuild_search_index.py` from the included corpus export. No pre-built
  database or vector-index binary is shipped.
- **OpenAI API key**: required only for `/answer`/`/refine` and for any LLM-driven step you
  choose to rerun (chunking, controller, judging). Never included -- copy `.env.example` to
  `.env` and supply your own.

## What is and is not exactly reproducible

Deterministic given the same inputs: ingestion, graph construction, indexing, retrieval, and all
statistics/tables/figures computed from the already-saved JSONL data in `results/`.

Not byte-for-byte reproducible: any step that calls an LLM without a fixed seed (corpus
chunking, controller planning, judging) -- these will produce architecturally comparable, not
identical, output on rerun. See `provenance/missing_artifacts.md` for the full list of known
limitations.

