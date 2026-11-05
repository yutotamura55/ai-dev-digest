# 誰でも開ける Cloud Run のサービス。API と画面の 2 つで使う。
# リクエストがないときは 0 台になり、リクエストを処理している間だけ CPU の料金がかかる。

resource "google_cloud_run_v2_service" "this" {
  name     = var.name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instance_count
    }

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  lifecycle {
    # イメージは GitHub Actions が gcloud で更新する。そのとき gcloud が client と client_version も書く。
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
    ]
  }
}

# 画面も API も、読むのは公開している記事だけなので、ログインなしで開けるようにする。
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.this.name
  location = google_cloud_run_v2_service.this.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
