# Environment

Two distinct claims are kept separate, as they are not the same thing:

## Currently verified compatible environment (this is what is actually recorded here)

Captured from the `.venv-embed` interpreter this session used to run every script referenced in
this bundle's validation report (pytest suite, `candidate_ceiling_CORRECTED.py`,
`build_final_tables.py`, `strict_target_recall.py`, etc.) on 2026-09-07.

- **Python**: 3.14.5 (`python3 --version`)
- **OS/platform**: Darwin 24.5.0, arm64 (`uname -a`: `Darwin ... Kernel Version 24.5.0 ...
  RELEASE_ARM64_T6041 arm64`)
- **Full pip freeze**: `pip-freeze.txt` (110 packages)
- **Key package versions** (`requirements-lock.txt`): `openai==2.54.0`,
  `qdrant-client==1.19.0`, `sentence-transformers==6.0.0`, `torch==2.13.0`,
  `transformers==5.15.0`, `numpy==2.5.2`, `scipy==1.18.0`, `matplotlib==3.11.1`,
  `jsonschema==4.26.0`, `pytest==9.1.1`.

This environment is confirmed to run the full test suite (60/60 pass) and all recomputation
scripts in this bundle.

## Historical recorded environment (corpus construction) -- NOT reconstructed exactly

The corpus itself (SQLite index, embeddings, ingest passes) was built over several days
(ingest report timestamps span 2026-09-03 to 2026-09-06 -- see
`corpus/audits/FINAL_CORPUS_AUDIT.md` section L). No `pip freeze` was captured at the time of
that original build, and the `.venv-embed` interpreter has almost certainly received package
updates since then (the `pip-freeze.txt` above reflects package versions as of the finalization
date, 2026-09-07, not as of the original corpus build). **Do not treat the versions above as an
exact historical record of what built the corpus** -- they are the versions confirmed to
successfully run the evaluation and recomputation code against the already-built corpus
snapshot today.

The one exception with an exact historical record is the corpus index's own embedding
configuration, frozen inside `index_manifest` at build time and independently confirmed by this
session's audit:

- **Embedding model**: `BAAI/bge-m3`
- **Embedding dimensions**: 1024
- **Distance metric**: cosine, normalized vectors
- **Vector store**: Qdrant, collection `chunks__bge_m3__merged`
- **Lexical index**: SQLite FTS5, `porter` tokenizer
- **Embedding model revision/commit**: not recorded anywhere found in this repository; the
  `sentence-transformers`/HuggingFace model card revision hash was not pinned or logged by the
  original ingest scripts. This is a genuine, disclosed gap, not an omission on this audit's part.

## LLM models and parameters (evaluation stage, independently confirmed from run artifacts)

- All controller/judge/adjudicator/generator slots: `gpt-4o-mini` (single-model configuration,
  disclosed throughout the results as repeated-model, not diverse-judge).
- Endpoint: `https://api.openai.com/v1/chat/completions`.
- No `temperature` or other sampling parameter is set explicitly anywhere in
  `configs/models.json` or the calling code (`prw/llm.py`) -- the provider's own default applies,
  which is not necessarily temperature 0. This means LLM calls are **not deterministic
  run-to-run**, and no random seed governs them (there is no seed parameter in the OpenAI
  Chat Completions request body constructed by this codebase).
- The only seeded randomness in this pipeline is the bootstrap resampling used for paired
  confidence intervals: seed `1234`, in both `prw/metrics.py::paired_bootstrap` and
  `evaluation/final_retrieval_benchmark/build_final_tables.py::paired_bootstrap`. Given the same
  saved per-scenario metrics, these confidence intervals are exactly reproducible; the LLM
  judgments and retrieval decisions that produced those per-scenario metrics in the first place
  are not.

## Deterministic execution: what is and is not possible

- **Deterministic from saved artifacts**: all metric aggregation, paired significance tests,
  candidate-ceiling classification, figure generation -- these are pure functions of the
  already-saved JSONL/JSON outputs and will produce byte-identical numbers every time.
- **Not deterministic if rerun**: any step that calls an LLM (controller planning/observation,
  bundle/pointwise judging, chunk text-emission during corpus construction) will very likely
  produce different raw output on a fresh run, though the validation/repair logic constrains
  what shape that output can take.
- **Not deterministic even for "the same" retrieval query**: dense retrieval itself is
  deterministic given a fixed embedding model and index (no randomness in `chunk_retrieval.py`'s
  search path), but the LLM-driven query decomposition feeding `planned_multisearch`/`adaptive`
  is not, so two runs of those two systems on the same scenario are not guaranteed to issue the
  same underlying retrieval queries.
