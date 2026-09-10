# Additional Materials

Reproducibility companion for an MSc extended research project on retrieval-augmented question
answering over UK public procurement law: a hybrid lexical/dense/graph retriever, four compared
retrieval systems (`hybrid`, `legal_static`, `planned_multisearch`, `adaptive`), and a two-track
evaluation (a standalone 6-configuration static-retrieval benchmark, and a matched DEV/TEST
comparison of the four production systems).

## What this supports

The UK public procurement AI assistant described in the thesis report: corpus construction over
legislation/guidance sources, a legal-structural chunking and reference-graph pipeline, and a
retrieval/evaluation harness comparing static and LLM-controller-driven retrieval strategies.

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

Requires **Python 3.10 or later** (the package's `pyproject.toml` enforces this; a fresh
environment defaulting to an older `python3` will fail to install with
`requires a different Python: ... not in '>=3.10'`). Also requires a reasonably current `pip`
(`python3 -m pip install --upgrade pip` first, if using a `python3 -m venv` environment with an
old bundled pip) -- an old pip cannot editable-install a pure-`pyproject.toml` package at all.

```bash
cd code/procurement_research_workbench_v1
python3 -m pip install --upgrade pip
python3 -m pip install -e .
python3 -m pip install pytest jsonschema   # minimum to run the suite; add numpy/scipy/matplotlib for diagnostics/plots
python3 -m pytest -q
```

## Reach the reported tables and figures

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

## Scientific language

This package avoids "proves," "guarantees," "fully reproducible," and "identical conditions"
unless literally true for the specific claim at hand.
