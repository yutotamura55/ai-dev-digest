provider "google" {
  project = var.project_id
  region  = var.region

  # 予算の API (billingbudgets) は、利用者の認証情報 (ADC) で呼ぶと、割り当てを使うプロジェクトの
  # 指定がないと 403 を返す (provider の google_billing_budget の文書の注意)。
  billing_project       = var.project_id
  user_project_override = true
}
