"""Diagnostic oracles and intervention traces. Evaluation-only: never feed gold to runtime."""
from __future__ import annotations
from .metrics import evaluate_ranking, _role_ok, FINAL_STATUSES


def action_gains(run,qrels,spec,k=10):
    rows=[]; previous=None
    for step in run.get('trace',[]):
        if 'bundle' not in step: continue
        m=evaluate_ranking(step['bundle'],qrels,spec,k)
        current=m['requirement_coverage']
        rows.append({'scenario_id':run['scenario_id'],'system':run['system'],'operation':step['operation'],
                     'action':step['action'],'coverage':current,
                     'observed_delta':None if previous is None else current-previous,
                     'interpretation':'Sequential observed change, not a causal effect or counterfactual graph-decision accuracy.'})
        previous=current
    return rows


def oracle_coverage(candidates,qrels,spec,k=10,char_budget=18000,lane_caps=None,time_limit=5):
    """Optional exact integer-programming diagnostic over JUDGED candidates.
    Maximise covered requirements subject to final chunk/character budgets.
    This is a label-aware attainable upper bound in this finite pool, NOT a retriever.
    Requires scipy, kept optional so the main pipeline is standard-library-only.
    """
    try:
        import numpy as np
        from scipy.optimize import milp,Bounds,LinearConstraint
    except ImportError as exc:
        raise ImportError('Oracle requires optional scipy and numpy; ordinary evaluation does not') from exc
    lookup={q['chunk_id']:q for q in qrels if q['scenario_id']==spec['scenario_id']}
    if len({c['chunk_id'] for c in candidates})!=len(candidates): raise ValueError('Duplicate oracle candidate')
    for c in candidates:
        q=lookup.get(c['chunk_id'])
        if not q or q.get('annotation_status') not in FINAL_STATUSES: raise ValueError('Oracle candidates must all be judged')
        if c['content_sha256']!=q['content_sha256']: raise ValueError('Stale oracle qrel')
    reqs=[r for r in spec['requirements'] if r.get('mandatory',True)]
    n,m=len(candidates),len(reqs)
    if not m: raise ValueError('No requirements')
    if not n:return {'coverage':0.,'proven_optimal':True,'selected_ids':[],'label_aware':True}
    objective=np.r_[np.zeros(n),-np.ones(m)]
    constraints=[];lower=[];upper=[]
    constraints.append(np.r_[np.ones(n),np.zeros(m)]);lower.append(-np.inf);upper.append(k)
    constraints.append(np.r_[[len(c['text'])+len(c.get('citation','')) for c in candidates],np.zeros(m)]);lower.append(-np.inf);upper.append(char_budget)
    for j,r in enumerate(reqs):
        row=np.zeros(n+m);row[n+j]=1
        for i,c in enumerate(candidates):
            q=lookup[c['chunk_id']]
            applicable=q['applicability']=='APPLICABLE' or (q['applicability']=='CONDITIONAL' and r.get('allow_conditional',False))
            full=q.get('requirements',{}).get(r['id'],{}).get('support')=='FULL'
            if applicable and full and _role_ok(c.get('authority_class','UNKNOWN'),r['source_policy']): row[i]=-1
        constraints.append(row);lower.append(-np.inf);upper.append(0)
    for lane,cap in (lane_caps or {}).items():
        row=np.r_[[int(c.get('lane','other')==lane) for c in candidates],np.zeros(m)]
        constraints.append(row);lower.append(-np.inf);upper.append(cap)
    result=milp(objective,integrality=np.ones(n+m),bounds=Bounds(np.zeros(n+m),np.ones(n+m)),
                constraints=LinearConstraint(np.array(constraints),np.array(lower),np.array(upper)),options={'time_limit':time_limit})
    selected=[candidates[i]['chunk_id'] for i in range(n) if result.x is not None and result.x[i]>.5]
    value=float(sum(result.x[n:]>.5)/m) if result.x is not None else None
    return {'coverage':value,'proven_optimal':result.status==0,'selected_ids':selected,'label_aware':True,
            'solver_status':int(result.status),'solver_message':result.message,
            'scope':'Attainable coverage in this judged candidate pool under specified budgets. Never deploy or compare as a normal system.'}
