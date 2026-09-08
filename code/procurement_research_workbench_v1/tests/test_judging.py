import pytest
from prw.judging import validate_judgment, adjudicate_consensus, make_judge_payload

REQS = [{'id': 'R1'}]

def judgment(grade=3, support='FULL', app='APPLICABLE'):
    return {'relevance_grade': grade, 'applicability': app,
            'judgments': [{'support': support}], 'short_rationale': 'Evidence-based reason', 'confidence': .8}

def rows(grades=(3,3,3), support=('FULL','FULL','FULL')):
    # Directly constructs the post-validation row shape (adjudicate_consensus's input), not
    # routed through validate_judgment -- these tests exercise consensus/disagreement logic with
    # deliberately varied grade/support combinations that need not individually satisfy
    # validate_judgment's own internal grade-vs-support consistency check.
    return [dict(scenario_id='X', chunk_id='a', content_sha256='h', judge_id=f'J{i}',
                 relevance_grade=g, applicability='APPLICABLE',
                 requirements={'R1': {'support': s}}, short_rationale='Evidence-based reason', confidence=.8)
            for i, (g, s) in enumerate(zip(grades, support))]

def test_no_quote_or_span_required():
    # v2 contract: no spans/quotes at all -- a bare support value per requirement is sufficient,
    # matched positionally, not by an ID the judge invents.
    r = validate_judgment(judgment(), REQS)
    assert r['requirements']['R1']['support'] == 'FULL'
    assert 'spans' not in r['requirements']['R1']

def test_wrong_length_judgments_rejected():
    out = judgment(); out['judgments'] = []
    with pytest.raises(ValueError): validate_judgment(out, REQS)

def test_extra_requirement_rejected():
    # harness expects 2 requirements but the judge's positional array has only 1 -- structurally
    # impossible for the judge to "rename" a requirement since it never emits IDs at all.
    with pytest.raises(ValueError): validate_judgment(judgment(), REQS + [{'id': 'R2'}])

def test_majority_does_not_override_material_disagreement():
    out=adjudicate_consensus(rows((0,3,3)))
    assert out['annotation_status']=='REQUIRES_ADJUDICATION'

def test_same_grade_different_sufficiency_adjudicated():
    out=adjudicate_consensus(rows(support=('FULL','FULL','PARTIAL')))
    assert out['annotation_status']=='REQUIRES_ADJUDICATION'

def test_regime_disagreement_adjudicated():
    r=rows();r[1]['applicability']='UNKNOWN'
    assert adjudicate_consensus(r)['annotation_status']=='REQUIRES_ADJUDICATION'

def test_concordant_grade_near_median():
    assert adjudicate_consensus(rows((2,3,3)))['relevance_grade']==3

def test_three_identical_judge_ids_rejected():
    r=rows();r[1]['judge_id']=r[0]['judge_id']
    with pytest.raises(ValueError): adjudicate_consensus(r)

def test_blinded_payload_omits_rank_and_system():
    p={'user_message':'Question','history':[]}; s={'requirements':[{'id':'R1','description':'rule','source_policy':'BINDING_REQUIRED'}]}
    pooled={'candidate_id':'C1','evidence':{'text':'Rule','score':100,'system':'adaptive','rank':1,'citation':'Act'}}
    data=make_judge_payload(p,s,pooled)
    assert 'system' not in data['candidate'] and 'rank' not in data['candidate'] and 'score' not in data['candidate']
