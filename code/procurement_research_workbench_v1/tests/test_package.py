import json
from pathlib import Path
import pytest
from prw.io import read_jsonl,write_json,file_hash,digest
from prw.benchmark import audit,freeze,check_freeze
from prw.pooling import build_pool
from prw.contracts import Evidence
from prw.shadow_fts import build_shadow,search_shadow
from prw.keywords import validate_enrichment
from prw.answers import validate_answer_judgment
from prw.llm import Budget,HTTPJsonModel
ROOT=Path(__file__).resolve().parents[1]

def test_dataset_exact_target_distribution():
    report=audit(ROOT/'data/dev/scenarios.jsonl',ROOT/'data/test_sealed/scenarios.jsonl',ROOT/'data/dev/requirements.jsonl',ROOT/'data/test_sealed/requirements.jsonl')
    assert report['status']=='STRUCTURAL_CHECK_PASS' and report['n_dev']==40 and report['n_test']==20
    expected={'statutory':8,'semantic':10,'vocabulary':8,'multi_evidence':10,'applicability':8,'guidance':8,'authority':4,'compound':4}
    assert {k:report['dev_suites'][k]+report['test_suites'][k] for k in expected}==expected

def test_followups_stay_in_parent_split():
    for folder in ['dev','test_sealed']:
        base={r['scenario_id']:r for r in read_jsonl(ROOT/'data'/folder/'scenarios.jsonl')}
        for f in read_jsonl(ROOT/'data'/folder/'followups.jsonl'):
            assert f['scenario_group_id']==base[f['parent_scenario_id']]['scenario_group_id']
            assert f['split']==base[f['parent_scenario_id']]['split']

def test_pool_includes_adaptive_unique_items():
    a=Evidence('a','A').to_dict(); b=Evidence('b','B').to_dict()
    runs=[{'scenario_id':'X','system':'static','ranking':[a]},{'scenario_id':'X','system':'adaptive','ranking':[a,b]}]
    pool,_=build_pool(runs)
    assert {r['chunk_id'] for r in pool}=={'a','b'}

def test_pool_rejects_cross_snapshot_text_change():
    a=Evidence('a','A').to_dict(); b=Evidence('a','B').to_dict()
    with pytest.raises(ValueError): build_pool([{'scenario_id':'X','system':'s1','ranking':[a]},{'scenario_id':'X','system':'s2','ranking':[b]}])

def test_source_keywords_cannot_use_unanchored_labels():
    with pytest.raises(ValueError): validate_enrichment({'chunk_id':'c','text':'public notice'},{'exact_keywords':[{'term':'section 43','quote':'public notice'}],'aliases':[]})

def test_alias_preserves_source_text_and_shadow_index(tmp_path):
    c={'chunk_id':'c','text':'The contract uses a standstill period.','citation':'A'}
    e=validate_enrichment(c,{'exact_keywords':[{'term':'standstill','quote':'standstill period'}],
       'aliases':[{'term':'cooling-off period','quote':'standstill period','kind':'CONTEXTUAL_RETRIEVAL_HINT','scope_note':'Only a prompt to retrieve standstill rules, not universal equivalence.'}]})
    build_shadow(tmp_path/'i2.db',[c],[e],arm='I2')
    result=search_shadow(tmp_path/'i2.db','cooling')
    assert result[0]['payload']['text']==c['text']

def test_shadow_cannot_overwrite_index(tmp_path):
    path=tmp_path/'db';build_shadow(path,[])
    with pytest.raises(FileExistsError):build_shadow(path,[])

def test_budget_is_persistent(tmp_path):
    p=tmp_path/'budget.json';b=Budget(p,1);b.reserve()
    with pytest.raises(RuntimeError):Budget(p,1).reserve()

def test_api_call_needs_explicit_opt_in(tmp_path):
    m=HTTPJsonModel({'model':'configured-model'},Budget(tmp_path/'b',1),tmp_path/'log',False)
    with pytest.raises(RuntimeError,match='opt-in'):m.complete('JSON',{})

def test_no_legal_accuracy_without_reference_evidence():
    with pytest.raises(ValueError):validate_answer_judgment({'legal_correctness':3},{'requirements':[]},False)

def test_freeze_detects_modified_config(tmp_path):
    s=tmp_path/'s';s.write_text('x');r=tmp_path/'r';r.write_text('y');c=tmp_path/'c';c.write_text('{}');f=tmp_path/'f'
    freeze(s,r,[c],f,'snapshot',ROOT)
    c.write_text('{"changed":true}')
    with pytest.raises(ValueError):check_freeze(f,s,c,'snapshot',ROOT)

def test_sidecar_uses_only_explicit_edges_and_live_mapping():
    from prw.graph import GraphSidecar
    from prw.adapters import ReplayBackend
    from prw.contracts import SearchRequest
    edges=[{'source_id':'s','target_id':'t','relation':'CROSS_REFERS_TO','confidence':.9},
           {'source_id':'s','target_id':'other','relation':'HAS_CHUNK','confidence':1}]
    graph=GraphSidecar(ReplayBackend([]),edges,{'t':['c']},lambda ids:[Evidence(x,'text') for x in ids])
    out=graph.expand_from('s','query',SearchRequest('query',target_anchor='s'))
    assert [e.chunk_id for e in out.evidence]==['c'] and len(out.trace['edges'])==1

def test_oracle_respects_char_budget():
    pytest.importorskip('scipy')
    from prw.diagnostics import oracle_coverage
    from test_metrics import item,label,spec
    a=item('a');a['text']='A'*100
    b=item('b');b['text']='B'*2
    # Restore hash consistency to text for this independent fixture.
    qa=label('a');qb=label('b','R2');a['content_sha256']=qa['content_sha256'];b['content_sha256']=qb['content_sha256']
    m=oracle_coverage([a,b],[qa,qb],spec(),k=2,char_budget=10)
    assert m['proven_optimal'] and m['coverage']==.5 and m['selected_ids']==['b']

def test_final_only_pool_includes_novel_final_outputs_without_all_acquired():
    a=Evidence('a','A').to_dict();b=Evidence('b','B').to_dict()
    pool,_=build_pool([{'scenario_id':'X','system':'S','ranking':[a],'acquired':[a,b]}],final_only=True)
    assert [r['chunk_id'] for r in pool]==['a']

def test_adapter_parses_json_encoded_source_ids():
    from prw.adapters import ProductionAdapter
    class R:pass
    output=ProductionAdapter(R())._convert([{'chunk_id':'c','text':'Text','source_node_ids':'["node-1"]'}])
    assert output[0].canonical_ids==['node-1']

def test_smoke_pipeline(tmp_path):
    from scripts.smoke_pipeline import run
    result=json.loads(run(tmp_path).read_text())
    assert result['network_calls']==0 and result['legal_research_metrics_produced'] is False

def test_changed_test_requirements_block_evaluation(tmp_path):
    from argparse import Namespace
    from prw.cli import evaluation_freeze
    scenario=tmp_path/'scenarios';scenario.write_text('scenario')
    req=tmp_path/'requirements';req.write_text('original')
    config=tmp_path/'config';config.write_text('{}')
    frozen=tmp_path/'frozen';freeze(scenario,req,[config],frozen,'snapshot',ROOT)
    req.write_text('changed after seeing output')
    args=Namespace(freeze=frozen,scenarios=scenario,requirements=req)
    with pytest.raises(ValueError,match='requirements changed'):evaluation_freeze(args,[{'split':'test'}])

def test_all_dataset_records_satisfy_shipped_schemas():
    jsonschema=pytest.importorskip('jsonschema')
    for folder in ('dev','test_sealed'):
        for name,schema in [('scenarios','scenario'),('followups','scenario'),('requirements','requirements'),('followup_requirements','requirements')]:
            definition=json.loads((ROOT/'schemas'/(schema+'.schema.json')).read_text())
            for row in read_jsonl(ROOT/'data'/folder/(name+'.jsonl')):jsonschema.validate(row,definition)
