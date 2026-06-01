/**
 * Core type definitions for mini-searxng-crawler-ext.
 *
 * All parameters are unbounded — set them as high as your hardware allows.
 */

// ─── Crawl Status ───────────────────────────────────────────────

export type CrawlStatus =
  | 'success'
  | 'failed'
  | 'timeout'
  | 'unreachable'
  | 'deduped'
  | 'noisy'
  | 'paywall'
  | 'skipped';

// ─── Crawl Result (single article) ──────────────────────────────

export interface CrawlResult {
  url: string;
  title: string;
  text: string;
  excerpt: string;
  status: CrawlStatus;
  wordCount: number;
  charCount: number;
  durationMs: number;
  fetchedAt: string;
  contentHash?: string;
  error?: string;
}

// ─── Crawl Progress (real-time) ─────────────────────────────────

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

// ─── Preset Config ──────────────────────────────────────────────

export interface PresetConfig {
  readonly name: string;
  readonly concurrency: number;
  readonly perUrlTimeoutMs: number;
  readonly connectTimeoutMs: number;
  readonly hardTimeLimitMs: number;
  readonly maxTargets: number;
  readonly maxTextCharsPerPage: number;
  readonly retryCount: number;
  readonly streamLimitBytes: number;
  readonly batchSize: number;
  readonly useWorkerPool: boolean;
  readonly workerThreads: number;
  readonly extractEngine: 'readability' | 'fast' | 'hybrid';
  readonly minContentChars: number;
  readonly minWordCount: number;
  readonly minSentenceCount: number;
}

// ─── Ultra Crawl Options (all fields optional, all unbounded) ────

export interface UltraCrawlOptions {
  /** Crawl mode */
  mode: 'search' | 'custom_urls';

  /** Preset name. Use 'unlimited' for 5000+ targets */
  preset?: 'fast' | 'balanced' | 'deep' | 'ultra' | 'maximum' | 'unlimited' | 'custom';

  /** Search query (mode=search) */
  query?: string;

  /** Target URLs (mode=custom_urls) */
  urls?: string[];

  // ─── Performance tuning (all unbounded) ───

  /** Parallel fetch count. 25 for 5s/50, 500 for unlimited */
  concurrency?: number;

  /** Per-URL total timeout in ms */
  perUrlTimeoutMs?: number;

  /** TCP connection timeout in ms */
  connectTimeoutMs?: number;

  /** Global hard deadline in ms */
  hardTimeLimitMs?: number;

  /** Max URLs to crawl. No upper limit. */
  maxTargets?: number;

  /** Max extracted text length per page */
  maxTextCharsPerPage?: number;

  /** Retry count (0 recommended for speed) */
  retryCount?: number;

  /** Stream read cutoff in bytes */
  streamLimitBytes?: number;

  // ─── Streaming & anti-bloat ───

  /** Results per batch callback. Default 100 */
  batchSize?: number;

  /** Called every time a batch is filled */
  onBatch?: (batch: CrawlResult[]) => void | Promise<void>;

  /** Called on every progress update */
  onProgress?: (progress: CrawlProgress) => void | Promise<void>;

  // ─── Extraction ───

  /** Use Piscina Worker pool for CPU extraction */
  useWorkerPool?: boolean;

  /** Worker thread count */
  workerThreads?: number;

  /** Text extraction engine */
  extractEngine?: 'readability' | 'fast' | 'hybrid';

  // ─── Content quality gates ───

  /** Minimum chars to consider valid */
  minContentChars?: number;

  /** Minimum words to consider valid */
  minWordCount?: number;

  /** Minimum sentences to consider valid */
  minSentenceCount?: number;

  // ─── Network ───

  /** Custom User-Agent */
  userAgent?: string;

  /** Deduplicate by content hash */
  removeDuplicates?: boolean;

  /** Max URLs per domain */
  maxPerDomain?: number;
}

// ─── Resolved Options (after preset merge) ──────────────────────

export interface ResolvedCrawlOptions extends Omit<UltraCrawlOptions, 'preset'> {
  preset: string;
}

// ─── Ultra Crawl Response ───────────────────────────────────────

export interface UltraCrawlResponse {
  mode: 'search' | 'custom_urls';
  query?: string;
  preset: string;
  options: ResolvedCrawlOptions;
  results: CrawlResult[];
  progress: CrawlProgress;
  batches: CrawlResult[][];
}

// ─── Fetch Result ───────────────────────────────────────────────

export interface FetchResult {
  html: string;
  finalUrl: string;
  statusCode: number;
  contentType: string;
  durationMs: number;
}

// ─── Extract Result ─────────────────────────────────────────────

export interface ExtractResult {
  title: string;
  text: string;
  excerpt: string;
  wordCount: number;
  charCount: number;
}
