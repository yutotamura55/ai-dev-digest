# ai-dev-digest

生成 AI の開発に関する公式の発信（各社のブログ、リリースノートなど）を集め、日本語の要約を日付ごとに読めるようにするサイトです。
ジョブが 1 日 1 回、発信元の RSS から新着を集め、LLM（Claude）でモデル・API・料金・廃止予定に関わる記事を選び、日本語の要約を付けて保存します。
画面は、その日の記事をカードで並べ、カードを押すと詳細と原文へのリンクを表示します。
本番は GCP の Cloud Run で動き、`main` へのマージで自動でデプロイします（「[本番の環境（GCP）](#本番の環境gcp)」）。

## 集める発信元

| 発信元 | フィード | 備考 |
| --- | --- | --- |
| OpenAI News | <https://openai.com/news/rss.xml> | 記事ページの取得はボットの判定で 403 になるため、フィードの概要だけで要約する |
| OpenAI Developers | <https://developers.openai.com/rss.xml> | |
| Claude Platform release notes | <https://platform.claude.com/docs/en/release-notes/feed.xml> | |
| Google DeepMind | <https://deepmind.google/blog/rss.xml> | |
| Google The Keyword（AI） | <https://blog.google/innovation-and-ai/technology/ai/rss/> | |
| Google Developers Blog | <https://developers.googleblog.com/feeds/posts/default/> | フィードの項目に公開日時がないため、記事ページの構造化データ（JSON-LD の `datePublished`）から補う |

発信元の一覧は `backend/src/ai_dev_digest/sources.py` にあります。
発信元ごとに、記事ページを取得して本文を補うか（`fetch_body`）、フィードにない公開日時を記事ページから補うか（`date_from_page`）を切り替えられます。
記事の URL にフラグメント（`overview#november-3-2026` のような `#` の後ろ）があれば、ページのその節だけを本文に使います。
Anthropic News には RSS がないため対象外です。

## 1 日の流れ

1. 各発信元のフィードを取得し、過去 48 時間に公開された項目を集める（実行の遅れや失敗で取りこぼさないよう、実行の間隔より長くしてある）。URL が同じ項目は 1 つにし、保存済みの記事は除く。発信元が 1 つ失敗しても、ほかの発信元の処理は続ける。
2. 候補をまとめて LLM に渡し、「モデル・API・料金・廃止予定のいずれかに関わるか」と 0〜100 のスコアを判定させる。
3. 関わるとされた記事をスコアの高い順に選ぶ。1 日（日本時間）に保存する記事は合計で最大 10 件（`MAX_ARTICLES_PER_DAY`）で、同じ日に 2 回実行しても超えない。
4. 記事ごとに、記事ページの本文（取得できなければフィードの概要）を LLM に渡し、題名の訳、2〜3 文の要約、箇条書きの詳細を日本語で生成する。詳細の各項目には根拠になる本文の一文をそのまま書き写させ、その一文が本文に含まれない項目は保存せず、警告のログに出す（空白の連続の違いだけは許す）。
5. 原文の題名と URL、発信元、公開日時、収集日時（UTC）、収集日（日本時間）、スコアと一緒に Firestore の `articles` に保存する。記事の ID は URL から決まり、同じ記事は 1 件のまま。

画面は、題名の訳・要約・詳細を LLM が生成したものであり、モデル名・料金・期日は原文で確かめるよう促す注意書きを、日付ごとのページに出します。

LLM の呼び出しは `backend/src/ai_dev_digest/llm.py` に閉じています。
モデルは環境変数 `LLM_MODEL` で切り替えます。
既定の `claude-sonnet-5-5` は入力 100 万トークンあたり 2 ドル、出力 10 ドルで、1 日 10 件なら月に数百円です（2026-11-04 に料金ページで確認）。
`claude-haiku-5-5`（0.10 ドル / 0.50 ドル）にすると月に数十円になります。

## 構成

| ディレクトリ | 中身 |
| --- | --- |
| `backend/` | Python 3.14。記事を集めて要約するジョブ（`ai_dev_digest.job`）と、日付ごとの記事を返す API（FastAPI、`ai_dev_digest.api`）。依存は uv で管理する |
| `frontend/` | Next.js 16 の画面。トップは今日の記事、`/days/YYYY-MM-DD` はその日の記事を表示する |
| `tools/` | リポジトリ全体に使う検査の道具（Semgrep CE、zizmor、diff-cover）。アプリの依存とぶつからないよう分けている |
| `infra/` | 本番の環境の Terraform。`bootstrap/` は最初に一度作る初期設定（API の有効化、GitHub Actions の認証、API キーの置き場、予算のアラート）、`app/` はアプリの部品（Firestore、Cloud Run、Cloud Scheduler など） |
| `backend/Dockerfile`、`frontend/Dockerfile` | 本番用のイメージ。ルートの `Dockerfile` は開発用 |
| `scripts/check.sh` | CI と同じ検査をすべて実行するコマンド |
| `scripts/terraform.sh` | `infra/` の Terraform を実行するコマンド |

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
| Terraform | `terraform fmt`、`terraform validate`、tflint（組み込みの規則）。GCP には接続しない |
| リポジトリ全体 | hadolint（Dockerfile）、ShellCheck、actionlint と zizmor（GitHub Actions の workflow）、Semgrep CE（セキュリティの静的解析。Terraform の規則を含む）、diff-cover（`origin/main` から変えた行のカバレッジ） |

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
`.env.example` を `.env` に写し、`ANTHROPIC_API_KEY` に Claude API のキーを書きます。
ジョブは Claude API を呼ぶため、1 回の実行に数十円かかることがあります。

```bash
export HOST_UID=$(id -u) HOST_GID=$(id -g)
cp .env.example .env
docker compose run --rm job
```

`saved N new article(s)` と出たら、<http://localhost:8000/articles> に今日（日本時間）の記事が JSON で返り、<http://localhost:3000> にカードで表示されます。
対象の記事がなければ `N` は 0 で、画面には「この日の記事はまだありません」と出ます。
エミュレーターのデータは、コンテナを止めると消えます。
止めるには `docker compose down` を実行します。

API は `GET /articles?date=YYYY-MM-DD` で、指定した日本時間の日付に集めた記事をスコアの高い順に返します。
`date` を省略すると今日の記事を返します。

### CI

`.github/workflows/ci.yml` は、次のジョブを実行します。

| ジョブ | 動くとき | すること |
| --- | --- | --- |
| Checks | PR と `main` への push | 開発用のコンテナで `scripts/check.sh` を実行する |
| Build images | PR | 本番用のイメージ（`backend/`、`frontend/`）を作れるか確かめる。push はしない |
| Terraform plan | このリポジトリのブランチから出た PR | `infra/app` の `terraform plan` を出す。GCP は読むだけ |
| Deploy | `main` への push と、`main` での手動の実行 | 本番用のイメージを作って push し、Cloud Run のサービスとジョブのイメージを更新する |

Terraform plan と Deploy は、リポジトリ変数 `GCP_PROJECT_ID` と `GCP_PROJECT_NUMBER` があるときだけ動きます。
GCP に構築する前は、この 2 つのジョブは飛ばされます。
`.github/workflows/dependency-review.yml` は、PR で加わる依存に既知の脆弱性があると失敗します。
依存の更新は Dependabot（`.github/dependabot.yml`）が毎週 PR にします。

## 本番の環境（GCP）

本番は GCP の東京リージョン（`asia-northeast1`）で動きます。
常時起動のサーバーは置かず、リクエストやジョブがあるときだけ動くサービスで組んでいます。

| 部品 | GCP のサービス | 名前 |
| --- | --- | --- |
| 画面 | Cloud Run のサービス | `ai-dev-digest-web` |
| API | Cloud Run のサービス | `ai-dev-digest-api` |
| 収集のジョブ | Cloud Run のジョブ | `ai-dev-digest-collect` |
| ジョブの起動（毎日 7:00、日本時間） | Cloud Scheduler | `ai-dev-digest-collect-daily` |
| 記事 | Firestore（ネイティブ モード） | `(default)` |
| 本番用のイメージ | Artifact Registry | `ai-dev-digest` |
| Claude API のキー | Secret Manager | `anthropic-api-key` |

作業の分担は次のとおりです。

- **GitHub Actions** は、PR で `terraform plan` を出し、`main` へのマージでイメージを更新します。GCP への認証は Workload Identity Federation で行い、サービスアカウントの鍵は作りません。
- **管理者** は、Terraform の apply を手元で実行します。apply にはプロジェクトの IAM を変える権限が要り、その権限を GitHub Actions に渡さないためです。インフラを変える PR をマージしたら、手元で apply します。

費用は、GCP の無料枠に収まる見込みです。
上限の代わりに、次の 2 つで費用を抑えます。

- Cloud Run の画面と API は、インスタンスを最大 2 台にしています（`infra/modules/cloud_run_service` の `max_instance_count`）。
- 1 か月の費用が 1,000 円の 50%・90%・100% に達したときと、月末に超える見込みになったときに、請求先アカウントの管理者にメールが届きます（`infra/bootstrap` の `budget_amount`）。予算は通知だけで、利用は止まりません。

### GCP に構築する

新しい GCP プロジェクトに、上の構成を作る手順です。
gcloud と Terraform はコンテナで動かすので、ホストに入れる必要はありません。

前もって、次を用意します。

- [Google Cloud コンソール](https://console.cloud.google.com/)で新しいプロジェクトを作り、請求先アカウントをリンクしておく。プロジェクト ID と請求先アカウントの ID を控える。
- Claude API のキー。

1. 端末で、以降のコマンドが使う値を設定します。`<>` の部分は控えた値に置き換えます。

   ```bash
   export HOST_UID=$(id -u) HOST_GID=$(id -g)
   export GCP_PROJECT_ID=<プロジェクト ID>
   export GCP_BILLING_ACCOUNT=<請求先アカウントの ID>
   ```

2. gcloud でログインします。
   ログインのコマンドは URL を表示します。
   その URL をブラウザで開いてアカウントを選び、表示されたコードを端末に貼ります。
   認証情報はホストの `~/.config/ai-dev-digest/gcloud` に保存されます。

   ```bash
   mkdir -p ~/.config/ai-dev-digest/gcloud && chmod 700 ~/.config/ai-dev-digest/gcloud
   docker compose run --rm gcloud auth login --no-launch-browser
   docker compose run --rm gcloud auth application-default login --no-launch-browser
   docker compose run --rm gcloud config set project "$GCP_PROJECT_ID"
   docker compose run --rm gcloud auth application-default set-quota-project "$GCP_PROJECT_ID"
   ```

3. Terraform を動かす前に要る API を有効にし、Terraform の state を置くバケットを作ります。

   ```bash
   docker compose run --rm gcloud services enable serviceusage.googleapis.com \
     cloudresourcemanager.googleapis.com storage.googleapis.com billingbudgets.googleapis.com
   docker compose run --rm gcloud storage buckets create "gs://${GCP_PROJECT_ID}-tfstate" \
     --location=asia-northeast1 --uniform-bucket-level-access --public-access-prevention
   docker compose run --rm gcloud storage buckets update "gs://${GCP_PROJECT_ID}-tfstate" --versioning
   ```

4. 初期設定（`infra/bootstrap`）を作ります。
   `plan` が変更の計画を表示して保存し、`apply` が保存した計画を確認の入力なしで適用します。
   `apply` の前に、計画の内容を確かめます。

   ```bash
   docker compose run --rm infra bootstrap plan
   docker compose run --rm infra bootstrap apply
   ```

   最後に表示される `project_number` を控えます。

5. Claude API のキーを Secret Manager に登録します。
   1 行目でキーを貼って Enter を押します。
   キーは画面に表示されず、Terraform の state にも残りません。

   ```bash
   read -rs ANTHROPIC_API_KEY
   printf %s "$ANTHROPIC_API_KEY" | docker compose run --rm -T gcloud secrets versions add anthropic-api-key --data-file=-
   unset ANTHROPIC_API_KEY
   ```

6. アプリの部品（`infra/app`）を作ります。

   ```bash
   docker compose run --rm infra app plan
   docker compose run --rm infra app apply
   ```

   この時点の画面と API は、Google の見本のページを返します。
   アプリのイメージは、次の手順のデプロイで入ります。

7. GitHub のリポジトリ変数に、プロジェクト ID と、手順 4 で控えたプロジェクト番号を設定します。

   ```bash
   gh variable set GCP_PROJECT_ID --body "$GCP_PROJECT_ID"
   gh variable set GCP_PROJECT_NUMBER --body <プロジェクト番号>
   ```

8. `main` で CI を手動で実行し、最初のデプロイをします。

   ```bash
   gh workflow run ci.yml --ref main
   ```

   Deploy のジョブが終わると、その実行の Summary に画面と API の URL が表示されます。
   画面の URL を開き、「ai-dev-digest」のページが表示されれば完了です。
   記事は、毎朝 7:00 のジョブの後に表示されます。

### インフラを変える

1. `infra/` を変える PR を作ると、CI の Terraform plan のジョブが `infra/app` の計画を表示します。
2. PR をマージした後、`main` の最新を手元に取り込んでから、手元で apply します。

   ```bash
   git switch main && git pull
   docker compose run --rm infra app plan
   docker compose run --rm infra app apply
   ```

`infra/bootstrap` の変更は CI では計画を出しません。
手元で `docker compose run --rm infra bootstrap plan` を実行して確かめます。

### 収集のジョブを手で実行する

毎朝の起動を待たずに記事を集めるときは、次を実行します。
`--wait` を付けると、ジョブが終わるまで待ちます。

```bash
docker compose run --rm gcloud run jobs execute ai-dev-digest-collect --region asia-northeast1 --wait
```

## 開発の規則

エージェントと開発者が守る規則は [AGENTS.md](AGENTS.md) にあります。
脆弱性の報告の仕方は [SECURITY.md](SECURITY.md) にあります。

## ライセンス

[MIT](LICENSE)
