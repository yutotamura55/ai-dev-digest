# Cloud Run のサービス・ジョブと Cloud Scheduler が使うサービスアカウント。
# 部品ごとに分け、それぞれが要る権限だけを付ける。

resource "google_service_account" "api" {
  account_id   = "run-api"
  display_name = "Cloud Run: API"
  description  = "記事を Firestore から読んで返す。"
}

resource "google_service_account" "web" {
  account_id   = "run-web"
  display_name = "Cloud Run: 画面"
  description  = "API を呼んで画面を返す。GCP の権限は要らない。"
}

resource "google_service_account" "collect" {
  account_id   = "run-collect"
  display_name = "Cloud Run: 収集のジョブ"
  description  = "記事を集めて要約し、Firestore に保存する。"
}

resource "google_service_account" "scheduler" {
  account_id   = "scheduler-collect"
  display_name = "Cloud Scheduler: 収集のジョブの起動"
  description  = "毎日、収集のジョブを起動する。"
}

# Firestore の権限はプロジェクト単位でしか付けられない。API は読むだけ、ジョブは読み書きする。
resource "google_project_iam_member" "api_reads_firestore" {
  project = var.project_id
  role    = "roles/datastore.viewer"
  member  = google_service_account.api.member
}

resource "google_project_iam_member" "collect_writes_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = google_service_account.collect.member
}

resource "google_secret_manager_secret_iam_member" "collect_reads_api_key" {
  secret_id = data.google_secret_manager_secret.anthropic_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.collect.member
}

# GitHub Actions の deployer が、Cloud Run のイメージを更新するときに、実行用のサービスアカウントとして
# 新しいリビジョンを作れるようにする。このプロジェクトのほかのサービスアカウントには付けない。
resource "google_service_account_iam_member" "deployer_acts_as" {
  for_each = {
    api     = google_service_account.api.name
    web     = google_service_account.web.name
    collect = google_service_account.collect.name
  }

  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = data.google_service_account.deployer.member
}
