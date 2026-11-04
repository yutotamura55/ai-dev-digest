import { describe, expect, it } from "vitest";

import { type Article, fetchArticles, groupByDate } from "./articles";

function article(overrides: Partial<Article>): Article {
  return {
    title: "Release",
    url: "https://example.com/news/1",
    source: "https://example.com/feed.xml",
    published_at: null,
    fetched_at: "2026-11-04T00:00:00Z",
    ...overrides,
  };
}

describe("groupByDate", () => {
  it("groups by the publication date in Japan time, newest first", () => {
    const groups = groupByDate([
      article({
        url: "https://example.com/a",
        published_at: "2026-11-02T10:00:00Z",
      }),
      // 2026-11-03 15:30 UTC は日本時間で 11 月 4 日。
      article({
        url: "https://example.com/b",
        published_at: "2026-11-03T15:30:00Z",
      }),
      article({
        url: "https://example.com/c",
        published_at: "2026-11-02T01:00:00Z",
      }),
    ]);

    expect(groups.map((g) => g.date)).toEqual(["2026-11-04", "2026-11-02"]);
    expect(groups[1].articles.map((a) => a.url)).toEqual([
      "https://example.com/a",
      "https://example.com/c",
    ]);
  });

  it("uses the fetch date when the publication date is missing", () => {
    const groups = groupByDate([
      article({ fetched_at: "2026-11-01T00:00:00Z" }),
    ]);

    expect(groups[0].date).toBe("2026-11-01");
  });
});

describe("fetchArticles", () => {
  it("returns the articles from the API", async () => {
    const body = [article({})];
    const fetcher = async (input: RequestInfo | URL) => {
      expect(String(input)).toBe("http://api:8000/articles");
      return Response.json(body);
    };

    await expect(
      fetchArticles("http://api:8000", fetcher as typeof fetch),
    ).resolves.toEqual(body);
  });

  it("keeps the path of the base URL", async () => {
    const fetcher = async (input: RequestInfo | URL) => {
      expect(String(input)).toBe("https://example.com/api/articles");
      return Response.json([]);
    };

    await expect(
      fetchArticles("https://example.com/api/", fetcher as typeof fetch),
    ).resolves.toEqual([]);
  });

  it("throws when the API fails", async () => {
    const fetcher = async () => new Response("", { status: 503 });

    await expect(
      fetchArticles("http://api:8000", fetcher as typeof fetch),
    ).rejects.toThrow("503");
  });
});
