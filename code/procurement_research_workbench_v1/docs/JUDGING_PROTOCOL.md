# Three-judge silver-label protocol

## Why three judging tasks exist

1. **Passage judging** asks whether a particular retrieved excerpt is relevant and what it supports. This drives pooled nDCG and conservative passage-level coverage.
2. **Bundle judging** asks whether the final collection of excerpts jointly supplies the necessary evidence. This is the primary scenario-completeness test.
3. **Answer judging** asks whether the generated answer uses evidence correctly, addresses the question and, when independently verified references are supplied, states the legal position correctly.

These are separate outputs. A controller's internal confidence is never an evaluation label.

## Common rubric, blinded systems

Three judge slots receive identical task definitions, source text, user context and evaluator requirements. They do not see the system name, source channel score, retrieval rank, generated keyword metadata or each other's first-pass label. The prompts request concise evidence rationales, not private chain of thought. For bundle judging, source order is stable by hashed source ID, not chosen by which system ranked it highly.

Prefer distinct accessible model families when practical. Three isolated invocations of one model remain correlated repeated-model judgments. Do not call them independent experts. Using three different grading standards would undermine agreement analysis; a separate adversarial review may supplement, not replace, the common rubric.

## Passage rubric

| Grade | Interpretation |
|---|---|
| 3 | Directly addresses a required information need |
| 2 | Material supporting evidence, but not necessarily sufficient alone |
| 1 | Relevant background |
| 0 | Irrelevant or misleading for the particular question |
| null | Judge abstains because responsible assessment is not possible |

For every evaluator requirement, the judge independently returns FULL, PARTIAL, NONE, CONTRADICTS or UNKNOWN. FULL requires necessary qualifications in the candidate; relevance >=2 alone never establishes sufficiency. Exact character spans and matching quotes are required for FULL, PARTIAL and CONTRADICTS. Offset errors are repaired only when the exact quoted text occurs once, and repairs are logged. Fabricated or ambiguous quotations fail validation.

Source role is not relevance. Binding law on the wrong issue can be grade 0; directly useful official implementation guidance can be grade 3. Requirement source policies encode when legislation is specifically needed. Metadata can be wrong and should not substitute for reading the source.

## Alternative and complementary evidence

All compared systems contribute to the passage pool, including adaptive-only discoveries. Reference passages can be added, but the reference list is not exclusive. Pooling must happen after every compared system runs. A new system introduced later may add previously unjudged outputs; expand the pool and recompute all systems against the revised qrels version.

Do not silently equate two PARTIAL passages with FULL support. The separate bundle judge must cite the combination and explain why it establishes the atomic requirement. Conversely, do not penalize a jointly sufficient bundle merely because no single passage is complete.

## Consensus and adjudication

Concordant support/applicability with adjacent ordinal grades may use the median grade. Any disagreement about FULL/PARTIAL status, applicability, or materially different grades goes to adjudication. A 2-vs-1 vote that changes scenario completeness is not automatically accepted. All abstentions remain visible.

The adjudicator re-reads the full evidence and treats earlier rationales as disputed claims. Its output is validated by the same schema and quotation rules. An adjudicated label is still silver, not expert legal gold.

Completion states:

- LLM_FIRST_PASS: an individual judge output.
- LLM_CONSENSUS_SILVER: accepted common assessment.
- LLM_ADJUDICATED_SILVER: resolved using another configured model.
- REQUIRES_ADJUDICATION / UNRESOLVED: do not score as zero.
- HUMAN_REVIEWED: only use when a human actually reviewed this record and provenance records that act.

## Judgment completeness

Every returned candidate affecting a reported top-k metric must be finally judged. `evaluate` fails when a top-k candidate is unjudged or the source hash changed. A zero-relevance ideal pool yields undefined nDCG, not an invented denominator; the number of defined cases is reported.

For deadline use, `pool --final-only` limits passage judging to the union of final evaluated outputs. This controls costs but narrows the pool and does not support deep candidate-recall analysis. `pool` without that option includes all saved acquisition candidates and is suitable for deeper diagnostics. Neither is exhaustive corpus relevance.

## Answer assessment

Use the same answer generator and prompt for every retrieval method. A citation-ID validator checks only whether supplied IDs are referenced. It does not prove support, truth or completeness. Judges distinguish these explicitly.

Independent reference excerpts must include actual text, citation and URL, not just a known section title. With no such reference evidence, `legal_correctness` must be null. Report groundedness, completeness and source-use metrics instead of disguising them as legal accuracy. A self-consistent answer built from an incorrect excerpt is still possible.

Rationales are short, evidence-based explanations. Do not infer that polished writing, confidence or consensus establishes legal truth.

## Agreement, uncertainty and sensitivity

Report pairwise ordinal weighted kappa and raw agreement for passage grades, plus disagreement counts for requirement support and applicability. Degenerate distributions can make kappa undefined. High agreement is not proof of correctness; low agreement signals uncertain labels.

Repeat primary system comparisons separately under J1, J2 and J3 bundle judgments. Report whether the ordering changes. Report scenario-group paired bootstrap intervals and wins/ties/losses for the final silver labels. Do not present these intervals as accounting for common model bias.

## Minimal reference format

`examples/reference_record.json` shows the structure. It is explicitly a template, not legal evidence. Build real reference excerpts in a separate evaluator workflow before answer correctness is assessed. A review of a small set of source passages by the author is useful only if actually completed and recorded; the package does not claim it occurred.
