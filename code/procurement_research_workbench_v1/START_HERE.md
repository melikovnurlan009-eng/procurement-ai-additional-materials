# Start here

## 1. Check the package without spending API credits

Use your existing embedding Python environment rather than installing another copy of all models:

```bash
cd /path/to/procurement_research_workbench_v1
/path/to/your/repo/.venv-embed/bin/python3 -m pip install -e '.[dev,plots,diagnostics]'
/path/to/your/repo/.venv-embed/bin/python3 -m pytest -q
/path/to/your/repo/.venv-embed/bin/python3 -m prw validate-data
/path/to/your/repo/.venv-embed/bin/python3 scripts/smoke_pipeline.py
```

Below, `python` means that same interpreter. Fixtures test software only. Their numbers must never enter the thesis results.

## 2. Connect the existing retriever

```bash
export PRW_REPO_ROOT='/absolute/path/to/procurement-kg-rag'
export PRW_DB="$PRW_REPO_ROOT/state/chunk_index_merged.sqlite3"
export PRW_COLLECTION='chunks__bge_m3__merged'
export QDRANT_URL='http://localhost:6333'
export LOCAL_EMBEDDING_MODEL='BAAI/bge-m3'
```

Create a snapshot identifier that corresponds to a real saved SQLite backup, Qdrant snapshot and code commit. Supplying a label alone does not freeze your database. Do not copy a SQLite file while writes are in flight; use your repository's backup/export procedure.

Run the adapter capability check before a full experiment:

```bash
python scripts/check_adapter.py
```

The adapter fails explicitly on an incompatible method signature instead of dropping controls. It disables the legacy forced-legislation-promotion patch for conventional baselines. If necessary, supply a small `module:factory` wrapper using `examples/backend_factory.py`; do not rewrite your retriever.

## 3. Run development baselines

```bash
python -m prw run --scenarios data/dev/scenarios.jsonl --system hybrid \
  --snapshot YOUR_REAL_SNAPSHOT --out runs/dev/hybrid
python -m prw run --scenarios data/dev/scenarios.jsonl --system legal_static \
  --snapshot YOUR_REAL_SNAPSHOT --out runs/dev/legal_static
```

Other implemented static arms: `lexical`, `dense`, `hybrid_priors`, `hybrid_graph`, `hybrid_full`. All use the same configured per-channel candidate depth. The final legal bundle has ten items total, not ten per lane.

Do not claim that these settings are optimal. Select a small, predeclared development comparison, not an unrestricted parameter search.

## 4. Configure accessible model APIs

The transport accepts an explicitly configured Chat-Completions-compatible JSON endpoint. No model ID, key, price or provider availability is assumed. Native non-compatible APIs require a transport wrapper; do not assume a URL conversion is supported.

Set the model ID and credential for each slot:

```bash
export PRW_CONTROLLER_MODEL='YOUR_ACCESSIBLE_MODEL_ID'
export PRW_CONTROLLER_API_KEY='SET_LOCALLY_NEVER_COMMIT'
export PRW_GENERATOR_MODEL='YOUR_ACCESSIBLE_MODEL_ID'
export PRW_GENERATOR_API_KEY='SET_LOCALLY_NEVER_COMMIT'
export PRW_JUDGE_A_MODEL='YOUR_ACCESSIBLE_JUDGE_A'
export PRW_JUDGE_A_API_KEY='SET_LOCALLY_NEVER_COMMIT'
export PRW_JUDGE_B_MODEL='YOUR_ACCESSIBLE_JUDGE_B'
export PRW_JUDGE_B_API_KEY='SET_LOCALLY_NEVER_COMMIT'
export PRW_JUDGE_C_MODEL='YOUR_ACCESSIBLE_JUDGE_C'
export PRW_JUDGE_C_API_KEY='SET_LOCALLY_NEVER_COMMIT'
export PRW_ADJUDICATOR_MODEL='YOUR_ACCESSIBLE_ADJUDICATOR'
export PRW_ADJUDICATOR_API_KEY='SET_LOCALLY_NEVER_COMMIT'
```

The corresponding `PRW_*_ENDPOINT` variables override the default endpoint. `configs/models.json` contains input caps, bounded retries and configurable request parameters. Verify supported parameters for the selected endpoint. Different model families are preferable for error diversity, but three separate calls to one model are allowed and must be described as repeated-model judgments.

Paid calls require `--allow-network`. Request budgets persist within each output directory. Increasing `--max-requests` resumes a budget-stopped run. Budgets count attempted requests, including retries, not dollars or tokens. Review actual provider prices before execution. Keep separate jobs in separate output directories.

## 5. Run planned multi-search and adaptive retrieval on DEV

```bash
python -m prw run --scenarios data/dev/scenarios.jsonl --system planned_multisearch \
  --snapshot YOUR_REAL_SNAPSHOT --out runs/dev/planned_multisearch \
  --allow-network --max-requests 50
python -m prw run --scenarios data/dev/scenarios.jsonl --system adaptive \
  --snapshot YOUR_REAL_SNAPSHOT --out runs/dev/adaptive \
  --allow-network --max-requests 180
```

These request limits are spending caps, not guaranteed completion estimates. Adaptive uses one planning call and up to one observation call per retrieval operation, at most three operations. Failures/retries can consume additional requests. Configuration and exhausted-budget errors stop rather than producing a falsely successful static fallback labelled adaptive.

## 6. Primary evaluation: combined-bundle sufficiency

First inspect the dry-run request count:

```bash
python -m prw judge-bundles \
  --runs runs/dev/hybrid/runs.jsonl runs/dev/legal_static/runs.jsonl \
         runs/dev/planned_multisearch/runs.jsonl runs/dev/adaptive/runs.jsonl \
  --scenarios data/dev/scenarios.jsonl --requirements data/dev/requirements.jsonl \
  --out judgments/dev/bundles
```

Repeat with `--allow-network --adjudicate --max-requests YOUR_APPROVED_CAP`. Each distinct bundle needs three initial judgments; material disagreements add adjudication requests. Complete bundles can contain complementary passages, so this test avoids declaring two partial but jointly sufficient excerpts insufficient simply because neither alone is complete.

Outputs include raw judgments, consensus/adjudication, a review queue and requirement-coverage records. Aggregation is blocked while material adjudications remain unresolved.

## 7. Optional ranking metrics: open pooled passage judgments

```bash
python -m prw pool \
  --runs runs/dev/hybrid/runs.jsonl runs/dev/legal_static/runs.jsonl \
         runs/dev/planned_multisearch/runs.jsonl runs/dev/adaptive/runs.jsonl \
  --final-only --out pools/dev
python -m prw judge --pool pools/dev/candidate_pool.jsonl \
  --scenarios data/dev/scenarios.jsonl --requirements data/dev/requirements.jsonl \
  --out judgments/dev/passages
```

The first command includes the union of all final outputs. Omit `--final-only` to judge all saved acquired candidates for deeper diagnostics. Inspect `cost_plan.json`, then authorize judging with `--allow-network --adjudicate --max-requests YOUR_APPROVED_CAP`.

```bash
python -m prw evaluate \
  --runs runs/dev/hybrid/runs.jsonl runs/dev/legal_static/runs.jsonl \
         runs/dev/planned_multisearch/runs.jsonl runs/dev/adaptive/runs.jsonl \
  --qrels judgments/dev/passages/qrels_silver.jsonl \
  --requirements data/dev/requirements.jsonl --out results/dev/pointwise
```

These are pooled nDCG/Hit/MRR and **conservative pointwise** coverage. Keep the combined-bundle sufficiency result as the primary coverage measure. Unjudged evaluated outputs cause an error, not grade zero. Newly discovered valid evidence is judged even if absent from the reference-source list.

## 8. Freeze before running any test system

Finish static, controller and prompt development on DEV first. Review candidate test scenarios using a separate evaluator process, not the coding/tuning agent. Confirm reference/source scope; do not discard hard cases because they score badly. The supplied test cases are candidates, not independently expert-validated cases.

```bash
python -m prw freeze --test data/test_sealed/scenarios.jsonl \
  --requirements data/test_sealed/requirements.jsonl \
  --configs configs/retrieval.json configs/models.json \
  --snapshot YOUR_REAL_SNAPSHOT --output research_state/test_freeze.json
```

Record resolved model IDs, settings and external repository commit in `research_state/FINAL_CONFIG.md`. The code freeze covers this package, not arbitrary imported repository code or model-provider updates. Save those separately.

Run each frozen system on `data/test_sealed/scenarios.jsonl` with `--freeze research_state/test_freeze.json` and new `runs/test/SYSTEM` output directories. Pass the same `--freeze research_state/test_freeze.json` to test judging, evaluation and answer commands. Pool and judge only after every compared system has run. Do not alter system policy after seeing test outcomes. Technical bug reruns require a new logged version and justification.

For a deadline-constrained primary comparison, retain `hybrid`, `legal_static`, `planned_multisearch`, and `adaptive`. A failed or inconclusive adaptive result is reportable.

## 9. Generate and judge answers

For each system use the same generator configuration:

```bash
python -m prw answers --runs runs/test/legal_static/runs.jsonl \
  --scenarios data/test_sealed/scenarios.jsonl --freeze research_state/test_freeze.json --out answers/test/legal_static \
  --allow-network --max-requests 25
python -m prw judge-answers --answers answers/test/legal_static/answers.jsonl \
  --scenarios data/test_sealed/scenarios.jsonl \
  --requirements data/test_sealed/requirements.jsonl --freeze research_state/test_freeze.json \
  --references references/independent_test_excerpts.jsonl \
  --out answer_judgments/test/legal_static --allow-network --adjudicate --max-requests 90
```

`independent_test_excerpts.jsonl` is deliberately **not fabricated or supplied**. Populate it from verified official/source excerpts with citation, URL and date using `examples/reference_record.json`. Without it, omit `--references`: legal correctness is then **not scored**. You still obtain groundedness, completeness and citation-support assessments. A cited passage matching the generated answer is not independent proof that the law was correctly stated.

## 10. Summarize, interpret, checkpoint

```bash
python scripts/report_bundles.py --metrics judgments/test/bundles/bundle_metrics.jsonl \
  --raw judgments/test/bundles/bundle_judgments_raw.jsonl --out results/test/bundles
python scripts/plot_results.py --metrics judgments/test/bundles/bundle_metrics.jsonl \
  --out results/test/figures
```

Update `research_state/LAST_CHECKPOINT.md` after each completed stage. Send the result JSONLs, reports and checkpoint back for thesis insertion. Do not replace a finished, defensible thesis chapter with an unexecuted proposed result.
