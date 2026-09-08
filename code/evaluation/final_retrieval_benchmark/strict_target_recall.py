#!/usr/bin/env python3
"""
Strict verified-target retrieval: recall against the corpus-verified essential-evidence
chunk_ids in gold_evidence.jsonl (resolution.status in MATCHED/FUZZY_MATCHED), with NO LLM
judgment involved anywhere in this computation. This is a primary, judge-independent metric,
complementing pooled LLM-judged passage relevance (compute_metrics.py) now that bundle-sufficiency
judging (a synthesis-across-passages LLM task) has been demoted to exploratory after observed
substantive false-positive verdicts (see procurement_research_workbench_v1/results/pilot3_v2/
PILOT_REPORT_V2.md sec 6). Requires only gold_evidence.jsonl and retrieval_runs/config_*.jsonl,
both already computed; does not depend on the qrels_provisional.jsonl LLM-judging job.

Per (scenario, requirement) with resolved essential evidence: does ANY of that requirement's
resolved chunk_ids appear in a config's top-k? Recall_at_k is the fraction of requirements (not
scenarios) satisfied, matching the coverage-formula convention used elsewhere in this project.
"""
import json
from pathlib import Path
from collections import defaultdict
import statistics

BENCH_DIR = Path(__file__).resolve().parent
CONFIGS = ["A_lexical", "B_dense", "C_hybrid", "D_hybrid_priors", "E_hybrid_graph", "F_two_lane"]


def load_jsonl(p):
    if not Path(p).exists():
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def resolved_requirement_targets(gold_record):
    """Per requirement_id -> set of corpus-verified essential-evidence chunk_ids."""
    out = {}
    for req in gold_record.get("requirements", []):
        ids = set()
        for item in req.get("essential_evidence", []):
            res = item.get("resolution", {})
            if res.get("status") in ("MATCHED", "FUZZY_MATCHED") and res.get("chunk_id"):
                ids.add(res["chunk_id"])
        if ids:
            out[req["requirement_id"]] = ids
    return out


def load_ranked(cfg):
    path = BENCH_DIR / "retrieval_runs" / f"config_{cfg}.jsonl"
    rows = load_jsonl(path)
    ranked = {}
    if cfg == "F_two_lane":
        for r in rows:
            merged = r.get("legislation_lane", []) + r.get("other_lane", [])
            merged.sort(key=lambda x: -x["final_score"])
            ranked[r["scenario_id"]] = [x["chunk_id"] for x in merged]
    else:
        for r in rows:
            ranked[r["scenario_id"]] = [x["chunk_id"] for x in r["results"]]
    return ranked


def main():
    scenarios = {s["scenario_id"]: s for s in load_jsonl(BENCH_DIR / "scenarios_all.jsonl")}
    gold = {g["scenario_id"]: g for g in load_jsonl(BENCH_DIR / "gold_evidence.jsonl")}
    targets = {sid: resolved_requirement_targets(g) for sid, g in gold.items()}
    n_no_resolved_target = sum(1 for sid, t in targets.items() if not t)

    run_data = {cfg: load_ranked(cfg) for cfg in CONFIGS}

    per_scenario = []
    agg = {cfg: defaultdict(list) for cfg in CONFIGS}
    agg_suite = {cfg: defaultdict(lambda: defaultdict(list)) for cfg in CONFIGS}

    for sid, reqs in targets.items():
        if not reqs:
            continue
        suite = scenarios.get(sid, {}).get("suite", "UNKNOWN")
        for cfg in CONFIGS:
            ranked = run_data.get(cfg, {}).get(sid, [])
            sat5 = sat10 = 0
            first_hit_rank = None
            for rid, chunk_ids in reqs.items():
                idx5 = next((i for i, c in enumerate(ranked[:5]) if c in chunk_ids), None)
                idx10 = next((i for i, c in enumerate(ranked[:10]) if c in chunk_ids), None)
                if idx5 is not None:
                    sat5 += 1
                if idx10 is not None:
                    sat10 += 1
            for i, c in enumerate(ranked, 1):
                if any(c in chunk_ids for chunk_ids in reqs.values()):
                    first_hit_rank = i
                    break
            rr = (1.0 / first_hit_rank) if first_hit_rank else 0.0
            total = len(reqs)
            rec = {
                "scenario_id": sid, "config": cfg, "suite": suite,
                "n_requirements_with_verified_target": total,
                "strict_recall_5": sat5 / total, "strict_recall_10": sat10 / total,
                "strict_scenario_complete_10": int(sat10 == total),
                "strict_mrr": round(rr, 4), "n_acquired": len(ranked),
            }
            per_scenario.append(rec)
            for k in ("strict_recall_5", "strict_recall_10", "strict_scenario_complete_10", "strict_mrr"):
                agg[cfg][k].append(rec[k])
                agg_suite[cfg][suite][k].append(rec[k])

    def mean(vals):
        vals = [float(v) for v in vals if v is not None]
        return round(statistics.mean(vals), 4) if vals else None

    summary = {}
    for cfg in CONFIGS:
        a = agg[cfg]
        summary[cfg] = {
            "n_scenarios_with_verified_target": len(a["strict_recall_10"]),
            "strict_recall_5_mean": mean(a["strict_recall_5"]),
            "strict_recall_10_mean": mean(a["strict_recall_10"]),
            "strict_scenario_complete_10_rate": mean(a["strict_scenario_complete_10"]),
            "strict_mrr_mean": mean(a["strict_mrr"]),
        }

    by_suite = {}
    for cfg in CONFIGS:
        by_suite[cfg] = {
            suite: {
                "n": len(vals["strict_recall_10"]),
                "strict_recall_10_mean": mean(vals["strict_recall_10"]),
                "strict_scenario_complete_10_rate": mean(vals["strict_scenario_complete_10"]),
            }
            for suite, vals in agg_suite[cfg].items()
        }

    (BENCH_DIR / "metrics").mkdir(exist_ok=True)
    out = {
        "note": "No LLM judgment used anywhere in this file. Recall is against corpus-verified "
                "(MATCHED/FUZZY_MATCHED) essential-evidence chunk_ids only -- acceptable "
                "alternatives and strong-supporting-only evidence are not counted as targets, so "
                "this is a strict lower bound on true system credit, not an upper bound.",
        "n_scenarios_total": len(gold), "n_scenarios_no_resolved_target": n_no_resolved_target,
        "summary": summary, "by_suite": by_suite,
    }
    json.dump(out, open(BENCH_DIR / "metrics" / "strict_target_recall.json", "w"), indent=2)
    with (BENCH_DIR / "metrics" / "strict_target_recall_per_scenario.jsonl").open("w") as f:
        for rec in per_scenario:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
