"""2008 baseline -> 2009 observed inpatient claims; synthetic demonstration only."""
import json
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss,log_loss
from threadpoolctl import threadpool_limits
from claims import ROOT,read_zip,parse_date
from ml_report import publish
FEATURES=['age','sex','part_a_2008','hmo_2008','claims_2008','payment_2008','days_2008','days_since_last_2008']

def metrics(y,p):
    return {'ROC_AUC':float(roc_auc_score(y,p)),'average_precision':float(average_precision_score(y,p)),'Brier':float(brier_score_loss(y,p)),'log_loss':float(log_loss(y,p,labels=[0,1]))}

def complete_followup(raw):
    coverage=pd.to_numeric(raw.BENE_HI_CVRAGE_TOT_MONS,errors='coerce');hmo=pd.to_numeric(raw.BENE_HMO_CVRAGE_TOT_MONS,errors='coerce');parsed=raw.BENE_DEATH_DT.map(parse_date)
    if any(status=='invalid' for _,status in parsed):raise ValueError('Invalid follow-up death date')
    death=pd.to_datetime(parsed.map(lambda x:x[0]));return (coverage==12)&(hmo==0)&(death.isna()|(death>pd.Timestamp('2009-12-31')))

def baseline_features(b,claims):
    c=claims.loc[claims.claim_year==2008].copy()
    assert (c.CLM_THRU_DT_date<=pd.Timestamp('2008-12-31')).all()
    g=c.groupby('DESYNPUF_ID').agg(claims_2008=('CLM_ID','size'),payment_2008=('CLM_PMT_AMT_cents','sum'),days_2008=('CLM_UTLZTN_DAY_CNT_int','sum'),last=('CLM_THRU_DT_date','max'))
    x=b.set_index('DESYNPUF_ID').join(g,how='left');birth=pd.to_datetime(x.BENE_BIRTH_DT,format='%Y%m%d',errors='coerce')
    x['age']=(pd.Timestamp('2008-12-31')-birth).dt.days/365.25;x['sex']=pd.to_numeric(x.BENE_SEX_IDENT_CD,errors='coerce');x['part_a_2008']=pd.to_numeric(x.BENE_HI_CVRAGE_TOT_MONS,errors='coerce');x['hmo_2008']=pd.to_numeric(x.BENE_HMO_CVRAGE_TOT_MONS,errors='coerce')
    for k in ['claims_2008','payment_2008','days_2008']:x[k]=x[k].fillna(0).astype(float)
    x['payment_2008']/=100;x['days_since_last_2008']=(pd.Timestamp('2008-12-31')-x['last']).dt.days.fillna(366)
    return x[FEATURES].astype(float)

def split_ids(y):
    idx=np.arange(len(y));train,other=train_test_split(idx,test_size=.4,stratify=y,random_state=20261031);cal,test=train_test_split(other,test_size=.5,stratify=np.asarray(y)[other],random_state=20261032)
    return train,cal,test

def logits(p):
    p=np.clip(p,1e-6,1-1e-6);return np.log(p/(1-p)).reshape(-1,1)

def run_ml():
    b=read_zip(ROOT/'data/raw/beneficiary_2008_sample1.zip','DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv');future=read_zip(ROOT/'data/raw/beneficiary_2009_sample1.zip','DE1_0_2009_Beneficiary_Summary_File_Sample_1.csv')
    assert b.DESYNPUF_ID.is_unique and future.DESYNPUF_ID.is_unique
    claims=pd.read_parquet(ROOT/'data/processed/claims_all_accepted.parquet');q=pd.read_parquet(ROOT/'data/processed/claim_quarantine.parquet')
    X=baseline_features(b,claims);initial=len(X);audit=[]
    def restrict(mask,reason):
        nonlocal X
        old=len(X);X=X.loc[mask.reindex(X.index,fill_value=False)];audit.append({'reason':reason,'excluded':old-len(X),'remaining':len(X)})
    death=b.set_index('DESYNPUF_ID').BENE_DEATH_DT.map(parse_date)
    if any(s=='invalid' for _,s in death):raise ValueError('Invalid baseline death date')
    alive=death.map(lambda x:pd.isna(x[0]) or x[0]>pd.Timestamp('2008-12-31'));restrict(alive,'Died before prediction boundary')
    good=future.loc[complete_followup(future),'DESYNPUF_ID'];restrict(pd.Series(X.index.isin(good),index=X.index),'Missing 2009, incomplete Part A, HMO or death during 2009')
    bad=q.loc[q.claim_year.isin([2008,2009])|q.claim_year.isna(),'DESYNPUF_ID'];restrict(pd.Series(~X.index.isin(bad),index=X.index),'Ambiguous baseline or target-year claim')
    positive=set(claims.loc[claims.claim_year==2009,'DESYNPUF_ID']);y=X.index.isin(positive).astype(int)
    train,cal,test=split_ids(y);scores=[];calibration=[];subgroups=[];predictions={};importance={}
    with threadpool_limits(limits=1):
        prior=float(y[train].mean());predictions['Training prevalence']=np.full(len(test),prior)
        models={'Logistic regression':make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),LogisticRegression(C=.1,max_iter=1000,random_state=20261031)),'Gradient boosting':make_pipeline(SimpleImputer(strategy='median'),HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,min_samples_leaf=100,l2_regularization=10,early_stopping=False,random_state=20261031))}
        for name,model in models.items():
            model.fit(X.iloc[train],y[train]);pi=permutation_importance(model,X.iloc[cal],y[cal],scoring='neg_log_loss',n_repeats=5,random_state=20261031);importance[name]=dict(zip(FEATURES,pi.importances_mean.tolist()));pc=model.predict_proba(X.iloc[cal])[:,1];pt=model.predict_proba(X.iloc[test])[:,1]
            calibrator=LogisticRegression(C=1e6,max_iter=1000);calibrator.fit(logits(pc),y[cal]);predictions[name]=pt;predictions[name+' + calibration']=calibrator.predict_proba(logits(pt))[:,1]
        for name,p in predictions.items():
            scores.append({'model':name,**metrics(y[test],p)})
            bins=pd.qcut(pd.Series(p),10,duplicates='drop')
            if bins.isna().all():bins=pd.Series(['constant']*len(p))
            z=pd.DataFrame({'bin':bins,'p':p,'y':y[test]})
            for _,g in z.groupby('bin',observed=True):calibration.append({'model':name,'n':len(g),'mean_probability':float(g.p.mean()),'observed_rate':float(g.y.mean())})
            for variable,labels in [('sex',X.iloc[test].sex.astype(str)),('prior_claim',pd.Series(np.where(X.iloc[test].claims_2008>0,'yes','no'),index=X.iloc[test].index)),('age',pd.cut(X.iloc[test].age,[0,64,74,84,200],labels=['<65','65-74','75-84','85+']).astype(str))]:
                for label in sorted(labels.unique()):
                    m=(labels==label).to_numpy()
                    if len(np.unique(y[test][m]))==2:subgroups.append({'variable':variable,'group':label,'model':name,'n':int(m.sum()),'positives':int(y[test][m].sum()),**metrics(y[test][m],p[m])})
    local=pd.DataFrame({'DESYNPUF_ID':X.index[test],'target':y[test],**predictions});local.to_parquet(ROOT/'data/processed/ml_test_predictions.parquet',index=False)
    result={'title':'CMS | Next-year inpatient claims ML','scope':f'CMS DE-SynPUF Sample 1, synthetic data only. {len(X):,} eligible beneficiaries. Baseline features end 2008-12-31; target is at least one accepted claim ending in 2009. Full 2009 Part A, no HMO and survival through 2009 are required to interpret absence as zero.','validation':'Fixed seed, stratified beneficiary split: 60% training, 20% probability calibration, 20% locked test. Fixed hyperparameters; median imputation and scaling fitted on training only. Platt calibration uses calibration people only. No test-driven model selection. This is a held-out-person evaluation with forward-looking labels, not validation in a later calendar cohort.','limitations':'Synthetic relationships do not demonstrate performance on real patients or clinical usefulness. Eligibility depends on later enrollment and survival, so results apply to that retrospective complete-follow-up population. Labels include carry-in stays ending in 2009, not incident admissions or readmissions. Aggregate held-out errors have no external validation or confidence intervals; subgroup scores do not establish fairness.','primary_metric':'average_precision','source_population_n':initial,'n':len(X),'features':FEATURES,'cohort_flow':audit,'split':{k:{'n':len(v),'positives':int(y[v].sum())} for k,v in [('train',train),('calibration',cal),('test',test)]},'test_prevalence':float(y[test].mean()),'scores':scores,'calibration':calibration,'subgroups':subgroups,'permutation_importance':{'metric':'increase in calibration-split log loss','features_by_model':importance,'repeats':5,'used_for_selection':False},'seed':20261031}
    publish(ROOT,result);return result
if __name__=='__main__':run_ml()
