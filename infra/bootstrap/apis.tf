# プロジェクトで使う API を有効にする。
# serviceusage・cloudresourcemanager・storage・billingbudgets は、Terraform を動かす前に gcloud で
# 有効にしておく (README)。ここにも並べ、Terraform の管理に含める。
locals {
  services = toset([
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ])
}

resource "google_project_service" "enabled" {
  for_each = local.services

  service = each.value
  # Terraform の管理から外しても API は止めない。止めると、その API を使うリソースが動かなくなる。
  disable_on_destroy = false
}
