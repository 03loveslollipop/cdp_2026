# Credit-risk MLOps pipeline

This repository contains a leakage-safe credit-risk training pipeline and its CPU-only
production services. CUDA is intentionally not part of tracked code or deployment.

## Layout

```text
.
├── mlops_pipeline/
│   └── src/
│       ├── load_data.py                raw-data inspection entry point
│       ├── eda.ipynb                   exploratory analysis
│       ├── ft_engineering.py            leakage-safe preparation
│       ├── heuristic_model.py           interpretable baseline
│       ├── adaptive_search.py           CPU-only TPE search
│       ├── model_training_evaluation.py training and evaluation
│       ├── model_training_config.json   search candidates and budgets
│       └── deployment/                  production-only boundary
│           ├── database/                PostgreSQL schema, migrations, repositories
│           ├── model_auth/              Ed25519 JWT authentication service
│           ├── model_deploy/            inference API and browser UI
│           ├── model_monitoring/        batch computation and monitoring UI
│           ├── service_clients/         inter-service contracts
│           ├── Dockerfile.*             non-root service images
│           ├── requirements-*.txt       service-specific dependencies
│           └── deployment_model_config.json deployment model contract
├── 02_eda_report/                       EDA report PDF and published analysis figures
├── 03_slides/                           presentation sources and rendered deck assets
├── database.csv                         approved non-production source extract
├── config.json                          shared data semantics and preparation rules
├── requirements.txt                     complete local analysis and training dependencies
├── setup.sh / setup.bat                 local environment helpers
└── .github/workflows/                   tests, SonarCloud, and master-only deployment
```

All Markdown other than this README is ignored. Generated artifacts, local runs,
credentials, record-level predictions, and CUDA experiments are also ignored.

## Local development

```bash
python -m pip install -r requirements.txt
python -m pytest -q tests
python -m mlops_pipeline.src.load_data
python -m mlops_pipeline.src.model_training_evaluation --smoke --output-dir runs/smoke
```

The training split is chronological (70/30). Selection uses only temporal training
validation: default-class F1, stability, and CPU inference cost. The final holdout is
never used to tune models, thresholds, or feature choices. Probabilities always follow
`[P(default), P(on-time)]` with default encoded as `0`.

## Deployment

The deployment package has four independently runnable components: PostgreSQL-backed
authentication, inference, monitoring batch calculation, and monitoring visualization.
Each service is CPU-only and the Docker images are built from its Dockerfile in
`mlops_pipeline/src/deployment/` using the repository root as Docker context.

```bash
python -m pip install -r mlops_pipeline/src/deployment/requirements-serving.txt
python mlops_pipeline/src/deployment/install_model_runtime.py \
  mlops_pipeline/src/deployment/deployment_model_config.json
python -m mlops_pipeline.src.deployment.model_deploy train \
  --output-dir deployment_artifacts
```

`deployment_model_config.json` is the model contract: family, fixed hyperparameters,
CPU runtime constraints, class order, and promotion stage. Changing it lets the release
pipeline train and package a different validated winner without application code changes.

GitHub Actions always runs CPU tests and SonarCloud; only pushes to `master` build and
release the Heroku images. The release uses explicit `cdp_2026` schema qualification and
does not modify unrelated PostgreSQL schemas.
