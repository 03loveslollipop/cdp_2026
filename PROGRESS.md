# Model Training Progress and Handoff

## 2026-09-13 Adaptive Search Update

Branch: `feat/adaptive-training-search` (to be proposed against `master`).
The historical checkpoint below describes the state before this branch; its statement
that adaptive optimization is missing is superseded by this section.

Optuna TPE is implemented as an opt-in alternative to the unchanged grid baseline.
`--search-method tpe`, `--n-trials`, `--timeout-seconds`, and `--study-storage` expose
per-learned-family limits and resumable SQLite studies. The default config retains
`grid` for checkpoint reproducibility and defines nine family-specific TPE spaces.
The objective remains mean default-class F1 on training-period temporal folds. Seed
checks, final refit, CPU inference benchmarks, and reporting are timed separately.
Search reports record trial states, fold scores, fit durations, resolved parameters,
optimizer seed, actual devices, and elapsed search time. A training-only protocol
fingerprint prevents incompatible study reuse; an exclusive local lock prevents two
processes using the same SQLite study storage concurrently. Trial and time caps are
totals across resumes; an in-flight trial can exceed the time cap. Fresh seeded studies
are reproducible, but resumed TPE sampler sequences need not match an uninterrupted run.

Validation of the tracked branch uses only CPU tests and dependencies:

```bash
python -m pytest -q tests
python -m compileall -q etl_scripts/src tests
ruff check etl_scripts/src tests --exclude '*.ipynb'
python -m etl_scripts.src.model_training_evaluation --search-method tpe --device cpu --smoke --output-dir runs/adaptive_cpu_only_smoke
```

The CPU suite passed 57 tests with no skips. Syntax, Ruff, and the all-family CPU
TPE CLI smoke run passed. The tracked trainer rejects non-CPU devices. The CPU
environment used Python 3.13.9, PyTorch 2.11.0+cpu,
`xgboost-cpu` 3.4.1, sklearn 1.9.0, pandas 3.0.5, NumPy 2.5.3, and Optuna 4.9.0.
Optuna emits experimental heartbeat warnings; its version is pinned for training.

CUDA experimentation remains **local and untracked** in `.local_cuda_training/`; its
test code, model binaries, studies, and record-level output are not pushed. On an
NVIDIA RTX 3050 Laptop GPU (4 GiB, driver 595.84), local tests fitted MLP and
XGBoost on CUDA and loaded their pipelines in a separate CPU-only interpreter.
Probabilities and the locally selected artifact's labels matched at `atol=1e-6,
rtol=1e-5`. The local CUDA-trained winner also loads and predicts with the tracked
CPU-only code. A local non-smoke integration run sampled real hyperparameters for all
nine learned families, with one successful trial each and no failures. It selected
random forest on temporal validation (mean default F1 0.1948); its diagnostic
holdout F1 was 0.1114, below the prior grid checkpoint's 0.1394. This one-trial
local run is **not** a final adaptive benchmark, evidence for changing the deployed
model, or fresh external validation. Feature snapshot timing, outcome maturity,
and genuinely new temporal data remain necessary before promotion.

## Checkpoint and Latest Request

Branch: `feat/model_training_evaluation`. Remote: `cdp_2026`
(`git@github.com:03loveslollipop/cdp_2026.git`).

The user requested this checkpoint be pushed so another agent can continue with
hyperparameter optimization. Assume CUDA is available for development/training,
but the deployment environment has **no GPU**. The amount of compute spent on
hyperparameter optimization must be a parameter. Bayesian or genetic optimization
is acceptable; Bayesian TPE is the recommended first implementation.

**Adaptive optimization is not implemented yet.** The existing pipeline already does
a bounded grid search; the next task is to replace/extend that search, not add tuning
from scratch. Do not promise that a broader search will improve generalization.

Tracking issue: [#4](https://github.com/03loveslollipop/cdp_2026/issues/4).
No model-training PR has been opened at this checkpoint. The branch includes the
still-open heuristic [PR #3](https://github.com/03loveslollipop/cdp_2026/pull/3).
Preparation PR #2 merged into `master`. When publishing a training PR, target `master`
and identify the heuristic dependency if it remains open. Do not merge those PRs as
part of the handoff. The user most recently asked for a branch push and handoff files.

## Implemented

- `etl_scripts/src/model_training_evaluation.py`: `build_model`,
  `summarize_classification`, `train_and_evaluate`, CLI, model selection, artifact export,
  aggregate report publication, and comparative graphs.
- `etl_scripts/src/torch_classifier.py`: sklearn-compatible PyTorch MLP with seeded
  minibatch training, dropout, AdamW, optional class weighting, and CPU-array weights.
- Nine learned families: MLP, XGBoost, LightGBM, RBF SVM, classification tree, Gaussian
  Bayes, logistic regression, random forest, and Extra Trees. Heuristic/dummy references
  keep their original prediction rules and cannot win selection.
- Configurable grids of at most eight candidates per family, followed by evaluation
  of family finalists with seeds 42, 43, and 44.
- A fitted `TrainingResult.best_model` accepting raw predictor records. It includes
  preparation, model, calibration, threshold, and original label/probability ordering.
- Summary tables, PR/ROC curves, temporal F1, inference-cost comparison, and confusion
  matrices. See [workflow](docs/model_training.md) and
  [completed CPU benchmark](docs/model_benchmark/README.md).

The output directory is protected against overwriting existing artifacts; normal
exceptions mark `status.json` as failed. Models and run-level data stay in ignored
`runs/`. All pipeline objects have importable module paths for cross-process loading.

## Preserve the Evaluation Protocol

The raw data splits chronologically into 7,534 training and 3,229 holdout records.
Within training, five timestamp-preserving blocks yield three expanding validation
folds. For each outer training window, the earliest 80% fits the entire base pipeline;
the latest 20% fits sigmoid calibration and selects the default-F1 threshold. Only
then is the later outer validation block evaluated.

Family finalists are compared using mean F1 across temporal folds and seeds. Within
0.01 absolute F1 of the leader, select lower temporal standard deviation, then lower
seed standard deviation, CPU batch latency, serialized size, and model name.

Final calibration/threshold use base-seed outer out-of-fold raw scores. The estimator
is refitted on all training rows. Selection is frozen before holdout evaluation.
Refitting can shift score distributions; do not use the holdout to repair this.

## Completed Results

The full CPU benchmark finished successfully; no training process remains running.
Selected model: **random forest**, 150 trees, maximum depth 6, minimum leaf size 10,
no class weighting. Default probability threshold: `0.14287507114631004`.

| Metric | Selected random forest | Existing heuristic |
| --- | ---: | ---: |
| Mean temporal default F1 | 0.217538 | 0.171103 |
| Holdout accuracy | 0.900588 | 0.792815 |
| Holdout default precision | 0.098113 | 0.046850 |
| Holdout default recall | 0.240741 | 0.268519 |
| Holdout default F1 | 0.139410 | 0.079780 |
| Holdout average precision | 0.119985 | 0.085801 |
| Holdout ROC-AUC | 0.673369 | 0.624149 |

Forest confusion matrix, actual rows/predicted columns `[default, on-time]`:
`[[26, 82], [239, 2882]]`. Temporal F1 standard deviation: `0.029919`;
seed standard deviation: `0.017595`.

Logistic regression happened to have slightly higher holdout F1 (`0.141058`);
**it was not substituted for the validation-selected forest**. Future searches must
also avoid selecting against this already-inspected holdout. It is a diagnostic
benchmark, not fresh external validation. Obtain new temporal data for a final
unbiased assessment. Feature availability at decision time and outcome maturity
remain assumptions of the source extract.

## Validation and Local Artifacts

Commands run from this repository root:

```bash
python -m pytest -q tests
python -m py_compile etl_scripts/src/model_training_evaluation.py etl_scripts/src/torch_classifier.py
python -m etl_scripts.src.model_training_evaluation --smoke --output-dir runs/training_smoke
python -m etl_scripts.src.model_training_evaluation --output-dir runs/training_full_cpu
git diff --check
```

Results: **50 tests passed, one CUDA-only test skipped**. Warnings were joblib/NumPy
deprecations. Tests cover chronology, training-only fitting, holdout invariance,
class/probability mapping, booster weighting, portability, output protection, and
aggregate-only publication. The EDA notebook also executed successfully from a clean
kernel, after installing its missing Seaborn dependency; output is in
`/tmp/credit_eda_training_validation.ipynb`, not the tracked notebook.

Original local run artifacts: `runs/training_full_cpu/`. The selected object is
`best_model.joblib`; configurations/versions/splits are in `manifest.json`.
**These ignored artifacts will not be present in a fresh clone.** The committed
benchmark contains aggregate results and figures. Recreate binaries by running the CLI.

This runtime had PyTorch `2.13.0+cpu`, sklearn `1.9.0`, XGBoost `3.4.1`, LightGBM
`4.7.0`, and Python `3.12.14`. SSH to `zerotwo@192.168.1.137:22` returned
`No route to host`; no GPU run occurred. Explicit CUDA mode failed early as intended.
Use the next environment's available CUDA device; do not assume the old host is required.

## Next Implementation: Configurable Adaptive Search

1. Add a search backend interface around the existing candidate evaluation loop.
   Keep the grid backend as the reproducible checkpoint comparator. Start with
   [Optuna TPESampler](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html)
   for Bayesian optimization; a genetic backend may be substituted or added later.
   Do not change the F1 objective into a multi-objective search implicitly.
2. Expose the method and budgets in configuration and CLI. Proposed defaults for the
   next implementation (not supported today): `search_method="bayesian"`,
   `n_trials=30`, `timeout_seconds=1800`, applied **per learned model family**.
   Both limits are configurable; stop launching trials when either is reached.
   A timeout checked between trials is not a hard wall-clock limit—document that
   an in-flight trial can finish. Seed checks, final refit, and reporting are outside
   the search budget and must have their time reported separately.
3. Record attempted/completed/pruned/failed trials, actual elapsed search time,
   optimizer seed, parameters, fold metrics, and actual devices. Use seeded, serial
   trials on a single GPU initially. Explicitly bound CPU threads. Keep heuristic
   and dummy out of optimization.
4. Define model-specific continuous/log/integer/categorical spaces in configuration.
   Tune regularization, tree complexity/learning rates, SVM C/gamma, and MLP widths,
   depth, learning rate, dropout, batch size, epochs, and weight decay. Class weighting
   stays a trial parameter with weights computed only from the fitting partition.
5. Optimize training-period temporal F1 only. Reuse `build_model`,
   `summarize_classification`, and the leakage-safe fitting/calibration boundaries.
   Preserve finalist seed checks and the agreed selection rule. A pruning or
   early-stopping implementation must never inspect outer validation or holdout
   labels to train the estimator; any validation used for training must be inside
   the fold's training window.
6. Persist resumable studies under ignored `runs/` (for example, Optuna
   [RDB storage](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.storages.RDBStorage.html)).
   Guard resume with fingerprints of dataset, preparation/search-space configuration,
   folds, label convention, and objective. Define resumed trial budgets as a total
   study cap, not another full allocation on every invocation. Log trial failures
   without disguising a failed family as a completed comparison.

These defaults are handoff recommendations, not additional confirmed user preferences.
The required user constraints are configurable compute effort, adaptive Bayesian or
genetic search, CUDA development, and CPU-only deployment.

## CUDA-to-CPU Acceptance Criteria

- Separate training-device configuration from CPU deployment/inference. Existing
  PyTorch weights are CPU arrays and XGBoost switches its fitted predictor to CPU;
  preserve that behavior. LightGBM remains CPU unless a GPU-capable build is verified.
- Train at least the MLP and XGBoost on CUDA. Load the exported winner in a separate
  CPU-only environment and compare predictions/probabilities within a documented
  numerical tolerance (start with `atol=1e-6`, `rtol=1e-5`). Test both original labels
  and preprocessing. Do not equate hiding a GPU with testing CPU-only dependencies.
- Add tests for trial/time caps, reproducible sampling, resume accounting, failure/
  pruning bookkeeping, holdout independence, and CUDA-trained artifact loading.
- Benchmark CPU inference separately from CUDA training and competing jobs. Update
  tables/graphs with search cost, consistency, and CPU deployment cost. Broader tuning
  is successful when the workflow is correct and its outcome is honestly reported,
  even if performance does not exceed the current checkpoint.
- Keep binaries, study databases, row-level predictions, and environments out of Git.
  Update this handoff and the issue/PR with exact validation results.
