"""Dataset structural audit and a test/configuration freeze, not a corpus audit."""
from __future__ import annotations
import re
from collections import Counter
from pathlib import Path
from .io import read_jsonl, read_json, write_json, file_hash, digest, now
from .contracts import Scenario, validate_requirement_set


def _scenario_text(row):
    text=row['user_message']
    return text.split('\n\n',1)[-1]


def audit(dev_path,test_path,dev_req,test_req):
    dev,test=read_jsonl(dev_path),read_jsonl(test_path)
    allrows=dev+test; ids=[r['scenario_id'] for r in allrows]
    errors=[]
    if len(ids)!=len(set(ids)): errors.append('duplicate scenario IDs')
    for r in allrows: Scenario.from_public(r)
    for path,rows in ((dev_req,dev),(test_req,test)):
        specs=read_jsonl(path)
        if {s['scenario_id'] for s in specs}!={r['scenario_id'] for r in rows}: errors.append('scenario/requirement ID mismatch')
        for s in specs: validate_requirement_set(s)
    groups_d={r['scenario_group_id'] for r in dev}; groups_t={r['scenario_group_id'] for r in test}
    if groups_d & groups_t: errors.append('scenario group shared across split')
    norm=lambda s:' '.join(re.findall(r'[a-z0-9]+',s.lower()))
    exact=[]; near=[]
    for a in dev:
        at=norm(_scenario_text(a)); aa=set(at.split())
        for b in test:
            bt=norm(_scenario_text(b)); bb=set(bt.split())
            score=len(aa&bb)/max(1,len(aa|bb))
            if at==bt: exact.append([a['scenario_id'],b['scenario_id']])
            near.append({'dev':a['scenario_id'],'test':b['scenario_id'],'token_jaccard':round(score,4)})
    if exact: errors.append('normalized cross-split duplicates')
    return {'generated_at':now(),'n_dev':len(dev),'n_test':len(test),
            'dev_suites':dict(Counter(r['suite'] for r in dev)),'test_suites':dict(Counter(r['suite'] for r in test)),
            'topics':dict(Counter(r['topic'] for r in allrows)), 'errors':errors,
            'exact_duplicate_pairs':exact,'highest_lexical_similarity_pairs':sorted(near,key=lambda x:-x['token_jaccard'])[:12],
            'status':'STRUCTURAL_CHECK_PASS' if not errors else 'FAIL',
            'limitation':'Lexical duplicate checking is not proof of independent legal scenarios. Test cases are fresh model-authored candidates; expert review, corpus sufficiency and semantic validation are not claimed.'}


def freeze(test_path,requirements_path,configs,output,snapshot_id,package_root):
    root=Path(package_root)
    record={'version':'1.0.0','created_at':now(),'snapshot_id':snapshot_id,
            'test_sha256':file_hash(test_path),'requirements_sha256':file_hash(requirements_path),
            'config_hashes':[file_hash(x) for x in configs],
            'code_hashes':{str(p.relative_to(root)):file_hash(p) for p in sorted((root/'prw').glob('*.py'))},
            'warning':'Cryptographic freeze prevents unnoticed edits; it does not establish independence or label correctness.'}
    write_json(output,record)
    return record


def check_freeze(path,scenarios_path,config_path,snapshot_id,root):
    record=read_json(path)
    if record['test_sha256']!=file_hash(scenarios_path): raise ValueError('Test scenarios changed since freeze')
    if file_hash(config_path) not in record['config_hashes']: raise ValueError('Configuration not frozen')
    if snapshot_id!=record['snapshot_id']: raise ValueError('Snapshot differs from freeze')
    for filename,h in record['code_hashes'].items():
        if file_hash(Path(root)/filename)!=h: raise ValueError(f'Code changed since freeze: {filename}')
    return record
