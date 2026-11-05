# infra/bootstrap で作ったリソースを、名前で読む。infra/bootstrap を先に apply しておく。

data "google_project" "this" {
  project_id = var.project_id
}

data "google_service_account" "deployer" {
  account_id = "github-deployer"
}

data "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"
}
