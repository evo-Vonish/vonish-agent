/**
 * Crawler module type definitions and preset configurations.
 *
 * Provides the core types for crawl operations including mode definitions,
 * preset configurations, crawl options, result structures, and statistics.
 *
 * @module types
 */

/** Crawl mode: 'search' triggers engine search first; 'custom_urls' uses provided URLs directly. */
export type CrawlMode = 'search' | 'custom_urls';

/** Preset name that determines default crawl behavior aggressiveness. */
export type PresetName = 'fast' | 'balanced' | 'deep' | 'ultra' | 'maximum' | 'unlimited' | 'custom';

/** Per-URL crawl status. */
export type ArticleStatus =
  | 'success'
  | 'failed'
  | 'timeout'
  | 'unreachable'
  | 'deduped'
  | 'noisy'
  | 'paywall'
  | 'skipped';

/**
 * Configuration values associated with a crawl preset.
 * Determines concurrency, timeouts, limits, and content handling.
 */
export interface PresetConfig {
  concurrency: number;
  perUrlTimeoutMs: number;
  hardTimeLimitMs: number;
  maxTargets: number;
  maxTextCharsPerPage: number;
  retryCount: number;
  contentComplexity: 'simple' | 'normal' | 'rich';
  connectTimeoutMs?: number;
  headersTimeoutMs?: number;
  streamLimitBytes?: number;
  batchSize?: number;
  useWorkerPool?: boolean;
  workerThreads?: number;
  extractEngine?: 'readability' | 'fast' | 'hybrid';
  minContentChars?: number;
  minWordCount?: number;
  minSentenceCount?: number;
}

/**
 * User-provided options for a crawl operation.
 * Combines mode/preset selection with optional per-parameter overrides.
 */
export interface CrawlOptions {
  /** Crawling mode: 'search' uses a query, 'custom_urls' uses a provided list. */
  mode?: CrawlMode;
  /** Preset configuration name to use as base defaults. */
  preset?: PresetName;
  /** Search query string (required when mode === 'search'). */
  query?: string;
  /** Explicit URL list (used when mode === 'custom_urls'). */
  urls?: string[];

  // Custom overrides
  /** Maximum number of concurrent fetches. */
  concurrency?: number;
  /** Timeout for each individual URL fetch (ms). */
  perUrlTimeoutMs?: number;
  /** Hard wall-clock limit for the entire crawl operation (ms). */
  hardTimeLimitMs?: number;
  /** Maximum number of URLs to crawl. */
  maxTargets?: number;
  /** Maximum characters to keep from extracted text. */
  maxTextChars?: number;
  /** Maximum characters per page (alias for maxTextChars). */
  maxTextCharsPerPage?: number;
  /** Number of retries per URL on transient failures. */
  retryCount?: number;
  /** TCP connect timeout before the request is treated as unreachable. */
  connectTimeoutMs?: number;
  /** Timeout for receiving response headers. */
  headersTimeoutMs?: number;
  /** Maximum response bytes to read before truncating the stream. */
  streamLimitBytes?: number;

  /** Remove duplicate articles based on content hash. */
  removeDuplicates?: boolean;
  /** Maximum number of articles to fetch from a single domain. */
  maxPerDomain?: number;
  /** Custom User-Agent string for HTTP requests. */
  userAgent?: string;
  /** Results per callback batch. Used by the ultra crawler replacement. */
  batchSize?: number;
  /** Called whenever the ultra crawler emits a filled batch. */
  onBatch?: (batch: CrawledArticle[]) => void | Promise<void>;
  /** Called when crawl progress changes. */
  onProgress?: (progress: CrawlProgress) => void | Promise<void>;
  /** Enable worker-pool extraction if supported by the active crawler. */
  useWorkerPool?: boolean;
  /** Worker thread count for extraction. */
  workerThreads?: number;
  /** Text extraction engine preference. */
  extractEngine?: 'readability' | 'fast' | 'hybrid';
  /** Minimum accepted content characters. */
  minContentChars?: number;
  /** Minimum accepted word count. */
  minWordCount?: number;
  /** Minimum accepted sentence count. */
  minSentenceCount?: number;
}

/**
 * Represents a single article/page that has been crawled.
 */
export interface CrawledArticle {
  /** Source URL of the article. */
  url: string;
  /** Normalized URL used for deduplication. */
  normalizedUrl: string;
  /** Extracted article title. */
  title: string;
  /** Cleaned article body text. */
  text: string;
  /** Short excerpt (first ~200 characters). */
  excerpt: string;
  /** MD5 hash of the normalized text for deduplication. */
  textHash: string;
  /** Final crawl status for this URL. */
  status: ArticleStatus;
  /** Human-readable error message when status !== 'success'. */
  error?: string;
  /** Time spent fetching and extracting this article (ms). */
  durationMs: number;
  /** Unix timestamp (ms) when the article was crawled. */
  crawledAt: number;
}

/**
 * Aggregate statistics for a completed (or partially completed) crawl operation.
 */
export interface CrawlStats {
  /** Total number of URLs that were attempted. */
  totalUrls: number;
  /** Number of successfully crawled articles. */
  success: number;
  /** Number of articles that failed due to non-timeout errors. */
  failed: number;
  /** Number of articles that hit the per-URL timeout. */
  timeout: number;
  /** Number of articles skipped (e.g., aborted by hard time limit). */
  skipped: number;
  /** Number of duplicate articles removed. */
  duplicatesRemoved: number;
  /** Number of URLs rejected as unreachable before full fetch. */
  unreachable?: number;
  /** Number of articles rejected by quality/noise gates. */
  noisy?: number;
  /** Number of articles rejected as soft paywalls. */
  paywall?: number;
  /** Total wall-clock duration of the crawl (ms). */
  durationMs: number;
}

/** Real-time progress payload emitted by the ultra crawler. */
export interface CrawlProgress {
  totalQueued: number;
  totalStarted: number;
  totalCompleted: number;
  totalSucceeded: number;
  totalFailed: number;
  totalDeduped: number;
  totalNoisy: number;
  totalPaywalled: number;
  currentBatch: number;
  elapsedMs: number;
  estimatedRemainingMs: number;
  throughputPerSecond: number;
}

/**
 * Complete response object returned after a crawl operation finishes.
 */
export interface CrawlResponse {
  /** Deduplicated list of crawled articles. */
  articles: CrawledArticle[];
  /** Summary statistics for the crawl. */
  stats: CrawlStats;
  /** The crawl options that were used (merged with preset). */
  options: Required<CrawlOptions>;
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

/**
 * Built-in crawl presets that trade speed against depth and quality.
 *
 * - **fast** – High concurrency, short timeouts, small limits. Best for quick previews.
 * - **balanced** – Moderate values, a good default for most use-cases.
 * - **deep** – Low concurrency, generous timeouts, large limits. Best for thorough research.
 * - **custom** – Placeholder preset; when selected, balanced values are used as defaults
 *   and then overridden by any explicit per-parameter values in `CrawlOptions`.
 */
export const PRESETS: Record<PresetName, PresetConfig> = {
  fast: {
    concurrency: 8,
    perUrlTimeoutMs: 3000,
    hardTimeLimitMs: 15000,
    maxTargets: 10,
    maxTextCharsPerPage: 8000,
    retryCount: 0,
    contentComplexity: 'simple',
    connectTimeoutMs: 1000,
    headersTimeoutMs: 2000,
    streamLimitBytes: 100 * 1024,
    batchSize: 10,
    useWorkerPool: false,
    workerThreads: 2,
    extractEngine: 'fast',
    minContentChars: 200,
    minWordCount: 50,
    minSentenceCount: 3,
  },
  balanced: {
    concurrency: 25,
    perUrlTimeoutMs: 2500,
    hardTimeLimitMs: 30000,
    maxTargets: 20,
    maxTextCharsPerPage: 15000,
    retryCount: 0,
    contentComplexity: 'normal',
    connectTimeoutMs: 800,
    headersTimeoutMs: 2000,
    streamLimitBytes: 200 * 1024,
    batchSize: 20,
    useWorkerPool: true,
    workerThreads: 4,
    extractEngine: 'hybrid',
    minContentChars: 200,
    minWordCount: 50,
    minSentenceCount: 3,
  },
  deep: {
    concurrency: 50,
    perUrlTimeoutMs: 5000,
    hardTimeLimitMs: 90000,
    maxTargets: 50,
    maxTextCharsPerPage: 30000,
    retryCount: 0,
    contentComplexity: 'rich',
    connectTimeoutMs: 1000,
    headersTimeoutMs: 3000,
    streamLimitBytes: 300 * 1024,
    batchSize: 50,
    useWorkerPool: true,
    workerThreads: 6,
    extractEngine: 'readability',
    minContentChars: 200,
    minWordCount: 50,
    minSentenceCount: 3,
  },
  ultra: {
    concurrency: 100,
    perUrlTimeoutMs: 2000,
    hardTimeLimitMs: 5000,
    maxTargets: 50,
    maxTextCharsPerPage: 15000,
    retryCount: 0,
    contentComplexity: 'normal',
    connectTimeoutMs: 500,
    headersTimeoutMs: 1500,
    streamLimitBytes: 200 * 1024,
    batchSize: 50,
    useWorkerPool: true,
    workerThreads: 8,
    extractEngine: 'fast',
    minContentChars: 100,
    minWordCount: 30,
    minSentenceCount: 2,
  },
  maximum: {
    concurrency: 200,
    perUrlTimeoutMs: 1500,
    hardTimeLimitMs: 10000,
    maxTargets: 500,
    maxTextCharsPerPage: 15000,
    retryCount: 0,
    contentComplexity: 'normal',
    connectTimeoutMs: 400,
    headersTimeoutMs: 1200,
    streamLimitBytes: 150 * 1024,
    batchSize: 100,
    useWorkerPool: true,
    workerThreads: 8,
    extractEngine: 'fast',
    minContentChars: 100,
    minWordCount: 30,
    minSentenceCount: 2,
  },
  unlimited: {
    concurrency: 500,
    perUrlTimeoutMs: 1000,
    hardTimeLimitMs: 30000,
    maxTargets: 5000,
    maxTextCharsPerPage: 10000,
    retryCount: 0,
    contentComplexity: 'simple',
    connectTimeoutMs: 300,
    headersTimeoutMs: 800,
    streamLimitBytes: 100 * 1024,
    batchSize: 100,
    useWorkerPool: true,
    workerThreads: 16,
    extractEngine: 'fast',
    minContentChars: 50,
    minWordCount: 10,
    minSentenceCount: 1,
  },
  custom: {
    // Custom has no intrinsic defaults — balanced values are used as a base
    // and then overridden by any explicit per-parameter values.
    concurrency: 5,
    perUrlTimeoutMs: 5000,
    hardTimeLimitMs: 30000,
    maxTargets: 20,
    maxTextCharsPerPage: 15000,
    retryCount: 1,
    contentComplexity: 'normal',
    connectTimeoutMs: 800,
    headersTimeoutMs: 2000,
    streamLimitBytes: 500 * 1024,
    batchSize: 20,
    useWorkerPool: true,
    workerThreads: 4,
    extractEngine: 'hybrid',
    minContentChars: 200,
    minWordCount: 50,
    minSentenceCount: 3,
  },
};
