#!/usr/bin/env bash
# infra/ の Terraform を実行する。開発用のコンテナの中で動かす。
#   docker compose run --rm infra bootstrap plan    計画を作り、infra/bootstrap/plan.tfplan に保存する
#   docker compose run --rm infra bootstrap apply   保存した計画を適用する (確認の入力はない)
#   docker compose run --rm infra app plan          infra/app も同じ
#   docker compose run --rm infra app apply
#   scripts/terraform.sh app plan-ci                CI で計画を表示する。state のロックを取らない
#   scripts/terraform.sh app check-ci               CI のデプロイの前に、未適用の変更がないことを確かめる
# 必要な環境変数:
#   GCP_PROJECT_ID         プロジェクト ID。state のバケットは <プロジェクト ID>-tfstate
#   GCP_BILLING_ACCOUNT    請求先アカウントの ID (bootstrap だけ)
#   GOOGLE_APPLICATION_CREDENTIALS  GCP の認証情報 (compose.yaml の infra と CI が設定する)
set -euo pipefail
cd "$(dirname "$0")/.."

usage() {
  echo "usage: scripts/terraform.sh <bootstrap|app> <plan|apply|plan-ci|check-ci>" >&2
  exit 2
}
[[ $# -eq 2 ]] || usage
stack="$1"
action="$2"
case "$stack" in bootstrap | app) ;; *) usage ;; esac
case "$action" in plan | apply | plan-ci | check-ci) ;; *) usage ;; esac

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID to the GCP project ID}"
export TF_VAR_project_id="$GCP_PROJECT_ID"
if [[ "$stack" == bootstrap ]]; then
  : "${GCP_BILLING_ACCOUNT:?set GCP_BILLING_ACCOUNT to the billing account ID}"
  export TF_VAR_billing_account="$GCP_BILLING_ACCOUNT"
fi
# プラグインのキャッシュは名前付きボリュームの中にあり、最初の実行ではまだない。
mkdir -p "$TF_PLUGIN_CACHE_DIR"

dir="infra/$stack"
plan_file="plan.tfplan"
terraform -chdir="$dir" init -input=false -lockfile=readonly \
  -backend-config="bucket=${GCP_PROJECT_ID}-tfstate" >/dev/null

case "$action" in
  plan)
    terraform -chdir="$dir" plan -input=false -out="$plan_file"
    echo "saved the plan to $dir/$plan_file. Apply it with: docker compose run --rm infra $stack apply" >&2
    ;;
  apply)
    if [[ ! -f "$dir/$plan_file" ]]; then
      echo "no saved plan: run 'docker compose run --rm infra $stack plan' first" >&2
      exit 1
    fi
    terraform -chdir="$dir" apply -input=false "$plan_file"
    rm -f "$dir/$plan_file"
    ;;
  plan-ci)
    terraform -chdir="$dir" plan -input=false -lock=false
    ;;
  check-ci)
    # -detailed-exitcode の終了コードは、0 が変更なし、1 がエラー、2 が変更あり。
    status=0
    terraform -chdir="$dir" plan -input=false -lock=false -detailed-exitcode || status=$?
    if [[ "$status" -eq 2 ]]; then
      echo "infra/$stack has changes that are not applied yet. Apply them first (README), then run CI on main again." >&2
      exit 1
    fi
    exit "$status"
    ;;
esac
