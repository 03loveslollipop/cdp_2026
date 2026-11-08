# Measured Python baseline and pending cloud comparison

Measured on the tracked non-production extract with `ci/training.json`. There are 10,763 records; the first 7,534 form the training period and the final 3,229 form the chronological holdout. Default is `Pago_atiempo=0`.

Selection uses temporal validation before the holdout is evaluated. References (heuristic and dummy) are not selection candidates. The selected model is **random forest**. These results were reproduced by the Jenkins CPU environment and a local execution of the custom training container. Neither execution is a Vertex AI training result.

| Python model | Holdout accuracy | Default F1 | Default recall | ROC-AUC | PR-AUC |
|---|---:|---:|---:|---:|---:|
| Logistic regression | 0.9080 | 0.1134 | 0.1759 | 0.6278 | 0.0652 |
| Decision tree | 0.9297 | 0.1498 | 0.1852 | 0.6084 | 0.0591 |
| Random forest (selected before holdout) | 0.8250 | 0.1130 | 0.3333 | 0.6573 | 0.0994 |
| Heuristic reference | 0.7928 | 0.0798 | 0.2685 | 0.6241 | 0.0858 |
| Majority-class dummy | 0.9666 | 0.0000 | 0.0000 | 0.5000 | 0.0334 |
| Vertex AI custom pipeline | Pending dashboard run | — | — | — | — |
| Vertex AI AutoML Tabular | Pending dashboard run | — | — | — | — |

PR-AUC in these tables uses scikit-learn's average precision (AP); keep native AutoML `auPrc` separately labeled. The decision tree's better holdout F1 is an audit finding; it does not change the training-selected winner. Tuning or reselecting on this table would compromise the frozen comparison.

## Stability and uncertainty

The selected forest's mean temporal validation default F1 is **0.1871**, with temporal standard deviation **0.0292** and across-seed standard deviation **0.0110** for seeds 42, 43, 44. These measures passed the exercise's versioned limits. The limited candidate budget and three seeds are a small lab check; they do not establish production suitability.

On the holdout, the forest's confusion matrix in actual/predicted order `[default, on-time]` is `[[36,72],[493,2628]]`: 36 of 108 defaults detected, with 493 false positives. Its fixed temporal-OOF-derived default threshold is approximately **0.08828**. The stratified bootstrap 95% intervals (200 resamples, fixed seed) are accuracy **[0.8132, 0.8365]**, default F1 **[0.0845, 0.1413]** and ROC-AUC **[0.6073, 0.7108]**. These intervals are conditional on the observed class mix and describe holdout sampling uncertainty, not variability from retraining.

Defaults fall from 403/7,534 (5.35%) in the training period to 108/3,229 (3.34%) in the holdout. This prevalence shift and the validation-to-holdout F1 decline motivate further temporal evaluation and calibration review. The dummy's 96.66% accuracy with no detected defaults shows why accuracy alone is misleading for this extract.

![Measured frozen-holdout result and bootstrap intervals](../output/comparison/comparison.png)

Additional measured figures: [ROC curves](../output/local-baseline/figures/holdout_roc.png), [PR curves](../output/local-baseline/figures/holdout_pr.png), [temporal F1](../output/local-baseline/figures/temporal_f1.png), [confusion matrices](../output/local-baseline/figures/holdout_confusion_matrices.png). These local generated artifacts are excluded from Git; include the `output/` evidence when sharing the lab submission.

## How cloud results will be added

Follow the [dashboard training runbook](gcp-training.md) after user approval/login. Both cloud methods must use the same dataset and final holdout fingerprints. AutoML receives leakage-safe engineered data and fixed TRAIN/VALIDATION/TEST labels. Custom Vertex training uses the repository's existing temporal selection and calibration code.

Download real predictions/artifacts and run `python -m cloud.compare`. No missing cloud score is replaced with a local score. Compare ranking metrics alongside F1 because the Python/custom calibrated threshold and the AutoML fixed 0.5 default threshold represent different operating policies. Repeated AutoML training at a fixed split and budget is needed to measure its retraining consistency; one run's bootstrap intervals cannot supply that evidence.

Manual training provides explicit control over temporal folds, feature processing, calibration, thresholds, seeds and runtime costs. AutoML reduces manual search work and provides managed evaluation, while spending a cloud budget and exposing less of its internal search. Superiority and stability conclusions about AutoML remain pending. The holdout was already examined during earlier EDA, and a fresh external dataset would be needed for an independent generalization claim. Predictor availability at the original credit-decision time remains an assumption in the source data contract.

Reproduce the measured baseline and comparison:

```bash
python -m mlops_pipeline.src.model_training_evaluation \
  --training-config ci/training.json --output-dir output/another-baseline
python -m cloud.compare local --run output/another-baseline --output output/python-local.json
python -m cloud.compare report --inputs output/python-local.json --output output/comparison
```

The training command requires a new/empty run directory. Dataset fingerprint: `48e34610b823055a5f4e7a107142e25b08ba40920848eab1a68ff6396eb26927`; holdout fingerprint: `f0f8ec775541328cfcaf07fa5a8455a089b2f3832549c583de35804f5216329a`.
