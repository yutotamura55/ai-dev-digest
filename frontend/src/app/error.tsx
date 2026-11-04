"use client";

// 記事の取得などで例外が起きたときに、ページの代わりに表示する。
// retry は、ページのデータを取得し直して描き直す (Next.js 16 の error.js の仕様)。
export default function ErrorPage({
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  return (
    <main>
      <h1>ai-dev-digest</h1>
      <p>記事を読み込めませんでした。時間をおいて、もう一度お試しください。</p>
      <button type="button" onClick={() => retry()}>
        もう一度読み込む
      </button>
    </main>
  );
}
