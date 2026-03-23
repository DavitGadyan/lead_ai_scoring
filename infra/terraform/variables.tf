variable "namespace" {
  type        = string
  description = "Kubernetes namespace for the platform"
  default     = "leadscore"
}

variable "database_url" {
  type        = string
  description = "Runtime Postgres connection string"
  sensitive   = true
}

variable "openai_api_key" {
  type        = string
  description = "OpenAI API key for LangChain backend"
  sensitive   = true
}

variable "openai_model" {
  type        = string
  description = "OpenAI model for scoring explanations"
  default     = "gpt-4o-mini"
}

variable "openai_base_url" {
  type        = string
  description = "Optional OpenAI-compatible base URL"
  default     = ""
}

variable "api_image" {
  type        = string
  description = "Container image for the API"
  default     = "ghcr.io/your-org/leadscore-api:latest"
}

variable "web_image" {
  type        = string
  description = "Container image for the web app"
  default     = "ghcr.io/your-org/leadscore-web:latest"
}
