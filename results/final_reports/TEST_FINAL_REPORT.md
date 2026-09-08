# Frozen TEST Execution — Final Report

**Methodology disclosure, stated first and not to be omitted anywhere this report is cited:**
this session authored the 20 TEST scenarios, their requirements, and their corpus-verified gold
evidence earlier in this project, and has read the full text and gold of every TEST scenario. It
therefore does not meet the bar for the independent "separate evaluator process" a genuine
held-out TEST freeze calls for -- it froze the design (`FINAL_FREEZE.json`) and then executed
that same frozen design itself. No TEST outcome was inspected, and no controller/prompt/config
decision was made using any TEST signal, at any point before this freeze and single execution.
That is a real, disclosed limitation on this TEST result's independence, not a technicality, and
must be stated plainly wherever this report's numbers are used, per the author's own instruction.

## 1. Execution (frozen, matched conditions, `--freeze results/final/prw_freeze_record.json`)

All 4 systems (`hybrid`, `legal_static`, `planned_multisearch`, `adaptive`) ran on all 20 TEST
scenarios under identical retrieval budgets, final evidence budget, corpus snapshot, controller
limits, model configuration and judging rubric as the DEV run (`FINAL_FREEZE.json`; freeze
verification -- test/config/code hashes -- passed on every invocation, confirming zero drift
since the freeze).

| System | Scenarios | Requests | Tokens | Fallback rate | Notes |
|---|---:|---:|---:|---:|---|
| hybrid | 20/20 | 0 (free) | -- | -- | -- |
| legal_static | 20/20 | 0 (free) | -- | -- | -- |
| planned_multisearch | 20/20 | 20 | 15,365 | 0/20 (0.0%) | clean, no errors |
| adaptive | 20/20 | 63 (2 invocations) | 604,504 | 9/20 (45.0%) | 1 transport-error stop (`FatalModelError`, network), resumed from checkpoint at scenario 8; 12 total `Observer cited nonexistent evidence` occurrences, all caught and recovered by the harness, none accepted into final state |

adaptive's 45.0% fallback rate is consistent with (slightly below) DEV's 52.5% -- the same
disclosed controller-reliability characteristic, not a new problem introduced at TEST scale.

## 2. Pooled passage judging

390 unique final-ranking candidates (`prw pool --final-only`, 4 systems x 20 scenarios). **387 of
390 judged successfully (99.2%)**, 3 failed even after the one bounded repair attempt, all
`Inconsistent grade and FULL support` -- the identical failure signature seen on DEV, at a
proportionally identical rate (3/390 = 0.77% vs DEV's 3/729 = 0.41%). Per instruction, these are
not retried a third time. **Affected scenarios excluded, named exactly**: `TEST007`
(`5f8342eb3f38e4119244d2f2__PDFV2__CH_0005`), `TEST010`
(`UKPGA_2023_54__NODEV1__CH_00028`), `TEST017`
(`717032ad1090f198aedfcd2a__717032ad1090f198aedfcd2a__SEG_0010__CH_001`). **17 of 20 scenarios
are scorable and reported below.**

## 3. Final TEST metrics (17 scorable scenarios, `prw evaluate --k 10`)

| System | req_coverage | scenario_complete | pooled_nDCG@10 | Hit>=2 |
|---|---:|---:|---:|---:|
| hybrid | 0.147 | 0.059 | 0.521 | 0.941 |
| legal_static | 0.559 | 0.529 | 0.416 | 0.882 |
| planned_multisearch | 0.706 | 0.647 | 0.471 | 1.000 |
| adaptive | **0.735** | **0.706** | **0.551** | 0.941 |

### Paired comparisons (§Phase 5 A-D, scenario-group sign test + bootstrap CI, n=17)

| Comparison | delta (higher - lower) | wins/ties/losses | p | 95% CI | Verdict |
|---|---:|---|---:|---|---|
| **A. legal_static vs hybrid** | +0.412 (legal_static higher) | 9/7/1 | **0.0215** | [0.176, 0.647] | **Significantly improved** |
| **B. planned_multisearch vs legal_static** | +0.147 (planned higher) | 5/10/2 | 0.4531 | [-0.088, 0.382] | Numerically higher but not statistically significant |
| **C. adaptive vs legal_static** | +0.176 (adaptive higher) | 4/13/0 | 0.1250 | [0.029, 0.353]* | Numerically higher but not statistically significant |
| **D. adaptive vs planned_multisearch** | +0.029 (adaptive higher) | 4/11/2 | 0.6875 | [-0.206, 0.235] | No measurable difference |

`*` the point estimate and one-sided portion of this CI are positive, but the sign test itself
(0 losses is unusual with only p=0.125, driven by the small n=17 and 13/17 ties) is not
significant at the conventional 0.05 threshold -- reported as directionally positive but not
confirmed, per instruction 25's exact phrasing rule.

**A is confirmed significant. B, C, D are not.** Do not state B/C/D as improvements; the
correct phrasing for each is used verbatim above.

## 4. Comparison with DEV -- consistent story, one notable shift

- **H1 (legal_static > hybrid) replicates on TEST**: significant on both DEV (p=1.1e-05) and
  TEST (p=0.0215), same direction, smaller/noisier effect at TEST's much smaller n=17 vs DEV's
  n=37 -- exactly the expected pattern, not a contradiction.
- **H2 (adaptive vs legal_static) shifts direction but stays non-significant**: DEV showed an
  exact 0.0 delta (perfect tie, p=1.0); TEST shows a positive but non-significant +0.176
  (p=0.125). This is reported as a genuine difference between the two evaluations, not smoothed
  into one number -- at n=17-37 scenarios, neither result should be treated as the final word on
  H2; both are retained.
- **H3's control (adaptive vs planned_multisearch) again shows no measurable difference** on
  TEST (delta=0.029, p=0.6875), consistent with DEV's non-significant +0.095 (p=0.375) --
  reproduced independently, strengthening this specific null result more than any of the other
  three comparisons.

## 5. TEST019 — independent replication of the DEV003 mechanism

TEST019's gold requirement is, independently, also about the PA2023 s.51 mandatory standstill
period (same underlying provision as the DEV003 case study, different scenario). Exact citations,
top-3, from `runs/test_final/*/runs.jsonl`:

| System | Rank 1 | Rank 2 | Rank 3 |
|---|---|---|---|
| `legal_static` | PA2023 s.50 (adjacent, wrong) | PA2023 s.11 | PA2023 s.26 |
| `planned_multisearch` | **PA2023 s.51 (correct)** | PA2023 s.41 | PA2023 s.50 |
| `adaptive` | **PA2023 s.51 (correct)** | PCR2015 reg 50 | PA2023 s.11 |

`legal_static` lands on the adjacent-but-wrong s.50 and never reaches s.51 in its top-3; both
decomposition systems place the correct s.51 at rank 1. This independently reproduces the DEV003
mechanism finding on a different scenario, at TEST time, without any tuning informed by this
result (it was not observed until this report was written, after the freeze). This strengthens
the case-study finding beyond a single anecdote, though it remains two scenarios out of 57 total
(37 DEV + 20 TEST), not a general proof.

## 6. Claims safe for the thesis from this TEST run

1. H1 (legal-aware static retrieval beats conventional hybrid) is confirmed significant on both
   DEV and TEST, independently.
2. H3's essential control (adaptive vs. its budget-matched non-adaptive equivalent,
   planned_multisearch) shows no significant difference on either DEV or TEST -- the most
   consistently reproduced null result in this project.
3. H2 (adaptive's observation/feedback loop improving on legal_static) is not confirmed on either
   DEV (exact tie) or TEST (positive but not significant) -- treat as an open question, not
   resolved in either direction.
4. The query-decomposition mechanism that recovers PA2023 s.51 in DEV003 independently
   reproduces on TEST019, a different scenario with the same underlying gold provision.
5. adaptive's ~45-53% controller-fallback rate (caught and recovered, never silently accepted) is
   consistent across DEV and TEST and should be reported as a first-order characteristic of this
   controller under `gpt-4o-mini`, not an edge case.
6. **This TEST execution was not run by an independent evaluator.** Any thesis claim drawing on
   these numbers must state that plainly.

## Source files

`runs/test_final/{hybrid,legal_static,planned_multisearch,adaptive}/runs.jsonl`,
`judgments/test_final/pointwise/{qrels_silver.jsonl,judge_failures.json}`,
`results/test_final/evaluate/{summary.json,per_scenario.jsonl}`, `results/final/FINAL_FREEZE.json`.
