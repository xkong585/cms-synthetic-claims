# 90-second explanation

I built an auditable Python and SQL workflow for CMS DE-SynPUF Sample 1. The
problem is reliable claim and beneficiary grain, not clinical prediction. I read
IDs as strings, parsed money to exact cents, defined 2008 using claim-through
date, and validated many-to-one joins before aggregating to every beneficiary.

The source has 66,773 rows but 66,705 claim keys. Most of the 68 repeated claims
have conflicting fields. I quarantined 67 entire claims rather than summing
segments or picking the largest payment. Twenty-one 2008 beneficiaries are
flagged and excluded from complete summaries, but their ledger rows remain and
are never reported as zero-claim. The complete domain retains 116,331 people,
including 100,607 true zero-claim people.

DuckDB independently reconstructs consistent claims from staging. SQLite checks
annual counts and cents. Sixteen identities reconcile, and twenty-five tests
exercise corrupt keys, conflicts, invalid dates, missing amounts and fail-closed
reporting. The official pass-through formula exactly reproduces annual source
reimbursement for all paired nonambiguous people; payment-only totals do not.

These are synthetic-data demonstrations. They do not show real Medicare costs,
clinical outcomes or hospital quality. I can explain every denominator and show
the source lock, exception policy, complete-case exclusions and clean-run evidence.
