# Finalization changelog

Referenced by `code/evaluation/final_retrieval_benchmark/candidate_ceiling_CORRECTED.py` and
`make_candidate_ceiling_figure_CORRECTED.py`. Records fixes made during a final-package audit
(2026-09-07/08) that changed a reported classification, kept alongside the original for the
audit trail rather than silently overwriting it.

## Candidate-generation-vs-ranking classification bug (2026-09-07)

`candidate_ceiling.py`'s original if/elif classification checked `not in_union50`
(candidate-generation failure) *before* checking `in_final10` (success). `in_union50` is
computed only from the lexical-only and dense-only candidate lists; `in_final10` is read from
config F (`config_F_two_lane.jsonl`), which also retrieves via the graph-expansion channel. Any
scenario where the gold chunk reached the final top-10 purely through graph expansion --
present in `final10` but absent from the narrower lexical+dense union -- was therefore
misclassified as `CANDIDATE_GENERATION_PROBLEM` instead of a genuine success.

**Fix** (`candidate_ceiling_CORRECTED.py`): check success first --
1. if gold is present in the final returned top-k -> success
2. elif gold is absent from the union candidate pool (lexical + dense) -> candidate-generation failure
3. else -> ranking/fusion failure

The "final top-10" definition itself is unchanged from the original script, and matches the
definition `compute_metrics.py` already uses for config F's own reported nDCG/coverage numbers
-- so the fix only corrects the classification logic, it does not change any other reported
number.

| | OK_FOUND_IN_FINAL_TOP10 | CANDIDATE_GENERATION_PROBLEM | RANKING_PROBLEM |
|---|---:|---:|---:|
| Original (`candidate_ceiling.py`, buggy) | 15 | 40 | 5 |
| Corrected (`candidate_ceiling_CORRECTED.py`) | 24 | 31 | 5 |

Both scripts and both sets of output (`metrics/candidate_ceiling{,_CORRECTED}.jsonl` and
`_summary.json`, `figures/candidate_ceiling{,_CORRECTED}.png`) are kept in the bundle. The
submitted thesis text reports the original numbers: "Forty of the 60 scenarios (66.7%) are
candidate-generation failures... [45] that fail outright (40 candidate-generation plus 5 ranking
failures)" -- i.e. 15 OK / 40 CANDIDATE_GENERATION_PROBLEM / 5 RANKING_PROBLEM, matching
`candidate_ceiling.py` (without `_CORRECTED`), not the reclassified 24/31/5.

See also `provenance/missing_artifacts.md` item 7 for a separate, still-unfixed data-quality
issue in this same analysis's gold-evidence input (`resolve_gold_targets.py`'s citation
resolution bug) -- unrelated to the classification-order bug fixed here.
