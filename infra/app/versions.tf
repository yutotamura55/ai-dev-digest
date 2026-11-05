terraform {
  # 2026-11-05 時点の最新の 1.17.1 以上。Dependabot が開発用のコンテナ (Dockerfile) の Terraform を
  # 1.x の新しい版に上げても、この指定を変えずに動くよう、上限は 2.0.0 にする。
  required_version = ">= 1.17.1, < 2.0.0"

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
