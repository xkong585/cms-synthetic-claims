# Payment definitions and exact accounting

Amounts are synthetic record values in USD, not real treatment cost or savings.
Integer cents are parsed from Decimal without rounding; negatives and zero are
separately reported. Blank payment is missing, not zero. Sums of known amounts
are explicitly partial if any component is missing; a complete beneficiary total
is NULL whenever an accepted claim payment is missing or an annual quarantine
could affect it. True no-claim beneficiaries alone receive derived zero totals.

`CLM_PMT_AMT` excludes pass-through amounts. Codebook Appendix 2 (printed p121,
PDF p125) defines MEDREIMB_IP using:

    SUM(CLM_PMT_AMT + CLM_UTLZTN_DAY_CNT * CLM_PASS_THRU_PER_DIEM_AMT)

The project uses a fixed CLM_THRU_DT 2008 rule, not calendar payment processing
or admission year. Covered days need not equal calendar stay length. The expanded
formula is compared to source MEDREIMB_IP on nonambiguous paired beneficiaries,
with exact cents, but equality is not assumed. Synthesis and year/boundary rules
can leave differences. No variable is altered to make these figures agree.

The independent DuckDB query reconstructs consistent claims from staging and
counts invariant claim payments once. A second SQLite query checks annual count,
known cents and distinct claimants. All ledger count and known-cent totals must
balance exactly; a failed identity blocks publication.

Sources:
- CMS DE-SynPUF codebook: https://www.cms.gov/files/document/cms08-10desynpufcodebookpdf
- CMS data-use context: https://www.cms.gov/research-statistics-data-and-systems/downloadable-public-use-files/synpufs/downloads/synpuf_dug.pdf
