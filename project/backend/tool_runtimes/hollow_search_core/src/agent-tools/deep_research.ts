// ─── Agent 工具: deep_research ───
// VonishAgent 调用的深度研究工具接口
// 完整管道: search → crawl → purify → evidence pack

const BASE = process.env.HOLLOW_SEARCH_URL || "http://127.0.0.1:3000";

export interface DeepResearchInput {
  query: string;
  mode?: "overview" | "scholar" | "dev" | "live" | "media" | "deep_dive";
  searchLimit?: number;
  crawlPreset?: "fast" | "balanced" | "deep" | "ultra";
  purifyMode?: "conservative" | "balanced" | "aggressive";
  maxEvidencePassages?: number;
  supplement?: boolean;
}

export interface DeepResearchOutput {
  success: boolean;
  query: string;
  mode: string;
  searchResults: number;
  crawledPages: number;
  purifiedPages: number;
  evidencePack?: {
    passages: Array<{
      text: string;
      sourceUrl: string;
      sourceTitle: string;
      score: number;
    }>;
    claims: Array<{
      text: string;
      sourceUrl: string;
      confidence: "high" | "medium" | "low";
    }>;
    gaps: Array<{
      description: string;
      severity: "critical" | "major" | "minor";
      category: string;
    }>;
    nextQueries: string[];
  };
  pages: Array<{
    url: string;
    title: string;
    markdown?: string;
    text: string;
    qualityScore?: number;
    status: string;
  }>;
  stats: {
    searchMs: number;
    crawlMs: number;
    totalMs: number;
    totalBytes: number;
    bandwidthMB: number;
  };
  error?: string;
  errorStage?: string;
}

export async function deep_research(input: DeepResearchInput): Promise<DeepResearchOutput> {
  const t0 = Date.now();

  try {
    const resp = await fetch(`${BASE}/api/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: input.query,
        mode: input.mode || "deep_dive",
        searchLimit: input.searchLimit || 15,
        crawlPreset: input.crawlPreset || "balanced",
        purifyMode: input.purifyMode || "balanced",
        maxEvidencePassages: input.maxEvidencePassages || 30,
        supplement: input.supplement !== false,
      }),
      // 长时间请求
      signal: AbortSignal.timeout?.(120_000),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      return {
        success: false,
        query: input.query,
        mode: input.mode || "deep_dive",
        searchResults: 0,
        crawledPages: 0,
        purifiedPages: 0,
        pages: [],
        stats: { searchMs: 0, crawlMs: 0, totalMs: Date.now() - t0, totalBytes: 0, bandwidthMB: 0 },
        error: err?.error?.message || err.error || `HTTP ${resp.status}`,
        errorStage: err?.stage,
      };
    }

    const data = await resp.json();
    const totalMs = Date.now() - t0;
    const totalBytes = data.totalBytes || 0;
    const bandwidthMB = totalBytes / (1024 * 1024);

    return {
      success: true,
      query: data.query,
      mode: data.mode,
      searchResults: (data.search?.results || []).length,
      crawledPages: (data.crawl?.pages || []).length,
      purifiedPages: (data.crawl?.pages || []).filter((p: any) => p.markdown).length,
      evidencePack: data.evidence
        ? {
            passages: (data.evidence.passages || []).map((ps: any) => ({
              text: ps.text,
              sourceUrl: ps.sourceUrl,
              sourceTitle: ps.sourceTitle,
              score: ps.score,
            })),
            claims: (data.evidence.claims || []).map((c: any) => ({
              text: c.text,
              sourceUrl: c.sourceUrl,
              confidence: c.confidence,
            })),
            gaps: (data.evidence.gaps || []).map((g: any) => ({
              description: g.description,
              severity: g.severity,
              category: g.category,
            })),
            nextQueries: data.evidence.nextQueries || [],
          }
        : undefined,
      pages: (data.crawl?.pages || []).map((p: any) => ({
        url: p.url,
        title: p.title,
        markdown: p.markdown,
        text: p.text,
        qualityScore: p.purifyResult?.qualityScore,
        status: p.status,
      })),
      stats: {
        searchMs: data.search?.tookMs || 0,
        crawlMs: data.crawl?.stats?.totalMs || 0,
        totalMs,
        totalBytes,
        bandwidthMB: Math.round(bandwidthMB * 100) / 100,
      },
    };
  } catch (err: any) {
    return {
      success: false,
      query: input.query,
      mode: input.mode || "deep_dive",
      searchResults: 0,
      crawledPages: 0,
      purifiedPages: 0,
      pages: [],
      stats: { searchMs: 0, crawlMs: 0, totalMs: Date.now() - t0, totalBytes: 0, bandwidthMB: 0 },
      error: err.name === "TimeoutError" ? "Research timed out after 120s" : err.message,
    };
  }
}
