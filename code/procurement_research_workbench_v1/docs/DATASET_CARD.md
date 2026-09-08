# Procurement Scenario Benchmark: dataset card

Version: 1.0.0. Authored: 7 September 2026. Language: English.

## Contents

60 fictional source-guided scenarios: 40 development and 20 test candidates. They define 161 mandatory evidence requirements. There are 12 additional fixed follow-ups, eight development and four test. There are 22 topic labels. Counts are reproducible from `data/test_sealed/build_dataset_source.py` (evaluator-only authoring source) and `validation/dataset_audit.json`.

| Primary task | DEV | TEST | Total |
|---|---:|---:|---:|
| Statutory or explicit rule lookup | 6 | 2 | 8 |
| Natural-language procurement question | 7 | 3 | 10 |
| Vocabulary mismatch | 5 | 3 | 8 |
| Multiple evidence needs | 6 | 4 | 10 |
| Applicability or transition | 5 | 3 | 8 |
| Practical official guidance | 6 | 2 | 8 |
| Requested source authority | 2 | 2 | 4 |
| Compound or underspecified | 3 | 1 | 4 |
| Total | 40 | 20 | 60 |

This is a purposive research sample, not an estimated distribution of real procurement users. Primary suites overlap conceptually: a practical scenario may also involve terminology mismatch. No percentile of UK procurement-law coverage is claimed.

## Scope

The common assumption is an English public contracting authority considering an above-threshold, non-exempt contract, not utilities, concessions, defence or light-touch procurement, unless expressly overridden. This avoids silently applying ordinary procurement rules to every contract category. One Scottish scenario deliberately tests jurisdictional scope recognition, not comprehensive Scottish procurement expertise.

The scenario subjects include planning and pipeline publication, market engagement, valuation, lots, competition, award criteria, participation, direct award, exclusion, frameworks, dynamic markets, notices, conflicts, performance, payments, modification and information disclosure. Regime uncertainty is intentional in selected cases. User phrasing never supplies evaluator requirement IDs to the retrieval controller.

The source registry lists official guidance/legislation pages checked for topical orientation. It does not establish that every required passage exists in the user's corpus, or that the question's legal resolution has been expert verified. The cases and evaluator requirements are authored by this assistant, not independently produced by three legal experts.

## Actual construction procedure

1. Read the supplied architecture, historical evaluation audit and user-defined project scope.
2. Select a task-by-topic blueprint before observing new system outputs.
3. Consult official guidance pages for topical orientation, especially transition, direct award, participation, award assessment, frameworks, modifications, KPIs, payment, lots, notices and FOIA.
4. Write 60 distinct fictional decision situations and corresponding information requirements. Requirements state what must be evidenced, not a predetermined legal decision.
5. Separate public questions from private evaluator requirements. Do not create a closed list of accepted chunks or fabricate IDs from the unavailable live index.
6. Assign whole scenario groups to DEV or TEST. Write follow-ups tied to their parent group using fixed user-only history.
7. Check record counts, identifiers, source-registry keys, field validity, group isolation and normalized lexical duplication. No exact cross-split duplicates were found. This is not a proof of legal-scenario independence.
8. Leave annotations UNJUDGED and corpus sufficiency NOT_ASSESSED. Generate final silver judgments only after all compared methods retrieve evidence.

No new production retrieval output was consulted when authoring the scenarios. The cases are not real user logs and no personal information is required.

## Record example

See `examples/development_case.json` for an actual DEV case and `examples/evaluator_requirements.json` for its separate private information needs. The scenario's source label is not evidence of applicability: that is assessed against the facts and excerpts.

Public fields: scenario_id, scenario_group_id, split, suite, topic, as_of, user_message, history, synthetic and authoring_status. Runtime construction forwards only scenario_id, user_message, history and as_of. Suite/topic/split are administrative metadata, not hints to the agent.

Private fields: requirements (id, description, mandatory, source_policy, allow_conditional), reference_source_ids, missing_facts, regime_context, annotation status and corpus support status. None enters the runtime controller.

Source policies:

- BINDING_REQUIRED: sufficiency additionally needs appropriate primary or secondary legal evidence.
- OFFICIAL_ALLOWED: binding or official explanatory/operational material is acceptable when it actually supplies the information.
- ANY_SUPPORTED: a supported source can be relevant without imposing the preceding class restriction.

## Follow-ups

Each follow-up supplies a factual clarification or change. It uses fixed user-only history, not a baseline model's answer and not feedback selected after seeing retrieval success. This design compares retrieval under context changes without coupling one system to another's previous output. It does not test natural dialogue satisfaction or authentic user correction behaviour.

## Test discipline and limits

Keep `data/test_sealed` outside code-development model context. The folder is readable, not encrypted. Freeze only after a separate evaluator process has checked scope and requirements. If the same agent sees test situations while tuning policy, a later hash does not restore independence.

The new test is small. Do not make stable suite-level generalisation claims from one to four cases per suite. Model-authored scenarios can reflect authoring biases, source-selection bias and unrealistically explicit context. AI silver judges can agree on errors. Report all these limits.

If corpus evidence is missing, retain the case in the full-sample result and label the gap; do not replace it merely because it is inconvenient. A separately reported supported-only subset needs a predeclared, independent support audit, which is excluded from this package.
