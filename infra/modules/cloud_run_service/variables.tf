variable "name" {
  type        = string
  description = "サービスの名前。"
}

variable "region" {
  type        = string
  description = "サービスを置くリージョン。"
}

variable "service_account_email" {
  type        = string
  description = "サービスを動かすサービスアカウント。"
}

variable "image" {
  type        = string
  description = "最初に作るときのイメージ。その後のイメージは GitHub Actions が更新し、Terraform は変えない。"
}

variable "env" {
  type        = map(string)
  description = "コンテナに渡す環境変数。"
  default     = {}
}

variable "max_instance_count" {
  type        = number
  description = "インスタンスの最大数。アクセスが急に増えたときの費用の上限になる。"
  default     = 2
}
