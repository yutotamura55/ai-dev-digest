# ai-dev-digest

生成 AI の開発に関する公式の発信（各社のブログ、リリースノートなど）を集め、日本語の要約を日付ごとに読めるようにするサイトです。
いまは開発環境を用意した段階です。
動くのは、1 つのフィードから記事を集めて保存し、画面に一覧で表示するところまでです。
要約と複数の発信元への対応は [#2](https://github.com/yutotamura55/ai-dev-digest/issues/2)、GCP へのデプロイは [#3](https://github.com/yutotamura55/ai-dev-digest/issues/3) で作ります。

## 構成

| ディレクトリ | 中身 |
| --- | --- |
| `backend/` | Python 3.14。記事を集めるジョブ（`ai_dev_digest.job`）と、記事を返す API（FastAPI、`ai_dev_digest.api`）。依存は uv で管理する |
| `frontend/` | Next.js 16 の画面。API から記事を読み、日本時間の日付ごとに並べる |
| `tools/` | リポジトリ全体に使う検査の道具（Semgrep CE、zizmor、diff-cover）。アプリの依存とぶつからないよう分けている |
| `scripts/check.sh` | CI と同じ検査をすべて実行するコマンド |

データは Firestore に置きます。
開発ではエミュレーターを使うため、GCP のアカウントは要りません。

## 開発

Docker と Docker Compose が要ります。
すべてのコマンドをリポジトリのルートで実行します。
最初に、コンテナで作られるファイル（`.venv`、`node_modules` など）の所有者をホストの利用者にそろえるため、次を設定します。
設定していないと、compose はエラーで止まります。

```bash
export HOST_UID=$(id -u) HOST_GID=$(id -g)
```

### 検査を実行する

次のコマンドで、CI と同じ検査がコンテナの中で動きます。
依存が lockfile と合っていなければ、先に入れ直します。

```bash
git fetch origin
docker compose run --rm dev scripts/check.sh
```

| 対象 | 検査 |
| --- | --- |
| Python | Ruff（書式、lint、セキュリティの規則 `S`）、mypy（strict）、vulture（使われていないコード）、pytest とカバレッジ（Firestore エミュレーターを使うテストを含む）、pip-audit（依存の脆弱性） |
| Next.js | Prettier、ESLint、`tsc --noEmit`（strict）、Knip（使われていないファイル・依存）、Vitest とカバレッジ、npm audit |
| リポジトリ全体 | hadolint（Dockerfile）、ShellCheck、actionlint と zizmor（GitHub Actions の workflow）、Semgrep CE（セキュリティの静的解析）、diff-cover（`origin/main` から変えた行のカバレッジ） |

カバレッジは、全体の値が下限（`backend/pyproject.toml` の `fail_under`、`frontend/vitest.config.mts` の `thresholds`）を下回るか、変えた行のカバレッジが 80% を下回ると失敗します。
`git fetch origin` は、diff-cover が比べる `origin/main` を最新にするためです。

書式を自動で直すには、次を実行します。

```bash
docker compose run --rm dev sh -c "cd backend && uv run ruff format . && uv run ruff check --fix ."
docker compose run --rm -w /work/frontend dev npm run format
```

### 起動して動作を確かめる

API（<http://localhost:8000>）と画面（<http://localhost:3000>）を起動します。
Firestore エミュレーターも一緒に起動します。

```bash
docker compose up api web
```

別の端末で記事を集めます。
`.env.example` を `.env` に写すと、OpenAI のニュースのフィードから最新の 1 件を集めます。

```bash
cp .env.example .env
docker compose run --rm job
```

`saved 1 new article(s)` と出たら、<http://localhost:8000/articles> に記事が JSON で返り、<http://localhost:3000> に日付と題名が表示されます。
エミュレーターのデータは、コンテナを止めると消えます。
止めるには `docker compose down` を実行します。

### CI

`.github/workflows/ci.yml` は、PR と `main` への push のたびに、開発用のコンテナで `scripts/check.sh` を実行します。
`.github/workflows/dependency-review.yml` は、PR で加わる依存に既知の脆弱性があると失敗します。
依存の更新は Dependabot（`.github/dependabot.yml`）が毎週 PR にします。

## 開発の規則

エージェントと開発者が守る規則は [AGENTS.md](AGENTS.md) にあります。
脆弱性の報告の仕方は [SECURITY.md](SECURITY.md) にあります。

## ライセンス

[MIT](LICENSE)
