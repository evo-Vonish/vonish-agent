// ─── 补充搜索源 ───
// 来自 HOLLOW SearchAdapter 的 Wikipedia API / GitHub API / ArXiv XML 补充搜索

import type { RawSearchResult } from "../types/index.js";
import { httpClient } from "../utils/http-client.js";

// ─── Wikipedia 补充搜索 ───

/**
 * 搜索 Wikipedia，返回页面摘要
 */
export async function searchWikipedia(
  query: string,
  language = "en",
  limit = 5,
): Promise<RawSearchResult[]> {
  try {
    const params = new URLSearchParams({
      action: "query",
      list: "search",
      srsearch: query,
      format: "json",
      srlimit: String(limit),
      origin: "*",
    });

    const url = `https://${language}.wikipedia.org/w/api.php?${params}`;
    const resp = await httpClient.get(url, {
      timeout: 8000,
    });
    const data = JSON.parse(resp) as {
      query?: { search?: Array<{ title: string; snippet: string; pageid: number }> };
    };

    const results: RawSearchResult[] = [];
    const searches = data.query?.search || [];
    for (const item of searches) {
      const snippet = item.snippet.replace(/<\/?[^>]+(>|$)/g, "");
      results.push({
        title: item.title,
        url: `https://${language}.wikipedia.org/wiki/${encodeURIComponent(item.title.replace(/ /g, "_"))}`,
        content: snippet,
        engine: "wikipedia-api",
        score: 0.7, // Wikipedia API 结果自带高权威
        publishedDate: undefined,
      });
    }

    // 同时请求中文 Wikipedia
    if (language === "en") {
      const zhResults = await searchWikipedia(query, "zh", 3);
      results.push(...zhResults);
    }

    return results;
  } catch {
    return [];
  }
}

// ─── GitHub 补充搜索 ───

/**
 * 搜索 GitHub 仓库
 */
export async function searchGitHub(
  query: string,
  limit = 5,
): Promise<RawSearchResult[]> {
  try {
    const params = new URLSearchParams({
      q: query,
      per_page: String(limit),
      sort: "stars",
      order: "desc",
    });

    const url = `https://api.github.com/search/repositories?${params}`;
    const text = await httpClient.get(url, {
      timeout: 8000,
      headers: {
        Accept: "application/vnd.github.v3+json",
        "User-Agent": "hollow-search-core/1.0",
      },
    });

    const data = JSON.parse(text) as {
      items?: Array<{
        full_name: string;
        html_url: string;
        description: string | null;
        stargazers_count: number;
        language: string;
      }>;
    };

    return (data.items || []).map((item) => ({
      title: `${item.full_name} ⭐${item.stargazers_count}`,
      url: item.html_url,
      content: `${item.description || ""} (${item.language || "unknown"})`,
      engine: "github",
      score: 200 / (200 + item.stargazers_count) * 0.5 + 0.3, // 星数加权，顶天 0.8
    }));
  } catch {
    return [];
  }
}

// ─── ArXiv 补充搜索 ───

/**
 * 搜索 ArXiv 论文
 */
export async function searchArXiv(query: string, limit = 5): Promise<RawSearchResult[]> {
  try {
    const params = new URLSearchParams({
      search_query: `all:${encodeURIComponent(query)}`,
      start: "0",
      max_results: String(limit),
      sortBy: "relevance",
    });

    const url = `https://export.arxiv.org/api/query?${params}`;
    const xml = await httpClient.get(url, {
      timeout: 10000,
      headers: { Accept: "application/atom+xml" },
    });

    // 简单 XML 解析 — 提取 entry 元素
    const results: RawSearchResult[] = [];
    const entryPattern = /<entry>([\s\S]*?)<\/entry>/g;
    let match: RegExpExecArray | null;

    while ((match = entryPattern.exec(xml)) !== null) {
      const entry = match[1];
      const titleMatch = /<title[^>]*>([\s\S]*?)<\/title>/i.exec(entry);
      const idMatch = /<id[^>]*>([\s\S]*?)<\/id>/i.exec(entry);
      const summaryMatch = /<summary[^>]*>([\s\S]*?)<\/summary>/i.exec(entry);
      const publishedMatch = /<published[^>]*>([\s\S]*?)<\/published>/i.exec(entry);

      const title = titleMatch?.[1]?.trim().replace(/\s+/g, " ") || "Untitled";
      const id = idMatch?.[1]?.trim() || "";
      const summary = summaryMatch?.[1]?.trim().replace(/\s+/g, " ").substring(0, 500) || "";
      const published = publishedMatch?.[1]?.trim();

      results.push({
        title,
        url: id,
        content: summary,
        engine: "arxiv",
        score: 0.55,
        publishedDate: published,
      });
    }

    return results;
  } catch {
    return [];
  }
}

// ─── 统一补充搜索入口 ───

export interface SupplementOptions {
  query: string;
  language?: string;
  includeWikipedia?: boolean;
  includeGitHub?: boolean;
  includeArXiv?: boolean;
  limit?: number;
}

export async function runSupplementSearch(options: SupplementOptions): Promise<RawSearchResult[]> {
  const { query, language = "en", limit = 5 } = options;
  const includeWikipedia = options.includeWikipedia ?? true;
  const includeGitHub = options.includeGitHub ?? false;
  const includeArXiv = options.includeArXiv ?? false;

  const tasks: Promise<RawSearchResult[]>[] = [];

  if (includeWikipedia) {
    tasks.push(searchWikipedia(query, language, limit));
  }
  if (includeGitHub) {
    tasks.push(searchGitHub(query, limit));
  }
  if (includeArXiv) {
    tasks.push(searchArXiv(query, limit));
  }

  const allResults = await Promise.allSettled(tasks);
  const merged: RawSearchResult[] = [];

  for (const result of allResults) {
    if (result.status === "fulfilled") {
      merged.push(...result.value);
    }
  }

  return merged;
}
