# Jenkins approval pipeline — reproducible lab and execution evidence

The exercise uses the actual `cdp_2026` repository. `Jenkinsfile` is a Declarative Pipeline whose first stage clones its SCM source into the job workspace. The local rehearsal uses an isolated Git snapshot; no existing branch is committed or pushed by setup. The cloud controller is provisioned by Terraform in the verified core IT project.

## 1. Build the local environment

From the `cdp_2026` directory:

```bash
python3 ci/prepare_local.py
python3 ci/jenkins/fetch_plugins.py
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

`prepare_local.py` generates private credentials under `.jenkins/secrets/` and a bare source snapshot under `.jenkins/source.git`. It copies tracked repository files plus this exercise's `ci`, `cloud`, `docs`, Jenkinsfile and Compose implementation, excluding credentials, generated plugin downloads, Terraform state and private local configuration. `.jenkins/source-receipt.json` records both the original commit and the review snapshot commit. The original branch remains `feat/bigquery-ingestion-pipeline`; its upstream is `git@github.com:03loveslollipop/cdp_2026.git`.

The image pins Jenkins 2.580.2/JDK 21 by digest, installs Python in `/opt/ci`, CPU PyTorch and the repository's serving/test dependencies. A lockfile pins every plugin and its official update-center SHA-256. The standard update host failed TLS in this environment; `fetch_plugins.py` resolves official compatible metadata from `archives.jenkins.io` and downloads artifacts from `repo.jenkins-ci.org`, verifying every checksum. Normal builds reuse the committed lock. Explicit plugin refresh: `python3 ci/jenkins/fetch_plugins.py --refresh-lock`.

Jenkins runs as the image's unprivileged `jenkins` user. It receives neither the Docker socket nor the host's credentials or live repository. The workspace is managed by Jenkins, so no `dir('..')` workaround is needed. Docker's `jenkins_home` named volume persists jobs, configuration, build history and artifacts across container restarts. Run `docker compose down` to stop; **do not add `-v` if you need to keep evidence**.

Local access:

| Service | URL | Persistent storage |
|---|---|---|
| Jenkins | `http://127.0.0.1:18081` | Compose-managed `jenkins_home` volume |
| Completion receiver | `http://127.0.0.1:18082` | `.jenkins/receipts/notifications.jsonl` |

The web interface requires `admin`; retrieve the generated password locally from `.jenkins/secrets/admin-password`. The parent secret directory is owner-only. Individual files are read-only and readable inside the unprivileged container. Do not include their contents in screenshots or reports. Anonymous access is disabled; CSRF protection remains enabled. Setup configures the required plugins and the pipeline job automatically, so the interactive setup wizard is unnecessary.

## 2. Inspect and run the job in the browser

Use the persistent Playwright skill session:

```bash
/home/zerotwo/.codex/skills/playwright/scripts/playwright_cli.sh --session semester-jenkins open http://127.0.0.1:18081 --headed
/home/zerotwo/.codex/skills/playwright/scripts/playwright_cli.sh --session semester-jenkins snapshot
```

Log in, capture the Jenkins dashboard, and open **credit-classification**. Open **Configure → Pipeline** to verify **Pipeline script from SCM**, Git source `file:///opt/source`, branch `*/ci-review`, script path `Jenkinsfile`. The read-only snapshot and `ALLOW_LOCAL_CHECKOUT` setting are specific to this private rehearsal.

Click **Build Now**, then open the numbered build. Watch **Stage View** and **Console Output**. Capture the running state while tests/training execute; do not substitute a static configuration page as proof of a running pipeline.

| Stage | What it verifies / produces |
|---|---|
| Clone repository | Deletes only this job's workspace, clones SCM and prints the exact commit |
| Validate structure | Required source/data/config/test files; chronological split; target/leakage exclusions |
| Repository tests | Entire `tests` suite; JUnit XML; a nonzero exit fails the pipeline |
| Train and evaluate | Real source extract; five model families, three seeds, five temporal blocks; frozen holdout |
| Quality and stability | Training-selected learned model passes versioned metric/stability policy |
| Approve model | Administrator-only human review, with a 20-minute timeout |
| Record approval | Approver, build URL and commit receipt |
| Post actions | JUnit report, completion webhook and aggregate evaluation/chart artifacts |

The whole pipeline has a 45-minute timeout and one executor; concurrent builds of the job are disabled. Build history retains ten runs. Model fitting uses two CPU threads. Quality thresholds in `ci/quality-gates.json` are exercise defaults, not a production model-risk policy: validation default F1 ≥ 0.10, validation ROC-AUC ≥ 0.50, temporal F1 standard deviation ≤ 0.15, seed F1 standard deviation ≤ 0.05. These checks use validation data; test scores do not tune selection or gate thresholds.

When the build pauses, inspect its console and evaluation artifacts. Default means `Pago_atiempo=0`, and probability columns follow `[P(default), P(on-time)]`. The majority-class dummy's high accuracy must not obscure its zero default recall/F1. Click the approval prompt and **Approve model** after reviewing the evidence. Capture the prompt, final successful stage view, console, test report and archived metrics. An aborted or timed-out approval stays unsuccessful and still enters the completion-notification path.

The notification receiver is an authenticated private local HTTP service. It accepts completion receipts without contacting email/chat providers. Jenkins archives its notification payload, while `.jenkins/receipts/notifications.jsonl` proves delivery. A delivery failure is visible and marks the build unstable. The payload describes the model workflow's result before transport, so a transport error can leave the payload as SUCCESS while the overall Jenkins result becomes UNSTABLE. Both must be reported.

## 3. Verify automatic triggering

The live GitHub job `credit-classification-github` now uses `githubPush()` and the signed Cloud Run receiver. The [GitHub webhook runbook](github-webhook.md) records actual push/merge verification on `ci/jenkins-lab-20261108`; master remains unchanged. The original `credit-classification` job and the historical execution evidence below remain SCM-polling evidence.

`pollSCM('H/2 * * * *')` polls the configured branch every two minutes at Jenkins' hashed minute offset. It is not a periodic unconditional build. The initial manual build registers the Jenkinsfile trigger; subsequent SCM changes should start a build with cause **Started by an SCM change**. Capture the polling log and the automatically started build, then review/approve it as above.

For this local review, update the isolated snapshot with `python3 ci/prepare_local.py` after an implementation change. Do not change the user's working branch or fabricate a GitHub merge. The root/snapshot commit receipt distinguishes the source repository's existing HEAD from the locally assembled review commit.

To activate real GitHub branch polling after these changes are published, edit **Configure → Pipeline → SCM** to the repository's HTTPS/SSH URL, add a Jenkins read credential if the repository is private, select the intended branch (`*/master` for the repository's existing release convention), and keep script path `Jenkinsfile`. Run once to register the trigger, then merge into that branch and verify the SCM cause in Jenkins. The bootstrap environment variables `JENKINS_REPOSITORY_URL` and `JENKINS_REPOSITORY_BRANCH` configure a newly created job; they do not overwrite an existing job on restart. Remote publication and GitHub merge-trigger evidence remain distinct from local snapshot polling.

## 4. Provision the GCP controller with Terraform

The organization/project identities were checked live before applying anything:

- Account: `contact@02labs.me`.
- Organization: `02labs.me`, ID `408308144073`.
- Core IT project: `nb-core-dev-99d0`, parent folder `351150074184`; billing enabled.
- Training remains in the separate risk project `nb-risk-ml-dev-99d0` and is launched through the dashboard after user approval.

The Terraform module is self-contained in `cloud/jenkins`; it does not import or modify the older landing-zone state in `../credit_payment/iac`. The authentication wrapper checks the project's organization and uses a short-lived gcloud access token for the specified account without writing it to a file or changing global gcloud settings.

```bash
cd cloud/jenkins
terraform init -input=false
terraform validate
python3 terraform.py plan -input=false -out=jenkins.tfplan
python3 terraform.py apply -input=false jenkins.tfplan
cd ../..
python3 ci/prepare_local.py
python3 cloud/jenkins/publish_controller.py
cd cloud/jenkins
python3 terraform.py plan -input=false -out=controller.tfplan
python3 terraform.py apply -input=false controller.tfplan
```

The first apply creates APIs, a dedicated VPC/subnet/IAP firewall, Artifact Registry, a dedicated service account and two Secret Manager containers. The publisher adds initial secret versions only if none exists, packages the tested local Jenkins image with the review Git snapshot, pushes it using a temporary isolated Docker credential directory, records its immutable digest and writes ignored Terraform variables. Secret values never enter Terraform state. The second apply creates the controller with the pinned image.

The small lab controller uses `e2-medium` (2 vCPU, 4 GB), a 40 GB balanced persistent boot disk and Debian 12 in `us-central1-a`. Startup installs Docker, retrieves just the two permitted secrets, pulls the pinned Jenkins image, and runs Jenkins plus its notification sidecar. The controller has no Vertex permissions. Its external address provides outbound connectivity; ingress permits TCP 8080/8081 only from the IAP range. OS Login and secure boot are enabled. There is no public Jenkins firewall rule.

Open an authenticated IAP tunnel and use the same browser verification sequence:

```bash
gcloud compute start-iap-tunnel semester-jenkins 8080 \
  --project=nb-core-dev-99d0 --zone=us-central1-a --account=contact@02labs.me \
  --local-host-port=127.0.0.1:18083
```

Then visit `http://127.0.0.1:18083`. An optional second tunnel maps remote 8081 to local 18084 for completion receipts. Only the current verified identity should access the tunnels. If a different user operates them, grant that user IAP tunnel access through the organization's normal policy; avoid anonymous access or broad firewall exceptions.

This uses a VM rather than Cloud Run. A continuously running Jenkins controller depends on persistent state, background polling and filesystem behavior; Cloud Run's storage mounts do not provide normal locking guarantees. A VM with a persistent disk is the chosen small-lab compromise. [Cloud Run billing/lifecycle](https://docs.cloud.google.com/run/docs/configuring/billing-settings), [NFS mount limitations](https://docs.cloud.google.com/run/docs/configuring/services/nfs-volume-mounts), [Cloud Storage mount limitations](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts).

## 5. Evidence, measured outcome and cleanup

The user has now authorized a fixed five-day expiry. See the [automatic cleanup policy](expiry-policy.md): VM stop at **2026-11-13 02:41:05 UTC**, followed by automatic removal of the dedicated Jenkins resources. The scheduling service operates in GCP independently of this workstation.

Screenshots and execution receipts are recorded in the companion `jenkins-execution.md` after the actual runs. Model charts and JUnit XML are downloadable from each completed Jenkins build. Local evidence is stored under `output/playwright/`, excluded from source control; preserve it with the report when sharing the submission. The workspace-root `CLOUD_DEPLOYMENT_INVENTORY.md` records actual resources, account, image digest, health and outstanding training approval.

To pause VM compute cost after documentation, stop only `semester-jenkins` in the core project. Persistent disk storage and stored images continue to incur charges. Reboot/startup preserves the boot-disk Docker volume. Terraform destroy removes this exercise's VM/disk, network, repository, service account and secrets; it deliberately leaves enabled APIs alone. Review `python3 terraform.py plan -destroy` before destructive cleanup, back up required Jenkins history, and obtain the user's cleanup instruction. Never delete a shared project, unrelated resources or the older landing-zone state.

In this minimal module, changing `metadata_startup_script` (including its pinned image) replaces the VM and boot disk. Back up Jenkins state before such updates once it contains evidence you need. During initial setup the empty controller was refreshed before its first pipeline run to include the complete review snapshot. Normal container/VM restarts preserve its named volume.

References: [Jenkins Docker image](https://github.com/jenkinsci/docker), [Pipeline syntax, post actions and polling](https://www.jenkins.io/doc/book/pipeline/syntax/), [Jenkins input step](https://www.jenkins.io/doc/pipeline/steps/pipeline-input-step/).
