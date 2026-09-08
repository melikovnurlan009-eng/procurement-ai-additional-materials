# Case Studies

## DEV003 — decomposition-recovery mechanism case (PA2023 s.51, standstill period)

Requirement: "the length of the mandatory standstill period and the event that starts it
running." Gold provision: PA2023 s.51 (`UKPGA_2023_54__NODEV1__CH_00051`, 8 working days from
contract award notice publication).

| System | s.51 in acquired candidates? | Acquired-pool rank | s.51 in final top-10? |
|---|---|---:|---|
| `hybrid` | No | -- (0/20 acquired) | No |
| `legal_static` | No | -- (0/30 acquired) | No |
| `planned_multisearch` | Yes | 3 / 93 | **Yes, rank 3** |
| `adaptive` | Yes | 16 / 83 | **No** |

Source: `runs/dev_scale/{system}/runs.jsonl`, scenario `DEV003`, direct chunk_id lookup against
`ranking` (final top-10) and `acquired` (full candidate set) fields.

**Mechanism**: both static systems' single-pass query never surfaces s.51 as a candidate at all
-- consistent with the benchmark-wide candidate-generation bottleneck in
`STATIC_BENCHMARK_FINAL_REPORT.md` §2. Both query-decomposition systems recover it into their
candidate pool via an explicit sub-query targeting the standstill period specifically. Only
`planned_multisearch` carries that recovery through into its reported final top-10;
`adaptive`'s own bundle-assembly step (coverage-driven selection layered on top of raw rank, see
`prw/controller.py::assemble`) does not select it for the final 10 in this run.

**Caveat, stated explicitly per instruction**: this is one scenario. It demonstrates that
query decomposition *can* recover a candidate-generation miss that a single-pass query cannot --
a real, mechanism-level finding -- but it does not establish that `adaptive` (or
`planned_multisearch`) is superior overall. `MATCHED_DEV_FINAL_REPORT.md` §2's aggregate H2 test
(`adaptive` vs `legal_static` delta = 0.0, p=1.0) and §3's three regression cases directly
contradict any inference that decomposition always helps.

## DEV013 — shared regression case (both `planned_multisearch` and `adaptive`)

Suite: `vocabulary_mismatch`. `legal_static`: requirement_coverage = 1.00 (single-pass query
succeeds). `planned_multisearch`: 0.00. `adaptive`: 0.00. `hybrid`: 0.00.

This is the one scenario where BOTH query-decomposition systems do strictly worse than
`legal_static`, not just no better. The suite label (`vocabulary_mismatch` -- scenarios
deliberately worded to avoid the statute's own terms) suggests a plausible mechanism: the
single legal-lane query, tuned for legal-source retrieval, already bridges the vocabulary gap in
one pass; decomposing into sub-queries risks fragmenting that one successful query into pieces
that individually match the mismatched vocabulary less well. This is stated as a plausible
mechanism, not confirmed by a dedicated ablation -- flagged for follow-up, not asserted as fact.

## DEV016 / DEV034 — adaptive-only regressions

`DEV016` (`vocabulary_mismatch`): `legal_static` and `planned_multisearch` both reach 1.00
coverage; `adaptive` reaches 0.00. `DEV034` (`guidance`): `hybrid`, `legal_static` and
`planned_multisearch` all reach 1.00; `adaptive` alone reaches 0.00. In both cases
`planned_multisearch` (same controller architecture and budget, no observation/adaptation step
-- but an independently generated, non-deterministic decomposition, not necessarily the same
sub-queries as `adaptive` produced for the same scenario) succeeds where
`adaptive` fails -- consistent with `MATCHED_DEV_FINAL_REPORT.md` §3's finding that `adaptive`'s
observation-and-adapt loop does not add measurable aggregate value over the budget-matched
`planned_multisearch` control, and shows here it can actively remove value the simpler control
would have kept, at least in these two cases.

## TEST019 — independent replication of the DEV003 mechanism (frozen TEST, not tuned on this result)

TEST019's gold requirement is independently also about PA2023 s.51 (mandatory standstill
period) -- same underlying provision as DEV003, different scenario, discovered only after the
TEST freeze and single execution (not used to tune anything).

| System | s.51 present at rank | Top-1 result instead |
|---|---|---|
| `legal_static` | Not in top-10 | s.50 (adjacent, wrong section) |
| `planned_multisearch` | **Rank 1** | -- |
| `adaptive` | **Rank 1** | -- |

Same mechanism as DEV003: `legal_static`'s single query lands adjacent to the correct provision
but not on it; both decomposition systems reach it directly. This is now confirmed on two
independent scenarios (DEV003, TEST019) rather than one -- still not proof of general adaptive
superiority (`TEST_FINAL_REPORT.md` §4's H2 result remains non-significant even with this case
included), but a stronger, twice-replicated mechanism finding than DEV003 alone.

## A TEST-scale pattern reversal, noted not smoothed over

On DEV, `adaptive` had *more* regression cases vs `legal_static` than `planned_multisearch` (3
vs 1, `CONTROLLER_DIAGNOSTICS.csv`). On TEST, this reverses: `adaptive` has **zero** regressions
vs `legal_static` (0/20) while `planned_multisearch` has 2 (`TEST002`, `TEST003`). At these
sample sizes (3 vs 1 out of 40; 0 vs 2 out of 20) neither pattern should be read as a stable,
general property of either system -- both are reported, and neither is presented as the "true"
finding overriding the other.

## Manual spot-check status

Human-labelled inspection status for a wider set of cases (major wins/regressions, a
graph-recovery example, an authority/regime failure example) is recorded separately in
`MANUAL_EVALUATION_AUDIT.md`, which also states plainly that this project's "manual" pass is an
agent-conducted QA audit, not independent human verification -- see that file's own framing note
before citing any confirmation from it.
