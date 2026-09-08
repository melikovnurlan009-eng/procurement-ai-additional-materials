#!/usr/bin/env python3
"""
Pool the union of candidates from configs A-F (retrieval_runs/config_*.jsonl) per scenario,
deduplicated by chunk_id, and force-include every resolved gold evidence chunk_id (from
gold_evidence.jsonl after resolve_gold_targets.py has run) even if no system retrieved it.

Output: candidate_pool.jsonl, one record per (scenario_id, chunk_id) pair:
  {"scenario_id":..., "chunk_id":..., "citation":..., "authority_class":..., "legal_regime":...,
   "source_url":..., "text":..., "retrieved_by": ["A_lexical","C_hybrid",...],
   "best_rank_by_config": {"A_lexical": 3, ...}, "forced_gold": true/false}
"""
import json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = Path(__file__).resolve().parent

con = sqlite3.connect(ROOT / "state" / "chunk_index_merged.sqlite3")
con.row_factory = sqlite3.Row


def load_run(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def main():
    run_dir = BENCH_DIR / "retrieval_runs"
    config_files = sorted(run_dir.glob("config_*.jsonl"))
    if not config_files:
        print("No retrieval_runs/config_*.jsonl found -- run run_retrieval_configs.py first.", file=sys.stderr)
        sys.exit(1)

    by_scenario = {}  # scenario_id -> chunk_id -> {"retrieved_by": {}, "best_rank": {}}

    for path in config_files:
        cfg_label = path.stem.replace("config_", "")
        for row in load_run(path):
            sid = row["scenario_id"]
            by_scenario.setdefault(sid, {})
            if "results" in row:
                lanes = {cfg_label: row["results"]}
            else:
                lanes = {
                    f"{cfg_label}_legislation": row.get("legislation_lane", []),
                    f"{cfg_label}_other": row.get("other_lane", []),
                }
            for lane_label, items in lanes.items():
                for item in items:
                    cid = item["chunk_id"]
                    if not cid:
                        continue
                    entry = by_scenario[sid].setdefault(cid, {"retrieved_by": {}, "meta": item})
                    entry["retrieved_by"][lane_label] = item["rank"]

    # force-include resolved gold
    gold_path = BENCH_DIR / "gold_evidence.jsonl"
    n_forced = 0
    if gold_path.exists():
        for rec in load_run(gold_path):
            sid = rec["scenario_id"]
            by_scenario.setdefault(sid, {})
            for req in rec.get("requirements", []):
                for bucket in ("essential_evidence", "strong_supporting_evidence"):
                    for item in req.get(bucket, []):
                        res = item.get("resolution", {})
                        cid = res.get("chunk_id")
                        if cid and res.get("status") in ("MATCHED", "FUZZY_MATCHED"):
                            entry = by_scenario[sid].setdefault(cid, {"retrieved_by": {}, "meta": None, "forced_gold": True})
                            entry["forced_gold"] = True
                            if entry.get("meta") is None:
                                n_forced += 1

    out_path = BENCH_DIR / "candidate_pool.jsonl"
    n_rows = 0
    with out_path.open("w") as f:
        for sid, chunks in by_scenario.items():
            # fetch full text/metadata for any forced-gold chunk missing meta
            missing_ids = [cid for cid, e in chunks.items() if e.get("meta") is None]
            meta_map = {}
            if missing_ids:
                placeholders = ",".join("?" * len(missing_ids))
                rows = con.execute(
                    f"SELECT chunk_id, citation, authority_class, legal_regime, source_url, "
                    f"substr(text,1,1200) as text FROM chunks WHERE chunk_id IN ({placeholders})",
                    missing_ids,
                ).fetchall()
                meta_map = {r["chunk_id"]: dict(r) for r in rows}
            for cid, entry in chunks.items():
                meta = entry.get("meta") or meta_map.get(cid) or {}
                # fetch full text for every pooled chunk (needed for judging), regardless of source
                text_row = con.execute("SELECT substr(text,1,1500) as t, source_url FROM chunks WHERE chunk_id=?", (cid,)).fetchone()
                out = {
                    "scenario_id": sid,
                    "chunk_id": cid,
                    "citation": meta.get("citation"),
                    "authority_class": meta.get("authority_class"),
                    "legal_regime": meta.get("legal_regime"),
                    "source_url": (text_row["source_url"] if text_row else None),
                    "text": (text_row["t"] if text_row else None),
                    "retrieved_by": entry["retrieved_by"],
                    "forced_gold": entry.get("forced_gold", False),
                }
                f.write(json.dumps(out, ensure_ascii=False) + "\n")
                n_rows += 1

    print(f"scenarios pooled: {len(by_scenario)}, total (scenario,chunk) rows: {n_rows}, "
          f"forced-gold-only additions: {n_forced}", file=sys.stderr)
    print(f"written {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
