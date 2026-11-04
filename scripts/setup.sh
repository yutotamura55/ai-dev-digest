#!/usr/bin/env bash
# lockfile のとおりに依存を入れる。開発用のコンテナの中で動かす。
#   scripts/setup.sh          Python と Node.js の両方 (scripts/check.sh が呼ぶ)
#   scripts/setup.sh python   Python だけ (compose.yaml の api と job が呼ぶ)
#   scripts/setup.sh node     Node.js だけ (compose.yaml の web が呼ぶ)
# api と web は同時に起動するため、同じ依存を 2 つのコンテナが同時に入れないよう対象を分けている。
set -euo pipefail
cd "$(dirname "$0")/.."

target="${1:-all}"
case "$target" in
  all | python | node) ;;
  *)
    echo "usage: scripts/setup.sh [all|python|node]" >&2
    exit 2
    ;;
esac

if [[ "$target" != node ]]; then
  uv sync --project backend --locked --quiet
  uv sync --project tools --locked --quiet
fi

if [[ "$target" != python ]]; then
  # npm ci は node_modules を消して入れ直すため、package.json か lockfile が変わったときだけ実行する。
  # package.json だけを変えた場合も npm ci が走り、lockfile と食い違えば CI と同じく失敗する。
  npm_hash="$(cat frontend/package.json frontend/package-lock.json | sha256sum | cut -d' ' -f1)"
  if [[ "$(cat frontend/node_modules/.install-hash 2>/dev/null)" != "$npm_hash" ]]; then
    npm ci --prefix frontend --no-audit --no-fund
    echo "$npm_hash" > frontend/node_modules/.install-hash
  fi
fi
