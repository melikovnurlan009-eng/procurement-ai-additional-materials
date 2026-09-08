# Final Thesis Findings

Mapped to `docs/RESEARCH_PROTOCOL.md`'s hypotheses H1-H3 (Purpose and status, Hypotheses and
comparisons sections).

## RQ1 — Does legal-aware static retrieval improve requirement coverage over conventional hybrid retrieval at the same final context size? (H1)

**Yes, replicated on both the DEV split and the frozen TEST split.** `legal_static` beats
`hybrid` by +0.486 requirement coverage on DEV (n=37, p=1.1e-05) and +0.412 on TEST (n=17,
p=0.0215). Same direction, same order of magnitude, on two separate scenario samples. This is
the single most statistically robust result in the whole project. (TEST was evaluated once,
frozen, by the same process that constructed it -- see the methodology disclosure in
`TEST_FINAL_REPORT.md`; "replicated" here refers to the statistical pattern holding on a second,
disjoint sample, not to independent execution.)

## RQ2 — Does feedback-controlled retrieval (adaptive, inspecting intermediate evidence) improve coverage beyond a planner issuing several queries without inspecting evidence (planned_multisearch/legal_static)? (H2)

**Not supported, at either DEV or TEST scale, and the two runs do not even agree with each other
on direction.** DEV: `adaptive` vs `legal_static` delta = exactly 0.0 (p=1.0). TEST: `adaptive`
vs `legal_static` delta = +0.176 (p=0.125, not significant). `adaptive` does have the highest
pooled nDCG@10 on DEV (0.552) and on TEST (0.551) of all four systems — a ranking-quality signal
worth reporting, but distinct from, and not sufficient to confirm, the coverage-based H2 test.
**Treat H2 as an open question**, not resolved positively or negatively by this project.

## RQ3 — Does any coverage gain depend on query type and come with additional cost, rather than being explained by extra search alone? (H3)

**H3's own warning is directly and repeatedly confirmed.** The essential control
(`planned_multisearch` vs `adaptive`, same controller architecture and maximum retrieval budget)
shows no significant difference on DEV (delta=+0.095, p=0.375) or TEST (delta=+0.029, p=0.6875)
— the most consistently reproduced null result in this project, replicated at two sample sizes.
Note this is not a perfectly isolated causal control: the two conditions independently generate
their own query decompositions via a stochastic, unseeded LLM call, so their realized sub-queries
for a given scenario are not guaranteed to be identical, only architecturally comparable under
the same budget. Additional cost is real and substantial:
`adaptive` used 1,271,466 tokens across 40 DEV scenarios (vs `planned_multisearch`'s 29,326) and
604,504 tokens across 20 TEST scenarios (vs 15,365), for no confirmed aggregate coverage benefit
over the cheaper, non-adaptive control. Per-suite/per-scenario variation is real (query
decomposition helps in some cases — DEV003, TEST019 — and actively hurts in others — DEV013,
DEV016, DEV034, TEST002, TEST003) — the gain is genuinely query-dependent, exactly as H3
anticipated, not a uniform improvement.

## Strongest supported claim

Legal-aware static retrieval (`legal_static`) delivers a large, statistically significant,
independently-replicated improvement in requirement coverage over conventional hybrid retrieval,
at no additional model cost (both are free, non-LLM retrieval configurations).

## Unsupported / inconclusive hypotheses

- H2 (adaptive feedback loop improves coverage over legal_static): not supported on either DEV or
  TEST; the two runs even disagree on direction (exact tie vs a non-significant positive gap).
- Whether graph expansion helps retrieval at all: not supported on the standalone benchmark (p=0.375,
  4 wins/55 ties/1 loss out of 60).
- Which of `C_hybrid`/`D_hybrid_priors`/`E_hybrid_graph`/`F_two_lane` is the single best static
  configuration: not resolved — no pairwise difference among them is significant at n=60.

## Principal limitations

1. **TEST was not run by an independent evaluator.** This session authored the TEST scenarios,
   requirements, and gold evidence, and read them all before freezing and then executing the
   design itself. This is disclosed in `FINAL_FREEZE.json` and `TEST_FINAL_REPORT.md` and must
   be stated in the thesis wherever TEST numbers are cited.
2. Bundle (combined-evidence) sufficiency judging is demoted to exploratory after observed
   substantive false-positive judgments (schema-valid, high-confidence, but factually wrong
   verdicts) — see `docs/RESEARCH_PROTOCOL.md`'s status update. No claim in this project rests on
   bundle-sufficiency numbers alone.
3. All LLM judging in this project used a single model family (`gpt-4o-mini`) in every
   controller/judge/adjudicator slot — a repeated-model, not a genuinely diverse-judge,
   configuration.
4. Pointwise pooled judging excluded a small number of scenarios where a judge failed validation
   even after one bounded repair attempt (3/40 DEV, 3/20 TEST) — reported exactly, not
   backfilled or treated as zero.
5. Sample sizes are small, especially at TEST (n=17 scorable scenarios) and for individual suites
   (as few as 1-4 scenarios per suite) — per-suite and small-n comparisons are descriptive, not
   stable estimates.
6. Manual QA in `MANUAL_EVALUATION_AUDIT.md` is an agent-conducted quality-assurance pass, not
   independent human verification.

## 5-8 exact, thesis-ready sentences (safe to state as written)

1. Legal-aware static retrieval significantly improves requirement coverage over conventional
   hybrid retrieval at matched context budgets, confirmed independently on both a 37-scenario
   development set (Δ=+0.486, p=1.1×10⁻⁵) and a 17-scenario frozen test set (Δ=+0.412, p=0.0215).
2. An adaptive, feedback-controlled retrieval policy did not achieve a statistically significant
   requirement-coverage improvement over a static, budget-matched planned multi-search baseline
   on either the development set (p=0.375) or the frozen test set (p=0.6875), despite issuing
   the same number of decomposed queries.
3. Candidate generation, not final-stage ranking, is the dominant retrieval failure mode across
   the evaluated corpus: two-thirds of scenarios in the standalone 60-scenario benchmark never
   surface the gold statutory provision as a candidate at all, regardless of how ranking is done.
4. Dense (embedding-only) retrieval achieved the highest pooled nDCG@10 of any single
   configuration but also the highest wrong-regime error rate, more than three times that of the
   best-balanced configuration — a trade-off that raw ranking-quality metrics alone would not
   surface.
5. Query decomposition recovered a statutory provision missed entirely by single-pass retrieval
   in two independently observed cases (one development, one frozen-test scenario concerning the
   same underlying provision), demonstrating a real recovery mechanism without establishing
   general superiority of decomposition-based retrieval.
6. The adaptive controller's validation layer caught and safely discarded invalid or
   self-contradictory model output in roughly half of development and test scenarios without any
   such output being accepted into a reported result, at the cost of materially higher token
   usage than its non-adaptive counterpart.
7. All reported large-language-model judgments in this work used a single model family across
   every judge and adjudicator role, and the frozen test-stage evaluation was executed by the
   same process that authored the test scenarios; both are disclosed limitations on the
   independence of the reported results, not omissions.
8. Graph-based query expansion produced no statistically significant change in requirement
   coverage on the standalone retrieval benchmark, differing from single-pass hybrid retrieval on
   only 5 of 60 scenarios in either direction.
