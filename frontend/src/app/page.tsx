import { connection } from "next/server";
import { Suspense } from "react";

import { DigestView } from "@/components/DigestView";
import { fetchDigest } from "@/digest/articles";

export default function Home() {
  return (
    <main>
      <h1>ai-dev-digest</h1>
      <p>
        生成 AI の開発に関する公式の発信を、日本語の要約で日付ごとにまとめます。
      </p>
      <Suspense fallback={<p>読み込み中…</p>}>
        <TodayDigest />
      </Suspense>
    </main>
  );
}

async function TodayDigest() {
  // 記事はリクエストのたびに API から読む。環境変数もリクエストの時点で読む。
  await connection();
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  // 今日の日付は API が日本時間で決める。画面とジョブで日付の区切りをそろえるため。
  const digest = await fetchDigest(apiBaseUrl);
  return <DigestView digest={digest} />;
}
