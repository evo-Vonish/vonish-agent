// ============================================================================
// web-search — Core Type Definitions
// ============================================================================

// ─── API Request ──────────────────────────────────────────────────────────

export interface WebSearchRequest {
  /** Search query */
  query: string;
  /** Total time limit in ms (default: 15000) */
  maxTime?: number;
  /** Maximum total content length in chars (default: 8000) */
  maxContentLength?: number;
  /** Timeout per URL in ms (default: 3000) */
  perUrlTimeout?: number;
  /** Maximum chars per single page (default: 5000) */
  maxPerUrl?: number;
}

// ─── API Response ─────────────────────────────────────────────────────────

export interface WebSearchResponse {
  query: string;
  results: WebSearchResult[];
  stats: WebSearchStats;
}

export interface WebSearchResult {
  title: string;
  url: string;
  /** Extracted and cleaned text content */
  text: string;
  /** Relevance score (0–1) */
  score: number;
  /** Which search engines found this URL */
  fromEngines: string[];
  /** Source domain */
  domain: string;
  /** Word count */
  wordCount: number;
}

export interface WebSearchStats {
  /** Total elapsed time in ms */
  totalTimeMs: number;
  /** Number of URLs found by search engines */
  urlsFound: number;
  /** Number of pages successfully crawled */
  crawled: number;
  /** Number of crawl failures */
  crawlFailed: number;
  /** Number of text extraction failures */
  extractFailed: number;
  /** Number of content duplicates removed */
  duplicatesRemoved: number;
  /** Number of final results returned */
  finalResults: number;
  /** Stage-level timing */
  stages: {
    searchMs: number;
    crawlMs: number;
    processMs: number;
  };
}

// ─── Internal Types ───────────────────────────────────────────────────────

/** Raw search result from an engine */
export interface RawSearchResult {
  title: string;
  url: string;
  snippet?: string;
  engine: string;
  position: number;
}

/** Merged & deduplicated URL entry after multi-engine search */
export interface MergedUrl {
  title: string;
  url: string;
  snippet: string;
  engines: string[];
  positions: number[];
  score: number;
}

/** Single page crawl result */
export interface CrawlResult {
  url: string;
  title: string;
  text: string;
  status: 'success' | 'timeout' | 'failed' | 'unreachable';
  durationMs: number;
  charCount: number;
  wordCount: number;
  error?: string;
}

/** Processed passage after dedup / scoring / selection */
export interface ProcessedPassage {
  url: string;
  title: string;
  text: string;
  score: number;
  domain: string;
  engine: string;
  engines: string[];
  wordCount: number;
}
