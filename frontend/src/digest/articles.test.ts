import { describe, expect, it } from "vitest";

import {
  type DayDigest,
  cardTitles,
  fetchDigest,
  formatDateJa,
  formatTimeInTokyo,
  hostnameOf,
  isValidDate,
  shiftDate,
} from "./articles";

describe("isValidDate", () => {
  it("accepts a real YYYY-MM-DD date", () => {
    expect(isValidDate("2026-11-04")).toBe(true);
    expect(isValidDate("2024-02-29")).toBe(true);
  });

  it("rejects other formats and impossible dates", () => {
    expect(isValidDate("2026-11-4")).toBe(false);
    expect(isValidDate("20261104")).toBe(false);
    expect(isValidDate("2026-02-30")).toBe(false);
    expect(isValidDate("2026-13-01")).toBe(false);
    expect(isValidDate("abc")).toBe(false);
  });
});

describe("shiftDate", () => {
  it("moves across month and year boundaries", () => {
    expect(shiftDate("2026-11-04", -1)).toBe("2026-11-03");
    expect(shiftDate("2026-11-30", 1)).toBe("2026-12-01");
    expect(shiftDate("2026-01-01", -1)).toBe("2025-12-31");
  });

  it("rejects an invalid date", () => {
    expect(() => shiftDate("2026-02-30", 1)).toThrow("invalid date");
  });
});

describe("formatDateJa", () => {
  it("formats the date with the weekday in Japanese", () => {
    expect(formatDateJa("2026-11-04")).toBe("2026年11月4日(水)");
  });

  it("rejects an invalid date", () => {
    expect(() => formatDateJa("nope")).toThrow("invalid date");
  });
});

describe("formatTimeInTokyo", () => {
  it("shows the publication time in Japan time", () => {
    // 2026-11-03 15:30 UTC は日本時間で 11 月 4 日 0:30。
    expect(formatTimeInTokyo("2026-11-03T15:30:00Z")).toBe("11/4 00:30");
  });
});

describe("cardTitles", () => {
  it("uses the translation as the heading and keeps the original below", () => {
    expect(
      cardTitles({ title: "New model", title_ja: "新しいモデル" }),
    ).toEqual({
      heading: "新しいモデル",
      original: "New model",
    });
  });

  it("falls back to the original title when the translation is empty or the same", () => {
    expect(cardTitles({ title: "New model", title_ja: " " })).toEqual({
      heading: "New model",
      original: null,
    });
    expect(cardTitles({ title: "Gemma 4", title_ja: "Gemma 4" })).toEqual({
      heading: "Gemma 4",
      original: null,
    });
  });
});

describe("hostnameOf", () => {
  it("returns the host of a URL and the input when it is not a URL", () => {
    expect(hostnameOf("https://example.com/news/1?x=1")).toBe("example.com");
    expect(hostnameOf("not a url")).toBe("not a url");
  });
});

describe("fetchDigest", () => {
  const digest: DayDigest = {
    date: "2026-11-04",
    today: "2026-11-04",
    articles: [],
  };

  it("asks the API for today when no date is given", async () => {
    const fetcher = async (input: RequestInfo | URL) => {
      expect(String(input)).toBe("http://api:8000/articles");
      return Response.json(digest);
    };

    await expect(
      fetchDigest("http://api:8000", undefined, fetcher as typeof fetch),
    ).resolves.toEqual(digest);
  });

  it("passes the date and keeps the path of the base URL", async () => {
    const fetcher = async (input: RequestInfo | URL) => {
      expect(String(input)).toBe(
        "https://example.com/api/articles?date=2026-11-03",
      );
      return Response.json(digest);
    };

    await expect(
      fetchDigest(
        "https://example.com/api/",
        "2026-11-03",
        fetcher as typeof fetch,
      ),
    ).resolves.toEqual(digest);
  });

  it("throws when the API fails", async () => {
    const fetcher = async () => new Response("", { status: 503 });

    await expect(
      fetchDigest("http://api:8000", undefined, fetcher as typeof fetch),
    ).rejects.toThrow("503");
  });
});
