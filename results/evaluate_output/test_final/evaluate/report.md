# Pointwise retrieval diagnostics

Labels: pooled silver judgments. Scenario sampling intervals do not capture shared judge error.

| System | Scenarios | Pointwise coverage | Pointwise complete | Pooled nDCG | Hit >=2 |
|---|---:|---:|---:|---:|---:|
| hybrid | 17 | 0.147 | 0.059 | 0.521 | 0.941 |
| legal_static | 17 | 0.559 | 0.529 | 0.416 | 0.882 |
| planned_multisearch | 17 | 0.706 | 0.647 | 0.471 | 1.000 |
| adaptive | 17 | 0.735 | 0.706 | 0.551 | 0.941 |

## Interpretation limits
No system is declared superior automatically. Inspect paired differences, the budget-matched multi-search control, unknown applicability, corpus support, and judge sensitivity.
