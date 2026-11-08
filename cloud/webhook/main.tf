terraform {
  required_version = ">= 1.5"
  required_providers {
    google = { source = "hashicorp/google", version = ">= 7.0, < 8.0" }
  }
}
locals {
  policy = jsondecode(file("${path.module}/../expiry/policy.json"))
  name   = "semester-jenkins-webhook"
}
provider "google" {
  project = local.policy.project
  region  = local.policy.region
}
variable "deploy_receiver" {
  type    = bool
  default = false
}
variable "image" {
  type    = string
  default = ""
}
variable "branch" {
  type    = string
  default = "ci/jenkins-lab-20261108"
}
resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}
data "google_compute_instance" "jenkins" {
  name = "semester-jenkins"
  zone = local.policy.zone
}
resource "google_service_account" "relay" {
  account_id   = local.name
  display_name = "Signature-validating GitHub webhook relay"
}
resource "google_secret_manager_secret" "shared" {
  secret_id = local.name
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_iam_member" "read" {
  secret_id = google_secret_manager_secret.shared.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.relay.email}"
}
resource "google_compute_subnetwork" "relay" {
  name          = local.name
  region        = local.policy.region
  network       = data.google_compute_instance.jenkins.network_interface[0].network
  ip_cidr_range = "10.81.1.0/26"
}
resource "google_compute_firewall" "relay" {
  name          = local.name
  network       = data.google_compute_instance.jenkins.network_interface[0].network
  source_ranges = [google_compute_subnetwork.relay.ip_cidr_range]
  target_tags   = ["semester-jenkins"]
  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
}
resource "google_cloud_run_v2_service" "relay" {
  count                = var.deploy_receiver ? 1 : 0
  name                 = local.name
  location             = local.policy.region
  deletion_protection  = false
  invoker_iam_disabled = true
  ingress              = "INGRESS_TRAFFIC_ALL"
  labels               = { purpose = "semester-lab", component = "jenkins-webhook", expires-on = substr(local.policy.expires_at, 0, 10) }
  template {
    service_account                  = google_service_account.relay.email
    timeout                          = "15s"
    max_instance_request_concurrency = 8
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = replace(data.google_compute_instance.jenkins.network_interface[0].network, "https://www.googleapis.com/compute/v1/", "")
        subnetwork = google_compute_subnetwork.relay.id
      }
    }
    containers {
      image = var.image
      resources {
        limits   = { cpu = "1", memory = "256Mi" }
        cpu_idle = true
      }
      env {
        name = "WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.shared.secret_id
            version = "1"
          }
        }
      }
      env {
        name  = "JENKINS_URL"
        value = "http://${data.google_compute_instance.jenkins.network_interface[0].network_ip}:8080"
      }
      env {
        name  = "EXPIRES_AT"
        value = local.policy.expires_at
      }
      env {
        name  = "BRANCHES"
        value = "${var.branch},master"
      }
      startup_probe {
        http_get { path = "/healthz" }
        period_seconds    = 5
        timeout_seconds   = 3
        failure_threshold = 24
      }
    }
  }
  depends_on = [google_project_service.run, google_secret_manager_secret_iam_member.read, google_compute_firewall.relay]
  lifecycle {
    precondition {
      condition     = timecmp(timestamp(), local.policy.expires_at) < 0
      error_message = "The lab has expired; do not recreate its public receiver."
    }
    precondition {
      condition     = can(regex("@sha256:[a-f0-9]{64}$", var.image))
      error_message = "Pin the receiver image by digest."
    }
  }
}
output "url" { value = try(google_cloud_run_v2_service.relay[0].uri, null) }
