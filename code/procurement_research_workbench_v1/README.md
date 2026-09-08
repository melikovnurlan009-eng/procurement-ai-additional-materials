# Procurement Research Workbench 1.0

A runnable research layer for an existing UK procurement retriever: scenario evaluation, open-world silver relevance labels, bounded adaptive retrieval, answer assessment and source-side alias experiments.

**Status:** implementation and offline tests, not a completed empirical study. No production SQLite/Qdrant retrieval or external model calls were executed in this environment. The 40 development scenarios and 20 test candidates are source-guided, fictional research cases, not expert-validated ground truth. No corpus audit is included.

Start with [START_HERE.md](START_HERE.md). The quickest high-value experiment is a paired comparison of `legal_static`, `planned_multisearch` and `adaptive`, using the same final evidence budget and three-judge **bundle sufficiency**. Pointwise pooled judging adds nDCG and detailed ranking diagnostics but costs more model calls.

## What is included

- 60 scenario records, eight task suites and 22 topic labels; 12 prewritten follow-up cases.
- Public scenario files and separate private evaluator requirements. The controller's input class rejects answer-key fields.
- Production adapter based on the supplied `ChunkRetriever` interface, plus an optional targeted-graph sidecar.
- Conventional and legal static baselines; a budget-matched planned multi-search control; a bounded evidence-feedback controller.
- Three blinded judging paths: passage relevance, combined-bundle sufficiency, and generated-answer assessment.
- Exact source-span checks, content-version hashes, adjudication queues and resumable caches.
- Requirement coverage, complete-scenario rate, pooled nDCG, first-sufficient MRR, applicability diagnostics and scenario-group paired bootstrap.
- A label-aware, budget-constrained oracle diagnostic, deliberately unavailable to the runtime controller.
- Source-only keyword and contextual-alias generation; separate I0/I1/I2 FTS5 indexes.
- Reporting scripts, schemas, prompts, a predeclared protocol, integration examples and checkpoint documentation.

## Research questions

1. Which evidence requirements remain unmet by lexical, dense and conventional hybrid retrieval?
2. Do explicit source roles, legal priors and citation links improve retrieval under a fixed final evidence budget?
3. Does evidence-feedback control improve on both the static legal retriever and a multi-search planner with the same maximum number of operations?
4. Do any retrieval gains translate into better grounded, more complete answers with the same generator?

These are hypotheses, not conclusions. The package never fabricates empirical improvements or substitutes fixture results for thesis results.

## Install and test

From the unpacked folder, with the same Python interpreter used by your production embedding environment:

```bash
python -m pip install -e '.[dev,plots,diagnostics]'
python -m pytest -q
python -m prw validate-data
python scripts/smoke_pipeline.py
```

An editable installation is intentional: schemas, datasets and scripts remain alongside the code. Do not move an installed package away from its unpacked project resources.

## Reading order

1. `START_HERE.md`: commands and deadline-safe execution order.
2. `docs/RESEARCH_PROTOCOL.md`: fair comparisons, metrics and test isolation.
3. `docs/DATASET_CARD.md`: scope, construction, task distribution and limitations.
4. `docs/JUDGING_PROTOCOL.md`: what silver labels mean and how to avoid false negatives.
5. `docs/ADAPTIVE_CONTROLLER.md`: executable policy, stopping and failure handling.
6. `docs/KEYWORD_EXPERIMENT.md`: isolated alias intervention.
7. `docs/RESULTS_AND_CLAIMS.md`: interpretation and thesis reporting.
8. `IMPLEMENTATION_HANDOFF.md`: compact instructions for the repository-side operator.

The `test_sealed` directory name is an organizational boundary, not encryption. Keep it out of coding-agent prompts and development sessions. A checksum is also not proof of methodological independence.
