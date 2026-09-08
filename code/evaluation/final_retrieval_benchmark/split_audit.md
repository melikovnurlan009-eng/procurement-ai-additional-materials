# Split Audit — Final Retrieval Benchmark

DEV scenarios: 40. TEST scenarios: 20.

## 1. Exact query-text duplicates (DEV vs TEST)

None found.

## 2. Normalised-text duplicates (DEV vs TEST)

None found.

## 3. Semantic similarity >= 0.9 (BGE-M3 cosine, DEV vs TEST)

None found above threshold 0.9.

## 4. Same topic + role + organisation-type template clusters spanning DEV and TEST

| topic | user_role | organisation_type | scenario_ids | decision |
|---|---|---|---|---|
| standstill | contract_manager | nhs_body | DEV028, TEST019 | NEEDS_REVIEW — read both, confirm distinct fact patterns |

## 5. Verdict

TEST scenarios with an exact or normalised duplicate are REJECTED and must be rewritten before this benchmark is used for anything. Semantic-similarity and template-cluster flags are NEEDS_REVIEW, not automatic rejections — provision overlap and topical similarity are legitimate; only genuine scenario/fact-pattern duplication is disqualifying. Each flagged pair should be read by a human or a separate adversarial reviewer before the TEST split is frozen.