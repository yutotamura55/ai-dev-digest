# GitHub Actions から GCP へ、サービスアカウントの鍵を作らずに認証する (Workload Identity Federation)。
# - github-planner：PR で infra/app の terraform plan を出す。読み取りだけ。
# - github-deployer：main へのマージで、イメージを push し、Cloud Run のイメージを更新する。
# Terraform の apply は GitHub Actions では行わず、利用者が手元で行う (README)。

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "ai-dev-digest"
  display_name                       = "ai-dev-digest"

  # このリポジトリの workflow が出した OIDC トークンだけを受け付ける。
  attribute_condition = join(" && ", [
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.repository_owner_id == '${var.github_repository_owner_id}'",
  ])
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    # 動いている workflow のファイルとブランチ (<所有者>/<名前>/.github/workflows/ci.yml@refs/heads/main)。
    "attribute.workflow_ref" = "assertion.workflow_ref"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "planner" {
  account_id   = "github-planner"
  display_name = "GitHub Actions (terraform plan)"
  description  = "PR で infra/app の terraform plan を出す。読み取りだけ。"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "deployer" {
  account_id   = "github-deployer"
  display_name = "GitHub Actions (deploy)"
  description  = "main へのマージで、イメージを push し、Cloud Run のイメージを更新する。"

  depends_on = [google_project_service.enabled]
}

# planner には、このリポジトリのどのブランチ・PR の workflow からもなれる。
resource "google_service_account_iam_member" "planner_from_github" {
  service_account_id = google_service_account.planner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

# deployer には、main ブランチで動く ci.yml の実行 (push と手動の実行) からだけなれる。
# PR の実行 (ci.yml@refs/pull/...) や、ほかの workflow のファイルからはなれない。
resource "google_service_account_iam_member" "deployer_from_github" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.workflow_ref/${var.github_repository}/.github/workflows/ci.yml@refs/heads/main"
}

resource "google_project_iam_member" "planner_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = google_service_account.planner.member
}

# plan は state を読むだけで、ロックを取らない (scripts/terraform.sh の plan-ci)。
resource "google_storage_bucket_iam_member" "planner_reads_state" {
  bucket = "${var.project_id}-tfstate"
  role   = "roles/storage.objectViewer"
  member = google_service_account.planner.member
}

# Cloud Run のサービスとジョブのイメージを更新する。実行に使うサービスアカウントとして振る舞う権限
# (iam.serviceAccountUser) と、イメージの push の権限は、infra/app で対象のリソースにだけ付ける。
resource "google_project_iam_member" "deployer_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = google_service_account.deployer.member
}
