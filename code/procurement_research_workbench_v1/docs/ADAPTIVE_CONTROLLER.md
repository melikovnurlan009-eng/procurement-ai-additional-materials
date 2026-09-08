# Adaptive retrieval controller

## Executable state machine

```
User scenario and fixed history
        |
        v
Plan 1-4 runtime information needs and 1-3 candidate queries
        |
        v
Retrieve original question with the frozen legal engine
        |
        v
Collect exact source excerpts and deterministic diagnostics
        |
        v
Assess runtime issues: FULL / PARTIAL / MISSING / CONFLICT
        |
        +-- sufficient or budget limit --> assemble final evidence
        |
        +-- SEARCH targeted query, graph on/off
        |
        +-- EXPAND observed canonical anchor, if backend supports it
        |
        +-- STOP with unresolved issues or clarification questions
```

Every search or targeted expansion consumes one of at most three total retrieval operations. A decomposed plan does not get three additional searches per subquery. Planning and observation are model calls counted separately in spending logs. The observer never sees evaluator requirements or silver labels.

## What makes this more than a query-rewrite prompt

The policy maintains accumulated evidence, observed legal identities, runtime issue support, repeated-action history, remaining operation budget, missing facts and actual source quotes. It can search a missing subproblem rather than paraphrase the whole question. Targeted expansion is allowed only from an observed anchor and implemented capability. The final evidence selector gives priority to newly supported runtime issues without accessing the evaluator's answer key.

The planner cannot certify legal permission. The observer cannot declare FULL solely from a heading or a high similarity score. It must quote an actual retrieved passage; a binding-required runtime issue is downgraded when its support is guidance-only. Source text is treated as untrusted input, not a place from which to accept tool instructions.

These controls reduce failure opportunities but do not prove the model interpreted evidence correctly. Exact quotation proves provenance, not entailment. Rewrite validation checks basic statutory locator introduction and does not implement a complete UK citation grammar or fact-verification system.

## Diagnostic inputs actually implemented

New unique chunk count, lane counts, observed canonical IDs, previous retrieved text and remaining operations are supplied. Raw cosine/BM25 scores are not converted into generic confidence thresholds. Score scales differ by query/channel; a low score does not by itself establish semantic failure. More elaborate calibrated diagnostics are future work unless separately implemented and evaluated.

## Targeted graph integration

Global graph search uses the existing retriever. A separate targeted operation is advertised only when the backend implements it. `prw.graph.GraphSidecar` supplies explicit one-hop expansion using real edge records, a supplied live legal-node-to-chunk mapping and a source-text loader. It does not guess mappings, generate new legal edges, or infer legal effects.

The sidecar supports the two substantive citation/reference relations. Traversal direction is logged even when incoming and outgoing references are inspected. Missing mappings are recorded, not silently translated to an unrelated ancestor. It is optional; the package does not claim the user's stale graph exports have been repaired.

## Stopping and failures

Stop on estimated coverage complete, explicit STOP, repeated action, two operations with no new evidence, or three total retrieval operations. Budget exhaustion is not evidence that the corpus lacks an answer. Missing facts produce clarification questions or conditional analysis, not invented answers.

Malformed model plans/observations can use a bounded, logged fallback. Such runs are marked COMPLETED_WITH_FALLBACKS. Missing credentials, inaccessible model endpoints and exhausted request budgets stop the job and retain checkpoints. They must not silently yield a static run represented as successful adaptive retrieval.

## Fair controls

`planned_multisearch` uses the same planner and the same maximum search count but no intermediate evidence feedback. It is a crucial control for attributing gains to feedback rather than simply asking more queries. All systems receive the same final total evidence budget. The controller is not said to have exhausted conventional optimization: it is compared with the strongest configuration actually tested on DEV.

## Assessing controller behaviour

Trace an action from request to acquired evidence to final selected bundle. A reached graph node that disappears before final selection is not a successful final retrieval. Measure before/after coverage using independent silver judgments, not runtime estimates.

An observed action delta is descriptive, not causal: the agent selects difficult states non-randomly. To claim that choosing graph was better than another action at the same state requires a counterfactual replay from a frozen state under matched budgets. This release logs the states but does not claim that counterfactual experiment has been run.
