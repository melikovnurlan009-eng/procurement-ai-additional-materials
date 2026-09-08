# Missing / Unavailable Artifacts

Stated plainly, per file, so no gap is silently implied to be covered.

## 1. Procurement Pathway discovery crawler (source code)

**CORRECTED 2026-09-08 -- an earlier version of this document wrongly stated this crawler was
"genuinely unavailable."** That was a research error in the earlier audit pass: the search for
it was limited to filenames containing "pathway" or "crawl" and a few known output-directory
names, and missed the actual crawler, which lives under a differently-named path. This was
caught and corrected after the author pointed out that an end-to-end crawling script does exist
in the project and had been iterated on multiple times.

**Status: the discovery crawler DOES exist and is now included.** It is
`code/scrapers/procurement_doc_counter/count_documents_relevance.py` (969 lines, with its own
`README.md` and `seeds.json`, all now included in this bundle). It is a genuine, general-purpose
link-following crawler (`requests` + BeautifulSoup, explicit `max_depth`/`max_pages_per_root`
bounds, a `crawl_root()` traversal loop) with dedicated handling for
`group_id == "PROCUREMENT_PATHWAY"` (same-domain crawl with procurement-relevance filtering and
bounded depth, per its own README's "Traversal policy" section). Running it against `seeds.json`
(58 source roots) is what produced the raw crawl output preserved in the project's
`crawl_v2_relevant/` directory (dated 2026-08-25), which itself contains 1,950 raw
Procurement-Pathway rows.

**What is still missing, precisely**: the *final* manifest included in this bundle,
`corpus_manifests/procurement_pathway_urls.jsonl` (1,690 URLs), is dated two days later
(2026-08-27) than the raw crawl and carries additional fields the raw crawler's own output does
not produce (`topic_slug`, `procurement_stage`, `include_decision`, `content_role`,
`same_topic_stage_variant_count`, `same_topic_other_stages`). An exhaustive grep across every
`.py` file in the repository for these exact field names found no script that produces them --
only the crawler's raw output and this later, already-curated file survive. So a **downstream
curation/refinement step** (which took the raw 1,950 crawled pages down to a de-duplicated,
topic-annotated, per-page-included/excluded 1,690) ran between the crawl and the final manifest,
and the code for that specific step is what is actually unrecoverable, not the crawl itself.

**Precise wording to use**: *"The package includes the actual discovery crawler
(`code/scrapers/procurement_doc_counter/`) used to traverse this source family, and its raw
output is independently reproducible by re-running it against the included seed list. A further
curation/annotation step then refined the raw crawl output (1,950 pages) into the final,
topic-annotated manifest included here (1,690 pages); the code for that specific refinement step
does not survive in the repository, so the exact final manifest cannot be regenerated
byte-for-byte from the raw crawl alone, though the raw discovery process itself can be rerun."*
Do not claim the crawler itself is unavailable -- it is included as of this correction. Do not
claim the *entire* pipeline including the curation step is reproducible -- that specific step is
not.

## 2. Exact historical build environment for corpus construction

**Status: genuinely unavailable.** No `pip freeze` or equivalent was captured at the time the
corpus was actually built (ingest timestamps 2026-09-03 to 2026-09-06). `environment/
environment_notes.md` documents the *currently verified compatible* environment (captured
2026-09-07) as a clearly labelled substitute, not a historical record.

## 3. Embedding model exact revision/commit hash

**Status: genuinely unavailable.** `index_manifest` records the model name (`BAAI/bge-m3`) and
dimensionality (1024) but no HuggingFace revision hash or commit was logged by the ingest
scripts. If `BAAI/bge-m3` has since been updated upstream, exact embedding reproduction cannot be
guaranteed from the model name alone.

## 4. Per-item cache/checkpoint directories (deliberately excluded, not "missing")

These are not unavailable -- they were deliberately excluded as redundant. Every one is fully
recoverable in content from the consolidated files that *are* included (`runs.jsonl`,
`qrels_silver.jsonl`, `judgments_raw.jsonl`), which is what every downstream analysis script in
this bundle actually reads.

| Excluded directory | Purpose | Original size | Reason for omission | How to restore |
|---|---|---:|---|---|
| `procurement_research_workbench_v1/runs/{dev_scale,test_final}/*/checkpoints/` | per-scenario cached controller output, one JSON file per scenario | ~27 MB | Fully redundant with that same system's consolidated `runs.jsonl` in the same original directory, which concatenates every checkpoint in order | Not needed for any analysis in this bundle. If the original project directory is available, these are the per-scenario files `runs/<split>/<system>/checkpoints/<SCENARIO_ID>.json` |
| `procurement_research_workbench_v1/judgments/{dev_scale,test_final}/pointwise/{final_cache,raw_cache,requests_cache}/` | per-candidate/per-judge-call cached JSON | ~28 MB | Fully redundant with `judgments_raw.jsonl` and `qrels_silver.jsonl` in the same directory, which already consolidate every judged item | Not needed for any analysis in this bundle |
| `evaluation/final_retrieval_benchmark/_judge_cache.jsonl`'s own internal structure is NOT excluded -- it is included in full (it is itself already the consolidated cache) | -- | -- | -- | -- |

No SHA-256 is given for these excluded directories as a whole (they contain thousands of small
files); their content is fully represented, file-for-file, in the consolidated JSONL files that
are included, and the original project's own directory structure (documented in
`TECHNICAL_APPENDIX.md` section 4) shows exactly where they would sit if restored.

## 5. Independent (non-self-authoring) execution of the TEST split

**Status: a methodological limitation, not a missing artifact.** The TEST split was constructed,
frozen, and executed by the same process (this session). This is disclosed in
`results/final_reports/FINAL_FREEZE.json`'s `test_inspection_disclosure` field and restated in
`TEST_FINAL_REPORT.md`. No independent-evaluator artifact exists to include, because none was
produced -- this is stated as a limitation, not corrected by omission.

## 6a. Which scraper version actually produced the live corpus (legislation family)

**Status: cannot be proven, only inferred from timestamps.** `code/scrapers/legislation/`
contains four scripts: `group_a_legislation_scraper.py` (declares `VERSION = "1.0.0"`, dated
2026-08-27 23:09), `group_a_legislation_scraper_v2.py` (`VERSION = "2.0.0"`, 2026-08-27 23:35,
26 minutes later), `group_a_legislation_scraper_v4.py` (`VERSION = "4.0.0"`, 2026-08-29 21:52; no
v3 was ever found), and `scrape_missing_legislation.py` (2026-09-05 13:34, a later supplementary
patch run). Neither the corpus database nor its ingest reports
(`state/ingest_legislation_report.json`) record which scraper version produced the raw pages
they ingested -- there is no version field anywhere in the pipeline linking a document back to
the specific script that fetched it.

The only evidence available is that the corpus database's own final build timestamp
(2026-09-06 19:07) is closest to `scrape_missing_legislation.py` (Sep 5) and
`group_a_legislation_scraper_v4.py` (Aug 29), while v1/v2 (Aug 27) are 8-10 days earlier and
read as earlier, superseded iterations kept for audit-trail history rather than the version
actually run last. **This is an inference from file timestamps, not a proven fact** -- do not
represent v4 as definitively "the" version that produced the live corpus; state it as the
best-supported candidate, with v1/v2 as historical/superseded and `scrape_missing_legislation.py`
as a later supplementary run, exactly as this note does.

All four files are included in the bundle regardless, so an examiner can inspect the actual
progression rather than being handed an unexplained single "final" file that erases that history.

## 6. Raw crawl logs, timestamps, and per-request source hashes for most source families

Beyond the ingest-stage report files already included (`ingest_legislation_report.json` etc.),
per-URL fetch timestamps and per-page content hashes at acquisition time were not found to be
logged by the scraper scripts that do survive in the repository (`scrapers/*.py`). Acquisition
dates as precise as "which day a given page was fetched" are not recoverable; only the ingest
(parsing/chunking) stage timestamps are.
