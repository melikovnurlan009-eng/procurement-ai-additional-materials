#!/usr/bin/env python3
"""End-to-end OFFLINE FIXTURE exercise. Its numbers are never thesis results."""
from pathlib import Path
import copy
from prw.io import write_json,write_jsonl
from prw.contracts import Scenario,Evidence
from prw.adapters import ReplayBackend
from prw.controller import AdaptiveController,run_static
from prw.pooling import build_pool
from prw.judging import judge_three,adjudicate_consensus
from prw.metrics import evaluate_ranking
from prw.bundles import judge_bundle_three,consensus_bundles,score_bundle
from prw.answers import generate_answer,judge_answer_three,consensus_answers

class ControllerFixture:
    identity={'model':'OFFLINE_TEST_DOUBLE'}
    def __init__(self):self.n=0
    def complete(self,prompt,payload):
        self.n+=1
        if self.n==1:return {'issues':[{'id':'I1','description':'Amber control','needs_binding':True,'fact_ids':['F1']},
                                        {'id':'I2','description':'Cobalt control','needs_binding':False,'fact_ids':['F1']}],
                             'queries':['amber control','cobalt control'],'clarifications':[]}
        full=self.n>=3
        return {'issues':{'I1':{'status':'FULL','evidence':['fixture-a']},
                          'I2':{'status':'FULL' if full else 'MISSING','evidence':['fixture-b'] if full else []}},
                'next_action':{'type':'STOP' if full else 'SEARCH','query':'cobalt control','graph':False},'clarifications':[],'short_rationale':'Fixture branch'}

class JudgeFixture:
    identity={'model':'OFFLINE_TEST_DOUBLE'}
    def complete(self,prompt,payload):
        if 'candidate' in payload:
            text=payload['candidate']['text']
            judgments=[{'support':'FULL' if r['description'].split()[0].lower() in text.lower() else 'NONE'}
                       for r in payload['requirements']]
            return {'relevance_grade':3,'applicability':'APPLICABLE','judgments':judgments,'short_rationale':'Offline fixture','confidence':1.}
        if 'requirements' in payload and 'evidence' in payload:
            judgments=[]
            for r in payload['requirements']:
                matches=[e for e in payload['evidence'] if r['description'].split()[0].lower() in e['text'].lower()]
                judgments.append({'status':'SATISFIED' if matches else 'NOT_SATISFIED','applicability':'APPLICABLE',
                    'supporting_chunk_ids':[e['chunk_id'] for e in matches],
                    'sufficiency_grade':3 if matches else 0,'confidence':1.0,'short_reason':'Offline fixture'})
            return {'judgments':judgments}
        return {'legal_correctness':None,'completeness':3,'grounding':3,'citation_correctness':2,'authority_applicability':2,
            'unsupported_claim_present':False,'wrong_regime_present':False,
            'requirements_addressed':{r['id']:{'addressed':True,'rationale':'Offline fixture'} for r in payload['requirements']},
            'claim_checks':[],'short_rationale':'Offline fixture'}

class GeneratorFixture:
    identity={'model':'OFFLINE_TEST_DOUBLE'}
    def complete(self,prompt,payload):
        return {'answer':'Amber control is required [E1]. Cobalt control is checked [E2].',
                'claims':[{'text':'Amber control is required','evidence_ids':['E1']},{'text':'Cobalt control is checked','evidence_ids':['E2']}],
                'unresolved_questions':[]}

def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    public={'scenario_id':'FIXTURE_01','user_message':'Find amber and cobalt controls.','history':[]}
    scenario=Scenario.from_public(public)
    spec={'scenario_id':'FIXTURE_01','requirements':[{'id':'R1','description':'Amber control','mandatory':True,'source_policy':'BINDING_REQUIRED'},
          {'id':'R2','description':'Cobalt control','mandatory':True,'source_policy':'OFFICIAL_ALLOWED'}]}
    a=Evidence('fixture-a','Amber control is required.',citation='Fictional test fixture A',authority_class='PRIMARY_LEGISLATION')
    b=Evidence('fixture-b','Cobalt control is checked.',citation='Fictional test fixture B',authority_class='OFFICIAL_GOVERNMENT_GUIDANCE')
    config={'max_retrieval_operations':3,'k':10,'context_chars':18000,'initial_graph':False}
    static=run_static(ReplayBackend([[a]]),scenario,config)
    adaptive=AdaptiveController(ReplayBackend([[a],[b]]),ControllerFixture(),config).run(scenario)
    pool,_=build_pool([static,adaptive]);judges=[JudgeFixture(),JudgeFixture(),JudgeFixture()];qrels=[]
    for pair in pool:
        q=adjudicate_consensus(judge_three(judges,public,spec,pair,out/'cache'))
        q['annotation_status']='TEST_FIXTURE';qrels.append(q)
    pointwise=[evaluate_ranking(r['ranking'],qrels,spec) for r in (static,adaptive)]
    bundles=[]
    for r in (static,adaptive):
        label=consensus_bundles(judge_bundle_three(judges,public,spec,r));label['annotation_status']='TEST_FIXTURE'
        bundles.append(score_bundle(r,spec,label))
    answer=generate_answer(GeneratorFixture(),public,adaptive)
    answer_labels=consensus_answers(judge_answer_three(judges,public,spec,answer))
    assert pointwise[0]['requirement_coverage']==.5 and pointwise[1]['requirement_coverage']==1.
    assert bundles[0]['requirement_coverage']==.5 and bundles[1]['requirement_coverage']==1.
    assert answer_labels['legal_correctness'] is None and adaptive['retrieval_operations']==2
    write_json(out/'smoke_fixture_results.json',{'status':'OFFLINE_FIXTURE_PASS_NOT_RESEARCH_EVIDENCE','network_calls':0,
       'checks':['static retrieval','bounded adaptive missing-issue search','open candidate union','three parallel passage judges',
                 'exact quote validation','bundle sufficiency','same-generator answer route','no-reference legal score stays null'],
       'fictional_fixture_metrics':{'pointwise':pointwise,'bundle':bundles},'legal_research_metrics_produced':False})
    write_jsonl(out/'fixture_runs.jsonl',[dict(r,experiment_status='OFFLINE_TEST_FIXTURE') for r in (static,adaptive)])
    return out/'smoke_fixture_results.json'

if __name__=='__main__':print(run(Path(__file__).resolve().parents[1]/'validation/smoke'))
