# Model-serving microservices

The staging deployment is split into four independently deployable Heroku container
applications:

| Responsibility | Heroku app | Public entry point |
| --- | --- | --- |
| Authentication and JWT issuance | `cdp-2026-auth-service` | [Authentication health](https://auth.cdp2026.02labs.me/health/ready) |
| Model inference and visual inference | `cdp-2026-credit-risk` | [Inference application](https://api.cdp2026.02labs.me/) |
| Scheduled monitoring calculations | `cdp-2026-monitor-batch` | No continuously running dyno |
| Monitoring visualization and outcomes | `cdp-2026-monitor-ui` | [Owner monitoring login](https://monitor.cdp2026.02labs.me/) |

```text
Browser or API client
        |
        +------------------------+
        |                        |
        v                        v
Inference service          Monitoring UI
model + visual form        Dash + outcomes
        |                        |
        +------> Auth service <--+
                 Ed25519 JWT
                 user database
                        |
                        v
          postgresql-tapered-63136
               cdp_2026 schema
                        ^
                        |
             Monitoring batch service
             daily aggregates + retention
```

All four apps attach the existing `postgresql-tapered-63136` add-on as
`CDP_DATABASE_URL`. Every table, foreign key, and query is explicitly qualified under
`cdp_2026`; unrelated schemas are outside the application boundary. The configured
connection pools have a worst-case total of 15 connections, below the datastore's
20-connection limit.

This remains a staging/demo deployment. The source extract does not establish feature
snapshot timing or outcome maturity, and the diagnostic holdout has already been
inspected. It must not be treated as an automated lending decision service.

## Code boundaries

```text
etl_scripts/src/
├── database/
│   ├── connectors/       engine and transaction setup
│   ├── migrations/       advisory-locked, checksum-verified schema versions
│   ├── models/           schema-qualified SQLAlchemy tables
│   └── repositories/     focused persistence operations
├── model_auth/
│   ├── api/              login, introspection, JWKS, and health
│   ├── models/           authentication HTTP contracts
│   └── services/         PostgreSQL credentials and Ed25519 JWTs
├── model_deploy/
│   ├── api/              model metadata, prediction, auth proxy, and health
│   ├── frontend/         dynamic single-record and batch inference
│   ├── models/           inference and artifact contracts
│   └── services/         artifact training/loading and prediction workflow
├── model_monitoring/
│   ├── models/           aggregate and outcome contracts
│   ├── pages/            five Dash monitoring views
│   ├── services/         drift, performance, retention, outcome, and dashboard logic
│   └── visualization/    independent owner-only FastAPI/Dash service
└── service_clients/
    ├── contracts.py      dependency-free auth roles and principal contract
    └── authentication.py async auth-service HTTP client
```

Only the authentication service has `CDP_JWT_PRIVATE_KEY`. Inference and monitoring
visualization validate each request through `POST /v1/auth/introspect`, protected by a
random `CDP_INTERNAL_SERVICE_TOKEN`. They use same-origin login proxies for their browser
pages, so credentials and cookies remain scoped to the service the user is visiting.

## Model-independent deployment

`etl_scripts/src/deployment_model_config.json` is the only file that selects the winning
model family and fixed hyperparameters. Deployment training reuses `build_model`, the
chronological split, temporal out-of-fold calibration, and default-class threshold
selection from `model_training_evaluation.py`:

```bash
python scripts/install_model_runtime.py etl_scripts/src/deployment_model_config.json
python -m etl_scripts.src.model_deploy train --output-dir deployment_artifacts
```

The ignored output contains `best_model.joblib`, `deployment_manifest.json`, and
`reference_profiles.json`. The manifest fixes class order `[default, on-time]`, records
artifact and configuration hashes, and pins runtime versions. The inference service
refuses startup if the hash, class order, model interface, or installed versions differ.
Changing model family or parameters requires a config change and retraining, not inference
or frontend code changes.

The supported learned families are logistic regression, classification tree, Gaussian
Bayes, random forest, Extra Trees, RBF SVM, XGBoost, LightGBM, and PyTorch MLP. The
inference image installs only the selected model's CPU runtime.

## HTTP contracts

Authentication service:

- `GET /health/live` and `GET /health/ready`
- `POST /v1/auth/login`
- `POST /v1/auth/introspect` with bearer and internal service credentials
- `POST /v1/auth/logout`
- `GET /.well-known/jwks.json`

Inference service:

- `GET /health/live` and `GET /health/ready`
- `POST /v1/auth/login` and `POST /v1/auth/logout` proxies
- `GET /v1/model`
- `POST /v1/predictions`
- `POST /v1/predictions/csv`
- `GET /` and `GET /inference/` visual inference pages

Monitoring visualization service:

- `GET /health/live` and `GET /health/ready`
- `POST /v1/auth/login` and `POST /v1/auth/logout` proxies
- `POST /v1/outcomes`
- `GET /monitor/` and Dash callback routes

Prediction requests require an `Idempotency-Key` header of 8–128 characters. Reusing a
key with the same canonical batch and user returns the stored result; reusing it for
different data returns HTTP 409. The full batch is validated before inference, then the
batch and every event are written transactionally with the requesting user's database ID.

## Authentication and roles

`POST /v1/auth/login` returns an EdDSA JWT with an exact 7,200-second lifetime. Tokens
contain the issuer, audience, immutable user ID, username, role, token version,
issue/not-before/expiry times, and unique token ID. API routes require an
`Authorization: Bearer <token>` header; browser pages use secure, HTTP-only, same-site
cookies.

| Role | Model contract | JSON/CSV inference | Submit outcomes | Monitoring UI |
| --- | --- | --- | --- | --- |
| `inference` (default) | Yes | Yes | No | No |
| `owner` | Yes | Yes | Yes | Yes |

Users live in `cdp_2026.auth_users` as canonical usernames, Argon2id hashes, roles,
active flags, token versions, and audit timestamps. Login and introspection recheck this
table, so password resets, role changes, and account disabling invalidate existing tokens.

Manage users with an interactive one-off dyno on the auth app:

```bash
heroku run --app cdp-2026-auth-service -- \
  python -m etl_scripts.src.database users list
heroku run --app cdp-2026-auth-service -- \
  python -m etl_scripts.src.database users create \
  --username analyst --role inference
heroku run --app cdp-2026-auth-service -- \
  python -m etl_scripts.src.database users reset-password --username analyst
heroku run --app cdp-2026-auth-service -- \
  python -m etl_scripts.src.database users set-role \
  --username analyst --role owner
heroku run --app cdp-2026-auth-service -- \
  python -m etl_scripts.src.database users disable --username analyst
```

The administration layer refuses to disable or demote the final active owner.

## Monitoring batch

Heroku Scheduler add-on `scheduler-dimensional-86985` belongs to
`cdp-2026-monitor-batch`. It launches an Eco one-off dyno daily at 06:30 UTC:

```bash
python -m etl_scripts.src.model_monitoring compute \
  --catch-up --include-retention
```

The command computes rolling seven-day windows and catches up at most seven missed daily
windows. It writes numeric/categorical PSI, missingness and unknown-category changes,
score and review-queue drift, and mature F1, precision, recall, average precision,
ROC-AUC, Brier score, log loss, and calibration metrics. Insufficient samples or a
single outcome class produce an explicit `insufficient_data` state.

The visualization reads aggregate monitoring tables for the currently active model on
every refresh. It does not expose record-level financial data or mix model versions.
Raw prediction batches default to 365-day retention; aggregate monitoring rows remain.

## Containers and CI/CD

Each service has a separate non-root image and pinned dependency set:

- `Dockerfile.auth` / `requirements-auth.txt`
- `Dockerfile.inference` / `requirements-inference.txt`
- `Dockerfile.monitoring-batch` / `requirements-monitoring-batch.txt`
- `Dockerfile.monitoring-ui` / `requirements-monitoring-ui.txt`
- `Dockerfile.release` owns migrations on the auth app
- `Dockerfile.inference-release` prevents inference from inheriting migration work

`.github/workflows/heroku-container.yml` runs on every branch push. It retrains the
configured winner, pushes service-specific images to each app's Heroku Container Registry,
then releases in dependency order: auth/migrations, inference, monitoring batch, and
monitoring visualization. Readiness gates stop the sequence if a dependency fails. The
batch web formation remains scaled to zero because Scheduler starts one-off dynos.

Required GitHub secrets are:

- `HEROKU_API_KEY`
- `HEROKU_AUTH_APP_NAME`
- `HEROKU_INFERENCE_APP_NAME`
- `HEROKU_MONITORING_BATCH_APP_NAME`
- `HEROKU_MONITORING_UI_APP_NAME`

The most recent completed branch deployment wins the shared staging environment.
`.github/workflows/model-monitoring.yml` is a manual recovery path and deliberately has
no second cron schedule.
