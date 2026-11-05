output "project_number" {
  description = "プロジェクト番号。GitHub のリポジトリ変数 GCP_PROJECT_NUMBER に設定する。"
  value       = data.google_project.this.number
}

output "workload_identity_provider" {
  description = "GitHub Actions の認証 (google-github-actions/auth) に渡すプロバイダーの名前。"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "planner_service_account" {
  description = "PR で terraform plan を出すサービスアカウント。"
  value       = google_service_account.planner.email
}

output "deployer_service_account" {
  description = "main へのマージでデプロイするサービスアカウント。"
  value       = google_service_account.deployer.email
}
