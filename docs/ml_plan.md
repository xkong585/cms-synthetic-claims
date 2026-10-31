# ML protocol

Frozen before first model execution. CMS: 2008 predictors only; 2009 through-date claims label. Complete Part A (12 months), no HMO, surviving 2009, no ambiguous baseline/target claims. Fixed stratified 60/20/20 beneficiary split, seed20261031/20261032. Logistic C=.1 and HGB100 iterations/7 leaves/min leaf100/L2=10; no early stopping. Fixed settings, no hyperparameter search. Platt logistic C=1e6 calibration on calibration split only. Locked test: ROC-AUC, AP, Brier, log loss, probability calibration and subgroup diagnostics. No threshold optimization.

Participant-level inputs and predictions remain ignored under data/processed. Published metrics are aggregates only. Results are exploratory portfolio benchmarks; they do not replace the original analysis.
