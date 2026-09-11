# Model serving and monitoring

The staging system is deployed at
[`cdp-2026-credit-risk`](https://cdp-2026-credit-risk-4b94df7c43fb.herokuapp.com/).
It is one Heroku Eco container app containing the FastAPI API, batch-upload page, dynamic
single-record form at `/inference/`, and Dash UI at `/monitor/`. API clients authenticate
with two-hour Ed25519-signed JWT bearer tokens. Role checks keep monitoring and outcome
ingestion owner-only.

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
│   └── repositories/     user, model, prediction, outcome, sample, and monitoring access
├── model_deploy/
│   ├── api/              health, model, prediction, and outcome routes
│   ├── frontend/         dynamic single-record and batch CSV pages
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
- `POST /v1/auth/login` with a JSON username and password
- `POST /v1/auth/logout`
- `GET /.well-known/jwks.json` for the public Ed25519 verification key
- `GET /v1/model`
- `POST /v1/predictions` with a JSON `records` array
- `POST /v1/predictions/csv` with a `file` multipart field
- `POST /v1/outcomes` for timezone-aware later-arriving labels

Prediction requests require an `Idempotency-Key` header of 8–128 characters. Reusing a
key with the same canonical batch returns the stored result; reusing it for different
data returns HTTP 409. Keys are scoped to the authenticated user, so one account cannot
replay another account's stored response. The service validates the entire batch before
inference and saves
the completed batch and every prediction event in one transaction. Each new batch stores
the authenticated user's database ID; deleting a user preserves historical batches while
setting that nullable attribution to `NULL`.
`GET /v1/model` includes `required_predictors` plus numeric/categorical field metadata.
Both browser inference forms are built from that live contract, so changing the configured
winner or its parameters requires no frontend code changes.

## Authentication and roles

`POST /v1/auth/login` returns an EdDSA JWT with an exact 7,200-second lifetime. Tokens
contain issuer, audience, immutable user ID, username, role, token version,
issue/not-before/expiry times, and a unique token ID. The server accepts only its
configured algorithm and key ID, and publishes only the public key through JWKS. API
routes require `Authorization: Bearer <token>`; cookies are not accepted as API
authentication. Login also sets a secure, HTTP-only, same-site token cookie solely so the
Dash browser callbacks can authenticate.

| Role | Model contract | JSON/CSV inference | Submit outcomes | Monitoring UI |
| --- | --- | --- | --- | --- |
| `inference` (default) | Yes | Yes | No | No |
| `owner` | Yes | Yes | Yes | Yes |

Users are stored in `cdp_2026.auth_users` in `postgresql-tapered-63136`. PostgreSQL holds
only canonical usernames, Argon2id password hashes, roles, active flags, token versions,
and audit timestamps—never recoverable plaintext passwords. Login and every authenticated
request consult this table. Password resets, role changes, and disabling an account bump
its token version, invalidating all JWTs previously issued to that user.

Migration `0002_auth_users` bootstraps the former owner and inference config credentials
exactly once. Existing database users are never overwritten by a later release, and the
four temporary username/password config vars are removed after bootstrap. Only the
Ed25519 signing pair remains in `CDP_JWT_PRIVATE_KEY` and `CDP_JWT_PUBLIC_KEY`; neither
key nor any password is committed.

Manage users through an interactive one-off dyno. Passwords are prompted twice and never
appear in shell history or command arguments:

```bash
heroku run --app cdp-2026-credit-risk -- \
  python -m etl_scripts.src.database users list
heroku run --app cdp-2026-credit-risk -- \
  python -m etl_scripts.src.database users create \
  --username analyst --role inference
heroku run --app cdp-2026-credit-risk -- \
  python -m etl_scripts.src.database users reset-password --username analyst
heroku run --app cdp-2026-credit-risk -- \
  python -m etl_scripts.src.database users set-role \
  --username analyst --role owner
heroku run --app cdp-2026-credit-risk -- \
  python -m etl_scripts.src.database users disable --username analyst
```

The administration layer refuses to disable or demote the final active owner.

Example API login and authenticated metadata request:

```bash
read -r -p "Username: " USERNAME
read -r -s -p "Password: " PASSWORD
echo
LOGIN_JSON="$(USERNAME="$USERNAME" PASSWORD="$PASSWORD" python -c \
  'import json,os; print(json.dumps({"username": os.environ["USERNAME"], "password": os.environ["PASSWORD"]}))')"
TOKEN="$(curl --silent --show-error \
  --header 'Content-Type: application/json' \
  --data "$LOGIN_JSON" \
  https://cdp-2026-credit-risk-4b94df7c43fb.herokuapp.com/v1/auth/login \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
curl --header "Authorization: Bearer ${TOKEN}" \
  https://cdp-2026-credit-risk-4b94df7c43fb.herokuapp.com/v1/model
unset USERNAME PASSWORD LOGIN_JSON TOKEN
```

Cookies are secure by default. Set `CDP_ENVIRONMENT=development` only for an HTTP local
stack; staging and production must leave the secure default in effect or use their named
environment.

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
