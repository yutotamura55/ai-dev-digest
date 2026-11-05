# 本番用のイメージ。Cloud Run の画面のサービスに使う。
# Next.js の standalone 出力 (next.config.ts の output) で、実行に要るファイルだけを入れる。
# 構成は Next.js 公式の例 (examples/with-docker) に合わせた。
# ベースのイメージは、開発用の Dockerfile と同じ版を、タグとダイジェストの両方で固定する。

FROM node:24-trixie-slim@sha256:54f84b4cf8432b21aaffd5d3ce8d41e12cea0d10d33c09d2f3c9879d49d6b446 AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-trixie-slim@sha256:54f84b4cf8432b21aaffd5d3ce8d41e12cea0d10d33c09d2f3c9879d49d6b446 AS build
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# public/ は中身がなく Git で管理していないので、checkout にはない。実行用の段で写せるよう作っておく。
RUN mkdir -p public && npm run build

FROM node:24-trixie-slim@sha256:54f84b4cf8432b21aaffd5d3ce8d41e12cea0d10d33c09d2f3c9879d49d6b446
WORKDIR /app
# Cloud Run は待ち受けるポートを PORT で渡す (既定は 8080)。server.js は PORT と HOSTNAME を読む。
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=8080
# ベースのイメージにある node 利用者 (ID 1000) で動かす。名前でなく数値で指定する。
COPY --from=build --chown=1000:1000 /app/public ./public
COPY --from=build --chown=1000:1000 /app/.next/standalone ./
COPY --from=build --chown=1000:1000 /app/.next/static ./.next/static
USER 1000:1000
EXPOSE 8080
CMD ["node", "server.js"]
