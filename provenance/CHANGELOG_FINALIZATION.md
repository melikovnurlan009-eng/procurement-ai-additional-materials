# Changelog: Finalization Audit (2026-09-07)

This changelog documents every change made while auditing and finalizing
`ADDITIONAL_MATERIALS_BUNDLE_2026-09-07.zip` into `ADDITIONAL_MATERIALS_FINAL_2026-09-07.zip`.
The original bundle and its zip are untouched. No raw experimental result (a retrieval run, a
judgment, a frozen metric) was modified; where a *derived* number was wrong due to a script bug,
that is listed under Analytical corrections below with the exact old/new values, the artifact
used, and the script used to recompute it.

## Packaging fixes

- **Corrected import path** (`code/evaluation/final_retrieval_benchmark/run_retrieval_configs.py`
  imports `chunk_retrieval` via `sys.path.insert(0, str(parents[2]))`): the original bundle split
  `chunk_retrieval.py` and the standalone benchmark into unrelated sibling directories, breaking
  this relative-path assumption baked into the (unmodified) frozen script. Fixed by restructuring
  `code/` to mirror the original repository's directory depths exactly (`code/chunk_retrieval.py`,
  `code/evaluation/final_retrieval_benchmark/*.py`), so `parents[2]` resolves correctly with zero
  edits to the frozen script itself. Verified: `from chunk_retrieval import ChunkRetriever`
  succeeds from the correct working directory.
- **Removed absolute local path**: `code/evaluation/final_retrieval_benchmark/
  build_final_tables.py` line 16 hardcoded `OUT_DIR = Path("/Users/nurlanmalikov7294/...")`.
  Replaced with `BENCH_DIR.parents[1] / "procurement_research_workbench_v1" / "results" /
  "final"`, a bundle-relative path. This is a packaging fix, not a behaviour change: verified the
  script produces byte-identical `FINAL_RESULTS_TABLE.csv`/`PAIRWISE_STATISTICS.csv` content
  before and after (same p-values, same deltas).
- **Added missing evaluation data and schemas**: `code/procurement_research_workbench_v1/data/
  {dev,test_sealed,pilot3}/*.jsonl` and `schemas/*.schema.json` were present in the source
  repository but omitted from the original bundle, causing 3 of 60 unit tests to fail with
  `FileNotFoundError`. Copied verbatim from the source repository (not regenerated). Result: 60/60
  tests now pass (was 57/60).
- **Added the actual DEV/TEST dataset used for reported results**: `evaluation/
  final_retrieval_benchmark/workbench_schema/{scenarios,requirements}_{dev,test}.jsonl` and
  `content_hash_manifest.json` were entirely absent from the original bundle (only the converter
  script that produced them was included) -- this is the dataset that produced every reported
  DEV/TEST number in `MATCHED_DEV_FINAL_REPORT.md`/`TEST_FINAL_REPORT.md`. Now included in full.
- **Added raw DEV/TEST run and judgment artifacts**: consolidated `runs.jsonl`,
  `model_events.jsonl`, `manifest.json`, `judgments_raw.jsonl`, `qrels_silver.jsonl` for all 4
  systems x 2 splits, plus the pooled candidate files and per-scenario evaluate output, are now
  included (`results/runs/`, `results/judgments/`, `results/pool/`, `results/evaluate_output/`).
  Per-scenario checkpoint caches and per-candidate judge-request caches were deliberately
  excluded as fully redundant with these consolidated files -- see `missing_artifacts.md` section
  4 for exact sizes and restoration notes.
- **Added missing corpus pipeline modules**: `scrapers/legislation/
  group_a_legislation_scraper_v4.py` (required for corpus reproduction, category A) was present
  in the source repo under a nested path not copied by the original bundle; now included at the
  correct relative path. `evaluate_chunk_quality.py`, `label_chunk_quality_llm.py`,
  `export_bad_chunks_by_domain.py`, `export_good_chunks.py` (category B, evaluation/QA tooling)
  added at `code/`. `answer_query.py`, `refine_query.py`, `query_expansion.py` were initially
  categorized as an unused demo layer and placed at `code/unused_demo_api/` -- **this was wrong
  and is corrected below** (see "Correction: the deployed application layer was mislabeled as
  unused").
- **Added the Procurement Pathway frozen URL manifest**: `procurement_pathway_urls.jsonl` and its
  sample files were entirely absent from the original bundle despite being referenced in prose as
  the acquisition boundary for that source family; now included at `corpus_manifests/`.
  (**Correction below**: this bullet originally said the discovery crawler itself was
  unavailable -- that was wrong and was corrected in a later pass; see "Correction to an earlier
  finding" further down this document and `missing_artifacts.md` section 1 for what was actually
  found.)
- **Removed packaging noise**: `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `.pyc`,
  `.DS_Store` removed throughout. No `.env` files or API keys were found anywhere in the original
  bundle (confirmed by an explicit secret-pattern scan, `scripts/verify_bundle.py`).
- **Removed ~370 MB of redundant duplication**: the original bundle's full copy of
  `procurement_research_workbench_v1/` included its own `runs/`, `judgments/`, `pool/`, and
  `results/{dev_scale,test_final,final}/` directories in full, duplicating what is now curated
  once under the top-level `results/` directory (with caches already stripped there). Removed
  the duplicate copies inside the package tree; the package's own code (`prw/`), tests, data,
  schemas, and configs are unaffected and the test suite still passes 60/60 after this removal.

## Documentation corrections

- **Corrected statistical-significance wording** (`STATIC_BENCHMARK_FINAL_REPORT.md`): the claim
  "`A_lexical` is statistically significantly worse than every other configuration (p < 0.05 in
  all 5 pairwise comparisons)" is false. Recomputed directly from
  `PAIRWISE_STATISTICS.csv`/`build_final_tables.py`: `A_lexical` vs `B_dense` has p=0.05224 (two-
  sided exact sign test, n=60, no multiple-comparison correction), which does **not** cross
  alpha=0.05. Corrected to: significantly worse than 4 of 5 configurations (`C_hybrid` p=0.00049,
  `D_hybrid_priors` p=0.0004, `E_hybrid_graph` p=0.0004, `F_two_lane` p=0.00149); the `B_dense`
  comparison is reported as not significant. Same correction propagated to `FINAL_THESIS_
  FINDINGS.md` (which did not repeat the specific overclaim but is checked for consistency) and
  the `provenance/artifact_manifest.csv`-referenced source data.
- **Clarified held-out TEST terminology**: `FINAL_THESIS_FINDINGS.md` RQ1 previously read
  "confirmed independently on both DEV and TEST" — ambiguous next to a TEST split that was not
  independently executed. Reworded to "replicated on both the DEV split and the frozen TEST
  split," with an explicit parenthetical clarifying that "replicated" refers to the statistical
  pattern holding on a second disjoint sample, not to independent execution (which
  `TEST_FINAL_REPORT.md` already disclosed was not the case).
- **Corrected planned-vs-adaptive methodology language**: `CASE_STUDIES.md` and `FINAL_THESIS_
  FINDINGS.md` both previously described `planned_multisearch` and `adaptive` as using "the same
  decomposed queries" / "same decomposition." Verified against `prw/controller.py`:
  `AdaptiveController.run()` is invoked separately for each system, each making its own
  independent, unseeded LLM planner call -- there is no code path that reuses one system's
  decomposition for the other. Corrected to state the two conditions share the same controller
  architecture and maximum retrieval budget, but independently generate their own (stochastic,
  not guaranteed identical) query decompositions.
- **Documented the F_two_lane / legal_static relationship precisely**: added an explicit note
  (`TECHNICAL_APPENDIX.md` section 8) that the standalone benchmark's `F_two_lane` (candidate
  depth 50, per `run_retrieval_configs.py::DEPTH`) and the workbench's `legal_static` (candidate
  depth 100, per `configs/retrieval.json`) implement the same high-level two-lane retrieval idea
  but are not numerically identical configurations -- confirmed the two are never directly
  compared as if identical in any of the final reports (checked by grep across all report files),
  but the relationship is now stated explicitly rather than left implicit.

## Analytical corrections

- **Recomputed candidate-generation vs. ranking-failure classification.** `candidate_ceiling.py`
  had a classification-order bug: it checked "gold absent from the lexical+dense union" before
  checking "gold present in the final top-10." Because the final top-10 (from `config_F_two_lane`)
  is also fed by graph expansion, any scenario recovered only via that channel (present in final
  top-10, absent from the narrower lexical+dense union) was misclassified as a
  candidate-generation failure instead of a success. **Old (buggy) values**:
  `OK_FOUND_IN_FINAL_TOP10`=15 (25.0%), `CANDIDATE_GENERATION_PROBLEM`=40 (66.7%),
  `RANKING_PROBLEM`=5 (8.3%). **Corrected values**: `OK_FOUND_IN_FINAL_TOP10`=24 (40.0%),
  `CANDIDATE_GENERATION_PROBLEM`=31 (51.7%), `RANKING_PROBLEM`=5 (8.3%, unchanged -- the bug only
  affected the OK/CANDIDATE_GENERATION boundary). Exactly 4 scenarios' classification changed:
  `DEV012`, `DEV038`, `TEST016` (RANKING_PROBLEM -> OK), `DEV027` (OK -> RANKING_PROBLEM, the one
  case where the old script's bug happened to work in the "success" direction by coincidence of
  which branch it hit first). Source artifact: `gold_evidence.jsonl`, `retrieval_runs/
  config_{A_lexical,B_dense,F_two_lane}.jsonl` (unchanged, frozen). Script used: `candidate_
  ceiling_CORRECTED.py` (new; original `candidate_ceiling.py` preserved unmodified alongside it
  for audit trail). Updated in `STATIC_BENCHMARK_FINAL_REPORT.md` sections 2, 6, and 9 (claims 1
  and the headline split), and in the corresponding figure caption note.

## Added: the corpus database and a Qdrant snapshot, so the application actually runs (2026-09-08, at the author's explicit request)

The author asked directly whether the application could be made to work fully standalone, after
being shown that `/health`/`/search`/`/answer`/`/refine` all fail without a real corpus database
and a populated Qdrant instance. Rather than leave that as a documented limitation, the following
were added:

- `code/state/chunk_index_merged.sqlite3` (262 MB) -- the actual corpus database, copied
  directly from the project's own `state/` directory. Previously excluded per the handbook's
  Appendix 4.1 note ("an examiner does not need direct access to re-run acquisition"); included
  now because the author explicitly asked for a working application, not only reproducible
  results.
- `qdrant_snapshot/chunks__bge_m3__merged.snapshot` (156 MB) -- a live snapshot of the actual
  Qdrant collection (22,042 points), taken via Qdrant's own snapshot API directly from the
  project's running instance and downloaded with its checksum verified
  (`bd2d954494f49bb9cfb374ff5efd92f822b71ca5602d7d5112046d45fe096810`, confirmed to match on
  download).
- `docker-compose.yml` (bundle root) and `scripts/restore_qdrant_snapshot.py` -- start a local
  Qdrant container and restore the snapshot into it, verifying the restored point count matches
  the documented corpus size exactly (22,042) before reporting success.
- `.env.example` -- a template for the one thing that is still deliberately **not** included: an
  OpenAI API key. A real credential cannot ship in a distributed academic package under any
  circumstances; the author was told this directly rather than the request being silently
  partially fulfilled. `/search` and `/health` need no key at all; only `/answer`/`/refine` do.

**Tested end-to-end, not merely assembled**: an isolated Qdrant instance was started on a
non-default port (so the author's own running instance was left untouched), the included
snapshot was restored into it (confirmed `status: green`, `points_count: 22042`), and the actual
`chunk_api.py` was pointed at the included database and that instance. A real `/health` call
returned correct corpus statistics with `openai_key_present: false`; a real `/search` call for
"standstill period before contract award" correctly returned `UKPGA_2023_54__NODEV1__CH_00051`
(PA2023 s.51) as its top result -- the same provision discussed in this bundle's own DEV003/
TEST019 case study. All test artifacts (the isolated Qdrant container, its volume, the
temporary uploaded snapshot copy on the author's own running instance) were cleaned up
afterward; the author's original Qdrant instance and its four collections were confirmed
untouched.

**Also found and fixed while investigating this**: `verify_bundle.py`'s secret scanner treats
any `.env*` file as a failure, which would have flagged the newly-added `.env.example` as a
false positive (it is a template containing no real secret, by design, and is the conventional,
safe way to document required environment variables). The scanner was updated to allow
`.env.example`/`.env.sample`/`.env.template` specifically, while still scanning their contents
for anything that actually looks like a real key and still failing on any other `.env*` file.

## Superseded: pre-built database/snapshot replaced with export + rebuild (2026-09-08, at the author's further request)

The above approach (shipping the 262 MB database and 156 MB Qdrant snapshot directly) was
**removed** after the author asked, in a follow-up message, not to ship pre-built binary
database/embedding artifacts at all -- instead, to include the underlying data plus scripts and
document an exact, tested sequence that produces the same working application. Both large files
were deleted from the bundle.

In their place:
- `code/corpus_export/export_corpus_from_db.py` -- exports the frozen database's own live
  chunks/documents/edges tables to JSONL (ground truth, not reconstructed from raw sources).
- `code/corpus_export/data/*.jsonl` (91 MB, run and included) -- that export's actual output:
  22,042 chunks, 2,078 documents, 15,678 structural + 11,922 reference edges -- confirmed to
  match the documented corpus counts exactly.
- `scripts/rebuild_search_index.py` -- runs the existing, unmodified `build_chunk_index.py`
  (lexical, then dense) plus `densify_graph_edges.py`, against that export, to reconstruct a
  fresh, working SQLite FTS5 index and Qdrant collection.

**A real gap was found and fixed while testing this sequence, not merely assumed to work**:
`build_chunk_index.py`'s own schema does not create three columns
(`retrieval_source_id`/`retrieval_target_id`/`retrieval_resolution`) that `chunk_retrieval.py`
requires at query time. Running `/search` against a database built by `build_chunk_index.py`
alone fails with `sqlite3.OperationalError: no such column: retrieval_source_id`. The missing
step, `densify_graph_edges.py --apply`, was identified (it is the script that adds and populates
those columns) and inserted into `rebuild_search_index.py` as stage 2 of 3. This is exactly the
kind of gap a "looks complete" script sequence can hide until someone actually runs it end to
end; it is documented here and in `TECHNICAL_APPENDIX.md` section 0.5 rather than silently
patched over.

**Tested end to end, at full scale, to completion**: the full 22,042-chunk lexical +
graph-densification stages were run against the complete export and matched the documented
corpus exactly. The full dense (embedding) stage was then also run to completion -- 24 minutes
38 seconds, producing exactly 22,042 vectors -- after two earlier partial observations had
suggested this could take 90 minutes to a few hours. A real `/health` and `/search` call against
the completed, full-scale rebuilt database and Qdrant collection confirmed `chunks: 22042,
edges: 27600, dense_ok: true`, and returned the correct top result (`UKPGA_2023_54__NODEV1__CH_00051`,
PA2023 s.51) for the same test query used throughout this pass. One nuance found and explained,
not hidden: the rebuilt database's `documents` count reads 1,737, not 2,078, because
`build_chunk_index.py` derives its documents table from the chunks table itself (aggregregating
distinct `document_id` values) rather than reading the included `documents.jsonl` export -- 1,737
is exactly the count of documents with at least one live chunk; the other 341 of the original
2,078 rows belong to documents whose chunks were all later superseded as duplicates. See
`TECHNICAL_APPENDIX.md` section 0.5 for full detail.

## Correction: the deployed application layer was mislabeled as unused (2026-09-08, prompted by author question)

The author asked whether the bundle contains "the last version which thesis used as application
behind" -- not just the evaluation pipeline. Checking `chunk_api.py` (the production FastAPI
service, already included) directly found `from answer_query import build_evidence_two_lanes,
verify, check_claim_grounding, ...` in its `/answer` endpoint and `from refine_query import
refine` in its `/refine` endpoint -- both bare, sibling-directory imports. These two files had
been placed in `code/unused_demo_api/` on the earlier, wrong assumption that they were an unused
demo layer; in that location, `chunk_api.py`'s own imports would not resolve and the running
application's `/answer` and `/refine` endpoints would fail with `ModuleNotFoundError`. This was
a real packaging defect, not merely a mischaracterization.

**Fixed**: moved `answer_query.py`, `refine_query.py`, `query_expansion.py` to `code/` (sibling
to `chunk_api.py`); confirmed with a fresh import smoke test (`import answer_query`, `import
refine_query`) that both now resolve cleanly. Also added `streamlit_app.py` (not previously
included at all), the fuller "Procurement KG Assistant" UI that talks to the same FastAPI
backend via the already-included `procurement_kg/ui.py::call_answer()`. `TECHNICAL_APPENDIX.md`
section 0.5 now documents the application layer explicitly (what each file does, what's required
to actually run it -- corpus DB, Qdrant, OpenAI key, none of which are included, consistent with
the Level 3 dependency already disclosed for retrieval reruns generally).

## Correction to an earlier finding (2026-09-08, prompted by author pushback)

**The earlier claim that the Procurement Pathway discovery crawler was "genuinely unavailable"
was wrong**, and is corrected here rather than left standing. The author pointed out that an
end-to-end crawling script exists in the project and had been iterated on multiple times; a
targeted re-search (for crawler-internal vocabulary like `SAME_SITE_RELEVANT_LINK`,
`seed_roots`, `exact_count_certified` rather than filenames containing "pathway"/"crawl") found
it at `scripts/procurement_doc_counter/count_documents_relevance.py` -- a genuine, documented,
969-line link-following crawler with explicit `PROCUREMENT_PATHWAY` handling. It is now included
at `code/scrapers/procurement_doc_counter/` (script + its own `README.md` + `seeds.json`).

What genuinely is still missing, after this correction, is narrower than originally claimed: the
crawler's raw output (1,950 Procurement Pathway pages, dated 2026-08-25, preserved in the
source project's `crawl_v2_relevant/` directory) was later refined -- deduplicated, topic-
annotated, and per-page included/excluded -- into the final 1,690-URL manifest actually used in
this project (`corpus_manifests/procurement_pathway_urls.jsonl`, dated 2026-08-27). No script
producing that specific refinement (fields like `topic_slug`, `include_decision`,
`content_role`) was found anywhere in the repository. So: the discovery crawl is included and
reproducible; the later curation step that produced the exact final manifest is not. Corrected
throughout `missing_artifacts.md` section 1, `TECHNICAL_APPENDIX.md` (§2.1, §7, §18), and
`README.md` (items 4, 5, Level 4).

## Additional corrections (2026-09-08 pass, after direct cross-check against the submitted thesis PDF)

- **Regenerated the candidate-ceiling figure with corrected counts**: the existing
  `candidate_ceiling.png` (both copies, `code/evaluation/final_retrieval_benchmark/figures/` and
  `results/final_reports/figures/`) still plotted the pre-correction 15/40/5 split, because
  `make_figures.py::fig_candidate_ceiling()` reads `candidate_ceiling_summary.json` (the
  original, buggy file) rather than `candidate_ceiling_CORRECTED_summary.json`. Per this
  project's rule against silently changing frozen script behaviour, `make_figures.py` was left
  unmodified; a new script, `make_candidate_ceiling_figure_CORRECTED.py`, was added alongside it
  and produces a separate file, `candidate_ceiling_CORRECTED.png` (24/31/5, with percentage
  labels), in both figures directories. The original, uncorrected `candidate_ceiling.png` is
  left in place for audit-trail purposes, exactly as `candidate_ceiling.py` was preserved
  alongside `candidate_ceiling_CORRECTED.py`.
- **Fixed systemic stale path references in `TECHNICAL_APPENDIX.md`**: the file was originally
  copied from the pre-finalization bundle and still referenced that bundle's directory layout
  (`results_summary/corpus_audit/`, `results_summary/final_evaluation/`,
  `code/retrieval_system/chunk_retrieval.py`, `code/evaluation_workbench/configs/retrieval.json`,
  `code/evaluation_workbench/prw/`, `code/standalone_benchmark/`, `code/configs/requirements.txt`)
  instead of this bundle's actual paths. All instances corrected to the real paths
  (`corpus_audit/`, `results/final_reports/`, `code/chunk_retrieval.py`,
  `code/procurement_research_workbench_v1/configs/retrieval.json`,
  `code/procurement_research_workbench_v1/prw/`, `code/evaluation/final_retrieval_benchmark/`,
  `code/requirements.txt`) so every path an examiner follows from the appendix actually resolves.
- **Cross-checked every major numeric claim in the submitted thesis PDF against bundle
  artifacts** (`provenance/PAPER_CLAIMS_CROSSWALK.md`): repository commit hash, retrieval
  protocol constants, corpus/graph statistics (Table 1), static benchmark results (Table 2),
  matched DEV/TEST results (Table 3), and the significance/TEST-independence/planned-vs-adaptive
  wording corrections were all found to match bundle artifacts exactly and/or already reflect
  this project's earlier corrections. **One exception was found and is not yet corrected in the
  submitted report itself**: the candidate-generation-ceiling numbers in the report's Abstract,
  Section 4.2, Figure 5, Section 5.5, and Chapter 7 still state the pre-correction 15/40/5
  (25.0%/66.7%/8.3%) split and an "88.9% of failures" figure, not the corrected 24/31/5
  (40.0%/51.7%/8.3%) split and 86.1% figure already applied throughout this bundle's own
  documentation. This is flagged as a required correction to the thesis report text itself, not
  merely to this additional-materials package — see `PAPER_CLAIMS_CROSSWALK.md` for exact page/
  section references and the corrected replacement figure now included at
  `results/final_reports/figures/candidate_ceiling_CORRECTED.png`.

## Added reproducibility artifacts

- `environment/pip-freeze.txt`, `requirements-lock.txt`, `environment_notes.md` -- exact
  currently-verified package versions, Python version, OS/platform, and an explicit distinction
  from the (unrecoverable) historical corpus-build environment.
- `corpus_manifests/procurement_pathway_urls.jsonl` and sample files -- the frozen acquisition
  boundary for the largest source family (see Missing artifacts section 1 for what this does and
  does not make reproducible).
- `scripts/verify_freeze.py` -- recomputes and checks all 20 frozen code/config hashes in
  `prw_freeze_record.json` against the included code. Currently: PASS.
- `scripts/verify_bundle.py` -- automated static bundle validator (see `FINAL_VALIDATION_REPORT.md`
  for its output).
- `scripts/generate_manifests.py` -- regenerates `MANIFEST.sha256` and `provenance/
  artifact_manifest.csv` from the bundle's actual current contents (not hand-typed).

## Unresolved limitations (carried forward, not fixed)

- The Procurement Pathway discovery crawler's source code remains unavailable (see
  `missing_artifacts.md` section 1).
- The exact historical corpus-build environment (package versions at build time) remains
  unrecoverable (section 2).
- The embedding model's exact revision/commit hash was never logged and remains unrecoverable
  (section 3).
- TEST execution was not performed by an independent evaluator (section 5) -- this is a
  methodological limitation of the underlying research, not something a packaging fix can
  resolve; it is disclosed, not concealed.
- LLM calls throughout the pipeline (corpus text-emission chunking, controller planning/
  observation, judging) are not seeded/deterministic; only the paired-bootstrap statistics
  computed from already-saved outputs are exactly reproducible.
