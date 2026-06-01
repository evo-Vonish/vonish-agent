/**
 * Stream Dispatcher — high-concurrency streaming crawl orchestrator.
 *
 * Key features:
 * - Promise.race() based scheduling: as soon as one URL completes,
 *   immediately start the next (no waiting for batch)
 * - Anti-bloat dedup applied inline (every result checked immediately)
 * - Batch flush every N results (default 100) — prints + callbacks
 * - Hard time limit enforced with AbortController
 * - No retries — retries waste time budget in high-concurrency mode
 */

import type { CrawlResult, CrawlProgress, PresetConfig } from '../types.js';
import { ultraFetch } from './ultra-fetcher.js';
import { AntiBloatMonitor } from './anti-bloat-monitor.js';
import { extractTextFast } from '../extractors/fast-text.js';
import { extractWithReadability } from '../extractors/readability-extractor.js';
import { cleanText } from '../extractors/text-cleaner.js';

export interface DispatchOptions {
  urls: string[];
  preset: PresetConfig;
  userAgent?: string;
  onBatch?: (batch: CrawlResult[]) => void | Promise<void>;
  onProgress?: (progress: CrawlProgress) => void | Promise<void>;
  removeDuplicates?: boolean;
}

// ─── Single URL crawl ───────────────────────────────────────────

async function crawlOne(
  url: string,
  preset: PresetConfig,
  userAgent?: string,
): Promise<CrawlResult> {
  const start = Date.now();

  // Step 1: Fetch with ultra-fast timeout
  const fetchResult = await ultraFetch({
    url,
    timeoutMs: preset.perUrlTimeoutMs,
    connectTimeoutMs: preset.connectTimeoutMs,
    userAgent,
    streamLimitBytes: preset.streamLimitBytes,
  });

  // Fast-fail: empty HTML or non-2xx
  if (!fetchResult.html || fetchResult.html.length === 0) {
    return {
      url,
      title: '',
      text: '',
      excerpt: '',
      status: fetchResult.durationMs < 1000 ? 'unreachable' : 'timeout',
      wordCount: 0,
      charCount: 0,
      durationMs: fetchResult.durationMs,
      fetchedAt: new Date().toISOString(),
      error: `HTTP ${fetchResult.statusCode || 0}`,
    };
  }

  // Step 2: Extract text
  const extractStart = Date.now();
  let extractResult: { title: string; text: string; excerpt: string } | null;

  try {
    if (preset.extractEngine === 'fast') {
      // Fast cheerio-based extraction (no JSDOM overhead)
      extractResult = extractTextFast(fetchResult.html, url);
    } else if (preset.extractEngine === 'readability') {
      // Full Mozilla Readability
      const article = extractWithReadability(fetchResult.html, url);
      extractResult = article
        ? {
            title: article.title,
            text: article.textContent,
            excerpt: article.excerpt || article.textContent.slice(0, 200),
          }
        : null;
    } else {
      // Hybrid: try Readability first, fallback to fast
      const article = extractWithReadability(fetchResult.html, url);
      if (article && article.textContent.length > 500) {
        extractResult = {
          title: article.title,
          text: article.textContent,
          excerpt: article.excerpt || article.textContent.slice(0, 200),
        };
      } else {
        extractResult = extractTextFast(fetchResult.html, url);
      }
    }
  } catch {
    extractResult = extractTextFast(fetchResult.html, url);
  }

  // Step 3: Clean text
  const text = extractResult ? cleanText(extractResult.text) : '';
  const title = extractResult?.title || '';

  if (text.length === 0) {
    return {
      url,
      title: '',
      text: '',
      excerpt: '',
      status: 'failed',
      wordCount: 0,
      charCount: 0,
      durationMs: Date.now() - start,
      fetchedAt: new Date().toISOString(),
      error: 'Extraction failed',
    };
  }

  // Step 4: Truncate if needed
  const maxChars = preset.maxTextCharsPerPage;
  const finalText = text.length > maxChars ? text.slice(0, maxChars) + '...' : text;

  const words = finalText.split(/\s+/).filter((w) => w.length > 0);

  return {
    url: fetchResult.finalUrl,
    title,
    text: finalText,
    excerpt: finalText.slice(0, 200),
    status: 'success',
    wordCount: words.length,
    charCount: finalText.length,
    durationMs: Date.now() - start,
    fetchedAt: new Date().toISOString(),
  };
}

// ─── Race-based concurrent scheduler ────────────────────────────

/**
 * The core scheduling algorithm.
 *
 * Instead of Promise.allSettled (waits for all in batch),
 * we use Promise.race — as soon as ONE request completes,
 * we immediately process it and start a new one.
 *
 * This keeps the concurrency pipeline full at all times.
 */
export async function streamDispatch(opts: DispatchOptions): Promise<CrawlResult[]> {
  const { urls, preset, userAgent, onBatch, onProgress, removeDuplicates } = opts;

  const startTime = Date.now();
  const abortController = new AbortController();
  const hardTimer = setTimeout(
    () => abortController.abort('HARD_TIME_LIMIT'),
    preset.hardTimeLimitMs,
  );

  // Initialize anti-bloat monitor
  const monitor = new AntiBloatMonitor({
    batchSize: preset.batchSize,
    removeDuplicates,
    qualityGate: {
      minChars: preset.minContentChars,
      minWordCount: preset.minWordCount,
      minSentenceCount: preset.minSentenceCount,
    },
    onBatch,
    onProgress,
  });

  // Mark all URLs as queued (dedup)
  for (const url of urls) {
    if (!monitor.isDuplicateUrl(url)) {
      monitor.markUrlQueued(url);
    }
  }
  monitor.start(urls.length);

  // Active request pool: Map<promise, url>
  const active = new Map<Promise<CrawlResult>, string>();
  let queueIdx = 0;

  // Fill initial concurrency pool
  function launchNext(): void {
    while (
      active.size < preset.concurrency &&
      queueIdx < urls.length &&
      !abortController.signal.aborted
    ) {
      const url = urls[queueIdx++];

      monitor.totalStarted++;

      // Create crawl promise
      const promise = crawlOne(url, preset, userAgent).then(async (result) => {
        if (abortController.signal.aborted) {
          result.status = 'skipped';
        }
        return monitor.processResult(result);
      });

      active.set(promise, url);
    }
  }

  // Launch initial burst
  launchNext();

  // Race loop: process completions as they happen
  const finalResults: CrawlResult[] = [];

  try {
    while (active.size > 0 && !abortController.signal.aborted) {
      // Race all active promises
      const result = await Promise.race(
        Array.from(active.keys()).map((p) =>
          p.then((r) => ({ type: 'done' as const, result: r, promise: p })),
        ),
      );

      // Remove completed from active pool
      active.delete(result.promise);

      // Immediately launch next to keep pipeline full
      launchNext();
    }
  } catch {
    // Abort triggered — drain remaining
  }

  // Wait for any remaining (in case of abort)
  const remaining = await Promise.allSettled(Array.from(active.keys()));
  for (const r of remaining) {
    if (r.status === 'fulfilled') {
      await monitor.processResult(r.value);
    }
  }

  // Clear hard timer
  clearTimeout(hardTimer);

  // Final flush
  const allResults = await monitor.finalize();

  // Print summary
  const p = monitor.getProgress();
  console.log(`\n========== 爬取完成 ==========`);
  console.log(`总目标: ${p.totalQueued} | 完成: ${p.totalCompleted}`);
  console.log(`成功: ${p.totalSucceeded} | 失败: ${p.totalFailed}`);
  console.log(`去重: ${p.totalDeduped} | 噪声: ${p.totalNoisy}`);
  console.log(`总耗时: ${p.elapsedMs}ms | 吞吐量: ${p.throughputPerSecond.toFixed(1)}/s`);
  console.log(`==============================\n`);

  return allResults;
}
