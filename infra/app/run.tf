# Cloud Run のサービス (API と画面) と、収集のジョブ。
# イメージは main へのマージで GitHub Actions が更新する (.github/workflows/ci.yml の deploy)。
# Terraform はイメージを変えず、最初に作るときだけ Google の見本のイメージを入れる。

locals {
  placeholder_service_image = "us-docker.pkg.dev/cloudrun/container/hello"
  placeholder_job_image     = "us-docker.pkg.dev/cloudrun/container/job"

  collect_overrides = {
    for name, value in {
      LLM_MODEL            = var.llm_model
      MAX_ARTICLES_PER_DAY = var.max_articles_per_day == null ? null : tostring(var.max_articles_per_day)
    } : name => value if value != null
  }
}

module "api" {
  source = "../modules/cloud_run_service"

  name                  = "ai-dev-digest-api"
  region                = var.region
  service_account_email = google_service_account.api.email
  image                 = local.placeholder_service_image
}

module "web" {
  source = "../modules/cloud_run_service"

  name                  = "ai-dev-digest-web"
  region                = var.region
  service_account_email = google_service_account.web.email
  image                 = local.placeholder_service_image
  env = {
    # 画面はサーバーの側で API を呼ぶ (frontend/src/digest/articles.ts)。
    API_BASE_URL = module.api.uri
  }
}

resource "google_cloud_run_v2_job" "collect" {
  name     = "ai-dev-digest-collect"
  location = var.region

  template {
    task_count = 1

    template {
      service_account = google_service_account.collect.email
      # 1 回の失敗で 1 日分を取りこぼさないよう、1 回だけやり直す。保存済みの記事は飛ばすので、
      # やり直しで同じ記事を 2 回保存することはない。
      max_retries = 1
      timeout     = "1800s"

      containers {
        image   = local.placeholder_job_image
        command = ["python", "-m", "ai_dev_digest.job"]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        # 指定した値だけを渡す。渡さない値は、イメージのコードの既定値になる。
        dynamic "env" {
          for_each = local.collect_overrides
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "ANTHROPIC_API_KEY"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.anthropic_api_key.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    # イメージは GitHub Actions が gcloud で更新する。そのとき gcloud が client と client_version も書く。
    ignore_changes = [
      client,
      client_version,
      template[0].template[0].containers[0].image,
    ]
  }

  # ジョブを作るとき、Cloud Run はシークレットを読めるかを確かめる。
  depends_on = [google_secret_manager_secret_iam_member.collect_reads_api_key]
}
