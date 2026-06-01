/**
 * Mini-SearXNG Crawler Extension — Enterprise-grade high-performance crawler.
 *
 * Features:
 * - Unlimited concurrency (up to 500+)
 * - 5-second / 50-article challenge mode
 * - Real-time streaming (every 100 results trigger callback)
 * - Anti-bloat deduplication (inline filtering, no waiting)
 * - undici Agent with HTTP/2, DNS cache, connection pooling
 * - TCP fast-fail probe (500ms unreachable detection)
 * - Layered timeouts (connect 300-800ms, body 1-5s)
 * - Stream truncation (stop reading after 100-300KB)
 *
 * @example
 * ```typescript
 * import { UltraCrawler, ULTRA_PRESETS } from 'mini-searxng-crawler-ext';
 *
 * const crawler = new UltraCrawler();
 *
 * const results = await crawler.crawl({
 *   mode: 'custom_urls',
 *   preset: 'unlimited',
 *   urls: urlList,              // 5000 URLs
 *   concurrency: 500,           // 500 parallel
 *   maxTargets: 5000,           // no upper limit
 *   batchSize: 100,             // callback every 100
 *   onBatch: (batch) => {
 *     console.log(`[驱虫] ${batch.length} articles processed`);
 *   },
 *   onProgress: (p) => {
 *     console.log(`${p.totalCompleted}/${p.totalQueued} | ${p.throughputPerSecond.toFixed(1)}/s`);
 *   },
 * });
 * ```
 */

// ─── Types ──────────────────────────────────────────────────────

export type {
  CrawlStatus,
  CrawlResult,
  CrawlProgress,
  PresetConfig,
  UltraCrawlOptions,
  ResolvedCrawlOptions,
  UltraCrawlResponse,
  FetchResult,
  ExtractResult,
} from './types.js';

// ─── Presets ────────────────────────────────────────────────────

export {
  FAST_PRESET,
  BALANCED_PRESET,
  DEEP_PRESET,
  ULTRA_PRESET,
  MAXIMUM_PRESET,
  UNLIMITED_PRESET,
  PRESETS,
  resolvePreset,
  mergePreset,
} from './presets.js';

// ─── Core ───────────────────────────────────────────────────────

export { getGlobalAgent, createAgent, warmConnections, closeAllPools } from './core/connection-pool.js';
export { ultraFetch, probeConnection } from './core/ultra-fetcher.js';
export { streamDispatch } from './core/stream-dispatcher.js';
export { AntiBloatMonitor, passesQualityGate } from './core/anti-bloat-monitor.js';

// ─── Extractors ─────────────────────────────────────────────────

export { extractTextFast } from './extractors/fast-text.js';
export { extractWithReadability } from './extractors/readability-extractor.js';
export { cleanText, stripHtml } from './extractors/text-cleaner.js';

// ─── Filters ────────────────────────────────────────────────────

export { isNoise, contentRatio, filterNoiseResults } from './filters/noise-filter.js';
export { detectSoftPaywall, stripPaywall } from './filters/soft-paywall.js';

// ─── Config ─────────────────────────────────────────────────────

export { resolveOptions } from './config.js';

// ─── Main API ───────────────────────────────────────────────────

import { streamDispatch } from './core/stream-dispatcher.js';
import { resolveOptions } from './config.js';
import { closeAllPools } from './core/connection-pool.js';
import type { UltraCrawlOptions, CrawlResult, CrawlProgress, PresetConfig } from './types.js';

/**
 * UltraCrawler — main entry class.
 *
 * Usage:
 * ```typescript
 * const crawler = new UltraCrawler();
 * const results = await crawler.crawl(options);
 * ```
 */
export class UltraCrawler {
  /**
   * Execute a crawl with the given options.
   *
   * @param opts — crawl options (preset, concurrency, callbacks, etc.)
   * @returns all crawl results
   */
  async crawl(opts: UltraCrawlOptions): Promise<CrawlResult[]> {
    const resolved = resolveOptions(opts);

    // Get URLs
    const urls = (resolved.urls || []).slice(0, resolved.maxTargets);

    if (urls.length === 0) {
      return [];
    }

    // Build preset config (all values guaranteed non-undefined by resolveOptions)
    const preset: PresetConfig = {
      name: resolved.preset ?? 'balanced',
      concurrency: resolved.concurrency ?? 25,
      perUrlTimeoutMs: resolved.perUrlTimeoutMs ?? 2500,
      connectTimeoutMs: resolved.connectTimeoutMs ?? 800,
      hardTimeLimitMs: resolved.hardTimeLimitMs ?? 30000,
      maxTargets: resolved.maxTargets ?? 20,
      maxTextCharsPerPage: resolved.maxTextCharsPerPage ?? 15000,
      retryCount: resolved.retryCount ?? 0,
      streamLimitBytes: resolved.streamLimitBytes ?? 204800,
      batchSize: resolved.batchSize ?? 100,
      useWorkerPool: resolved.useWorkerPool ?? true,
      workerThreads: resolved.workerThreads ?? 4,
      extractEngine: (resolved.extractEngine ?? 'hybrid') as 'readability' | 'fast' | 'hybrid',
      minContentChars: resolved.minContentChars ?? 200,
      minWordCount: resolved.minWordCount ?? 50,
      minSentenceCount: resolved.minSentenceCount ?? 3,
    };

    // Execute stream dispatch
    const results = await streamDispatch({
      urls,
      preset,
      userAgent: resolved.userAgent,
      onBatch: resolved.onBatch,
      onProgress: resolved.onProgress,
      removeDuplicates: resolved.removeDuplicates,
    });

    return results;
  }

  /**
   * Quick crawl — shorthand for common use case.
   *
   * @param urls — URLs to crawl
   * @param presetName — preset ('fast' | 'balanced' | 'deep' | 'ultra' | 'maximum' | 'unlimited')
   */
  async quickCrawl(
    urls: string[],
    presetName: string = 'balanced',
    onProgress?: (p: CrawlProgress) => void,
  ): Promise<CrawlResult[]> {
    return this.crawl({
      mode: 'custom_urls',
      preset: presetName as UltraCrawlOptions['preset'],
      urls,
      onProgress,
    });
  }

  /**
   * Gracefully close all connection pools.
   * Call this before process exit.
   */
  async close(): Promise<void> {
    await closeAllPools();
  }
}

// ─── Default export ─────────────────────────────────────────────

export default UltraCrawler;
