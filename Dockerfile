# 開発用のイメージ。API・ジョブ・画面の起動と、scripts/check.sh の検査に使う。
# 本番用のイメージは #3 で別に作る。
# ベースと道具のイメージは、タグとダイジェストの両方で固定する。

FROM node:24-trixie-slim@sha256:54f84b4cf8432b21aaffd5d3ce8d41e12cea0d10d33c09d2f3c9879d49d6b446 AS node
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv
FROM hadolint/hadolint:v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d AS hadolint
FROM rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667 AS actionlint

FROM python:3.14-slim-trixie@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966

# git は diff-cover が比べるブランチを読むため、shellcheck は actionlint が run: を検査するために使う。
# DL3008（apt の版の固定）を外す理由：Debian の配布元は古い版を消すため、版を書くとビルドが
# やがて失敗する。ベースイメージをダイジェストで固定し、取り込む版の範囲を抑えている。
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git shellcheck \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=hadolint /bin/hadolint /usr/local/bin/hadolint
COPY --from=actionlint /usr/local/bin/actionlint /usr/local/bin/actionlint

# キャッシュは名前付きボリュームに置く。ボリュームは最初にこのディレクトリの権限を写すため、
# ホストの利用者として動かしても書き込めるようにしておく。
RUN mkdir /cache && chmod 1777 /cache
ENV XDG_CACHE_HOME=/cache \
    UV_CACHE_DIR=/cache/uv \
    npm_config_cache=/cache/npm \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    HOME=/tmp \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /work
