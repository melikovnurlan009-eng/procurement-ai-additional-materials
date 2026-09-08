# Manual Evaluation Audit

**Framing note, stated once here and binding for how this file is cited anywhere else in this
project or the thesis:** this is not independent human verification. It is a targeted
quality-assurance pass conducted by this session (an LLM agent) re-reading actual saved retrieval
output, actual saved judge output, and actual chunk citations against the actual requirement
text, applying its own judgment. The accurate phrasing for the thesis, per the standing
instruction: **"LLM-generated silver judgments were supplemented by targeted manual quality
assurance"** -- read "manual" there as "a targeted, deliberate secondary pass," not as "performed
by a human being." No claim in this file or elsewhere should say LLM labels were human-verified,
because that would not be true.

## Status at time of writing

DEV-stage cases plus TEST cases, both included below. TEST was executed once, frozen, by this
same session -- see `TEST_FINAL_REPORT.md`'s own methodology disclosure at its top, which applies
equally to every TEST case recorded here.

## Cases inspected

### 1. DEV003 -- PA2023 s.51 candidate-generation/decomposition-recovery case

- **Scenario**: DEV003, standstill-period question.
- **Retrieved citation**: `planned_multisearch` rank 3 = PA2023 s.51 (`UKPGA_2023_54__NODEV1__CH_00051`);
  `adaptive` acquired-rank 16 (not in final top-10, same chunk); `hybrid`/`legal_static` do not
  retrieve it at all.
- **LLM label**: not directly applicable here -- this is a candidate-generation fact (does the
  chunk appear at all), independently confirmed against the live corpus (chunk exists,
  unfiltered, not superseded -- `sqlite3` query against `state/chunk_index_merged.sqlite3`,
  reconfirmed this session).
- **Assessment**: confirmed correct. s.51 genuinely is PA2023's mandatory 8-working-day
  standstill provision; its absence from both static systems and its recovery-but-partial-loss
  in the two decomposition systems is a real, verifiable retrieval fact, not a judge artifact.
- **Confirmed / disputed**: confirmed.
- **Reason**: independently checked against the corpus directly, not against an LLM judgment.

### 2. DEV013 -- shared regression case (both paid systems worse than legal_static)

- **Scenario**: DEV013, `vocabulary_mismatch` suite.
- **Retrieved citations, top-3**: `legal_static`: PR2024 reg 31, PA2023 s.58, PA2023 s.28.
  `adaptive`: PR2024 reg 18, PA2023 s.20, PA2023 s.19. `planned_multisearch`: PA2023 s.19,
  an EU Official Journal document (`L_2014094EN...`), PCR2015 reg 30.
- **LLM label**: `legal_static` scored requirement_coverage 1.00 on this scenario;
  `planned_multisearch` and `adaptive` both scored 0.00.
- **Assessment**: the three systems' top results cite genuinely *different* provisions, not the
  same provision judged differently -- this is a real retrieval-content difference, not a
  labelling artifact. `legal_static`'s single query lands on reg 31/s.58/s.28, which the pooled
  judge treated as sufficient; the decomposed systems' sub-queries land on adjacent but different
  sections (s.19/s.20, and one EU-era document for `planned_multisearch`) that did not satisfy
  the judge. Plausible mechanism (not confirmed by a dedicated ablation): decomposition
  fragmented a single query that already worked, redirecting search away from the correct
  section.
- **Confirmed / disputed**: confirmed as a genuine retrieval-content difference, not a judge
  error. The "why" (fragmentation hypothesis) is disputed/unconfirmed and stated as such in
  `CASE_STUDIES.md`.
- **Reason**: citations were pulled directly from `runs/dev_scale/*/runs.jsonl` and cross-checked
  by eye against each other; no independent legal-correctness check of which single section is
  actually most on-point was performed (would require expert legal review, out of scope here).

### 3. DEV034 -- adaptive-only regression, representative wrong-authority-type failure

- **Scenario**: DEV034, `guidance` suite. `hybrid`, `legal_static`, `planned_multisearch` all
  reach 1.00 coverage; `adaptive` reaches 0.00.
- **Retrieved citations, top-3, `adaptive`**: an EU Official Journal XML document
  (`L_2014094EN.01006501.xml`), a `procurementportal_part3` PDF chunk, and "The Construction
  Playbook" guidance document. **`legal_static`'s top-3 for comparison**: PA2023 s.108, s.2, s.29
  -- all direct statutory provisions.
- **LLM label**: `adaptive`'s bundle for this scenario was judged as not satisfying the
  requirement (0.00 coverage); `legal_static`'s was judged as satisfying it (1.00).
- **Assessment**: this looks like a genuine representative case of `adaptive`'s query
  decomposition drifting toward lower-authority, more tangential sources (an EU directive
  document that is very unlikely to be the controlling PA2023-era authority for a
  guidance-suite scenario, plus general portal/playbook material) instead of the specific
  statutory sections `legal_static`'s single pass reaches directly. This is a plausible,
  visible mechanism for the regression -- the LLM judge's 0.00 score for `adaptive` here looks
  substantively defensible on inspection, not an artifact of the judge contract fix.
- **Confirmed / disputed**: confirmed -- the judge's 0.00 for `adaptive` on this scenario is
  supported by what was actually retrieved.
- **Reason**: direct citation comparison between systems for the same scenario; the qualitative
  difference in source authority type (EU directive / portal / playbook vs direct PA2023
  sections) is visible without needing the full passage text.

### 4. Statistically influential case -- `hybrid` -> `legal_static` H1 comparison

- Already the basis of §2 of `MATCHED_DEV_FINAL_REPORT.md` (21 wins, 15 ties, 1 loss, p=1.1e-05).
  Spot-checked one of the 21 wins directly at the source-data level (DEV003, DEV013, DEV034 all
  already covered above show `legal_static` doing at least as well as `hybrid`, consistent with
  the aggregate direction). No single win/loss pair beyond the three cases above was
  individually re-examined; the aggregate statistical result is treated as the primary evidence
  for H1, not a claim that every one of the 21 wins was individually eyeballed.

### 5. TEST019 -- decomposition-recovery replication (statutory suite)

- Covered in full in `CASE_STUDIES.md`. `legal_static` top-1 = PA2023 s.50 (adjacent, wrong);
  `planned_multisearch`/`adaptive` top-1 = PA2023 s.51 (correct), matching DEV003's mechanism.
- **Confirmed / disputed**: confirmed. Independently checked against the corpus (s.51 exists,
  live, correctly the standstill provision), same method as the DEV003 check.

### 6. TEST014 -- representative wrong-regime failure (`planned_multisearch`)

- **Scenario**: TEST014, direct-award-after-failed-competitive-tender question (two
  requirements: the statutory route, and the pre-award transparency notice step).
- **Retrieved citations, top-3**: `legal_static`: PA2023 s.54, s.19, a PA2023 guidance
  collection chunk. `adaptive`: PA2023 s.54, s.43, s.19. **`planned_multisearch`: Public
  Contracts Regulations 2015 reg 29 (x2, different sub-chunks), then PA2023 s.19.**
- **LLM label**: `legal_static`=0.0, `planned_multisearch`=0.5, `adaptive`=1.0 requirement
  coverage.
- **Assessment**: PCR2015 is the pre-PA2023 regime; a scenario framed under the current regime
  being top-ranked to a PCR2015 regulation is a genuine wrong-regime retrieval, not a labelling
  quirk -- `planned_multisearch`'s decomposed sub-query for this scenario evidently drifted to
  the superseded regulatory text. `legal_static`'s and `adaptive`'s citations are all
  current-regime (PA2023), and are the substantively correct family of authority for this
  scenario. `legal_static` scoring 0.0 despite citing s.54 (the plausible right section) is worth
  a second look -- likely REQ2 (the transparency-notice procedural step) was not satisfied by any
  of its top-10 despite REQ1 being addressable by s.54; this was not separately re-verified
  passage-by-passage here.
- **Confirmed / disputed**: the wrong-regime characterisation of `planned_multisearch`'s result
  is confirmed. `legal_static`'s 0.0 score is plausible but not independently re-verified at the
  per-requirement level in this pass.
- **Reason**: citation family (PCR2015 vs PA2023) is directly visible from the `citation` field
  without needing full passage text; the coverage-formula internals were not re-derived by hand.

## What was not inspected (disclosed, not hidden)

- The bulk of the 726 pooled-DEV judgments and 5,895 standalone judgments were not individually
  re-read; the QA pass above targeted the cases explicitly called for (major wins/regressions,
  the DEV003 mechanism case) plus the ones the controller diagnostics flagged as regressions.
- No representative graph-recovery case was inspected -- `STATIC_BENCHMARK_FINAL_REPORT.md` §7
  found graph expansion has no statistically significant effect on this benchmark at all (4
  wins, 1 loss, 55 ties out of 60), so no single graph-recovery example was available to select
  as clearly representative rather than one of very few noisy individual differences.
- TEST-split examples across suites: pending Phase 4/5.
