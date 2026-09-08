#!/usr/bin/env python3
"""
Run the six required static retrieval configurations (A-F) against every scenario in
scenarios_all.jsonl, using the ACTUAL production ChunkRetriever (chunk_retrieval.py) against
the live corpus (state/chunk_index_merged.sqlite3, collection chunks__bge_m3__merged).

Must be run with .venv-embed/bin/python3 -- the bare python3 on PATH cannot import
sentence_transformers/qdrant_client, and chunk_retrieval.py's dense() silently returns []
rather than raising on ImportError, which would silently corrupt the B/C/D/E/F configs.

Configs (exact production settings, no silent parameter drift):
  A LEXICAL       use_lexical=True,  use_dense=False, use_graph=False, use_rerank=False
  B DENSE         use_lexical=False, use_dense=True,  use_graph=False, use_rerank=False
  C HYBRID        use_lexical=True,  use_dense=True,  use_graph=False, use_rerank=False   (RRF k=60, production default)
  D HYBRID+PRIORS use_lexical=True,  use_dense=True,  use_graph=False, use_rerank=True    (+ authority/regime/jurisdiction)
  E HYBRID+GRAPH  use_lexical=True,  use_dense=True,  use_graph=True,  use_rerank=False   (graph channel, no priors, isolates graph's own effect)
  F FINAL TWO-LANE search_two_lanes(), production defaults (candidates=100, hops=1, per_hop=40,
                    use_graph=True) -- priors always applied inside search_two_lanes per the
                    production code (chunk_retrieval.py has no use_rerank param on that method).

Depths saved: @1/@5/@10/@20/@50 (ranked list truncated to 50; @1..@20 read off the same list).
Candidate depth requested from the retriever: 50 (per the brief's "depth 30 or 50" instruction --
50 chosen since it strictly covers @1..@20 with headroom for pooling to work from).

Output: retrieval_runs/config_<X>.jsonl, one record per scenario:
  {"scenario_id":..., "config":"A", "results": [{"rank":1,"chunk_id":...,"citation":...,
   "authority_class":...,"legal_regime":...,"final_score":...}, ...]}
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from chunk_retrieval import ChunkRetriever  # noqa: E402

BENCH_DIR = Path(__file__).resolve().parent
DEPTH = 50

CONFIGS = {
    "A_lexical": dict(use_lexical=True, use_dense=False, use_graph=False, use_rerank=False),
    "B_dense": dict(use_lexical=False, use_dense=True, use_graph=False, use_rerank=False),
    "C_hybrid": dict(use_lexical=True, use_dense=True, use_graph=False, use_rerank=False),
    "D_hybrid_priors": dict(use_lexical=True, use_dense=True, use_graph=False, use_rerank=True),
    "E_hybrid_graph": dict(use_lexical=True, use_dense=True, use_graph=True, use_rerank=False),
}


def load_scenarios():
    path = BENCH_DIR / "scenarios_all.jsonl"
    return [json.loads(l) for l in open(path) if l.strip()]


def result_row(rank, item):
    return {
        "rank": rank,
        "chunk_id": item.get("chunk_id"),
        "citation": item.get("citation"),
        "authority_class": item.get("authority_class"),
        "legal_regime": item.get("legal_regime"),
        "final_score": round(item.get("final_score", item.get("score", 0.0)), 6),
    }


def main():
    scenarios = load_scenarios()
    print(f"Loaded {len(scenarios)} scenarios", file=sys.stderr)
    retriever = ChunkRetriever(ROOT / "state" / "chunk_index_merged.sqlite3", collection="chunks__bge_m3__merged")

    out_dir = BENCH_DIR / "retrieval_runs"
    out_dir.mkdir(exist_ok=True)

    for cfg_name, cfg_kwargs in CONFIGS.items():
        out_path = out_dir / f"config_{cfg_name}.jsonl"
        t0 = time.time()
        with out_path.open("w") as f:
            for i, sc in enumerate(scenarios):
                query = sc["query"]
                try:
                    results, trace = retriever.search(query, top_k=DEPTH, candidates=DEPTH, **cfg_kwargs)
                except Exception as e:
                    print(f"  ERROR {cfg_name} {sc['scenario_id']}: {e}", file=sys.stderr)
                    results = []
                row = {
                    "scenario_id": sc["scenario_id"],
                    "config": cfg_name,
                    "query": query,
                    "results": [result_row(r + 1, item) for r, item in enumerate(results)],
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                if (i + 1) % 15 == 0:
                    print(f"  {cfg_name}: {i+1}/{len(scenarios)}", file=sys.stderr)
        print(f"{cfg_name} done in {time.time()-t0:.1f}s -> {out_path}", file=sys.stderr)

    # F: final two-lane, production defaults
    out_path = out_dir / "config_F_two_lane.jsonl"
    t0 = time.time()
    with out_path.open("w") as f:
        for i, sc in enumerate(scenarios):
            query = sc["query"]
            try:
                leg, other, trace = retriever.search_two_lanes(
                    query, top_k_legislation=DEPTH, top_k_other=DEPTH, candidates=DEPTH, use_graph=True
                )
            except Exception as e:
                print(f"  ERROR F {sc['scenario_id']}: {e}", file=sys.stderr)
                leg, other = [], []
            row = {
                "scenario_id": sc["scenario_id"],
                "config": "F_two_lane",
                "query": query,
                "legislation_lane": [result_row(r + 1, item) for r, item in enumerate(leg)],
                "other_lane": [result_row(r + 1, item) for r, item in enumerate(other)],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if (i + 1) % 15 == 0:
                print(f"  F_two_lane: {i+1}/{len(scenarios)}", file=sys.stderr)
    print(f"F_two_lane done in {time.time()-t0:.1f}s -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
