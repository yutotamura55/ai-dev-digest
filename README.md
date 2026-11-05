# ai-dev-digest

生成 AI の開発に関する公式の発信（各社のブログ、リリースノートなど）を集め、日本語の要約を日付ごとに読めるようにするサイトです。
ジョブが 1 日 1 回、発信元の RSS から新着を集め、LLM（Claude）でモデル・API・料金・廃止予定に関わる記事を選び、日本語の要約を付けて保存します。
画面は、その日の記事をカードで並べ、カードを押すと詳細と原文へのリンクを表示します。
GCP へのデプロイは [#3](https://github.com/yutotamura55/ai-dev-digest/issues/3) で作ります。

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
4. 記事ごとに、記事ページの本文（取得できなければフィードの概要）を LLM に渡し、題名の訳、2〜3 文の要約、箇条書きの詳細を日本語で生成する。詳細の各項目には根拠になる本文の一文をそのまま書き写させ、その一文が本文に含まれない項目は保存せず、警告のログに出す（空白の連続の違いは許し、20 字より短い引用は根拠にしない）。
5. 原文の題名と URL、発信元、公開日時、収集日時（UTC）、収集日（日本時間）、スコアと一緒に Firestore の `articles` に保存する。記事の ID は URL から決まり、同じ記事は 1 件のまま。

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

`.github/workflows/ci.yml` は、PR と `main` への push のたびに、開発用のコンテナで `scripts/check.sh` を実行します。
`.github/workflows/dependency-review.yml` は、PR で加わる依存に既知の脆弱性があると失敗します。
依存の更新は Dependabot（`.github/dependabot.yml`）が毎週 PR にします。

## 開発の規則

エージェントと開発者が守る規則は [AGENTS.md](AGENTS.md) にあります。
脆弱性の報告の仕方は [SECURITY.md](SECURITY.md) にあります。

## ライセンス

[MIT](LICENSE)
