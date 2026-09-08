#!/usr/bin/env python3
"""
Build FINAL_RESULTS_TABLE.csv, PER_SUITE_RESULTS.csv and PAIRWISE_STATISTICS.csv for the
standalone static-benchmark configs (A-F), from already-computed metrics/per_scenario.jsonl and
metrics/strict_target_recall_per_scenario.jsonl. No new judging, no new retrieval.
"""
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
OUT_DIR = BENCH_DIR.parents[1] / "procurement_research_workbench_v1" / "results" / "final"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONFIGS = ["A_lexical", "B_dense", "C_hybrid", "D_hybrid_priors", "E_hybrid_graph", "F_two_lane"]


def load_jsonl(p):
    return [json.loads(l) for l in open(p)] if Path(p).exists() else []


def mean(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 4) if vals else None


def paired_bootstrap(a_vals, b_vals, n_boot=2000, seed=1234):
    """a_vals, b_vals aligned by scenario. Returns delta, ci95, wins/ties/losses, sign p (approx)."""
    diffs = [a - b for a, b in zip(a_vals, b_vals)]
    n = len(diffs)
    wins = sum(1 for d in diffs if d > 0)
    losses = sum(1 for d in diffs if d < 0)
    ties = n - wins - losses
    delta = round(statistics.mean(diffs), 4)
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        boots.append(statistics.mean(sample))
    boots.sort()
    lo = boots[int(0.025 * n_boot)]
    hi = boots[int(0.975 * n_boot) - 1]
    # two-sided exact sign test p-value (ties excluded), matching prw/metrics.py's convention
    m = wins + losses
    if m == 0:
        p = 1.0
    else:
        k = min(wins, losses)
        from math import comb
        p = sum(comb(m, i) for i in range(0, k + 1)) * 2 / (2 ** m)
        p = min(p, 1.0)
    return {"delta": delta, "ci95": [round(lo, 4), round(hi, 4)], "wins": wins, "ties": ties,
            "losses": losses, "n": n, "exact_two_sided_sign_p": p}


def main():
    per = load_jsonl(BENCH_DIR / "metrics/per_scenario.jsonl")
    strict = load_jsonl(BENCH_DIR / "metrics/strict_target_recall_per_scenario.jsonl")

    by_cfg = defaultdict(list)
    for r in per:
        by_cfg[r["config"]].append(r)
    strict_by_cfg = defaultdict(dict)
    for r in strict:
        strict_by_cfg[r["config"]][r["scenario_id"]] = r

    # ---- FINAL_RESULTS_TABLE.csv ----
    rows = []
    for cfg in CONFIGS:
        rs = by_cfg.get(cfg, [])
        srs = strict_by_cfg.get(cfg, {})
        known_auth = [r["authority_top1_ok"] for r in rs if r["authority_top1_ok"] is not None]
        rows.append({
            "config": cfg, "n_scenarios": len(rs),
            "ndcg10_mean": mean([r["ndcg10"] for r in rs]),
            "hit10_rate": mean([r["hit10"] for r in rs]),
            "mrr_mean": mean([r["mrr"] for r in rs]),
            "req_coverage_5_mean": mean([r["req_coverage_5"] for r in rs]),
            "req_coverage_10_mean": mean([r["req_coverage_10"] for r in rs]),
            "scenario_complete_10_rate": mean([r["scenario_complete_10"] for r in rs]),
            "regime_error_rate": mean([r["regime_error"] for r in rs]),
            "authority_top1_ok_rate": mean(known_auth),
            "strict_recall_10_mean": mean([v["strict_recall_10"] for v in srs.values()]),
            "strict_scenario_complete_10_rate": mean([v["strict_scenario_complete_10"] for v in srs.values()]),
            "strict_mrr_mean": mean([v["strict_mrr"] for v in srs.values()]),
        })
    with open(OUT_DIR / "FINAL_RESULTS_TABLE.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print("FINAL_RESULTS_TABLE.csv:")
    for r in rows:
        print(" ", r["config"], "ndcg10=", r["ndcg10_mean"], "req_cov10=", r["req_coverage_10_mean"],
              "regime_err=", r["regime_error_rate"], "strict_recall10=", r["strict_recall_10_mean"])

    # ---- PER_SUITE_RESULTS.csv ----
    suite_rows = []
    for cfg in CONFIGS:
        rs = by_cfg.get(cfg, [])
        by_suite = defaultdict(list)
        for r in rs:
            by_suite[r["suite"]].append(r)
        for suite, srs2 in sorted(by_suite.items()):
            suite_rows.append({
                "config": cfg, "suite": suite, "n": len(srs2),
                "ndcg10_mean": mean([r["ndcg10"] for r in srs2]),
                "req_coverage_10_mean": mean([r["req_coverage_10"] for r in srs2]),
                "scenario_complete_10_rate": mean([r["scenario_complete_10"] for r in srs2]),
                "regime_error_rate": mean([r["regime_error"] for r in srs2]),
            })
    with open(OUT_DIR / "PER_SUITE_RESULTS.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(suite_rows[0].keys()))
        w.writeheader(); w.writerows(suite_rows)
    print(f"PER_SUITE_RESULTS.csv: {len(suite_rows)} rows")

    # ---- PAIRWISE_STATISTICS.csv (standalone configs, paired by scenario_id, req_coverage_10) ----
    by_cfg_by_sid = {cfg: {r["scenario_id"]: r["req_coverage_10"] for r in rs} for cfg, rs in by_cfg.items()}
    pair_rows = []
    for i, a in enumerate(CONFIGS):
        for b in CONFIGS[i + 1:]:
            common = sorted(set(by_cfg_by_sid[a]) & set(by_cfg_by_sid[b]))
            common = [s for s in common if by_cfg_by_sid[a][s] is not None and by_cfg_by_sid[b][s] is not None]
            av = [by_cfg_by_sid[a][s] for s in common]
            bv = [by_cfg_by_sid[b][s] for s in common]
            res = paired_bootstrap(av, bv)
            pair_rows.append({"metric": "req_coverage_10", "system_a": a, "system_b": b, **res})
    with open(OUT_DIR / "PAIRWISE_STATISTICS.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pair_rows[0].keys()))
        w.writeheader(); w.writerows(pair_rows)
    print(f"PAIRWISE_STATISTICS.csv: {len(pair_rows)} rows")
    for r in pair_rows:
        if r["system_a"] in ("A_lexical", "D_hybrid_priors") or r["system_b"] == "F_two_lane":
            print(" ", r["system_a"], "vs", r["system_b"], "delta=", r["delta"], "p=", round(r["exact_two_sided_sign_p"], 5),
                  "wins/ties/losses=", r["wins"], r["ties"], r["losses"])


if __name__ == "__main__":
    main()
