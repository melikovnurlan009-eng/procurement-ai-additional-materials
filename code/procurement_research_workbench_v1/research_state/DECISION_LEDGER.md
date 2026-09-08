# Design decision ledger

| Decision | Reason | Implemented check | Empirical status |
|---|---|---|---|
| Separate public scenarios and private requirements | Prevent answer-key access by controller | Runtime allowlist and rejection tests | Software-tested |
| Judge all competing outputs | Credit valid evidence not prelisted as gold | Union pool and novelty test | Pipeline tested; real labels unrun |
| Separate bundle sufficiency from passage relevance | Complementary excerpts can jointly answer a requirement | Three bundle judges with cited spans | Pipeline tested; hypothesis unmeasured |
| Do not equate grade >=2 with sufficiency | Supporting evidence may omit a decisive condition | FULL requirement checks | Software-tested |
| Add planned multi-search baseline | Separate feedback benefit from extra query budget | Same planner and operation cap, no observer | Software-tested |
| Total final budget 10, not 10 per lane | Prevent apparent gains from doubling evidence | Shared selector and cap tests | Software-tested |
| Three common-rubric judge slots | Assess consistency without varying the task | Isolated payloads, same rubric | No actual judge agreement measured |
| Adjudicate support/applicability disagreement | Majority can change completeness incorrectly | Disagreement queue tests | Software-tested |
| Stop on credential/request-budget failure | Avoid static fallback being claimed as adaptive completion | Fatal errors propagate | Software-tested |
| Alias proposals use sources only | Avoid mining evaluation questions into index | Input allowlist and source quote validation | Software-tested; performance unrun |
| Label-aware oracle is diagnostic only | Separate pool availability and constrained ranking opportunity | No runtime import/use of evaluator labels | Solver fixture tested |
| Independent reference required for legal score | Retrieved self-consistency is not legal truth | Legal correctness null without reference text | Software-tested |
