terraform {
  required_version = ">= 1.8.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.38"
    }
  }
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}

resource "kubernetes_namespace_v1" "leadscore" {
  metadata {
    name = var.namespace
    labels = {
      app = "leadscore"
    }
  }
}

resource "kubernetes_secret_v1" "runtime" {
  metadata {
    name      = "leadscore-secrets"
    namespace = kubernetes_namespace_v1.leadscore.metadata[0].name
  }

  string_data = {
    DATABASE_URL   = var.database_url
    OPENAI_API_KEY = var.openai_api_key
    OPENAI_MODEL   = var.openai_model
    OPENAI_BASE_URL = var.openai_base_url
  }
}

resource "kubernetes_deployment_v1" "api" {
  metadata {
    name      = "leadscore-api"
    namespace = kubernetes_namespace_v1.leadscore.metadata[0].name
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "leadscore-api"
      }
    }

    template {
      metadata {
        labels = {
          app = "leadscore-api"
        }
      }

      spec {
        container {
          name  = "api"
          image = var.api_image

          port {
            container_port = 8000
          }

          env {
            name = "APP_NAME"
            value = "LeadScore AI API"
          }

          env {
            name  = "LLM_ENABLED"
            value = "true"
          }

          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.runtime.metadata[0].name
                key  = "DATABASE_URL"
              }
            }
          }

          env {
            name = "OPENAI_API_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.runtime.metadata[0].name
                key  = "OPENAI_API_KEY"
              }
            }
          }

          env {
            name = "OPENAI_MODEL"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.runtime.metadata[0].name
                key  = "OPENAI_MODEL"
              }
            }
          }

          env {
            name = "OPENAI_BASE_URL"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.runtime.metadata[0].name
                key  = "OPENAI_BASE_URL"
              }
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "api" {
  metadata {
    name      = "leadscore-api"
    namespace = kubernetes_namespace_v1.leadscore.metadata[0].name
  }

  spec {
    selector = {
      app = "leadscore-api"
    }

    port {
      port        = 8000
      target_port = 8000
    }
  }
}

resource "kubernetes_deployment_v1" "web" {
  metadata {
    name      = "leadscore-web"
    namespace = kubernetes_namespace_v1.leadscore.metadata[0].name
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "leadscore-web"
      }
    }

    template {
      metadata {
        labels = {
          app = "leadscore-web"
        }
      }

      spec {
        container {
          name  = "web"
          image = var.web_image

          port {
            container_port = 3000
          }

          env {
            name  = "NEXT_PUBLIC_API_BASE_URL"
            value = "http://leadscore-api.${var.namespace}.svc.cluster.local:8000"
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "web" {
  metadata {
    name      = "leadscore-web"
    namespace = kubernetes_namespace_v1.leadscore.metadata[0].name
  }

  spec {
    selector = {
      app = "leadscore-web"
    }

    port {
      port        = 3000
      target_port = 3000
    }
  }
}
