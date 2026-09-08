#!/usr/bin/env python3
"""Opt-in source-only keyword proposals, cached by content and model configuration."""
import argparse
from pathlib import Path
from prw.io import read_jsonl,read_json,write_json,write_jsonl,digest
from prw.cli import model_set,ROOT
from prw.keywords import KEYWORD_PROMPT,validate_enrichment

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--chunks',required=True);p.add_argument('--out',required=True)
    p.add_argument('--models',default=str(ROOT/'configs/models.json'))
    p.add_argument('--allow-network',action='store_true');p.add_argument('--max-requests',type=int,default=100)
    a=p.parse_args();chunks=read_jsonl(a.chunks);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if not a.allow_network:
        write_json(out/'cost_plan.json',{'chunks':len(chunks),'minimum_requests':len(chunks),'status':'DRY_RUN_NO_ENRICHMENT_EXECUTED'})
        print(out/'cost_plan.json');return
    model=model_set(a,['controller'])['controller'];model.preflight();result=[]
    for chunk in chunks:
        # Deliberate allowlist: no scenario, qrel or benchmark field can pass through.
        payload={k:chunk[k] for k in ('chunk_id','text','citation','source_url','authority_class','legal_regime') if k in chunk}
        if not payload.get('text'):raise ValueError('Exact source text is required')
        key=digest([KEYWORD_PROMPT,payload,model.identity]);path=out/'cache'/(key+'.json')
        record=read_json(path) if path.exists() else validate_enrichment(payload,model.complete(KEYWORD_PROMPT,payload))
        record.update({'generation_model':model.identity,'prompt_hash':digest(KEYWORD_PROMPT)})
        write_json(path,record);result.append(record);write_jsonl(out/'enrichments.jsonl',result)
    print(out/'enrichments.jsonl')
if __name__=='__main__':main()
