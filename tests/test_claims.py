"""Tiny invented fixtures exercise failure paths; not extra real-data discoveries."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import pandas as pd
import pytest
from claims import parse_date,parse_cents,integer,typed_stage,resolve_claims,annual_join,beneficiary_ledger,QualityError,BENE_FIELDS,IP_FIELDS

def fixture_bene():
    return pd.DataFrame([{'DESYNPUF_ID':'0001','BENE_BIRTH_DT':'19400102','BENE_DEATH_DT':'','BENE_SEX_IDENT_CD':'1','BENE_HI_CVRAGE_TOT_MONS':'12','MEDREIMB_IP':'10.00'},
                         {'DESYNPUF_ID':'0002','BENE_BIRTH_DT':'19500102','BENE_DEATH_DT':'','BENE_SEX_IDENT_CD':'2','BENE_HI_CVRAGE_TOT_MONS':'6','MEDREIMB_IP':'0.00'}],dtype='string')

def fixture_ip(payment='10.00'):
    return pd.DataFrame([{'DESYNPUF_ID':'0001','CLM_ID':'000001','SEGMENT':'1','CLM_FROM_DT':'20081230','CLM_THRU_DT':'20081231','CLM_ADMSN_DT':'20081230','NCH_BENE_DSCHRG_DT':'20081231','CLM_PMT_AMT':payment,'CLM_UTLZTN_DAY_CNT':'1','CLM_PASS_THRU_PER_DIEM_AMT':'0.00'}],dtype='string')

def staged(raw):return typed_stage(raw,'inpatient')[0]
def bstage(raw=None):return typed_stage(fixture_bene() if raw is None else raw,'beneficiary')[0]

def test_money_exact_cents_and_negative():
    assert parse_cents('12.34')==(1234,'ok')
    assert parse_cents('-0.01')==(-1,'ok')
    assert parse_cents('0.00')==(0,'ok')

@pytest.mark.parametrize('value',['1.001','NaN','Inf','1e3','$1.00','abc'])
def test_nonblank_bad_money_not_coerced(value):assert parse_cents(value)==(None,'invalid')

def test_blank_money_missing_not_zero():assert parse_cents('')==(None,'missing')

def test_date_leap_and_strict_format():
    assert parse_date('20080229')[1]=='ok'
    assert parse_date('20090229')[1]=='invalid'
    assert parse_date('2008-01-01')[1]=='invalid'
    assert parse_date('')[1]=='missing'

def test_integer_coverage_contract():
    assert integer('12',0,12)==(12,'ok')
    assert integer('13',0,12)[1]=='invalid'
    assert integer('1.5',0,12)[1]=='invalid'

def test_duplicate_beneficiary_stops():
    raw=fixture_bene()
    with pytest.raises(QualityError,match='Duplicate'):bstage(pd.concat([raw,raw]))

def test_required_schema_stops():
    with pytest.raises(QualityError,match='required'):staged(fixture_ip().drop(columns='SEGMENT'))

def test_missing_id_stops():
    raw=fixture_ip();raw.loc[0,'CLM_ID']=''
    with pytest.raises(QualityError,match='identifier'):staged(raw)

def test_duplicate_segment_key_stops():
    d=staged(fixture_ip())
    with pytest.raises(QualityError,match='segment key'):resolve_claims(pd.concat([d,d]))

def test_cross_beneficiary_claim_reuse_stops():
    raw=pd.concat([fixture_ip(),fixture_ip()],ignore_index=True);raw.loc[1,'DESYNPUF_ID']='0002'
    with pytest.raises(QualityError,match='reused'):resolve_claims(staged(raw))

def test_consistent_segments_count_money_once():
    raw=pd.concat([fixture_ip(),fixture_ip()],ignore_index=True);raw.loc[1,'SEGMENT']='2';raw.loc[1,'CLM_FROM_DT']='';raw.loc[1,'CLM_THRU_DT']='';raw.loc[1,'CLM_UTLZTN_DAY_CNT']=''
    a,q,_,_=resolve_claims(staged(raw))
    assert len(a)==1 and len(q)==0 and a.CLM_PMT_AMT_cents.iloc[0]==1000

def test_conflicting_segments_quarantine_entire_claim():
    raw=pd.concat([fixture_ip(),fixture_ip('20.00')],ignore_index=True);raw.loc[1,'SEGMENT']='2'
    a,q,detail,_=resolve_claims(staged(raw))
    assert len(a)==0 and len(q)==1 and detail.CLM_PMT_AMT.iloc[0]
    assert pd.isna(q.CLM_PMT_AMT_cents.iloc[0])
    ledger=beneficiary_ledger(bstage(),a,q)
    affected=ledger[ledger.DESYNPUF_ID=='0001'].iloc[0]
    assert not affected.analysis_eligible and pd.isna(affected.payment_total_cents) and pd.isna(affected.claim_count)
    assert not affected.true_zero_claim

def test_reversed_dates_quarantined():
    raw=fixture_ip();raw.loc[0,'CLM_FROM_DT']='20090101'
    a,q,_,_=resolve_claims(staged(raw));assert len(a)==0 and q.quarantine_reason.iloc[0]=='invalid_date_order'

def test_year_by_thru_date_not_admission():
    raw=fixture_ip();raw.loc[0,'CLM_FROM_DT']='20071230';raw.loc[0,'CLM_ADMSN_DT']='20071230'
    a,q,_,_=resolve_claims(staged(raw));annual,_=annual_join(a,bstage())
    assert len(annual)==1 and annual.cross_year.iloc[0]
    raw.loc[0,'CLM_THRU_DT']='20090102';raw.loc[0,'NCH_BENE_DSCHRG_DT']='20090102'
    a,_,_,_=resolve_claims(staged(raw));assert len(annual_join(a,bstage())[0])==0

def test_unmatched_claim_stops(tmp_path,monkeypatch):
    import claims
    monkeypatch.setattr(claims,'ROOT',tmp_path)
    raw=fixture_ip();raw.loc[0,'DESYNPUF_ID']='not-in-beneficiaries'
    a,_,_,_=resolve_claims(staged(raw))
    with pytest.raises(QualityError,match='Unmatched'):annual_join(a,bstage())
    assert (tmp_path/'data/processed/unmatched_claims.parquet').exists()

def test_missing_payment_retained_as_null_and_true_zero_kept():
    a,q,_,_=resolve_claims(staged(fixture_ip('')));annual,_=annual_join(a,bstage());ledger=beneficiary_ledger(bstage(),annual,q).set_index('DESYNPUF_ID')
    assert ledger.loc['0001','accepted_claim_count']==1 and ledger.loc['0001','missing_payment_count']==1
    assert pd.isna(ledger.loc['0001','payment_total_cents'])
    assert ledger.loc['0002','true_zero_claim'] and ledger.loc['0002','payment_total_cents']==0

def test_negative_payment_not_deleted():
    a,q,_,_=resolve_claims(staged(fixture_ip('-2.50')))
    ledger=beneficiary_ledger(bstage(),a,q).set_index('DESYNPUF_ID')
    assert ledger.loc['0001','payment_total_cents']==-250

def test_unknown_thru_conflict_flags_beneficiary():
    raw=pd.concat([fixture_ip(),fixture_ip()],ignore_index=True);raw.loc[1,'SEGMENT']='2';raw.loc[1,'CLM_THRU_DT']='20091231'
    a,q,_,_=resolve_claims(staged(raw));ledger=beneficiary_ledger(bstage(),a,q)
    assert not ledger.loc[ledger.DESYNPUF_ID=='0001','analysis_eligible'].iloc[0]

def test_sql_independently_reconstructs_consistent_grain(tmp_path,monkeypatch):
    import analyze
    monkeypatch.setattr(analyze,'ROOT',Path(__file__).resolve().parents[1])
    b=bstage();raw=pd.concat([fixture_ip(),fixture_ip()],ignore_index=True);raw.loc[1,'SEGMENT']='2';s=staged(raw)
    a,q,_,_=resolve_claims(s);annual,_=annual_join(a,b);ledger=beneficiary_ledger(b,annual,q)
    # Keep test evidence separate from the production evidence directory.
    actual_root=analyze.ROOT; test_root=tmp_path
    (test_root/'evidence').mkdir();(test_root/'sql').mkdir()
    (test_root/'sql/reconcile.sql').write_text((actual_root/'sql/reconcile.sql').read_text())
    monkeypatch.setattr(analyze,'ROOT',test_root)
    checks=analyze.reconcile(b,s,a,annual,ledger)
    assert all(r['pass'] for r in checks)

def test_failed_rerun_invalidates_report(tmp_path,monkeypatch):
    import run_pipeline
    (tmp_path/'reports').mkdir();(tmp_path/'evidence').mkdir()
    for f in ['report.html','brief.pdf','READY.json']:(tmp_path/'reports'/f).write_text('stale')
    def broken():raise QualityError('intentional corrupt input')
    monkeypatch.setattr(run_pipeline,'ROOT',tmp_path);monkeypatch.setattr(run_pipeline,'download',broken)
    with pytest.raises(QualityError):run_pipeline.run(tests=False)
    assert not (tmp_path/'reports/report.html').exists() and not (tmp_path/'reports/READY.json').exists()
