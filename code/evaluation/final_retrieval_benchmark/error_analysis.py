#!/usr/bin/env python3
"""
For every TEST scenario where the final system (F_two_lane) failed to reach
scenario_complete_10, classify one primary failure category using the candidate-ceiling
diagnosis plus qrel/regime signals already computed. This is a first-pass automatic
classification -- it should be spot-checked, not treated as ground truth.

Categories: QUERY_UNDERSTANDING, VOCABULARY_MISMATCH, WRONG_REGIME, WRONG_LEGAL_TOPIC,
GUIDANCE_BEATS_STATUTE, STATUTE_BEATS_GUIDANCE, GRAPH_SEED_FAILURE, GRAPH_HUB_NOISE,
MISSING_CORPUS_EVIDENCE, GOLD_LABEL_PROBLEM, RANKING_FAILURE, OTHER
"""
import json
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent


def load_jsonl(p):
    if not Path(p).exists():
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def main():
    scenarios = {s["scenario_id"]: s for s in load_jsonl(BENCH_DIR / "scenarios_all.jsonl")}
    per_scenario = load_jsonl(BENCH_DIR / "metrics" / "per_scenario.jsonl")
    ceiling = {r["scenario_id"]: r for r in load_jsonl(BENCH_DIR / "metrics" / "candidate_ceiling.jsonl")}
    final_runs = {r["scenario_id"]: r for r in load_jsonl(BENCH_DIR / "retrieval_runs" / "config_F_two_lane.jsonl")}

    f_metrics = {r["scenario_id"]: r for r in per_scenario if r["config"] == "F_two_lane"}

    failures = []
    for sid, sc in scenarios.items():
        if sc["split"] != "test":
            continue
        m = f_metrics.get(sid)
        if not m or m.get("scenario_complete_10"):
            continue  # not a failure, or not measured
        c = ceiling.get(sid, {})
        diag = c.get("diagnosis", "UNKNOWN")

        if diag == "CANDIDATE_GENERATION_PROBLEM":
            category = "MISSING_CORPUS_EVIDENCE" if not c.get("gold_in_lexical_top10") and not c.get("gold_in_dense_top10") else "QUERY_UNDERSTANDING"
        elif diag == "RANKING_PROBLEM":
            category = "RANKING_FAILURE"
        elif m.get("regime_error"):
            category = "WRONG_REGIME"
        elif sc.get("suite") == "vocabulary_mismatch":
            category = "VOCABULARY_MISMATCH"
        elif sc.get("requires_graph") and c.get("gold_in_union_top50") and not c.get("gold_in_final_top10"):
            category = "GRAPH_SEED_FAILURE"
        else:
            category = "OTHER"

        run = final_runs.get(sid, {})
        top10 = (run.get("legislation_lane", []) + run.get("other_lane", []))[:10]

        failures.append({
            "scenario_id": sid,
            "query": sc["query"],
            "suite": sc.get("suite"),
            "expected_evidence": [r["description"] for r in sc.get("evidence_requirements", [])],
            "top10_citations": [t.get("citation") for t in top10],
            "failure_category": category,
            "short_explanation": f"diagnosis={diag}, regime_error={m.get('regime_error')}, req_coverage_10={m.get('req_coverage_10')}",
        })

    with (BENCH_DIR / "error_analysis_test.jsonl").open("w") as f:
        for row in failures:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(failures)} TEST failures classified -> error_analysis_test.jsonl")


if __name__ == "__main__":
    main()
