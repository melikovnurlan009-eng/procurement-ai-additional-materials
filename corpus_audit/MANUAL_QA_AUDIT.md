# Manual / Agent QA Audit — Corpus Construction

**Bottom line, stated first:** no human review of any kind has occurred anywhere in this
repository for chunk quality, relevance judgments, or reference-resolution edges. Every
"manual"/"human review" artifact found is either (a) an empty template with unfilled
human-input columns, (b) explicitly disclosed in the repo's own text as LLM/agent-performed
despite using the word "manual," or (c) a documented gap the repo itself flags as not-yet-done.
All QA that was actually performed is automated (deterministic scripts) or LLM-judge-based.

## QA activity table

| QA_activity | stage | what_was_checked | sample_size | method | result | evidence_file_or_log | human_or_agent |
|---|---|---|---|---|---|---|---|
| Structural defect detection | chunk quality | severed sentences, orphaned list items, dangling connectives, size, metadata gaps | full corpus (744-973 chunks per run) | deterministic regex/heuristics | 93.4% defect-free on one snapshot | `METHODOLOGY.md:263-274`, `data/search_corpus_v2/chunk_quality_report.json` | automated (script) |
| Chunk quality rubric judging | chunk quality | boundary correctness, coherence, 6 dimensions, 1-5 scale | up to 120 sampled | `evaluate_chunk_quality.py` "judge" mode, `gpt-4o-mini` | scores recorded, not independently confirmed | `evaluate_chunk_quality.py:346-407` | agent (LLM) |
| GOOD/INCOMPLETE/LOW_VALUE labelling | chunk quality (retrieval-unit usefulness) | 900 stratified chunks | 900 | `label_chunk_quality_llm.py`, `gpt-4.1`, temp 0 | 21% GOOD / 56% INCOMPLETE / 23% LOW_VALUE | `evaluation/chunk_quality_llm/summary.json` | agent (LLM) |
| Bad/good chunk export by domain | chunk quality | representative failure examples per domain | 6 per label per domain | `export_bad_chunks_by_domain.py`, `export_good_chunks.py` | files written for a reader | `evaluation/bad_chunks_by_domain/`, `evaluation/good_chunks_by_source/` | prepared for human, **no evidence anyone opened it** |
| Reference-resolution edge precision spot-check | graph/reference | stratified sample with `MANUAL_VERDICT`/`MANUAL_NOTES` columns | 251-254 rows | template created for human labelling | **0 rows filled** | `data/search_corpus_v2/reference_resolution_review_sample.jsonl` (confirmed by direct inspection: `MANUAL_VERDICT` non-empty count = 0) | **template only -- not performed** |
| Corpus-inclusion triage (KEEP/REVIEW/EXCLUDE) | source inclusion | 1,885 rows flagged REVIEW by automated validator | 1,885 | `corpus_validation_v2/manual_review_workbook.xlsx`, auto-generated template | **0 rows filled** (`MANUAL_DECISION`/`MANUAL_NOTES` both empty; `created`==`modified` to the second) | `corpus_validation_v2/validation_summary.json` (`"manual_review_required": true, "freeze_ready": false"`) | **template only -- not performed** |
| Graded-relevance judgment (qrels) | pointwise judging | first-pass relevance grading | 60 of 300 queries (20%), dev split only, 2 of 7 suites | LLM first-pass, `gpt-4o-mini` | review queue created but never consumed; `data/evaluation/manual_annotations.jsonl` does not exist anywhere in the repo | `THESIS_EVIDENCE_PACK.md:422`, `thesis_evidence/_section16_18_eval_datasets.md:89-110` | agent (LLM); **human review step never happened** |
| Workbench pilot/DEV/TEST spot-checks (this thesis's own final evaluation) | retrieval/judgment QA | 6 named cases across bundle and pointwise judgments | 6 of 726+5,895+387 pooled judgments | re-reading saved outputs against requirement text | all 6 confirmed as genuine differences, not artifacts | `procurement_research_workbench_v1/results/final/MANUAL_EVALUATION_AUDIT.md` | **agent, explicitly self-disclosed as such in the file's own binding framing note** |
| Corpus/PAPER.md claim cross-check | documentation | 4 cited figures checked against source data | 4 | agent-conducted cross-check | discrepancies found and corrected (e.g. edge-count staleness) | `FINAL_FACT_CHECK.md` | agent |

## Terminology discipline applied throughout this audit

If a review was performed by an LLM/agent, it is labelled "agent-conducted QA" or
"automated/agent-assisted QA" everywhere in this audit and its companion files. The phrase
"human manual review" is used only where direct textual evidence shows a human actually
performed it — **no such evidence was found anywhere in this repository**, so that phrase does
not appear as a positive claim in any corpus-construction document produced by this session.

Where an exact sample size for a "spot-check" claim could not be independently confirmed (e.g.
some `PAPER.md`/`METHODOLOGY.md` prose referring to earlier ad hoc checks with no surviving log),
this audit states: *"targeted manual spot-checking was performed; exact sample count was not
recorded"* rather than inventing a number.

## Reusable prior documentation (read, not re-derived)

- `reproducibility/` — a substantial, already-written reproducibility record for corpus
  `baseline_v1` (frozen 2026-08-18, git tag `baseline-v1`), including a full "how to reproduce"
  sequence and `KNOWN_GAPS_baseline_v1.md`, which itself already documents that the acquisition/
  parsing pipeline for baseline_v1 is not reproducible from the checked-in repository — the same
  finding this audit independently reached for the Procurement Pathway crawler specifically (see
  `FINAL_CORPUS_AUDIT.md` section C).
- `thesis_evidence/` — a prior draft audit pass (generated 2026-09-07) covering similar ground,
  including its own self-flagged corpus/graph snapshot staleness warning (independently confirmed
  by this audit's own fresh database queries — see `FINAL_CORPUS_AUDIT.md` section A).
- `thesis_evidence/missing_evidence.md` explicitly lists "no human review of any LLM relevance
  judgment" as a known gap — directly corroborating this audit's own finding.

## What this audit did NOT find (explicitly, not silently)

- No log, note, or file anywhere records a human opening `evaluation/bad_chunks_by_domain/`,
  `evaluation/good_chunks_by_source/`, `export_chunk_samples.py` output, or
  `export_retrieval_results.py` output and recording a judgment.
- No evidence any human inspected Procurement Pathway child URLs specifically, oversized chunks
  specifically, or duplicate-detection output specifically, beyond what the deterministic
  dedup/validation scripts themselves computed.
- No evidence of expert legal review of any gold citation, chunk, or graph edge.
