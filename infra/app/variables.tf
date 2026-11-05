variable "project_id" {
  type        = string
  description = "GCP のプロジェクト ID。scripts/terraform.sh が環境変数 GCP_PROJECT_ID から渡す。"
}

variable "region" {
  type        = string
  description = "リソースを置くリージョン。infra/bootstrap と同じにする。"
  default     = "asia-northeast1"
}

variable "llm_model" {
  type        = string
  description = "収集のジョブが選別と要約に使う Claude のモデル。null ならコードの既定値 (backend の llm.DEFAULT_MODEL) を使う。"
  default     = null
}

variable "max_articles_per_day" {
  type        = number
  description = "1 日 (日本時間) に保存する記事の上限。null ならコードの既定値 (backend の job.DEFAULT_LIMIT) を使う。"
  default     = null
}

variable "collect_schedule" {
  type        = string
  description = "収集のジョブを起動する時刻 (cron 形式、日本時間)。"
  default     = "0 7 * * *"
}
