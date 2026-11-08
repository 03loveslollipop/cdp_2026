terraform {
  required_version = ">= 1.5"
  required_providers {
    google = { source = "hashicorp/google", version = ">= 6.0, < 8.0" }
  }
}

variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "zone" {
  type    = string
  default = "us-central1-a"
}
variable "image" {
  type        = string
  description = "Artifact Registry image pinned by digest"
  default     = ""
}
variable "deploy_controller" {
  type    = bool
  default = false
}

provider "google" {
  project = var.project_id
  region  = var.region
}
locals {
  expiry = try(jsondecode(file("${path.module}/../expiry/policy.json")), null)
}

resource "google_project_service" "api" {
  for_each = toset([
    "compute.googleapis.com", "artifactregistry.googleapis.com", "secretmanager.googleapis.com",
    "iam.googleapis.com", "iap.googleapis.com", "logging.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "jenkins" {
  location      = var.region
  repository_id = "semester-jenkins"
  description   = "Credit classification Jenkins lab container"
  format        = "DOCKER"
  depends_on    = [google_project_service.api]
}

resource "google_secret_manager_secret" "secret" {
  for_each  = toset(["semester-jenkins-admin", "semester-jenkins-notify"])
  secret_id = each.key
  replication {
    auto {}
  }
  depends_on = [google_project_service.api]
}

resource "google_service_account" "controller" {
  account_id   = "semester-jenkins"
  display_name = "Semester Jenkins controller"
  depends_on   = [google_project_service.api]
}
resource "google_artifact_registry_repository_iam_member" "pull" {
  location   = var.region
  repository = google_artifact_registry_repository.jenkins.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.controller.email}"
}
resource "google_secret_manager_secret_iam_member" "read" {
  for_each  = google_secret_manager_secret.secret
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.controller.email}"
}

resource "google_compute_network" "lab" {
  name                    = "semester-jenkins"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.api]
}
resource "google_compute_subnetwork" "lab" {
  name          = "semester-jenkins"
  region        = var.region
  network       = google_compute_network.lab.id
  ip_cidr_range = "10.81.0.0/28"
}
resource "google_compute_firewall" "iap" {
  name          = "semester-jenkins-iap"
  network       = google_compute_network.lab.name
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["semester-jenkins"]
  allow {
    protocol = "tcp"
    ports    = ["8080", "8081"]
  }
}

resource "google_compute_instance" "controller" {
  count        = var.deploy_controller ? 1 : 0
  name         = "semester-jenkins"
  machine_type = "e2-medium"
  zone         = var.zone
  tags         = ["semester-jenkins"]
  labels = merge({ purpose = "semester-lab", component = "jenkins" }, local.expiry == null ? {} : {
    expires-on = substr(local.expiry.expires_at, 0, 10)
  })
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 40
      type  = "pd-balanced"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.lab.id
    # Egress for image pulls and Git polling. Ingress is IAP-only.
    access_config {}
  }
  service_account {
    email  = google_service_account.controller.email
    scopes = ["cloud-platform"]
  }
  shielded_instance_config { enable_secure_boot = true }
  metadata = merge({ enable-oslogin = "TRUE", block-project-ssh-keys = "TRUE" }, local.expiry == null ? {} : {
    lab-expiry-at    = local.expiry.expires_at
    lab-expiry-queue = local.expiry.queue
  })
  metadata_startup_script = templatefile("${path.module}/startup.sh.tftpl", {
    project  = var.project_id, image = var.image, region = var.region,
    receiver = filebase64("${path.module}/../../ci/jenkins/notification_server.py")
  })
  depends_on = [google_artifact_registry_repository_iam_member.pull,
  google_secret_manager_secret_iam_member.read]
  lifecycle {
    precondition {
      condition     = local.expiry == null ? true : timecmp(timestamp(), local.expiry.expires_at) < 0
      error_message = "This Jenkins lab has expired; do not recreate its controller."
    }
    precondition {
      condition     = !var.deploy_controller || can(regex("@sha256:[a-f0-9]{64}$", var.image))
      error_message = "Deploy the controller with an immutable published image digest."
    }
  }
}

output "repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.jenkins.repository_id}"
}
output "service_account" { value = google_service_account.controller.email }
output "instance" { value = try(google_compute_instance.controller[0].name, null) }
