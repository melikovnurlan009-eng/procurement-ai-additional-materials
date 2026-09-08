#!/usr/bin/env python3
"""Plot actual bundle metrics only. No supplied fictitious benchmark results."""
import argparse
from pathlib import Path
import statistics
from prw.io import read_jsonl

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--metrics',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();rows=read_jsonl(a.metrics)
    if not rows:raise ValueError('No actual results to plot')
    if any(r.get('annotation_status')=='TEST_FIXTURE' for r in rows):raise ValueError('Fixture numbers cannot be plotted as research results')
    import matplotlib.pyplot as plt
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    systems=sorted({r['system'] for r in rows})
    for metric,label in [('requirement_coverage','Mean requirement coverage'),('scenario_complete','Complete-scenario proportion')]:
        means=[statistics.mean(r[metric] for r in rows if r['system']==s) for s in systems]
        fig,ax=plt.subplots(figsize=(8,4.5));ax.bar(systems,means);ax.set_ylim(0,1);ax.set_ylabel(label)
        ax.tick_params(axis='x',rotation=18)
        for i,v in enumerate(means):ax.text(i,v+.015,f'{v:.3f}',ha='center')
        fig.tight_layout();fig.savefig(out/(metric+'.png'),dpi=200);fig.savefig(out/(metric+'.svg'));plt.close(fig)
    ids=sorted({r['scenario_id'] for r in rows});fig,ax=plt.subplots(figsize=(10,4.5))
    for s in systems:
        lookup={r['scenario_id']:r['requirement_coverage'] for r in rows if r['system']==s}
        if set(lookup)!=set(ids):raise ValueError('Incomplete per-system scenario set')
        ax.plot(ids,[lookup[i] for i in ids],marker='o',label=s)
    ax.set_ylim(-.03,1.03);ax.set_ylabel('Requirement coverage');ax.tick_params(axis='x',rotation=90);ax.legend()
    fig.tight_layout();fig.savefig(out/'per_scenario.png',dpi=200);fig.savefig(out/'per_scenario.svg');plt.close(fig)
    print(out)
if __name__=='__main__':main()
