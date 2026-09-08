# Last checkpoint

Completed: runnable package, 40 DEV scenarios, 20 test candidates, 12 fixed follow-ups, 161 base evidence requirements, judging/evaluation/controller implementation, tests, source-side alias tools, documentation, schemas and result-report scripts.

**Update 2026-09-07 (this session):** Steps 1-3 of START_HERE.md executed for real, against the actual repository:
- `pip install -e '.[dev,plots,diagnostics]'` — clean install via the repo's own `.venv-embed` interpreter.
- `pytest -q` — **61 passed**, 0 failures.
- `python -m prw validate-data` — `STRUCTURAL_CHECK_PASS`, n_dev=40, n_test=20.
- `scripts/smoke_pipeline.py` — ran offline as designed (fixture labels, zero network calls); output at `validation/smoke/smoke_fixture_results.json`. Confirmed: these numbers are fixture-only and are NOT reported as procurement results anywhere.
- `scripts/check_adapter.py`, run against the real backend (`PRW_REPO_ROOT` pointed at the actual `procurement-kg-rag` checkout, live `state/chunk_index_merged.sqlite3`, live Qdrant collection `chunks__bge_m3__merged`): **no interface mismatch** — `search_signature`/`two_lane_signature` match the production `ChunkRetriever.search()`/`search_two_lanes()` exactly (confirmed independently against `chunk_retrieval.py` itself in a parallel evidence-gathering pass this session). No adapter patch was needed.
- First real DEV pilot against the live backend: `prw run --system hybrid` and `--system legal_static` on the full 40 `data/dev/scenarios.jsonl`, snapshot label `pilot_2026-09-07`. Both completed cleanly (40/40 rows each, `runs/dev/hybrid/runs.jsonl`, `runs/dev/legal_static/runs.jsonl`). Spot-checked output is genuine, not a fixture: real `chunk_id` (e.g. `UKPGA_2023_54__NODEV1__CH_00023`), real `citation`, real `content_sha256`, real `source_url`, real fusion `score` — matches the live corpus exactly.

**This resolves the "live backend compatibility" item** from the prior checkpoint's unresolved list — it is no longer unresolved; it is now verified working.

**Update 2026-09-07 (continued, same session) — benchmark unification and 3-scenario pilot:**

- `evaluation/final_retrieval_benchmark/` (a separate, independently-built 60-scenario benchmark
  from this same session: 40 dev/20 test, every gold citation corpus-verified, 0 exact/normalised/
  semantic-similarity duplicates between splits) is now the benchmark of record for this
  package. Converted to this package's own schema (`evaluation/final_retrieval_benchmark/
  workbench_schema/{scenarios,requirements}_{dev,test}.jsonl`) with NO change to wording,
  requirement content, or split membership — verified via strict `jsonschema` validation against
  `schemas/scenario.schema.json`/`requirements.schema.json` AND via this package's own
  `prw validate-data` (`STRUCTURAL_CHECK_PASS`, n_dev=40, n_test=20, 0 errors). Full conversion
  method and field-by-field mapping recorded in
  `evaluation/final_retrieval_benchmark/WORKBENCH_INTEGRATION_NOTES.md`.
- **Compatibility check found a real mismatch, acted on correctly, not papered over:** the
  benchmark's own prior standalone retrieval outputs (`retrieval_runs/config_*.jsonl`) do NOT
  match this package's `configs/retrieval.json` (candidate_depth 100 vs 50, per-lane depth 20 vs
  50, final budget 10-total-via-5/5-quota vs up to 100, graph_fanout 20 vs 40) or its query
  construction (`user_message` = scenario_text+query concatenated, vs a bare query field). Per
  instruction, those standalone outputs are **not reused** for this package's comparisons; they
  remain a separate, validly-scoped experiment under their own settings only.
- Ran a **3-scenario DEV pilot** (`data/pilot3/`: DEV003 "straightforward legal"/standstill,
  DEV040 "compound"/termination, DEV030 "practical guidance"/KPIs) for the two free static
  systems (`hybrid`, `legal_static`) — both completed cleanly against the live backend
  (`runs/pilot3/{hybrid,legal_static}/runs.jsonl`, 3/3 rows each). **`planned_multisearch` and
  `adaptive` were NOT run** — `prw run` itself refuses both without `--allow-network`, and no
  paid call has been made or authorised yet.
- **A genuine adverse finding surfaced and is retained, not discarded:** PA2023 s.51 (the actual
  gold provision for DEV003) is absent from the top 30 `legal_static` candidates, and — checked
  independently — also absent from the separate standalone benchmark's full top-50 under
  `hybrid_priors`, lexical-only, and dense-only individually. Confirmed s.51 is live/unfiltered
  in the corpus, so this is a genuine candidate-generation miss common to both pipelines for
  this query's wording, not a configuration artefact. Full detail:
  `results/pilot3/PILOT_REPORT.md`.
- **Dry-run cost check actually run** (`prw judge-bundles`, no `--allow-network`, on the 2
  completed static systems x 3 scenarios = 6 bundles): real tool output
  `{"bundles": 6, "minimum_requests": 18}`. Extrapolated to all 4 systems (12 bundles): 36
  minimum judge requests before adjudication. Model configuration prepared for all 5 slots
  (controller/generator/judge_a/b/c) plus adjudicator, all pointed at the one accessible,
  already-validated endpoint (`gpt-4o-mini` via this repo's own `.env` key) — explicitly
  disclosed as a **repeated-model configuration**, not genuine judge diversity, since no second
  model/provider was available this session.
- **Proposed, not yet approved:** per-job request caps totalling 95 (`planned_multisearch`=15,
  `adaptive`=30, bundle judging=50), plus an estimated-cost calculation (~$0.05-$0.15 for all
  three jobs combined, derived from this session's own measured per-token cost on a 5,895-item
  judging job) and a requested dollar ceiling of **$2.00** for the pilot. **Awaiting explicit
  author approval of this ceiling before any `--allow-network` call is made.**

**Update 2026-09-07 (continued) — $2.00 ceiling approved; paid pilot jobs run; definitive
bundle-judging outcome:**

- Author approved the proposed $2.00 ceiling. `planned_multisearch` and `adaptive` retrieval
  ran with `--allow-network` on all 3 pilot scenarios: 3 model calls/~504 tokens and 8 model
  calls/~71,648 tokens respectively, both well under their proposed caps (15, 30).
- **Positive finding, retained:** PA2023 s.51 (DEV003's gold provision, missing from
  `legal_static` top-30 and from the standalone benchmark's own top-50 under 3 separate configs)
  is recovered by both query-decomposition systems — rank 20/80 (`planned_multisearch`), rank
  7/68 (`adaptive`) — via explicit sub-query decomposition.
- **Adverse finding, retained with equal weight:** `adaptive`'s controller produced validation
  errors in **all 3 of 3** pilot scenarios ("Planner invented a scenario fact", "Observer cited
  nonexistent evidence"), correctly caught by the package's own harness (`COMPLETED_WITH_FALLBACKS`),
  not silently accepted.
- **Bundle judging (Task 6) attempted 3 times, succeeded 0 times.** All 12 bundles (4 systems x
  3 scenarios), `--max-requests 50`: attempt 1 failed `Bundle support quote cannot be verified`
  (3 req), attempt 2 failed a different error `Bundle judge changed requirement set` (3 more
  req, 6 total), attempt 3 failed with the SAME error as attempt 1 (3 more req, 9 total). Every
  individual API call itself succeeded (`model_events.jsonl`: 9/9 `status: success`) — all 3
  failures are the harness's own post-hoc validation of the judge's JSON output, not
  network/auth/budget errors. **Stopped retrying after 3 attempts** (41 of 50 approved requests
  unused) rather than continue burning budget chasing an elusive pass. Reported plainly in
  `results/pilot3/PILOT_REPORT.md` §8 as a genuine, reproducible `gpt-4o-mini` compliance
  problem with this package's bundle-judging output contract — not a coding error, not
  concealed, no placeholder/fabricated score substituted. **No combined-bundle-sufficiency
  result exists for any of the 12 pilot bundles.**
- Full detail, actual token/request counts, and the definitive per-attempt table: 
  `results/pilot3/PILOT_REPORT.md` §7-9.

**Update 2026-09-07 (continued) — v2 contract repair, rerun, and a new higher-priority finding:**

Per explicit instruction, the two v1 contract bugs were fixed narrowly (`prw/controller.py`,
`prw/bundles.py`, `prw/cli.py::cmd_bundles`), without touching retrieval ranking, the benchmark,
or the existing evaluation-definition formulas in `prw/metrics.py`. Full detail:
`results/pilot3_v2/PILOT_REPORT_V2.md`. v1 outputs (`runs/pilot3/`, `judgments/pilot3/bundles/`)
were preserved untouched; v2 outputs are under `runs/pilot3_v2/`, `judgments/pilot3_v2/bundles/`.

- **Fact-invention eliminated**: "Planner invented a scenario fact" went from 2 of 3 scenarios
  (v1) to 0 of 3 (v2), by giving the planner a harness-extracted, immutable fact-ID list to
  reference instead of asking it to reproduce scenario text.
- **Evidence-hallucination reduced but not eliminated**: "Observer cited nonexistent evidence"
  went from 3 of 3 scenarios (v1) to 1 of 3 (v2, DEV003 only) after switching to bare chunk-id
  citations (no quote reproduction required).
- **Bundle judging: 11 of 12 bundles now produce a usable judgment (v1: 0 of 12)**, via a
  positional `{"judgments":[...]}` array (harness attaches requirement_id, so a changed
  requirement set is now structurally impossible) plus a bounded one-repair loop. 1 bundle
  (`DEV040`/`legal_static`) still fails even after repair ("Unknown supporting chunk id") — not
  retried further, logged as a genuine residual failure.
- Retrieval rankings for `hybrid`/`legal_static` reconfirmed byte-identical to v1. s.51 recovery
  by `planned_multisearch`/`adaptive` reconfirmed. Total v2 paid usage: 56 requests / ~375k
  tokens, well inside the existing $2.00 pilot ceiling.
- **New finding, more consequential than the two bugs this pilot fixed**: spot-checking 3 of the
  11 successfully-judged bundles found the bundle judge can produce a schema-valid, high-
  confidence SATISFIED verdict that is substantively wrong — `legal_static`/DEV003/REQ1 cited
  PA2023 **s.17** (preliminary market engagement, unrelated) as satisfying the standstill-period
  requirement; `planned_multisearch`/DEV003/REQ1 wrote a substantively correct rationale about
  s.51 in its own words but did not actually cite chunk s.51 among its supporting IDs despite it
  being present in the bundle at rank 12 (apparent reliance on memorized legal knowledge rather
  than the supplied evidence, which the prompt explicitly instructs against). A third spot-check
  (`adaptive`/DEV030, KPI requirements) found genuinely correct grounding (s.52, s.71, matching
  this project's own corpus-verified gold). **Neither the v1 nor the v2 judge contract can
  structurally catch this class of error** — validation only confirms a cited chunk_id exists in
  the bundle, never that the citation is topically entailed by the requirement. This is now the
  single most important open question before trusting any bundle-judge coverage number at scale.
- Per the pilot's own acceptance criteria, this has **not fully passed**: 11/12 not 12/12 bundles,
  plus the new substantive-accuracy finding above. Full DEV/TEST execution should not proceed
  until the author has decided how to handle both.

**Update 2026-09-07 (continued) — bundle sufficiency demoted, primary metrics redefined, controller frozen:**

Per explicit author decision (in response to the sec-6 finding above): bundle-judge development is
stopped; `results/pilot3_v2/` left unchanged (not touched further). `docs/RESEARCH_PROTOCOL.md`
updated: bundle requirement coverage relabeled exploratory; pooled passage relevance (workbench
`prw judge`/`evaluate`) + strict verified target retrieval are now primary. A standing caveat was
added: no LLM-judged label here validates topical entailment between a citation and its
rationale, only that the cited id exists.

- **New, judge-independent metric implemented and run**:
  `evaluation/final_retrieval_benchmark/strict_target_recall.py` — Recall@5/@10, scenario-
  complete@10, MRR against corpus-verified essential-evidence chunk_ids only, zero LLM
  involvement. Ran immediately (does not depend on the still-running judging job). Result across
  all 60 scenarios, 0 unresolved targets: best config (`F_two_lane`) strict_recall_10=0.264,
  scenario_complete_10=0.133 -- low in absolute terms, consistent with the known candidate-
  generation misses (e.g. DEV003 s.51) already documented. Full output:
  `evaluation/final_retrieval_benchmark/metrics/strict_target_recall.json` (+
  `strict_target_recall_per_scenario.jsonl`).
- **Controller/config freeze checkpoint recorded** (development-discipline freeze, distinct from
  the later pre-TEST `prw freeze`): `research_state/controller_freeze_2026-09-07.json` hashes
  `prw/controller.py`, `prw/bundles.py`, `prw/adapters.py`, `prw/metrics.py`, `prw/contracts.py`,
  `configs/retrieval.json`, `configs/models.json` as of this point. No further prompt or
  validation-logic tuning should happen without updating this record and stating why.
- **Standalone benchmark's own 5,895-item judging job** (unrelated to workbench bundle judging;
  feeds `strict_target_recall.py`'s complement, the LLM-judged pooled metrics in
  `compute_metrics.py`/`candidate_ceiling.py`/`error_analysis.py`/`make_figures.py`) is still
  running: 2,637/5,895 as of this update (~45%). Not yet complete -- those scripts have not been
  run against real complete data yet; will run the moment it finishes.
- **Not yet done, needs an explicit cost-ceiling decision before proceeding** (this is new,
  larger paid spend beyond the $2.00 pilot ceiling, which was scoped only to the 3-scenario
  pilot): running `hybrid`/`legal_static`/`planned_multisearch`/`adaptive` on the full 40-scenario
  DEV split (`evaluation/final_retrieval_benchmark/workbench_schema/scenarios_dev.jsonl`), then
  `prw pool`/`prw judge` for pooled passage relevance at that scale, then (after author review)
  `prw freeze` + a single TEST execution on the 20-scenario test split. See the author's next
  response for the DEV-stage cost approval; the pooled-judging cost will be measured exactly
  (not estimated) via `prw pool`'s own deterministic output once DEV runs exist, before spending
  on that stage; TEST-stage approval, including the standing self-authorship conflict-of-interest
  note (this session wrote the TEST scenarios/gold), is deferred until DEV review is done.

**Update 2026-09-07 (final) — full pipeline complete: static benchmark finalized, DEV
consolidated, frozen TEST executed once, thesis-ready outputs produced.**

All of `results/final/` is now populated: `STATIC_BENCHMARK_FINAL_REPORT.md`,
`MATCHED_DEV_FINAL_REPORT.md`, `TEST_FINAL_REPORT.md`, `CASE_STUDIES.md`,
`MANUAL_EVALUATION_AUDIT.md`, `FINAL_THESIS_FINDINGS.md`, `FINAL_FREEZE.json`,
`FINAL_RESULTS_TABLE.csv`, `PER_SUITE_RESULTS.csv`, `PAIRWISE_STATISTICS.csv`,
`CONTROLLER_DIAGNOSTICS.csv`, `figures/*.png`. Headlines: H1 (legal_static > hybrid) confirmed
significant on both DEV (p=1.1e-05) and TEST (p=0.0215). H2 (adaptive > legal_static) not
supported on either (DEV exact tie; TEST +0.176 not significant). H3's essential control
(adaptive vs planned_multisearch) shows no significant difference on either (p=0.375 DEV,
p=0.6875 TEST) -- the most robustly reproduced null result in the project. TEST was executed by
this same session (self-authorship disclosure recorded verbatim in `FINAL_FREEZE.json` and
`TEST_FINAL_REPORT.md`, per explicit author instruction to proceed with disclosure rather than
conceal it). Per instruction: **experimental development is now stopped.** No further retrieval
models, graph relations, controller actions, benchmarks, tuning, or evaluation rubrics should be
added. The next phase is thesis writing only, drawing on `results/final/`.

Next exact action:
1. ~~Unpack, install, test, check_adapter, small DEV pilot.~~ DONE.
2. ~~Unify the two datasets; verify config/budget compatibility.~~ DONE — mismatch found and
   correctly handled (not reused), per `WORKBENCH_INTEGRATION_NOTES.md`.
3. ~~Prepare a 3-scenario DEV pilot on the two free static systems.~~ DONE.
4. ~~Await dollar-ceiling approval.~~ DONE — $2.00 approved.
5. ~~Run the 3 remaining pilot jobs at the proposed request caps.~~ DONE, v1. ~~Fix the two
   reported contract bugs and rerun as v2.~~ DONE — see the v2 update above and
   `results/pilot3_v2/PILOT_REPORT_V2.md`. **Decision point for the author, not an in-progress
   task:** the v2 pilot did not fully pass its own acceptance criteria (11 of 12 bundles, not 12
   of 12; and a new, more consequential judge substantive-accuracy finding — schema-valid but
   factually wrong SATISFIED verdicts in 2 of 3 DEV003 spot-checks). Before any further bundle-
   judging spend or a scale-up to the full 40/20 DEV/TEST split, the author needs to choose: (a)
   accept both residual gaps as disclosed limitations and proceed anyway with coverage numbers
   explicitly caveated as unverified, (b) authorise a further, separately-scoped harness change
   to check topical entailment between a judge's citation and its rationale (not just chunk_id
   existence) before trusting SATISFIED verdicts, (c) fall back to pooled passage judging/nDCG
   (already mentioned as an optional addition in the original handoff) as the primary metric
   instead of bundle sufficiency, or (d) commission a human spot-check pass over more than the 3
   bundles checked so far. No further bundle-judging or scale-up spend proceeds without one of
   these explicit directions, per the standing instruction not to redesign the controller or
   evaluation metrics unilaterally.
6. Finalize method settings before the separate evaluator reviews/freezes/executes the test
   stage. The coding/tuning agent (this session) has read the full text and gold of all 20 TEST
   scenarios while constructing them — it therefore cannot itself serve as the "separate
   evaluator process" the freeze step calls for; a genuinely independent process (a different
   session or a human) is needed for that step.
7. Separately, the standalone `evaluation/final_retrieval_benchmark/` LLM judging job (its own,
   already-scoped 5,895-item candidate-pool judging, unrelated to the workbench's bundle
   judging) remains running in the background: 1,285/5,895 judged as of this update, up from
   957/5,895 previously checked. Not yet complete; no action needed until it finishes, at which
   point `compute_metrics.py`/`candidate_ceiling.py`/`error_analysis.py`/`make_figures.py` run
   against its output.

Do not read data/test_sealed/build_dataset_source.py during policy tuning: it contains the complete authoring source, including test cases. Tests and validation may check hashes/counts without placing test text into a model's development prompt.

Unresolved, intentionally not fabricated: real silver labels (`judge-bundles` was run 3 times against the paid budget and failed all 3 times on harness-side output validation — see above; zero bundle-sufficiency labels exist for the pilot); corpus sufficiency; independent legal reference excerpts; model costs/availability beyond the single `gpt-4o-mini` endpoint validated this session; expert legal validity; genuine judge diversity (only one model family is currently configured/accessible). Measured performance gains for `planned_multisearch`/`adaptive` retrieval ARE now available (s.51 recovery, both systems) alongside a real adverse controller-hallucination finding for `adaptive` (3/3 scenarios) — these are resolved, not pending.

Do not regenerate a whole dataset, repeat the earlier 150/150 wrapper construction or rewrite the thesis around unexecuted results.
