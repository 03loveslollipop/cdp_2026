# Measured credit-classification results and cloud comparison

Measured on the tracked non-production extract with `ci/training.json`. There are 10,763 records; the first 7,534 form the training period and the final 3,229 form the chronological holdout. Default is `Pago_atiempo=0`.

Selection uses temporal validation before the holdout is evaluated. References (heuristic and dummy) are not selection candidates. The selected model is **random forest**. These results were reproduced by the Jenkins CPU environment and a local execution of the custom training container. Those initial checks were followed by a real Vertex AI custom pipeline, `credit-cpu-demo-20261108-r3`, which succeeded on 2026-11-08 and reproduced the same metrics and data fingerprints; see [GCP execution evidence](gcp-execution.md).

| Python model | Holdout accuracy | Default F1 | Default recall | ROC-AUC | PR-AUC |
|---|---:|---:|---:|---:|---:|
| Logistic regression | 0.9080 | 0.1134 | 0.1759 | 0.6278 | 0.0652 |
| Decision tree | 0.9297 | 0.1498 | 0.1852 | 0.6084 | 0.0591 |
| Random forest (selected before holdout) | 0.8250 | 0.1130 | 0.3333 | 0.6573 | 0.0994 |
| Heuristic reference | 0.7928 | 0.0798 | 0.2685 | 0.6241 | 0.0858 |
| Majority-class dummy | 0.9666 | 0.0000 | 0.0000 | 0.5000 | 0.0334 |
| Vertex AI custom pipeline (same selected forest) | 0.8250 | 0.1130 | 0.3333 | 0.6573 | 0.0994 |
| Vertex AI AutoML Tabular (fixed 0.5) | 0.9625 | 0.1037 | 0.0648 | 0.6542 | N/A: native PR-AUC 0.1201 |

PR-AUC in these tables uses scikit-learn's average precision (AP); keep native AutoML `auPrc` separately labeled. The decision tree's better holdout F1 is an audit finding; it does not change the training-selected winner. Tuning or reselecting on this table would compromise the frozen comparison.

## Stability and uncertainty

The selected forest's mean temporal validation default F1 is **0.1871**, with temporal standard deviation **0.0292** and across-seed standard deviation **0.0110** for seeds 42, 43, 44. These measures passed the exercise's versioned limits. The limited candidate budget and three seeds are a small lab check; they do not establish production suitability.

On the holdout, the forest's confusion matrix in actual/predicted order `[default, on-time]` is `[[36,72],[493,2628]]`: 36 of 108 defaults detected, with 493 false positives. Its fixed temporal-OOF-derived default threshold is approximately **0.08828**. The stratified bootstrap 95% intervals (200 resamples, fixed seed) are accuracy **[0.8132, 0.8365]**, default F1 **[0.0845, 0.1413]** and ROC-AUC **[0.6073, 0.7108]**. These intervals are conditional on the observed class mix and describe holdout sampling uncertainty, not variability from retraining.

Defaults fall from 403/7,534 (5.35%) in the training period to 108/3,229 (3.34%) in the holdout. This prevalence shift and the validation-to-holdout F1 decline motivate further temporal evaluation and calibration review. The dummy's 96.66% accuracy with no detected defaults shows why accuracy alone is misleading for this extract.

![Measured frozen-holdout result and bootstrap intervals](../output/comparison/comparison.png)

Additional measured figures: [ROC curves](../output/local-baseline/figures/holdout_roc.png), [PR curves](../output/local-baseline/figures/holdout_pr.png), [temporal F1](../output/local-baseline/figures/temporal_f1.png), [confusion matrices](../output/local-baseline/figures/holdout_confusion_matrices.png). These local generated artifacts are excluded from Git; include the `output/` evidence when sharing the lab submission.

## Completed comparison with native AutoML

AutoML pipeline `7023547864391352320` completed **SUCCEEDED** at 2026-11-08T19:55:04.833658Z (9 November 04:55:04 JST). Model `3834067964554903552`, version 1, evaluation `2989617876806692894` uses the original dataset, manual `data_split`, 84 checked predictors and a 1000 milli-node-hour budget. Its 2h35m wall duration includes managed processing and does not multiply the configured node-hour budget.

| Holdout measure | Python local | Vertex custom | AutoML native |
|---|---:|---:|---:|
| Accuracy | 0.825023 | 0.825023 | 0.962527 |
| Default precision | 0.068053 | 0.068053 | 0.259259 |
| Default recall | 0.333333 | 0.333333 | 0.064815 |
| Default F1 | 0.113030 | 0.113030 | 0.103704 |
| Default ROC-AUC | 0.657321 | 0.657321 | 0.654208 |
| sklearn average precision | 0.099415 | 0.099415 | Not available |
| Native default PR-AUC | Not available | Not available | 0.120123 |
| Default probability threshold | 0.088279, temporal OOF | 0.088279, temporal OOF | 0.5, fixed |

AutoML's default-first confusion matrix is `[[7,101],[20,3101]]`: 7 of 108 defaults detected with 20 false alarms. Python/custom detect 36 with 493 false alarms. F1 and recall compare different operating policies as well as fitted models; neither threshold was tuned on TEST. AutoML accuracy is below the majority dummy's 0.966553, which detects no defaults. ROC-AUC is similar across methods; these results do not establish a material ranking advantage. Native PR-AUC and sklearn AP have different integration/aggregation definitions and must not be ranked as the same metric. Overall native **micro ROC-AUC 0.976393 and micro PR-AUC 0.971952** are retained separately, never substituted for default-class ranking scores.

![Final measured Python, Vertex custom and AutoML comparison](../output/comparison-final/comparacion-final-python-vertex-automl.png)

The native evaluation's 3,229 observations and 108 defaults match the TEST manifest. The provenance chain links uploaded export manifest → dataset GCS URI → manual split → successful pipeline → model/version → default evaluation slice. AutoML's source/holdout hashes are inherited from that verified upload manifest; the native aggregate API does not independently provide row hashes. See `cloud/native_evaluation.py`, its rejection tests and `output/vertex-automl-native.json`.

Python/custom temporal F1 std is 0.029162 and seed F1 std is 0.011031 (three seeds). Their identical results demonstrate environment consistency for this protocol, not independent cloud retraining variance. AutoML has one run; temporal/seed stability is **unmeasured**, not zero. No raw AutoML predictions were purchased, so no AutoML bootstrap or chronological TEST-block analysis is claimed. Additional paid runs are unnecessary for the current academic demonstration and were not launched.

Manual training provides explicit control over temporal folds, feature processing, calibration, thresholds, seeds and runtime costs. AutoML reduces model-search work and supplies managed evaluation, with less control over its internal search and a higher training budget for this small exercise. This observed run provides no general superiority claim. The holdout was already examined during EDA; a fresh external dataset is needed for independent validation. Predictor availability at the original decision time remains an assumption. RMSE is not used for this classification task.

Reproduce the measured baseline and comparison:

```bash
python -m mlops_pipeline.src.model_training_evaluation \
  --training-config ci/training.json --output-dir output/another-baseline
python -m cloud.compare local --run output/another-baseline --output output/python-local.json
python -m cloud.compare report --inputs output/python-local.json --output output/comparison
```

The training command requires a new/empty run directory. Dataset fingerprint: `48e34610b823055a5f4e7a107142e25b08ba40920848eab1a68ff6396eb26927`; holdout fingerprint: `f0f8ec775541328cfcaf07fa5a8455a089b2f3832549c583de35804f5216329a`.
