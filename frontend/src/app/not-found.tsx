import Link from "next/link";

// 存在しないページ (例: 日付の形が違う /days/...) に表示する。
export default function NotFound() {
  return (
    <main>
      <h1>ai-dev-digest</h1>
      <p>ページが見つかりません。日付は /days/YYYY-MM-DD の形で指定します。</p>
      <Link href="/">今日の記事へ</Link>
    </main>
  );
}
