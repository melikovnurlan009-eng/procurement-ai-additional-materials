#!/usr/bin/env python3
"""Summarize actual completed silver bundle metrics, with paired and per-judge sensitivity."""
import argparse
from pathlib import Path
import statistics
import itertools
import copy
from prw.io import read_jsonl,write_json
from prw.metrics import paired_bootstrap
from prw.bundles import score_bundle

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--metrics',required=True);p.add_argument('--raw');p.add_argument('--runs',nargs='+');p.add_argument('--requirements');p.add_argument('--out',required=True)
    a=p.parse_args();rows=read_jsonl(a.metrics);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    keys=[(r['system'],r['scenario_id']) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate system/scenario measurements')
    systems={s:[r for r in rows if r['system']==s] for s in sorted({r['system'] for r in rows})}
    if any({r['scenario_id'] for r in v}!={r['scenario_id'] for r in next(iter(systems.values()))} for v in systems.values()):
        raise ValueError('Unequal evaluated scenario sets; finish missing judgments before comparison')
    summary={s:{'n':len(v),'coverage':statistics.mean(x['requirement_coverage'] for x in v),
                'complete':statistics.mean(x['scenario_complete'] for x in v)} for s,v in systems.items()}
    paired={a+' -> '+b:paired_bootstrap(systems[a],systems[b]) for a,b in itertools.combinations(systems,2)}
    report={'annotation_basis':'THREE_JUDGE_SILVER_NOT_EXPERT_GOLD','systems':summary,'paired':paired,
            'uncertainty':'Scenario-group sampling intervals conditional on the labels; correlated judge errors are not captured.'}
    if a.raw:
        raw=read_jsonl(a.raw);groups={}
        for r in raw:groups.setdefault((r['scenario_id'],r['bundle_hash']),[]).append(r)
        disagreement=0;total=0
        for values in groups.values():
            if len(values)!=3:continue
            for rid in values[0]['requirements']:
                total+=1
                disagreement+=len({(r['requirements'][rid]['support'],r['requirements'][rid]['applicability']) for r in values})>1
        report['requirement_disagreement']={'different_support_or_applicability':disagreement,'assessed_requirements':total}
        if a.runs and a.requirements:
            specs={r['scenario_id']:r for r in read_jsonl(a.requirements)};runs=[r for f in a.runs for r in read_jsonl(f)]
            from prw.bundles import bundle_hash
            sensitivity={}
            for judge in ('J1','J2','J3'):
                metrics=[]
                for run in runs:
                    match=[r for r in groups.get((run['scenario_id'],bundle_hash(run['ranking'])),[]) if r['judge_id']==judge]
                    if not match:raise ValueError('Missing judge-specific bundle assessment')
                    q=copy.deepcopy(match[0]);q['annotation_status']='LLM_SINGLE_JUDGE_SILVER'
                    metrics.append(score_bundle(run,specs[run['scenario_id']],q))
                bysystem={s:[r for r in metrics if r['system']==s] for s in systems}
                sensitivity[judge]={s:statistics.mean(r['requirement_coverage'] for r in v) for s,v in bysystem.items()}
            report['judge_sensitivity']=sensitivity
        else:report['judge_sensitivity_status']='Supply --runs and --requirements to compute per-judge outcome sensitivity.'
    write_json(out/'bundle_report.json',report)
    lines=['# Bundle evidence-sufficiency comparison','','These are LLM silver assessments, not independently verified legal accuracy.','',
           '| System | Scenarios | Requirement coverage | Scenario complete |','|---|---:|---:|---:|']
    for s,v in summary.items():lines.append(f"| {s} | {v['n']} | {v['coverage']:.3f} | {v['complete']:.3f} |")
    lines+=['','## Paired comparisons','']
    for name,v in paired.items():lines.append(f'- {name}: `{v}`')
    lines+=['','## Interpretation','Compare adaptive against planned_multisearch as well as static. A positive estimate does not prove improvement when uncertainty or judge sensitivity remains substantial. Report actual operation/token costs and corpus gaps separately.']
    (out/'bundle_report.md').write_text('\n'.join(lines)+'\n')
    print(out/'bundle_report.md')
if __name__=='__main__':main()
