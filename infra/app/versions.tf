terraform {
  # 2026-11-05 時点の最新。開発用のコンテナ (Dockerfile) と同じ版を使う。
  required_version = "~> 1.17.1"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.10"
    }
  }

  # state を置くバケット (<プロジェクト ID>-tfstate) は、scripts/terraform.sh が -backend-config で渡す。
  backend "gcs" {
    prefix = "app"
  }
}
