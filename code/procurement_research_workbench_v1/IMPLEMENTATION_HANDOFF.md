# Repository-side handoff

You are continuing an existing MSc procurement retrieval project. This package is implemented. Do not regenerate its datasets, rewrite its evaluation metrics or redesign its controller before testing integration.

1. Read START_HERE.md, docs/RESEARCH_PROTOCOL.md, and research_state/LAST_CHECKPOINT.md.
2. Use the project's existing embedding Python environment. Install this folder editable and run the unit tests and fixture smoke test. Never report fixture scores as procurement results.
3. Verify PRW_REPO_ROOT, SQLite/Qdrant snapshot and actual ChunkRetriever signatures. Run scripts/check_adapter.py. If a small interface mismatch exists, adapt only that boundary and add a regression test.
4. Keep data/test_sealed and private evaluator requirements out of coding/planning prompts. Do development work with the public DEV questions. Label construction runs in a separate evaluator process.
5. First run a small DEV integration pilot, then hybrid, legal_static, planned_multisearch and adaptive on the same DEV cases and final evidence budgets. Do not promise improvements or select cases by success.
6. Prefer three-judge combined-bundle sufficiency for the primary scenario coverage experiment. Add pooled passage judging/nDCG if credits and time permit. Every evaluated output must be judged; unjudged is not zero.
7. Three judges use the same rubric and do not see system identities. Evidence-support/applicability disagreements require adjudication. Report silver provenance and per-judge sensitivity.
8. Finish all intended policy choices before freezing test, requirements, configurations, external source snapshot and model IDs. Run every frozen method on the same test cases. Do not feed evaluator requirements or labels to the adaptive policy.
9. Keep source-side alias experiments isolated. Source text remains unchanged; benchmark questions cannot populate keywords.
10. For answer evaluation use identical generator settings across systems. Legal correctness requires verified independent reference excerpts. Without those, leave it unscored and report grounding/completeness instead.
11. Preserve every run and update research_state/LAST_CHECKPOINT.md after each stage. Budget/network failures must stop and resume, not produce fake completed results.
12. Return run JSONLs, silver labels, result summaries, figure files and a compact list of unsupported claims. Do not rewrite the whole dissertation until the evidence exists.

Current limitations: production adapter not executed against the user's local backend here; no external model judgments run; test scenarios not expert validated; corpus sufficiency not audited; no new measured retrieval gains.
