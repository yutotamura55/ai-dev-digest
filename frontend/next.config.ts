import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 本番用のイメージ (Dockerfile) に、実行に要るファイルだけを .next/standalone に集める。
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
