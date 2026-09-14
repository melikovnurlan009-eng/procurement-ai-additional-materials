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
python3 candidate_ceiling.py
python3 build_final_tables.py
python3 strict_target_recall.py
pip install matplotlib
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

A short version first, then the full file-by-file guide below it.

- **`code/`** -- all source: scrapers, chunking/ingestion, graph construction, the retriever,
  the deployed application layer, a standalone benchmark, and the `procurement_research_workbench_v1`
  evaluation package. `corpus_export/data/` inside it is the actual exported corpus.
- **`corpus_manifests/`** -- the curated Procurement Pathway URL manifest.
- **`results/`** -- raw DEV/TEST run and judgment artifacts needed to regenerate the reported
  tables and figures.
- **`environment/`** -- package versions, Python/OS, embedding/LLM model identifiers.
- **`scripts/`** -- integrity verification and index-rebuild scripts.
- **`provenance/`** -- the artifact manifest and the disclosed-limitations document.

## Directory and file guide

Every directory and every non-obvious file, what it is, and what it does. Files already fully
covered by `TECHNICAL_APPENDIX.md`'s table 0.2 (the acquisition-to-retrieval pipeline scripts) are
only summarized here with a pointer, to avoid repeating that table twice -- come back to this
section for everything *else* in the bundle: the deployed app, the evaluation packages, one-off
analysis tools, and every data/config/results directory.

### Top level

| Path | What it is |
|---|---|
| `README.md` | This file. |
| `TECHNICAL_APPENDIX.md` | The full pipeline diagram/table, evaluation methodology, retrieval-system internals, package versions, and significance-testing detail. |
| `MANIFEST.sha256` | One SHA-256 line per file in the bundle (1,805 files), for tamper/corruption detection -- checked by `scripts/verify_bundle.py`. |
| `docker-compose.yml` | Single-service Compose file running Qdrant v1.18.3 (the dense vector store), ports 6333/6334, persisted to a named volume. Start this before rebuilding the index or running the API. |
| `.env.example` | Template for a runtime `.env` (no real credentials): `OPENAI_API_KEY` (only needed for `/answer`/`/refine`), plus `OPENAI_CHAT_MODEL`, `QDRANT_URL`, `QDRANT_COLLECTION`, `LOCAL_EMBEDDING_MODEL` overrides. |
| `.gitignore` | Standard ignores. |
| `corpus_manifests/` | Three files (2.3MB) documenting the curated Procurement Pathway source list: `procurement_pathway_urls.jsonl` (1,690 URLs, the final de-duplicated/topic-annotated crawl manifest) and a 20-URL sample (`.json`/`.txt`) for spot-checking. This curated manifest's own refinement code isn't included (see `provenance/missing_artifacts.md`), so it can't be regenerated byte-for-byte from a fresh raw crawl alone. |
| `environment/` | `environment_notes.md` (distinguishes the currently-verified-compatible environment from the historical corpus-build one, and documents what is/isn't deterministic on rerun), `pip-freeze.txt` (110 packages, full closure), `requirements-lock.txt` (15 key pins). |
| `provenance/` | `missing_artifacts.md` (six disclosed reproducibility gaps -- Procurement Pathway curation code, no historical environment snapshot, no pinned embedding-model revision, TEST-split independence, unseeded LLM steps, excluded per-item caches) and `artifact_manifest.csv` (a curated, categorized inventory of the whole bundle, generated by `scripts/generate_manifests.py`). |
| `results/` | Raw DEV/TEST artifacts -- see the dedicated table under "code/procurement_research_workbench_v1/" below, since these mirror that package's own output shape. |
| `scripts/` | See the table below. |

### `scripts/`

| File | What it does |
|---|---|
| `verify_freeze.py` | Recomputes SHA-256 over every frozen `prw/` code/config file and compares against `results/final_reports/prw_freeze_record.json`; fails on any mismatch. Proves code/config integrity only, not that a fresh LLM call reproduces prior judgments. |
| `verify_bundle.py` | Offline, no-network validator: required files exist, no leaked absolute paths/secrets, no packaging noise, every `MANIFEST.sha256` entry checks out, calls `verify_freeze.py`, dataset counts match (40 dev/20 test), no conflicting duplicate result tables, README references resolve, every `.py` file compiles. |
| `generate_manifests.py` | Produces `provenance/artifact_manifest.csv` and `MANIFEST.sha256` (in that order, since the CSV itself gets hashed too). |
| `rebuild_search_index.py` | Drives `build_chunk_index.py` (lexical + dense) and `densify_graph_edges.py` against the shipped `code/corpus_export/data/` export to rebuild a working index in minutes, no scraping/LLM calls. Asserts the exact expected chunk/edge counts (22,042 / 27,600). |
| `verify_deterministic_chunking.py` | Freshly re-scrapes PA2023 or PR2024 live and re-runs the deterministic (non-LLM) structural chunker, diffing the result against the shipped corpus -- the one lane of the pipeline that's genuinely spot-checkable against a live source. |

### `code/` -- pipeline scripts (acquisition through retrieval)

Fully documented, in dependency order with exact commands, in `TECHNICAL_APPENDIX.md` section
0.2 -- not repeated here. Covers: the legislation/guidance/Procurement-Pathway scrapers
(`scrapers/`), PDF extraction, the four chunking methods (`chunk_legislation_from_nodes.py`,
`build_search_corpus.py`, `chunk_legislation_text.py`, `chunk_pdf_text.py`,
`chunk_commencement_regs_from_xml.py`), reference resolution (`resolve_references.py`,
`extract_guidance_references.py`), index bootstrap and ingestion (`build_chunk_index.py`,
`ingest_legislation_chunks.py`, `ingest_pdf_chunks.py`, `ingest_structural_node_chunks.py`),
`deduplicate_instruments.py`, `densify_graph_edges.py`, the re-export bridge
(`code/corpus_export/export_corpus_from_db.py`), and the backfill loop
(`collect_missing_references.py`, `code/scrapers/legislation/scrape_missing_legislation.py`).

`code/scrapers/` also contains three scripts **not** part of that pipeline, kept for
reference/audit only, each explicitly superseded by a newer version per `TECHNICAL_APPENDIX.md`:
`code/scrapers/legislation/group_a_legislation_scraper.py` (v1) and `_v2.py` (early iterations of the scraper
`_v4.py` replaced -- v2's own docstring notes it corrects a real bug in v1: fetching the
"contents" view instead of the full instrument body), `scrape_core_legislation_full.py` (a
duplicate producing the same output format as `_v4.py` but wired into nothing), and
`rescrape_procurement_journey.py` (an optional later-stage quality tool that requires the
database to already exist and deliberately does not ingest its own output).

### `code/` -- the deployed application layer

| File | What it does |
|---|---|
| `chunk_retrieval.py` | The production retriever: `search()`/`search_two_lanes()`, hybrid lexical+dense+graph, RRF fusion, two-lane authority/regime/jurisdiction reranking. |
| `chunk_api.py` | FastAPI service: `/health`, `/search`, `/answer`, `/refine`, `/chunk/{chunk_id}`, plus a minimal built-in HTML/JS page at `/`. |
| `answer_query.py` | Generates a cited answer over retrieved evidence and verifies it against the claims it cites (`verify`/`check_claim_grounding`). |
| `refine_query.py` | Query refinement/follow-up handling for the API. |
| `query_expansion.py` | Query-expansion helper used by the app layer. |
| `streamlit_app.py` | A fuller Streamlit UI ("Procurement KG Assistant") talking to the same backend via its own small `call_answer()`/`normalize_base_url()` helpers. |

### `code/` -- one-off analysis and dev tools (not needed to reproduce the reported results)

These exist to substantiate specific claims made *about* the corpus/pipeline in the thesis text,
or to develop a prompt/heuristic that was later folded into a production script. None is a
required reproduction step, and none is referenced by `TECHNICAL_APPENDIX.md`'s pipeline table.

| File | What it does |
|---|---|
| `analyze_graph.py` | Tests whether the graph's connected components correspond to meaningful legal relationships (topic/legal-concept Jaccard overlap vs. a random-pairs baseline) or are citation artefacts; identifies hub nodes. |
| `analyze_graph_edges.py` | Companion analysis at edge level (component analysis alone can't discriminate, since 99.8% of nodes fall in one component): edge coherence, hub structure, reachability, authority-to-authority citation flow. |
| `baseline_fixed_chunking.py` | Builds two deterministic fixed-size chunking baselines and scores them with the same structural detectors as the production LLM-chunked corpus, to test whether LLM-selected boundaries actually help. |
| `build_chunk_representations.py` | Experimental sentence/summary-level embeddings, to test whether whole-chunk embeddings dilute topical signal on long chunks. **Superseded/unused** -- `chunk_retrieval.py` does not reference these representations. |
| `content_filters.py` | A library of navigation/boilerplate DROP rules and whitespace-repair functions, validated against a 900-chunk LLM quality-labelling run. Designed but **not currently wired into** `build_search_corpus.py` or any ingestion script. |
| `evaluate_chunk_quality.py` | Two-tier chunk-quality evaluator (deterministic structural defect detection, plus optional sampled LLM judging). Its functions are imported by `baseline_fixed_chunking.py` and `optimize_chunking_prompt.py` -- shared evaluation-library infrastructure for those experiments. |
| `export_bad_chunks_by_domain.py` / `export_good_chunks.py` | Export the INCOMPLETE/LOW_VALUE and GOOD chunks (respectively) from `label_chunk_quality_llm.py`'s labelling run, grouped by source domain/type, to build a qualitative failure/success catalogue. |
| `label_chunk_quality_llm.py` | Batch LLM labelling (GOOD/INCOMPLETE/LOW_VALUE) of a 900-chunk sample, catching failures the structural detectors can't see. Upstream source for the two export scripts above. |
| `optimize_chunking_prompt.py` | Evolutionary (WizardLM-style) optimization of the semantic-chunking prompt, scored by the deterministic Tier-1 detectors. Its output is now embedded directly in `chunk_legislation_text.py`/`chunk_pdf_text.py`'s production prompts; the tool itself is not re-run. |
| `rechunk_from_index.py` | Targeted re-chunk (text-emission) of specific documents shown to be over-represented in retrieval-blocking failures, reconstructing source text from already-ingested chunks (no re-fetching). |
| `run_pdf_pipeline.py` | Fetches, extracts (via `extract_pdf_pages.py`), and LLM-chunks every PDF in the corpus; resumable and staged -- "nothing enters the index" from this script alone, its output is what a later `ingest_pdf_chunks.py` run reads. |
| `validate_search_corpus.py` | Non-destructive integrity validator for the JSONL search corpus: block coverage, placeholder conservation, exact text reconstruction, content-hash match, chunk-id uniqueness, ordinal continuity, edge validity. QA tool, not a pipeline stage. |
| `extract_pdf_pages.py` | Plain, lossless per-page PDF text extraction (deliberately rejects heuristic structure-inference as unreliable); imported by `run_pdf_pipeline.py`. Also listed in the main pipeline table (row 4). |
| `extract_pdf_structured.py` | An alternative, layout-aware PDF extractor (recovers headings/lists via font metadata) explored as a replacement for the plain page-emission lane. Not imported by any other script -- a standalone comparison tool, despite sharing a pipeline-table row with `extract_pdf_pages.py`. |

### `code/evaluation/final_retrieval_benchmark/` -- the standalone 60-scenario benchmark

| File | What it does |
|---|---|
| `scenarios_all.jsonl` / `scenarios_dev.jsonl` / `scenarios_test.jsonl` | This benchmark's own native flat scenario schema (60 total: 40 dev/20 test) -- the schema `run_retrieval_configs.py`, `compute_metrics.py`, `error_analysis.py`, etc. actually read. |
| `gold_evidence.jsonl` | Per-scenario, per-requirement essential/strong-supporting/acceptable-alternative evidence citations, each resolved to a real corpus `chunk_id` by `resolve_gold_targets.py`. |
| `resolve_gold_targets.py` | Resolves each citation in `gold_evidence.jsonl` against the live corpus DB. **Known bug, not yet fixed**: matches on only the first 4 normalized citation tokens with no `ORDER BY`, so most regulation citations (e.g. "reg.72") collapse onto the same wrong target ("regulation 1") -- see `TECHNICAL_APPENDIX.md` and the corresponding note in `provenance/missing_artifacts.md`. |
| `gold_resolution_report.json` | Summary of that resolution run: 224 MATCHED, 4 FUZZY_MATCHED, 0 UNRESOLVED. |
| `run_retrieval_configs.py` | Runs all six static configs (A-F) against all 60 scenarios using the real production retriever; needs `.venv-embed` (with `sentence_transformers`/`qdrant_client`) or the dense-dependent configs silently zero out. |
| `build_candidate_pool.py` | Deduplicated union of every chunk retrieved by any config, force-including every resolved gold chunk even if nothing retrieved it, so judging isn't biased against under-retrieved gold. |
| `judge_candidate_pool.py` | First-pass LLM (gpt-4o-mini) relevance judging of the pool, 0-3 scale -- a **single-pass judge**, structurally simpler than and unrelated to the `prw` package's 3-judge+adjudicator mechanism. Writes `qrels_provisional.jsonl`. |
| `compute_metrics.py`, `candidate_ceiling.py`, `strict_target_recall.py`, `error_analysis.py`, `build_final_tables.py`, `make_figures.py` | Metrics and figure generation from the already-judged data, reproducing the reported tables/figures -- see `TECHNICAL_APPENDIX.md` for what each specifically computes. |
| `convert_to_workbench_schema.py` | Pure structural re-export of the same 60 scenarios into the `procurement_research_workbench_v1` package's schema -- no fact/wording/split changes. Writes `workbench_schema/`. |
| `run_split_audit.py` / `split_audit.md` | DEV/TEST leakage audit (exact/normalized duplicates, BGE-M3 semantic similarity, template clustering). Result: zero duplicates, zero high-similarity pairs; one template cluster (DEV028/TEST019, both "standstill" scenarios) flagged for human read-through, not auto-rejected. |
| `workbench_schema/` | `convert_to_workbench_schema.py`'s output: `scenarios_{dev,test}.jsonl` + `requirements_{dev,test}.jsonl`, the same scenario IDs/content as the top-level trio, restructured into the `prw` package's public/private schema split, plus a `content_hash_manifest.json`. |
| `metrics/`, `figures/`, `retrieval_runs/` | Computed outputs and raw per-config retrieval results (depth 50) that all the scripts above read/write. |

### `code/procurement_research_workbench_v1/` -- the matched DEV/TEST evaluation package

| File | What it does |
|---|---|
| `code/procurement_research_workbench_v1/prw/cli.py`, `controller.py`, `judging.py`, `bundles.py`, `answers.py` | Already covered in depth elsewhere in this conversation/`TECHNICAL_APPENDIX.md` (the CLI subcommands, the planner/observer adaptive loop, the three judging tracks). |
| `code/procurement_research_workbench_v1/prw/contracts.py` | Core typed data model: `Scenario` (rejects any hidden evaluation field leaking into the public object), `Evidence` (self-verifying content hash), `SearchRequest`/`SearchResponse`, the `Backend` protocol, requirement-set schema validation. |
| `code/procurement_research_workbench_v1/prw/adapters.py` | Translates the package's typed request/response contract into calls on the real production retriever (`ProductionAdapter`, `production_backend()`), plus a deterministic `ReplayBackend` fixture for smoke tests. |
| `code/procurement_research_workbench_v1/prw/metrics.py` | `evaluate_ranking()` (requirement coverage, pooled nDCG, MRR, precision@k -- hard-fails on any unjudged/stale-hash candidate), `macro_summary()`, `paired_bootstrap()` (scenario-group paired bootstrap CI + exact sign test), `judge_agreement()` (pairwise kappa). |
| `code/procurement_research_workbench_v1/prw/pooling.py` | Merges every acquired candidate across all compared systems into one deduplicated judgment pool, keyed by (scenario, chunk), raising on conflicting text for the same chunk_id. |
| `code/procurement_research_workbench_v1/prw/graph.py` | `GraphSidecar`, a strictly one-hop citation-expansion wrapper using only explicit `CROSS_REFERS_TO`/`REFERENCES` edges. |
| `code/procurement_research_workbench_v1/prw/keywords.py` / `code/procurement_research_workbench_v1/prw/shadow_fts.py` | A separate keyword/alias-enrichment ablation (arms I0/I1/I2): validated, source-anchored keyword extraction plus an isolated FTS5 index that never touches the production corpus. |
| `code/procurement_research_workbench_v1/prw/llm.py` | Opt-in HTTP model transport: no bundled credentials, requires `--allow-network`, enforces HTTPS, treats truncated/filtered completions as hard failures, journals every request, and enforces a request-count `Budget`. |
| `code/procurement_research_workbench_v1/prw/io.py` | Canonical JSON hashing (`digest`/`file_hash`), strict `read_jsonl`, atomic writes, an append-only event journal. |
| `code/procurement_research_workbench_v1/prw/diagnostics.py` | Evaluation-only oracles that must never feed back into retrieval: sequential action-gain tracking, and an optional MILP-computed label-aware coverage ceiling. |
| `code/procurement_research_workbench_v1/prw/benchmark.py` | Dataset structural audit (duplicate IDs, cross-split leakage, near-duplicate detection) and the code/config `freeze()`/`check_freeze()` mechanism used before the TEST run. |
| `prompts/` | The 8 fixed prompt templates driving every model role (planner, observer, passage judge + adjudicator, bundle judge, answer generator + judge, source-keywords). |
| `schemas/` | JSON Schema definitions for a judge's output, the private requirement set, and the public scenario shape. |
| `configs/` | `models.json` (model-slot config: controller/generator/3 judges/adjudicator, no hardcoded credentials) and `retrieval.json` (the shared retrieval budget: depth 100, k=10, 18,000-char cap, max 3 operations, graph fanout 20). |
| `tests/` | The 61-test pytest suite covering controller, judging, metrics, and package-level behavior. |
| `scripts/` | Orchestration CLIs on top of the package: `build_controller_diagnostics.py`, `build_shadow_indexes.py`, `check_adapter.py`, `enrich_sources.py`, `make_final_figures.py`/`make_intervention_figure.py`/`plot_results.py`, `report_bundles.py`, and `smoke_pipeline.py` (a fully offline, fixture-only run explicitly labeled non-research data). |
| `docs/` | `RESEARCH_PROTOCOL.md` (predeclared hypotheses, budgets, and the bundle-sufficiency demotion writeup discussed earlier in this conversation), `ADAPTIVE_CONTROLLER.md`, `JUDGING_PROTOCOL.md`, `DATASET_CARD.md`, `KEYWORD_EXPERIMENT.md`, `RESULTS_AND_CLAIMS.md`, `workflow.mmd` (the evaluation-methodology diagram). |
| `examples/` | Illustrative, non-authoritative samples: a custom-backend example, one fully worked scenario (D019) showing the public/private split, and an explicitly-labeled template (not real data). |
| `references/` | `reading_list.md` (background/provenance notes) and `source_registry.json` (the ~20 official guidance URLs used to orient scenario authoring). |
| `validation/` | Recorded proof the package's tests/smoke pipeline actually ran: `TEST_REPORT.md`, raw pytest output, `dataset_audit.json`, and `smoke/` (offline fixture results, explicitly tagged not-research-evidence). |
| `data/dev/`, `data/test_sealed/` | The 40-scenario DEV and 20-scenario TEST splits: `scenarios.jsonl`, `requirements.jsonl`, `followups.jsonl`, `followup_requirements.jsonl`, all generated by the single `code/procurement_research_workbench_v1/data/test_sealed/build_dataset_source.py` script (the sole source of truth for both splits and the source registry). |

### `results/` -- raw DEV/TEST artifacts

| Path | What's in it |
|---|---|
| `runs/{dev_scale,test_final}/{hybrid,legal_static,planned_multisearch,adaptive}/` | Per-scenario retrieved chunks (`runs.jsonl`), execution trace (`events.jsonl`), a provenance/freeze signature (`manifest.json`), and for the two LLM-driven systems, model call/budget logs. |
| `judgments/{dev_scale,test_final}/pointwise/` | The real, at-scale 3-judge output: `judgments_raw.jsonl`, `qrels_silver.jsonl`, `agreement.json` (pairwise judge kappa), `judge_manifest.json` (confirms all 3 judge slots are the same model identity). |
| `pool/{dev_scale,test_final}/` | `candidate_pool.jsonl` (pooled chunks sent to judges), `membership_private.jsonl` (which system contributed each one, kept separate so judges stay blind), `cost_plan.json`. |
| `evaluate_output/{dev_scale,test_final}/evaluate/` | `summary.json`, `per_scenario.jsonl`, `by_suite.json`, `report.md` -- the final computed metrics and paired significance comparisons. `dev_scale/` also has `DEV_RUN_REPORT.md` and `CONTROLLER_DIAGNOSTICS.csv`. |
| `results/final_reports/prw_freeze_record.json` | The cryptographic freeze snapshot checked by `scripts/verify_freeze.py` -- proves tamper-evidence only, not TEST-split independence or label correctness. |

### `code/corpus_export/`, `code/normalized_html_json_v2/`, `code/corpus_minor_formats/`, `code/data/`

| Path | What's in it |
|---|---|
| `code/corpus_export/data/chunks.jsonl` | The main exported chunk table -- 22,042 retrieval-ready chunks, the literal unit the system indexes/embeds. The largest file in the bundle (~87MB). |
| `code/corpus_export/data/documents.jsonl` | 2,078 document-level records that `chunks.jsonl` rows join against via `document_id`. |
| `code/corpus_export/data/edges.jsonl` | Structural graph edges (15,678): `CONTAINS` + `HAS_CHUNK` only -- the containment/provenance skeleton, not citations. |
| `code/corpus_export/data/edges_v2.jsonl` | Cross-reference graph edges (11,922): `REFERENCES` + `CROSS_REFERS_TO`, the resolved citation layer. |
| `normalized_html_json_v2/records/` | 1,512 per-document JSON records -- the normalized-HTML acquisition stage, upstream of chunking: logical structure outline, ordered content blocks, links, legal references. |
| `corpus_minor_formats/xml/` | 13 native Akoma Ntoso XML source files kept alongside the main HTML-based pipeline for instruments sourced/retried in this format. |
| `code/data/search_corpus/reference_resolution_all.jsonl` | 14,491 records logging every citation candidate the resolver attempted, resolved or not -- the full audit trail `edges_v2.jsonl`'s successful edges are drawn from. |

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
thesis's Table 2 and its associated figures.

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
python3 candidate_ceiling.py              # candidate-generation/ranking classification
python3 build_final_tables.py             # FINAL_RESULTS_TABLE.csv, PAIRWISE_STATISTICS.csv
python3 strict_target_recall.py           # judge-independent strict recall
pip install matplotlib                    # not in code/requirements.txt -- only this last step needs it
python3 make_figures.py                   # figures/*.png
```

All of these are pure functions of the already-saved retrieval-run/judgment JSONL files in
`results/`; none calls an external API. `make_figures.py` is the only script in this list that
imports `matplotlib`, which isn't part of `code/requirements.txt` -- install it separately
before this one step, as shown above.

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

