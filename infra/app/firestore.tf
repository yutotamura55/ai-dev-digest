# 記事を置くデータベース。場所は作った後に変えられない。
resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # 消すとデータも消えるので、GCP の側でも Terraform の側でも消せないようにする。
  # Terraform の管理から外す (destroy する) と、データベースは残り、state からだけ消える。
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"
}
