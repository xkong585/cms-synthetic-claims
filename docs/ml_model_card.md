# ML model card

Added a 2008-feature / 2009-claim benchmark for 73,757 synthetic beneficiaries with complete follow-up. Held-out test average precision: prevalence baseline 0.1749, logistic 0.2660, gradient boosting 0.2711; gradient boosting ROC-AUC 0.6155 and Brier 0.1388 versus baseline 0.1443. Calibration did not improve Brier on this test. Keep the raw and calibrated results visible; do not claim clinical or real-world validity.

CMS DE-SynPUF Sample 1, synthetic data only. 73,757 eligible beneficiaries. Baseline features end 2008-12-31; target is at least one accepted claim ending in 2009. Full 2009 Part A, no HMO and survival through 2009 are required to interpret absence as zero.

Fixed seed, stratified beneficiary split: 60% training, 20% probability calibration, 20% locked test. Fixed hyperparameters; median imputation and scaling fitted on training only. Platt calibration uses calibration people only. No test-driven model selection. This is a held-out-person evaluation with forward-looking labels, not validation in a later calendar cohort.

## Predictors

age, sex, part_a_2008, hmo_2008, claims_2008, payment_2008, days_2008, days_since_last_2008

## Intended use and limits

Synthetic relationships do not demonstrate performance on real patients or clinical usefulness. Eligibility depends on later enrollment and survival, so results apply to that retrospective complete-follow-up population. Labels include carry-in stays ending in 2009, not incident admissions or readmissions. Aggregate held-out errors have no external validation or confidence intervals; subgroup scores do not establish fairness.

Permutation importance measures the score decrease after independently permuting a feature. Correlated predictors can share information; the measure is not causal. It is not used for selecting features or hyperparameters. No model was selected by the held-out test score. Settings are deliberately fixed in docs/ml_plan.md, rather than tuned on evaluation folds. The scorecard is a benchmark, not a deployed medical tool.

## Reproducibility and privacy

Pinned packages, deterministic seeds, official source hashes, full pipeline tests, and empty-cache rerun evidence are included. No individual rows or serialized estimator are committed. The original descriptive/association analysis retains its separate assumptions and results.
