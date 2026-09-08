#!/usr/bin/env python3
"""
For each scenario, compute whether the RESOLVED gold chunk_ids (from gold_evidence.jsonl,
status MATCHED/FUZZY_MATCHED) appear in the lexical-only, dense-only, and lexical+dense union
candidate lists at depths 10/20/50, versus whether they appear in the FINAL (two-lane) top-10.

If gold is in the union candidate pool at depth 50 but not in the final top-10: RANKING problem.
If gold never enters the union candidate pool at all: CANDIDATE GENERATION / QUERY problem.

Requires config_A_lexical.jsonl, config_B_dense.jsonl, config_F_two_lane.jsonl already run,
and gold_evidence.jsonl already resolved.
"""
import json
from pathlib import Path
from collections import defaultdict

BENCH_DIR = Path(__file__).resolve().parent


def load_jsonl(p):
    if not Path(p).exists():
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def main():
    gold = {g["scenario_id"]: g for g in load_jsonl(BENCH_DIR / "gold_evidence.jsonl")}
    lex = {r["scenario_id"]: [x["chunk_id"] for x in r["results"]] for r in load_jsonl(BENCH_DIR / "retrieval_runs" / "config_A_lexical.jsonl")}
    dense = {r["scenario_id"]: [x["chunk_id"] for x in r["results"]] for r in load_jsonl(BENCH_DIR / "retrieval_runs" / "config_B_dense.jsonl")}
    two_lane_raw = load_jsonl(BENCH_DIR / "retrieval_runs" / "config_F_two_lane.jsonl")
    final_top10 = {}
    for r in two_lane_raw:
        merged = r.get("legislation_lane", []) + r.get("other_lane", [])
        merged.sort(key=lambda x: -x["final_score"])
        final_top10[r["scenario_id"]] = [x["chunk_id"] for x in merged[:10]]

    def resolved_gold_ids(sid):
        g = gold.get(sid)
        if not g:
            return set()
        ids = set()
        for req in g.get("requirements", []):
            for item in req.get("essential_evidence", []):
                res = item.get("resolution", {})
                if res.get("status") in ("MATCHED", "FUZZY_MATCHED") and res.get("chunk_id"):
                    ids.add(res["chunk_id"])
        return ids

    rows = []
    diag_counts = defaultdict(int)
    for sid in gold:
        gids = resolved_gold_ids(sid)
        if not gids:
            diag_counts["no_resolved_gold"] += 1
            continue
        lex_ids, dense_ids, final_ids = set(lex.get(sid, [])), set(dense.get(sid, [])), set(final_top10.get(sid, []))
        union_50 = lex_ids | dense_ids

        in_lex10 = bool(gids & set(lex.get(sid, [])[:10]))
        in_dense10 = bool(gids & set(dense.get(sid, [])[:10]))
        in_union50 = bool(gids & union_50)
        in_final10 = bool(gids & final_ids)

        if in_union50 and not in_final10:
            diag = "RANKING_PROBLEM"
        elif not in_union50:
            diag = "CANDIDATE_GENERATION_PROBLEM"
        else:
            diag = "OK_FOUND_IN_FINAL_TOP10"
        diag_counts[diag] += 1

        rows.append({
            "scenario_id": sid, "n_gold_resolved": len(gids),
            "gold_in_lexical_top10": in_lex10, "gold_in_dense_top10": in_dense10,
            "gold_in_union_top50": in_union50, "gold_in_final_top10": in_final10,
            "diagnosis": diag,
        })

    (BENCH_DIR / "metrics").mkdir(exist_ok=True)
    with (BENCH_DIR / "metrics" / "candidate_ceiling.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(dict(diag_counts), open(BENCH_DIR / "metrics" / "candidate_ceiling_summary.json", "w"), indent=2)
    print(json.dumps(dict(diag_counts), indent=2))


if __name__ == "__main__":
    main()
