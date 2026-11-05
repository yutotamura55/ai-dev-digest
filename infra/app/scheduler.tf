# 毎日、収集のジョブを起動する。Cloud Run の API (jobs/<名前>:run) を OAuth のトークンで呼ぶ
# (Cloud Run の文書「Execute jobs on a schedule」の構成)。

resource "google_cloud_run_v2_job_iam_member" "scheduler_runs_collect" {
  name     = google_cloud_run_v2_job.collect.name
  location = google_cloud_run_v2_job.collect.location
  role     = "roles/run.invoker"
  member   = google_service_account.scheduler.member
}

resource "google_cloud_scheduler_job" "collect_daily" {
  name      = "ai-dev-digest-collect-daily"
  region    = var.region
  schedule  = var.collect_schedule
  time_zone = "Asia/Tokyo"
  # ジョブの起動を頼むだけで、終わりは待たない。
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.collect.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }

  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_runs_collect]
}
