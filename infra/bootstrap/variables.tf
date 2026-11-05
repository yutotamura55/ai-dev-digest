variable "project_id" {
  type        = string
  description = "GCP のプロジェクト ID。scripts/terraform.sh が環境変数 GCP_PROJECT_ID から渡す。"
}

variable "region" {
  type        = string
  description = "リソースを置くリージョン。記事の読者が日本にいるため東京にする。"
  default     = "asia-northeast1"
}

variable "billing_account" {
  type        = string
  description = "予算のアラートを置く請求先アカウントの ID (XXXXXX-XXXXXX-XXXXXX)。scripts/terraform.sh が環境変数 GCP_BILLING_ACCOUNT から渡す。"
}

variable "budget_amount" {
  type        = number
  description = "1 か月の予算。超えそうなときと超えたときに、請求先アカウントの管理者にメールが届く。"
  default     = 1000
}

variable "budget_currency" {
  type        = string
  description = "予算の通貨。請求先アカウントの通貨と同じでないと、API がエラーを返す。"
  default     = "JPY"
}

variable "github_repository" {
  type        = string
  description = "GitHub Actions から認証を許すリポジトリ (所有者/名前)。"
  default     = "yutotamura55/ai-dev-digest"
}

variable "github_repository_id" {
  type        = string
  description = "上のリポジトリの数値の ID。名前を変えたり、同じ名前で作り直したりしたリポジトリに認証を渡さないよう、名前と合わせて確かめる。"
  default     = "1444522857"
}

variable "github_repository_owner_id" {
  type        = string
  description = "上のリポジトリの所有者の数値の ID。"
  default     = "45176609"
}
