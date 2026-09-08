#!/usr/bin/env python3
"""
Regenerates the candidate-ceiling figure from the CORRECTED classification
(candidate_ceiling_CORRECTED_summary.json), produced during the 2026-09-07/08
finalization audit. The original make_figures.py::fig_candidate_ceiling() is left
untouched and still reads the pre-correction candidate_ceiling_summary.json,
producing the original (buggy, 15/40/5) candidate_ceiling.png for audit-trail
purposes. This script produces a separate, additional file,
candidate_ceiling_CORRECTED.png, with the corrected 24/31/5 counts. See
provenance/CHANGELOG_FINALIZATION.md for the root-cause explanation.
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BENCH_DIR = Path(__file__).resolve().parent
FIG_DIR = BENCH_DIR / "figures"
FIG_DIR.mkdir(exist_ok=True)


def main():
    path = BENCH_DIR / "metrics" / "candidate_ceiling_CORRECTED_summary.json"
    data = json.load(open(path))
    order = ["OK_FOUND_IN_FINAL_TOP10", "CANDIDATE_GENERATION_PROBLEM", "RANKING_PROBLEM"]
    labels = [l for l in order if l in data] + [l for l in data if l not in order]
    values = [data[l] for l in labels]
    colors = {"OK_FOUND_IN_FINAL_TOP10": "#55A868", "RANKING_PROBLEM": "#DD8452",
              "CANDIDATE_GENERATION_PROBLEM": "#C44E52", "no_resolved_gold": "#8172B2"}
    bar_colors = [colors.get(l, "#999999") for l in labels]
    total = sum(values)
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, color=bar_colors)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.5, f"{v} ({v/total*100:.1f}%)",
                ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("scenario count")
    ax.set_title("Candidate-generation ceiling (CORRECTED classification order):\n"
                  "where do gold-evidence failures occur?")
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "candidate_ceiling_CORRECTED.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {FIG_DIR / 'candidate_ceiling_CORRECTED.png'} with counts: {data}")


if __name__ == "__main__":
    main()
