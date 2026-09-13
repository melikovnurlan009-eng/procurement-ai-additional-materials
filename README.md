# Additional Materials

Reproducibility companion for an MSc thesis: *A Legal-Structure-Aware Retrieval System for a UK
Public Procurement AI Assistant* (student 14322782, CSDI pathway).

The thesis builds a retrieval system that answers UK public-procurement-law questions. It
combines three search methods -- lexical (keyword) search, dense (embedding-based) search, and a
legal citation graph -- and compares four retrieval strategies built on top of that combination
(see "What this supports" below for what each one does).

Two separate evaluations were run:
- A standalone benchmark comparing 6 retrieval configurations.
- A matched DEV/TEST comparison of the four main retrieval systems.

See `TECHNICAL_APPENDIX.md` for the full pipeline diagram and methodology.

## Prerequisites

- **Python 3.10 or later.** Check with `python3 --version`. If your default `python3` is older
  (e.g. macOS ships 3.9.x by default), install a newer one -- `brew install python@3.12`
  (macOS/Homebrew) or `pyenv install 3.12` -- then create a virtual environment **from that
  interpreter** and use it for everything below:
  ```bash
  python3.12 -m venv .venv          # use whichever new version you installed, e.g. python3.14
  source .venv/bin/activate         # `python3`/`pip` in this shell now point at .venv
  python3 -m pip install --upgrade pip
  ```
  Do not `pip install` straight into a Homebrew/system Python -- on current macOS it is
  "externally managed" (PEP 668) and refuses direct installs; a venv is required, not optional.
  An old pip also cannot editable-install a pure-`pyproject.toml` package at all, hence the
  upgrade above.
- **git**, to have cloned this repository.
- **Docker**, only if you rebuild and run the live retrieval application (last section below).
- **An OpenAI API key**, only for the live application's `/answer`/`/refine` endpoints, or to
  rerun any LLM-driven step yourself (chunking, controller, judging).

Run this once, from the repository root (the directory this file is in), before anything else:

```bash
REPO_ROOT="$(pwd)"
```

Every command block below uses `$REPO_ROOT`, so it still works even if a previous step's `cd`
left your shell somewhere else. (Opened a new terminal? Re-run that line there first.)

## Quickstart: run these in order

Every command below is copy-pasteable in sequence, from the repository root. Steps marked
**(optional)** can be skipped without affecting anything after them -- everything else is a hard
prerequisite for the step that follows it. Every step is explained in more detail, with its own
heading, further down this file; this section only fixes the order.

**1. Set up Python 3.10+ and capture the repo root** (see "Prerequisites" above if this fails):
```bash
REPO_ROOT="$(pwd)"
python3.12 -m venv .venv   # substitute whichever 3.10+ interpreter you installed
source .venv/bin/activate
python3 -m pip install --upgrade pip
```

**2. Verify integrity** (static checks, no network, seconds to run):
```bash
python3 "$REPO_ROOT/scripts/verify_freeze.py"
python3 "$REPO_ROOT/scripts/verify_bundle.py"
```

**3. Build the final database and search index** -- from the corpus already exported in this
bundle, **not** by re-scraping (see "What is and is not exactly reproducible" below for why):
```bash
docker compose -f "$REPO_ROOT/docker-compose.yml" up -d qdrant
cd "$REPO_ROOT/code" && pip install -r requirements.txt
python3 "$REPO_ROOT/scripts/rebuild_search_index.py"   # ~20-40 min on CPU
```

**4. Run the live application:**
```bash
cd "$REPO_ROOT" && cp .env.example .env   # add your own OPENAI_API_KEY
cd "$REPO_ROOT/code" && python chunk_api.py   # serves on :8899
```
`/search` and `/health` work with no key; `/answer`/`/refine` need one. **This is the final,
working system** -- same database, same search index, same retrieval code that was evaluated.
Everything below is about the evaluation, not the system itself, and every one of the remaining
steps is independent of the others -- run whichever you actually need, in any order.

**5. (optional) Run the evaluation package's own test suite:**
```bash
cd "$REPO_ROOT/code/procurement_research_workbench_v1"
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
```

**6. (optional) Reproduce the reported tables and figures:**
```bash
cd "$REPO_ROOT/code/evaluation/final_retrieval_benchmark"
python3 candidate_ceiling_CORRECTED.py
python3 build_final_tables.py
python3 strict_target_recall.py
python3 make_figures.py
```

**7. (optional) Spot-check the acquisition/chunking methodology against live sources:**
```bash
cd "$REPO_ROOT/code"
python3 "$REPO_ROOT/scripts/verify_deterministic_chunking.py" --source PA2023
python3 "$REPO_ROOT/scripts/verify_deterministic_chunking.py" --source PR2024
```

Steps 5-7 each have their own section below (with what to expect, and why the command does what
it does) -- this list exists so you never have to guess what comes next.

## What this supports

The UK public procurement AI assistant described in the thesis. Three parts:

1. **Corpus construction** -- turning legislation and guidance documents into a searchable,
   legally-structured chunk and reference-graph database.
2. **Retrieval** -- four compared systems:
   - `hybrid`: lexical+dense search only.
   - `legal_static`: `hybrid` plus legal-authority weighting and one-hop graph expansion, still no
     LLM call.
   - `planned_multisearch`: an LLM breaks the query into sub-queries once, with no inspection of
     what comes back.
   - `adaptive`: an LLM breaks the query down and iteratively inspects retrieved evidence, bounded
     to 3 retrieval operations.
3. **Evaluation** -- comparing those four systems against each other and against the standalone
   benchmark named above.

## Directory layout

- **`code/`** -- all source, laid out to mirror the original repository's directory structure:
  - Corpus scrapers and chunking/ingestion scripts.
  - The graph-construction scripts (`resolve_references.py`, `extract_guidance_references.py`,
    `densify_graph_edges.py`) and the production retriever (`chunk_retrieval.py`).
  - The deployed application layer (`chunk_api.py`, `answer_query.py`, `refine_query.py`,
    `query_expansion.py`, `streamlit_app.py`).
  - The standalone benchmark (`evaluation/final_retrieval_benchmark/`).
  - The evaluation package (`procurement_research_workbench_v1/`, with its own tests, data,
    schemas, and configs).
  - `corpus_export/data/` -- the actual chunk/document/edge data exported from the evaluated
    corpus.
- **`corpus_manifests/`** -- the curated Procurement Pathway URL manifest.
- **`results/`** -- raw DEV/TEST run and judgment artifacts (`runs/`, `judgments/`, `pool/`,
  `evaluate_output/`) needed to regenerate the reported tables and figures.
- **`environment/`** -- package versions, Python/OS, embedding/LLM model identifiers.
- **`scripts/`** -- `verify_freeze.py`, `verify_bundle.py`, `generate_manifests.py`,
  `rebuild_search_index.py`.
- **`provenance/`** -- `artifact_manifest.csv`, `missing_artifacts.md`.

## Verify integrity

```bash
python3 "$REPO_ROOT/scripts/verify_freeze.py"     # frozen code/config hashes vs prw_freeze_record.json
python3 "$REPO_ROOT/scripts/verify_bundle.py"     # static validator (paths, secrets, manifests, syntax)
```

## Verify the deterministic chunking lane (optional)

The two checks above are static (no network, no scraping). This one is different: it actually
scrapes PA2023 or PR2024 live from legislation.gov.uk today, chunks the result with the
fully-deterministic (no-LLM) chunker, and compares the output against the shipped, evaluated
corpus -- the concrete way to confirm that lane genuinely reproduces, rather than take it on
faith. Needs `requests`/`lxml` (`pip install -r code/requirements.txt`).

```bash
cd "$REPO_ROOT/code"
python3 "$REPO_ROOT/scripts/verify_deterministic_chunking.py" --source PA2023
python3 "$REPO_ROOT/scripts/verify_deterministic_chunking.py" --source PR2024
```

Expect an exact text/hash match on every provision both runs agree exists. A handful of
differences on either side is normal, not a failure -- legislation.gov.uk is live and can be
amended after the corpus was built (see "What is and is not exactly reproducible" below).

## Run tests

```bash
cd "$REPO_ROOT/code/procurement_research_workbench_v1"
python3 -m pip install -e ".[dev]"   # pytest + jsonschema; add ",diagnostics" for the scipy-based test too, ",plots" for matplotlib
python3 -m pytest -q
```

Expect all tests to pass. With only the `dev` extra installed, one test is `SKIPPED` (it imports
`scipy`, which is in the optional `diagnostics` extra) -- that skip is expected, not a problem.

## Reach the reported tables and figures

This reproduces the standalone 6-configuration static-retrieval benchmark: configs A-F (lexical,
dense, hybrid, hybrid+priors, hybrid+graph, two-lane final fusion). It corresponds to the
thesis's Table 1 and its associated figures.

This is a separate pipeline from the four-system (`hybrid`/`legal_static`/`planned_multisearch`/
`adaptive`) DEV/TEST comparison in `code/procurement_research_workbench_v1`. That comparison's
`pool`/`judge`/`judge-bundles`/`judge-answers`/`evaluate` commands *are* fully documented and
runnable -- see `TECHNICAL_APPENDIX.md` section 4.0 ("Evaluation methodology, and what you need
before running any of it") and 4.4 ("Exact commands") -- they are just not included in this
Quickstart because their judging steps call an LLM with no fixed seed (see "Reproducibility
scope" in `TECHNICAL_APPENDIX.md`), so rerunning them produces architecturally comparable, not
identical, output. Two ways to use them: point them at the already-shipped
`results/runs/<split>/<system>/runs.jsonl` files to reproduce the same judgments/metrics this project
recorded (no rebuild, nothing overwritten), or run `prw run` yourself first against your own
freshly built index if you specifically want to verify the retrieval step end to end. This
package's own code is additionally exercised, independent of either path, by the test suite in
step 5 above.

```bash
cd "$REPO_ROOT/code/evaluation/final_retrieval_benchmark"
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
docker compose -f "$REPO_ROOT/docker-compose.yml" up -d qdrant
cd "$REPO_ROOT/code" && pip install -r requirements.txt   # rebuild_search_index.py needs these installed first
python3 "$REPO_ROOT/scripts/rebuild_search_index.py"     # ~20-40 min on CPU; builds the search index from code/corpus_export/data/
cd "$REPO_ROOT" && cp .env.example .env                   # add your own OPENAI_API_KEY
cd "$REPO_ROOT/code" && python chunk_api.py                # serves on :8899
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

**Exactly reproducible:** ingestion, graph construction, indexing, and retrieval, given the same
inputs -- meaning the already-exported corpus (`code/corpus_export/data/`). Rebuilding the search
index from that export (`scripts/rebuild_search_index.py`) reproduces the exact same chunk/edge
counts and content every time. All statistics/tables/figures computed from the already-saved
JSONL data in `results/` are exactly reproducible the same way.

**Not byte-for-byte reproducible, for two different reasons:**
- Any step that calls an LLM without a fixed seed (corpus chunking, controller planning, judging)
  -- these produce architecturally comparable, not identical, output on rerun.
- The *scraping* steps (`code/scrapers/...`) fetch live content from external websites
  (legislation.gov.uk, GOV.UK, law firm commentary, the Procurement Pathway). That content can
  change over time -- new amendments, updated guidance, edited pages -- independent of any LLM
  involvement, so re-running the scrapers today will not necessarily pull the same raw text they
  did originally. The Procurement Pathway's curation step is also not included at all (see
  `provenance/missing_artifacts.md` item 1), so a fresh crawl wouldn't even target the same final
  set of pages. Running the full from-scratch acquisition pipeline (`TECHNICAL_APPENDIX.md`
  section 0.2) is therefore not guaranteed to reproduce the same corpus as the one already
  exported and evaluated -- use the export (above) if exact reproduction is what you need.

See `provenance/missing_artifacts.md` for the full list of known limitations.

