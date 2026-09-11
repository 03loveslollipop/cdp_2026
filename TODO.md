# Project delivery checklist

## Stage 1: collaboration

Use feature branches and bring completed work back to the repository default branch
through review. The feature-engineering pipeline is merged; the heuristic and model
training work retain their existing branch/PR history.

## Stage 2: test automation

Do not configure SonarCloud yet. Wait until the requested repository work is available
from the default branch. Code quality, security, coverage, integrity, and style checks
remain a later task.

## Stage 3: repository contents

- `etl_scripts/src/development/eda.ipynb`: implemented exploratory analysis.
- `etl_scripts/src/ft_engineering.py`: implemented leakage-safe feature pipeline.
- `etl_scripts/src/heuristic_model.py`: implemented explainable reference model.
- `etl_scripts/src/model_training_evaluation.py`: implemented tracked training,
  evaluation, model selection, and artifact export pipeline. The previously added
  `model_training.ipynb` is obsolete and is not part of this branch.
- `etl_scripts/src/model_deploy/`: implemented modular FastAPI API, model training/loading
  services, dynamic visual and batch frontends, asymmetric JWT authentication, inference
  and owner roles, validation, idempotency, and transactional prediction logs.
- `etl_scripts/src/model_monitoring/`: implemented modular scheduled monitoring and Dash
  views for data drift, prediction drift, matured performance, calibration, data quality,
  and job health.
- `etl_scripts/src/database/`: implemented modular PostgreSQL connectors, models,
  repositories, database-backed Argon2id users/roles, prediction ownership, and versioned
  migrations in the isolated `cdp_2026` schema.
- `etl_scripts/src/deployment_model_config.json`: winning family, fixed hyperparameters,
  runtime class order, and deployment settings.
- `dataset.csv`: approved non-production sample, loaded idempotently into Heroku Postgres.
- `Dockerfile.web`, `Dockerfile.release`, requirements, GitHub Actions, and Heroku
  Scheduler: implemented CPU-only container build, Heroku release, branch-push CI/CD,
  daily monitoring, and a manual monitoring recovery workflow.

The deployed model is exposed for batch prediction. Predictor records, returned
probabilities, decisions, and later outcomes are stored for periodic population-drift and
performance monitoring. Model binaries and record-level exports must remain outside Git.
