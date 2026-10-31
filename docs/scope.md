# Frozen scope | 2026-10-31 | Synthetic CMS DE-SynPUF Sample 1

Purpose: demonstrate reliable claims data preparation and exact reconciliation,
not real healthcare cost, disease burden, causal effects or hospital quality.
No Kaiser patient data, risk prediction or inference to Medicare populations.

Inputs: official Sample 1 2008 beneficiary summary and 2008-2010 inpatient claims.
Annual claim attribution: CLM_THRU_DT in [2008-01-01, 2009-01-01). Claims are not
independent hospitalization episodes. Three-year claim data must be filtered
before linking to 2008 attributes for the main analysis.

Questions: How many synthetic beneficiaries have a qualifying claim? How many
claims per beneficiary, retaining zero-claim beneficiaries? How do synthetic
claim payment distributions vary across prespecified age groups?

Reference age: completed years on 2008-12-31 from source synthetic birth date.
Groups: <65, 65-74, 75-84, 85+, Unknown. Dates remain synthetic; no age-based
exclusion. Compare all beneficiaries to the Part-A-12-month domain. Per-person
metrics are descriptive counts/amounts, never complete annual incidence rates.

Grain policy: test beneficiary uniqueness, claim ID cross-beneficiary reuse,
claim and claim+segment keys, and within-claim invariance of all selected claim
level fields (dates, payment, covered days, pass-through amount). Duplicate
segment keys, claim-ID reuse, unexpected segment codes or conflicting fields
block reports and retain local conflict rows. For consistent repeated segments,
count invariant claim-level amounts once, using the lowest segment after proving
invariance. Never select max to conceal conflicts, or sum segment-level payments.

Type policy: read all source fields as strings. Dates are blank=missing or strict
YYYYMMDD; nonblank parse errors fail. Money uses Decimal converted to integer
cents, exact to two decimals (no rounding of extra precision). Negative amounts
are retained and reported. Missing amounts remain missing. Invalid categories,
coverage months outside integer 0-12, invalid date order, and missing mandatory
claim dates are quarantined/count-reconciled or blocked as specified in schema
contract. Default: block invalid date ordering and missing annual claim dates.
Missing optional admission/discharge dates are flagged without dropping claims.

Join: left join annual claims to unique beneficiaries (many-to-one), preserving
row and known-amount totals. Orphans block publication after local exception
export. Aggregate claim counts and known cents per beneficiary, then left join
onto all beneficiaries. Only true zero-claim beneficiaries get zero payment;
beneficiaries with missing claim payment have null complete total, separately
retained known-payment sum and missing-payment count.

Payment comparison: codebook Appendix 2 defines annual MEDREIMB_IP as sum of
CLM_PMT_AMT + CLM_UTLZTN_DAY_CNT * CLM_PASS_THRU_PER_DIEM_AMT. Report simple
payment and this expanded definition side by side. Differences are investigated,
not forced to zero, because synthesized variables and calendar definitions may
differ. No missing covered day count/pass-through value is imputed to zero.

Deliverables: source manifest, staged/claim/beneficiary Parquet (local), exact
DuckDB and independent SQLite reconciliation, grain/date/boundary/join audits,
full-coverage sensitivity, aggregate charts, HTML report, two-page PDF, fault
injection tests, one-command run, clean-directory rerun, pinned dependencies,
CI, verified resume bullets, source/licensing and limitations documentation.

## Reviewed preflight addendum

The initial conflict gate exposed real inconsistent multi-segment claims. The
resolution is whole-claim quarantine plus explicit affected-beneficiary flags,
as documented in segment_policy.md. Reports may proceed only with these
exceptions counted and those people excluded from complete-analysis summaries.
This does not select or impute a preferred payment value.
