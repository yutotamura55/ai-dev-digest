#!/usr/bin/env bash
# CI と同じ検査をすべて実行する。開発用のコンテナの中で動かす：
#   docker compose run --rm dev scripts/check.sh
# 依存が lockfile と合っていなければ先に入れ直し、検査はどれか 1 つでも失敗したら止まる。
set -euo pipefail
cd "$(dirname "$0")/.."

: "${FIRESTORE_EMULATOR_HOST:?run this in the dev container: docker compose run --rm dev scripts/check.sh}"

# PR で変更した行のカバレッジの下限 (%)。
DIFF_COVERAGE_FLOOR=80
# 変更した行を比べる相手。CI では fetch-depth: 0 で取得した origin/main になる。
COMPARE_BRANCH="${COMPARE_BRANCH:-origin/main}"

step() { printf '\n==> %s\n' "$*"; }

step "Install dependencies from the lockfiles"
scripts/setup.sh

step "Repository: Dockerfile, shell scripts, workflows"
hadolint Dockerfile backend/Dockerfile frontend/Dockerfile
shellcheck scripts/*.sh
actionlint
uv run --project tools --locked zizmor --offline .github/workflows

step "Repository: security static analysis (Semgrep CE)"
# 規則は Semgrep の公開の規則集から実行時に取得する。リポジトリには同梱しない。
uv run --project tools --locked semgrep scan --metrics=off --error --quiet \
  --config p/python --config p/typescript --config p/react --config p/nextjs \
  --config p/dockerfile --config p/github-actions --config p/terraform

step "Infrastructure (Terraform): format, validate, lint"
# GCP には接続しない。provider はロックファイルの版だけを取る。
mkdir -p "$TF_PLUGIN_CACHE_DIR"
terraform fmt -check -recursive -diff infra
for root in infra/bootstrap infra/app; do
  terraform -chdir="$root" init -backend=false -input=false -lockfile=readonly >/dev/null
  terraform -chdir="$root" validate -no-color
done
tflint --chdir=infra --recursive --config="$PWD/infra/.tflint.hcl"

step "Backend (Python): format, lint, types, unused code, tests"
(
  cd backend
  uv run --locked ruff format --check .
  uv run --locked ruff check .
  uv run --locked mypy
  uv run --locked vulture
  uv run --locked pytest -q --cov --cov-report=term --cov-report=xml:coverage.xml
)

step "Python dependency audit (backend and tools)"
# 自分自身 (ai-dev-digest) は PyPI にないため、lockfile から書き出した依存だけを監査する。
audit_lockfile() {
  local project="$1"
  shift
  local requirements
  requirements="$(mktemp)"
  uv export --project "$project" --locked --all-groups --no-emit-project --quiet \
    --output-file "$requirements"
  uv run --project backend --locked pip-audit --strict --disable-pip --require-hashes \
    --requirement "$requirements" "$@"
  rm -f "$requirements"
}
audit_lockfile backend
# Semgrep 1.183.0 は mcp==1.29.0 と opentelemetry-api~=1.37.0 を固定しており、tools の中では直せない
# (semgrep/semgrep#12018)。semgrep scan はこの 5 件の脆弱な処理を呼ばない (2026-11-04 に、
# scan の実行中に該当するクラスの生成と関数の呼び出しが 0 回であることを確かめた。ai-dev-digest#1)。
# Semgrep が固定を上げたら、除外を外す。ほかの脆弱性が見つかれば、これまでどおり失敗する。
audit_lockfile tools \
  --ignore-vuln CVE-2026-59951 \
  --ignore-vuln CVE-2026-116684 \
  --ignore-vuln CVE-2026-116685 \
  --ignore-vuln CVE-2026-116686 \
  --ignore-vuln CVE-2026-114603

step "Frontend (Next.js): format, lint, types, unused code, tests, audit"
(
  cd frontend
  npm run --silent check
  # 本番の依存は、勧告が 1 件でもあれば失敗にする。
  npm audit --omit=dev
  # 開発用の道具を含めると、ESLint 9 とそのプラグインが古い minimatch を使っており
  # moderate の勧告 (GHSA-g3hv-75wg-m249) が残る。Next.js の ESLint 設定が ESLint 10 に
  # 対応するまでは、開発用を含む監査は high 以上で失敗にする。
  npm audit --audit-level=high
)

step "Coverage of the changed lines (compared with ${COMPARE_BRANCH})"
if git rev-parse --verify --quiet "${COMPARE_BRANCH}^{commit}" > /dev/null; then
  uv run --project tools --locked diff-cover \
    backend/coverage.xml frontend/coverage/cobertura-coverage.xml \
    --compare-branch "$COMPARE_BRANCH" --fail-under "$DIFF_COVERAGE_FLOOR"
else
  echo "error: ${COMPARE_BRANCH} does not exist here; run 'git fetch origin' first" >&2
  exit 1
fi

step "All checks passed"
