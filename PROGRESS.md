# Model Training Progress and Handoff

## 2026-09-15 Custom domains and monitoring showcase

- Registered `auth.cdp2026.02labs.me`, `api.cdp2026.02labs.me`, and
  `monitor.cdp2026.02labs.me` on their respective Heroku apps. DNS-only Cloudflare
  CNAMEs resolve to the assigned Heroku targets, ACM certificates are issued, and
  HTTPS readiness passes for all three services.
- Logged one 120-row synthetic showcase batch through the deployed inference runtime's
  normal validation, prediction, idempotency, and transactional persistence service.
  The deliberately shifted predictors are demonstration data, not model-validation
  evidence. The batch completed once and produced 120 on-time decisions with mean
  default probability 0.075477.
- Forced a new rolling seven-day monitoring window ending after the showcase batch.
  Run `c61a8302-2d01-4067-b2fd-3d8444637ad6` completed over 121 prediction rows and
  wrote 46 aggregate metrics: 22 `ok`, 19 `alert`, 4 `warning`, and one
  `insufficient_data`. Mature-outcome performance remains unavailable because the
  window contains no mature outcomes.
- Removed the stale CUDA choice from the deployment-training CLI. Tracked training and
  deployment now expose CPU only; CUDA remains confined to the ignored local copy.

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

## Serving integration and quality gates on 2026-09-13

- SonarCloud setup merged to `master` through PR #6. PR #7 adds CPU-only tests,
  coverage upload, syntax, and Ruff checks; all of its PR checks passed. Its workflow
  is also merged into the serving feature branch so PR #8 can be measured before #7
  reaches `master`.
- PR #8 targets `master` with the four previously deployed services. The first
  SonarCloud scan found two accessibility bugs, public bind defaults, build-time path
  warnings, and 0% coverage because the test workflow had not been included. The
  accessibility and bind defaults were fixed; build artifacts and configuration reads
  are now confined to explicit checkout directories. The remaining JSON write was
  separated from its validated path to make the trust boundary clear.
- Added isolated tests for remote authentication errors, database administration and
  repositories, sample imports, migrations, artifact packaging, monitoring catch-up and
  Dash aggregate pages, readiness, and prediction/outcome API errors. No live database
  or raw record export is needed for the CPU suite.
- Local validation on Linux x86_64, Python 3.13.9: `ruff check etl_scripts/src tests
  scripts --exclude '*.ipynb'` and `python -m compileall -q etl_scripts/src tests
  scripts` passed; isolated serving-dependency environment ran `pytest -q tests
  --cov=etl_scripts.src --cov-report=xml:coverage.xml` with **141 passed, 5 skipped**
  and **89% Python line coverage**. The CI Python 3.12 result and SonarCloud new-code
  gate for this test batch are pending; do not equate local total coverage with the
  SonarCloud new-code metric.
- The prior branch-push deployment after merging PR #7's workflow succeeded through
  all four Heroku release/readiness stages. The next push will redeploy the hardened
  trainer and expanded tests. The staging/demo limitations below remain unchanged.

## Independent serving microservices on 2026-09-11

Branch: `feat/model-serving-monitoring`. Datastore: existing add-on
`postgresql-tapered-63136`, attached to all services as `CDP_DATABASE_URL`.

- Split the combined application into four independently deployable services:
  `cdp-2026-auth-service`, inference-only `cdp-2026-credit-risk`,
  `cdp-2026-monitor-batch`, and `cdp-2026-monitor-ui`.
- Added a dedicated `model_auth` package. It is the only runtime holding the Ed25519
  private key and the only service that reads credentials during login or token
  introspection. Inference and monitoring visualization use a protected HTTP contract and
  shared internal credential instead of importing authentication business logic.
- Kept prediction storage with inference, moved observed-outcome ingestion into the
  monitoring visualization boundary, and kept drift/performance/retention calculations in
  the non-web batch process. Dash reads the active model at refresh time, independently of
  an inference-process rollout.
- Added four non-root Docker images with purpose-specific requirements. Auth has no HTTP
  client or ML stack, inference has no Dash or signing stack, batch has no web framework,
  and visualization has no sklearn or JWT signing package. A no-op inference release image
  prevents the pre-split app from retaining migration ownership.
- Updated branch-push CI/CD to train once, publish each image to its own Heroku registry,
  and release in dependency order with readiness gates. Migrations are released only with
  auth. Service app names are separate GitHub secrets.
- Moved the daily 06:30 UTC Eco Scheduler job to `cdp-2026-monitor-batch` under add-on
  `scheduler-dimensional-86985`. The former inference-app scheduler was destroyed after
  the new schedule was confirmed. The batch web formation stays at zero.
- Removed signing keys and batch-monitoring settings from inference after live cutover.
  All services use explicit `cdp_2026` queries. Configured connection pools total at most
  15 concurrent connections against the datastore's limit of 20.

Validation completed:

```text
CPU suite: 71 passed, 1 CUDA-only skipped
Ruff and compileall: passed for all service packages
Images: four service images built; all run as non-root with dependency isolation checks
Live auth: database login, 7,200-second JWT, JWKS, and protected introspection passed
Live inference: readiness, remote auth, model metadata, prediction, attribution passed
Live authorization: inference denied monitoring; owner Dash and outcomes passed
Live monitoring batch: seven idempotent catch-up windows replayed; retention deleted 0
Cleanup: temporary users, prediction, and outcome removed
```

The deployed model remains staging/demo only. The same unresolved feature-timing,
outcome-maturity, and inspected-holdout limitations continue to apply.

## PostgreSQL authentication persistence on 2026-09-11

Branch: `feat/model-serving-monitoring`. Datastore: existing Heroku add-on
`postgresql-tapered-63136`, attached as `CDP_DATABASE_URL`.

- Added frozen migration `0002_auth_users`. It creates `cdp_2026.auth_users` with
  canonical unique usernames, Argon2id password hashes, `inference`/`owner` roles,
  active state, token-version invalidation, and audit timestamps. It does not use or
  modify another schema.
- Login now reads password hashes and roles from PostgreSQL. Every authenticated request
  rechecks active state, role, and token version, so password resets, role changes, and
  disabling an account revoke existing tokens immediately. JWT signing keys remain in
  Heroku config; plaintext passwords are not persisted.
- Prediction batches now reference the requesting database user. Idempotency keys are
  scoped per user with PostgreSQL 17 `UNIQUE NULLS NOT DISTINCT`, preventing one account
  from replaying another account's stored response. Prediction events, predictor payloads,
  probabilities, decisions, and observed outcomes remain in the monitoring datastore.
- The release command idempotently bootstraps existing config credentials only when the
  users do not exist. Interactive commands list/create/reset/enable/disable users and set
  roles without placing passwords in command arguments; the last active owner is protected.

Validation completed before the shared-database migration:

```text
Python 3.12 isolated CPU environment: 69 passed, 1 CUDA-only skipped
Ruff: database, deployment, and changed tests passed
PostgreSQL 17 clean release: 0001 + 0002 applied once; second run applied/seeded 0
PostgreSQL 17 hashes: 2/2 Argon2id, 0 plaintext matches
PostgreSQL 17 isolation: unrelated schema/table and row retained
Live before-snapshot: cdp_2026=9, ch0wn3rs_pt_prod=5, ctf_auth=1,
ctf_ctf=8, public=13; only migration 0001 was present
```

Manual Heroku release v13 applied `0002_auth_users`, bootstrapped two active users, and
seeded zero duplicate sample rows. Live checks passed for both roles, exact JWT TTL,
owner-only monitoring/outcomes, one user-attributed inference, both migration checksums,
two Argon2id hashes, and zero plaintext-password matches. The after-snapshot is
`cdp_2026=10`, `ch0wn3rs_pt_prod=5`, `ctf_auth=1`, `ctf_ctf=8`, and `public=13`; unrelated
schemas did not change. Release v14 removed `CDP_AUTH_USERNAME`, `CDP_AUTH_PASSWORD`,
`CDP_INFERENCE_USERNAME`, and `CDP_INFERENCE_PASSWORD`. Both PostgreSQL-backed logins and
readiness passed again after that restart. The JWT private/public keys remain configured.

## JWT authentication and role isolation on 2026-09-11

Branch: `feat/model-serving-monitoring`.

- Replaced HTTP Basic authentication with Ed25519-signed JWT access tokens. Login tokens
  have a fixed two-hour lifetime and validated issuer, audience, key ID, role, timestamps,
  subject, and unique token ID. The public verification key is available as JWKS; private
  signing material remains only in Heroku config.
- Added `inference` as the default role and `owner` as its privileged superset. Both roles
  can inspect the live model contract and run JSON/CSV predictions. Only `owner` can ingest
  observed outcomes or load the Dash monitoring routes. API routes accept bearer tokens,
  not cookies; a secure HTTP-only same-site token cookie is limited to Dash browser traffic.
- Added public login shells for the batch page and `/inference/`. The new single-record
  visual form generates numeric/categorical inputs from the active artifact's reference
  profiles and calls the same transactionally logged prediction API. It therefore requires
  no code change when the deployment config selects another supported model or parameters.
- Provisioned a separate inference account and matching Ed25519 pair without printing or
  committing secrets. The existing staging credential is now the owner account.
- Manually released CPU image v11 before the branch push. Live checks passed for login,
  external signature verification, exact 7,200-second TTL, bearer-only API enforcement,
  inference-role denial on outcomes/monitoring, owner inference, Dash layout/dependencies,
  one real prediction, logout, public pages, readiness, and absence of web errors.

Validation completed:

```text
Python 3.12 isolated environment: 65 passed, 1 CUDA-only skipped
Ruff: changed deployment/authentication files passed
JavaScript: shared authentication and both page scripts passed syntax checks
CPU web image: built successfully and ran as non-root user app
local container: JWT/JWKS, roles, API prediction, and Dash access passed
live Heroku v11: readiness and full JWT/role matrix passed; no web errors
```

## Serving and monitoring deployment on 2026-09-10

Branch: `feat/model-serving-monitoring`, based directly on
`feat/model_training_evaluation` at `bc41ac1`. The obsolete
`development/model_training.ipynb` is not included; the tracked training implementation
remains `etl_scripts/src/model_training_evaluation.py`.

- Deployed one authenticated Eco container app at
  `https://cdp-2026-credit-risk-4b94df7c43fb.herokuapp.com/`. FastAPI serves JSON/CSV
  batches and the simple upload frontend; Dash is mounted at `/monitor/`.
- Attached existing add-on `postgresql-tapered-63136` under `CDP_DATABASE_URL` and
  created only schema `cdp_2026`. Eight application tables plus the migration ledger exist.
  The approved 10,763-row CSV sample was imported idempotently. Structural before/after
  checks left unrelated schema table counts unchanged: `ch0wn3rs_pt_prod=5`,
  `ctf_auth=1`, `ctf_ctf=8`, and `public=11`.
- Added schema-fixed SQLAlchemy models, connectors, focused repositories, a PostgreSQL
  advisory-lock/checksum migration runner with frozen SQL snapshots, model registry, transactional prediction
  batches/events, observed outcomes, frozen reference profiles, monitoring aggregates,
  and configurable raw-record retention.
- Added `deployment_model_config.json`. It selects the local CUDA TPE winner, XGBoost,
  and records its fixed hyperparameters. The deployment trainer reuses the tracked
  chronological/temporal pipeline and uses all available local CPU threads. The ignored
  CPU retrain artifact is deterministic with SHA-256
  `e9619058075d2fb9bda293bbaa51018395053928a97013ae4c441b5f518e9a10`, threshold
  `0.09492067992687225`, and temporal OOF default F1 `0.2154255319148936`.
  This does not replace or reselect against the inspected holdout.
- The artifact loader verifies its hash, `[0, 1]` class order, prediction interface, and
  exact dependency versions. A config-driven build script supports every learned family
  with a CPU runtime, so changing the winner or parameters does not change serving code.
- Added strict atomic batch validation, idempotency-key conflict/replay semantics,
  initial Basic authentication (superseded by the JWT role boundary above), outcome
  ingestion, and protected aggregate-only dashboards.
  Monitoring computes feature/score PSI, missingness, unknown categories,
  predicted-default rate, mature outcome performance, and calibration; low-volume or
  single-class windows are explicitly `insufficient_data`.
- Added separate non-root web and release Docker images. The initial Heroku release ran
  the migration/sample command successfully and scaled exactly one Eco web dyno. Docker
  Manifest V2 Schema 2 is forced for registry compatibility.
- Added a branch-push deployment GitHub Action. It retrains, pushes, releases, and checks
  readiness for every branch. Secrets are stored in GitHub; the dedicated Heroku
  authorization lasts one year from this date. A free Heroku Scheduler job (`1341184`)
  runs the idempotent monitoring catch-up and retention command daily at 06:30 UTC; the
  monitoring Action remains available as a manual recovery path without a duplicate cron.

Validation completed:

```text
python -m pytest -q tests
63 passed, 1 skipped in 41.59s (CUDA-only skip in the CPU environment)

local artifact: 256 rows, finite [P(default), P(on-time)], max sum error 0
fresh PostgreSQL 17: migration 0001 applied once, reran idempotently, unrelated table retained
local Docker: release seeded 10,763 rows; web and release run as uid/gid 999 (app)
local container stack: health/auth/frontend/Dash/model/prediction/replay all passed
live: liveness 200, readiness 200, unauthenticated frontend 401
live authenticated: frontend 200, model 200, JSON prediction 200, Dash 200
live Dash: layout 200, dependencies 200, aggregate callback 200
live monitoring: seven catch-up windows complete; repeated window is replayed
Heroku Scheduler: daily Eco job 1341184 saved at 06:30 UTC, not paused
live restart: readiness returned to 200; prediction idempotency replay remained true
release idempotency: no migrations or sample rows applied on the second run
```

The deployed model remains **staging/demo only**. Feature snapshot timing and outcome
maturity are unresolved, the holdout has already been inspected, and sparse production
outcomes mean performance pages will initially show insufficient data. Model binaries,
record-level exports, local environments, and optimization databases remain ignored.

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
