# Results and thesis reporting

## One main table

System | scenarios completed | bundle requirement coverage | scenario complete | pooled nDCG (optional) | mean operations | request/token use | fallback/error cases

Use the same scenarios and final evidence budgets. Never hide failed or unjudged scenarios by averaging only convenient cases. Report missing values and denominator changes.

For the main adaptive comparison include both static legal and planned multi-search controls. Separate descriptive role-aware improvements from isolated causal attribution to graph, priors or feedback.

## Recommended figures

1. Exact source-to-chunk-to-edge example, using real source text and stored references from the user's repository.
2. Existing engine under a bounded planner/observer/controller loop.
3. Source-guided scenario authoring, private requirements and blind silver judging.
4. Per-scenario bundle coverage for hybrid, legal static, planned multi-search and adaptive.
5. Paired coverage differences with scenario-group confidence intervals.
6. Actual trace: observed seed, search/graph action, new candidate, final evidence membership.
7. Passage relevance versus score only if the required raw candidate data and labels were actually generated.

The scripts create result charts only from real result JSONLs supplied to them. No placeholder research bars are shipped.

## Appropriate claim templates

'On the prespecified test scenarios, the adaptive policy changed mean bundle requirement coverage by [observed delta] relative to [named comparison], using [operation counts]. Judgments were produced by three blinded LLM invocations and [adjudication procedure]. They are silver labels, not expert legal ground truth.'

'The planned multi-search control [did/did not] explain the observed gain; this comparison estimates the value of evidence feedback beyond additional planned searches under the tested budgets.'

'Pooled nDCG reflects judgments on the union of outputs from all compared methods. It does not establish exhaustive corpus recall.'

'Legal correctness was not scored because independent reference excerpts were unavailable; reported outcomes concern evidence support, completeness and source use.'

## Claims to avoid

- The system generalises to all UK procurement scenarios.
- Three judges agreed, therefore the legal label is correct.
- A valid source ID proves a legal claim is true.
- The controller's FULL flag is the benchmark's ground truth.
- Any rise in final coverage proves an individual graph decision was causally correct.
- The adaptive policy is better simply because it returned more passages or had more searches.
- Missing relevant passages are irrelevant because they were absent from an initial gold list.
- A source-only alias is a legally equivalent term.
- The existing benchmark or corpus was repaired merely by packaging these tools.
- Unit-test outcomes are empirical procurement research findings.

## Thesis insertion status

The package is an implemented research method. Before a real experiment, write its method in proposal/implementation terms and identify what has not been measured. After execution, cite actual run paths, source snapshots, frozen settings, judge models, coverage denominators and confidence intervals. Preserve historical results as historical, not as results of this new system.
