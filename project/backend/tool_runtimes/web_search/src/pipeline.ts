// ============================================================================
// web-search — Main Pipeline Orchestrator
//
// Pipeline: Search → Crawl → Extract → Process → Return
//
// Flow:
//  1. Multi-engine parallel search (DDG + Wikipedia)
//  2. URL deduplication & merging
//  3. Race-based parallel crawl (Promise.race scheduling)
//  4. Fast text extraction (cheerio, no JSDOM)
//  5. Content deduplication (Jaccard similarity)
//  6. Relevance scoring (TF-IDF-like)
//  7. Best passage selection (greedy + diversity)
// ============================================================================

import { multiSearch } from './search.js';
import { batchCrawl } from './crawler.js';
import { extractAll } from './extractor.js';
import { deduplicate, scoreRelevance, selectBest } from './processor.js';
import type {
  WebSearchRequest,
  WebSearchResponse,
  WebSearchStats,
  CrawlResult,
} from './types.js';

// ─── Defaults ──────────────────────────────────────────────────────────────

const DEFAULTS = {
  maxTime: 15000,
  maxContentLength: 8000,
  perUrlTimeout: 3000,
  maxPerUrl: 5000,
  concurrency: 25,
};

export async function executePipeline(
  req: WebSearchRequest,
): Promise<WebSearchResponse> {
  const t0 = performance.now();

  const query = req.query.trim();
  if (!query) {
    throw new Error('query is required');
  }

  const maxTime = req.maxTime || DEFAULTS.maxTime;
  const maxContentLength = req.maxContentLength || DEFAULTS.maxContentLength;
  const perUrlTimeout = req.perUrlTimeout || DEFAULTS.perUrlTimeout;
  const maxPerUrl = req.maxPerUrl || DEFAULTS.maxPerUrl;

  // ── Stage 1: Multi-engine Search ──────────────────────────────────────
  const searchResult = await multiSearch(query);

  if (searchResult.results.length === 0) {
    return {
      query,
      results: [],
      stats: {
        totalTimeMs: Math.round(performance.now() - t0),
        urlsFound: 0,
        crawled: 0,
        crawlFailed: 0,
        extractFailed: 0,
        duplicatesRemoved: 0,
        finalResults: 0,
        stages: {
          searchMs: searchResult.elapsedMs,
          crawlMs: 0,
          processMs: 0,
        },
      },
    };
  }

  const urls = searchResult.results.map((r) => r.url);

  // ── Stage 2: Race-Based Parallel Crawl ─────────────────────────────────
  const crawlDeadline = t0 + maxTime;
  const remainingBudget = Math.max(crawlDeadline - performance.now(), 5000);
  const crawlTimeLimit = Math.min(remainingBudget, maxTime - searchResult.elapsedMs - 2000);

  const crawlResults: CrawlResult[] = await batchCrawl(urls, {
    concurrency: DEFAULTS.concurrency,
    perUrlTimeoutMs: perUrlTimeout,
    hardTimeLimitMs: crawlTimeLimit,
  });

  const crawlElapsed = Math.round(performance.now() - (t0 + searchResult.elapsedMs));

  // ── Stage 3: Text Extraction ───────────────────────────────────────────
  const extracted = extractAll(crawlResults, maxPerUrl);

  const succeeded = extracted.filter((r) => r.status === 'success' && r.text.length > 0);
  const extractFailed = extracted.filter(
    (r) => r.status !== 'success' && r.status !== 'unreachable' && r.status !== 'timeout',
  ).length + extracted.filter((r) => r.status === 'success' && r.text.length === 0).length;

  // ── Stage 4: Content Dedup, Score, Select ──────────────────────────────
  const tProcess = performance.now();

  const { kept, removed } = deduplicate(succeeded, searchResult.results);

  const scored = scoreRelevance(query, kept, searchResult.results);

  const selected = selectBest(scored, searchResult.results, maxContentLength);

  const processElapsed = Math.round(performance.now() - tProcess);
  const totalElapsed = Math.round(performance.now() - t0);

  // ── Build Response ─────────────────────────────────────────────────────
  return {
    query,
    results: selected.map((p) => ({
      title: p.title,
      url: p.url,
      text: p.text,
      score: Math.round(p.score * 100) / 100,
      fromEngines: p.engines,
      domain: p.domain,
      wordCount: p.wordCount,
    })),
    stats: {
      totalTimeMs: totalElapsed,
      urlsFound: searchResult.results.length,
      crawled: crawlResults.filter((r) => r.status === 'success').length,
      crawlFailed: crawlResults.filter(
        (r) => r.status === 'failed' || r.status === 'timeout' || r.status === 'unreachable',
      ).length,
      extractFailed,
      duplicatesRemoved: removed,
      finalResults: selected.length,
      stages: {
        searchMs: searchResult.elapsedMs,
        crawlMs: crawlElapsed,
        processMs: processElapsed,
      },
    },
  };
}
