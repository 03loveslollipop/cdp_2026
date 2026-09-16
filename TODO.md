# Project delivery checklist

## Stage 1: collaboration

Use feature branches and bring completed work back to the repository default branch
through review. Feature engineering, the heuristic and model-training pipelines,
quality gates, four serving services, and adaptive search are merged into `master`.

## Stage 2: test automation

SonarCloud analysis is configured on `master` through PR #6. PR #7 merged CPU-only
tests, XML coverage, syntax, and Ruff checks.
SonarCloud provides static code-quality and security analysis. The exploratory notebook
has pre-existing Ruff findings and is excluded from that style check.

## Stage 3: repository contents

- `etl_scripts/src/development/eda.ipynb`: implemented exploratory analysis.
- `etl_scripts/src/ft_engineering.py`: implemented leakage-safe feature pipeline.
- `etl_scripts/src/heuristic_model.py`: implemented explainable reference model.
- `etl_scripts/src/model_training_evaluation.py`: implemented tracked training,
  evaluation, model selection, and artifact export pipeline. The previously added
  `model_training.ipynb` is obsolete and is not part of this branch.
- `etl_scripts/src/adaptive_search.py`: implemented budget-controlled CPU-only TPE
  search for the tracked training pipeline.
- `etl_scripts/src/model_auth/`: implemented independent PostgreSQL-backed login, Ed25519
  JWT issuance, protected introspection, and public JWKS service.
- `etl_scripts/src/model_deploy/`: implemented independent generic FastAPI inference API,
  dynamic visual and batch frontends, auth-service proxy/client, validation, idempotency,
  and transactional prediction logs.
- `etl_scripts/src/model_monitoring/`: implemented independent scheduled monitoring batch
  process and a separately deployable owner-only Dash visualization for drift, matured
  performance, calibration, data quality, outcomes, and job health.
- `etl_scripts/src/database/`: implemented modular PostgreSQL connectors, models,
  repositories, database-backed Argon2id users/roles, prediction ownership, and versioned
  migrations in the isolated `cdp_2026` schema.
- `etl_scripts/src/deployment_model_config.json`: winning family, fixed hyperparameters,
  runtime class order, and deployment settings.
- `dataset.csv`: approved non-production sample, loaded idempotently into Heroku Postgres.
- Service-specific Dockerfiles and requirements, GitHub Actions, and Heroku Scheduler:
  implemented CPU-only non-root images, ordered branch-push CI/CD, an independent daily
  monitoring app, and a manual monitoring recovery workflow.

The deployed model is exposed for batch prediction. Predictor records, returned
probabilities, decisions, and later outcomes are stored for periodic population-drift and
performance monitoring. Model binaries and record-level exports must remain outside Git.

## Remaining work after serving integration

- [x] Configure custom-domain DNS and TLS for `auth.cdp2026.02labs.me`,
  `api.cdp2026.02labs.me`, and `monitor.cdp2026.02labs.me`. Their DNS-only Cloudflare
  CNAME records point to the assigned Heroku DNS targets, Heroku ACM certificates are
  issued, and HTTPS health, public-page, and protected-route checks pass. The scheduled
  monitoring-batch app does not need a public DNS record.
- [ ] Establish feature snapshot timing and outcome maturity, then validate on genuinely
  new temporal data before considering promotion beyond the staging/demo deployment.
