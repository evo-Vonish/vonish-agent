// ─── hollow-search-core 统一 API 服务器 ───
// 组合 mini-searxng 搜索执行 + HOLLOW 搜索策略 + Ultra Crawler + content-purifier + Evidence Pack

import Fastify from "fastify";
import cors from "@fastify/cors";
import { EngineOrchestrator } from "../search/orchestrator.js";
import { ResultMerger } from "../search/merger.js";
import { CrawlManager } from "../crawler/crawl-manager.js";
import { purifyHtml } from "../purifier/index.js";
import { buildEvidencePack } from "../evidence/build-evidence-pack.js";
import { createDefaultEngines } from "../engines/index.js";
import {
  inferSearchMode,
  getIntentConfig,
} from "../search/intent-router.js";
import {
  rankResults,
} from "../search/result-ranker.js";
import {
  runSupplementSearch,
} from "../search/supplement.js";
import {
  cleanUrl,
  isValidUrl,
} from "../search/url-normalizer.js";

import type {
  SearchRequest,
  SearchResponse,
  SearchMode,
  RawSearchResult,
  CrawlRequest,
  CrawlResponse,
  CrawledPage,
  PurifyMode,
  ResearchRequest,
  ResearchResponse,
  EvidenceRequest,
  EvidencePack,
  HealthResponse,
} from "../types/index.js";

// ─── 初始化 ───

const PORT = parseInt(process.env.PORT || "3000", 10);
const VERSION = "1.0.0";
const startTime = Date.now();

const engines = createDefaultEngines();
const orchestrator = new EngineOrchestrator(engines);
const merger = new ResultMerger();
const crawlManager = new CrawlManager();

function sendRuntimeError(
  reply: any,
  status: number,
  code: string,
  message: string,
  detail: Record<string, unknown> = {},
  retryable = true,
) {
  return reply.status(status).send({
    success: false,
    error: {
      code,
      message,
      source: "hollow_search_core",
      retryable,
      detail,
    },
  });
}

const app = Fastify({
  logger: {
    level: process.env.LOG_LEVEL || "info",
    transport: process.env.NODE_ENV === "development"
      ? { target: "pino-pretty" }
      : undefined,
  },
});

await app.register(cors, { origin: true });

// ─── 健康检查 ───

app.get("/health", async (_req, reply) => {
  const health: HealthResponse = {
    status: "ok",
    version: VERSION,
    uptime: Math.floor((Date.now() - startTime) / 1000),
    engines: engines.map((e) => e.name),
    modes: ["overview", "scholar", "dev", "live", "media", "deep_dive"],
    presets: ["fast", "balanced", "deep", "ultra", "maximum", "unlimited"],
    purifyModes: ["conservative", "balanced", "aggressive"],
  };
  return reply.send(health);
});

// ─── 搜索端点 ───

app.post<{ Body: SearchRequest }>("/api/search", async (req, reply) => {
  const t0 = Date.now();
  const { query, mode: explicitMode, limit = 10, language } = req.body;

  if (!query || query.trim().length === 0) {
    return sendRuntimeError(reply, 400, "INVALID_QUERY", "query is required", {}, false);
  }

  try {
    // Step 1: 推断搜索意图
    const intent = inferSearchMode(query, explicitMode);

    // Step 2: 多引擎并行搜索
    const engineResults = await orchestrator.execute({
      query,
      engines: intent.engines,
      timeout: intent.timeoutMs,
      language: language || "auto",
      limit,
    });

    // Step 3: 合并去重
    const merged = merger.merge(engineResults);

    // 转换 merger 输出为 RawSearchResult 格式供 rankResults 使用
    const rawForRank: RawSearchResult[] = merged.map((r) => ({
      title: r.title,
      url: r.url,
      content: r.content || "",
      engine: r.engine,
      score: r.score,
      publishedDate: r.publishedDate,
      thumbnail: r.thumbnail,
    }));

    // Step 4: HOLLOW 搜索质量增强
    const ranked = rankResults(rawForRank, {
      preferFresh: intent.freshOnly,
      queryLanguage: language,
      preferAcademic: intent.preferAcademic,
      preferOfficial: intent.preferOfficial,
      preferRepos: intent.preferRepos,
    });

    // Step 5: 补充搜索
    let supplementResults = ranked;
    if (intent.supplement) {
      const supplements = await runSupplementSearch({
        query,
        language: language || "auto",
        includeWikipedia: true,
        includeGitHub: intent.preferRepos,
        includeArXiv: intent.preferAcademic,
        limit: 5,
      });
      supplementResults = [...ranked, ...rankResults(supplements, {
        preferAcademic: intent.preferAcademic,
        preferRepos: intent.preferRepos,
      })];
      // 重新排序 + 去重
      setCleanUrls(supplementResults);
    }

    // 截断
    const final = supplementResults.slice(0, intent.limit);

    // 统计
    const adsFiltered = ranked.filter((r) => r.isAd).length;
    const seoFiltered = ranked.filter((r) => r.isSeoSpam).length;
    const engineBreakdown: Record<string, number> = {};
    for (const r of final) {
      engineBreakdown[r.engine] = (engineBreakdown[r.engine] || 0) + 1;
    }

    const response: SearchResponse = {
      query,
      mode: intent.mode,
      results: final,
      stats: {
        totalResults: final.length,
        engineBreakdown,
        adsFiltered,
        seoFiltered,
        duplicatesRemoved: engineResults.reduce((s, e) => s + e.results.length, 0) - ranked.length,
      },
      tookMs: Date.now() - t0,
    };

    return reply.send(response);
  } catch (err: any) {
    app.log.error({ err }, "search failed");
    return sendRuntimeError(reply, 500, "SEARCH_FAILED", err.message, { stage: "search" });
  }
});

// ─── 抓取端点 ───

app.post<{ Body: CrawlRequest }>("/api/fetch", async (req, reply) => {
  const t0 = Date.now();
  const {
    urls,
    preset = "balanced",
    extraction = "hybrid",
    maxCharsPerPage = 100000,
    purify = true,
    purifyMode = "balanced",
  } = req.body;

  if (!urls || urls.length === 0) {
    return sendRuntimeError(reply, 400, "INVALID_URLS", "urls array is required", {}, false);
  }

  // 验证 URL
  const validUrls = urls.filter(isValidUrl).map(cleanUrl);
  if (validUrls.length === 0) {
    return sendRuntimeError(reply, 400, "INVALID_URLS", "no valid URLs provided", {}, false);
  }

  try {
    // Step 1: 爬取 (crawler 已内置 Readability 提取)
    const crawlResult = await crawlManager.crawl({
      urls: validUrls,
      preset,
      maxTextCharsPerPage: maxCharsPerPage,
    });

    // Step 2: 构建页面结果
    const pages: CrawledPage[] = [];
    for (const article of crawlResult.articles) {
      const isSuccess = article.status === "success";
      const isFailed = article.status === "failed" || article.status === "timeout" || article.status === "unreachable";

      const page: CrawledPage = {
        url: article.url,
        title: article.title || "",
        text: article.text || "",
        extractionMode: extraction,
        status: isSuccess ? "success" : isFailed ? "failed" : "partial",
        error: article.error,
        charCount: (article.text || "").length,
        fetchMs: article.durationMs || 0,
      };

      // Step 3: 净化 (仅当有 HTML 时可用；crawler 当前不返回 HTML，净化跳过)
      // 注意：mini-searxng crawler 已将 Readability 提取的文本作为 article.text；
      //       如需更深度净化（双阶段+Markdown），需要原始 HTML。
      //       未来可通过扩展 CrawlResult 添加 html 字段来实现。

      pages.push(page);
    }

    const totalCharsVal = pages.reduce((s, p) => s + p.charCount, 0);

    const response: CrawlResponse = {
      pages,
      stats: {
        total: crawlResult.stats.totalUrls,
        succeeded: crawlResult.stats.success,
        failed: crawlResult.stats.failed,
        partial: crawlResult.stats.timeout + crawlResult.stats.skipped,
        totalBytes: 0,
        totalChars: totalCharsVal,
        totalMs: Date.now() - t0,
      },
    };

    return reply.send(response);
  } catch (err: any) {
    app.log.error({ err }, "fetch failed");
    return sendRuntimeError(reply, 500, "FETCH_FAILED", err.message, { stage: "crawl" });
  }
});

// ─── 研究端点 (完整管道) ───

app.post<{ Body: ResearchRequest }>("/api/research", async (req, reply) => {
  const t0 = Date.now();
  const {
    query,
    mode: explicitMode,
    searchLimit = 10,
    crawlPreset = "balanced",
    extraction = "hybrid",
    purifyMode = "balanced",
    maxEvidencePassages = 30,
    supplement = true,
  } = req.body;

  if (!query || query.trim().length === 0) {
    return sendRuntimeError(reply, 400, "INVALID_QUERY", "query is required", {}, false);
  }

  try {
    // Stage 1: 搜索
    const s0 = Date.now();
    const intent = inferSearchMode(query, explicitMode);
    const engineResults = await orchestrator.execute({
      query,
      engines: intent.engines,
      timeout: intent.timeoutMs,
      limit: searchLimit,
      language: "auto",
    });
    const merged = merger.merge(engineResults);
    const rawForRank2: RawSearchResult[] = merged.map((r) => ({
      title: r.title,
      url: r.url,
      content: r.content || "",
      engine: r.engine,
      score: r.score,
      publishedDate: r.publishedDate,
      thumbnail: r.thumbnail,
    }));
    const ranked = rankResults(rawForRank2, {
      preferFresh: intent.freshOnly,
      preferAcademic: intent.preferAcademic,
      preferOfficial: intent.preferOfficial,
      preferRepos: intent.preferRepos,
    });

    // 补充搜索
    let allSearchResults = ranked;
    if (supplement && intent.supplement) {
      const supps = await runSupplementSearch({
        query,
        includeWikipedia: true,
        includeGitHub: intent.preferRepos,
        includeArXiv: intent.preferAcademic,
        limit: 5,
      });
      const suppRanked = rankResults(supps, {
        preferAcademic: intent.preferAcademic,
      });
      allSearchResults = [...ranked, ...suppRanked];
      setCleanUrls(allSearchResults);
    }
    const searchMs = Date.now() - s0;

    // Stage 2: 爬取
    const c0 = Date.now();
    const urls = allSearchResults.slice(0, Math.min(searchLimit, allSearchResults.length)).map((r) => r.cleanUrl);
    const crawlResult = await crawlManager.crawl({
      urls,
      preset: crawlPreset,
      maxTextCharsPerPage: 100000,
    });
    const crawlMs = Date.now() - c0;

    // Stage 3: 构建页面 (crawler 已内置 Readability，无需额外净化)
    const p0 = Date.now();
    const pages: CrawledPage[] = [];
    for (const article of crawlResult.articles) {
      const isSuccess = article.status === "success";
      const isFailed = article.status === "failed" || article.status === "timeout" || article.status === "unreachable";

      pages.push({
        url: article.url,
        title: article.title || "",
        text: article.text || "",
        extractionMode: extraction,
        status: isSuccess ? "success" : isFailed ? "failed" : "partial",
        error: article.error,
        charCount: (article.text || "").length,
        fetchMs: article.durationMs || 0,
      });
    }
    const purifyMs = Date.now() - p0;

    // Stage 4: Evidence Pack
    const e0 = Date.now();
    const successfulPages = pages.filter((p) => p.status === "success" && p.text.length > 200);
    let evidence: EvidencePack | undefined;
    if (successfulPages.length > 0) {
      const evidenceSources = successfulPages.map((p) => ({
        url: p.url,
        title: p.title,
        text: p.text,
      }));
      const evidenceResult = buildEvidencePack(
        query,
        evidenceSources as any,
        { maxPassages: maxEvidencePassages },
      );
      const pack = evidenceResult.pack;
      const estats = evidenceResult.stats;
      evidence = {
        query,
        passages: (pack.passages || []).map((ps) => ({
          text: ps.text,
          sourceUrl: "",
          sourceTitle: "",
          score: ps.score,
          charCount: ps.text.length,
        })),
        claims: (pack.claims || []).map((c) => ({
          text: c.claim,
          sourceUrl: "",
          confidence: c.confidence,
        })),
        gaps: (pack.gaps || []).map((g) => ({
          description: g,
          severity: "minor" as const,
          category: "coverage" as const,
        })),
        nextQueries: pack.nextQueries || [],
        sources: (pack.sources || []).map((s) => ({
          url: s.url,
          title: s.title,
          domain: s.domain,
          passageCount: 0,
          averageScore: 0,
        })),
        stats: {
          totalChunks: estats.totalChunks,
          scoredChunks: 0,
          exactDeduped: estats.exactDuplicatesRemoved,
          nearDeduped: estats.nearDuplicatesRemoved,
          selectedPassages: pack.passages.length,
          claimsFound: pack.claims.length,
          gapsIdentified: pack.gaps?.length || 0,
          totalSources: pack.sources.length,
          processingMs: estats.processingTimeMs,
        },
      };
    }
    const evidenceMs = Date.now() - e0;

    const totalMs = Date.now() - t0;
    const totalBytes = pages.reduce((s, p) => s + (p.charCount || 0), 0);

    const response: ResearchResponse = {
      query,
      mode: intent.mode,
      search: {
        results: allSearchResults.slice(0, searchLimit),
        tookMs: searchMs,
      },
      crawl: {
        pages,
        stats: {
          total: crawlResult.stats.totalUrls,
          succeeded: crawlResult.stats.success,
          failed: crawlResult.stats.failed,
          partial: crawlResult.stats.timeout + crawlResult.stats.skipped,
          totalBytes: 0,
          totalChars: pages.reduce((s, p) => s + p.charCount, 0),
          totalMs: crawlMs,
        },
      },
      evidence,
      totalMs,
      totalBytes,
    };

    app.log.info({
      query,
      mode: intent.mode,
      pages: pages.length,
      evidencePassages: evidence?.passages?.length || 0,
      totalMs,
      totalBytes,
    }, "research completed");

    return reply.send(response);
  } catch (err: any) {
    app.log.error({ err }, "research failed");
    return sendRuntimeError(reply, 500, "RESEARCH_FAILED", err.message, { stage: "research" });
  }
});

// ─── Evidence Pack 端点 ───

app.post<{ Body: EvidenceRequest }>("/api/evidence", async (req, reply) => {
  const { query, texts, maxPassages = 30, minScore = 0, dedupSimilarity = 0.85 } = req.body;

  if (!query || !texts || texts.length === 0) {
    return sendRuntimeError(reply, 400, "INVALID_EVIDENCE_INPUT", "query and texts array are required", {}, false);
  }

  try {
    const result = buildEvidencePack(query, texts as any, {
      maxPassages,
    });

    const p = result.pack;
    const s = result.stats;
    const pack: EvidencePack = {
      query,
      passages: (p.passages || []).map((ps) => ({
        text: ps.text,
        sourceUrl: "",
        sourceTitle: "",
        score: ps.score,
        charCount: ps.text.length,
      })),
      claims: (p.claims || []).map((c) => ({
        text: c.claim,
        sourceUrl: "",
        confidence: c.confidence,
      })),
      gaps: (p.gaps || []).map((g) => ({
        description: g,
        severity: "minor" as const,
        category: "coverage" as const,
      })),
      nextQueries: p.nextQueries || [],
      sources: (p.sources || []).map((src) => ({
        url: src.url,
        title: src.title,
        domain: src.domain,
        passageCount: 0,
        averageScore: 0,
      })),
      stats: {
        totalChunks: s.totalChunks,
        scoredChunks: 0,
        exactDeduped: s.exactDuplicatesRemoved,
        nearDeduped: s.nearDuplicatesRemoved,
        selectedPassages: s.finalPassages,
        claimsFound: p.claims.length,
        gapsIdentified: p.gaps?.length || 0,
        totalSources: p.sources.length,
        processingMs: s.processingTimeMs,
      },
    };

    return reply.send(pack);
  } catch (err: any) {
    app.log.error({ err }, "evidence failed");
    return sendRuntimeError(reply, 500, "EVIDENCE_FAILED", err.message, { stage: "evidence" });
  }
});

// ─── 辅助函数 ───

function setCleanUrls(results: any[]) {
  for (const r of results) {
    if (r.url && !r.cleanUrl) {
      r.cleanUrl = cleanUrl(r.url);
    }
  }
}

// ─── 启动 ───

try {
  await app.listen({ port: PORT, host: "127.0.0.1" });
  console.log(`🐋 hollow-search-core v${VERSION} running on http://127.0.0.1:${PORT}`);
  console.log(`   Endpoints: /health /api/search /api/fetch /api/research /api/evidence`);
} catch (err) {
  app.log.error(err);
  process.exit(1);
}

// 优雅退出
process.on("SIGINT", async () => {
  await app.close();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  await app.close();
  process.exit(0);
});

export default app;
