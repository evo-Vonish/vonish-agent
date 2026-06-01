// ─── Agent 工具: web_fetch ───
// VonishAgent 调用的网页抓取+净化工具接口

const BASE = process.env.HOLLOW_SEARCH_URL || "http://127.0.0.1:3000";

export interface WebFetchInput {
  urls: string[];
  preset?: "fast" | "balanced" | "deep" | "ultra";
  purify?: boolean;
  purifyMode?: "conservative" | "balanced" | "aggressive";
  maxCharsPerPage?: number;
}

export interface WebFetchOutput {
  success: boolean;
  pages: Array<{
    url: string;
    title: string;
    text: string;
    markdown?: string;
    status: "success" | "partial" | "failed";
    error?: string;
    charCount: number;
    qualityScore?: number;
  }>;
  stats: {
    total: number;
    succeeded: number;
    failed: number;
    totalChars: number;
    totalMs: number;
  };
  error?: string;
}

export async function web_fetch(input: WebFetchInput): Promise<WebFetchOutput> {
  const t0 = Date.now();

  try {
    const resp = await fetch(`${BASE}/api/fetch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        urls: input.urls,
        preset: input.preset || "balanced",
        purify: input.purify !== false,
        purifyMode: input.purifyMode || "balanced",
        maxCharsPerPage: input.maxCharsPerPage || 100000,
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      return {
        success: false,
        pages: [],
        stats: { total: 0, succeeded: 0, failed: input.urls.length, totalChars: 0, totalMs: Date.now() - t0 },
        error: err.error || `HTTP ${resp.status}`,
      };
    }

    const data = await resp.json();
    return {
      success: true,
      pages: (data.pages || []).map((p: any) => ({
        url: p.url,
        title: p.title,
        text: p.text,
        markdown: p.markdown,
        status: p.status,
        error: p.error,
        charCount: p.charCount || (p.text || "").length,
        qualityScore: p.purifyResult?.qualityScore,
      })),
      stats: {
        total: data.stats?.total || 0,
        succeeded: data.stats?.succeeded || 0,
        failed: data.stats?.failed || 0,
        totalChars: data.stats?.totalChars || 0,
        totalMs: data.stats?.totalMs || (Date.now() - t0),
      },
    };
  } catch (err: any) {
    return {
      success: false,
      pages: [],
      stats: { total: 0, succeeded: 0, failed: input.urls.length, totalChars: 0, totalMs: Date.now() - t0 },
      error: err.message,
    };
  }
}
