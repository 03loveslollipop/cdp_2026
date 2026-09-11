# Model serving and monitoring

The staging system is deployed at
[`cdp-2026-credit-risk`](https://cdp-2026-credit-risk-4b94df7c43fb.herokuapp.com/).
It is one Heroku Eco container app containing the FastAPI API, batch-upload page, and
Dash UI at `/monitor/`. HTTP Basic authentication protects every route except the two
health endpoints.

This remains a staging/demo deployment. The source extract does not establish feature
snapshot timing or outcome maturity, and the diagnostic holdout has already been
inspected. It must not be treated as an automated lending decision service.

## Packages

```text
etl_scripts/src/
├── database/
│   ├── connectors/       engine and transaction setup
│   ├── migrations/       advisory-locked, checksum-verified schema versions
│   ├── models/           schema-qualified SQLAlchemy tables
│   └── repositories/     model, prediction, outcome, sample, and monitoring access
├── model_deploy/
│   ├── api/              health, model, prediction, and outcome routes
│   ├── frontend/         batch CSV page
│   ├── models/           API and artifact contracts
│   └── services/         artifact training/loading and business workflows
└── model_monitoring/
    ├── models/           aggregate metric values
    ├── pages/            five independent Dash views
    └── services/         drift, performance, retention, dashboard, and job logic
```

All SQLAlchemy tables and foreign keys explicitly target the `cdp_2026` schema. The
migration runner takes a PostgreSQL advisory transaction lock, records a checksum for
each applied version, and refuses to continue if an applied migration was edited.

## Model-independent deployment contract

`etl_scripts/src/deployment_model_config.json` is the only file that chooses the model
family and fixed winning hyperparameters. The deployment training command reuses
`build_model`, the chronological split, temporal out-of-fold calibration, and
default-class threshold selection from `model_training_evaluation.py`:

```bash
python scripts/install_model_runtime.py etl_scripts/src/deployment_model_config.json
python -m etl_scripts.src.model_deploy train --output-dir deployment_artifacts
```

The ignored output contains `best_model.joblib`, `deployment_manifest.json`, and
`reference_profiles.json`. The manifest fixes class order `[default, on-time]`, records
the artifact and configuration hashes, and pins the exact runtime dependency versions.
The web process refuses to start if the hash, class order, model interface, or installed
versions do not match. Model binaries remain outside Git.

The supported learned families are logistic regression, classification tree, Gaussian
Bayes, random forest, Extra Trees, RBF SVM, XGBoost, LightGBM, and the PyTorch MLP. The
Docker build reads the same config and installs only the selected family's CPU runtime.
Changing a family or parameters requires a config change and retraining, not serving-code
changes.

## HTTP endpoints

- `GET /health/live` and `GET /health/ready`
- `GET /v1/model`
- `POST /v1/predictions` with a JSON `records` array
- `POST /v1/predictions/csv` with a `file` multipart field
- `POST /v1/outcomes` for timezone-aware later-arriving labels

Prediction requests require an `Idempotency-Key` header of 8–128 characters. Reusing a
key with the same canonical batch returns the stored result; reusing it for different
data returns HTTP 409. The service validates the entire batch before inference and saves
the completed batch and every prediction event in one transaction.
`GET /v1/model` includes the active `required_predictors` contract used by the browser's
pre-submit CSV header preview and by API clients generating batches.

Retrieve the generated staging credentials locally without committing them:

```bash
heroku config:get CDP_AUTH_USERNAME --app cdp-2026-credit-risk
heroku config:get CDP_AUTH_PASSWORD --app cdp-2026-credit-risk
```

## Monitoring

Heroku Scheduler job `1341184` runs daily at 06:30 UTC on an Eco dyno. The command
computes rolling seven-day windows, filling up to seven missed daily windows on each run:

```bash
heroku run --no-tty --app cdp-2026-credit-risk -- \
  python -m etl_scripts.src.model_monitoring compute \
  --catch-up --include-retention
```

Metrics include numeric/categorical PSI, missingness changes, unknown-category rate,
score PSI, predicted-default fraction, default F1/precision/recall, average precision,
ROC-AUC, accuracy, Brier score, log loss, and expected calibration error. Performance is
only calculated after enough mature outcomes include both classes. Otherwise the stored
status is `insufficient_data`.

The Dash pages read only `monitoring_runs` and `monitoring_metrics` for the active model
version; they never return raw financial predictor records or mix versions. Raw prediction
batches default to 365-day retention, while aggregate monitoring rows remain.

## Docker and automation

`Dockerfile.web` and `Dockerfile.release` run as an unprivileged user. The release image
applies migrations and idempotently imports the approved sample CSV. Heroku Container
Registry requires Docker Manifest V2 Schema 2, so local and CI pushes use a buildx
registry exporter with `oci-mediatypes=false`:

```bash
docker buildx build --platform linux/amd64 --provenance=false \
  --output type=registry,name=registry.heroku.com/cdp-2026-credit-risk/web,oci-mediatypes=false \
  --file Dockerfile.web .
docker buildx build --platform linux/amd64 --provenance=false \
  --output type=registry,name=registry.heroku.com/cdp-2026-credit-risk/release,oci-mediatypes=false \
  --file Dockerfile.release .
heroku container:release web release --app cdp-2026-credit-risk
```

`.github/workflows/heroku-container.yml` runs on every branch push, retrains from the
deployment config, pushes both images, releases them serially, and verifies readiness.
This deliberately makes the Heroku app a shared staging target: the most recent completed
branch deployment wins. `.github/workflows/model-monitoring.yml` is a manual recovery
path; it deliberately has no second cron because Heroku Scheduler owns the daily run.
GitHub stores only `HEROKU_APP_NAME` and a dedicated one-year `HEROKU_API_KEY`; rotate
the authorization before it expires.
