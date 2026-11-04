import { connection } from "next/server";
import { Suspense } from "react";

import { fetchArticles, groupByDate } from "@/digest/articles";

export default function Home() {
  return (
    <main>
      <h1>ai-dev-digest</h1>
      <p>生成 AI の開発に関する公式の発信を、日付ごとにまとめます。</p>
      <Suspense fallback={<p>読み込み中…</p>}>
        <ArticleList />
      </Suspense>
    </main>
  );
}

async function ArticleList() {
  // 記事はリクエストのたびに API から読む。環境変数もリクエストの時点で読む。
  await connection();
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const groups = groupByDate(await fetchArticles(apiBaseUrl));
  if (groups.length === 0) {
    return <p>まだ記事がありません。</p>;
  }
  return groups.map((group) => (
    <section key={group.date}>
      <h2>{group.date}</h2>
      <ul>
        {group.articles.map((article) => (
          <li key={article.url}>
            <a href={article.url} rel="noopener noreferrer">
              {article.title}
            </a>
          </li>
        ))}
      </ul>
    </section>
  ));
}
