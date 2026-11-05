# 本番用のイメージ (backend と web) を置く。無料枠 (0.5 GB) に収まるよう、古いイメージを消す。
# 1 版の大きさは backend が約 72 MB、web が約 94 MB (2026-11-05 に圧縮した大きさを測った)。
resource "google_artifact_registry_repository" "images" {
  repository_id = "ai-dev-digest"
  location      = var.region
  format        = "DOCKER"
  description   = "ai-dev-digest の本番用のイメージ"

  cleanup_policy_dry_run = false

  # 各イメージの新しい 2 版は残す。ふつうは、いま動いている版と、1 つ前に戻すための版になる。
  # push の後のデプロイ (Cloud Run の更新) が 2 回続けて失敗すると、動いている版が 3 番目に古くなり、
  # 1 日後に消える。その場合も動いているリビジョンは止まらないが、その版をレジストリから
  # デプロイし直せなくなる。デプロイの失敗は、その日のうちに直す。
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }

  # それ以外は、作ってから 1 日たったら消す。
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "1d"
    }
  }
}

# GitHub Actions の deployer が、この置き場にだけイメージを push できるようにする。
resource "google_artifact_registry_repository_iam_member" "deployer_pushes" {
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.writer"
  member     = data.google_service_account.deployer.member
}
