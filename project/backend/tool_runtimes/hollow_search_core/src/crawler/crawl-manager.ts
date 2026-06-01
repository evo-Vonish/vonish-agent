/**
 * Compatibility wrapper for the Mini-SearXNG ultra crawler extension.
 *
 * The public server/evidence API still expects the original CrawlManager
 * response shape (`articles`, `stats`, `options`). Internally, crawling is now
 * delegated to `UltraCrawler`, which provides high-concurrency dispatch,
 * socket-level timeouts, fast unreachable detection, streaming batches, and
 * anti-bloat filtering.
 */

import { createHash } from 'crypto';
import { UltraCrawler } from './ultra/index.js';
import {
  type ArticleStatus,
  type CrawlMode,
  type CrawlOptions,
  type CrawlProgress,
  type CrawlResponse,
  type CrawlStats,
  type CrawledArticle,
  type PresetName,
  PRESETS,
} from './types.js';
import type { CrawlResult, UltraCrawlOptions } from './ultra/types.js';

/**
 * Extended crawl options accepted by CrawlManager.
 *
 * `searchUrls` preserves the original search+URL resolution hook so the server
 * does not need to know whether crawling is powered by the legacy manager or
 * the ultra extension.
 */
export interface CrawlManagerOptions extends CrawlOptions {
  searchUrls?: (query: string) => Promise<string[]>;
}

const DEFAULT_PRESET: PresetName = 'balanced';

export class CrawlManager {
  private readonly ultra = new UltraCrawler();

  async crawl(options: CrawlManagerOptions): Promise<CrawlResponse> {
    const startTime = Date.now();
    const merged = this.mergeOptions(options);
    const urls = await this.resolveUrls(options, merged);

    const batches: CrawledArticle[][] = [];
    const userOnBatch = options.onBatch;
    const userOnProgress = options.onProgress;

    const results = await this.ultra.crawl({
      mode: 'custom_urls',
      preset: merged.preset === 'custom' ? 'balanced' : merged.preset,
      urls,
      concurrency: merged.concurrency,
      perUrlTimeoutMs: merged.perUrlTimeoutMs,
      connectTimeoutMs: merged.connectTimeoutMs,
      hardTimeLimitMs: merged.hardTimeLimitMs,
      maxTargets: merged.maxTargets,
      maxTextCharsPerPage: merged.maxTextCharsPerPage,
      retryCount: merged.retryCount,
      streamLimitBytes: merged.streamLimitBytes,
      batchSize: merged.batchSize,
      useWorkerPool: merged.useWorkerPool,
      workerThreads: merged.workerThreads,
      extractEngine: merged.extractEngine,
      minContentChars: merged.minContentChars,
      minWordCount: merged.minWordCount,
      minSentenceCount: merged.minSentenceCount,
      removeDuplicates: merged.removeDuplicates,
      maxPerDomain: merged.maxPerDomain,
      userAgent: merged.userAgent,
      onBatch: async (batch) => {
        const mapped = batch.map((item) => this.toArticle(item));
        batches.push(mapped);
        await userOnBatch?.(mapped);
      },
      onProgress: async (progress) => {
        await userOnProgress?.(progress as CrawlProgress);
      },
    } satisfies UltraCrawlOptions);

    const articles = results.map((item) => this.toArticle(item));
    const durationMs = Date.now() - startTime;
    const stats = this.buildStats(articles, durationMs);

    return {
      articles,
      stats,
      options: merged,
    };
  }

  async close(): Promise<void> {
    await this.ultra.close();
  }

  private async resolveUrls(options: CrawlManagerOptions, merged: Required<CrawlOptions>): Promise<string[]> {
    let targetUrls: string[] = [];

    if (merged.mode === 'search') {
      if (!options.searchUrls || !options.query) {
        throw new Error("CrawlManager: 'searchUrls' function and 'query' are required when mode is 'search'");
      }
      targetUrls = await options.searchUrls(options.query);
    } else {
      targetUrls = options.urls ?? [];
    }

    const seen = new Set<string>();
    const unique: string[] = [];
    for (const url of targetUrls) {
      const normalized = normalizeUrl(url);
      if (!seen.has(normalized)) {
        seen.add(normalized);
        unique.push(url);
      }
    }

    return unique.slice(0, merged.maxTargets);
  }

  private mergeOptions(options: CrawlManagerOptions): Required<CrawlOptions> {
    const preset = options.preset ?? DEFAULT_PRESET;
    const base = PRESETS[preset] ?? PRESETS[DEFAULT_PRESET];
    const maxTextCharsPerPage =
      options.maxTextCharsPerPage ?? options.maxTextChars ?? base.maxTextCharsPerPage;

    return {
      mode: options.mode ?? 'custom_urls',
      preset,
      query: options.query ?? '',
      urls: options.urls ?? [],
      concurrency: options.concurrency ?? base.concurrency,
      perUrlTimeoutMs: options.perUrlTimeoutMs ?? base.perUrlTimeoutMs,
      hardTimeLimitMs: options.hardTimeLimitMs ?? base.hardTimeLimitMs,
      maxTargets: options.maxTargets ?? base.maxTargets,
      maxTextChars: options.maxTextChars ?? maxTextCharsPerPage,
      maxTextCharsPerPage,
      retryCount: options.retryCount ?? base.retryCount,
      connectTimeoutMs: options.connectTimeoutMs ?? base.connectTimeoutMs ?? 800,
      headersTimeoutMs:
        options.headersTimeoutMs ??
        base.headersTimeoutMs ??
        Math.min(options.perUrlTimeoutMs ?? base.perUrlTimeoutMs, 2000),
      streamLimitBytes: options.streamLimitBytes ?? base.streamLimitBytes ?? 500 * 1024,
      removeDuplicates: options.removeDuplicates ?? true,
      maxPerDomain: options.maxPerDomain ?? 0,
      userAgent: options.userAgent ?? '',
      batchSize: options.batchSize ?? base.batchSize ?? 100,
      onBatch: options.onBatch ?? (() => undefined),
      onProgress: options.onProgress ?? (() => undefined),
      useWorkerPool: options.useWorkerPool ?? base.useWorkerPool ?? true,
      workerThreads: options.workerThreads ?? base.workerThreads ?? 4,
      extractEngine: options.extractEngine ?? base.extractEngine ?? 'hybrid',
      minContentChars: options.minContentChars ?? base.minContentChars ?? 200,
      minWordCount: options.minWordCount ?? base.minWordCount ?? 50,
      minSentenceCount: options.minSentenceCount ?? base.minSentenceCount ?? 3,
    };
  }

  private toArticle(result: CrawlResult): CrawledArticle {
    const normalizedUrl = normalizeUrl(result.url);
    const textHash = result.contentHash || hashText(result.text || normalizedUrl);

    return {
      url: result.url,
      normalizedUrl,
      title: result.title || normalizedUrl,
      text: result.text || '',
      excerpt: result.excerpt || (result.text || '').slice(0, 200),
      textHash,
      status: result.status as ArticleStatus,
      error: result.error,
      durationMs: result.durationMs,
      crawledAt: Date.parse(result.fetchedAt) || Date.now(),
    };
  }

  private buildStats(articles: CrawledArticle[], durationMs: number): CrawlStats {
    const count = (status: ArticleStatus) => articles.filter((item) => item.status === status).length;
    const timeout = count('timeout');
    const skipped = count('skipped');
    const unreachable = count('unreachable');
    const noisy = count('noisy');
    const paywall = count('paywall');
    const duplicatesRemoved = count('deduped');
    const failed = articles.filter((item) =>
      ['failed', 'unreachable', 'noisy', 'paywall'].includes(item.status),
    ).length;

    return {
      totalUrls: articles.length,
      success: count('success'),
      failed,
      timeout,
      skipped,
      duplicatesRemoved,
      unreachable,
      noisy,
      paywall,
      durationMs,
    };
  }
}

export function normalizeUrl(url: string): string {
  try {
    const parsed = new URL(url);
    parsed.hash = '';
    parsed.searchParams.sort();
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return url.trim();
  }
}

function hashText(text: string): string {
  return createHash('sha1').update(text).digest('hex');
}
