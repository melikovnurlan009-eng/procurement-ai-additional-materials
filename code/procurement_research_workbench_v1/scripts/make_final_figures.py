#!/usr/bin/env python3
"""Two DEV-stage thesis figures: matched-system comparison, and the DEV003 s.51 case study.
Reads only saved artifacts; no new retrieval or judging."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/final/figures'
OUT.mkdir(parents=True, exist_ok=True)

d = json.load(open(ROOT / 'results/dev_scale/evaluate/summary.json'))
systems = ['hybrid', 'legal_static', 'planned_multisearch', 'adaptive']
cov = [d['systems'][s]['requirement_coverage']['mean'] for s in systems]
ndcg = [d['systems'][s]['pooled_ndcg']['mean'] for s in systems]

fig, axes = plt.subplots(1, 2, figsize=(10, 4))
colors = ['#9aa5b1', '#4c78a8', '#f58518', '#54a24b']
axes[0].bar(systems, cov, color=colors)
axes[0].set_title('Requirement coverage (pooled, n=37)')
axes[0].set_ylim(0, 1)
axes[0].tick_params(axis='x', rotation=20)
axes[1].bar(systems, ndcg, color=colors)
axes[1].set_title('Pooled nDCG@10 (n=37)')
axes[1].set_ylim(0, 1)
axes[1].tick_params(axis='x', rotation=20)
fig.suptitle('Matched DEV comparison: hybrid vs legal_static vs planned_multisearch vs adaptive')
fig.tight_layout()
fig.savefig(OUT / 'matched_dev_comparison.png', dpi=150)
plt.close(fig)

# DEV003 case study
labels = ['hybrid', 'legal_static', 'planned_multisearch', 'adaptive']
in_final_top10 = [0, 0, 1, 0]
in_acquired = [0, 0, 1, 1]
fig, ax = plt.subplots(figsize=(7, 4))
x = range(len(labels))
ax.bar(x, in_acquired, color='#c9d4e0', label='Recovered into candidate pool')
ax.bar(x, in_final_top10, color='#4c78a8', label='Survived into final top-10')
ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=20)
ax.set_ylim(0, 1.2)
ax.set_ylabel('PA2023 s.51 present (0/1)')
ax.set_title('DEV003 case study: PA2023 s.51 (standstill period) retrieval')
ax.legend()
fig.tight_layout()
fig.savefig(OUT / 'dev003_s51_case_study.png', dpi=150)
plt.close(fig)

print('Figures written to', OUT)
