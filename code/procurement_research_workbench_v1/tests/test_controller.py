import pytest
from prw.contracts import Evidence, Scenario
from prw.controller import AdaptiveController, assemble, validate_plan, validate_query, validate_observation, segment_facts
from prw.adapters import ReplayBackend

class Model:
    identity='fixture'
    def __init__(self,outputs):self.outputs=list(outputs)
    def complete(self,*args):return self.outputs.pop(0)

P={'issues':[{'id':'I1','description':'Find rule','needs_binding':True},{'id':'I2','description':'Find notice','needs_binding':True}],
   'queries':['rule','notice'],'clarifications':[]}
def obs(complete=False):
    return {'issues':{'I1':{'status':'FULL','evidence':['a']},
                     'I2':{'status':'FULL' if complete else 'MISSING','evidence':['b'] if complete else []}},
            'next_action':{'type':'SEARCH','query':'notice','graph':False},'clarifications':[],'short_rationale':'Look for missing notice'}
def test_adaptive_retrieves_missing_issue():
    a=Evidence('a','Rule',authority_class='PRIMARY_LEGISLATION');b=Evidence('b','Notice',authority_class='PRIMARY_LEGISLATION')
    backend=ReplayBackend([[a],[b]])
    run=AdaptiveController(backend,Model([P,obs(),obs(True)]),{'max_retrieval_operations':3}).run(Scenario('X','What rule and notice?'))
    assert run['retrieval_operations']==2 and run['stop_reason']=='ESTIMATED_COVERAGE_COMPLETE'
    assert {e['chunk_id'] for e in run['ranking']}=={'a','b'}

def test_hidden_gold_rejected():
    with pytest.raises(ValueError): Scenario.from_public({'scenario_id':'X','user_message':'Q','requirements':[]})

def test_unseen_statutory_locator_rewrite_rejected():
    with pytest.raises(ValueError): validate_query('section 43',Scenario('X','Which rule?'),[])

def test_observed_statutory_locator_allowed():
    validate_query('section 43',Scenario('X','Which rule?'),[Evidence('a','section 43 applies')])

def test_planner_cannot_reference_unknown_fact_id():
    scenario=Scenario('X','Which rule?')
    p={'issues':[{'id':'I1','description':'Find rule','needs_binding':True,'fact_ids':['F99']}],'queries':['rule']}
    with pytest.raises(ValueError): validate_plan(p,scenario,segment_facts(scenario))

def test_planner_facts_are_deterministic_and_not_model_generated():
    scenario=Scenario('X','The contract starts in January 2024. It runs for four years.')
    facts=segment_facts(scenario)
    assert facts==segment_facts(scenario)
    assert [f['text'] for f in facts]==['The contract starts in January 2024.','It runs for four years.']

def test_observer_cannot_cite_unknown_chunk_id():
    with pytest.raises(ValueError): validate_observation(obs(),P,[Evidence('z','Unrelated')])

def test_binding_issue_not_fully_supported_by_guidance():
    o=obs(); x=validate_observation(o,P,[Evidence('a','Rule',authority_class='OFFICIAL_GOVERNMENT_GUIDANCE')])
    assert x['issues']['I1']['status']=='PARTIAL'

def test_context_budget_never_silently_truncates():
    evidence=[Evidence('a','A'*30),Evidence('b','B'*5)]
    out=assemble(evidence,k=10,char_budget=10,two_lanes=False)
    assert len(out)==1 and out[0].text=='BBBBB'

def test_lanes_share_ten_slots_not_twenty():
    ev=[Evidence(str(i),'text',authority_class='PRIMARY_LEGISLATION' if i<8 else 'OFFICIAL_GOVERNMENT_GUIDANCE') for i in range(16)]
    out=assemble(ev,k=10)
    assert len(out)==10 and sum(x.lane=='legislation' for x in out)==5

def test_budget_limits_all_tool_calls():
    p={'issues':[{'id':'I1','description':'Need','needs_binding':False}],'queries':['one','two']}
    o={'issues':{'I1':{'status':'MISSING','evidence':[]}},'next_action':{'type':'SEARCH','query':'different query','graph':False}}
    backend=ReplayBackend([[Evidence('a','A')]])
    run=AdaptiveController(backend,Model([p,o]),{'max_retrieval_operations':1}).run(Scenario('X','Q'))
    assert run['retrieval_operations']==1 and run['stop_reason']=='BUDGET_EXHAUSTED'

def test_invalid_model_plan_safe_fallback():
    backend=ReplayBackend([[Evidence('a','A')]])
    run=AdaptiveController(backend,Model([{},{}]),{'max_retrieval_operations':1}).run(Scenario('X','Q'))
    assert run['retrieval_operations']==1 and len(run['errors'])>=1

def test_repeated_action_stops():
    p={'issues':[{'id':'I1','description':'Need','needs_binding':False}],'queries':['Q']}
    o={'issues':{'I1':{'status':'MISSING','evidence':[]}},'next_action':{'type':'SEARCH','query':'Q','graph':True}}
    run=AdaptiveController(ReplayBackend([[Evidence('a','A')]]),Model([p,o]),{'max_retrieval_operations':3,'initial_graph':True}).run(Scenario('X','Q'))
    assert run['stop_reason']=='REPEATED_ACTION'

def test_model_budget_failure_does_not_become_fake_adaptive_success():
    from prw.llm import BudgetExhausted
    class EmptyBudget:
        def complete(self,*args):raise BudgetExhausted('stop')
    backend=ReplayBackend([])
    with pytest.raises(BudgetExhausted):AdaptiveController(backend,EmptyBudget(),{}).run(Scenario('X','Q'))
    assert not backend.calls

def test_matched_planned_control_uses_no_observation_calls():
    backend=ReplayBackend([[Evidence('a','A')],[Evidence('b','B')],[Evidence('c','C')]])
    model=Model([P])
    result=AdaptiveController(backend,model,{'max_retrieval_operations':3}).run(Scenario('X','Original question'),system='planned_multisearch')
    assert result['retrieval_operations']==3 and not result['errors']
