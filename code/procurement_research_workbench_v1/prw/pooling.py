"""Pool every evaluated output, without rewarding one system or changing source text."""
from __future__ import annotations
from .io import digest


def build_pool(runs: list[dict], reference_items: list[dict] | None = None, depth: int=20, final_only: bool=False) -> tuple[list[dict],list[dict]]:
    pool={}; membership=[]
    for run in runs:
        sid=run['scenario_id']
        # Include all acquired candidates, not only the final selected context.
        acquired=run['ranking'] if final_only else run.get('acquired',run['ranking'])
        for rank,item in enumerate(acquired,1):
            if 'acquired' not in run and not final_only and rank>depth: break
            key=(sid,item['chunk_id'])
            if key in pool and pool[key]['evidence']['content_sha256']!=item['content_sha256']:
                raise ValueError('Same chunk ID with different text across systems/snapshots')
            pool[key]={'scenario_id':sid,'chunk_id':item['chunk_id'],'content_sha256':item['content_sha256'],
                       'candidate_id':'C_'+digest([sid,item['chunk_id'],item['content_sha256']])[:16],
                       'evidence':{k:item[k] for k in ['chunk_id','text','citation','source_url','authority_class','legal_regime','jurisdiction','canonical_ids','content_sha256'] if k in item}}
            membership.append({'scenario_id':sid,'chunk_id':item['chunk_id'],'system':run['system'],'acquisition_rank':rank})
    for entry in reference_items or []:
        sid,item=entry['scenario_id'],entry['evidence']; key=(sid,item['chunk_id'])
        if key in pool and pool[key]['content_sha256']!=item['content_sha256']: raise ValueError('Reference text conflict')
        pool[key]={'scenario_id':sid,'chunk_id':item['chunk_id'],'content_sha256':item['content_sha256'],
                   'candidate_id':'C_'+digest([sid,item['chunk_id'],item['content_sha256']])[:16],
                   'evidence':{k:v for k,v in item.items() if k not in ('score','rank','provenance','lane')}}
    return [pool[k] for k in sorted(pool)], membership
