# Pointwise retrieval diagnostics

Labels: pooled silver judgments. Scenario sampling intervals do not capture shared judge error.

| System | Scenarios | Pointwise coverage | Pointwise complete | Pooled nDCG | Hit >=2 |
|---|---:|---:|---:|---:|---:|
| hybrid | 37 | 0.230 | 0.189 | 0.475 | 0.973 |
| legal_static | 37 | 0.716 | 0.703 | 0.486 | 0.973 |
| planned_multisearch | 37 | 0.811 | 0.784 | 0.510 | 0.973 |
| adaptive | 37 | 0.716 | 0.703 | 0.552 | 1.000 |

## Interpretation limits
No system is declared superior automatically. Inspect paired differences, the budget-matched multi-search control, unknown applicability, corpus support, and judge sensitivity.
