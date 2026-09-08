"""Command-line execution with checkpoints. Paid model calls always require opt-in."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .io import read_json, read_jsonl, write_json, write_jsonl, digest, file_hash, append_event, now
from .benchmark import audit, freeze, check_freeze
from .contracts import Scenario
from .adapters import load_backend
from .controller import run_static, AdaptiveController
from .pooling import build_pool
from .judging import judge_three, adjudicate_consensus, adjudicate_model
from .llm import Budget, HTTPJsonModel
from .metrics import evaluate_ranking, macro_summary, paired_bootstrap, judge_agreement
from .answers import generate_answer, judge_answer_three, consensus_answers, adjudicate_answer
from .bundles import judge_bundle_three,consensus_bundles,adjudicate_bundle,score_bundle

ROOT=Path(__file__).resolve().parents[1]


def model_set(args,keys):
    conf=read_json(args.models); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    budget=Budget(out/'model_budget.json',args.max_requests)
    result={}
    for key in keys:
        val=conf[key]
        configs=val if isinstance(val,list) else [val]
        models=[HTTPJsonModel(c,budget,out/'model_events.jsonl',args.allow_network) for c in configs]
        result[key]=models if isinstance(val,list) else models[0]
    return result



def evaluation_freeze(args, public=None, specs=None):
    """A test label definition cannot be silently changed after the retrieval freeze."""
    rows=list(public or [])+list(specs or [])
    if not any(r.get('split')=='test' for r in rows): return
    if not getattr(args,'freeze',None):
        raise ValueError('Test judging/evaluation requires --freeze to protect the scenario and requirement definitions')
    record=read_json(args.freeze)
    if getattr(args,'scenarios',None) and file_hash(args.scenarios)!=record['test_sha256']:
        raise ValueError('Test scenarios differ from frozen file')
    if getattr(args,'requirements',None) and file_hash(args.requirements)!=record['requirements_sha256']:
        raise ValueError('Test evaluator requirements changed after freeze')


def cmd_validate(args):
    report=audit(args.dev,args.test,args.dev_requirements,args.test_requirements)
    write_json(args.output,report)
    print(json.dumps({'status':report['status'],'n_dev':report['n_dev'],'n_test':report['n_test'],'output':args.output},indent=2))
    if report['errors']: raise SystemExit(1)


def cmd_run(args):
    scenarios=read_jsonl(args.scenarios); config=read_json(args.config); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    if any(r.get('split')=='test' for r in scenarios):
        if not args.freeze: raise ValueError('Test execution requires a pre-existing --freeze record')
        check_freeze(args.freeze,args.scenarios,args.config,args.snapshot,ROOT)
    signature={'scenarios_sha256':file_hash(args.scenarios),'config_sha256':file_hash(args.config),'snapshot':args.snapshot,
               'system':args.system,'backend_factory':args.backend,'code_sha256':{p.name:file_hash(p) for p in sorted((ROOT/'prw').glob('*.py'))}}
    if args.system in ('adaptive','planned_multisearch') and not args.allow_network:
        raise ValueError('Adaptive runs require --allow-network and accessible model credentials; no synthetic fallback experiment is permitted')
    models=model_set(args,['controller']) if args.system in ('adaptive','planned_multisearch') else {}
    if models: models['controller'].preflight()
    signature['model_identity']=models['controller'].identity if models else None
    manifest=out/'manifest.json'
    if manifest.exists() and read_json(manifest)['signature']!=signature: raise ValueError('Output directory belongs to a different run; choose a new path')
    backend=load_backend(args.backend)
    write_json(manifest,{'signature':signature,'started':now(),'backend_capabilities':sorted(backend.capabilities),
                         'model_identity':models['controller'].identity if models else None,
                         'experiment_status':'EXECUTED_AGAINST_CONFIGURED_BACKEND'})
    results=[]
    for obj in scenarios:
        dest=out/'checkpoints'/(obj['scenario_id']+'.json')
        if dest.exists(): result=read_json(dest)
        else:
            scenario=Scenario.from_public(obj)
            result=(AdaptiveController(backend,models['controller'],config).run(scenario,args.system)
                    if models else run_static(backend,scenario,config,args.system))
            result.update({'scenario_group_id':obj.get('scenario_group_id',obj['scenario_id']),
                           'suite':obj.get('suite'),'scenario_sha256':digest(obj),'snapshot':args.snapshot})
            write_json(dest,result)
            append_event(out/'events.jsonl',{'scenario_id':obj['scenario_id'],'status':'completed','retrieval_operations':result['retrieval_operations']})
        results.append(result); write_jsonl(out/'runs.jsonl',results)
    print(str(out/'runs.jsonl'))


def cmd_pool(args):
    runs=[r for path in args.runs for r in read_jsonl(path)]
    refs=read_jsonl(args.references) if args.references else None
    pool,membership=build_pool(runs,refs,args.depth,args.final_only)
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    write_jsonl(out/'candidate_pool.jsonl',pool); write_jsonl(out/'membership_private.jsonl',membership)
    write_json(out/'cost_plan.json',{'candidate_pairs':len(pool),'minimum_judge_requests':3*len(pool),
        'worst_case_with_one_adjudicator':4*len(pool),'source_characters':sum(len(x['evidence']['text']) for x in pool),
        'estimated_input_tokens_note':'No token or dollar estimate is asserted: add actual tokenizer and configured provider prices.',
        'judgment_scope':'FINAL_OUTPUT_UNION' if args.final_only else 'ALL_SAVED_ACQUIRED_CANDIDATES',
        'not_exhaustive_corpus_qrels':True})
    print(json.dumps(read_json(out/'cost_plan.json'),indent=2))


def cmd_judge(args):
    pool=read_jsonl(args.pool); public={r['scenario_id']:r for r in read_jsonl(args.scenarios)}
    specs={r['scenario_id']:r for r in read_jsonl(args.requirements)}
    evaluation_freeze(args,public.values(),specs.values())
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    if not args.allow_network:
        print(json.dumps({'dry_run':True,'pairs':len(pool),'minimum_requests':len(pool)*3,'unjudged':True},indent=2)); return
    models=model_set(args,['judges']+(['adjudicator'] if args.adjudicate else []))
    # Same model names across slots are allowed but explicitly reported as repeated-model judgments.
    identities=[m.identity for m in models['judges']]
    write_json(out/'judge_manifest.json',{'identities':identities,'distinct_configured_identities':len({digest(x) for x in identities}),
        'rubric':'common pointwise rubric, separate isolated requests','warning':'Agreement is not expert-ground-truth accuracy.'})
    finals=[]; raw=[]; queue=[]; failures=[]
    for pair in pool:
        sid=pair['scenario_id']; dest=out/'final_cache'/(digest([pair,public[sid],specs[sid],identities,args.adjudicate,models['adjudicator'].identity if args.adjudicate else None,__import__('prw.judging',fromlist=['RETRIEVAL_RUBRIC']).RETRIEVAL_RUBRIC])+'.json')
        rawdest=out/'raw_cache'/(digest([pair,public[sid],specs[sid],identities,__import__('prw.judging',fromlist=['RETRIEVAL_RUBRIC']).RETRIEVAL_RUBRIC])+'.json')
        try:
            if dest.exists():
                final=read_json(dest); rows=read_json(rawdest)
            else:
                rows=judge_three(models['judges'],public[sid],specs[sid],pair,out/'requests_cache')
                final=adjudicate_consensus(rows)
                if final['annotation_status']=='REQUIRES_ADJUDICATION' and args.adjudicate:
                    final=adjudicate_model(models['adjudicator'],public[sid],specs[sid],pair,rows)
                write_json(rawdest,rows); write_json(dest,final)
            raw.extend(rows)
            if final['annotation_status'] in ('LLM_CONSENSUS_SILVER','LLM_ADJUDICATED_SILVER'): finals.append(final)
            else: queue.append(final)
        except ValueError as exc:
            # A compliance failure surviving its one repair attempt is a real, reported finding
            # about this item -- not a reason to discard every other item already judged this
            # run. A FatalModelError (budget/network) is NOT caught here and still stops the run.
            failure={'scenario_id':sid,'candidate_id':pair['candidate_id'],'error':str(exc)}
            failures.append(failure); append_event(out/'errors.jsonl',failure)
        write_jsonl(out/'qrels_silver.jsonl',finals); write_jsonl(out/'judgments_raw.jsonl',raw); write_jsonl(out/'review_queue.jsonl',queue)
    if failures: write_json(out/'judge_failures.json',{'failed_items':len(failures),'failures':failures})
    write_json(out/'agreement.json',judge_agreement([r for r in raw if r.get('relevance_grade') is not None]))
    print(json.dumps({'judged_final':len(finals),'needs_review':len(queue),'failed_items':len(failures),'outputs':str(out)},indent=2))


def cmd_evaluate(args):
    specs={r['scenario_id']:r for r in read_jsonl(args.requirements)}; qrels=read_jsonl(args.qrels)
    evaluation_freeze(args,specs=specs.values())
    runs=[r for path in args.runs for r in read_jsonl(path)]; by_system={}; allmetrics=[]
    for run in runs:
        if run['scenario_id'] not in specs: raise ValueError('Missing evaluator requirements')
        result=evaluate_ranking(run['ranking'],qrels,specs[run['scenario_id']],args.k)
        result.update({'system':run['system'],'suite':run.get('suite'),'scenario_group_id':run.get('scenario_group_id',run['scenario_id']),
                       'retrieval_operations':run.get('retrieval_operations'),'elapsed_seconds':run.get('elapsed_seconds'),
                       'corpus_support_status':specs[run['scenario_id']].get('corpus_support_status','UNKNOWN')})
        by_system.setdefault(run['system'],[]).append(result); allmetrics.append(result)
    summaries={s:macro_summary(rows) for s,rows in by_system.items()}
    comparisons={}
    systems=sorted(by_system)
    for i,a in enumerate(systems):
        for b in systems[i+1:]:
            comparisons[a+' -> '+b]=paired_bootstrap(by_system[a],by_system[b])
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    write_jsonl(out/'per_scenario.jsonl',allmetrics)
    write_json(out/'summary.json',{'systems':summaries,'paired':comparisons,'interpretation':'Pointwise conservative coverage and pooled silver ranking metrics. Use judge-bundles for primary complementary-evidence sufficiency; no exhaustive-corpus recall or expert legal accuracy claimed.'})
    suites={}
    for s,rows in by_system.items():
        suites[s]={t:macro_summary([r for r in rows if r['suite']==t]) for t in sorted({r['suite'] for r in rows if r['suite']})}
    write_json(out/'by_suite.json',suites)
    lines=['# Pointwise retrieval diagnostics','', 'Labels: pooled silver judgments. Scenario sampling intervals do not capture shared judge error.','',
           '| System | Scenarios | Pointwise coverage | Pointwise complete | Pooled nDCG | Hit >=2 |', '|---|---:|---:|---:|---:|---:|']
    f=lambda x:'N/A' if x is None else f'{x:.3f}'
    for s,m in summaries.items():
        lines.append(f"| {s} | {m['n_scenarios']} | {f(m['requirement_coverage']['mean'])} | {f(m['scenario_complete']['mean'])} | {f(m['pooled_ndcg']['mean'])} | {f(m['hit_ge2']['mean'])} |")
    lines+=['','## Interpretation limits','No system is declared superior automatically. Inspect paired differences, the budget-matched multi-search control, unknown applicability, corpus support, and judge sensitivity.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    print(str(out/'report.md'))


def cmd_answers(args):
    public={r['scenario_id']:r for r in read_jsonl(args.scenarios)}; runs=read_jsonl(args.runs[0]); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    evaluation_freeze(args,public.values())
    if not args.allow_network: print(json.dumps({'dry_run':True,'answer_requests':len(runs)})); return
    model=model_set(args,['generator'])['generator']; results=[]
    for run in runs:
        key=digest([run,public[run['scenario_id']],model.identity,__import__('prw.answers',fromlist=['ANSWER_PROMPT']).ANSWER_PROMPT]); dest=out/'cache'/(key+'.json')
        answer=read_json(dest) if dest.exists() else generate_answer(model,public[run['scenario_id']],run)
        write_json(dest,answer); results.append(answer); write_jsonl(out/'answers.jsonl',results)
    print(str(out/'answers.jsonl'))


def cmd_judge_answers(args):
    public={r['scenario_id']:r for r in read_jsonl(args.scenarios)}; specs={r['scenario_id']:r for r in read_jsonl(args.requirements)}
    evaluation_freeze(args,public.values(),specs.values())
    answers=read_jsonl(args.answers); refs={}
    if args.references:
        for row in read_jsonl(args.references): refs.setdefault(row['scenario_id'],[]).append(row['evidence'])
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    if not args.allow_network: print(json.dumps({'dry_run':True,'answers':len(answers),'judge_requests':3*len(answers)})); return
    configured=model_set(args,['judges']+(['adjudicator'] if args.adjudicate else [])); models=configured['judges']; raw=[]; finals=[]
    for answer in answers:
        sid=answer['scenario_id']; key=digest([answer,specs[sid],refs.get(sid),[m.identity for m in models],__import__('prw.answers',fromlist=['ANSWER_JUDGE_PROMPT']).ANSWER_JUDGE_PROMPT])
        dest=out/'cache'/(key+'.json')
        rows=read_json(dest) if dest.exists() else judge_answer_three(models,public[sid],specs[sid],answer,refs.get(sid))
        write_json(dest,rows); raw.extend(rows); final=consensus_answers(rows)
        if final['annotation_status']=='REQUIRES_ADJUDICATION' and args.adjudicate:
            apath=out/'adjudication_cache'/(digest([key,configured['adjudicator'].identity])+'.json')
            final=read_json(apath) if apath.exists() else adjudicate_answer(configured['adjudicator'],public[sid],specs[sid],answer,rows,refs.get(sid))
            write_json(apath,final)
        final['system']=answer['system']; finals.append(final)
        write_jsonl(out/'answer_judgments_raw.jsonl',raw); write_jsonl(out/'answer_consensus.jsonl',finals)
    print(str(out/'answer_consensus.jsonl'))


def cmd_bundles(args):
    public={r['scenario_id']:r for r in read_jsonl(args.scenarios)}
    specs={r['scenario_id']:r for r in read_jsonl(args.requirements)}
    runs=[r for p in args.runs for r in read_jsonl(p)]
    evaluation_freeze(args,public.values(),specs.values())
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if not args.allow_network:
        print(json.dumps({'dry_run':True,'bundles':len(runs),'minimum_requests':3*len(runs)}));return
    models=model_set(args,['judges']+(['adjudicator'] if args.adjudicate else []));raw=[];final=[];metrics=[];queue=[];failures=[]
    for run in runs:
        sid=run['scenario_id']
        key=digest([run['ranking'],public[sid],specs[sid],[m.identity for m in models['judges']],args.adjudicate,__import__('prw.bundles',fromlist=['BUNDLE_PROMPT']).BUNDLE_PROMPT])
        dest=out/'cache'/(key+'.json')
        try:
            rows=read_json(dest) if dest.exists() else judge_bundle_three(models['judges'],public[sid],specs[sid],run)
            write_json(dest,rows);raw.extend(rows);label=consensus_bundles(rows)
            if label['annotation_status']=='REQUIRES_ADJUDICATION' and args.adjudicate:
                adest=out/'adjudication_cache'/(digest([key,models['adjudicator'].identity])+'.json')
                label=read_json(adest) if adest.exists() else adjudicate_bundle(models['adjudicator'],public[sid],specs[sid],run,rows)
                write_json(adest,label)
            label['system']=run['system'];final.append(label)
            if label['annotation_status']=='REQUIRES_ADJUDICATION':queue.append(label)
            else: metrics.append(score_bundle(run,specs[sid],label))
        except ValueError as exc:
            # A bundle that still fails after its one bounded repair attempt is a real, reported
            # finding, not a reason to discard every other bundle already judged this run. A
            # FatalModelError (budget/network) is NOT caught here and still stops the run.
            failure={'scenario_id':sid,'system':run['system'],'error':str(exc)}
            failures.append(failure); append_event(out/'bundle_errors.jsonl',failure)
        write_jsonl(out/'bundle_judgments_raw.jsonl',raw);write_jsonl(out/'bundle_consensus.jsonl',final)
        write_jsonl(out/'bundle_metrics.jsonl',metrics);write_jsonl(out/'bundle_review_queue.jsonl',queue)
    if failures: write_json(out/'bundle_failures.json',{'failed_bundles':len(failures),'failures':failures})
    # Do not summarize an incomplete system as though omitted disagreements were irrelevant.
    if queue:
        write_json(out/'summary_status.json',{'status':'INCOMPLETE_ADJUDICATION','unresolved_bundles':len(queue),'failed_bundles':len(failures)})
    else:
        systems={}
        for r in metrics:systems.setdefault(r['system'],[]).append(r)
        import statistics
        summary={k:{'n':len(v),'requirement_coverage':statistics.mean(r['requirement_coverage'] for r in v),'scenario_complete':statistics.mean(r['scenario_complete'] for r in v)} for k,v in systems.items()}
        write_json(out/'summary_status.json',{'status':'COMPLETE_SILVER' if not failures else 'PARTIAL_SILVER_SOME_BUNDLES_FAILED','systems':summary,'failed_bundles':len(failures)})
    print(str(out/'summary_status.json'))


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    v=sub.add_parser('validate-data'); v.add_argument('--dev',default=str(ROOT/'data/dev/scenarios.jsonl')); v.add_argument('--test',default=str(ROOT/'data/test_sealed/scenarios.jsonl'))
    v.add_argument('--dev-requirements',default=str(ROOT/'data/dev/requirements.jsonl')); v.add_argument('--test-requirements',default=str(ROOT/'data/test_sealed/requirements.jsonl')); v.add_argument('--output',default=str(ROOT/'validation/dataset_audit.json')); v.set_defaults(func=cmd_validate)
    f=sub.add_parser('freeze'); f.add_argument('--test',required=True); f.add_argument('--requirements',required=True); f.add_argument('--configs',nargs='+',required=True); f.add_argument('--output',required=True); f.add_argument('--snapshot',required=True)
    f.set_defaults(func=lambda a: print(json.dumps(freeze(a.test,a.requirements,a.configs,a.output,a.snapshot,ROOT),indent=2)))
    r=sub.add_parser('run'); r.add_argument('--scenarios',required=True); r.add_argument('--system',required=True,choices=['lexical','dense','hybrid','hybrid_priors','hybrid_graph','hybrid_full','legal_static','planned_multisearch','adaptive']); r.add_argument('--config',default=str(ROOT/'configs/retrieval.json')); r.add_argument('--backend',default='prw.adapters:production_backend'); r.add_argument('--snapshot',required=True); r.add_argument('--freeze'); r.set_defaults(func=cmd_run)
    po=sub.add_parser('pool'); po.add_argument('--runs',nargs='+',required=True); po.add_argument('--references'); po.add_argument('--depth',type=int,default=20); po.add_argument('--final-only',action='store_true'); po.set_defaults(func=cmd_pool)
    j=sub.add_parser('judge'); j.add_argument('--pool',required=True); j.add_argument('--scenarios',required=True); j.add_argument('--requirements',required=True); j.add_argument('--adjudicate',action='store_true'); j.set_defaults(func=cmd_judge)
    e=sub.add_parser('evaluate'); e.add_argument('--runs',nargs='+',required=True); e.add_argument('--qrels',required=True); e.add_argument('--requirements',required=True); e.add_argument('--k',type=int,default=10); e.set_defaults(func=cmd_evaluate)
    a=sub.add_parser('answers'); a.add_argument('--runs',nargs=1,required=True); a.add_argument('--scenarios',required=True); a.set_defaults(func=cmd_answers)
    aj=sub.add_parser('judge-answers'); aj.add_argument('--answers',required=True); aj.add_argument('--scenarios',required=True); aj.add_argument('--requirements',required=True); aj.add_argument('--references'); aj.add_argument('--adjudicate',action='store_true'); aj.set_defaults(func=cmd_judge_answers)
    bj=sub.add_parser('judge-bundles');bj.add_argument('--runs',nargs='+',required=True);bj.add_argument('--scenarios',required=True);bj.add_argument('--requirements',required=True);bj.add_argument('--adjudicate',action='store_true');bj.set_defaults(func=cmd_bundles)
    for parser in (r,po,j,e,a,aj,bj): parser.add_argument('--out',required=True)
    for parser in (j,e,a,aj,bj): parser.add_argument('--freeze')
    for parser in (r,j,a,aj,bj):
        parser.add_argument('--models',default=str(ROOT/'configs/models.json')); parser.add_argument('--allow-network',action='store_true'); parser.add_argument('--max-requests',type=int,default=100)
    args=p.parse_args(); args.func(args)

if __name__=='__main__': main()
