#!/usr/bin/env python3
"""Adaptive intervention/cost figure: fallback rate and token cost, DEV vs TEST, adaptive vs planned_multisearch."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/final/figures'

data = {
    'DEV planned_multisearch': {'fallback': 0.0, 'tokens': 29326, 'scenarios': 40},
    'DEV adaptive': {'fallback': 0.525, 'tokens': 1271466, 'scenarios': 40},
    'TEST planned_multisearch': {'fallback': 0.0, 'tokens': 15365, 'scenarios': 20},
    'TEST adaptive': {'fallback': 0.45, 'tokens': 604504, 'scenarios': 20},
}
labels = list(data.keys())
fallback = [data[l]['fallback'] for l in labels]
tok_per_scenario = [data[l]['tokens'] / data[l]['scenarios'] for l in labels]

fig, axes = plt.subplots(1, 2, figsize=(11, 4))
colors = ['#4c78a8', '#f58518', '#4c78a8', '#f58518']
axes[0].bar(labels, fallback, color=colors)
axes[0].set_title('Controller fallback rate')
axes[0].set_ylim(0, 1)
axes[0].tick_params(axis='x', rotation=25)
axes[1].bar(labels, tok_per_scenario, color=colors)
axes[1].set_title('Tokens per scenario')
axes[1].tick_params(axis='x', rotation=25)
fig.suptitle('Adaptive intervention cost: fallback rate and token usage, DEV vs frozen TEST')
fig.tight_layout()
fig.savefig(OUT / 'adaptive_intervention_cost.png', dpi=150)
print('Written', OUT / 'adaptive_intervention_cost.png')
