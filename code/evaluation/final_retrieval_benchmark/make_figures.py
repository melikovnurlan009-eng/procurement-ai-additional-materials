#!/usr/bin/env python3
"""
Generate thesis-ready figures from the final retrieval benchmark's actual result files.
Run after compute_metrics.py and candidate_ceiling.py. No decorative figures without
analytical value -- every figure here reads real numbers from real result files.
"""
import json
from pathlib import Path
from collections import Counter, defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BENCH_DIR = Path(__file__).resolve().parent
FIG_DIR = BENCH_DIR / "figures"
FIG_DIR.mkdir(exist_ok=True)


def load_jsonl(p):
    if not Path(p).exists():
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def fig_suite_distribution():
    scenarios = load_jsonl(BENCH_DIR / "scenarios_all.jsonl")
    if not scenarios:
        return
    by_suite_split = defaultdict(lambda: {"dev": 0, "test": 0})
    for s in scenarios:
        by_suite_split[s["suite"]][s["split"]] += 1
    suites = sorted(by_suite_split)
    dev_counts = [by_suite_split[s]["dev"] for s in suites]
    test_counts = [by_suite_split[s]["test"] for s in suites]
    fig, ax = plt.subplots(figsize=(9, 5))
    x = range(len(suites))
    ax.bar(x, dev_counts, label="dev", color="#4C72B0")
    ax.bar(x, test_counts, bottom=dev_counts, label="test", color="#DD8452")
    ax.set_xticks(list(x))
    ax.set_xticklabels(suites, rotation=30, ha="right")
    ax.set_ylabel("scenario count")
    ax.set_title("Final Retrieval Benchmark: suite distribution (dev vs test)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "suite_distribution.png", dpi=150)
    plt.close(fig)


def fig_topic_distribution():
    scenarios = load_jsonl(BENCH_DIR / "scenarios_all.jsonl")
    if not scenarios:
        return
    topics = Counter(s["topic"] for s in scenarios)
    fig, ax = plt.subplots(figsize=(10, 6))
    items = sorted(topics.items(), key=lambda kv: -kv[1])
    ax.barh([k for k, _ in items], [v for _, v in items], color="#55A868")
    ax.set_xlabel("scenario count")
    ax.set_title("Final Retrieval Benchmark: procurement-lifecycle topic coverage")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "topic_distribution.png", dpi=150)
    plt.close(fig)


def fig_retrieval_comparison():
    summary_path = BENCH_DIR / "metrics" / "summary.json"
    if not summary_path.exists():
        return
    summary = json.load(open(summary_path))
    configs = list(summary.keys())
    metrics_to_plot = ["req_coverage_10_mean", "ndcg10_mean", "hit10_rate"]
    fig, ax = plt.subplots(figsize=(10, 6))
    width = 0.25
    x = range(len(configs))
    for i, m in enumerate(metrics_to_plot):
        vals = [summary[c].get(m) or 0 for c in configs]
        ax.bar([xi + i * width for xi in x], vals, width=width, label=m)
    ax.set_xticks([xi + width for xi in x])
    ax.set_xticklabels(configs, rotation=20, ha="right")
    ax.set_ylim(0, 1.0)
    ax.set_title("Static retrieval comparison: Requirement Coverage@10 / nDCG@10 / Hit@10")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "retrieval_comparison.png", dpi=150)
    plt.close(fig)


def fig_per_suite_heatmap():
    per_scenario_path = BENCH_DIR / "metrics" / "per_scenario.jsonl"
    if not per_scenario_path.exists():
        return
    rows = load_jsonl(per_scenario_path)
    if not rows:
        return
    configs = sorted(set(r["config"] for r in rows))
    suites = sorted(set(r["suite"] for r in rows if r.get("suite")))
    grid = []
    for cfg in configs:
        row_vals = []
        for suite in suites:
            vals = [r["req_coverage_10"] for r in rows if r["config"] == cfg and r["suite"] == suite and r["req_coverage_10"] is not None]
            row_vals.append(sum(vals) / len(vals) if vals else float("nan"))
        grid.append(row_vals)
    fig, ax = plt.subplots(figsize=(1.2 * len(suites) + 3, 1.0 * len(configs) + 2))
    im = ax.imshow(grid, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(suites)))
    ax.set_xticklabels(suites, rotation=30, ha="right")
    ax.set_yticks(range(len(configs)))
    ax.set_yticklabels(configs)
    for i in range(len(configs)):
        for j in range(len(suites)):
            v = grid[i][j]
            if v == v:  # not nan
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="Requirement Coverage@10")
    ax.set_title("Requirement Coverage@10 by config x suite")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "per_suite_heatmap.png", dpi=150)
    plt.close(fig)


def fig_candidate_ceiling():
    path = BENCH_DIR / "metrics" / "candidate_ceiling_summary.json"
    if not path.exists():
        return
    data = json.load(open(path))
    labels = list(data.keys())
    values = list(data.values())
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"OK_FOUND_IN_FINAL_TOP10": "#55A868", "RANKING_PROBLEM": "#DD8452",
              "CANDIDATE_GENERATION_PROBLEM": "#C44E52", "no_resolved_gold": "#8172B2"}
    bar_colors = [colors.get(l, "#999999") for l in labels]
    ax.bar(labels, values, color=bar_colors)
    ax.set_ylabel("scenario count")
    ax.set_title("Candidate-generation ceiling: where do gold-evidence failures occur?")
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "candidate_ceiling.png", dpi=150)
    plt.close(fig)


def main():
    fig_suite_distribution()
    fig_topic_distribution()
    fig_retrieval_comparison()
    fig_per_suite_heatmap()
    fig_candidate_ceiling()
    print("Figures written to", FIG_DIR)


if __name__ == "__main__":
    main()
