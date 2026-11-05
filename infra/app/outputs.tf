output "web_url" {
  description = "画面の URL。"
  value       = module.web.uri
}

output "api_url" {
  description = "API の URL。"
  value       = module.api.uri
}

output "image_repository" {
  description = "本番用のイメージを置く場所。GitHub Actions はここに backend と web を push する。"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "project_number" {
  description = "プロジェクト番号。"
  value       = data.google_project.this.number
}
