output "namespace" {
  value = kubernetes_namespace_v1.leadscore.metadata[0].name
}

output "api_service_name" {
  value = kubernetes_service_v1.api.metadata[0].name
}

output "web_service_name" {
  value = kubernetes_service_v1.web.metadata[0].name
}
