import Link from "next/link";

import { ArticleCard } from "@/components/ArticleCard";
import { type DayDigest, formatDateJa, shiftDate } from "@/digest/articles";

// 1 日分の記事の一覧と、前後の日への移動。今日かどうかは API が返した日付で決める。
export function DigestView({ digest }: { digest: DayDigest }) {
  const isToday = digest.date === digest.today;
  // 今日より先の日には記事がないので、次の日へのリンクは今日の手前まで出す。
  const hasNext = digest.date < digest.today;
  return (
    <>
      <h2>
        {formatDateJa(digest.date)}
        {isToday ? "（今日）" : ""}
      </h2>
      <nav className="day-nav" aria-label="日付の移動">
        <Link href={`/days/${shiftDate(digest.date, -1)}`}>← 前の日</Link>
        {!isToday && <Link href="/">今日</Link>}
        {hasNext && (
          <Link href={`/days/${shiftDate(digest.date, 1)}`}>次の日 →</Link>
        )}
      </nav>
      {/* 題名の訳・要約・詳細は LLM の生成なので、値は原文で確かめるよう促す (#20)。記事がない日にも出す。 */}
      <p className="notice" role="note">
        題名の訳、要約、詳細は
        LLM（Claude）が生成したものです。モデル名・料金・期日は原文で確かめてください。
      </p>
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
