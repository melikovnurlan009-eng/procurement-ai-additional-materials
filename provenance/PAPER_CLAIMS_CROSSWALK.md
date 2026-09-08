# Thesis Report Claims Crosswalk

This document cross-checks every major quantitative claim in the submitted thesis report
(`14322782_DATA72000.pdf`, "A Legal-Structure-Aware Retrieval System for a UK Public Procurement
AI Assistant") against the artifacts actually included in this bundle, so an examiner (or the
author) can verify each number independently rather than trusting the report's prose alone. This
was produced during the 2026-09-07/08 finalization pass, after the corrections already recorded
in `CHANGELOG_FINALIZATION.md`.

## Verified exact matches

| Report claim | Report location | Bundle artifact | Verified value |
|---|---|---|---|
| Repository commit `79c488c7103078633159e26bdfe24e7410313821` | Appendix A | this project's own git history (`git log --oneline -1` on the working repository, run during this audit) | Confirmed: this commit is the real HEAD of the working repository, not a stale or unverifiable reference. |
| Candidate depth 100, retrieval depth 20, final k=10, context cap 18,000 chars, max 3 retrieval operations, graph fan-out 20, graph hops 1 | Appendix A | `code/procurement_research_workbench_v1/configs/retrieval.json`, `code/chunk_retrieval.py` (`hops: int = 1` default) | Every constant matches exactly, field-for-field. |
| Corpus snapshot `state/chunk_index_merged.sqlite3`, Qdrant collection `chunks__bge_m3__merged` | Appendix A | literal default values across `code/chunk_retrieval.py`, `code/chunk_api.py`, `code/analyze_graph.py` and others | Names match exactly; the database/vector-index contents themselves are not included (Level 3, see README). |
| 2,078 source documents; 22,042 live chunks; 27,600 graph edges | Table 1 | `corpus_audit/FINAL_CORPUS_AUDIT.json` → `final_counts.total_documents`, `.total_edge_rows`, sum of `live_chunks_by_authority_class` | 2078 / 22042 / 27600 — all exact matches. |
| CONTAINS 6,489 / HAS_CHUNK 9,189 / REFERENCES 7,159 / CROSS_REFERS_TO 4,763 | Table 1, Figure 3 | `corpus_audit/FINAL_CORPUS_AUDIT.json` → `final_counts.edges_by_relation` | Exact match on all four counts. |
| Live chunks by authority class (8,850 / 7,642 / 2,253 / 1,630 / 823 / 530 / 165 / 149) | Table 1 text, Figure 1 | `corpus_audit/FINAL_CORPUS_AUDIT.json` → `final_counts.live_chunks_by_authority_class` | Exact match on all eight categories. |
| Static benchmark Table 2 (all six configurations, all four metric columns) | Table 2, Figure 4 | `results/final_reports/FINAL_RESULTS_TABLE.csv` (`scope=standalone_static_benchmark` rows) | Exact match to 3-4 significant figures on every cell (e.g. `A_lexical` req_coverage_10 0.550 = 0.55, `F_two_lane` strict_recall_10 0.264 = 0.2639). |
| Matched DEV/TEST Table 3 (all four systems, both splits, both metric columns) | Table 3, Figure 7 | `results/final_reports/FINAL_RESULTS_TABLE.csv` (`scope=matched_dev` / `matched_test_frozen` rows) | Exact match on every cell (e.g. TEST `adaptive` req_coverage 0.735 = 0.7353, nDCG10 0.551 = 0.5506). |
| Pairwise significance values (H1 p=1.1e-5 and p=0.0215; H3 p=0.375 and p=0.6875; A_lexical vs B_dense p=0.0522) | Section 4.1, 4.3, 4.4 | `results/final_reports/PAIRWISE_STATISTICS.csv`, reproducible via `build_final_tables.py` (re-run and confirmed during this audit — see `FINAL_VALIDATION_REPORT.md`) | Exact match; this specific significance wording ("just misses the conventional 0.05 cutoff") is already the corrected wording from `CHANGELOG_FINALIZATION.md` — **this correction is already reflected in the submitted report text**, not only in this bundle. |
| DEV token costs (1,271,466 vs 29,326) and TEST token costs (604,504 vs 15,365); fallback rates 52.5%/45.0% | Section 4.3, 4.4, 4.6 | `results/final_reports/CONTROLLER_DIAGNOSTICS.csv` | Present in the cited source file; not independently re-summed cell-by-cell in this pass, but the file exists and is the disclosed source. |
| TEST-independence and planned/adaptive decomposition wording (Sections 3.5, 3.6, Chapter 6) | throughout | `CHANGELOG_FINALIZATION.md` "Documentation corrections" | The report's actual wording ("replicates," "does not meet the bar of an independent evaluator," "independently generate their own... query decompositions") already matches the corrected language from this audit — **these two corrections are already reflected in the submitted report**, not only in this bundle. |

## Critical mismatch found — NOT yet corrected in the submitted report

**The candidate-generation-ceiling classification bug fix has NOT been applied to the thesis
report text**, even though it has been applied throughout this bundle's own documentation
(`STATIC_BENCHMARK_FINAL_REPORT.md`, per `CHANGELOG_FINALIZATION.md`).

The submitted report currently states, in at least four locations, the **pre-correction, buggy**
classification (`OK_FOUND_IN_FINAL_TOP10=15 (25.0%)`, `CANDIDATE_GENERATION_PROBLEM=40 (66.7%)`,
`RANKING_PROBLEM=5 (8.3%)`), and derives an "88.9% of scenarios that fail outright are
candidate-generation failures" figure from it:

- **Abstract** (p.7): "Forty of the 60 scenarios (66.7%) fail because the correct evidence never
  enters the retrieved candidate pool at all... among the 45 scenarios that fail outright,
  candidate-generation failures account for 88.9% of them."
- **Section 4.2** (p.31): "(25.0%, 15 scenarios)... (66.7%, 40 scenarios)... (8.3%, 5
  scenarios)," and "Framed against the 45 scenarios that fail outright... candidate-generation
  failures make up 88.9% of failures."
- **Figure 5** (p.31): bar chart plotting 15 / 40 / 5.
- **Section 5.5** (p.39): "66.7% of the 60 scenarios (88.9% of the 45 that fail outright) are
  candidate-generation failures."
- **Chapter 7 Conclusion** (p.42): "66.7% of this benchmark's 60 scenarios fail... (88.9% of the
  45 that fail outright)."

Recomputed directly from the frozen, unchanged scenario-level artifacts in this bundle
(`code/evaluation/final_retrieval_benchmark/candidate_ceiling_CORRECTED.py`, run during this
audit — see `FINAL_VALIDATION_REPORT.md` item 5), the corrected classification is:
`OK_FOUND_IN_FINAL_TOP10=24 (40.0%)`, `CANDIDATE_GENERATION_PROBLEM=31 (51.7%)`,
`RANKING_PROBLEM=5 (8.3%, unchanged)`. Scenarios that fail outright = 31 + 5 = 36 (not 45); the
candidate-generation share of those failures is 31/36 = **86.1%** (not 88.9%).

**This is a scientific correctness issue in the submitted report itself, not only in the
additional-materials bundle.** The bug is in the classification-order logic of
`candidate_ceiling.py` (see `CHANGELOG_FINALIZATION.md` for the exact root cause); it does not
reflect any error in the underlying retrieval runs, judgments, or corpus, all of which are
unchanged. Every other headline number checked in this crosswalk (corpus statistics, static
benchmark table, DEV/TEST table, pairwise significance, TEST-independence wording, planned/
adaptive wording) was found to already be accurate in the submitted report. This is the one
exception, and it is a load-bearing one: it appears in the Abstract and is restated as a
standalone conclusion in Chapter 7.

**Action needed**: the five locations listed above should be corrected to 40.0% / 51.7% / 8.3%
(24 / 31 / 5) and 86.1%, and Figure 5 regenerated with the corrected counts, before the report is
considered final. See `results/final_reports/figures/` (regenerated in this bundle) for a
corrected version of the figure that can be substituted directly.

**Which script reproduces which set of numbers, explicitly** (both are included, deliberately,
so the report's own numbers stay traceable even though they are now known to be wrong):

| To reproduce... | Run | Confirmed output |
|---|---|---|
| the exact numbers currently printed in the submitted PDF (15/40/5, i.e. 25.0%/66.7%/8.3%) | `code/evaluation/final_retrieval_benchmark/candidate_ceiling.py` (original, unmodified, still buggy on purpose) | `{"OK_FOUND_IN_FINAL_TOP10": 15, "CANDIDATE_GENERATION_PROBLEM": 40, "RANKING_PROBLEM": 5}` -- re-run and confirmed to match the PDF exactly during this audit. |
| the corrected numbers (24/31/5, i.e. 40.0%/51.7%/8.3%) that should replace them | `code/evaluation/final_retrieval_benchmark/candidate_ceiling_CORRECTED.py` (new) | `{"OK_FOUND_IN_FINAL_TOP10": 24, "CANDIDATE_GENERATION_PROBLEM": 31, "RANKING_PROBLEM": 5}` |

Do not delete or "fix" `candidate_ceiling.py` -- its job now is exactly to let an examiner verify
that the submitted report's stated numbers are real output of a real (if buggy) script, not a
typo or a fabricated figure, and to see precisely what changed when the bug is fixed.
