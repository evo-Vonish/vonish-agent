// ─── Agent 工具: web_search ───
// VonishAgent 调用的搜索工具接口

const BASE = process.env.HOLLOW_SEARCH_URL || "http://127.0.0.1:3000";

export interface WebSearchInput {
  query: string;
  mode?: "overview" | "scholar" | "dev" | "live" | "media" | "deep_dive";
  limit?: number;
  language?: string;
}

export interface WebSearchOutput {
  success: boolean;
  query: string;
  mode: string;
  results: Array<{
    title: string;
    url: string;
    cleanUrl: string;
    snippet: string;
    engine: string;
    score: number;
    domain: string;
    isAd: boolean;
    isSeoSpam: boolean;
  }>;
  stats: {
    total: number;
    tookMs: number;
    enginesUsed: string[];
    adsFiltered: number;
  };
  error?: string;
}

export async function web_search(input: WebSearchInput): Promise<WebSearchOutput> {
  const t0 = Date.now();

  try {
    const resp = await fetch(`${BASE}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: input.query,
        mode: input.mode || "overview",
        limit: input.limit || 10,
        language: input.language,
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      return {
        success: false,
        query: input.query,
        mode: input.mode || "overview",
        results: [],
        stats: { total: 0, tookMs: Date.now() - t0, enginesUsed: [], adsFiltered: 0 },
        error: err.error || `HTTP ${resp.status}`,
      };
    }

    const data = await resp.json();
    return {
      success: true,
      query: data.query,
      mode: data.mode,
      results: (data.results || []).map((r: any) => ({
        title: r.title,
        url: r.url,
        cleanUrl: r.cleanUrl,
        snippet: r.content,
        engine: r.engine,
        score: r.score,
        domain: r.domain,
        isAd: r.isAd || false,
        isSeoSpam: r.isSeoSpam || false,
      })),
      stats: {
        total: (data.results || []).length,
        tookMs: data.tookMs,
        enginesUsed: Object.keys(data.stats?.engineBreakdown || {}),
        adsFiltered: data.stats?.adsFiltered || 0,
      },
    };
  } catch (err: any) {
    return {
      success: false,
      query: input.query,
      mode: input.mode || "overview",
      results: [],
      stats: { total: 0, tookMs: Date.now() - t0, enginesUsed: [], adsFiltered: 0 },
      error: err.message,
    };
  }
}
