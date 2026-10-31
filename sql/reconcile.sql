-- Independent claim-grain reconstruction from STAGED SEGMENTS, never raw SUM(payment).
-- Missing segment values do not create a second distinct nonmissing value.
CREATE OR REPLACE TEMP VIEW sql_claims AS
SELECT DESYNPUF_ID, CLM_ID,
       MIN(CLM_FROM_DT_date) AS from_date, MIN(CLM_THRU_DT_date) AS thru_date,
       MIN(CLM_ADMSN_DT_date) AS admission, MIN(NCH_BENE_DSCHRG_DT_date) AS discharge,
       MIN(CLM_PMT_AMT_cents) AS payment_cents,
       MIN(CLM_PASS_THRU_PER_DIEM_AMT_cents) AS pass_cents,
       MIN(CLM_UTLZTN_DAY_CNT_int) AS covered_days
FROM staged
GROUP BY DESYNPUF_ID, CLM_ID
HAVING GREATEST(
 COUNT(DISTINCT NULLIF(CLM_FROM_DT,'')), COUNT(DISTINCT NULLIF(CLM_THRU_DT,'')),
 COUNT(DISTINCT NULLIF(CLM_ADMSN_DT,'')), COUNT(DISTINCT NULLIF(NCH_BENE_DSCHRG_DT,'')),
 COUNT(DISTINCT NULLIF(CLM_PMT_AMT,'')), COUNT(DISTINCT NULLIF(CLM_PASS_THRU_PER_DIEM_AMT,'')),
 COUNT(DISTINCT NULLIF(CLM_UTLZTN_DAY_CNT,''))) <= 1
 AND MIN(CLM_FROM_DT_date) IS NOT NULL AND MIN(CLM_THRU_DT_date) IS NOT NULL
 AND MIN(CLM_FROM_DT_date) <= MIN(CLM_THRU_DT_date)
 AND (MIN(CLM_ADMSN_DT_date) IS NULL OR MIN(NCH_BENE_DSCHRG_DT_date) IS NULL
      OR MIN(CLM_ADMSN_DT_date) <= MIN(NCH_BENE_DSCHRG_DT_date));
CREATE OR REPLACE TEMP VIEW sql_annual AS
SELECT * FROM sql_claims WHERE thru_date >= DATE '2008-01-01' AND thru_date < DATE '2009-01-01';
-- All beneficiary rows stay present; no inner join to claim aggregates.
CREATE OR REPLACE TEMP VIEW sql_ledger AS
SELECT b.DESYNPUF_ID, COALESCE(c.claims,0)::BIGINT AS accepted_claim_count,
       CASE WHEN c.claims IS NULL THEN 0 ELSE c.known_cents END AS known_cents,
       COALESCE(c.missing_amounts,0)::BIGINT AS missing_amounts
FROM beneficiary b LEFT JOIN (
 SELECT DESYNPUF_ID, COUNT(*) claims, SUM(payment_cents)::BIGINT known_cents,
        COUNT(*)-COUNT(payment_cents) missing_amounts
 FROM sql_annual GROUP BY DESYNPUF_ID
) c USING (DESYNPUF_ID);
