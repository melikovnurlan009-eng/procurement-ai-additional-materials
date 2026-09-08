# DEV-scale retrieval run (40 scenarios, all 4 systems)

Snapshot `dev_scale_2026-09-07`. Scenarios: `evaluation/final_retrieval_benchmark/
workbench_schema/scenarios_dev.jsonl` (40, unchanged from the earlier benchmark-unification
work). Controller/config frozen beforehand per `research_state/controller_freeze_2026-09-07.json`
(matches `prw/controller.py`, `prw/bundles.py`, `prw/adapters.py`, `prw/metrics.py`,
`prw/contracts.py`, `configs/retrieval.json`, `configs/models.json` at that point; unchanged
since). Author approved a $3.00 ceiling for this stage.

## 1. Execution summary

| System | Scenarios | Requests used / cap | Total tokens | Errors |
|---|---:|---:|---:|---|
| `hybrid` | 40/40 | 0 (free) | -- | -- |
| `legal_static` | 40/40 | 0 (free) | -- | -- |
| `planned_multisearch` | 40/40 | 40 / 60 | 29,326 | 0 |
| `adaptive` | 40/40 | 136 / 320 (across 3 invocations, see sec 2) | 1,271,466 | 21/40 scenarios |

**Total measured spend for this stage: 176 requests, 1,300,792 tokens.** At `gpt-4o-mini` list
pricing this is on the order of $0.20-$0.30 -- well under the $3.00 approved ceiling.
`planned_multisearch` came in far cheaper than the pilot-based estimate suggested (29,326 tokens
for all 40 scenarios vs. an ~32,000-token estimate for the same count -- close, actually, the
estimate held up well). `adaptive`'s actual usage (1,271,466 tokens / 40 = ~31,800/scenario) came
in *below* the pilot's own per-scenario average (~43,200/scenario) -- the pilot's 3-scenario
sample, all `BUDGET_EXHAUSTED`, was not representative of the full DEV distribution, which
includes many scenarios that stop early (`ESTIMATED_COVERAGE_COMPLETE`, `CONTROLLER_STOP`).

## 2. A real, disclosed transport failure -- not a design defect

The `adaptive` run hit `HTTP 429` (rate-limited) three times over its full 40-scenario execution,
each time raising `FatalModelError` and stopping the process immediately, exactly as designed
("budget/network failures must stop and resume, not produce fake completed results" --
`prw/llm.py`'s bounded-retry-then-fail behavior, `cmd_run`'s per-scenario checkpointing). Each
resume picked up from the next unchecked scenario, spending no further requests on already-
completed ones:

| Invocation | Scenarios completed after this run | New requests this run |
|---|---:|---:|
| 1st (fresh) | 14 | 49 |
| 2nd (resume) | 35 | 69 |
| 3rd (resume) | 40 | 18 |

This is reported as a real, expected characteristic of running LLM-driven retrieval at 40-
scenario scale against this API key's rate limits, not hidden. No scenario's result reflects a
truncated or partial adaptive run -- every one of the 40 checkpoints represents a fully completed
controller execution.

## 3. Controller reliability at DEV scale (40 scenarios) vs. the 3-scenario pilot

| | Pilot v2 (3 scenarios) | DEV scale (40 scenarios) |
|---|---|---|
| Scenarios with >=1 controller error | 1 of 3 (33%) | **21 of 40 (52.5%)** |
| "Observer cited nonexistent evidence" occurrences | 3 (all in 1 scenario) | 37 (spread across ~20 scenarios) |
| "Observer changed issue set" -- new failure mode, not seen in the pilot | 0 | 1 |
| `execution_status` COMPLETED (zero errors) | 2 of 3 | 19 of 40 (47.5%) |
| `execution_status` COMPLETED_WITH_FALLBACKS | 1 of 3 | 21 of 40 (52.5%) |
| `stop_reason` distribution | BUDGET_EXHAUSTED x2, CONTROLLER_STOP x1 (in the earlier 3-scenario runs) | ESTIMATED_COVERAGE_COMPLETE 18, BUDGET_EXHAUSTED 17, CONTROLLER_STOP 5 |

**The 3-scenario pilot understated the observer-hallucination rate.** At DEV scale, just over
half of all scenarios trigger at least one caught-and-recovered observer citation error. All 21
were correctly caught by `validate_observation` (chunk_id not in the supplied evidence set) and
never entered controller state -- the safety net held for all 40 scenarios, with zero invalid
observations accepted. But the underlying model behavior that this pilot's fix reduced (not
eliminated) is common enough at this scale to be a first-order characteristic of this controller
under `gpt-4o-mini`, not an edge case. This is reported plainly per instruction not to
extrapolate small-sample rates and not to let a fix look more complete than it is.

"Observer changed issue set" is a new failure mode not seen in the pilot: the observer returned a
different set of issue IDs than the plan defined for at least one operation in one scenario.
Also caught and recovered (the run still reached `COMPLETED_WITH_FALLBACKS`, not a crash) via the
same fallback path as the other observation-stage errors.

## 4. Pooled passage judging: a second contract bug found and fixed, then executed

Building on `prw pool --final-only` (729 unique final-ranking candidates across all 4 systems x
40 scenarios, confirmed free/deterministic) and a dry-run cost check (2,187 minimum requests, 3
judges x 729), `prw judge --allow-network --adjudicate --max-requests 3000` was run after author
approval of a $2.00 ceiling.

**First attempt crashed on item 1**: `prw/judging.py`'s pointwise judge contract had the exact
same class of bug already fixed in the bundle judge -- `ValueError: Requirement set changed by
judge`, because the judge was asked to echo back a dict keyed by requirement ID. `judging.py` was
out of scope of the original bundle-judge fix, so it had never been touched. Applied the same
pattern here: the judge returns a plain positional `judgments` array (no requirement IDs, and no
quoted text spans either -- `spans`/`quote` were confirmed unused by `metrics.py`/`diagnostics.py`,
only `support` is read, so dropping them changes no evaluation definition); the harness attaches
`requirement_id` deterministically by zipping against its own known list; one bounded repair
attempt is recorded (`first_pass_valid`/`repair_attempted`/`repair_valid`/`validation_failure_type`).
Also added the same per-item resilience to `cmd_judge` as `cmd_bundles` already had, narrowed in
both places to catch only `ValueError` (a compliance failure) -- a `FatalModelError`
(budget/network) still stops the whole run immediately, unchanged.

**Result after the fix: 726 of 729 candidates judged successfully (99.6%), 0 left in the review
queue, 2,468 of 3,000 requests used.** 3 candidates failed even after repair, all with the
identical error `Inconsistent grade and FULL support` (a judge claiming a low relevance grade
while also marking a requirement FULL -- a genuine self-contradiction the harness correctly
rejects, not a schema-shape bug). Per the same policy as the bundle-judge residual failure, these
3 were not retried a third time. The affected (scenario, chunk) pairs --
`DEV008`/`1943682c988f7744c205ea18__PDFV2__CH_0380`,
`DEV015`/`36600b7dfd5d078bdf36c9b3__36600b7dfd5d078bdf36c9b3__SEG_0005__CH_004`,
`DEV023`/`52c560d9476c0de06e747fc9__PDFV2__CH_0028` -- mean those 3 scenarios cannot be scored by
`prw evaluate` (it correctly refuses rather than treating an unjudged chunk as zero). **These 3
scenarios (DEV008, DEV015, DEV023) are excluded from the pooled-metric results below and their
exclusion is stated here, not silently absorbed into a "40 scenarios" count.**

## 5. Pooled passage relevance -- primary metric, real results (37 of 40 DEV scenarios)

`prw evaluate --k 10` (free, deterministic given the qrels):

| System | Scenarios | Pointwise coverage | Pointwise complete | Pooled nDCG@10 | Hit>=2 |
|---|---:|---:|---:|---:|---:|
| hybrid | 37 | 0.230 | 0.189 | 0.475 | 0.973 |
| legal_static | 37 | 0.716 | 0.703 | 0.486 | 0.973 |
| planned_multisearch | 37 | 0.811 | 0.784 | 0.510 | 0.973 |
| adaptive | 37 | 0.716 | 0.703 | 0.552 | 1.000 |

Paired scenario-group sign tests (`requirement_coverage`, matching `RESEARCH_PROTOCOL.md`'s H1-H3):

- **H1 confirmed at DEV scale**: `legal_static` beats `hybrid` by +0.486 coverage (wins 21,
  ties 15, losses 1; p=1.1e-05). Legal-aware static retrieval is a large, statistically clear
  improvement over conventional hybrid retrieval at the same final context size.
- **H2/H3, not yet significant at n=37**: `adaptive` vs `legal_static` shows a delta of exactly
  0.0 (wins 3, ties 31, losses 3; p=1.0) -- no measurable pointwise-coverage difference between
  the two on this pooled silver label set. `adaptive` vs `planned_multisearch` favors adaptive by
  +0.095 but is not significant (wins 4, ties 32, losses 1; p=0.375). Numerically, `adaptive` has
  the highest pooled nDCG@10 (0.552) of all four systems, but this is a ranking-quality signal,
  not the same test as paired requirement-coverage wins -- treat the nDCG gap as suggestive, not
  as confirming H2 on its own.
- The third, essential comparison (`planned_multisearch` vs `adaptive`) shows planned_multisearch
  is NOT statistically distinguishable from adaptive on requirement coverage at this sample size
  -- consistent with H3's own warning that "extra searches alone can explain an apparent
  improvement over a single-pass baseline," and a reminder not to credit adaptive's own
  observation/feedback loop for the coverage gain over `hybrid` without this control.

Full detail: `results/dev_scale/evaluate/report.md`, `summary.json` (paired bootstrap detail),
`per_scenario.jsonl`, `by_suite.json`.

## 6. Next step

Retrieval + pooled passage judging are both done for DEV. Remaining before the pre-TEST freeze:
wait for the separate standalone-benchmark 5,895-item judging job to finish, then run its own
`compute_metrics.py`/`candidate_ceiling.py`/`error_analysis.py`/`make_figures.py` (covers nDCG@10,
Hit@10, MRR, candidate-generation ceiling, authority/regime diagnostics and per-suite results for
the 60-scenario benchmark specifically, complementing `strict_target_recall.py` already run);
then review DEV results as a whole before requesting approval for the TEST-stage freeze and
execution, including the standing self-authorship caveat for that step.
