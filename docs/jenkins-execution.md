# Jenkins execution evidence

The [unified Spanish report](../04_jenkins_report/INFORME_RESULTADOS_ES.md) embeds the selected screenshots and measured results. The later [GitHub webhook integration](github-webhook.md) uses 76 plugins in GCP and the separate job `credit-classification-github`. Its push/merge receipts live in `output/github-webhook/verification.json`; it does not change the source or trigger attribution of the historical builds recorded here.

The pipeline was exercised locally and on the Terraform-managed GCP Jenkins controller. This document records observed executions; the [Jenkins runbook](jenkins.md) supplies the reproducible setup and configuration steps. Vertex AI/AutoML training is a separate, approval-gated dashboard exercise described in the [GCP runbook](gcp-training.md).

## Source and environment

The original repository HEAD is `b5c51c7b92c99364cab1857ea1a972a5b838e79f`, branch `feat/bigquery-ingestion-pipeline`, upstream `git@github.com:03loveslollipop/cdp_2026.git`. The working changes were assembled into an isolated review Git snapshot, **`242e2edf71981a4ea10dd8bb8756d0b614c569b6`**, used by the final local and cloud builds. It contains the original tracked files plus the implementation and its five regression tests. The original working branch has not been committed, pushed or merged by this task.

Jenkins is **2.580.2**, Java 21, with 71 version-locked/checksum-verified plugins. Its Python 3.13 CPU environment includes the repository's serving and training test dependencies. The local controller uses the Compose named volume and loopback port 18081. The cloud controller uses project **`nb-core-dev-99d0`**, VM **`semester-jenkins`**, zone **`us-central1-a`**, an `e2-medium` machine, a 40 GB balanced persistent boot disk and the IAP tunnel at local port 18083. Runtime identity is `semester-jenkins@nb-core-dev-99d0.iam.gserviceaccount.com`; provisioning used `contact@02labs.me` under organization `02labs.me` (`408308144073`).

Cloud image: `us-central1-docker.pkg.dev/nb-core-dev-99d0/semester-jenkins/controller@sha256:d67038d4d8d975ae514ed8fa9e6b863f56ce469cda1bb4650c740844eeeda297`.

Terraform created the 16 infrastructure foundation resources and one controller. Before its first pipeline run, the empty controller was refreshed to include the corrected complete snapshot. Its final plan found no drift. The module replaces the boot-disk VM on startup-script/image updates, so future updates require preserving any needed Jenkins evidence first. Ordinary restarts preserve the Docker volume; the local restart was checked and retained its job and build history.

## Browser workflow and screenshots

Playwright sessions `semester-jenkins` and `semester-jenkins-cloud` were kept open across the whole workflow. Each numbered screenshot is an actual browser capture. Files are under `output/playwright/`; authentication state and passwords are kept separately in ignored owner-only runtime directories.

| Step | Action and observed evidence | Screenshot |
|---|---|---|
| 1 | Authenticated local Jenkins dashboard with the provisioned job | [01 — dashboard](../output/playwright/01-local-dashboard.png) |
| 2 | Clicked Build Now; console shows the SCM clone and running job | [02 — running console](../output/playwright/02-local-running-console.png) |
| 3 | Watched live Stage View while tests executed | [03 — running stages](../output/playwright/03-local-running-stages.png) |
| 4 | Opened the administrator approval form after the quality gate | [05 — initial approval form](../output/playwright/05-local-approval-form.png) |
| 5 | Verified a subsequent build's cause as Started by an SCM change | [08 — automatic trigger](../output/playwright/08-local-scm-triggered.png) |
| 6 | Inspected the actual polling log for the detected revision change | [09 — polling log](../output/playwright/09-local-polling-log.png) |
| 7 | Inspected the configured review branch and Jenkinsfile path | [13 — SCM configuration](../output/playwright/13-local-scm-configuration.png) |
| 8 | Reviewed the final build's pending approval, then clicked Approve model | [14 — final local approval](../output/playwright/14-local-final-approval.png) |
| 9 | Verified all 165 tests passed, zero failed and zero skipped | [16 — final local test report](../output/playwright/16-local-165-tests.png) |
| 10 | Verified the completed local stages and retained earlier run history | [17 — final local stages](../output/playwright/17-local-final-full-stage-view.png) |
| 11 | Checked received completion payloads, including build URL and commit | [18 — local completion receipts](../output/playwright/18-local-final-receipts.png) |
| 12 | Opened the GCP-hosted Jenkins dashboard through IAP | [19 — cloud Jenkins dashboard](../output/playwright/19-cloud-dashboard.png) |
| 13 | Started the first cloud job from the browser and watched its console | [20 — cloud running console](../output/playwright/20-cloud-running-console.png) |
| 14 | Captured the cloud job's stages during execution | [21 — cloud running stages](../output/playwright/21-cloud-running-stages.png) |

The cloud approval/completion evidence and verified run summary are recorded below. The screenshot index in `output/playwright/index.json` records capture timestamps and page URLs. Screenshots are local submission artifacts, excluded from Git; retain `output/` when sharing this report.

## Findings and corrections during the rehearsal

The first local build passed the original 160 tests and model gates, was approved by `admin`, then finished **UNSTABLE**: Jenkins had no root URL and notification delivery raised `KeyError: BUILD_URL`. This unsuccessful completion is preserved in its console and stage view; it is not counted as a successful notification. The controller now configures its URL and the notification code supports a relative URL fallback; a regression test exercises that fallback.

The next local builds verified successful delivery. Reviewing the saved test-report screenshot exposed a source-packaging gap: the added untracked regression test file had not entered the isolated snapshot, so the earlier Jenkins reports still contained 160 tests. The snapshot builder was corrected and its Git tree checked explicitly. The final local build (#5) includes and passes **165 tests**, including the five new tests for metric-gate failure/NaN handling, holdout-independent gating, missing Jenkins URL notification, mismatched holdout refusal, and reversed AutoML class order/duplicate prediction IDs. Earlier statements of 161 tests were incorrect and are superseded by the actual final JUnit counts.

The checkout result is explicitly stored as `GIT_COMMIT`, so final approval and notification receipts contain the actual snapshot commit. Approval artifacts are published before the input pause; a reviewer can open real metrics/charts while deciding. Raw per-record predictions and serialized models are excluded from Jenkins' public artifact list.

## Model evaluation and approval

For the final local run, temporal validation selected **random forest**. Its validation default F1 is **0.1871**, validation ROC-AUC **0.6650**, temporal F1 standard deviation **0.0292**, and seed F1 standard deviation **0.0110**. All four quality/stability checks passed. Evaluation uses seeds 42/43/44 and five chronological blocks; threshold/calibration and selection precede the 3,229-row holdout audit.

The frozen holdout gives accuracy **0.8250**, default-class F1 **0.1130**, default recall **0.3333**, ROC-AUC **0.6573** and average precision **0.0994**. These are measured lab results, not production-model certification. The [measured-results discussion](model-results.md) contains the full comparison, uncertainty, imbalance and stability analysis.

`admin` approved the final local build, and the receipt records its build URL and full snapshot hash. The authenticated completion receiver accepted a SUCCESS payload. Local build #5 was automatically triggered by SCM polling. That is direct evidence of the configured branch polling behavior; it is not evidence of a GitHub merge. Publish the implementation and select its real repository/branch in Jenkins before claiming remote merge-trigger activation.

## Logs and reproducibility

`output/jenkins-receipts/` contains each observed build's API metadata, console text, JUnit counts, aggregate model metrics, approval and notification payload where available. These receipts distinguish stage success, overall result, human approval and notification delivery. They contain no administrator password or webhook token.

Reproduce with the [local/Cloud IaC runbook](jenkins.md), or review the existing live controllers at <http://127.0.0.1:18081> and <http://127.0.0.1:18083> while the IAP tunnel remains open. The cloud notification receiver is available through the separate IAP tunnel at <http://127.0.0.1:18084>. Closing tunnels removes local access but does not stop the VM. The workspace-root inventory records the deployed resources and the training approval boundary.

## Verified execution summary

| Environment | Build | Overall result | Passed | Failed | Skipped | Started (UTC) | Duration (s, including approval wait) | Cause |
|---|---:|---|---:|---:|---:|---|---:|---|
| local | 1 | UNSTABLE | 160 | 0 | 0 | 2026-11-07T23:45:58.031000+00:00 | 155.04 | Started by user admin |
| local | 2 | SUCCESS | 160 | 0 | 0 | 2026-11-07T23:49:08.161000+00:00 | 193.82 | Started by an SCM change |
| local | 3 | SUCCESS | 160 | 0 | 0 | 2026-11-07T23:52:22.019000+00:00 | 167.14 | Started by an SCM change |
| local | 4 | SUCCESS | 160 | 0 | 0 | 2026-11-07T23:55:09.194000+00:00 | 154.53 | Started by an SCM change |
| local | 5 | SUCCESS | 165 | 0 | 0 | 2026-11-08T00:01:08.368000+00:00 | 193.02 | Started by an SCM change |
| cloud | 1 | SUCCESS | 165 | 0 | 0 | 2026-11-08T00:07:10.050000+00:00 | 247.3 | Started by user admin |

The final local #5 and cloud #1 builds both use snapshot `242e2edf71981a4ea10dd8bb8756d0b614c569b6`. Their selected-forest holdout accuracy, default F1, ROC-AUC and average precision match to numerical tolerance (1e-12). This establishes reproducibility for the tested image/data/protocol; it is not an AutoML comparison or a fresh external evaluation. The 13 warnings in each full suite are third-party deprecation/experimental-API warnings; no tests were skipped.

| Final cloud step | Screenshot |
|---|---|
| Administrator approval | [22-cloud-approval.png](../output/playwright/22-cloud-approval.png) |
| 165 passed; zero failures/skips | [23-cloud-165-tests.png](../output/playwright/23-cloud-165-tests.png) |
| All completed stages successful | [24-cloud-completed-stages.png](../output/playwright/24-cloud-completed-stages.png) |
| Cloud completion receiver accepted SUCCESS | [25-cloud-notification-delivered.png](../output/playwright/25-cloud-notification-delivered.png) |

![Final cloud stages](../output/playwright/24-cloud-completed-stages.png)

![Final cloud tests](../output/playwright/23-cloud-165-tests.png)

![Cloud completion receipt](../output/playwright/25-cloud-notification-delivered.png)

Machine-readable [summary](../output/jenkins-receipts/summary.json) and [screenshot index with UTC times, page URLs and SHA-256 checksums](../output/playwright/index.json). Both controller environments and the cloud IAP tunnels remain available for review. No Vertex AI or AutoML run was launched during these historical Jenkins checks. The later custom Vertex success and authorized AutoML submission are documented separately in [gcp-execution.md](gcp-execution.md).

## Actualización: todas las ramas y master (9/11/2026 JST)

Proyecto `credit-classification-branches`, origen Git sin filtro de ramas y Jenkinsfile compartido fijado en `045a2300caf63506fdc0dd4092d7a771a43a1aee`. Cada hijo usa githubPush(); escaneo del padre cada minuto. El usuario eligió master. El relay tiene BRANCHES=*; se mantiene el hook 708866067, TLS y HMAC. La configuración no modifica master ni su despliegue Heroku.

Push real a `ci/webhook-all-branches-20261109`, SHA `7cdc8211ad9974afa01d7e1e6d49273b13a4da77`, entrega `3852983580569370624` HTTP 200: build#5 SUCCESS, 160  tests, 0 fallos, causa GitHubPushCause. Las etapas completas de modelos fueron omitidas. Master#2 terminó SUCCESS con 160 tests, entrenamiento/gates, aprobación y notificación; su causa fue la indexación inicial. No se presenta como push a master. Administración del hook/API con `03loveslollipop`; el push de verificación registra `02loveslollipop` como emisor en GitHubPushCause.

Se corrigieron el chequeo de layouts antiguos y el uso de la cuota API; se conservan intentos fallidos/cancelados y se detuvo el backfill migratorio para limitar carga. Los recibos actuales están en output/github-webhook/all-branches/verification.json. No se afirma que todos los commits históricos pasaron tests. No se repitió AutoML ni se modificó el vencimiento del 13/11.

Jenkins corre en GCP VM `semester-jenkins`, `nb-core-dev-99d0`, zona `us-central1-a`. `localhost:18083` es el extremo del túnel IAP a `10.81.0.3:8080`; GitHub utiliza la URL HTTPS de Cloud Run. Capturas raíz51,57,48,56 y GCP54; índice con fechas y SHA-256.
