// API (backend の /articles) が返す 1 日分の記事と、日付の扱い。

export type Article = {
  title: string;
  // 題名の日本語訳。古い記事では空。
  title_ja: string;
  url: string;
  source: string;
  published_at: string;
  fetched_at: string;
  fetched_date_jst: string;
  summary_ja: string;
  detail_ja: string[];
  score: number;
};

export type DayDigest = {
  // YYYY-MM-DD (日本時間)。today は API が決めた今日の日付。
  date: string;
  today: string;
  articles: Article[];
};

const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

// YYYY-MM-DD を UTC の Date にする。日付の計算と表示は UTC で行い、実行環境の時差の影響を受けない。
function parseDate(date: string): Date | null {
  const match = DATE_PATTERN.exec(date);
  if (!match) {
    return null;
  }
  const [, year, month, day] = match.map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  // 2 月 30 日のように繰り上がる日付は受け付けない。
  if (parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) {
    return null;
  }
  return parsed;
}

function toDateString(date: Date): string {
  return date.toISOString().slice(0, 10);
}

// URL の /days/YYYY-MM-DD に使える日付か。
export function isValidDate(date: string): boolean {
  return parseDate(date) !== null;
}

// 日付を days 日ずらす (負なら前)。月や年の境も越える。
export function shiftDate(date: string, days: number): string {
  const parsed = parseDate(date);
  if (parsed === null) {
    throw new Error(`invalid date: ${date}`);
  }
  parsed.setUTCDate(parsed.getUTCDate() + days);
  return toDateString(parsed);
}

const dateFormat = new Intl.DateTimeFormat("ja-JP", {
  timeZone: "UTC",
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "short",
});

// 見出し用の日付。例: 2026年11月4日(水)
export function formatDateJa(date: string): string {
  const parsed = parseDate(date);
  if (parsed === null) {
    throw new Error(`invalid date: ${date}`);
  }
  return dateFormat.format(parsed);
}

const timeFormat = new Intl.DateTimeFormat("ja-JP", {
  timeZone: "Asia/Tokyo",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

// 記事の公開日時を日本時間で短く表す。例: 11/3 18:00
export function formatTimeInTokyo(iso: string): string {
  return timeFormat.format(new Date(iso));
}

// カードの見出しに出す題名と、その下に小さく出す原文の題名。
// 日本語訳があれば訳を見出しにし、原文を添える。なければ原文だけを見出しにする。
export function cardTitles(article: Pick<Article, "title" | "title_ja">): {
  heading: string;
  original: string | null;
} {
  const translated = article.title_ja.trim();
  if (translated === "" || translated === article.title) {
    return { heading: article.title, original: null };
  }
  return { heading: translated, original: article.title };
}

// 原文へのリンクに添えるホスト名。URL として読めなければ URL をそのまま返す。
export function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

// API から 1 日分の記事を取得する。date を省略すると API が日本時間の今日を返す。
// 失敗したら例外を投げ、画面のエラー表示 (app/error.tsx) に任せる。
// apiBaseUrl にパスが付いていても (例: https://example.com/api) そのパスの下を読む。
export async function fetchDigest(
  apiBaseUrl: string,
  date?: string,
  fetcher: typeof fetch = fetch,
): Promise<DayDigest> {
  const base = `${apiBaseUrl.replace(/\/+$/, "")}/articles`;
  const url = date === undefined ? base : `${base}?date=${date}`;
  const response = await fetcher(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`the API returned ${response.status}`);
  }
  return (await response.json()) as DayDigest;
}
