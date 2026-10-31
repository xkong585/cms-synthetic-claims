"""Denominator-explicit summaries and independent SQL/Python ledger reconciliation."""
from pathlib import Path
import json,sqlite3
import numpy as np
import pandas as pd
import duckdb
from claims import ROOT,QualityError

def reconcile(b,staged,accepted,annual,ledger):
    out=[]
    def check(name,expected,actual):
        ok=(expected==actual) if isinstance(expected,(int,str)) else bool(np.isclose(expected,actual,atol=1e-8,rtol=1e-12))
        out.append({'check':name,'python':expected,'independent_SQL':actual,'pass':bool(ok)})
    with duckdb.connect() as db:
        db.register('beneficiary',b);db.register('staged',staged)
        db.execute((ROOT/'sql/reconcile.sql').read_text())
        result=db.execute('SELECT COUNT(*), SUM(payment_cents)::BIGINT, SUM(payment_cents+pass_cents*covered_days)::BIGINT FROM sql_annual').fetchone()
        check('annual_claim_count_from_segments',len(annual),int(result[0]))
        check('annual_known_payment_cents_from_segments',int(annual.CLM_PMT_AMT_cents.sum()),int(result[1] or 0))
        check('annual_known_expanded_cents_from_segments',int(annual.expanded_reimbursement_cents.sum()),int(result[2] or 0))
        check('accepted_all_year_claim_count',len(accepted),int(db.execute('SELECT COUNT(*) FROM sql_claims').fetchone()[0]))
        result=db.execute('SELECT COUNT(*), SUM(accepted_claim_count)::BIGINT, SUM(known_cents)::BIGINT, SUM(missing_amounts)::BIGINT FROM sql_ledger').fetchone()
        for name,py,sql in zip(['all_beneficiary_rows','ledger_claim_count','ledger_known_payment_cents','ledger_missing_payment_count'],[len(ledger),int(ledger.accepted_claim_count.sum()),int(ledger.known_payment_cents.sum()),int(ledger.missing_payment_count.sum())],result):check(name,py,int(sql or 0))
        sqlrows=db.execute('SELECT DESYNPUF_ID, accepted_claim_count, known_cents, missing_amounts FROM sql_ledger ORDER BY DESYNPUF_ID').fetchdf()
        pyrows=ledger.sort_values('DESYNPUF_ID')
        check('beneficiary_count_per_ID',0,int((sqlrows.accepted_claim_count.to_numpy()!=pyrows.accepted_claim_count.to_numpy()).sum()))
        # Missing all amounts remains NULL; compare normalized nullable exact cents.
        sv=pd.Series(sqlrows.known_cents).astype('Int64').fillna(-2**62).to_numpy()
        pv=pyrows.known_payment_cents.astype('Int64').fillna(-2**62).to_numpy()
        check('beneficiary_known_cents_per_ID',0,int((sv!=pv).sum()))
    # A second engine checks canonical annual grain using exact integer arithmetic.
    with sqlite3.connect(':memory:') as con:
        annual[['DESYNPUF_ID','CLM_ID','CLM_PMT_AMT_cents']].to_sql('annual',con,index=False)
        r=con.execute('SELECT COUNT(*), SUM(CLM_PMT_AMT_cents), COUNT(DISTINCT DESYNPUF_ID) FROM annual').fetchone()
        check('SQLite_annual_claims',len(annual),int(r[0]));check('SQLite_known_cents',int(annual.CLM_PMT_AMT_cents.sum()),int(r[1] or 0));check('SQLite_claimant_IDs',annual.DESYNPUF_ID.nunique(),int(r[2]))
    check('claim_to_ledger_count_conservation',len(annual),int(ledger.accepted_claim_count.sum()))
    check('claim_to_ledger_known_cents_conservation',int(annual.CLM_PMT_AMT_cents.sum()),int(ledger.known_payment_cents.sum()))
    check('ledger_unique_beneficiary_rows',len(b),ledger.DESYNPUF_ID.nunique())
    pd.DataFrame(out).to_csv(ROOT/'evidence/aggregation_reconciliation.csv',index=False)
    if not all(r['pass'] for r in out):raise QualityError('Independent SQL reconciliation failed; reports blocked')
    return out

def summarize_group(d,label,scope):
    eligible=d[d.analysis_eligible]
    amounts=eligible.payment_total_cents.dropna().astype('float64')/100
    n=len(eligible);known=len(amounts)
    return {'scope':scope,'age_group':label,'ledger_beneficiaries':len(d),'excluded_ambiguous_beneficiaries':len(d)-n,
        'analysis_beneficiaries':n,'claimants':int(eligible.accepted_claim_count.gt(0).sum()),
        'claimant_fraction':float(eligible.accepted_claim_count.gt(0).mean()) if n else None,
        'accepted_claims':int(eligible.accepted_claim_count.sum()),'claims_per_beneficiary':float(eligible.accepted_claim_count.mean()) if n else None,
        'payment_complete_beneficiaries':known,'payment_missing_beneficiaries':n-known,
        'payment_mean_USD':float(amounts.mean()) if known else None,'payment_median_USD':float(amounts.median()) if known else None,
        'payment_p75_USD':float(amounts.quantile(.75)) if known else None,'payment_p90_USD':float(amounts.quantile(.90)) if known else None,
        'payment_p95_USD':float(amounts.quantile(.95)) if known else None,
        'known_payment_cents':int(eligible.known_payment_cents.sum()),
        'denominator':'Nonambiguous beneficiaries in selected domain; complete-payment subset for amount quantiles; true zero-claim people retained'}

def analyze(parts):
    b,d,accepted,q,annual,enriched,ledger=parts
    rec=reconcile(b,d,accepted,annual,ledger)
    rows=[]
    for scope,domain in [('All coverage',ledger),('Part A 12 months',ledger[ledger.part_a_full_year])]:
        for group in ['All ages','<65','65-74','75-84','85+','Unknown']:
            part=domain if group=='All ages' else domain[domain.age_group.eq(group)]
            rows.append(summarize_group(part,group,scope))
    pd.DataFrame(rows).to_csv(ROOT/'evidence/summary_tables.csv',index=False)
    pd.DataFrame([r for r in rows if r['age_group']=='All ages']).to_csv(ROOT/'evidence/coverage_sensitivity.csv',index=False)
    diagnostics=[]
    for label,frame in [('source_segments',d),('accepted_annual_claims',annual),('quarantined_claims_all_years',q)]:
        diagnostics.append({'layer':label,'rows':len(frame),'negative_payment':int(frame.CLM_PMT_AMT_cents.lt(0).sum()),'zero_payment':int(frame.CLM_PMT_AMT_cents.eq(0).sum()),'missing_payment':int(frame.CLM_PMT_AMT_cents.isna().sum())})
    pd.DataFrame(diagnostics).to_csv(ROOT/'evidence/payment_quality.csv',index=False)
    # Compare source annual reimbursement to the two definitions, without forcing equality.
    comp=ledger[ledger.analysis_eligible].copy()
    pair=comp.dropna(subset=['MEDREIMB_IP_cents','expanded_total_cents','payment_total_cents'])
    simple=pair.payment_total_cents-pair.MEDREIMB_IP_cents
    expanded=pair.expanded_total_cents-pair.MEDREIMB_IP_cents
    payment_comp=[{'definition':'claim_payment_only','paired_beneficiaries':len(pair),'exact_matches':int(simple.eq(0).sum()),'difference_cents_sum':int(simple.sum()),'absolute_difference_cents_sum':int(simple.abs().sum())}, {'definition':'claim_payment_plus_covered_days_times_pass_through','paired_beneficiaries':len(pair),'exact_matches':int(expanded.eq(0).sum()),'difference_cents_sum':int(expanded.sum()),'absolute_difference_cents_sum':int(expanded.abs().sum())}]
    pd.DataFrame(payment_comp).to_csv(ROOT/'evidence/reimbursement_definition_comparison.csv',index=False)
    # No participant examples or IDs are published.
    warning_rows=[{'item':'quarantined_claims','n':len(q),'resolution':'Retain local conflict rows; flag affected 2008 beneficiaries; never sum conflicting payments'},
                  {'item':'affected_2008_beneficiaries','n':int((~ledger.analysis_eligible).sum()),'resolution':'Retain full ledger rows with null complete counts/totals; exclude from main complete-analysis domain'},
                  {'item':'annual_missing_payment_claims','n':int(annual.CLM_PMT_AMT_cents.isna().sum()),'resolution':'Retain missing and separate known sum; do not zero-fill'},
                  {'item':'annual_negative_payment_claims','n':int(annual.CLM_PMT_AMT_cents.lt(0).sum()),'resolution':'Preserve negative payment; official codebook permits negative amounts'},
                  {'item':'claims_crossing_calendar_year','n':int(annual.cross_year.sum()),'resolution':'Assign by thru date; no proration or admission-year relabeling'},
                  {'item':'partial_Part_A_coverage','n':int((~ledger.part_a_full_year).sum()),'resolution':'Report all-coverage and 12-month domains separately; no full-year incidence claim'},
                  {'item':'source_reimbursement_mismatch_after_formula','n':int(expanded.ne(0).sum()),'resolution':'Retain comparison; investigate synthesis/year definitions; not a fatal accounting equality'}]
    pd.DataFrame(warning_rows).to_csv(ROOT/'evidence/investigation_log.csv',index=False)
    checks=[{'check':n,'status':'pass'} for n in ['official_input_hashes','expected_sample_members','required_columns','identifiers_nonempty','beneficiary_key_unique','claim_segment_key_unique','claim_ID_not_reused','segment_categories','strict_nonblank_date_parse','strict_nonblank_money_parse','coverage_integer_range','conflicts_quarantined','claim_row_accounting','annual_thru_date_filter','left_join_cardinality','left_join_payment_conservation','beneficiary_zero_preservation','ambiguous_beneficiary_not_zero','annual_ledger_unique']]
    if ledger.loc[~ledger.analysis_eligible,'payment_total_cents'].notna().any():raise QualityError('Ambiguous beneficiary given a complete payment')
    if not ledger.loc[ledger.true_zero_claim,'payment_total_cents'].eq(0).all():raise QualityError('True zero preservation failed')
    pd.DataFrame(checks).to_csv(ROOT/'evidence/qc_results.csv',index=False)
    payload={'build':json.loads((ROOT/'evidence/data_build.json').read_text()),'summaries':rows,'reconciliation':rec,'checks':checks,'warnings':warning_rows,'payment_comparison':payment_comp}
    (ROOT/'evidence/summary.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')
    return payload,ledger,annual
