# CDP 2026 project handoff

This document is the technical map for an agent continuing the project. Read
`AGENTS.md` first for repository rules, then this file for the system overview,
`PROGRESS.md` for chronological evidence and experiment results, and `TODO.md` for the
short remaining-work list.

## Current handoff state

- Repository: `03loveslollipop/cdp_2026`; default branch: `master`.
- Current handoff branch: `chore/showcase-monitoring-handoff`.
- Pull request: [#10](https://github.com/03loveslollipop/cdp_2026/pull/10), targeting
  `master`. At the time of this handoff it is mergeable and all CPU-test, coverage, and
  SonarCloud checks pass, but repository policy still requires approval.
- PR #10 documents the custom domains and monitoring showcase, removes the stale CUDA
  deployment option, and restricts automatic Heroku deployment to pushes on `master`.
- The deployed model is explicitly `staging`/demo. It must not be represented as a
  production lending-decision system.
- CUDA code, environments, studies, and artifacts exist only in the ignored local
  `.local_cuda_training/` tree. They are not part of the repository or remote CI/CD.

Time-sensitive state must be rechecked with `git fetch`, `gh pr view 10`, GitHub Actions,
and Heroku before making operational claims.

## Purpose and data

The repository implements an end-to-end credit-payment-risk workflow around 10,763
Colombian consumer loans. `Pago_atiempo=0` is default and `Pago_atiempo=1` is on-time
payment. Public probability arrays always use `[P(default), P(on-time)]`, or class order
`[0, 1]`.

The project contains:

1. Exploratory data analysis and documented data-quality findings.
2. Leakage-safe feature preparation with chronological partitioning.
3. Heuristic, reference, and learned-model training and comparison.
4. Reproducible grid or budgeted Optuna TPE search.
5. Config-driven CPU artifact packaging.
6. Four independently deployed Heroku microservices.
7. PostgreSQL-backed users, predictions, outcomes, and monitoring aggregates.
8. Scheduled population-drift, data-quality, and mature-performance monitoring.
9. CPU-only CI, coverage, Ruff, SonarCloud, container build, and Heroku deployment.

The source CSV and current outcome semantics are suitable for demonstration, not final
credit-policy validation. The extract does not establish when every feature was observed
relative to the decision or when an outcome becomes mature. The diagnostic holdout has
also already been inspected.

## System architecture

```text
Browser / API client
        |
        +-----------------------------+
        |                             |
        v                             v
Inference service               Monitoring UI
FastAPI + batch/visual UI        FastAPI + owner-only Dash
        |                             |
        +----------> Auth service <---+
                      Ed25519 JWT
                           |
                           v
              Heroku PostgreSQL add-on
              postgresql-tapered-63136
                    cdp_2026 schema
                           ^
                           |
                 Monitoring batch service
                 scheduled aggregates/retention
```

All application SQL is explicitly qualified under `cdp_2026`. The shared Essential-tier
credential can see unrelated schemas, so never rely on `search_path`, create unqualified
tables, or modify another schema.

## Live services

| Responsibility | Heroku app | Public URL |
| --- | --- | --- |
| Authentication/JWT | `cdp-2026-auth-service` | `https://auth.cdp2026.02labs.me/` |
| Inference and visual inference | `cdp-2026-credit-risk` | `https://api.cdp2026.02labs.me/` |
| Scheduled calculations | `cdp-2026-monitor-batch` | No persistent web dyno |
| Monitoring visualization | `cdp-2026-monitor-ui` | `https://monitor.cdp2026.02labs.me/monitor/` |

Useful public checks:

- `https://auth.cdp2026.02labs.me/health/ready`
- `https://auth.cdp2026.02labs.me/.well-known/jwks.json`
- `https://api.cdp2026.02labs.me/health/ready`
- `https://api.cdp2026.02labs.me/inference/`
- `https://monitor.cdp2026.02labs.me/health/ready`

The three CNAMEs are DNS-only and point to their Heroku DNS targets. Heroku Automatic
Certificate Management is enabled. Do not expose secret config values while inspecting
apps. The Scheduler add-on is attached only to the monitoring-batch app.

## Repository layout

```text
.
├── AGENTS.md                         mandatory agent/development rules
├── PROJECT.md                        this technical handoff
├── PROGRESS.md                       chronological results and validation evidence
├── TODO.md                           concise outstanding work
├── README.md                         EDA findings and project introduction
├── CONTRIBUTING.md                   contribution workflow
├── dataset.csv                       approved non-production sample
├── etl_scripts/src/
│   ├── development/eda.ipynb         exploratory analysis
│   ├── config.json                   data semantics and preparation rules
│   ├── ft_engineering.py             preparation and chronological split
│   ├── heuristic_model.py            explainable reference classifier
│   ├── torch_classifier.py           sklearn-compatible CPU MLP
│   ├── adaptive_search.py            resumable Optuna TPE orchestration
│   ├── model_training_config.json     candidates, search spaces, budgets, seeds
│   ├── model_training_evaluation.py   comparison, selection, reports, artifacts
│   ├── deployment_model_config.json   deployed family and fixed parameters
│   ├── database/                      persistence and migrations
│   ├── model_auth/                    authentication microservice
│   ├── model_deploy/                  inference microservice and frontend
│   ├── model_monitoring/              batch calculations and visualization
│   └── service_clients/               service-to-service auth contracts/client
├── tests/                             CPU-only unit/integration tests
├── scripts/install_model_runtime.py   selected-family CPU dependency installer
├── docs/
│   ├── deployment.md                  serving operations and contracts
│   ├── model_training.md              modelling protocol
│   ├── model_benchmark/               published aggregate benchmark
│   └── figures/                       published EDA figures
├── Dockerfile.*                       purpose-specific non-root images
├── requirements*.txt                  base/training/service dependency sets
└── .github/workflows/
    ├── build.yml                      CPU tests, coverage, Ruff, SonarCloud
    ├── heroku-container.yml           master/manual deployment
    └── model-monitoring.yml           manual monitoring recovery
```

Model binaries, record-level predictions, Optuna databases, local environments, and run
directories must remain outside Git. Aggregate reports and figures may be published.

## Modelling invariants

These constraints are correctness requirements, not preferences:

- Preserve the chronological 70/30 raw-data split and timestamp groups.
- Fit preparation, encoding, scaling, weights, calibration, and thresholds using
  training-period data only.
- Do not use `puntaje`, its derivatives, the target, or metadata as predictors.
- Do not silently drop rows. Preserve configured missingness indicators and validation
  flags.
- Default is class `0`; APIs and artifacts expose class order `[0, 1]`.
- Use `build_model` and `summarize_classification` for every model family.
- Select on default-class F1, temporal/seed consistency, and CPU inference cost.
- Never use the final holdout for trial, threshold, or winner selection.
- Tracked training, tests, CI, and deployment are CPU-only. Do not add CUDA code to a
  tracked path.

`model_training_evaluation.py` supports logistic regression, classification tree,
Gaussian Bayes, random forest, Extra Trees, RBF SVM, XGBoost, LightGBM, PyTorch MLP,
the heuristic reference, and the always-on-time dummy reference. Learned families use
temporal folds, temporal calibration, and frozen threshold selection. See
`docs/model_training.md` for the exact protocol.

## Training and model configuration

`etl_scripts/src/model_training_config.json` controls seeds, temporal blocks, thread
counts, grid candidates, TPE search spaces, trial/time budgets, benchmarking, and review
fraction. Grid remains the reproducible default; TPE is opt-in and stores resumable,
fingerprinted studies under ignored `runs/`.

Typical commands:

```bash
python -m pip install -r requirements.txt -r requirements-training.txt
python -m etl_scripts.src.model_training_evaluation \
  --smoke --device cpu --output-dir runs/smoke
python -m etl_scripts.src.model_training_evaluation \
  --search-method tpe --device cpu --n-trials 30 --timeout-seconds 1800 \
  --study-storage runs/training_studies.sqlite3 \
  --output-dir runs/tpe_cpu
```

`etl_scripts/src/deployment_model_config.json` is the deployment contract. It currently
selects an XGBoost model, class order `[0, 1]`, CPU training/serving, and stage `staging`.
The source field records the local experiment that supplied the fixed parameters; it is
provenance, not permission to add CUDA to tracked deployment code.

Deployment artifact creation:

```bash
python scripts/install_model_runtime.py etl_scripts/src/deployment_model_config.json
python -m etl_scripts.src.model_deploy train \
  --output-dir deployment_artifacts
```

The ignored output contains `best_model.joblib`, `deployment_manifest.json`, and
`reference_profiles.json`. The loader verifies SHA-256, exact package versions, model
interface, and class order before serving.

## Database layer

`etl_scripts/src/database/` is deliberately modular:

- `connectors/postgres.py`: engine, pool, transactions, required `CDP_DATABASE_URL`.
- `models/`: schema-qualified SQLAlchemy models.
- `repositories/`: focused persistence operations.
- `migrations/runner.py`: advisory lock, immutable SQL snapshots, checksums.
- `seed.py`: idempotent `dataset.csv` import.
- `passwords.py` and `user_admin.py`: Argon2id credentials and account operations.
- `__main__.py`: release, migration, seed, and user-administration CLI.

Versioned migrations create:

- `schema_migrations`
- `model_versions`
- `sample_loans`
- `prediction_batches`
- `prediction_events`
- `observed_outcomes`
- `reference_profiles`
- `monitoring_runs`
- `monitoring_metrics`
- `auth_users`

Prediction batches and their events are saved transactionally. Idempotency is scoped to
the requesting user. Outcome ingestion references an existing prediction event. Migrations
must remain idempotent and must prove unrelated schemas are untouched.

## Authentication and authorization

The auth service is the only runtime holding `CDP_JWT_PRIVATE_KEY`. It uses Ed25519/EdDSA
JWTs with a fixed 7,200-second lifetime, issuer/audience validation, JTI, token version,
and a public JWKS endpoint. Passwords are stored only as Argon2id hashes.

Every introspection rechecks PostgreSQL active state, role, and token version. Password
reset, role change, or disable therefore revokes existing tokens. The administration
layer prevents disabling or demoting the last active owner.

Roles:

| Capability | `inference` | `owner` |
| --- | --- | --- |
| View model contract | Yes | Yes |
| JSON/CSV prediction | Yes | Yes |
| Submit outcomes | No | Yes |
| View monitoring | No | Yes |

Inference and monitoring UI call the auth service using
`CDP_INTERNAL_SERVICE_TOKEN`; they do not import signing logic. Browser pages use secure,
HTTP-only, same-site cookies. APIs require bearer tokens.

## Inference service

Key routes:

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/auth/login`, `POST /v1/auth/logout`
- `GET /v1/model`
- `POST /v1/predictions`
- `POST /v1/predictions/csv`
- `GET /` for batch upload
- `GET /inference/` for visual single-record inference

Prediction requests require an `Idempotency-Key` between 8 and 128 characters. The entire
batch is validated atomically against the artifact's required predictor contract. Missing
values are retained for the fitted pipeline. A key replay with identical canonical input
returns the stored result; different input returns HTTP 409. Maximum batch size defaults
to 1,000 rows.

The frontend reads the artifact contract dynamically, so changing the configured family
or hyperparameters does not require inference UI code changes.

## Monitoring

The monitoring batch process calculates:

- numeric and categorical population PSI;
- missingness and unknown-category changes;
- default-probability and review-queue drift;
- default-class F1, precision, recall, average precision, and ROC-AUC;
- Brier score, log loss, and calibration metrics when mature outcomes exist;
- explicit `insufficient_data` states instead of misleading estimates.

The owner-only Dash UI provides operational overview, feature drift, prediction
distribution, matured performance, and data-quality/job-health views. It reads aggregate
monitoring tables and does not expose raw financial rows.

Heroku Scheduler runs on `cdp-2026-monitor-batch` daily at 06:30 UTC:

```bash
python -m etl_scripts.src.model_monitoring compute \
  --catch-up --include-retention
```

Defaults are seven-day windows, up to seven missed-window replays, minimum 30 rows, and
365-day raw prediction retention. The batch app has no persistent web dyno.

A synthetic showcase batch was added on 2026-09-15. A forced monitoring run over 121
prediction rows wrote 46 aggregate metrics: 22 OK, 19 alert, 4 warning, and one
insufficient-data result. This is demonstration data, not validation evidence. Exact
aggregate details and run ID are in `PROGRESS.md`.

## Containers and deployment

Each service has a separate non-root image and minimized dependency set:

- `Dockerfile.auth`
- `Dockerfile.release` for migrations/auth release
- `Dockerfile.inference`
- `Dockerfile.inference-release` as a no-op release boundary
- `Dockerfile.monitoring-batch`
- `Dockerfile.monitoring-ui`

`.github/workflows/heroku-container.yml` automatically deploys only a push to `master`.
It may also be deliberately started with `workflow_dispatch`. It trains the configured
winner once, builds/pushes the service images, releases auth/migrations first, then
inference, monitoring batch, and monitoring UI, with readiness gates.

Do not broaden the push trigger back to all branches: every app shares one staging
environment, so a feature-branch deployment would overwrite it. Pull requests and other
branch pushes must run tests/SonarCloud only.

Required GitHub secret names are documented in `docs/deployment.md`. Never print, commit,
or copy their values into documentation.

## CI and local validation

`.github/workflows/build.yml` runs on pull requests and pushes to `master`. It installs
CPU PyTorch and the serving/training requirements, then runs compile checks, Ruff, pytest
with coverage XML, and SonarCloud.

Local equivalent:

```bash
python -m pip install -r requirements.txt -r requirements-training.txt
python -m pip install -r requirements-serving.txt
python -m compileall -q etl_scripts/src tests scripts
ruff check etl_scripts/src tests scripts --exclude '*.ipynb'
python -m pytest -q tests --cov=etl_scripts.src --cov-report=xml:coverage.xml
```

If the ambient Python environment has missing or incompatible packages, do not interpret
collection errors as repository failures. Use an isolated environment with the pinned
requirements or rely on the matching CI job. Do not use the ignored CUDA environment to
claim CPU deployment validation.

## Safe operational commands

```bash
# Current repository/PR state
git fetch origin
git status --short --branch
gh pr view 10
gh pr checks 10

# Public readiness
curl --fail https://auth.cdp2026.02labs.me/health/ready
curl --fail https://api.cdp2026.02labs.me/health/ready
curl --fail https://monitor.cdp2026.02labs.me/health/ready

# Scheduler attachment and recent batch logs
heroku addons --app cdp-2026-monitor-batch
heroku logs --app cdp-2026-monitor-batch --num 100

# Interactive user administration; passwords are prompted, never command arguments
heroku run --app cdp-2026-auth-service -- \
  python -m etl_scripts.src.database users list
```

Prefer health, aggregate, and metadata checks. Do not print database URLs, JWT keys,
internal tokens, passwords, raw prediction payloads, or record-level outcomes.

## Known limitations and next work

The remaining substantive work is not another model-family implementation:

1. Merge PR #10 after approval if it is still open and green.
2. Establish feature snapshot timing and confirm each predictor exists at decision time.
3. Define outcome maturity and label finality.
4. Collect genuinely new temporal data and run a locked external validation.
5. Accumulate enough mature outcomes for meaningful live performance/calibration views.
6. Decide promotion criteria before changing `deployment_model_config.json` from
   `staging` to a stronger environment label.
7. Monitor shared Heroku Eco-hour and PostgreSQL connection/storage limits.

Do not treat the synthetic drift showcase, the inspected holdout, or local CUDA search as
evidence that these production-readiness gates have been satisfied.

## How to continue safely

1. Fetch remote state and inspect the active branch, dirty files, PRs, and Actions runs.
2. Preserve user edits and keep new work on a focused branch from current `master`.
3. Read the relevant tests and config before changing pipeline behavior.
4. Maintain the modelling invariants and CPU-only tracked boundary.
5. Run focused tests while iterating, then the full CPU suite for integration changes.
6. Update `PROGRESS.md` with commands, versions, aggregate results, limitations, and
   outstanding work.
7. Keep `TODO.md` concise; use this file and the detailed docs for architecture.
8. Open PRs against `master`; do not deploy a feature branch unless explicitly invoking
   the manual workflow for a deliberate recovery operation.

