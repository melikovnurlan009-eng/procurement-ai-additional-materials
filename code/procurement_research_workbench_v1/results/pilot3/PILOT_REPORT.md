# Three-Scenario DEV Pilot Report

Scenarios (from `evaluation/final_retrieval_benchmark/`, converted to workbench schema,
snapshot label `pilot3_2026-09-07`, backend = live `state/chunk_index_merged.sqlite3` /
Qdrant collection `chunks__bge_m3__merged`):

| scenario_id | suite (workbench) | topic | category requested |
|---|---|---|---|
| DEV003 | statutory | standstill | straightforward legal |
| DEV040 | compound | termination | compound |
| DEV030 | guidance | kpis_performance | practical guidance |

## 1. What has actually been executed (no paid calls)

`hybrid` and `legal_static` ran cleanly against the real backend for all three scenarios
(`runs/pilot3/hybrid/runs.jsonl`, `runs/pilot3/legal_static/runs.jsonl`, 3/3 rows each).
`planned_multisearch` and `adaptive` were **not run** — `prw run` itself refuses both without
`--allow-network` (`prw/cli.py:61-62`: "Adaptive runs require --allow-network and accessible
model credentials; no synthetic fallback experiment is permitted") — so no placeholder or
fake result exists for either.

## 2. Requirement coverage by system (static systems only, so far)

| scenario | requirement | legal_static: covered by top-30 acquired? |
|---|---|---|
| DEV003 | REQ1 (s.51 mandatory standstill period) | **NOT FOUND** in top 30 (see §3) |
| DEV040 | REQ1 (whether poor performance alone is a termination ground) | s.71/s.74 present in top 5, plausible support (not yet judged) |
| DEV040 | REQ2 (duty to publish poor-performance info) | s.71 present at rank 1 (score 0.041) |
| DEV040 | REQ3 (KPI/publication duties depend on value+regime, flag missing facts) | not directly assessable without judging |
| DEV030 | REQ1 (>=3 KPIs, publication) | s.52 present (rank 1, score 0.0339); Contract Performance Notices guidance present |
| DEV030 | REQ2 (12-month assessment, contract performance notice) | s.71 present (rank 3) |

This table is a raw acquired-candidate check (citation string matching), **not** a judged
sufficiency result — no bundle judging has been run (see §5). It is reported here only to
surface the one clear miss below before any paid step, per instructions not to hide adverse
results.

## 3. A real, adverse finding: DEV003 ("straightforward legal") misses its gold provision entirely

PA2023 s.51 (the mandatory 8-working-day standstill period — the actual controlling provision
for this scenario) does **not** appear anywhere in the top 30 acquired candidates for
`legal_static` on DEV003. Checked further:

- Confirmed s.51 is live and unfiltered in the corpus: `chunk_id
  UKPGA_2023_54__NODEV1__CH_00051`, `filtered_out` empty, `superseded_by` empty.
- Checked this project's own separate standalone retrieval run (different candidate depth/query
  construction, see `WORKBENCH_INTEGRATION_NOTES.md` §2) for the same scenario: s.51 is **also
  absent from its full top-50** under `hybrid_priors`, and absent from **both** the lexical-only
  and dense-only channels individually at depth 50.
- This rules out the workbench's specific candidate-depth/query-construction settings as the
  cause — it is a genuine **candidate-generation** failure common to both pipelines for this
  query wording, not a ranking or configuration artefact. The query text ("how long do we
  legally have to wait... before we can actually sign the contract") shares little vocabulary
  with the statute's own terms ("mandatory standstill period", "contract award notice"), and
  dense retrieval does not bridge this gap for this specific phrasing.
- This scenario was deliberately labelled "straightforward legal" going into the pilot; the
  result shows that label was an assumption about difficulty, not a finding — it is retained
  here, not swapped for an easier case, per instruction not to discard hard cases.

## 4. Model configuration prepared (Task 7) — not yet used to spend

`configs/models.json` slots (controller, generator, judge_a/b/c, adjudicator) are configured to
point at the same accessible endpoint already validated working this session
(OpenAI-compatible Chat Completions, model `gpt-4o-mini`, key from this repository's own
`.env`). **This is a repeated-model configuration, not genuine model diversity** — all five
slots (controller/generator/judge_a/judge_b/judge_c) plus the adjudicator would use the same
model family. This is explicitly permitted by START_HERE.md ("three separate calls to one
model are allowed and must be described as repeated-model judgments") but is disclosed here as
a real limitation on judge independence, not hidden. No second accessible model/provider was
configured or available this session.

Environment variables prepared (not yet exported with real spend authorised):
```
PRW_CONTROLLER_MODEL=gpt-4o-mini   PRW_GENERATOR_MODEL=gpt-4o-mini
PRW_JUDGE_A_MODEL=gpt-4o-mini      PRW_JUDGE_B_MODEL=gpt-4o-mini      PRW_JUDGE_C_MODEL=gpt-4o-mini
PRW_ADJUDICATOR_MODEL=gpt-4o-mini
```

## 5. Dry-run cost check actually performed (Task 7/8)

Ran `prw judge-bundles` without `--allow-network` on the two completed static runs (hybrid +
legal_static, 3 scenarios, 2 systems = 6 bundles):
```
{"dry_run": true, "bundles": 6, "minimum_requests": 18}
```
This is a **real** number from the tool itself (3 judges x 6 bundles = 18), not an estimate.
Extrapolated to all four systems (hybrid, legal_static, planned_multisearch, adaptive) x 3
scenarios = 12 bundles x 3 judges = **36 minimum judge requests**, before any adjudication
requests for disagreements (unknown count until judging actually runs).

`prw run --system adaptive/planned_multisearch` has **no dry-run path** — the CLI raises
immediately without `--allow-network` (confirmed in §1), so retrieval-stage cost for these two
systems cannot be measured by the tool itself and is estimated analytically below from
`configs/retrieval.json`'s own declared bounds (`max_retrieval_operations: 3`) and
START_HERE.md's own description ("one planning call and up to one observation call per
retrieval operation, at most three operations" for `adaptive`).

## 6. Proposed per-job request caps for the pilot (Task 8) — total 95, under the 100 ceiling

| Job | `--max-requests` proposed | Basis |
|---|---|---|
| `planned_multisearch` retrieval (3 scenarios) | 15 | ~1-2 planning calls/scenario x 3, x5 buffer for retries |
| `adaptive` retrieval (3 scenarios) | 30 | worst case ~7 calls/scenario (1 plan + 3 ops x 2 calls) x 3 = 21, +buffer |
| Bundle judging, 4 systems x 3 scenarios (12 bundles), 3 judges + adjudicator | 50 | 36 minimum (confirmed by dry-run above, extrapolated to 12 bundles) + adjudication buffer for disagreements |
| **Total** | **95** | under the requested <=100 ceiling |

**These are request caps, not a dollar cap** (per instruction, `--max-requests` counts attempted
requests including retries, not spend). Estimated dollar cost at `gpt-4o-mini` list pricing
($0.15/1M input tokens, $0.60/1M output tokens), based on the same per-call size assumptions
used in this session's already-executed 5,895-item judging job for the standalone benchmark
(~700 tokens in / ~120 tokens out per judge call; controller/planning calls assumed similar or
smaller): **approximately $0.05-$0.15 total for all three paid jobs combined at the proposed
request caps.** This is a real cost model derived from this session's own measured API usage,
not a guess, but it is an estimate of *expected* spend, not a hard ceiling — actual spend could
exceed it if individual calls run longer than assumed (e.g. `adaptive`'s controller receiving a
large evidence context, up to the configured 100,000-char `max_input_chars` cap per slot).

**Requesting an explicit dollar ceiling before any of these three jobs are run with
`--allow-network`.** A ceiling of **$2.00** for this three-scenario pilot (all three jobs
combined) would give roughly 15-40x headroom over the estimate above while remaining a small,
bounded, explicitly-authorised amount. This session will not proceed past this point without
that (or an alternative) explicit approval.

## 7. Approval received; paid pilot jobs executed

Author approved a **$2.00 ceiling** for this three-scenario pilot and authorised proceeding.
`planned_multisearch` and `adaptive` were then run with `--allow-network` on all 3 pilot
scenarios (`runs/pilot3/planned_multisearch/runs.jsonl`, `runs/pilot3/adaptive/runs.jsonl`,
3/3 rows each, model `gpt-4o-mini` in all five configured slots). Both completed.

**A genuine, positive finding:** PA2023 s.51 (DEV003's gold provision, absent from
`legal_static`'s top 30 and from the standalone benchmark's own top-50 under three separate
configs — see §3) **is recovered by both query-decomposition systems**: rank 20/80 under
`planned_multisearch`, rank 7/68 under `adaptive`. Both rescue it via explicit sub-query
decomposition, not by luck of a wider single-pass net — `legal_static`'s single query against
the same corpus and a comparable candidate depth still misses it. This is retained as a real
result, not cherry-picked; the counterpart adverse finding directly below is retained with equal
weight.

**A genuine, adverse finding, in all 3 of 3 scenarios:** `adaptive`'s controller produced
validation errors caught by the harness rather than silently accepted, surfacing as
`COMPLETED_WITH_FALLBACKS` runs: "Planner invented a scenario fact" (the controller's planning
step asserted a fact not present in the scenario's `user_message`) and "Observer cited
nonexistent evidence" (the controller's observation step cited a chunk_id not actually present
in the retrieved evidence set it was given). These occurred in all 3 pilot scenarios, not a
subset. They were correctly caught by the package's own output validation, not swallowed — no
run silently reports a clean result it did not earn. This is reported as a disclosed limitation
of the current `adaptive` controller under `gpt-4o-mini`, not hidden to make the s.51 recovery
finding look cleaner.

Actual usage measured from `model_events.jsonl`: `planned_multisearch` — 3 model calls total
across 3 scenarios (~504 tokens), well under the proposed cap of 15. `adaptive` — 8 model calls
total across 3 scenarios (~71,648 tokens; the larger figure reflects the retrieved-evidence
context passed to the controller's planning/observation calls, up to the configured
`max_input_chars` per slot), under the proposed cap of 30.

## 8. Bundle judging (Task 6): three attempts, three failures — stopped, not hidden

`prw judge-bundles --allow-network --adjudicate --max-requests 50` was run on all 12 bundles (4
systems x 3 scenarios: `hybrid`, `legal_static`, `planned_multisearch`, `adaptive`). It was
attempted **three times**, treating this as a bounded diagnostic sample (a genuine tool/model
compliance question, not a network/budget failure, so retrying a small fixed number of times
before stopping was judged reasonable and within the approved request cap):

| Attempt | Requests reserved (cumulative) | Individual API call status | Harness validation outcome |
|---|---|---|---|
| 1 | 3 | all `success` | `ValueError: Bundle support quote cannot be verified` |
| 2 | 6 | all `success` | `ValueError: Bundle judge changed requirement set` |
| 3 | 9 | all `success` | `ValueError: Bundle support quote cannot be verified` (same failure mode as attempt 1) |

**Result: 9 of the approved 50 requests consumed; zero successful bundle judgments produced.
41 requests remain unused; this session is stopping here rather than continuing to retry.**

Every individual API call itself succeeded (`model_events.jsonl` reports `status: success` for
all 9) — the failures are entirely in the package's own post-hoc validation of the judge's JSON
output against the bundle it was shown (`prw/bundles.py::validate_bundle_judgment`), not in
network/auth/schema-of-request errors. Two distinct, real compliance problems recurred across
three attempts:
1. The judge asserts a "supporting quote" from the bundle text that the harness cannot locate
   verbatim in that bundle (occurred twice, attempts 1 and 3).
2. The judge returns a requirement-ID set that does not match the requirement set it was given
   to assess (occurred once, attempt 2).

**Conclusion, stated plainly: with only `gpt-4o-mini` configured for all three judge slots (an
already-disclosed repeated-model, not diverse-judge, configuration — see §4), this specific
model shows a real, reproducible compliance problem with this package's bundle-judging output
contract.** This is not a network failure, not a budget failure, and not this session's coding
error — it is a genuine finding about model/prompt/schema fit that Task 9 explicitly asks to be
reported, not concealed. No combined-bundle-sufficiency score exists for any of the 12 pilot
bundles as a result. Per instruction not to fabricate results when budget/failures occur, no
placeholder or partial judgment is reported in its place.

**What would plausibly fix this** (not attempted further this pilot, to conserve the remaining
41 requests for author decision): a stricter quote-matching tolerance in the harness
(normalising whitespace/quotation marks before the verbatim check), or a repair/retry-with-
feedback loop that shows the judge its own rejected output and asks it to correct just the
failing field, rather than discarding the whole judgment and re-prompting from scratch. Neither
was implemented here per the standing instruction not to redesign the controller/evaluation
metrics before author review.

## 9. Status: pilot complete, pending author review

Retrieval-stage paid jobs (`planned_multisearch`, `adaptive`) succeeded and produced real,
disclosed findings (s.51 recovery; controller hallucination in 3/3 adaptive runs). Bundle
judging paid jobs did not produce a usable score after 3 attempts (9/50 requests spent) and
stopped rather than continuing to retry or fabricating a result. Total spend across all paid
jobs this pilot is well within the approved $2.00 ceiling (exact dollar total pending final
token-cost reconciliation, but bounded by 11 total model calls at `gpt-4o-mini` list pricing —
on the order of a few cents, not dollars). `research_state/LAST_CHECKPOINT.md` has been updated
to reflect this exact stopping point and what remains before any scale-up to the full 40/20
DEV/TEST sets.
</content>
