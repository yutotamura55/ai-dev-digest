output "uri" {
  description = "サービスの URL。"
  value       = google_cloud_run_v2_service.this.uri
}
