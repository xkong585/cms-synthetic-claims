# Reviewed segment-resolution policy

CMS codebook IP-3 (printed p45, PDF p49) permits up to two segments per claim,
with suppressed segment information and reduced analytic utility. The source
files do not justify summing payment across every row.

Observed in official frozen Sample 1: 66,773 rows, 66,705 claim keys, 68 two-row
claims. Nonmissing values conflict in 67 claim keys: admission date (61 claims),
payment amount (58), pass-through per diem (33); these sets overlap. All 68
segment-2 rows lack billing from/thru dates and covered-day count. There is no
cross-beneficiary reuse of claim ID or duplicate claim+segment key.

Resolution after preflight investigation (addendum to initial scope):

1. Compare every selected claim-level field within each claim, ignoring blank
   segment entries when counting distinct nonmissing values.
2. Quarantine the ENTIRE claim if any field has >1 distinct nonmissing value.
   Do not choose max, favor segment 1, or sum conflicting payments.
3. For proven-consistent claims, carry the single nonmissing value to claim
   grain. One repeated claim is consistent and safely counts once.
4. Quarantine missing/invalid claim-grain billing date/order separately. Invalid
   nonblank date formats are fatal at staging, not silently coerced.
5. A quarantined claim's unique nonmissing thru date is used ONLY to flag annual
   impact. Conflicting/missing thru dates would flag that beneficiary for the
   year as uncertain. In the frozen input all quarantined thru dates are unique.
6. Keep every beneficiary in the annual ledger. Mark a beneficiary affected by
   a potentially eligible quarantine; set complete annual count/amount to NULL
   and exclude that person from the main complete-analysis domain. Never label
   such a person zero-claim. Keep accepted counts, known sums and missing counts
   as separate ledger columns for exact reconciliation.

The conflict quarantine comprises 21 claims ending in 2008, 32 ending in 2009,
and 14 ending in 2010. Published reports show aggregated exceptions, not record
screenshots. Local `claim_conflicts.csv` and quarantine Parquet contain only
synthetic records and are excluded from Git. Fault-injection examples are tests,
not additional issues discovered in the official dataset.
