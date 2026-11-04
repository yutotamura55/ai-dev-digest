import Link from "next/link";

import { ArticleCard } from "@/components/ArticleCard";
import { type DayDigest, formatDateJa, shiftDate } from "@/digest/articles";

// 1 日分の記事の一覧と、前後の日への移動。
export function DigestView({
  digest,
  isToday,
}: {
  digest: DayDigest;
  isToday: boolean;
}) {
  return (
    <>
      <h2>
        {formatDateJa(digest.date)}
        {isToday ? "（今日）" : ""}
      </h2>
      <nav className="day-nav" aria-label="日付の移動">
        <Link href={`/days/${shiftDate(digest.date, -1)}`}>← 前の日</Link>
        {!isToday && <Link href="/">今日</Link>}
        {!isToday && (
          <Link href={`/days/${shiftDate(digest.date, 1)}`}>次の日 →</Link>
        )}
      </nav>
      {digest.articles.length === 0 ? (
        <p>この日の記事はまだありません。</p>
      ) : (
        <div className="cards">
          {digest.articles.map((article) => (
            <ArticleCard key={article.url} article={article} />
          ))}
        </div>
      )}
    </>
  );
}
