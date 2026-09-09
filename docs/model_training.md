# Model training and evaluation

`etl_scripts/src/model_training_evaluation.py` trains and compares nine learned
classifiers plus the existing heuristic and always-on-time reference. The output is a
fitted object that accepts raw predictor records, applies preparation, and returns
predictions or class probabilities. No target or date is required at inference.

## Run locally

From `PYTHON_ETL/`, using your project environment:

```bash
python -m pip install -r requirements.txt -r requirements-training.txt
python -m etl_scripts.src.model_training_evaluation \
  --smoke --output-dir runs/comparison_smoke
python -m etl_scripts.src.model_training_evaluation \
  --device cpu --output-dir runs/comparison_cpu
python -m pytest -q tests
```

The smoke profile uses one small candidate and one seed per family; it checks the
workflow but is not a performance benchmark. Use a new output directory for each run.
`--input`, `--config`, and `--training-config` accept alternative dataset/config paths.
The default dataset remains the repository's `dataset.csv`.

## Models and shared functions

`build_model(name, config, random_state, device, parameters=..., training_config=...)`
returns an unfitted sklearn Pipeline. Supported names are `pytorch_mlp`, `xgboost`,
`lightgbm`, `svm`, `decision_tree`, `gaussian_nb`, `logistic_regression`, `random_forest`,
`extra_trees`, `heuristic`, and `dummy`. The tree is a classification tree: the outcome
is binary, so a regression objective is not used.

All models use the shared leakage exclusions, semantic transformations, and imputation.
Categorical predictors are one-hot encoded with unknown-category handling. Numerical
features are standardized for MLP, SVM, logistic regression, and Gaussian Bayes.
Heuristic inputs retain their original prepared DataFrame representation.

The PyTorch classifier is cloneable and exposes `fit`, `predict`, and `predict_proba`.
It uses two/three ReLU hidden layers, dropout, AdamW, fixed epoch budgets, and minibatches.
Learned weights are exported as CPU arrays. Boosters translate the original target to
positive-default labels internally so class weighting emphasizes defaults correctly.

`summarize_classification(y_true, y_pred, default_probability)` returns accuracy,
default precision/recall/F1, average precision, ROC-AUC, recall at the configured review
budget, prevalence, review share, and the confusion matrix. **Label 0 is default**;
probability columns and confusion-matrix axes follow `[0, 1]`. Review-budget recall
uses the top `ceil(n * review_fraction)` scores, with chronological row order breaking
ties. This ranking metric does not change the model's classification threshold.

## Temporal validation and model selection

The raw chronological split remains 70% training (7,534 records) and 30% holdout
(3,229 records). The training portion is divided into five blocks of distinct timestamps.
Expanding folds train on blocks 1–2, 1–3, and 1–4 and validate on blocks 3, 4, and 5.
Equal timestamps stay together. Each partition must contain both classes.

Within each outer training window, the earliest 80% fits the entire pipeline; the
latest 20% fits a sigmoid probability calibrator and chooses the default-F1 threshold.
The later outer validation window evaluates these frozen predictions. SVM uses its
decision score and this explicit temporal calibration, without shuffled internal CV.
Neither validation nor holdout records can fit preprocessing or class weights.

The bounded search considers up to eight configurations per learned family. Each
family's best configuration is checked with seeds 42, 43, and 44. Models within 0.01
absolute mean F1 of the leader are ranked by temporal F1 standard deviation, seed F1
standard deviation, CPU batch latency, artifact bytes, and finally model name. Temporal
variation is measured across fold means; seed variation is measured across seed means.
These spreads are descriptive, not confidence intervals. References cannot win selection.

For each family finalist, base-seed out-of-fold raw scores fit the final sigmoid and F1
threshold. The base estimator is then refitted on all training records. Refitting can
shift score distributions; the holdout measures the resulting complete prediction object.
Selection is written to disk before any holdout evaluation and is never revised based on
holdout scores. The heuristic keeps its original 20% training-quantile review policy.

Search spaces, seeds, thresholds, model devices, thread counts, and benchmarking budgets
live in `etl_scripts/src/model_training_config.json`. No SMOTE, row deletion, or additional
outlier repair is introduced. Candidate failures abort the run instead of quietly
excluding a requested model.

## Consume the selected object

```python
import joblib
from etl_scripts.src.ft_engineering import read_raw_data
from etl_scripts.src.model_training_evaluation import train_and_evaluate

result = train_and_evaluate(read_raw_data(), output_dir="runs/my_comparison")
best_model = result.best_model
raw_records = read_raw_data().drop(columns=["Pago_atiempo"])
predictions = best_model.predict(raw_records)
default_probability = best_model.predict_proba(raw_records)[:, 0]

restored = joblib.load(result.artifact_paths["model"])
```

The artifact includes fitted preparation, encoding/scaling, model, calibration, threshold,
and class order. Keep the project importable and use the dependency versions recorded
in its manifest. Only load artifacts from trusted sources. Inference runs on CPU,
including artifacts trained by PyTorch or XGBoost on CUDA.

## Reports and reproducibility

Each run writes `best_model.joblib`, `selection.json`, a Markdown report, validation and
holdout CSV tables, per-fold/search results, out-of-fold and holdout predictions, and
JSON metrics. Figures compare holdout PR/ROC curves, temporal F1, F1 versus CPU latency,
and holdout confusion matrices. The manifest records data/configuration fingerprints,
split boundaries, package versions, seeds, platform, and requested/actual training devices.

CPU latency includes preparation, calibration, and prediction on the same first 256
training records, after warmup, using the median of five repeats. Two threads are the
default; PyTorch uses one. Artifact size is uncompressed serialized bytes. These are
local scalability proxies, not production throughput guarantees or a load test.

Run artifacts live in ignored `runs/`; selected reports and figures may be published
under `docs/`. Binaries and record-level predictions must not be committed.

To regenerate the committed aggregate [benchmark report](model_benchmark/README.md)
and its figures from a completed run:

```bash
python -c 'from etl_scripts.src.model_training_evaluation import publish_comparison; publish_comparison("runs/training_full_cpu", "docs/model_benchmark")'
```

The publisher reads saved predictions to draw the graphs but exports only aggregate
tables, figures, and reproducibility metadata. A failed run has `status.json` marked
`failed` and cannot be published as complete.

## GPU validation

The requested host is `zerotwo@192.168.1.137:22`; it is currently unreachable from this
workspace (`No route to host`). GPU validation remains pending. Once reachable, use an
isolated checkout/environment on that host, inspect `nvidia-smi`, and install a PyTorch
CUDA wheel compatible with its driver using the
[official installer](https://pytorch.org/get-started/locally/). Run:

```bash
python -m pytest -q tests/test_model_training_evaluation.py
python -m etl_scripts.src.model_training_evaluation \
  --device cuda --smoke --output-dir runs/comparison_cuda_smoke
python -m etl_scripts.src.model_training_evaluation \
  --device cuda --output-dir runs/comparison_cuda
```

CUDA is used for PyTorch and XGBoost; LightGBM stays on CPU unless its separate
`lightgbm_device` configuration is changed for a supported build. Explicit CUDA requests
must not silently fall back to CPU. Record GPU/driver details with the PR validation.
Seeded runs are reproducible within a supported runtime, but bitwise CPU/GPU agreement
is not promised.

## Interpretation limits

F1 is the chosen selection objective; it is not an estimated lending profit or cost.
Hyperparameter selection makes validation estimates optimistic. The holdout was already
examined during EDA and heuristic assessment, so it is not an untouched external test.
Feature availability at decision time and outcome maturity cannot be verified from the
extract's timestamps. Confirm those assumptions and obtain fresh temporal validation
before using this model for lending decisions.
