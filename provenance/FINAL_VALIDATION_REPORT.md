# Final Validation Report

Run from a clean bundle root (`ADDITIONAL_MATERIALS_FINAL/`), 2026-09-07, using the
`.venv-embed` interpreter documented in `environment/environment_notes.md`.

| # | Command | Outcome | Failures | Expected? | Reason / external dependency |
|---|---|---|---|---|---|
| 1 | `python3 scripts/verify_freeze.py` | **PASS** | 0 | -- | Verifies 20 frozen code/config hashes against `prw_freeze_record.json`. No external dependency. |
| 2 | `python3 scripts/generate_manifests.py` | **PASS** | -- | -- | Regenerated `MANIFEST.sha256` (358 files) and `provenance/artifact_manifest.csv` (299 rows) from actual bundle contents. |
| 3 | `cd code/procurement_research_workbench_v1 && python3 -m pytest -q` | **PASS** | 0/60 | -- | 60 passed, 0 failed. Was 57/60 in the pre-finalization bundle; fixed by adding `data/{dev,test_sealed,pilot3}` and `schemas/`. No external dependency. |
| 4 | Evaluation-data/schema existence check (`data/dev/scenarios.jsonl`, `schemas/*.schema.json`) | **PASS** | 0 | -- | All present; verified by `scripts/verify_bundle.py::check_evaluation_data_and_schemas`. |
| 5 | `cd code/evaluation/final_retrieval_benchmark && python3 candidate_ceiling_CORRECTED.py` | **PASS** | -- | -- | Recomputed classification: 24 OK / 31 candidate-gen / 5 ranking (see `CHANGELOG_FINALIZATION.md`). No external dependency. |
| 6 | `python3 build_final_tables.py` | **PASS** | -- | -- | Regenerated `FINAL_RESULTS_TABLE.csv`, `PER_SUITE_RESULTS.csv`, `PAIRWISE_STATISTICS.csv`. Confirmed A_lexical vs B_dense p=0.05224 (not significant). No external dependency; machine-specific absolute path removed first (see changelog). |
| 7 | `cd .. (bundle root)/code/evaluation/final_retrieval_benchmark`, import smoke test: `from chunk_retrieval import ChunkRetriever` | **PASS** | 0 | -- | Fixed by restructuring `code/` to mirror original repo directory depths; zero edits to the frozen script. No external dependency (only needs the module to *import*, not run retrieval, which would require the corpus DB/Qdrant -- Level 3). |
| 8 | Recursive absolute-path scan (`scripts/verify_bundle.py::check_no_absolute_machine_paths`) | **PASS** | 0 | -- | One instance found and fixed (`build_final_tables.py`); none remain in executable `.py` source. |
| 9 | Secret scan (`scripts/verify_bundle.py::check_no_secrets`) | **PASS** | 0 | -- | No `.env` files, no real API-key patterns found; `sk-...`-looking matches in scraped text/citation data were manually confirmed to be URL slug false positives, not credentials. |
| 10 | Python syntax/import check, all `.py` files (`scripts/verify_bundle.py::check_python_syntax`) | **PASS** | 0 | -- | Every `.py` file in the bundle compiles (`py_compile`). This checks syntax only, not that every script can *run* without its external dependency (Qdrant/OpenAI/corpus DB). |
| 11 | Packaging-noise scan (`__pycache__`, `.pyc`, `.DS_Store`) | **PASS** | 0 | -- | Removed during finalization; re-scanned clean. |
| 12 | `python3 scripts/verify_bundle.py` (full run, all checks above plus manifest/duplicate/README-reference checks) | see below | see below | -- | Full combined run; exact output appended below this table after the bundle's final state was reached. |

## Explicitly not run (require external services, out of scope for a packaging audit)

- **Retrieval rerun** (Level 3: requires the original SQLite corpus index + a running Qdrant
  instance with `BAAI/bge-m3` loaded) -- not attempted. This bundle does not include the corpus
  database (see `TECHNICAL_APPENDIX.md` section 6 for why).
- **Any fresh LLM call** (controller planning/observation, judging, corpus text-emission
  chunking) -- not attempted, and would not be expected to reproduce prior output byte-for-byte
  even if attempted (LLM calls are not seeded -- see `environment/environment_notes.md`).
- **End-to-end corpus rebuild from scraped source** -- not attempted; would additionally require
  network access to the original source domains and, for one source family, source code that is
  not available (Procurement Pathway crawler -- see `provenance/missing_artifacts.md`).

## Full `scripts/verify_bundle.py` output

(Appended verbatim after the script was run against the bundle's final state, including this
file and the final `MANIFEST.sha256`/`artifact_manifest.csv` regeneration.)

```
=== Bundle validator ===
Checking required files...
Checking for absolute machine paths in source...
Checking for secrets...
Checking for packaging noise (__pycache__, .pyc, .DS_Store)...
Checking MANIFEST.sha256...
  manifest entries checked: 336, mismatches: 0
Checking frozen-source hashes (scripts/verify_freeze.py)...
Checked 20 hashes from results/final_reports/prw_freeze_record.json.
PASS: all frozen-source hashes match the included code exactly.
Note: this verifies code/config integrity only, not that a fresh LLM call would
reproduce prior judgments (LLM calls are not deterministic -- see
environment/environment_notes.md).
Checking evaluation data/schema files exist...
Checking documented scenario counts...
Checking for conflicting duplicate result files...
Checking README.md references resolve...
Checking Python syntax across all included scripts...
  python files syntax-checked: 114, failed: 0

=== 0 failure(s), 0 warning(s) ===

RESULT: PASS
```

This is the final, clean state of the bundle (no `__pycache__`/`.pyc` regenerated after this run
-- confirmed by a follow-up recursive scan before zipping).

## Second finalization pass (2026-09-08): cross-check against the submitted thesis PDF

After the above pass, every major numeric claim in the submitted thesis report
(`14322782_DATA72000.pdf`) was cross-checked directly against bundle artifacts --
see `provenance/PAPER_CLAIMS_CROSSWALK.md` for the full table. Additional actions taken:

| # | Command | Outcome | Notes |
|---|---|---|---|
| 13 | `git log --oneline -1` (working repository) | **PASS** | Confirmed the report's stated commit `79c488c7...` is the actual HEAD, not stale. |
| 14 | Manual diff of `configs/retrieval.json` against Appendix A's stated protocol constants | **PASS** | Exact match on all 7 constants. |
| 15 | `python3 -c "..."` inline check of `corpus_audit/FINAL_CORPUS_AUDIT.json` against Table 1/Figure 1/Figure 3 | **PASS** | Exact match on document count, live chunk count, edge counts (all 4 relations), and authority-class breakdown (all 8 categories). |
| 16 | Manual diff of `FINAL_RESULTS_TABLE.csv` against Tables 2 and 3 | **PASS** | Exact match on every cell of both tables. |
| 17 | Recursive stale-path grep across `TECHNICAL_APPENDIX.md` | **FAIL -> fixed** | Found and corrected 9 stale path references left over from the pre-finalization bundle's directory layout (see `CHANGELOG_FINALIZATION.md`). Re-scanned clean after the fix. |
| 18 | `python3 make_candidate_ceiling_figure_CORRECTED.py` | **PASS** | Produced `candidate_ceiling_CORRECTED.png` (24/31/5 with percentage labels) without modifying the frozen `make_figures.py` or its original (buggy) output. |
| 19 | Re-run of item 12 (`scripts/verify_bundle.py`) after all of the above | **PASS** | 0 failures, 0 warnings; 340 manifest entries checked, 115 Python files syntax-clean, 20/20 freeze hashes match. |

**Finding requiring action outside this bundle**: item 15/16's cross-check also surfaced that the
submitted thesis report's Abstract, Section 4.2, Figure 5, Section 5.5, and Chapter 7 still state
the pre-correction candidate-ceiling classification (15/40/5, 66.7%, 88.9%) rather than the
corrected classification (24/31/5, 51.7%, 86.1%) already applied throughout this bundle's
`STATIC_BENCHMARK_FINAL_REPORT.md`. This is a correction to the thesis report text itself, not a
bundle defect -- see `PAPER_CLAIMS_CROSSWALK.md` for exact locations.
