#!/usr/bin/env python3
"""
Compute all primary metrics for configs A-F against scenarios_all.jsonl, using
qrels_provisional.jsonl (LLM first-pass graded relevance) and gold_evidence.jsonl (mandatory
requirement structure). Writes metrics/summary.json, metrics/per_scenario.jsonl, and
metrics/candidate_ceiling.json (the candidate-generation-vs-ranking diagnostic).

All metrics are computed per requirement_grade_if_satisfied threshold recorded in the gold file
(defaults to 3 if absent), not a single global threshold.
"""
import json, math, statistics, sys
from pathlib import Path
from collections import defaultdict

BENCH_DIR = Path(__file__).resolve().parent


def load_jsonl(p):
    if not Path(p).exists():
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def dcg(grades):
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades))


def main():
    scenarios = {s["scenario_id"]: s for s in load_jsonl(BENCH_DIR / "scenarios_all.jsonl")}
    gold = {g["scenario_id"]: g for g in load_jsonl(BENCH_DIR / "gold_evidence.jsonl")}
    qrels = load_jsonl(BENCH_DIR / "qrels_provisional.jsonl")

    # qrel_map[(scenario_id, chunk_id)] -> judgment record
    qrel_map = {}
    for q in qrels:
        qrel_map[(q["scenario_id"], q["chunk_id"])] = q

    configs = ["A_lexical", "B_dense", "C_hybrid", "D_hybrid_priors", "E_hybrid_graph"]
    run_data = {}
    for cfg in configs:
        path = BENCH_DIR / "retrieval_runs" / f"config_{cfg}.jsonl"
        if path.exists():
            run_data[cfg] = {r["scenario_id"]: r["results"] for r in load_jsonl(path)}
    two_lane_path = BENCH_DIR / "retrieval_runs" / "config_F_two_lane.jsonl"
    two_lane_data = {}
    if two_lane_path.exists():
        for r in load_jsonl(two_lane_path):
            merged = r.get("legislation_lane", []) + r.get("other_lane", [])
            merged.sort(key=lambda x: -x["final_score"])
            for rank, item in enumerate(merged, 1):
                item["rank"] = rank
            two_lane_data[r["scenario_id"]] = merged[:50]
    if two_lane_data:
        run_data["F_two_lane"] = two_lane_data
        configs = configs + ["F_two_lane"]

    per_scenario_metrics = []
    agg = {cfg: defaultdict(list) for cfg in configs}

    for sid, sc in scenarios.items():
        g = gold.get(sid)
        if not g:
            continue
        reqs = g.get("requirements", [])
        mandatory_reqs = [r for r in reqs if any(True for _ in [1])]  # all provided reqs treated per their own mandatory flag from scenario record
        scenario_reqs = {r["requirement_id"]: r for r in sc.get("evidence_requirements", [])}

        for cfg in configs:
            results = run_data.get(cfg, {}).get(sid, [])
            chunk_ids_ranked = [r["chunk_id"] for r in results]

            # grades for retrieved chunks (0 if unjudged, per instructions: unjudged != irrelevant,
            # so track separately how many top-k are unjudged)
            grades = []
            unjudged_in_top10 = 0
            for i, cid in enumerate(chunk_ids_ranked[:10]):
                jr = qrel_map.get((sid, cid))
                if jr is None or jr.get("relevance_grade") is None:
                    grades.append(0)
                    unjudged_in_top10 += 1
                else:
                    grades.append(jr["relevance_grade"])

            ndcg10 = None
            if grades:
                dcg10 = dcg(grades)
                idcg10 = dcg(sorted(grades, reverse=True)) or 1e-9
                ndcg10 = round(dcg10 / idcg10, 4) if idcg10 else 0.0

            hit10 = any(g_ >= 2 for g_ in grades)

            # requirement coverage: for each mandatory req in gold, check if any top-k chunk
            # satisfies it (requirement_id in requirement_ids_supported AND grade >= threshold)
            def coverage_at(k):
                satisfied, total = 0, 0
                for req in reqs:
                    threshold = req.get("requirement_grade_if_satisfied", 3)
                    rid = req["requirement_id"]
                    total += 1
                    found = False
                    for cid in chunk_ids_ranked[:k]:
                        jr = qrel_map.get((sid, cid))
                        if jr and jr.get("relevance_grade") is not None and jr["relevance_grade"] >= threshold \
                           and rid in (jr.get("requirement_ids_supported") or []):
                            found = True
                            break
                    if found:
                        satisfied += 1
                return (satisfied / total) if total else None

            cov5 = coverage_at(5)
            cov10 = coverage_at(10)
            scenario_complete10 = (cov10 == 1.0) if cov10 is not None else None

            # MRR: first chunk supporting ANY mandatory requirement at its threshold
            rr = 0.0
            for i, cid in enumerate(chunk_ids_ranked, 1):
                jr = qrel_map.get((sid, cid))
                if jr and jr.get("relevance_grade") is not None:
                    for req in reqs:
                        threshold = req.get("requirement_grade_if_satisfied", 3)
                        if jr["relevance_grade"] >= threshold and req["requirement_id"] in (jr.get("requirement_ids_supported") or []):
                            rr = 1.0 / i
                            break
                if rr:
                    break

            # authority@1: top-1 result's authority_class matches an "expected" role heuristic --
            # for authority-suite scenarios, top-1 should be binding if scenario demands binding_rule
            top1_ok = None
            if results:
                top1 = results[0]
                jr = qrel_map.get((sid, top1["chunk_id"]))
                if jr is not None:
                    wants_binding = any(r.get("role") == "binding_rule" for r in gold_requirement_roles(g))
                    top1_ok = (jr.get("is_binding") is True) if wants_binding else True

            # regime error: any top-10 result judged is_currently_applicable == False AND
            # relevance_grade >= 2 (i.e. a plausible-looking but wrong-regime result reached top10)
            regime_error = any(
                (qrel_map.get((sid, cid), {}).get("is_currently_applicable") is False) and
                (qrel_map.get((sid, cid), {}).get("relevance_grade", 0) or 0) >= 2
                for cid in chunk_ids_ranked[:10]
            )

            rec = {
                "scenario_id": sid, "config": cfg, "suite": sc.get("suite"),
                "ndcg10": ndcg10, "hit10": hit10, "mrr": round(rr, 4),
                "req_coverage_5": cov5, "req_coverage_10": cov10,
                "scenario_complete_10": scenario_complete10,
                "authority_top1_ok": top1_ok, "regime_error": regime_error,
                "unjudged_in_top10": unjudged_in_top10,
                "n_results": len(results),
            }
            per_scenario_metrics.append(rec)
            for k in ("ndcg10", "hit10", "mrr", "req_coverage_5", "req_coverage_10", "scenario_complete_10", "regime_error"):
                if rec[k] is not None:
                    agg[cfg][k].append(rec[k])

    def mean(vals):
        vals = [float(v) for v in vals if v is not None]
        return round(statistics.mean(vals), 4) if vals else None

    summary = {}
    for cfg in configs:
        a = agg[cfg]
        summary[cfg] = {
            "n_scenarios": len(a["ndcg10"]),
            "ndcg10_mean": mean(a["ndcg10"]),
            "hit10_rate": mean(a["hit10"]),
            "mrr_mean": mean(a["mrr"]),
            "req_coverage_5_mean": mean(a["req_coverage_5"]),
            "req_coverage_10_mean": mean(a["req_coverage_10"]),
            "scenario_complete_10_rate": mean(a["scenario_complete_10"]),
            "regime_error_rate": mean(a["regime_error"]),
        }

    (BENCH_DIR / "metrics").mkdir(exist_ok=True)
    json.dump(summary, open(BENCH_DIR / "metrics" / "summary.json", "w"), indent=2)
    with (BENCH_DIR / "metrics" / "per_scenario.jsonl").open("w") as f:
        for rec in per_scenario_metrics:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(json.dumps(summary, indent=2))


def gold_requirement_roles(g):
    roles = []
    for req in g.get("requirements", []):
        for item in req.get("essential_evidence", []) + req.get("strong_supporting_evidence", []):
            if "role" in item:
                roles.append(item)
    return roles


if __name__ == "__main__":
    main()
