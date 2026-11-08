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

Exercise runbooks in `docs/` are versioned alongside this README. Generated artifacts, local runs,
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

## Jenkins and Vertex AI semester exercise

The [Jenkins runbook](docs/jenkins.md) covers the approval pipeline, persistent local
container, automatic SCM polling, completion receipts and Terraform deployment in
the verified core IT GCP project. Start locally with:

```bash
python3 ci/prepare_local.py
python3 ci/jenkins/fetch_plugins.py
docker compose up -d --build
```

Open Jenkins at <http://127.0.0.1:18081>. The administrator credential is generated
under the ignored `.jenkins/secrets/` directory.

The [GCP training runbook](docs/gcp-training.md) covers AutoML and the custom Vertex
AI Pipeline, launched through the web dashboard after user approval and login.
`cloud/` provides offline data export, a KFP compiler, the training container and
comparison tools. Cloud scores remain pending until real dashboard runs finish.
The workspace-root `CLOUD_DEPLOYMENT_INVENTORY.md` records identities, project IDs,
resources, configurations and verified deployment state.

The [five-day expiry policy](docs/expiry-policy.md) schedules the Jenkins VM to stop
on **2026-11-13 at 02:41:05 UTC**, followed by teardown of its dedicated cloud resources.
# Informe unificado y webhook GitHub

El [informe de resultados en español](04_jenkins_report/INFORME_RESULTADOS_ES.md) reúne las ejecuciones reales, capturas de Jenkins, métricas, costos y política de eliminación. El PDF autocontenido y el ZIP para compartir se generan con `04_jenkins_report/build_report.py` en `output/pdf/`. El [procedimiento del webhook](docs/github-webhook.md) distingue implementación preparada, instalación y verificación efectiva de push/merge. La integración remota sigue pendiente de acceso del propietario y receptor HTTPS; los builds históricos acreditan polling SCM.
