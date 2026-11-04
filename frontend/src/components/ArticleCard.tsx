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
            {/* LLM が同じ文を 2 回返すことがあるので、番号を key にする。 */}
            {article.detail_ja.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
          <a href={article.url} target="_blank" rel="noopener noreferrer">
            原文を読む ({hostnameOf(article.url)})
          </a>
        </div>
      )}
    </article>
  );
}
