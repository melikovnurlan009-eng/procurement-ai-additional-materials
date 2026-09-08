# Final Corpus Audit

Read-only, fact-finding audit of the corpus, its acquisition, parsing, chunking, graph
construction, and QA history, conducted by re-reading actual code, actual database contents, and
actual existing documentation. No corpus, crawler, parser, graph, retrieval system, benchmark or
evaluation logic was changed to produce this document; the two factual discrepancies found (both
count-staleness, section A) are reported, not silently fixed.

## A. Corpus snapshot identity

- **Git commit**: `79c488c7103078633159e26bdfe24e7410313821`, 2026-09-07 00:08:24 +0400.
- **Final SQLite database**: `state/chunk_index_merged.sqlite3` (274,874,368 bytes, last modified
  2026-09-06 19:07). Confirmed as the production snapshot by direct reference in
  `chunk_retrieval.py:53` (`DEFAULT_DB = "state/chunk_index_merged.sqlite3"`) and
  `procurement_research_workbench_v1/prw/adapters.py:106-108`.
- **Qdrant collection**: `chunks__bge_m3__merged` (from the same adapter default and the
  database's own `index_manifest` table).
- **Embedding model**: `BAAI/bge-m3`, 1024 dimensions, cosine distance, normalized vectors
  (`index_manifest`).
- **Corpus source dir**: `data/search_corpus_merged` (`index_manifest.corpus_dir`).
- **Source manifests / reports**: `state/ingest_legislation_report.json`,
  `state/ingest_pdf_chunks_report.json`, `state/ingest_structural_node_report.json`,
  `state/densify_graph_report.json`, `state/deduplicate_instruments_report.json` — all read and
  quoted in full below.

### Exact counts, this snapshot only

| Metric | Count |
|---|---:|
| Total document rows (`documents` table) | 2,078 |
| Total chunk rows (`chunks` table) | 27,558 |
| **Live/queryable chunks** (`filtered_out` empty AND `superseded_by` empty) | **22,042** |
| Total edge rows (`edges` table) | 27,600 |
| Edges: CONTAINS | 6,489 |
| Edges: HAS_CHUNK | 9,189 |
| Edges: REFERENCES | 7,159 |
| Edges: CROSS_REFERS_TO | 4,763 |

No formal `nodes` table exists in the final schema; document and legal-provision identity are
represented by the `documents` table and by `parent_node_id`/`parent_type` columns on `chunks`
respectively (see section E).

### Two discrepancies found and disclosed, not hidden

1. **The database's own `index_manifest` table is stale.** It records
   `chunks_indexed=8511, edges_indexed=27824`, dated `built_at=2026-08-30T20:48:42Z` — a build
   state that predates the later legislation/PDF/structural-node ingest passes (dated
   2026-09-05 to 2026-09-06 per the report files above). The manifest was never refreshed after
   those ingests. **Do not cite `index_manifest`'s row counts as current; use the direct
   `SELECT count(*)` figures in the table above.**
2. **`thesis_evidence/graph_statistics.json` was computed from the same stale source**
   (`data/search_corpus_merged/edges.jsonl`, which itself predates the live database by roughly a
   week — this staleness is self-flagged inside that very file). Its edge counts (27,824 total;
   HAS_CHUNK 9,408; REFERENCES 7,164; CONTAINS 6,489 — matches; CROSS_REFERS_TO 4,763 — matches)
   differ from the fresh count above by +219 HAS_CHUNK and +5 REFERENCES (both structural/small
   categories were fully consistent). Two independent audit agents queried the live database
   directly and obtained the same fresh counts, cross-confirming this finding. **Any thesis
   figure using edge counts should cite the fresh counts in this document, not
   `thesis_evidence/graph_statistics.json`'s edge-count numbers**, though that file's other
   content (connected-component statistics, `total_live_chunks_in_corpus: 22042`) matches
   directly and can still be cited.

### Historical corpus snapshots (not used in final evaluation)

| Database | Chunks | Documents | Edges | Built | Status |
|---|---:|---:|---:|---|---|
| `state/chunk_index.sqlite3` | 743 | 46 | 12,600 | 2026-08-29 | historical, superseded |
| `state/chunk_index_v2.sqlite3` | 959 | 46 | 12,817 | 2026-08-30 | historical, superseded |
| `state/chunk_index_merged.sqlite3.bak_pre_leg_ingest` | (not queried; backup file, pre-legislation-ingest) | -- | -- | 2026-09-06 09:36 | historical backup |
| `state/chunk_index_merged.sqlite3.bak_pre_pdf_ingest` | (not queried; backup file, pre-PDF-ingest) | -- | -- | 2026-09-06 03:40 | historical backup |
| `state/procurement_kg.sqlite3` | n/a (different schema: 132,398 `nodes` / 277,729 `edges`) | -- | -- | 2026-08-20 | **separate, older KG-construction pipeline; not wired into `chunk_retrieval.py`; not the final snapshot** |

`state/procurement_kg.sqlite3` deserves a specific caution: it implements a richer relation
vocabulary (`amends` 4,131 edges, `commences` 3,607 edges, `cites_legislation` 1,252 edges, and
17 further relation types) than the final `chunk_index_merged.sqlite3` graph. **These richer
relation types exist in the codebase's history but are not part of the final evaluated corpus's
graph** — do not describe the final corpus as having AMENDS/COMMENCES edges; it does not. This
older store also has no confirmed connection to the production retriever (`chunk_retrieval.py`
does not reference it), and its own `.env`-declared Qdrant collection
(`kg__bge_m3__text_focused_v1`) differs from the one actually used
(`chunks__bge_m3__merged`) — a further sign it is a superseded pipeline stage, not the final one.

## B. Source inventory

Full table: `CORPUS_SOURCE_INVENTORY.csv`. Summary by chunk-level `authority_class` (live chunks
only, `state/chunk_index_merged.sqlite3`):

| authority_class | live chunks |
|---|---:|
| OFFICIAL_GOVERNMENT_GUIDANCE | 8,850 |
| PRIMARY_LEGISLATION | 7,642 |
| OFFICIAL_WORKFLOW | 2,253 |
| PROFESSIONAL_INTERPRETATION | 1,630 |
| SECONDARY_LEGISLATION | 823 |
| OFFICIAL_REGULATOR_GUIDANCE | 530 |
| OFFICIAL_TECHNICAL_GUIDANCE | 165 |
| NON_AUTHORITATIVE_PROFESSIONAL | 149 |

By `source_kind`: PDF 9,546; LEGISLATION 8,341; BLOCKS 4,044; HTML 111.
By `legal_regime` (most non-legislation chunks carry no regime tag): PA2023 3,208; PCR2015 1,903;
PR2024 539; untagged 21,908.

## C. Data acquisition and source discovery

Every scraper script that exists in the current repository (`scrapers/*.py`, 9 files) is
**fixed-URL / non-recursive**. Several state this explicitly in their own code/docstrings:

- `scrape_associated_law_guidance.py`: `"NO recursive crawling"`, manifest field
  `"follow_links": False`.
- `scrape_competition_procurement_guidance.py`: same, `"follow_links": False`.
- `scrape_procurement_compliance_oversight.py`: `"This script deliberately DOES NOT: recursively
  crawl linked pages"`.
- `scrape_nsup.py`: single fixed page, `"follow_links": False`.
- `scrape_professional_procurement_sources.py`: `"recursive_html_crawl": False`; the one partial
  exception follows only PDF-class links found within one specific page's own body.
- `scrape_core_legislation_full.py`: `"recursive_external_crawl": False`; fetches up to 4
  candidate XML representation URLs per statute and selects the most complete.
- `scrape_procurement_policy_notes.py` / `scrape_procurement_act_guidance.py`: crawl one GOV.UK
  collection page to its own publication pages, then to those pages' document-attachment links
  only — no further traversal.

**`rescrape_procurement_journey.py` is not a discovery crawler.** It targets
`procurementjourney.scot` (a different site from `procurementpathway.civilservice.gov.uk`), and
its URL list is drawn from a SQL query against chunks already in the database
(`WHERE source_url LIKE '%/print/pdf/node/%'`) — it re-fetches known nodes in a different format,
with no traversal or discovery logic of its own.

### Procurement Pathway — the special-focus finding

`procurement_pathway_urls.jsonl` (1,690 distinct URLs, every row tagged
`discovery_relation: LIFECYCLE_STAGE_LINK`, spanning 459 distinct topic slugs across up to 17
lifecycle stages, URL patterns like
`.../lifecycle/plan/strategy-and-plan/` → `.../documents/best-practice/<topic>/<stage>`) and
`crawl_seed_counts.csv` (1,949 documents attributed to this seed) together prove that a genuine
recursive crawl of Procurement Pathway's lifecycle-stage child pages was actually performed, and
reached real depth (not a shallow fixed list).

**However: no script producing this file, or implementing this traversal, exists anywhere in the
current repository.** An exhaustive grep for the discovery-relation field name, for
`procurementpathway.civilservice`, and for the output directory names
(`crawl_A_official`, `crawl_B_bounded`, `crawl_output`, `crawl_v2_relevant`, `corpus_ingest*`,
`normalized_html_json_v2`/`v3retry`) across every `.py` file in the repository found only
downstream *consumers* of these outputs, never a producer. `crawl_v2_relevant/` even contains a
leftover `validate_corpus.py` but no crawler. This matches `reproducibility/
KNOWN_GAPS_baseline_v1.md`'s own, earlier, independently-recorded finding that "the acquisition
and parsing stage of baseline_v1 survives only as its output... cannot be rerun, audited or
version-matched" — the same gap, found again independently by this audit.

**This is a genuine, disclosed reproducibility gap, not an inferred one**: Procurement Pathway is
the single largest identified source family by discovered-URL count, and its acquisition method
cannot be rerun, audited step-by-step, or version-matched from this checkout. Whether the
strategy could systematically miss deep child pages cannot be answered from code, because the
code does not exist; the data alone (459 topics × up to 17 stages) suggests real depth was
reached, but this is not independently verifiable.

### Inclusion/exclusion logic actually implemented

`content_filters.py` (quoted, not paraphrased): universal drop rules for site chrome, Crown-
copyright/OGL boilerplate, cookie banners, contact blocks, phone-number lists, and trailing
filename artifacts; per-domain extra rules (e.g. Procurement Pathway drops "seek legal and
commercial advice" footer text, comment "57% LOW_VALUE"; procurementjourney.scot drops
lawyer-deferral sentences and route-navigation text, comment "29% LOW_VALUE";
procurementlawyers.org.uk drops association-news/biography content, comment "43% LOW_VALUE"); a
generic fallback drops any block under 45 characters with no heading and no legal-substance
keyword match. The module explicitly states its scope limit: LLM labelling found 21% GOOD / 56%
INCOMPLETE / 23% LOW_VALUE chunks corpus-wide; this filter addresses only the LOW_VALUE class —
INCOMPLETE (mid-sentence truncation from chunk-boundary placement) is explicitly left untouched,
"because it is caused by where chunk boundaries fall, not by what the scraper collected."

`deduplicate_instruments.py` found exactly 3 duplicate-instrument groups (the same legislative
instrument ingested twice via two different acquisition paths, e.g. a properly-parsed
`UKPGA_2023_54` alongside a generic raw-block scrape of the same statute's `/data.akn` URL) and
resolved them non-destructively via a `superseded_by` column, affecting 71 chunks total.

## D. Inclusion / exclusion criteria (what actually happened, not idealized)

Actual inclusion: content passed domain-specific scraping (per source family), survived
`content_filters.py`'s drop rules, and was not flagged as a duplicate by
`deduplicate_instruments.py` or the per-ingest hash-based dedup in
`ingest_legislation_chunks.py`/`ingest_pdf_chunks.py`. Actual exclusions recorded in the ingest
report files:

| Report | Kept | Dropped (dup/small/fidelity/other) |
|---|---:|---:|
| `ingest_legislation_report.json` | 7,752 | 397 dup-within, 669 too-small, 81 fidelity-failed, 1,147 flagged (not necessarily excluded) |
| `ingest_pdf_chunks_report.json` | 9,546 | 285 fidelity-failed, 98 dup-within, 9 dup-existing, 392 flagged |
| `ingest_structural_node_report.json` | 11 | 40 superseded (older duplicate structural chunks for the same 2 documents) |

**Important nuance**: "fidelity_failed"/"flagged" chunks are, per the ingest scripts' own
documented behaviour, **inserted, not discarded** — flagged as a status, visible and reversible,
not silently dropped. Only true duplicates and below-minimum-length chunks are excluded outright.

## E. Parsing and canonical representation

- **Legislation**: raw legislation.gov.uk XML in AKN (Akoma Ntoso) or CLML (Crown Legislation
  Markup Language) form, auto-detected by inspecting the root tag/namespace
  (`group_a_legislation_scraper_v4.py::detect_representation()`). A recursive tree walk assigns
  each node a `node_type`, `number`, `heading`, `text`, `eId`, `parent_id`, `depth`, `path`. CLML
  hierarchy, quoted from the parser's own docstring: `P1 → section/regulation, P2 →
  subsection/paragraph, P3 → paragraph/subparagraph, P4-P6 → deeper points; Part/Chapter/Schedule
  are structural containers`. The source XML's own `eId` is preserved and combined into
  `parent_node_id = f"{document_id}__{suffix}"`; citations are synthesized from instrument name +
  unit word + provision number.
- **PDF**: PyMuPDF (`fitz`) text extraction, page by page, text blocks sorted into reading order.
  Hyphenated line-break words are rejoined; likely-repeated headers/footers are flagged (not
  deleted, "a false positive silently deletes body text"); font-size-based structure inference is
  explicitly avoided ("a dropped line is unrecoverable downstream").
- **HTML**: BeautifulSoup, main content container selected by trying `.govspeak` →
  `.gem-c-govspeak` → `main` → whole-page fallback; script/style/nav/form/button/noscript tags
  removed; only visible flattened text is retained at this stage (headings/links are not stored
  as separate structured metadata by this specific extraction function).
- **Canonical representation**: the schema distinguishes DOCUMENT (the `documents` table),
  LEGAL_PROVISION (represented by `parent_node_id`/`parent_type` on `chunks`, plus the XML
  tree's own node records — the addressable legal-citation identity), and CHUNK (the `chunks`
  table itself, the retrieval unit, which may be smaller or larger than a single provision —
  long provisions are split, short ones merged). There is no separate Python dataclass named for
  each; the distinction lives in the SQL schema and foreign-key-like id fields.

## F. Chunking audit

Two structurally different LLM-touching chunking lanes, plus two non-LLM lanes, are all present
in the live corpus simultaneously:

| Method tag | Active (live) chunks | % of live corpus | LLM role |
|---|---:|---:|---|
| LLM_PDF_TEXT_V2 | 9,546 | 43.3% | LLM emits chunk **text** directly |
| LLM_LEG_TEXT_V2 | 7,715 | 35.0% | LLM emits chunk **text** directly |
| LLM_SEMANTIC_BOUNDARY_V1 | 4,388 | 19.9% | LLM selects **boundaries only**; text reconstructed by code |
| STRUCTURAL_NODE_V1 | 393 | 1.8% | no LLM; deterministic XML-tree walk |

**This is the single most important finding for section K/M**: the boundary-selection lane
(`LLM_SEMANTIC_BOUNDARY_V1`, ~20% of the live corpus) has a hard, code-enforced provenance
guarantee — `build_search_corpus.py`'s `stage_chunks()` reconstructs chunk text by slicing the
original immutable source blocks (`text="\n\n".join(b["text"] for b in selected_blocks)`) and
never reads a `text` field from the LLM's own JSON output; `validate_plan()` additionally rejects
any boundary plan that does not cover every source block exactly once, in order. The two
text-emission lanes (`LLM_LEG_TEXT_V2` + `LLM_PDF_TEXT_V2`, together **78.3% of the live
corpus**) have the LLM emit chunk text directly, verified only by a statistical shingle-overlap
fidelity check (5-token shingles, default minimum coverage 0.80) against the source window — and
chunks that fail this check are flagged (`fidelity_failed`) but **still inserted, not excluded**.
Both scripts' docstrings state the reason explicitly: broken/fragmentary PDF and some legislation
sources made boundary-selection produce up to 88% "INCOMPLETE" chunks, so a lower-guarantee,
higher-coverage method was deliberately chosen for those sources as a disclosed trade-off.

**Consequence for claims**: "the LLM selected boundaries but did not rewrite evidence text" is
verifiably true for ~20% of the live corpus and **not independently provable** for the remaining
~78% (fidelity-checked to ≥80% shingle overlap, not exactly reconstructed).

### Chunk length statistics (live chunks, characters)

count 22,042 · mean 1,327.3 · median 864 · p75 1,625 · p90 2,573 · p95 3,373 · p99 9,085 · min 29
· max 51,649.
`>1,500` chars: 6,183 (28.05%) · `>3,000`: 1,469 (6.66%) · `>5,000`: 573 (2.60%).

By chunking method (live chunks): `LLM_PDF_TEXT_V2` mean 1,400.7 / median 1,268.0;
`LLM_LEG_TEXT_V2` mean 518.3 / median 331.0; `LLM_SEMANTIC_BOUNDARY_V1` mean 2,585.4 / median
1,271.5; `STRUCTURAL_NODE_V1` mean 1,376.5 / median 779.0.

### Data-quality checks (live chunks)

Duplicate `content_sha256` groups: **0**. Missing/empty `citation`: **0**. Missing/empty
`source_url`: **0**. Missing/empty `content_sha256`: **0**. No chunks were altered as a result of
this audit.

## G. Graph and reference audit

Node/edge types actually implemented and populated in the final snapshot's schema (section A's
counts repeated here for context): CONTAINS 6,489, HAS_CHUNK 9,189, REFERENCES 7,159,
CROSS_REFERS_TO 4,763. **No AMENDS/COMMENCES/or similar relation exists in the final evaluated
corpus's graph** — those relation types exist only in the separate, older, unused
`state/procurement_kg.sqlite3` store (section A).

Reference-resolution status is set only on the 11,922 reference-type edges (CROSS_REFERS_TO +
REFERENCES); structural edges (CONTAINS, HAS_CHUNK) carry no status. Two resolver code paths feed
this field: `resolve_references.py` (general legal-citation resolution — actual status vocabulary
in code: `EXACT_INTERNAL, EXACT_URL, EXACT_DOCUMENT, EXACT_CROSS_DOCUMENT, NEAREST_ANCESTOR,
DOCUMENT_ONLY, TARGET_NOT_IN_CORPUS, AMBIGUOUS, EXTERNAL_INSTRUMENT_REFERENCE,
NOT_A_LEGAL_REFERENCE, UNRESOLVED`; only the first five are edge-creating) and a separate,
undocumented-in-the-first-script's-docstring script, `extract_guidance_references.py`, which
produces `GUIDANCE_EXACT`/`GUIDANCE_ANCESTOR` statuses that in fact dominate the final edge
population.

### Status counts on the 11,922 reference-type edges in the final snapshot

| status | count | % |
|---|---:|---:|
| GUIDANCE_EXACT | 6,892 | 57.8% |
| EXACT_INTERNAL | 3,464 | 29.1% |
| EXACT_CROSS_DOCUMENT | 802 | 6.7% |
| NEAREST_ANCESTOR | 497 | 4.2% |
| GUIDANCE_ANCESTOR | 263 | 2.2% |
| EXACT_URL | 2 | <0.1% |
| EXACT_DOCUMENT | 2 | <0.1% |

Representative examples (real rows): `GUIDANCE_EXACT` — a national-security-exclusions guidance
chunk referencing PA2023 s.28(2) verbatim (confidence 0.9). `EXACT_INTERNAL` — Schedule 1
referencing Schedule 1 paragraph 2 within the same instrument (confidence 0.95).
`EXACT_CROSS_DOCUMENT` — a PR2024 regulation referencing PA2023 s.11 (confidence 0.9).
`NEAREST_ANCESTOR` — Part 3 referencing s.7(4)(a), resolved to the nearest available ancestor
node (confidence 0.75).

**The final snapshot database does not itself store unresolved-candidate rows** — those exist
only in intermediate JSONL files, not in `chunk_index_merged.sqlite3`. The most recent full
resolver run available (`data/search_corpus_v2/reference_resolution_report.json`, 2026-08-30, an
earlier corpus stage, 14,492 candidates) gives the major unresolved categories: `UNRESOLVED`
3,282 (dominant cause: opaque internal CLML `key-...` hrefs, not real citations to resolve),
`TARGET_NOT_IN_CORPUS` 2,511 (genuinely external instruments, e.g. `S.I. 2008/3231`, not
acquired), `DOCUMENT_ONLY` 1,194 (locator cited but no matching node in-corpus for that specific
sub-locator), `EXTERNAL_INSTRUMENT_REFERENCE` 524, `AMBIGUOUS` 208 (amendment-context citations
of another instrument), `NOT_A_LEGAL_REFERENCE` 16 (e.g. mailto: links misidentified as
citations by the regex layer, then correctly reclassified).

Graph connectivity (from `analyze_graph.py`, rerun read-only against the live database): the
legal-citation-only graph (CROSS_REFERS_TO + REFERENCES) has 3,961 nodes; the giant component
covers 99.8% of them (3,954 nodes), mean degree 6.0, median 1 — a small number of high-degree
hub nodes (max degree 432, a thresholds regulation) dominate connectivity. Edge-level topical
coherence (Jaccard similarity of topic/legal-concept tags across a CROSS_REFERS_TO edge) is 4.05x
above a random baseline (0.0674 vs 0.0167) — citations do carry real topical signal at the
individual-edge level, even though whole connected components are not more topically coherent
than chance (component-level lift 0.33, i.e. below chance).

## H. Corpus EDA / coverage

Composition tables above (sections B, G). Lifecycle coverage: see `CORPUS_COVERAGE_MATRIX.csv`,
built by keyword-mapping the corpus's own free-text `procurement_stage` field (LLM-assigned per
chunk, 1,529 distinct raw values observed, uncontrolled vocabulary — e.g. "Pre-Award",
"Pre-award", "pre-award" all appear as separate literal strings) onto the suggested lifecycle
dimensions. **This mapping is a best-effort keyword match over an uncontrolled tag field, not a
corpus-native controlled taxonomy** — stated explicitly in the CSV's own `method_note` column.
**84.9% of live chunks (18,706 of 22,042) carry no `procurement_stage` tag at all** — this field
appears to be populated mainly for guidance/workflow-type chunks, not for legislation text, so
its absence on a legislation chunk is expected, not a data-quality defect.

Largest mapped lifecycle buckets by chunk count: contract_management_implementation (728),
contract_award (702), strategy_planning (625), award_criteria_evaluation (436), tendering (385).
Smallest: dynamic_markets (4), direct_award (5), standstill (5), procedure_selection (2).

## I. Corpus sufficiency for the benchmark

Full 115-row table: `CORPUS_SUFFICIENCY.csv`. This measures whether required evidence *exists
anywhere* in the corpus — explicitly not a retrieval evaluation (which is answered separately by
`evaluation/final_retrieval_benchmark/metrics/candidate_ceiling.json` and
`strict_target_recall.json`, already computed in this project's earlier evaluation work and not
re-derived here).

- **Requirement-level FULLY_SUPPORTED: 113/115 = 98.26%** (115/115 = 100% if the two UNCERTAIN
  edge cases below are resolved in the corpus's favour).
- **Scenario-level complete support: 58/60 = 96.67%**.
- By split: DEV 78/78 (100.00%); TEST 35/37 (94.59%).
- By suite: 100% for 7 of 8 suites; `semantic` 17/19 (89.47%).
- By regime (citation-text pattern match): PA2023 85/85 (100%); PCR2015 3/3 (100%); mixed-regime
  6/6 (100%); guidance-only citations (`OTHER`) 14/16 (87.50%) — the two UNCERTAIN rows fall here.

The two non-FULLY_SUPPORTED rows are both `UNCERTAIN`, not `NOT_IN_CORPUS`: TEST005/REQ2 and
TEST006/REQ2 both have an empty `essential_evidence` list in the gold file, with their only
recorded citation filed under `strong_supporting_evidence` instead — and that citation
independently verifies as a live chunk in both cases. This is a gold-file labelling nuance (both
requirements are `requirement_grade_if_satisfied: 2`, i.e. lower-priority), **not a genuine
corpus gap** — no requirement in this benchmark has evidence that is actually absent from the
corpus.

**Corpus gap vs. candidate-generation failure vs. ranking failure, kept explicitly separate**:
this section answers only "does the evidence exist." The earlier retrieval-evaluation work in
this project (`evaluation/final_retrieval_benchmark/`) already answers the other two questions
directly and separately: 66.7% of scenarios show a candidate-generation problem (gold never
enters the retrieved candidate pool at all) and 8.3% show a pure ranking problem (gold is
retrieved but not ranked into the final top-10) — see that project's own
`STATIC_BENCHMARK_FINAL_REPORT.md` section 2. **Given corpus sufficiency is ~98-100%, the
retrieval bottleneck documented elsewhere in this project is confirmed to be a retrieval/ranking
problem, not a corpus-completeness problem** — the required evidence is present; the retrieval
systems evaluated in this project's separate retrieval-evaluation work largely fail to surface
it.

## J. Manual / human QA audit

See `MANUAL_QA_AUDIT.md` for the full table. Bottom line: no human review has occurred anywhere
in this repository's corpus-construction pipeline. All actually-performed QA is automated
(deterministic scripts) or agent/LLM-conducted; every artifact that looks like it was prepared
for human review (stratified samples with `MANUAL_VERDICT`/`MANUAL_DECISION` columns) is
confirmed, by direct inspection, to be completely unfilled.

## K. LLM use during corpus construction

| Use | Script(s) | Model | Output trusted directly? | Deterministic verification |
|---|---|---|---|---|
| Chunk boundary selection | `build_search_corpus.py` | not independently confirmed in this pass (see chunking scripts for defaults) | No — only block-id selection is used | Yes: text reconstructed from immutable blocks by code; `validate_plan()` rejects incomplete/malformed plans |
| Chunk text emission (legislation) | `chunk_legislation_text.py`, `rechunk_from_index.py` | `gpt-4o-mini` | Yes, LLM output is stored as chunk text | Statistical only: 5-token shingle-overlap fidelity check, default min. coverage 0.80; failures flagged, not excluded |
| Chunk text emission (PDF) | `chunk_pdf_text.py` | `gpt-4.1` | Yes, LLM output is stored as chunk text | Same statistical fidelity check as above |
| Chunk-quality rubric judging | `evaluate_chunk_quality.py` | `gpt-4o-mini` | For diagnostics only, not corpus inclusion | None (self-report scores) |
| GOOD/INCOMPLETE/LOW_VALUE labelling | `label_chunk_quality_llm.py` | `gpt-4.1` | For diagnostics only, not corpus inclusion | None |
| Missing retrieval-summary generation | `build_chunk_representations.py` | `gpt-4o-mini` | Yes, for chunks lacking a summary | None (metadata field only, not evidence text) |
| Chunking prompt evolution (meta-level) | `optimize_chunking_prompt.py` | mutator `gpt-4.1`, scorer `gpt-4o-mini` | No — deterministic, model-free objective function scores candidate prompts | Yes: reuses the exact block-slicing reconstruction logic, explicitly to avoid "a model judging a model" |

**The sentence "the LLM selected semantic boundaries/metadata where applicable but did not
rewrite the source evidence text" is only safe to state for the boundary-selection lane
(`LLM_SEMANTIC_BOUNDARY_V1`, ~19.9% of the live corpus).** For the two text-emission lanes
(`LLM_LEG_TEXT_V2` + `LLM_PDF_TEXT_V2`, 78.3% of the live corpus), the LLM's output is what is
actually stored, checked only by a statistical similarity threshold that does not exclude
failures. This must not be stated as a blanket claim for "the corpus" as a whole.

## L. Reproducibility

- Repository commit: `79c488c7103078633159e26bdfe24e7410313821` (dirty working tree — 20
  modified files unrelated to this session's corpus/audit work, per `git status`).
- Corpus snapshot: `state/chunk_index_merged.sqlite3`, `chunks__bge_m3__merged` (see section A).
- Key scripts (acquisition through ingestion, in dependency order where reconstructable):
  `scrapers/*.py` → **[gap: the Procurement Pathway / general recursive-crawl code is absent —
  see section C]** → `content_filters.py` → `chunk_legislation_text.py` /
  `chunk_legislation_from_nodes.py` / `chunk_pdf_text.py` / `chunk_commencement_regs_from_xml.py`
  → `ingest_legislation_chunks.py` / `ingest_pdf_chunks.py` / `ingest_structural_node_chunks.py`
  → `deduplicate_instruments.py` → `resolve_references.py` / `extract_guidance_references.py` →
  `densify_graph_edges.py` → `build_chunk_index.py`.
- Environment: Python 3.9.6 (per `index_manifest`); embedding model `BAAI/bge-m3`, 1024
  dimensions; Qdrant `http://localhost:6333`, collection `chunks__bge_m3__merged`, cosine
  distance, normalized vectors; SQLite FTS5 with the `porter` tokenizer.
- Random seeds: not applicable to corpus construction itself (no sampling-based step in the
  final ingest chain was found to require a seed); the evaluation-side paired-bootstrap seed
  (1234) is documented separately in `procurement_research_workbench_v1/results/final/
  FINAL_FREEZE.json` and is not a corpus-construction concern.
- Date of acquisition: not uniformly recorded per source; ingest report timestamps range from
  2026-09-03 (`densify_graph_report.json`) to 2026-09-06 (`ingest_structural_node_report.json`);
  the underlying scrapes themselves are undated in the surviving artifacts for several source
  families (see section C's gap).
- Manifest hash: `index_manifest.chunks_sha256 = 829d97a362145ebcb37fa7e4606a4a35e158a641dd52913f349582f22fd46bf3`
  (stale, corresponds to the 8,511-chunk build state noted in section A, not the current 27,558).

### How to reproduce this corpus (honest, including the known gap)

1. Checkout commit `79c488c7103078633159e26bdfe24e7410313821`.
2. **Cannot currently reproduce**: the Procurement Pathway / general recursive web crawl (source
   code absent from this checkout — see section C). Its outputs (`procurement_pathway_urls.jsonl`,
   `crawl_root_url_counts.csv`, `crawl_merged_documents.json`, and the `crawl_A_official`/
   `crawl_B_bounded`/`crawl_v2_relevant`/`corpus_ingest*` directories) would need to be supplied
   as-is, or the crawl re-implemented from scratch.
3. Run the fixed-URL scrapers in `scrapers/` for the remaining source families (each is
   independently rerunnable; each writes its own manifest with `follow_links: False` or
   equivalent).
4. Run `content_filters.py`-based filtering (invoked from within the chunking scripts, not a
   separate CLI step in this repository as checked out).
5. Run the chunking scripts appropriate to each source type: `chunk_legislation_from_nodes.py` /
   `chunk_commencement_regs_from_xml.py` (structural, no LLM) or `chunk_legislation_text.py` /
   `chunk_pdf_text.py` (LLM text-emission, requires `OPENAI_API_KEY` and model access) or
   `build_search_corpus.py` (LLM boundary-selection).
6. Run `ingest_legislation_chunks.py` / `ingest_pdf_chunks.py` / `ingest_structural_node_chunks.py`
   to insert, dedup, and flag chunks into the SQLite database.
7. Run `deduplicate_instruments.py` to mark cross-acquisition-path duplicate instruments.
8. Run `resolve_references.py` and `extract_guidance_references.py` to populate reference edges.
9. Run `densify_graph_edges.py` to roll up unreachable reference targets to their nearest
   chunked ancestor.
10. Run `build_chunk_index.py` to build the FTS5 lexical index and the Qdrant dense index
    (requires a running Qdrant instance and the `BAAI/bge-m3` embedding model).
11. **Not automated in this checkout**: refreshing `index_manifest` after later ingest passes —
    step 6 onward were run multiple times (per the report file timestamps) without this table
    being updated; a reproduction attempt should recompute counts directly from the tables
    rather than trusting `index_manifest`, exactly as this audit did.

No manual/human steps are hidden in this sequence — the one genuinely missing piece (the
Procurement Pathway crawl) is disclosed as missing, not silently assumed reproducible.

## M. Safe claims for the thesis

### Safe claims for the thesis

1. The final evaluated corpus (`state/chunk_index_merged.sqlite3`, snapshot as of commit
   `79c488c7...313821`, 2026-09-06) contains 22,042 live, non-superseded, non-filtered retrieval
   chunks drawn from 2,078 source documents, spanning primary legislation, secondary legislation,
   official government guidance, regulator/technical guidance, procurement-lifecycle workflow
   guidance, and professional/practitioner commentary.
2. The corpus preserves legal structural identity separately from retrieval identity: each chunk
   carries a `parent_node_id`/`parent_type` linking it to the legislative provision or document
   section it was drawn from, and the source XML's own element identifiers are retained in
   citation construction.
3. Approximately one-fifth of the live corpus (`LLM_SEMANTIC_BOUNDARY_V1`, 4,388 chunks) has a
   code-enforced guarantee that chunk text is reconstructed verbatim from immutable source blocks,
   with the LLM restricted to selecting boundaries only.
4. The remaining roughly four-fifths of the live corpus (two LLM text-emission chunking methods)
   is verified only by a statistical shingle-overlap fidelity check against the source text
   (minimum 80% coverage), and chunks failing that check are flagged, not excluded — this is a
   disclosed, deliberate trade-off made because stricter boundary-only selection failed
   frequently on fragmentary PDF and some legislation sources.
5. The corpus's reference graph resolves the large majority of in-scope legal citations to a
   specific status category (five status types are edge-creating; three further categories
   account for the bulk of unresolved candidates, dominated by opaque internal markup anchors and
   genuinely external, unacquired instruments), and no relation type not actually implemented in
   the final graph (e.g. AMENDS, COMMENCES) is present in the evaluated corpus's edge set.
6. Independent verification against a 60-scenario, 115-requirement legal-question benchmark found
   that 98.26% of requirements (100% under a defensible resolution of two gold-file labelling
   edge cases) have their required essential evidence genuinely present in the corpus as a live,
   unfiltered chunk — corpus completeness is not the binding constraint on this project's
   retrieval results.
7. No human review of chunk quality, relevance judgments, or reference-resolution edges is
   evidenced anywhere in this repository; quality assurance actually performed during corpus
   construction was either fully automated (deterministic scripts) or LLM/agent-conducted, and
   is reported as such throughout this audit.
8. A specific, material reproducibility gap exists: the acquisition method for the corpus's
   single largest identified source family (Procurement Pathway lifecycle guidance, and the
   general recursive web crawl behind several other source directories) is not present as
   runnable code in this repository — only its outputs and downstream consumers survive.
9. Two count discrepancies were found between this corpus's own internal manifest/prior
   documentation and a fresh direct query of the live database (both under 1% of the affected
   totals), traced to a manifest that was not refreshed after later ingest passes; this audit's
   counts are the fresh, current ones and should be preferred over `index_manifest` or
   `thesis_evidence/graph_statistics.json`'s edge-count figures specifically.
10. The corpus spans three legal regimes with tagged chunk counts (PA2023: 3,208; PCR2015: 1,903;
    PR2024: 539), alongside a large body of untagged guidance/professional material.
11. Chunk-level data-quality checks on the live corpus found zero duplicate chunk texts, zero
    missing citations, and zero missing source URLs among live rows.
12. Procurement-lifecycle coverage is present across all of the suggested lifecycle dimensions to
    some degree, though highly uneven (from 2 chunks for "procedure selection" to 728 for
    "contract management/implementation"), and this mapping is a best-effort keyword match over
    an uncontrolled, LLM-assigned free-text field, not a corpus-native controlled taxonomy.

### Claims NOT safe to make

- "The corpus is exhaustive" or "all UK procurement law is covered" — not evidenced; large,
  known gaps exist (e.g. `TARGET_NOT_IN_CORPUS` reference candidates citing genuinely external,
  unacquired instruments).
- "All chunks were manually reviewed" — false; no human review is evidenced anywhere.
- "All LLM outputs were human verified" — false, for the same reason; some LLM outputs (the
  boundary-selection lane) have a code-level provenance guarantee instead of human verification,
  which is a different and narrower claim.
- "All references resolve" — false; a substantial fraction of reference candidates are
  UNRESOLVED, TARGET_NOT_IN_CORPUS, or AMBIGUOUS in the most recent full resolver run available.
- "The LLM only selected chunk boundaries and never touched evidence text" as a claim about the
  whole corpus — false as a blanket statement; true only for ~20% of live chunks.
- "The final corpus's graph includes AMENDS/COMMENCES relations" — false for the evaluated
  corpus; those relation types exist only in a separate, unused, older KG-construction database.
- "The acquisition pipeline is fully reproducible from this repository" — false; the Procurement
  Pathway crawl (and related recursive-crawl source directories) cannot currently be rerun from
  checked-in code.
- "Corpus statistics in `thesis_evidence/graph_statistics.json` are current" — not for edge
  counts specifically; that file's own staleness self-disclosure is confirmed by this audit, and
  its edge-count figures should not be cited as current.
