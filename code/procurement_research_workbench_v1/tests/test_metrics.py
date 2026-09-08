import pytest
from prw.io import digest
from prw.metrics import evaluate_ranking, paired_bootstrap, judge_agreement

def spec():
    return {'scenario_id':'X','requirements':[{'id':'R1','description':'rule','mandatory':True,'source_policy':'BINDING_REQUIRED','allow_conditional':False},
                                            {'id':'R2','description':'workflow','mandatory':True,'source_policy':'OFFICIAL_ALLOWED','allow_conditional':False}]}

def item(cid,role='PRIMARY_LEGISLATION'):
    return {'chunk_id':cid,'text':cid,'content_sha256':digest(cid),'authority_class':role}

def label(cid,req='R1',support='FULL',grade=3,app='APPLICABLE'):
    return {'scenario_id':'X','chunk_id':cid,'content_sha256':digest(cid),'relevance_grade':grade,'applicability':app,
            'requirements':{req:{'support':support}},'annotation_status':'LLM_CONSENSUS_SILVER'}

def test_partial_does_not_satisfy_requirement():
    m=evaluate_ranking([item('a')],[label('a',support='PARTIAL',grade=2)],spec(),1)
    assert m['requirement_coverage']==0 and m['hit_ge2']==1

def test_guidance_can_fully_support_workflow():
    m=evaluate_ranking([item('a','OFFICIAL_GOVERNMENT_GUIDANCE')],[label('a','R2')],spec(),1)
    assert m['requirement_coverage']==.5

def test_guidance_cannot_replace_explicit_binding_requirement():
    m=evaluate_ranking([item('a','OFFICIAL_GOVERNMENT_GUIDANCE')],[label('a')],spec(),1)
    assert m['content_coverage']==.5 and m['requirement_coverage']==0

def test_multiple_evidence_items_complete_scenario():
    m=evaluate_ranking([item('a'),item('b','OFFICIAL_GOVERNMENT_GUIDANCE')],[label('a'),label('b','R2')],spec(),2)
    assert m['scenario_complete']==1 and m['requirement_coverage']==1

def test_unanticipated_new_passage_can_be_relevant():
    m=evaluate_ranking([item('new_valid')],[label('new_valid')],spec(),1)
    assert m['requirement_coverage']==.5

def test_unjudged_not_zero():
    with pytest.raises(ValueError,match='Unjudged'): evaluate_ranking([item('x')],[],spec())

def test_stale_qrels_rejected():
    r=item('a'); r['content_sha256']='wrong'
    with pytest.raises(ValueError,match='Stale'): evaluate_ranking([r],[label('a')],spec())

def test_unknown_applicability_not_positive():
    m=evaluate_ranking([item('a')],[label('a',app='UNKNOWN')],spec(),1)
    assert m['requirement_coverage']==0 and m['applicability_unknown_fraction']==1

def test_wrong_regime_counted_separately():
    m=evaluate_ranking([item('a')],[label('a',app='INAPPLICABLE')],spec(),1)
    assert m['requirement_coverage']==0 and m['inapplicable_fraction_returned']==1

def test_duplicate_results_do_not_inflate_scores():
    with pytest.raises(ValueError,match='Duplicate'): evaluate_ranking([item('a'),item('a')],[label('a')],spec(),2)

def test_ndcg_has_pooled_denominator():
    m=evaluate_ranking([item('a')],[label('a',grade=1,support='NONE'),label('b',grade=3)],spec(),1)
    assert m['pooled_ndcg']==pytest.approx(1/7)

def test_no_relevant_pool_is_na():
    m=evaluate_ranking([item('a')],[label('a',grade=0,support='NONE')],spec(),1)
    assert m['pooled_ndcg'] is None

def test_empty_return_not_perfect():
    m=evaluate_ranking([],[],spec())
    assert m['requirement_coverage']==0 and m['scenario_complete']==0

def test_bootstrap_is_paired_and_grouped():
    a=[{'scenario_id':'1','scenario_group_id':'g','requirement_coverage':0}, {'scenario_id':'1f','scenario_group_id':'g','requirement_coverage':.5}]
    b=[{'scenario_id':'1','scenario_group_id':'g','requirement_coverage':.5}, {'scenario_id':'1f','scenario_group_id':'g','requirement_coverage':1}]
    m=paired_bootstrap(a,b,repetitions=50)
    assert m['n_groups']==1 and m['ci95']==[.5,.5] and m['delta']==.5

def test_paired_missing_case_rejected():
    with pytest.raises(ValueError): paired_bootstrap([{'scenario_id':'1'}],[])

def test_agreement_handles_degenerate_grades():
    rows=[{'scenario_id':'1','chunk_id':'a','content_sha256':'h','judge_id':j,'relevance_grade':3} for j in ['A','B','C']]
    assert judge_agreement(rows)['pairs'][0]['quadratic_weighted_kappa'] is None

def test_bundle_can_combine_two_partial_passages():
    from prw.bundles import score_bundle,bundle_hash
    s={'scenario_id':'X','requirements':[spec()['requirements'][0]]}
    run={'scenario_id':'X','system':'s','ranking':[item('a'),item('b')]}
    judge={'scenario_id':'X','bundle_hash':bundle_hash(run['ranking']),'annotation_status':'LLM_ADJUDICATED_SILVER',
           'requirements':{'R1':{'status':'SATISFIED','applicability':'APPLICABLE','supporting_chunk_ids':['a','b'],
                                  'confidence':1.0}}}
    # Validated bundle judge, not adding up partial passage grades, establishes sufficiency.
    assert score_bundle(run,s,judge)['requirement_coverage']==1

def test_bundle_disagreement_is_not_silent_majority():
    from prw.bundles import consensus_bundles
    r=[{'scenario_id':'X','bundle_hash':'H','judge_id':str(i),
        'requirements':{'R1':{'status':st,'applicability':'APPLICABLE','supporting_chunk_ids':[]}}}
       for i,st in enumerate(['SATISFIED','SATISFIED','PARTIAL'])]
    assert consensus_bundles(r)['annotation_status']=='REQUIRES_ADJUDICATION'
