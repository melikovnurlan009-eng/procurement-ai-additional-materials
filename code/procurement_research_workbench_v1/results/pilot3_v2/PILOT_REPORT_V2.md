# Three-Scenario DEV Pilot Report — v2 (harness/controller-contract repair)

`v2` is a harness/controller-contract repair following the failed v1 pilot
(`results/pilot3/PILOT_REPORT.md`, `research_state/LAST_CHECKPOINT.md`), not a new experiment.
v1's outputs are untouched (`runs/pilot3/`, `judgments/pilot3/bundles/`). Same 3 DEV scenarios
(DEV003 straightforward legal/standstill, DEV040 compound/termination, DEV030 practical
guidance/KPIs), same 4 systems (hybrid, legal_static, planned_multisearch, adaptive), same
scenario/requirement data files (`data/pilot3/scenarios.jsonl`, `requirements.jsonl`) — no
scenario selection was retuned.

**What changed and why (the two reproducible v1 failures, fixed narrowly):**
1. **Bundle judge contract** (`prw/bundles.py`): the judge no longer generates or reproduces
   supporting quotations, and no longer emits its own requirement-ID set. It returns a plain,
   positional `{"judgments":[...]}` array (one object per requirement, harness order); the
   harness attaches `requirement_id` deterministically by zipping that array against its own
   known requirement list. Validation now only checks: every `supporting_chunk_id` exists in the
   supplied bundle; the array is exactly the right length (so an unknown/changed requirement set
   is structurally impossible, not just detected); `SATISFIED`/`PARTIAL` require at least one
   supporting chunk id, `NOT_SATISFIED` may have none. One field beyond the five specified was
   added back — `applicability` — see the deviation note in §6.
2. **Controller state safety** (`prw/controller.py`): scenario facts are now segmented
   deterministically by the harness (`segment_facts`, sentence-splitting, no model involved) and
   given immutable IDs (`F1`, `F2`, ...) *before* the planner runs. The planner references
   `fact_ids` from this fixed list instead of reproducing scenario text verbatim — it can no
   longer "invent a fact" because it never generates fact text at all, only points at IDs the
   harness already extracted. The observer's evidence citations are now bare `chunk_id` strings
   (no quote) validated by simple set-membership against the actually-retrieved evidence, instead
   of a verbatim-substring quote check.
3. **Repair loop**: on an invalid judge response, at most one repair request is made, stating the
   exact validation failure and including the previous structured output, asking only for
   corrected JSON. `first_pass_valid` / `repair_attempted` / `repair_valid` /
   `validation_failure_type` are recorded per judge call.
4. **Harness resilience** (`prw/cli.py::cmd_bundles`, one addition beyond the literal 7-point
   spec, narrowly justified): a bundle that still fails after its one repair attempt is now
   logged and skipped, not allowed to abort all 12 bundles the way a single v1 failure did. This
   was necessary to actually measure "how many of 12 bundles succeed" in one pass, per the
   acceptance criteria in §6.

All changes were verified against the existing test suite plus new/updated unit tests for the
new contracts (`62 passed`, up from 61 — one new test added, several updated for the new
shapes), and the offline fixture smoke pipeline (`scripts/smoke_pipeline.py`), before any paid
call was made.

## 1. Retrieval rankings: confirmed unchanged

`hybrid` and `legal_static` were rerun and their `ranking` chunk-id sequences are **byte-for-byte
identical** to v1 for all 3 scenarios (verified by direct comparison, not assumed) — `run_static`
and the retrieval/fusion code (`assemble`, `search`) were not touched by this fix. Only the
`AdaptiveController`'s planning/observation *validation* logic changed, which affects controller
decision-making, not the retriever or its scoring.

For `planned_multisearch`/`adaptive`, the underlying retrieval mechanism is identical, but the
*sequence of queries the LLM controller chooses to issue* legitimately varies run-to-run — this
is inherent LLM sampling variance in an adaptive system, present before and after this fix, and
is not a retrieval-ranking change. Acquired-pool sizes differ from v1's single sample for this
reason (e.g. DEV003 planned_multisearch: 58 acquired in v2 vs 80 in v1), not because search
scoring changed.

## 2. Controller validation failures: before vs after

| Failure mode | v1 (3 scenarios) | v2 (3 scenarios) |
|---|---|---|
| "Planner invented a scenario fact" | 2 of 3 (DEV040, DEV030) | **0 of 3 — eliminated** |
| "Observer cited nonexistent evidence" | 3 of 3 (all scenarios) | 1 of 3 (DEV003 only, 3 occurrences across its 3 operations) |
| Scenarios with `COMPLETED_WITH_FALLBACKS` | 3 of 3 | 1 of 3 (DEV003) |
| Scenarios with zero controller errors | 0 of 3 | **2 of 3 (DEV040, DEV030) — `COMPLETED`, zero errors** |

Removing the requirement to reproduce scenario text verbatim (replaced by a deterministic,
harness-owned fact-ID list) **eliminated fact invention entirely** in this sample. Removing the
requirement to reproduce an exact evidence quote **substantially reduced but did not eliminate**
observer evidence-citation hallucination — DEV003 still shows the observer citing a chunk_id
absent from the evidence it was actually shown, in all 3 of its operations. This is retained as a
real, adverse, unresolved finding, not smoothed over by the improvement elsewhere.

In every case, both before and after this fix, the acceptance criterion "zero invented facts /
zero nonexistent evidence IDs **accepted into controller state**" already held — the harness
always rejected and discarded the invalid output rather than merging it. What changed is the
*rate* at which the model attempts an invalid output in the first place, not the safety net
itself (which was already sound).

**Positive finding retained:** PA2023 s.51 (DEV003's gold provision, absent from `legal_static`
top-30 and from the standalone benchmark's own top-50 under 3 separate configs) is again
recovered by both query-decomposition systems in v2 — rank 12/58 (`planned_multisearch`), rank
8/70 (`adaptive`).

## 3. Bundle judging: 11 of 12 bundles produced a usable judgment (up from 0 of 12 in v1)

`prw judge-bundles --allow-network --adjudicate --max-requests 50` was run once on all 12
bundles (4 systems x 3 scenarios). Outcome:

| | v1 (3 attempts) | v2 (1 attempt, with repair) |
|---|---|---|
| Bundles with a usable judgment | 0 of 12 | **11 of 12** |
| Requests consumed | 9 of 50 (zero results) | 41 of 50 |
| Individual per-judge calls, first-pass valid | 0 (both v1 crashes were mid-batch) | **33 of 33 for the 11 successful bundles — no repair needed for any of them** |
| Bundles requiring a repair attempt | n/a (command aborted before reaching most bundles) | 1 (DEV040/legal_static) |
| Repair outcome for that bundle | n/a | **repair also failed** (`Unknown supporting chunk id`) — logged and skipped, not retried a third time |

The one residual failure means the acceptance criterion "bundle judge produces usable judgments
for **all 12** bundles, either first-pass or after one repair" is **not fully met** — 11 of 12,
not 12 of 12. This is reported plainly rather than rounded up. No further retry was attempted
for this bundle, per the one-repair bound; `judgments/pilot3_v2/bundles/bundle_failures.json`
records the failure.

Of the 3 judges producing valid output on the first pass for 11 bundles: 4 of those 11 bundles
had at least one requirement where the three judges disagreed on (status, applicability) and
were escalated to the adjudicator (`LLM_ADJUDICATED_SILVER`); the adjudicator's own call was
first-pass valid in all 4 cases (no repair needed for adjudication either). 7 of 11 bundles had
full 3-judge agreement (`LLM_CONSENSUS_SILVER`).

## 4. Request/token cost (actual, measured)

| Job | Requests | Total tokens |
|---|---:|---:|
| `planned_multisearch` retrieval (3 scenarios) | 3 | 2,418 |
| `adaptive` retrieval (3 scenarios) | 12 | 129,590 |
| Bundle judging (12 bundles attempted, 11 succeeded) | 41 | 243,123 |
| **Total** | **56** | **375,131** |

All within the previously-approved $2.00 pilot ceiling and the per-job caps used (30/30/50,
mirroring v1's structure). At `gpt-4o-mini` list pricing this totals on the order of a few cents,
not dollars — the same order of magnitude as v1's own measured usage.

## 5. Requirement coverage by system (11 of 12 bundles scored)

| scenario | system | requirement_coverage | content_coverage | scenario_complete | mean_confidence | annotation_status |
|---|---|---:|---:|---:|---:|---|
| DEV003 | hybrid | 0.00 | 1.00 | 0 | 1.00 | LLM_CONSENSUS_SILVER |
| DEV040 | hybrid | 0.00 | 0.33 | 0 | 0.63 | LLM_CONSENSUS_SILVER |
| DEV030 | hybrid | 1.00 | 1.00 | 1 | 1.00 | LLM_CONSENSUS_SILVER |
| DEV003 | legal_static | **1.00*** | 1.00 | 1 | 1.00 | LLM_ADJUDICATED_SILVER |
| DEV040 | legal_static | — | — | — | — | **FAILED (bundle judging error)** |
| DEV030 | legal_static | 1.00 | 1.00 | 1 | 1.00 | LLM_CONSENSUS_SILVER |
| DEV003 | planned_multisearch | **1.00*** | 1.00 | 1 | 1.00 | LLM_CONSENSUS_SILVER |
| DEV040 | planned_multisearch | 0.33 | 0.33 | 0 | 0.60 | LLM_ADJUDICATED_SILVER |
| DEV030 | planned_multisearch | 1.00 | 1.00 | 1 | 1.00 | LLM_CONSENSUS_SILVER |
| DEV003 | adaptive | 0.00 | 0.00 | 0 | 0.80 | LLM_ADJUDICATED_SILVER |
| DEV040 | adaptive | 0.00 | 0.67 | 0 | 0.90 | LLM_ADJUDICATED_SILVER |
| DEV030 | adaptive | 1.00 | 1.00 | 1 | 1.00 | LLM_ADJUDICATED_SILVER |

`*` — flagged and spot-checked; see §6, these two numbers are **not trustworthy as reported**.

## 6. A more important finding than the two bugs this pilot set out to fix

Fixing the two schema-compliance bugs did **not** fix, and was never going to fix, the judge's
*substantive* accuracy — whether a schema-valid `SATISFIED` verdict is actually correct. Spot-
checking the two DEV003 `SATISFIED` results marked `*` above (chosen because they were
surprising given §2's known retrieval facts) found both to be wrong:

- **`legal_static`/DEV003/REQ1** ("the length of the mandatory standstill period and the event
  that starts it running"): the judge (adjudicated, confidence 1.0, sufficiency_grade 3) marked
  this SATISFIED, citing `UKPGA_2023_54__NODEV1__CH_00017` as supporting evidence. That chunk is
  **Procurement Act 2023 s.17 — preliminary market engagement notices**, entirely unrelated to
  standstill periods. Confirmed independently: s.51 (the real answer) is verifiably absent from
  `legal_static`'s candidate pool for this scenario (§2), so the judge could not have cited it —
  instead of correctly returning NOT_SATISFIED, it certified an unrelated section with full
  confidence.
- **`planned_multisearch`/DEV003/REQ1**: also marked SATISFIED, confidence 1.0. Here the judge's
  own `short_reason` text states *"The Procurement Act 2023 s.51 provides binding legal
  information regarding the mandatory standstill period of 8 working days..."* — a substantively
  **correct** statement of law — but s.51 (`UKPGA_2023_54__NODEV1__CH_00051`) is **not** among
  its own `supporting_chunk_ids`, despite being present in this system's bundle at rank 12. The
  judge appears to be answering from memorized legal knowledge rather than the specific supplied
  bundle, while citing four other, different chunks instead — precisely the behavior the bundle
  prompt explicitly instructs against ("Do not use remembered law to fill missing evidence").

Neither the v1 nor the v2 judge contract can structurally catch either failure: validation only
confirms a cited `chunk_id` exists in the bundle, never that the citation or rationale is
*topically entailed* by that chunk's actual text. The old (v1) exact-quote mechanism would not
have caught this either — a model can quote real text from the wrong chunk just as easily as
citing the wrong chunk's ID.

A third spot-check, chosen as a plausibility check on a full-coverage result (`adaptive`/DEV030,
KPI requirements), found the opposite: citations resolved to `UKPGA_2023_54__NODEV1__CH_00052`
(s.52, KPI-setting duty) and `UKPGA_2023_54__NODEV1__CH_00071` (s.71, performance-assessment
duty) — both are the actually-correct governing provisions, matching this project's own
independently corpus-verified gold evidence from the original benchmark construction. So this is
not a uniform judge failure; on this small sample it appears concentrated in the case where the
correct authority is scarce or genuinely hard to retrieve (DEV003), where the judge seems more
willing to manufacture a plausible-sounding SATISFIED than to return NOT_SATISFIED.

**This was not a full audit** — only 3 of 11 successfully-judged bundles were spot-checked (2
surprising results, both wrong; 1 plausibility check, correct). The coverage numbers in §5 for
the other 8 bundles have not been individually verified and should not be treated as validated
either.

**Recommendation, not implemented here (would need a further, separate contract decision, out of
this narrow fix's scope):** before trusting bundle-judge coverage numbers at DEV/TEST scale, add
a safeguard that checks topical entailment between a cited chunk and the rationale/status — for
example, requiring the judge to name the citation string (not full text) it relied on, cross-
checked against the requirement's `source_policy`/description keywords, or a second independent
"does this citation plausibly relate to this requirement" pass. This is a genuinely new, separate
problem from the two this pilot was scoped to fix, and is flagged rather than silently absorbed
into an apparently-clean 11/12 success count.

## 7. Deviation from the literal schema in point 1, disclosed

The requested schema listed exactly five fields (`status`, `supporting_chunk_ids`,
`sufficiency_grade`, `confidence`, `short_reason`). A sixth field, `applicability`
(`APPLICABLE`/`CONDITIONAL`/`INAPPLICABLE`), was added back. Reason: `score_bundle`'s existing,
untouched evaluation definition applies a harness-side deterministic gate — a `CONDITIONAL`
applicability only counts toward a requirement's satisfaction when that specific requirement's
own `allow_conditional` flag permits it. Folding applicability into the model's own `status`
judgment would remove this gate and be a real, if implicit, change to the evaluation definition
the instructions said to preserve. Adding the one field back was judged the smaller deviation.
Coverage-formula code (`requirement_coverage`, `content_coverage`, `scenario_complete`, the
mandatory/`source_policy`/`_role_ok` authority-type gate) is otherwise **unchanged** from the
pre-existing, untouched `prw/metrics.py` definitions.

`requirements_unknown` is no longer populated (the v2 status enum has no UNKNOWN/abstention
value — the judge must commit to one of three statuses); `confidence` is reported per bundle
instead as the nearest available abstention-strength signal. This is a disclosed simplification,
not a silent drop.

## 8. Acceptance criteria (§6 of the instruction) — checked against actual results

| Criterion | Result |
|---|---|
| Zero invented scenario facts entering controller state | **Met** (already true in v1 via the safety net; now also true at the *attempt* level — 0 of 3 in v2 vs 2 of 3 in v1) |
| Zero nonexistent evidence IDs accepted | **Met** (structural safety net; residual attempt rate 1 of 3 scenarios, not 0 of 3 — see §2) |
| Zero requirement-set changes possible by construction | **Met** — the model never emits requirement IDs at all; a wrong-length array is the only way this class of error can occur, and it did not occur in v2 |
| Bundle judge produces usable judgments for all 12 bundles, first-pass or after one repair | **Not met** — 11 of 12 |
| All search budgets remain matched | **Met** — retrieval config (`candidate_depth`, `retrieval_depth`, `k`, `graph_fanout`) unchanged; rankings for static systems verified byte-identical to v1 |
| s.51 positive result and all adverse results retained regardless of outcome | **Met** — s.51 recovery reconfirmed in both systems (§2); DEV003 residual observer hallucination, the 1 failed bundle, and the judge substantive-accuracy problem (§6) are all reported, not smoothed over |

**Given the unmet criterion and the new §6 finding, this pilot has not fully passed.** Per
instruction 10, the full DEV/TEST experiment should not be launched yet. Recommended next
decision points, in order: (a) decide how to handle the judge substantive-accuracy risk in §6
before trusting any coverage number at scale; (b) decide whether the 1-of-12 residual bundle
failure and DEV003's residual observer hallucination are acceptable to proceed with as disclosed
limitations, or need a further bounded fix.

## 9. Remaining limitations

- Judge substantive-accuracy risk (§6) — the most consequential open issue, newly discovered by
  this pilot, not previously visible because v1 never produced a single usable bundle judgment.
- 1 of 12 bundles still fails even with the repair loop (`DEV040`/`legal_static`, "Unknown
  supporting chunk id" on both first pass and repair).
- DEV003's observer still hallucinates a nonexistent chunk_id citation in all 3 operations,
  though this no longer affects 2 of the 3 pilot scenarios as it did in v1.
- Single-model (`gpt-4o-mini`) repeated-judge configuration remains, as before — no genuine judge
  diversity.
- Sample size remains 3 scenarios; none of the above rates should be extrapolated to the full
  40/20 DEV/TEST split without a larger diagnostic run.
- `research_state/LAST_CHECKPOINT.md` updated to reflect this exact state.
