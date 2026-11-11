terraform {
  required_version = ">= 1.5"
  required_providers {
    google = { source = "hashicorp/google", version = ">= 6.0, < 8.0" }
  }
}
locals {
  policy  = jsondecode(file("${path.module}/policy.json"))
  project = local.policy.project
  runner  = "semester-jenkins-expiry"
  trigger = "semester-expiry-trigger"
}
provider "google" {
  project = local.project
  region  = local.policy.region
}
resource "google_project_service" "api" {
  for_each           = toset(["cloudtasks.googleapis.com", "cloudbuild.googleapis.com", "cloudresourcemanager.googleapis.com"])
  service            = each.key
  disable_on_destroy = false
}
resource "google_service_account" "runner" {
  account_id   = local.runner
  display_name = "Jenkins lab expiry cleanup worker"
}
resource "google_service_account" "trigger" {
  account_id   = local.trigger
  display_name = "Jenkins lab expiry task dispatcher"
}
resource "google_project_iam_custom_role" "cleanup" {
  role_id = "semesterJenkinsCleanup"
  title   = "Temporary Jenkins lab cleanup"
  permissions = [
    "resourcemanager.projects.get", "serviceusage.services.use", "logging.logEntries.create",
    "compute.instances.get", "compute.instances.stop", "compute.instances.delete",
    "compute.disks.get", "compute.disks.delete", "compute.zoneOperations.get",
    "compute.regionOperations.get", "compute.globalOperations.get",
    "compute.firewalls.get", "compute.firewalls.delete",
    "compute.subnetworks.get", "compute.subnetworks.delete",
    "compute.networks.get", "compute.networks.delete",
    "artifactregistry.repositories.get", "artifactregistry.repositories.delete",
    "secretmanager.secrets.get", "secretmanager.secrets.delete",
    "iam.serviceAccounts.get", "iam.serviceAccounts.delete", "iam.roles.delete",
    "cloudtasks.queues.get", "cloudtasks.queues.delete",
    "run.services.get", "run.services.delete", "run.operations.get"
  ]
}
resource "google_project_iam_custom_role" "dispatch" {
  role_id     = "semesterJenkinsExpiryDispatch"
  title       = "Jenkins expiry stop and cleanup submission"
  permissions = ["cloudbuild.builds.create", "compute.instances.stop", "resourcemanager.projects.get", "serviceusage.services.use"]
}
resource "google_project_iam_member" "runner" {
  project = local.project
  role    = google_project_iam_custom_role.cleanup.name
  member  = "serviceAccount:${google_service_account.runner.email}"
  condition {
    title      = "expires-after-cleanup-retry-window"
    expression = "request.time < timestamp('${local.policy.authorization_expires_at}')"
  }
}
resource "google_project_iam_member" "trigger" {
  project = local.project
  role    = google_project_iam_custom_role.dispatch.name
  member  = "serviceAccount:${google_service_account.trigger.email}"
  condition {
    title      = "expires-after-cleanup-retry-window"
    expression = "request.time < timestamp('${local.policy.authorization_expires_at}')"
  }
}
resource "google_service_account_iam_member" "act_as" {
  service_account_id = google_service_account.runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.trigger.email}"
}
# Allows the last cleanup request to delete its own identity after deleting its
# temporary project roles. This binding disappears with that service account.
resource "google_service_account_iam_member" "self_delete" {
  service_account_id = google_service_account.runner.name
  role               = "roles/iam.serviceAccountAdmin"
  member             = "serviceAccount:${google_service_account.runner.email}"
  condition {
    title      = "self-cleanup-only-window"
    expression = "request.time < timestamp('${local.policy.authorization_expires_at}')"
  }
}
resource "google_cloud_tasks_queue" "expiry" {
  name     = local.policy.queue
  location = local.policy.region
  rate_limits {
    max_concurrent_dispatches = 1
    max_dispatches_per_second = 1
  }
  retry_config {
    max_attempts       = 10
    max_retry_duration = "86400s"
    min_backoff        = "60s"
    max_backoff        = "3600s"
    max_doublings      = 5
  }
  depends_on = [google_project_service.api]
}
output "queue" { value = google_cloud_tasks_queue.expiry.id }
output "expires_at" { value = local.policy.expires_at }
