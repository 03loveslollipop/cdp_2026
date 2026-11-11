# Five-day automatic Jenkins cleanup

The user authorized automatic shutdown and teardown of this Jenkins lab after five days. The fixed policy is [cloud/expiry/policy.json](../cloud/expiry/policy.json).

**Stop deadline: 2026-11-13 02:41:05 UTC / 2026-11-13 11:41:05 JST.** This is 120 hours after policy creation. Restarts, Terraform plans and rerunning setup do not move it.

## What happens

1. A Cloud Tasks HTTP task sends an authenticated Compute Engine stop request for `semester-jenkins` at the deadline.
2. One minute later, another task starts the pinned cleanup worker in a temporary Cloud Build execution in `us-central1`.
3. The worker verifies its fixed project/location, the VM's lab labels and the disk's attachment before deleting the named workload resources. It treats resources already absent as successfully cleaned and waits for asynchronous deletion operations.
4. There are 49 cleanup submissions at 30-minute intervals over a 24-hour fallback window. These handle a build accepted by Cloud Tasks whose worker subsequently fails. HTTP delivery also has bounded retries. Once all workload resources are confirmed absent, the successful worker deletes the queue, cancelling remaining attempts.
5. The worker removes the temporary dispatcher identity, deletes its temporary custom roles and finally deletes its own identity using a separate self-resource IAM binding. Its permissions also expire automatically on 2026-11-15 02:41:05 UTC.

The first scheduled requests begin at the times above; completion depends on GCP task delivery, worker startup and API operation latency. The VM stop task is independent of the cleanup worker so compute can stop even if the worker needs a retry. Both operate entirely in GCP; the user's computer and Jenkins process need not remain online.

## Exact scope

Everything below is in **`nb-core-dev-99d0`**:

| Resource | Scheduled action |
|---|---|
| VM `semester-jenkins`, `us-central1-a` | Stop, then delete |
| Boot disk `semester-jenkins`, 40 GiB | Auto-delete with VM; explicit deletion also checks for leftovers |
| VM's ephemeral public IPv4 | Released when the VM is deleted; no reserved addresses were found in the project |
| Firewall `semester-jenkins-iap` | Delete |
| Subnet `semester-jenkins`, `us-central1` | Delete |
| VPC `semester-jenkins` | Delete after dependent resources |
| Artifact Registry repository `semester-jenkins`, `us-central1` | Delete the repository and all image versions/tags |
| Secrets `semester-jenkins-admin` and `semester-jenkins-notify` | Delete the secrets and their versions |
| Controller identity `semester-jenkins@nb-core-dev-99d0.iam.gserviceaccount.com` | Delete |
| Cleanup task queue and two temporary cleanup identities | Self-clean after the workload is absent |

Cloud projects, billing links, training-project resources, shared API enablement, Google-managed service agents and audit/build-history records are retained. These are not running Jenkins workloads. Deleted IAM principals/roles can leave inactive policy metadata, and IAM custom-role deletion has a soft-delete period. The worker cannot modify the project's IAM policy or delete projects. It has only the specified lifecycle/read/log permissions, with a time limit; its code accepts no resource-name or project override.

Cloud Jenkins history, workspace and artifacts on the boot disk will be removed at expiry. The already exported local screenshots, receipts, report files and local Docker rehearsal are retained. No additional backup bucket or snapshot is created that would keep accruing storage costs.

## Implementation and validation

The expiry infrastructure has its own Terraform state in `cloud/expiry`, separate from the original controller state in `cloud/jenkins`. Cloud Tasks, Cloud Build and Cloud Resource Manager APIs support scheduling, execution and the read-only IAM check. No service-account key is generated. Cloud Tasks uses a temporary dispatch identity with OAuth; it can submit the worker only through its explicit service-account-use binding. Worker logs go to Cloud Logging, avoiding a new Cloud Storage build-log bucket.

The runtime image is pinned by digest. Cloud Build argument chunks respect the API's 10,000-character per-argument limit. The official SDK image uses its bundled Python interpreter and SDK CA bundle; TLS certificate validation stays enabled.

Six local tests verify early-deletion refusal before any API request, read-only validation, refusal of another project, refusal of an unrelated VM/disk, idempotence and self-cleanup ordering, and the Cloud Build argument/runtime contract:

```bash
python3 -m pytest -q cloud/expiry/test_worker.py
```

The live smoke task uses the same worker with `--dry-run`. It inventories targets and tests the worker's required project permissions without issuing DELETE or stop requests. Deployment/validation receipts are recorded in the root `CLOUD_DEPLOYMENT_INVENTORY.md` and under the ignored `.jenkins/expiry-*` files. Earlier failed validation attempts are read-only and remain visible in Cloud Build history.

**Activation verified:** all 50 future tasks were read back on 2026-11-08 at 03:01:42 UTC. Their schedule times, OAuth identity, embedded expiry policy and payload hashes matched. Live read-only build `b774b2cd-309f-4c9c-a375-340f8674b34f` finished **SUCCESS**, found all nine targets and verified all 26 required project permissions. The future tasks contain the same tested worker/policy bytes. No resource has been stopped or deleted early.

## Reproduce or inspect

```bash
python3 cloud/expiry/schedule.py init  # prints an existing policy; never extends it
terraform -chdir=cloud/expiry init -input=false
python3 cloud/expiry/terraform.py plan -out=expiry.tfplan
python3 cloud/expiry/terraform.py apply expiry.tfplan
python3 cloud/expiry/schedule.py smoke
# After the read-only cloud execution succeeds:
python3 cloud/expiry/schedule.py install

gcloud tasks list --queue=semester-jenkins-expiry-20261113 \
  --location=us-central1 --project=nb-core-dev-99d0 --account=contact@02labs.me
gcloud builds list --region=us-central1 --project=nb-core-dev-99d0 \
  --account=contact@02labs.me --filter='tags:semester-jenkins-expiry'
```

Do not force-run the scheduled VM stop task as a test. The smoke command creates its own immediate read-only task. The cleanup worker itself refuses all deletions before the deadline, even if its execution is forced early.

The VM has `expires-on`, `lab-expiry-at` and `lab-expiry-queue` metadata/labels. These were applied in place, preserving VM ID `5997403931846771384` and its RUNNING state. Both provided Terraform wrappers reject normal plan/apply commands after expiry, and the controller has an additional Terraform expiry precondition. Explicit destroy commands remain available to reconcile state. Normal apply will not silently recreate the expired lab.

No further confirmation is required at the deadline: the user's five-day cleanup instruction authorizes the scheduled deletion. Any extension must be an explicit policy change and rescheduling action, not a side effect of restarting Jenkins or rerunning Terraform.

References: [authenticated Cloud Tasks](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks), [Cloud Build service accounts](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts), [Artifact Registry repository deletion](https://docs.cloud.google.com/artifact-registry/docs/reference/rest/v1/projects.locations.repositories/delete).

## Ampliación para el webhook GitHub

El 8/11 se incorporó el receptor Cloud Run `semester-jenkins-webhook`, su subred `10.81.1.0/26`, firewall privado, secreto y cuenta de servicio. El rol temporal del worker suma `run.services.get`, `run.services.delete` y `run.operations.get` (29 permisos en total). El servicio se elimina antes de liberar la red; si Direct VPC conserva temporalmente direcciones, los reintentos idempotentes continúan.

Las 49 tareas `cleanup-webhook-00` a `cleanup-webhook-48` reemplazan los payloads anteriores después de verificar el contenido FULL de todas las páginas. **No se cambió ninguna fecha**: la parada sigue en `2026-11-13T02:41:05Z` y la limpieza empieza a las `02:42:05Z`. Los logs locales de migración conservan las 49 retiradas; la verificación final vuelve a leer las nuevas. El Cloud Build de solo lectura `ce5426ac-f105-4027-87f8-636c16ddcf1d` terminó SUCCESS tras crear el receptor.

Reproducir comprobación: `python3 cloud/expiry/schedule.py verify`. La opción `retire-legacy` solo retira las tareas de la generación anterior cuando todas las nuevas coinciden con el worker y la política locales; no extiende el vencimiento. El hook en GitHub es un registro externo: tras retirar el receptor su URL queda inactiva, y puede eliminarse desde los ajustes del repositorio sin conservar credenciales GitHub en GCP.
