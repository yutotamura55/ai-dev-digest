// API (backend の /articles) が返す記事と、日付ごとにまとめる処理。

export type Article = {
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  fetched_at: string;
};

export type DayGroup = {
  // YYYY-MM-DD (日本時間)。
  date: string;
  articles: Article[];
};

const dateInTokyo = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Tokyo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

// 公開日時 (なければ収集日時) の日本時間の日付で記事をまとめ、新しい日付から並べる。
export function groupByDate(articles: Article[]): DayGroup[] {
  const groups = new Map<string, Article[]>();
  for (const article of articles) {
    const date = dateInTokyo.format(
      new Date(article.published_at ?? article.fetched_at),
    );
    groups.set(date, [...(groups.get(date) ?? []), article]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, items]) => ({ date, articles: items }));
}

// API から記事を取得する。失敗したら例外を投げ、画面のエラー表示に任せる。
export async function fetchArticles(
  apiBaseUrl: string,
  fetcher: typeof fetch = fetch,
): Promise<Article[]> {
  const response = await fetcher(new URL("/articles", apiBaseUrl), {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`the API returned ${response.status}`);
  }
  return (await response.json()) as Article[];
}
