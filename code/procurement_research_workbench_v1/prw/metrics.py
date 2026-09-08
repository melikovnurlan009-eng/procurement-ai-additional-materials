"""Requirement-based, pooled-silver metrics with strict judgment completeness.
No exhaustive-corpus recall or legal accuracy is inferred from retrieval labels.
"""
from __future__ import annotations
import math
import random
import statistics
from itertools import combinations
from .contracts import BINDING, OFFICIAL, validate_requirement_set

FINAL_STATUSES = {'LLM_CONSENSUS_SILVER', 'LLM_ADJUDICATED_SILVER', 'HUMAN_REVIEWED', 'TEST_FIXTURE', 'LLM_SINGLE_JUDGE_SILVER'}


def _role_ok(authority: str, policy: str) -> bool:
    if policy == 'BINDING_REQUIRED':
        return authority in BINDING
    if policy == 'OFFICIAL_ALLOWED':
        return authority in OFFICIAL
    return True


def evaluate_ranking(ranked: list[dict], qrels: list[dict], spec: dict, k: int = 10) -> dict:
    """Every evaluated top-k chunk must have final labels for this content version.
    FULL support, not a generic relevance >=2, is required for a requirement hit.
    Complementary passages can satisfy separately defined atomic requirements.
    """
    if k < 1:
        raise ValueError('k must be positive')
    validate_requirement_set(spec)
    ids=[x['chunk_id'] for x in ranked]
    if len(ids)!=len(set(ids)):
        raise ValueError('Duplicate chunk IDs in ranking')
    labels={}
    for q in qrels:
        if q['scenario_id'] != spec['scenario_id']:
            continue
        if q['chunk_id'] in labels:
            raise ValueError('Duplicate qrel: reconcile instead of overwriting')
        labels[q['chunk_id']]=q
    top=ranked[:k]
    missing=[r['chunk_id'] for r in top if r['chunk_id'] not in labels or labels[r['chunk_id']].get('annotation_status') not in FINAL_STATUSES]
    if missing:
        raise ValueError(f'Unjudged/unresolved evaluated candidates: {missing}')
    for r in top:
        if r.get('content_sha256') != labels[r['chunk_id']].get('content_sha256'):
            raise ValueError('Stale qrel text hash; rebuild pool and rejudge')
    reqs=[r for r in spec['requirements'] if r.get('mandatory', True)]
    content=set(); strict=set(); first=None; wrong=0; unknown=0
    relevant=[]
    for rank, item in enumerate(top,1):
        q=labels[item['chunk_id']]
        g=q['relevance_grade']
        if not isinstance(g,int) or not 0<=g<=3:
            raise ValueError('Invalid relevance grade')
        relevant.append(g)
        wrong += q['applicability']=='INAPPLICABLE'
        unknown += q['applicability']=='UNKNOWN'
        for req in reqs:
            support=q.get('requirements',{}).get(req['id'],{}).get('support','NONE')
            applicable=q['applicability']=='APPLICABLE' or (q['applicability']=='CONDITIONAL' and req.get('allow_conditional',False))
            if support=='FULL' and applicable:
                content.add(req['id'])
                if _role_ok(item.get('authority_class','UNKNOWN'),req['source_policy']):
                    strict.add(req['id'])
                    if first is None: first=rank
    dcg=sum((2**g-1)/math.log2(i+2) for i,g in enumerate(relevant))
    pool_final=[q for q in labels.values() if q.get('annotation_status') in FINAL_STATUSES]
    ideal=sorted((q['relevance_grade'] for q in pool_final),reverse=True)[:k]
    idcg=sum((2**g-1)/math.log2(i+2) for i,g in enumerate(ideal))
    n=len(reqs)
    binding=[r['id'] for r in reqs if r['source_policy']=='BINDING_REQUIRED']
    guidance=[r['id'] for r in reqs if r['source_policy']=='OFFICIAL_ALLOWED']
    return {
      'scenario_id':spec['scenario_id'],'scenario_group_id':spec.get('scenario_group_id',spec['scenario_id']),
      'k':k,'returned':len(top),'judged_at_k':1.0 if top else None,
      'requirement_coverage':len(strict)/n,'content_coverage':len(content)/n,
      'scenario_complete':int(len(strict)==n),'mrr_first_sufficient':1/first if first else 0.,
      'hit_ge2':int(any(g>=2 for g in relevant)),
      'pooled_ndcg':dcg/idcg if idcg else None,
      'precision_ge2_at_k':sum(g>=2 for g in relevant)/k,
      'binding_requirement_coverage':sum(x in strict for x in binding)/len(binding) if binding else None,
      'official_requirement_coverage':sum(x in strict for x in guidance)/len(guidance) if guidance else None,
      'inapplicable_fraction_returned':wrong/len(top) if top else None,
      'applicability_unknown_fraction':unknown/len(top) if top else None,
      'requirements_satisfied':sorted(strict),'requirements_content_only':sorted(content-strict),
      'denominator_requirements':n,'pooled_judged_candidates':len(pool_final),
      'annotation_basis':sorted(set(q.get('annotation_status') for q in pool_final)),
    }


def macro_summary(rows: list[dict]) -> dict:
    keys=('requirement_coverage','content_coverage','scenario_complete','pooled_ndcg','mrr_first_sufficient','hit_ge2','precision_ge2_at_k','binding_requirement_coverage','official_requirement_coverage','inapplicable_fraction_returned','applicability_unknown_fraction')
    out={'n_scenarios':len(rows)}
    for key in keys:
        values=[r[key] for r in rows if r.get(key) is not None]
        out[key]={'mean':statistics.mean(values) if values else None,'n_defined':len(values)}
    return out


def paired_bootstrap(a: list[dict], b: list[dict], metric='requirement_coverage', repetitions=2000, seed=37) -> dict:
    """Equal-weight scenario groups; follow-up turns do not become independent cases."""
    aa={r['scenario_id']:r for r in a}; bb={r['scenario_id']:r for r in b}
    if set(aa)!=set(bb): raise ValueError('Paired systems require identical scenario sets')
    groups={}
    for sid in sorted(aa):
        x,y=aa[sid].get(metric),bb[sid].get(metric)
        if x is None or y is None: continue
        group=aa[sid].get('scenario_group_id',sid)
        if group!=bb[sid].get('scenario_group_id',sid): raise ValueError('Group mismatch')
        groups.setdefault(group,[]).append(y-x)
    deltas=[statistics.mean(v) for v in groups.values()]
    if not deltas: return {'n_groups':0,'delta':None,'ci95':None}
    rng=random.Random(seed)
    boot=sorted(statistics.mean(rng.choices(deltas,k=len(deltas))) for _ in range(repetitions))
    def quantile(q):
        at=(len(boot)-1)*q; lo=int(at); hi=min(lo+1,len(boot)-1)
        return boot[lo]+(boot[hi]-boot[lo])*(at-lo)
    wins=sum(d>1e-12 for d in deltas); losses=sum(d< -1e-12 for d in deltas); ties=len(deltas)-wins-losses
    n=wins+losses
    p=min(1.,2*sum(math.comb(n,i) for i in range(min(wins,losses)+1))/2**n) if n else 1.
    return {'metric':metric,'n_groups':len(deltas),'delta':statistics.mean(deltas),'ci95':[quantile(.025),quantile(.975)],
            'wins':wins,'ties':ties,'losses':losses,'exact_two_sided_sign_p':p,
            'uncertainty':'scenario sampling conditional on these silver labels; not legal-truth or judge-error uncertainty'}


def judge_agreement(judgments: list[dict]) -> dict:
    """Pairwise quadratic-weighted kappa for grades; agreement does not prove correctness."""
    by_item={}; judges=set()
    for row in judgments:
        key=(row['scenario_id'],row['chunk_id'],row['content_sha256'])
        judges.add(row['judge_id']); by_item.setdefault(key,{})[row['judge_id']]=row['relevance_grade']
    results=[]
    for ja,jb in combinations(sorted(judges),2):
        pairs=[(r[ja],r[jb]) for r in by_item.values() if ja in r and jb in r]
        n=len(pairs)
        if not n: continue
        ma=[sum(x==i for x,y in pairs)/n for i in range(4)]
        mb=[sum(y==j for x,y in pairs)/n for j in range(4)]
        observed=sum((x-y)**2/9 for x,y in pairs)/n
        expected=sum(ma[i]*mb[j]*(i-j)**2/9 for i in range(4) for j in range(4))
        results.append({'judges':[ja,jb],'n':n,'exact_agreement':sum(x==y for x,y in pairs)/n,
                        'quadratic_weighted_kappa':1-observed/expected if expected>0 else None})
    return {'pairs':results,'note':'Concordance among models is reliability evidence, not validation against expert legal truth.'}
