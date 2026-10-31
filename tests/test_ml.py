import sys,json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from ml import FEATURES,complete_followup,split_ids,baseline_features,metrics

def test_followup_does_not_treat_missing_coverage_or_death_as_zero():
    d=pd.DataFrame({'BENE_HI_CVRAGE_TOT_MONS':['12','11','12','12',''],'BENE_HMO_CVRAGE_TOT_MONS':['0','0','1','0','0'],'BENE_DEATH_DT':['','','','20090601','']})
    assert complete_followup(d).tolist()==[True,False,False,False,False]

def test_disjoint_reproducible_beneficiary_splits():
    y=np.tile([0,0,0,0,1],200);a=split_ids(y);b=split_ids(y)
    assert all(np.array_equal(x,z) for x,z in zip(a,b))
    assert not(set(a[0])&set(a[1]) or set(a[1])&set(a[2]) or set(a[0])&set(a[2]))
    assert len(set(np.concatenate(a)))==len(y)

def test_future_claim_mutation_cannot_change_baseline_features():
    b=pd.DataFrame({'DESYNPUF_ID':['a'],'BENE_BIRTH_DT':['19400101'],'BENE_SEX_IDENT_CD':['1'],'BENE_HI_CVRAGE_TOT_MONS':['12'],'BENE_HMO_CVRAGE_TOT_MONS':['0']})
    c=pd.DataFrame({'DESYNPUF_ID':['a','a','a'],'CLM_ID':['1','2','3'],'claim_year':[2008,2009,2010],'CLM_THRU_DT_date':pd.to_datetime(['20081231','20090101','20100101']),'CLM_PMT_AMT_cents':[100,200,300],'CLM_UTLZTN_DAY_CNT_int':[1,2,3]})
    before=baseline_features(b,c);c.loc[c.claim_year>2008,'CLM_PMT_AMT_cents']=999999
    pd.testing.assert_frame_equal(before,baseline_features(b,c))
    assert before.loc['a','claims_2008']==1 and before.loc['a','payment_2008']==1
    assert list(before)==FEATURES

def test_probability_baseline_and_locked_test_evidence():
    m=metrics(np.array([0,1,0,1]),np.array([.5]*4))
    assert m['ROC_AUC']==.5 and m['Brier']==.25 and m['average_precision']==.5
    r=json.loads((ROOT/'evidence/ml_results.json').read_text())
    assert sum(x['n'] for x in r['split'].values())==r['n']
    assert len(r['scores'])==5
    assert abs(r['scores'][0]['average_precision']-r['test_prevalence'])<1e-12
