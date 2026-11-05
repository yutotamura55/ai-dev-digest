# 収集のジョブが使う Claude API のキー。値 (バージョン) は Terraform の state に残さないよう、
# 利用者が gcloud で足す (README)。infra/app のジョブはこのシークレットの最新のバージョンを読む。
resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}
