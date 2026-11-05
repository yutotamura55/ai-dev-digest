# 本番用のイメージ。Cloud Run の API サービス (既定のコマンド) と、収集のジョブ
# (python -m ai_dev_digest.job。infra/app で指定する) に使う。
# ベースと道具のイメージは、開発用の Dockerfile と同じ版を、タグとダイジェストの両方で固定する。

FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.14-slim-trixie@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# 依存だけを先に入れ、ソースだけを変えたときにこの層を作り直さないようにする。
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
# 自分のパッケージは編集可能にせず venv に入れ、実行用のイメージには /src を持ち込まない。
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim-trixie@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966
RUN useradd --no-create-home --uid 10001 app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1
# 名前でなく数値で指定する。実行する側の環境に app という利用者がなくても、同じ ID で動く。
USER 10001:10001
# Cloud Run は待ち受けるポートを PORT で渡す (既定は 8080)。
CMD ["sh", "-c", "exec uvicorn ai_dev_digest.api:app --host 0.0.0.0 --port \"${PORT:-8080}\""]
