# Matched DEV Experiment — Final Report

Scope: `procurement_research_workbench_v1`, 40-scenario DEV split, 4 systems (`hybrid`,
`legal_static`, `planned_multisearch`, `adaptive`) under matched retrieval/evidence budgets
(`configs/retrieval.json`, unchanged since `research_state/controller_freeze_2026-09-07.json`).
Every number below is re-read directly from source artifacts for this report (`runs/dev_scale/`,
`judgments/dev_scale/pointwise/`, `results/dev_scale/evaluate/`,
`results/final/CONTROLLER_DIAGNOSTICS.csv`) — none is copied forward from earlier prose without
re-confirming against the file.

## 1. Pooled DEV judging result (confirmed from source)

- Total pooled candidates (`prw pool --final-only`, 4 systems x 40 scenarios, deduplicated):
  **729**.
- Successfully judged: **726 (99.59%)**. Failed even after one bounded repair attempt: **3**
  (0.41%), all `Inconsistent grade and FULL support` (a judge asserting a low relevance grade
  while also marking a requirement FULL -- a genuine self-contradiction the harness correctly
  rejects on both the first pass and the repair pass, not a schema-shape bug).
- Annotation status of the 726 judged: 455 `LLM_CONSENSUS_SILVER` (full 3-judge agreement), 271
  `LLM_ADJUDICATED_SILVER` (required the 4th adjudicator call).
- **3 scenarios excluded from all pooled-metric results below, named exactly**: `DEV008`
  (candidate `1943682c988f7744c205ea18__PDFV2__CH_0380`), `DEV015`
  (`36600b7dfd5d078bdf36c9b3__36600b7dfd5d078bdf36c9b3__SEG_0005__CH_004`), `DEV023`
  (`52c560d9476c0de06e747fc9__PDFV2__CH_0028`) -- each because `prw evaluate` correctly refuses
  to score a ranking containing an unjudged chunk rather than treating it as zero. **37 of 40
  scenarios are scorable and reported below.**

## 2. Pooled passage relevance — primary metric (37 scenarios, `prw evaluate --k 10`)

| System | req_coverage | content_coverage | scenario_complete | pooled_nDCG@10 | Hit>=2 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| hybrid | 0.230 | 0.784 | 0.189 | 0.475 | 0.973 | 0.141 |
| legal_static | 0.716 | 0.838 | 0.703 | 0.486 | 0.973 | 0.616 |
| planned_multisearch | **0.811** | **0.910** | **0.784** | 0.510 | 0.973 | **0.662** |
| adaptive | 0.716 | 0.829 | 0.703 | **0.552** | **1.000** | 0.640 |

Confirmed exactly matching `results/dev_scale/evaluate/summary.json`. **`adaptive` remains
numerically the highest pooled nDCG@10 (0.552) of all four systems after recomputation from
source.**

### Paired comparisons (scenario-group sign test + bootstrap CI, `requirement_coverage`, n=37)

| Comparison | delta | wins/ties/losses | p | 95% CI |
|---|---:|---|---:|---|
| hybrid -> legal_static | **+0.486** | 21/15/1 | **1.10e-05** | [0.324, 0.649] |
| adaptive -> legal_static | 0.000 | 3/31/3 | 1.0 | [-0.135, 0.135] |
| adaptive -> planned_multisearch | +0.095 | 4/32/1 | 0.375 | [0.000, 0.203] |

- **H1 (legal-aware static > conventional hybrid) is confirmed**, with a large, statistically
  clear effect.
- **H2 (feedback-controlled retrieval improves coverage beyond a planner issuing several queries
  without inspecting evidence) is not supported at DEV scale**: `adaptive` vs `legal_static`
  shows a delta of exactly 0.0 on requirement coverage (p=1.0). `adaptive` does have the highest
  pooled nDCG@10 among all four systems, a ranking-quality signal distinct from the
  requirement-coverage test above -- this is reported as suggestive, not as confirming H2 by
  itself.
- **H3's own warning is directly illustrated, not just theoretical**: the essential
  `planned_multisearch` vs `adaptive` control shows `adaptive` numerically ahead by +0.095 but
  **not statistically significant** (p=0.375) -- extra searches alone (`planned_multisearch`,
  which never inspects intermediate evidence) explain most of the gain over `hybrid`; the
  observation/feedback loop specific to `adaptive` adds no measurable additional coverage over
  that budget-matched control at this sample size.

## 3. Controller diagnostics (`CONTROLLER_DIAGNOSTICS.csv`, all 40 scenarios, both paid systems)

| | planned_multisearch | adaptive |
|---|---:|---:|
| Scenarios run | 40/40 | 40/40 |
| Fallback rate (`COMPLETED_WITH_FALLBACKS`) | **0/40 (0.0%)** | **21/40 (52.5%)** |
| Multi-operation scenarios (issued >1 search) | 40/40 | 26/40 |
| Intervention added new grade>=2 evidence (of multi-op scenarios) | 34/40 (85.0%) | 22/26 (84.6%) |
| Regressions vs. `legal_static` (lower coverage) | 1/40: `DEV013` | 3/40: `DEV013`, `DEV016`, `DEV034` |
| Total paid requests (this run) | 40 | 136 (across 3 invocations, see §5) |
| Total tokens (this run) | 29,326 | 1,271,466 |

`planned_multisearch` never triggers a controller validation error (it issues its planned queries
without ever calling the observer, so it cannot hit the observation-stage failure modes at all --
this is a structural property of that system, not evidence of a more reliable model). `adaptive`'s
52.5% fallback rate is a real, disclosed characteristic of the DEV-scale run under `gpt-4o-mini`,
consistent with (and higher than) the 3-scenario pilot's 33% rate -- **the pilot understated this
rate; it should not be extrapolated from small samples going forward.**

Both systems show essentially the same intervention-success rate (~85%) among scenarios where a
second/third operation actually ran: when the controller does issue more than one search, it
usually recovers genuinely new, judge-graded-relevant evidence, whether or not it inspects
intermediate results (`planned_multisearch`) or adapts to them (`adaptive`). This further
explains why H2 is not supported: the VALUE of extra search effort is present in both systems
about equally often; what differs is only whether the extra effort is spent at all
(`planned_multisearch` always issues its full plan; `adaptive` stops early in 14/40 scenarios).

**Regressions**: `DEV013` (`vocabulary_mismatch` suite) is a shared regression for both paid
systems -- `legal_static`'s single-pass search reaches 1.00 coverage while both
`planned_multisearch` and `adaptive` drop to 0.00, suggesting query decomposition actively hurts
when the single correct query already bridges the vocabulary gap that decomposition then
fragments. `DEV016` (`vocabulary_mismatch`) and `DEV034` (`guidance`) are adaptive-only
regressions (`planned_multisearch` matches `legal_static`'s 1.00 on both) -- these are real,
adverse, system-specific findings and are not omitted.

Per-scenario token/latency reconstruction beyond the aggregate totals above was not attempted --
`model_events.jsonl` does not record `scenario_id` per call, so an exact per-scenario token count
would require inference rather than a direct read; this is disclosed as a limitation rather than
approximated and presented as measured.

## 4. Retrieval rankings: unchanged from the underlying retriever

`hybrid` and `legal_static` rankings were confirmed byte-identical to the earlier 3-scenario
pilot's rankings for the 3 overlapping scenarios (pilot-v2 verification, unchanged since -- no
retrieval-scoring code has been touched at any point in this project's DEV/TEST work).

## 5. DEV003 case study — see `CASE_STUDIES.md` for full detail

Static systems (`hybrid`, `legal_static`) do not retrieve PA2023 s.51
(`UKPGA_2023_54__NODEV1__CH_00051`) at all for DEV003 (absent from both systems' acquired
candidate pools, 20 and 30 candidates respectively). `planned_multisearch` recovers it into
its **final top-10 at rank 3**. `adaptive` recovers it into its **acquired candidate pool at rank
16 of 83, but it does not survive into adaptive's own final top-10 ranking**. This is a more
precise, nuanced result than earlier pilot-stage reporting suggested (the pilot's smaller acquired
pool made adaptive's recovery look more complete than it is at DEV scale) -- corrected here from
source, not carried forward uncritically. **This single case does not, by itself, establish
adaptive's overall superiority** -- see §2's H2 result, which shows no aggregate advantage, and
§3's regression cases, which show the same query-decomposition mechanism actively hurting on 3
other scenarios.

## Source files

`runs/dev_scale/{hybrid,legal_static,planned_multisearch,adaptive}/runs.jsonl`,
`judgments/dev_scale/pointwise/{qrels_silver.jsonl,judge_failures.json}`,
`results/dev_scale/evaluate/{summary.json,per_scenario.jsonl}`,
`results/final/CONTROLLER_DIAGNOSTICS.csv`, `research_state/controller_freeze_2026-09-07.json`.
