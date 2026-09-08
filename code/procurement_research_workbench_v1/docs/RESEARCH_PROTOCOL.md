# Predeclared research protocol

## Purpose and status

This protocol tests an existing procurement retrieval engine and an added, bounded retrieval controller. It is not a claim of novelty for BM25, embeddings, RRF or generic query rewriting. The contribution under test is the interaction between legal source roles, explicit citations, retrieval-budget allocation and evidence-based stopping on compound questions.

This release contains no new research performance results. Runtime integrations must be tested in the user's repository. Corpus audit, full-corpus completeness, legal-effect extraction and a rebuilt benchmark annotation history are outside this package.

## Hypotheses and comparisons

H1: legal-aware static retrieval improves requirement coverage over conventional hybrid retrieval at the same final context size.

H2: feedback-controlled retrieval improves coverage beyond a planner issuing several queries without inspecting intermediate evidence.

H3: any gain depends on query type and comes with additional model/search cost; it should not be inferred from one aggregate number.

H4: improved evidence sufficiency may improve answer completeness and grounding when the answer model and prompt remain fixed.

Primary comparisons: `hybrid` vs `legal_static`; `legal_static` vs `adaptive`; `planned_multisearch` vs `adaptive`. The third is essential: extra searches alone can explain an apparent improvement over a single-pass baseline. Different comparisons isolate different questions, not the effect of every individual component.

Development ablations also implement lexical, dense, hybrid+priors, hybrid+graph and hybrid+priors+graph. These call the existing production methods while disabling the separate forced-legislation-promotion patch for conventional baseline arms. Verify the adapter's capability report before citing this separation.

## Budgets

Defaults are declared starting settings, not optimized results:

| Resource | Static | Planned multi-search | Adaptive |
|---|---:|---:|---:|
| Maximum retrieval tool operations | 1 | 3 | 3 |
| Candidate depth per lexical/dense channel per operation | 100 | 100 | 100 |
| Final evidence chunks, total | 10 | 10 | 10 |
| Final text + citation character cap | 18,000 | 18,000 | 18,000 |
| Graph hops per operation | 1 | 1 | 1 |
| Graph fan-out cap | 20 | 20 | 20 |

The legal engine returns acquisition candidates from two source lanes; `retrieval_depth=20` means 20 per lane there, but 20 merged results in the conventional adapter. This is logged, not hidden. All final comparisons use the same total context budget. For an isolated source-role ablation beyond this design, compare partitions of the same cached candidate union and record that additional control explicitly.

The final legal bundle initially reserves half its slots for each lane and permits backfill when one lane cannot use its slots. A character cap is not an exact token cap; report observed generator input/output tokens when available. Do not call three retrieval operations computationally identical if models, graph fan-out or answer context differ.

## Train, development, test

No model training is performed here. Use 40 scenarios for development and 20 new candidate scenarios for a final prospective evaluation. There are 12 optional follow-ups grouped with parent scenarios. Public files contain user facts; private files contain evaluator requirements. Runtime objects use a strict allowlist and reject common answer-key fields.

The test directory is not cryptographically secret. A coding agent allowed to read it can contaminate development even without executing retrieval. Keep test authoring/review in an evaluator-only process. Freeze scenario texts, requirement definitions, all method configurations, prompt/code versions, external repository commit and source snapshot before final testing. The package checks its own code/config/test hash; the operator must preserve the external corpus and model identities.

Matching legal provisions across splits is allowed. Repeated decision situations with changed names or wrapper text are not independent test cases. Structural duplicate checks are included; expert/scenario-semantic independence remains a review task, not a guaranteed property of a low lexical similarity value.

Do not use the former 150/150 wrapper dataset as this prospective test. Preserve its historical results as development or paraphrase evidence. Do not reclassify old analyses as prospective validation.

## Label construction

Requirements describe the information necessary to answer the user's actual question. They are not a list of section IDs the retriever must reproduce. Topic source links are reference leads, not final legal truth and not a closed set of correct passages. Every genuinely useful candidate discovered by any compared system can receive credit.

Evaluate whole final bundles for sufficiency and individual pooled passages for ranking quality. Three separately invoked judges use a common rubric. Their agreement is evidence of label consistency, not external legal validity. Source quotes constrain unsupported labeling but do not prove entailment. Any legal-accuracy claims remain conditional on verified independent reference excerpts.

Corpus-support states begin NOT_ASSESSED. Do not silently drop an unsupported or difficult scenario after a poor result. Report full-sample performance and visible corpus gaps. A supported-only diagnostic is permissible only with an independent, predeclared support audit and a separately reported denominator. No such corpus audit has been performed here.

## Status update (2026-09-07): bundle sufficiency demoted to exploratory

Three-judge combined-bundle sufficiency was this protocol's original primary outcome. A 3-
scenario pilot (`procurement_research_workbench_v1/results/pilot3_v2/PILOT_REPORT_V2.md` sec 6)
fixed the two reproducible schema-compliance bugs in the bundle-judge contract, then spot-checked
3 of the resulting 11 usable bundle judgments as a plausibility check. Two of the three were
substantively wrong despite being schema-valid and high-confidence: one certified an unrelated
statutory provision (Procurement Act 2023 s.17, preliminary market engagement) as satisfying a
standstill-period requirement; another wrote a substantively correct legal rationale in its own
words while citing chunks that did not include the actually-correct, actually-retrieved provision.
Neither failure is catchable by validating that a cited chunk_id merely exists in the bundle --
that check never verifies topical entailment between a citation and the judge's rationale. This
is a materially different problem from the two fixed contract bugs, discovered only because this
pilot was the first run to produce any usable bundle judgments at all.

**Bundle requirement coverage is therefore demoted from primary to exploratory** as of this
update. Its formulas below are retained and still computed/reported where available, but no
thesis claim should rest on a bundle-coverage number alone without independent spot-checking.
Pooled passage relevance and strict verified target retrieval (next section) are now primary.

### Exploratory outcome: bundle requirement coverage

For scenario q with mandatory requirements Rq, a requirement is satisfied only when the final bundle has assessed FULL/SATISFIED support, appropriate applicability, and evidence meeting the stated source policy. Supporting passages can be complementary. A binding-required requirement cannot be met by guidance alone.

Coverage(q) = satisfied mandatory requirements / all mandatory requirements.

Complete(q) = 1 only when every mandatory requirement is satisfied.

Macro-average scenarios equally. Follow-ups do not count as independent scenarios in uncertainty estimation: aggregate by scenario_group_id first. Separate content-only coverage from coverage meeting binding/official source policies.

## Primary outcomes: pooled passage relevance and strict verified target retrieval

Two outcomes now jointly serve as primary, chosen for complementary reasons: pooled passage
relevance is broader (any judged-relevant passage counts, not only a resolved essential-evidence
citation) but still LLM-mediated at the single-passage level (a smaller, more contained judgment
than bundle synthesis, though not immune in principle to the same class of error); strict
verified target retrieval is narrower (only corpus-verified essential-evidence chunk_ids count)
but requires no LLM judgment anywhere in its computation, giving one purely mechanical,
judge-independent signal alongside the LLM-mediated one.

**Pooled passage relevance** (`procurement_research_workbench_v1`, `prw judge`/`prw evaluate`):
- Pooled nDCG@10 with gains 2^grade - 1 and a single shared judged pool. Its IDCG is pool-relative, not exhaustive corpus truth.
- Hit@10 for at least one grade >=2 passage. This is not Recall@10.
- MRR for first sufficiently supporting passage.
- Inapplicable and unknown-applicability fractions among returned passages.
- Binding and official evidence requirement coverage, with explicit denominators.

**Strict verified target retrieval** (`evaluation/final_retrieval_benchmark/strict_target_recall.py`):
computed directly against `gold_evidence.jsonl`'s corpus-verified (MATCHED/FUZZY_MATCHED)
essential-evidence chunk_ids, with zero LLM involvement. Per (scenario, requirement) with a
resolved target: Recall@5, Recall@10 (does any resolved target chunk appear in the top-k?),
scenario-complete@10 (all requirements satisfied), and MRR to the first target hit. Reported as a
strict lower bound -- acceptable alternatives and strong-supporting-only evidence are not counted
as targets, so true system credit is understated, not overstated, by this metric.

**Both outcomes, plus candidate-generation-ceiling and authority/regime diagnostics, plus:**
- Total operations, source candidates, context characters, latency, request/token usage and failure rates.
- Paired wins/ties/losses and scenario-group bootstrap intervals, not a single arbitrary weighted score.

Do not report corpus-level passage recall without an appropriate relevance denominator. The exact budget-constrained oracle is an evaluation-only upper bound for the judged pointwise incidence matrix in a finite pool, not a corpus-wide ceiling and not a deployment baseline. It does not model undiscovered complementary sets.

## Failure and label sensitivity

Report model errors, invalid plans, invalid quoted support, forced stop, no new evidence, budget exhaustion, missing corpus evidence and bad backend integration separately. An invalid model decision may fall back deterministically and is marked as a degraded execution. Unavailable credentials and exhausted spending budgets stop execution instead of scoring a fake adaptive run.

Show per-judge outcome sensitivity. If the sign of an adaptive-vs-static delta changes across judges, qualify the conclusion. Bootstrap intervals address scenario sampling, not systematic AI-judge error. With only 20 test candidates, per-suite counts of one to four are descriptive examples, not stable suite-level performance estimates.

Standing caveat (2026-09-07): any LLM-judged label (bundle or pointwise) can be schema-valid, high-confidence and substantively wrong -- observed directly in bundle judging (see the status update above). No validation mechanism here checks topical entailment between a citation and a judge's rationale, only that the cited id exists in what it was shown. Treat any single LLM-judged SATISFIED/FULL/relevant label as provisional until spot-checked; prefer the strict verified-target metric where a claim needs to be judge-independent.

## Follow-up experiment

The 12 supplied follow-ups change or clarify facts and reuse fixed user-only history. They were not selected because one phrasing succeeded. This is a contextual retrieval test, not yet a user study or a full natural conversation benchmark. Do not claim a generic template approximates real user feedback quality. Keep parent and follow-up together for sampling and splitting.

## Freeze and stopping the research

Select configurations using DEV before opening test outcomes. Finish all intended methods before one final comparative test stage. Re-running for a software execution error must preserve the earlier failed run and document why it was invalid. New test results cannot be used to tune an agent and still be called held out.

Under a deadline, finish one defensible static/adaptive comparison with bundle judging before optional large passage pools, additional embedding sweeps or new agent tools. A negative result remains a valid result.

## Hash convention

File manifests use SHA-256 of the complete file bytes. Workbench evidence `content_sha256` uses SHA-256 of the canonical JSON string encoding of the exact text (`prw.io.digest(text)`). This is distinct from a corpus scraper's raw-byte hash. Convert exported evidence with `Evidence` rather than copying a hash from another convention. Original source content and its external provenance remain unchanged.
