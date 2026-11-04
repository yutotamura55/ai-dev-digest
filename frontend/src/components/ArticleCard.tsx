"use client";

import { useState } from "react";

import {
  type Article,
  cardTitles,
  formatTimeInTokyo,
  hostnameOf,
} from "@/digest/articles";

// 1 件の記事のカード。押すと同じページ内で広がり、詳細と原文へのリンクを表示する。
export function ArticleCard({ article }: { article: Article }) {
  const [open, setOpen] = useState(false);
  const toggle = () => setOpen((value) => !value);
  const titles = cardTitles(article);
  const originalLink = (
    <a href={article.url} target="_blank" rel="noopener noreferrer">
      原文を読む ({hostnameOf(article.url)})
    </a>
  );
  // 短い記事では詳細が空のことがある (#18)。そのときは開閉せず、原文へのリンクだけを出す。
  if (article.detail_ja.length === 0) {
    return (
      <article className="card">
        <div className="card-head card-head-static">
          <h3>{titles.heading}</h3>
          {titles.original !== null && (
            <p className="card-original-title">{titles.original}</p>
          )}
          <p className="card-meta">
            {article.source} · {formatTimeInTokyo(article.published_at)}
          </p>
          <p>{article.summary_ja}</p>
          <p className="card-link">{originalLink}</p>
        </div>
      </article>
    );
  }
  return (
    <article className={open ? "card card-open" : "card"}>
      {/* カード全体で開閉できるようにし、キーボードにはボタンで応える。 */}
      <div className="card-head" onClick={toggle}>
        <h3>{titles.heading}</h3>
        {titles.original !== null && (
          <p className="card-original-title">{titles.original}</p>
        )}
        <p className="card-meta">
          {article.source} · {formatTimeInTokyo(article.published_at)}
        </p>
        <p>{article.summary_ja}</p>
        <button
          type="button"
          className="card-toggle"
          aria-expanded={open}
          onClick={(event) => {
            event.stopPropagation();
            toggle();
          }}
        >
          {open ? "閉じる" : "詳細を見る"}
        </button>
      </div>
      {open && (
        <div className="card-detail">
          <ul>
            {/* 項目は保存時に重複を除いてあるので、文字列を key にできる。 */}
            {article.detail_ja.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {originalLink}
        </div>
      )}
    </article>
  );
}
