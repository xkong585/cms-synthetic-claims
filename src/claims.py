"""Typed staging, claim-grain resolution and a zero-preserving beneficiary ledger."""
from pathlib import Path
from datetime import datetime,date
from decimal import Decimal,InvalidOperation
import json,re,zipfile
import numpy as np
import pandas as pd
from download_data import ROOT
CONTRACT=json.loads((ROOT/'docs/schema_contract.json').read_text())
BENE_FIELDS=CONTRACT['beneficiary_required'];IP_FIELDS=CONTRACT['inpatient_required']
CLAIM_KEYS=['DESYNPUF_ID','CLM_ID']
CLAIM_FIELDS=['CLM_FROM_DT','CLM_THRU_DT','CLM_ADMSN_DT','NCH_BENE_DSCHRG_DT','CLM_PMT_AMT','CLM_UTLZTN_DAY_CNT','CLM_PASS_THRU_PER_DIEM_AMT']

class QualityError(ValueError):pass

def parse_date(value):
    if value is None or pd.isna(value) or str(value).strip()=='':return pd.NaT,'missing'
    s=str(value).strip()
    if not re.fullmatch(r'\d{8}',s):return pd.NaT,'invalid'
    try:return pd.Timestamp(datetime.strptime(s,'%Y%m%d')),'ok'
    except (ValueError,OverflowError):return pd.NaT,'invalid'

def parse_cents(value):
    if value is None or pd.isna(value) or str(value).strip()=='':return None,'missing'
    s=str(value).strip()
    if not re.fullmatch(r'-?\d+(?:\.\d{1,2})?',s):return None,'invalid'
    try:
        v=Decimal(s)*100
        if not v.is_finite() or abs(v)>2**62:return None,'invalid'
        return int(v),'ok'
    except InvalidOperation:return None,'invalid'

def integer(value,low=0,high=None):
    if value is None or pd.isna(value) or str(value).strip()=='':return None,'missing'
    s=str(value).strip()
    if not re.fullmatch(r'\d+',s):return None,'invalid'
    n=int(s)
    if n<low or (high is not None and n>high):return None,'invalid'
    return n,'ok'

def read_zip(file,expected):
    with zipfile.ZipFile(file) as z:
        names=[n for n in z.namelist() if n.lower().endswith('.csv')]
        if len(names)!=1 or names[0].split('/')[-1]!=expected:raise QualityError('Unexpected sample/file inside ZIP')
        with z.open(names[0]) as f:return pd.read_csv(f,dtype='string',keep_default_na=False)

def require_schema(d,fields,name):
    missing=set(fields)-set(d)
    if missing:raise QualityError(name+': missing required fields '+','.join(sorted(missing)))

def typed_stage(raw,table):
    fields=BENE_FIELDS if table=='beneficiary' else IP_FIELDS
    require_schema(raw,fields,table)
    d=raw[fields].copy();d.insert(0,'source_row',range(1,len(d)+1));errors=[];audit=[]
    dates=['BENE_BIRTH_DT','BENE_DEATH_DT'] if table=='beneficiary' else ['CLM_FROM_DT','CLM_THRU_DT','CLM_ADMSN_DT','NCH_BENE_DSCHRG_DT']
    money=['MEDREIMB_IP'] if table=='beneficiary' else ['CLM_PMT_AMT','CLM_PASS_THRU_PER_DIEM_AMT']
    ints=['BENE_HI_CVRAGE_TOT_MONS'] if table=='beneficiary' else ['SEGMENT','CLM_UTLZTN_DAY_CNT']
    for col in dates+money+ints:
        parser=parse_date if col in dates else parse_cents if col in money else (lambda v:integer(v,1,2)) if col=='SEGMENT' else (lambda v:integer(v,0,12)) if col=='BENE_HI_CVRAGE_TOT_MONS' else integer
        parsed=d[col].map(parser);target=col+'_date' if col in dates else col+'_cents' if col in money else col+'_int'
        values=[v[0] for v in parsed];statuses=[v[1] for v in parsed]
        d[target]=pd.to_datetime(values) if col in dates else pd.array(values,dtype='Int64')
        d[col+'_status']=statuses
        audit.append({'table':table,'field':col,'rows':len(d),'ok':statuses.count('ok'),'missing':statuses.count('missing'),'invalid':statuses.count('invalid')})
        for row,value,status in zip(d.source_row,d[col],statuses):
            if status=='invalid':errors.append({'table':table,'source_row':int(row),'field':col,'raw_value':value,'reason':'invalid_nonblank_value'})
    for key in ['DESYNPUF_ID']+(['CLM_ID'] if table=='inpatient' else []):
        if d[key].isna().any() or d[key].str.strip().eq('').any():raise QualityError('Missing identifier: '+key)
    if table=='beneficiary':
        if d.DESYNPUF_ID.duplicated().any():raise QualityError('Duplicate beneficiary key')
        if not d.BENE_SEX_IDENT_CD.isin(['0','1','2']).all():raise QualityError('Unknown source sex category')
        if d.BENE_HI_CVRAGE_TOT_MONS_int.isna().any():raise QualityError('Missing/invalid coverage months')
    if table=='inpatient' and d.SEGMENT_int.isna().any():raise QualityError('Missing/invalid segment code')
    return d,errors,audit

def resolve_claims(d):
    if d.duplicated(CLAIM_KEYS+['SEGMENT']).any():raise QualityError('Duplicate claim/segment key')
    reuse=d.groupby('CLM_ID').DESYNPUF_ID.nunique()
    if reuse.gt(1).any():raise QualityError('Claim ID reused across beneficiaries')
    raw=d[CLAIM_KEYS+CLAIM_FIELDS].replace('',pd.NA)
    unique=raw.groupby(CLAIM_KEYS,sort=True)[CLAIM_FIELDS].nunique(dropna=True)
    conflict=unique.gt(1)
    badindex=conflict.index[conflict.any(axis=1)]
    # At this point no conflicting value is silently selected. first() ignores blanks
    # only to expose a candidate and the quarantine attribution; conflicts stay flagged.
    parsed=['CLM_FROM_DT_date','CLM_THRU_DT_date','CLM_ADMSN_DT_date','NCH_BENE_DSCHRG_DT_date','CLM_PMT_AMT_cents','CLM_PASS_THRU_PER_DIEM_AMT_cents','CLM_UTLZTN_DAY_CNT_int']
    c=d.sort_values(['DESYNPUF_ID','CLM_ID','SEGMENT_int']).groupby(CLAIM_KEYS,sort=True)[parsed].first().reset_index()
    size=d.groupby(CLAIM_KEYS).size();c['segment_rows']=c.set_index(CLAIM_KEYS).index.map(size)
    c['quarantine_reason']=''
    c.loc[c.set_index(CLAIM_KEYS).index.isin(badindex),'quarantine_reason']='conflicting_segments'
    reason=c.quarantine_reason
    missing=c.CLM_FROM_DT_date.isna()|c.CLM_THRU_DT_date.isna()
    reason=reason.mask(reason.eq('')&missing,'missing_billing_date')
    reversed_dates=c.CLM_FROM_DT_date.gt(c.CLM_THRU_DT_date)|c.CLM_ADMSN_DT_date.gt(c.NCH_BENE_DSCHRG_DT_date)
    reason=reason.mask(reason.eq('')&reversed_dates,'invalid_date_order')
    c['quarantine_reason']=reason
    c['claim_year']=c.CLM_THRU_DT_date.dt.year.astype('Int64')
    # Multiple/nonexistent thru dates make annual attribution uncertain. Flag all years.
    thru_n=c.set_index(CLAIM_KEYS).index.map(unique.CLM_THRU_DT)
    c['year_attribution_uncertain']=(np.asarray(thru_n)!=1)
    # Conflicting fields have no defensible canonical value, even in quarantine.
    # Do not publish sums of an arbitrarily selected segment value.
    for raw_col,parsed_col in zip(CLAIM_FIELDS,['CLM_FROM_DT_date','CLM_THRU_DT_date','CLM_ADMSN_DT_date','NCH_BENE_DSCHRG_DT_date','CLM_PMT_AMT_cents','CLM_UTLZTN_DAY_CNT_int','CLM_PASS_THRU_PER_DIEM_AMT_cents']):
        bad_keys=conflict.index[conflict[raw_col]]
        bad_mask=c.set_index(CLAIM_KEYS).index.isin(bad_keys)
        c.loc[bad_mask,parsed_col]=pd.NaT if parsed_col.endswith('_date') else pd.NA
    c.loc[c.year_attribution_uncertain,'claim_year']=pd.NA
    c['cross_year']=c.CLM_FROM_DT_date.dt.year.ne(c.CLM_THRU_DT_date.dt.year)&~missing
    c['payment_negative']=c.CLM_PMT_AMT_cents.lt(0).fillna(False)
    c['payment_zero']=c.CLM_PMT_AMT_cents.eq(0).fillna(False)
    c['expanded_reimbursement_cents']=c.CLM_PMT_AMT_cents+c.CLM_UTLZTN_DAY_CNT_int*c.CLM_PASS_THRU_PER_DIEM_AMT_cents
    quarantine=c[c.quarantine_reason.ne('')].copy();accepted=c[c.quarantine_reason.eq('')].copy()
    conflict_detail=conflict.loc[conflict.any(axis=1)].reset_index()
    return accepted,quarantine,conflict_detail,unique

def annual_join(claims,bene):
    if bene.DESYNPUF_ID.duplicated().any():raise QualityError('Duplicate beneficiary key')
    annual=claims[claims.claim_year.eq(2008)].copy()
    joined=annual.merge(bene,on='DESYNPUF_ID',how='left',validate='many_to_one',indicator=True)
    orphans=joined[joined._merge!='both']
    if len(orphans):
        (ROOT/'data/processed').mkdir(parents=True,exist_ok=True);orphans.to_parquet(ROOT/'data/processed/unmatched_claims.parquet',index=False)
        raise QualityError('Unmatched annual claims: '+str(len(orphans)))
    if len(joined)!=len(annual):raise QualityError('Join inflated annual claims')
    if int(joined.CLM_PMT_AMT_cents.sum())!=int(annual.CLM_PMT_AMT_cents.sum()):raise QualityError('Join changed known payment cents')
    return annual,joined.drop(columns='_merge')

def beneficiary_ledger(bene,annual,quarantine):
    if bene.DESYNPUF_ID.duplicated().any():raise QualityError('Duplicate beneficiary key')
    g=annual.groupby('DESYNPUF_ID')
    ag=g.agg(accepted_claim_count=('CLM_ID','size'),known_payment_cents=('CLM_PMT_AMT_cents',lambda x:x.sum(min_count=1)),missing_payment_count=('CLM_PMT_AMT_cents',lambda x:int(x.isna().sum())),known_expanded_cents=('expanded_reimbursement_cents',lambda x:x.sum(min_count=1)),missing_expanded_count=('expanded_reimbursement_cents',lambda x:int(x.isna().sum())))
    impact=quarantine[quarantine.claim_year.eq(2008)|quarantine.year_attribution_uncertain]
    qcount=impact.groupby('DESYNPUF_ID').size().rename('quarantined_claim_count')
    out=bene.merge(ag,on='DESYNPUF_ID',how='left',validate='one_to_one').merge(qcount,on='DESYNPUF_ID',how='left',validate='one_to_one')
    for col in ['accepted_claim_count','missing_payment_count','missing_expanded_count','quarantined_claim_count']:out[col]=out[col].fillna(0).astype('int64')
    out['analysis_eligible']=out.quarantined_claim_count.eq(0)
    out['true_zero_claim']=out.accepted_claim_count.eq(0)&out.analysis_eligible
    # A known-payment partial sum is explicit. It is not the complete annual amount.
    for col in ['known_payment_cents','known_expanded_cents']:
        out[col]=out[col].astype('Int64');out.loc[out.accepted_claim_count.eq(0),col]=0
    out['claim_count']=out.accepted_claim_count.astype('Int64').where(out.analysis_eligible)
    out['payment_total_cents']=out.known_payment_cents.where(out.analysis_eligible&out.missing_payment_count.eq(0))
    out['expanded_total_cents']=out.known_expanded_cents.where(out.analysis_eligible&out.missing_expanded_count.eq(0))
    birth=out.BENE_BIRTH_DT_date;ref=pd.Timestamp('2008-12-31')
    age=ref.year-birth.dt.year-((birth.dt.month>ref.month)|((birth.dt.month==ref.month)&(birth.dt.day>ref.day))).astype('Int64')
    out['age_at_2008_12_31']=age.astype('Int64')
    if age.dropna().lt(0).any():raise QualityError('Birth after fixed age reference date')
    out['age_group']=pd.cut(age.astype('float64'),[-np.inf,65,75,85,np.inf],right=False,labels=['<65','65-74','75-84','85+']).astype('string').fillna('Unknown')
    out['part_a_full_year']=out.BENE_HI_CVRAGE_TOT_MONS_int.eq(12)
    return out

def build():
    root=ROOT/'data/processed';e=ROOT/'evidence';root.mkdir(parents=True,exist_ok=True);e.mkdir(exist_ok=True)
    braw=read_zip(ROOT/'data/raw/beneficiary_2008_sample1.zip','DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv')
    iraw=read_zip(ROOT/'data/raw/inpatient_2008_2010_sample1.zip','DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.csv')
    b,be,ba=typed_stage(braw,'beneficiary');d,de,da=typed_stage(iraw,'inpatient')
    errors=be+de
    pd.DataFrame(errors,columns=['table','source_row','field','raw_value','reason']).to_csv(root/'parse_errors.csv',index=False)
    pd.DataFrame(ba+da).to_csv(e/'parse_audit.csv',index=False)
    pd.DataFrame([{'table':'beneficiary','rows':len(braw),'source_columns':len(braw.columns)},{'table':'inpatient','rows':len(iraw),'source_columns':len(iraw.columns)}]).to_csv(e/'raw_profile.csv',index=False)
    if errors:raise QualityError('Nonblank type parsing errors: '+str(len(errors)))
    b.to_parquet(root/'stg_beneficiary.parquet',index=False);d.to_parquet(root/'stg_inpatient.parquet',index=False)
    accepted,q,conflicts,unique=resolve_claims(d)
    q.to_parquet(root/'claim_quarantine.parquet',index=False);conflicts.to_csv(root/'claim_conflicts.csv',index=False)
    if len(accepted)+len(q)!=len(unique):raise QualityError('Claim accounting failed')
    annual,enriched=annual_join(accepted,b);ledger=beneficiary_ledger(b,annual,q)
    accepted.to_parquet(root/'claims_all_accepted.parquet',index=False);annual.to_parquet(root/'claims_2008.parquet',index=False)
    enriched.to_parquet(root/'claims_enriched.parquet',index=False);ledger.to_parquet(root/'beneficiary_2008_analytic.parquet',index=False)
    pd.DataFrame([{'key':'DESYNPUF_ID','distinct':d.DESYNPUF_ID.nunique(),'duplicate_rows':int(d.duplicated('DESYNPUF_ID').sum())},
                  {'key':'CLM_ID','distinct':d.CLM_ID.nunique(),'duplicate_rows':int(d.duplicated('CLM_ID').sum())},
                  {'key':'DESYNPUF_ID+CLM_ID','distinct':len(unique),'duplicate_rows':int(d.duplicated(CLAIM_KEYS).sum())},
                  {'key':'DESYNPUF_ID+CLM_ID+SEGMENT','distinct':len(d),'duplicate_rows':0}]).to_csv(e/'grain_audit.csv',index=False)
    pd.DataFrame([{'field':col,'conflicting_claims':int(unique[col].gt(1).sum())} for col in CLAIM_FIELDS]).to_csv(e/'segment_conflicts_by_field.csv',index=False)
    rows=[]
    for status,frame in [('accepted',accepted),('quarantined',q)]:
        for year,part in frame.groupby('claim_year',dropna=False):rows.append({'status':status,'claim_year':str(year),'claims':len(part),'known_payment_cents':int(part.CLM_PMT_AMT_cents.sum()),'missing_or_conflicting_payment_claims':int(part.CLM_PMT_AMT_cents.isna().sum()),'cross_year':int(part.cross_year.sum())})
    pd.DataFrame(rows).to_csv(e/'year_boundary_summary.csv',index=False)
    pd.DataFrame([{'claim_rows_in':len(annual),'claim_rows_out':len(enriched),'matched':len(enriched),'unmatched':0,'known_cents_in':int(annual.CLM_PMT_AMT_cents.sum()),'known_cents_out':int(enriched.CLM_PMT_AMT_cents.sum())}]).to_csv(e/'join_audit.csv',index=False)
    dates=[]
    for status,frame in [('all_records',d),('accepted_claims',accepted),('quarantined_claims',q)]:
        dates.append({'layer':status,'n':len(frame),'missing_from':int(frame.CLM_FROM_DT_date.isna().sum()),'missing_thru':int(frame.CLM_THRU_DT_date.isna().sum()),'from_after_thru':int(frame.CLM_FROM_DT_date.gt(frame.CLM_THRU_DT_date).sum()),'admission_after_discharge':int(frame.CLM_ADMSN_DT_date.gt(frame.NCH_BENE_DSCHRG_DT_date).sum())})
    pd.DataFrame(dates).to_csv(e/'date_qc.csv',index=False)
    pd.DataFrame([{'stage':'source_segment_records','n':len(d)}, {'stage':'distinct_claims','n':len(unique)}, {'stage':'quarantined_claims_all_years','n':len(q)}, {'stage':'accepted_claims_all_years','n':len(accepted)}, {'stage':'accepted_claims_2008','n':len(annual)}, {'stage':'beneficiary_ledger','n':len(ledger)}, {'stage':'eligible_beneficiaries','n':int(ledger.analysis_eligible.sum())}, {'stage':'affected_beneficiaries','n':int((~ledger.analysis_eligible).sum())}, {'stage':'true_zero_beneficiaries','n':int(ledger.true_zero_claim.sum())}]).to_csv(e/'cohort_flow.csv',index=False)
    summary={'raw_beneficiaries':len(b),'raw_segments':len(d),'distinct_claims':len(unique),'multi_segment_claims':int((d.groupby(CLAIM_KEYS).size()>1).sum()),'quarantined_claims':len(q),'quarantined_2008':int(q.claim_year.eq(2008).sum()),'accepted_claims_2008':len(annual),'eligible_beneficiaries':int(ledger.analysis_eligible.sum()),'affected_beneficiaries':int((~ledger.analysis_eligible).sum()),'zero_claim_beneficiaries':int(ledger.true_zero_claim.sum()),'parse_errors':len(errors)}
    (e/'data_build.json').write_text(json.dumps(summary,indent=2)+'\n')
    return b,d,accepted,q,annual,enriched,ledger
