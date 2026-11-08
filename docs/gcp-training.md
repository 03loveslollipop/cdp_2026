# GCP credit classification training — dashboard runbook

Status: **custom Vertex pipeline SUCCEEDED on 2026-11-08; user authorized one classic AutoML run at approximately USD21.25 on 2026-11-09 JST**. Console language remains Japanese. See `gcp-execution.md` for observed evidence and the revised one-node-hour AutoML authorization; this runbook also describes steps that have not been executed. Launch AutoML and custom Vertex AI Pipeline runs from the web dashboard. Python helpers compile packages and analyze downloaded results; they never submit training jobs.

## 1. Verify account and project in the persistent browser

Use the Playwright skill wrapper with the named session `semester-gcp`, opened headed. Keep the session open between steps so the user can sign in interactively. Do not save browser cookies or credentials into Git.

```bash
/home/zerotwo/.codex/skills/playwright/scripts/playwright_cli.sh --session semester-gcp open https://console.cloud.google.com/ --headed
```

After user login, capture the account menu (without secrets), organization/project selector and project dashboard. Confirm organization `02labs.me` (`408308144073`) and training project `nb-risk-ml-dev-99d0` (`novabank-riesgo-ml-dev`). `novabank-riesgoanalitica` describes the organizational area, not a project ID. Do not select the test/prod siblings or the core IT Jenkins project for training.

In the dashboard, check billing and Vertex AI availability; enable Vertex AI if needed, and choose `us-central1` consistently for datasets, training, storage, artifacts and pipeline runs. Enable supporting services only as needed. Record the signed-in browser identity and actual chosen region in the workspace-root `CLOUD_DEPLOYMENT_INVENTORY.md`. The existing training project satisfies the exercise's project prerequisite; do not create a duplicate.

## 2. Prepare and import the fixed dataset

Local preparation already ran on the tracked approved non-production extract:

```bash
python -m cloud.prepare_data --output output/cloud-data-gcp
```

This refuses to overwrite an existing export. `manifest.json` records source, normalized-dataset and holdout SHA-256 fingerprints, exact time boundaries, feature columns and class counts. No labels, timestamps, `puntaje` (post-outcome score), or row IDs are predictive features.

| Partition | Rows | Defaults (label 0) | Role |
|---|---:|---:|---|
| TRAIN | 6,027 | 331 | Earliest 56%; fits AutoML export preprocessing |
| VALIDATE | 1,507 | 72 | Next 14%; AutoML tuning |
| TEST | 3,229 | 108 | Final 30%; frozen audit |

Timestamp groups stay together. The shared preparation transformer learns imputation only from TRAIN before exporting AutoML features. Python/custom use the existing raw-record pipeline and temporal folds in the first 70%, so this comparison includes differences in tuning/preprocessing workflows as well as model search. The final test rows are identical. The historical holdout was examined in EDA; it is not a fresh external validation set.

Through **Cloud Storage → Buckets → Create**, create a uniquely named regional private bucket in the risk project, use uniform bucket-level access and public-access prevention, and upload `automl.csv`, `raw.csv`, `holdout-features.csv` and `manifest.json`. Keep `holdout-labels.csv` local for scoring. Record the bucket name, region, file paths and permissions; take screenshots of the upload and object listing.

Through **Vertex AI → Datasets → Create dataset**, choose **Tabular → Classification**, name it `credit-classification-temporal`, and import `automl.csv` from that bucket. Capture the import running, completed dataset, schema and class distribution.

## 3. Run AutoML from the dashboard

On the dataset page choose **Train new model → AutoML → Classification**. Set target to `Pago_atiempo`; use binary classification. Under data split choose the predefined/manual split column `data_split`, whose values are `TRAIN`, `VALIDATE`, `TEST`. Confirm that split metadata is excluded from features. Do not choose a random split.

**Historical budget decision 2026-11-08 (superseded for one AutoML run):** The actual classic AutoML form rejected 0.7 node-hours and requires 1–72. One node-hour costs USD21.252 at the standard published rate, exceeding the user’s USD15 limit. The form was cancelled without submission. Under that former limit, AutoML and batch inference were not submitted. On 2026-11-09 JST the user explicitly authorized one classic AutoML run with a 1000 milli-node-hour budget (approximately USD21.25). Use early stopping and the fixed manual split; do not increase that budget or add batch inference/endpoints. The alternative AutoML workflow has additional Dataflow, storage and training charges, so it is not treated as a USD15 fallback. The current authorization permits the classic AutoML configuration below; see the execution log for its actual state.

Review included predictors and transformations, then choose the ranking objective suited to rare defaults (AUC PR if available), and the minimum budget allowed by the UI, initially one node-hour if supported, with early stopping enabled. Record the exact offered objective, node-hours and price estimate. Any increase beyond the reviewed initial budget needs the user's choice. Capture the configuration and cost summary **before** clicking **Start training**, then capture the submitted run, training in progress and completion page, including model/run IDs and timestamps.

Open **Model Registry → model → Evaluate**. Capture overall metrics, default-class `0` precision/recall/F1, ROC and PR curves, confusion matrix and threshold settings. Overall/micro F1 must not be relabeled default-class F1. Record model version, training split counts and evaluation IDs. A missing metric remains missing; never substitute a result from another model.

**Future optional step, not authorized by the current training-only budget:** for canonical local scoring, use **Batch predictions → Create** in the dashboard with `holdout-features.csv`, GCS output in JSONL and no online endpoint. Extra `row_id` is passthrough metadata, absent during training, and lets us join output rows without trusting batch order. Download every `predictions*.jsonl` shard and inspect any error shards. Score at the fixed default-probability threshold 0.5:

```bash
python -m cloud.compare automl \
  --predictions output/automl-batch/predictions*.jsonl \
  --data output/cloud-data --output output/vertex-automl.json
```

The scorer maps the returned class names to `P(default=0)` even if class order changes; it rejects missing, extra or duplicate row IDs, malformed probabilities and prediction errors. It computes Accuracy, default precision/recall/F1, ROC-AUC, PR-AUC, a confusion matrix, conditional bootstrap intervals and three chronological holdout block summaries. Thresholds are never tuned on TEST. Preserve native evaluation screenshots separately from this fixed-threshold comparison.

## 4. Prepare the custom pipeline, then launch it through the dashboard

The custom component runs the existing CPU training/evaluation implementation with `ci/training.json`: logistic regression, decision tree, random forest, heuristic and dummy references; three seeds; temporal folds; selection/calibration before the frozen holdout. It verifies dataset/holdout fingerprints before fitting and exports artifacts plus Vertex metrics. Cache reuse is disabled for measured runs.

After approval, create a private training Artifact Registry repository in the risk project and build/push `cloud/Dockerfile`. This infrastructure/package preparation can be scripted; **submission and training are dashboard actions**. Record the image's immutable digest, permissions and package versions. Grant a dedicated pipeline service account Vertex AI User and object access to the lab bucket, plus reader access to the training-image repository. Grant the initiating user service-account use as needed; never use a service-account key or owner/editor roles for the runtime.

```bash
docker build -f cloud/Dockerfile -t TRAINING_IMAGE_TAG .
# Authenticate to the verified risk project's registry, push, then obtain its digest.
python -m cloud.compile_pipeline \
  --image REGION-docker.pkg.dev/PROJECT/REPOSITORY/trainer@sha256:REAL_DIGEST \
  --output cloud/pipeline.json
```

`output/pipeline-draft.json` was compiled successfully using a dummy digest as an offline structural check. It is not the final package. Replace the digest and compile again before upload.

The final package is now `output/credit-pipeline-dashboard.json`, using the published digest recorded in `output/training-runtime.json`. Through **Vertex AI → Pipelines → Create run**, upload that package; select the dedicated service account and pipeline root `gs://BUCKET/pipeline-root`. Enter:

| Parameter | Value |
|---|---|
| `input_uri` | `gs://BUCKET/raw.csv` |
| `dataset_sha256` | `48e34610b823055a5f4e7a107142e25b08ba40920848eab1a68ff6396eb26927` |
| `holdout_sha256` | `f0f8ec775541328cfcaf07fa5a8455a089b2f3832549c583de35804f5216329a` |

Verify these against the actual manifest if the source changes. Capture the upload/parameters page and summary, click **Submit** in the dashboard, and capture the running DAG, task logs, resource settings (2 CPUs, 8 GB), completion status and Metrics/Artifacts panels. Download the `results` artifact directory and its `comparison.json`; preserve the pipeline run ID, image digest, logs, duration and actual status in the inventory.

## 5. Compare measured results and discuss consistency

The already measured Python baseline is in `output/local-baseline`. Normalize it and add only real cloud reports:

```bash
python -m cloud.compare local --run output/local-baseline --output output/python-local.json
python -m cloud.compare report \
  --inputs output/python-local.json output/vertex-custom/comparison.json \
  --output output/comparison-gcp --language es
```

The report refuses comparisons across different source/holdout hashes and emits a CSV table, chart and discussion. Until cloud runs finish, its report explicitly lists them as pending. Bootstrap intervals describe holdout sampling uncertainty conditional on observed class counts; they do not establish repeated-training stability. Python/custom report variation over temporal folds and three seeds. A single AutoML run cannot establish seed stability: repeat the same dashboard configuration and budget, if approved, and compare its holdout results. Record failed/cancelled runs as such, including charged duration.

Discuss rare-default prevalence, calibration/threshold effects, temporal drift and repeat variance. Compare ROC/PR ranking metrics alongside operating-point F1; Python/custom use calibrated validation-derived thresholds whereas AutoML scoring fixes 0.5. Accuracy alone rewards predicting everyone on-time (96.66% on this holdout). RMSE is a regression metric and is not presented as credit-classification quality.

Manual Python provides direct control over temporal validation, preprocessing, class conventions, thresholds, seeds and runtime costs. AutoML supplies managed search and evaluation with less manual model design, but training budget and internal choices are less transparent. Draw superiority conclusions only after the actual dashboard runs complete.

## 6. Evidence and cleanup

Save real screenshots under `output/playwright/gcp/` and inspect each saved PNG for legible settings, job status, project and timestamps. Maintain a run log with screenshot path, UTC timestamp, URL, action, observed result, run/model ID and next step. The minimum evidence sequence is: identity/project, service enabled, uploaded objects, dataset import, AutoML configuration, AutoML running, AutoML completed/evaluation, custom package parameters, custom DAG running, custom completed/artifacts, comparison chart and cleanup.

Actual Japanese-console screenshots are indexed in `output/playwright/gcp/index.json`; the user authorized and signed into this session. The initial AutoML form was cancelled under the former USD15 limit; after explicit authorization of approximately USD21.25, job 7023547864391352320 was submitted through the dashboard. Setup screenshots must not be represented as completed cloud training.

After evidence is saved, remove lab endpoints if any were explicitly deployed, and remove only this exercise's models/datasets/bucket artifacts and images when the user is ready. No online endpoint is required. Never delete an existing shared project or another workload. Update the root inventory with retained resources and recurring charges.

References: [Vertex AutoML training SDK and split definitions](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.AutoMLTabularTrainingJob), [AutoML batch input/output requirements](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/tabular-workflows/e2e-automl-batch-predictions), [Vertex AI Pipeline runs](https://docs.cloud.google.com/vertex-ai/docs/pipelines/run-pipeline).

The completed dashboard run and observed billing/credits are documented in [gcp-execution.md](gcp-execution.md). The earlier USD15 restriction was superseded for one explicitly authorized AutoML run at approximately USD21.25. Record its actual submission and outcome; never add local substitute scores for AutoML.
