#!/usr/bin/env python3
"""
CORRECTED version of candidate_ceiling.py, produced during final-package audit (2026-09-07).

Bug found in the original script (preserved unmodified alongside this file as
candidate_ceiling.py, for audit trail): the if/elif classification checked
`not in_union50` (candidate-generation failure) BEFORE checking `in_final10` (success).
`in_union50` is computed only from the lexical-only and dense-only candidate lists; but
`in_final10` is read from config F_two_lane, which ALSO retrieves via the graph-expansion
channel. Consequently any scenario where gold was retrieved into the final top-10 purely via
graph expansion (i.e. present in final10 but absent from the narrower lexical+dense union) was
misclassified as CANDIDATE_GENERATION_PROBLEM instead of a genuine success.

Fix: check success (gold in final top-10) FIRST, exactly as the audit's prescribed algorithm
specifies:
  1. if gold present in the final returned top-k -> retrieval success
  2. elif gold absent from the union candidate pool (lexical + dense, depth 50) -> candidate-
     generation failure
  3. else -> ranking/fusion failure

The "final top-10" definition itself (top 10 by final_score across legislation_lane + other_lane
merged) is UNCHANGED from the original script, and matches the same definition used by
compute_metrics.py to compute F_two_lane's own reported nDCG/coverage numbers elsewhere in this
project -- so this fix does not introduce a new inconsistency with those already-reported
numbers, it only corrects the classification logic bug.

No retrieval results are altered by this fix; only the downstream diagnostic classification.
Old vs corrected counts: see provenance/CHANGELOG_FINALIZATION.md.
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

        # CORRECTED ORDER: success check first.
        if in_final10:
            diag = "OK_FOUND_IN_FINAL_TOP10"
        elif not in_union50:
            diag = "CANDIDATE_GENERATION_PROBLEM"
        else:
            diag = "RANKING_PROBLEM"
        diag_counts[diag] += 1

        rows.append({
            "scenario_id": sid, "n_gold_resolved": len(gids),
            "gold_in_lexical_top10": in_lex10, "gold_in_dense_top10": in_dense10,
            "gold_in_union_top50": in_union50, "gold_in_final_top10": in_final10,
            "diagnosis": diag,
        })

    (BENCH_DIR / "metrics").mkdir(exist_ok=True)
    with (BENCH_DIR / "metrics" / "candidate_ceiling_CORRECTED.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(dict(diag_counts), open(BENCH_DIR / "metrics" / "candidate_ceiling_CORRECTED_summary.json", "w"), indent=2)
    print(json.dumps(dict(diag_counts), indent=2))


if __name__ == "__main__":
    main()
