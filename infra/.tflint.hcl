# 組み込みの規則だけを使う。プラグインの取得が要らないので、CI とコンテナで同じに動く。
# 規則の選び方は github-settings リポジトリと同じにした。
config {
  format = "compact"
}

rule "terraform_required_version" {
  enabled = true
}

rule "terraform_required_providers" {
  enabled = true
}

rule "terraform_naming_convention" {
  enabled = true
}

rule "terraform_documented_variables" {
  enabled = true
}

rule "terraform_documented_outputs" {
  enabled = true
}

rule "terraform_unused_declarations" {
  enabled = true
}
