// ─── hollow-search-core 统一类型系统 ───

// ============================================================
// 搜索类型
// ============================================================
export type SearchMode =
  | "overview"
  | "scholar"
  | "dev"
  | "live"
  | "media"
  | "deep_dive";

export interface SearchRequest {
  query: string;
  mode?: SearchMode;
  engines?: string[];
  limit?: number;
  language?: string;
  safeSearch?: boolean;
  fresh?: boolean;
  timeoutMs?: number;
  // mini-searxng orchestrator 兼容字段
  timeout?: number;
  categories?: string[];
  pageno?: number;
}

export interface SearchResult {
  title: string;
  url: string;
  cleanUrl: string;
  content: string;
  engine: string;
  score: number;
  domain: string;
  isAd: boolean;
  isSeoSpam: boolean;
  domainAuthority: number;
  publishedDate?: string;
  thumbnail?: string;
  // mini-searxng merger 兼容字段
  engines?: string[];
  positions?: number[];
  category?: string;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  results: SearchResult[];
  stats: SearchStats;
  tookMs: number;
}

export interface SearchStats {
  totalResults: number;
  engineBreakdown: Record<string, number>;
  adsFiltered: number;
  seoFiltered: number;
  duplicatesRemoved: number;
}

export interface RawSearchResult {
  title: string;
  url: string;
  content: string;
  engine: string;
  score: number;
  publishedDate?: string;
  thumbnail?: string;
}

// 别名 — mini-searxng 旧代码使用 RawResult
export type RawResult = RawSearchResult;

// ============================================================
// 爬虫类型
// ============================================================
export type CrawlPreset = "fast" | "balanced" | "deep" | "ultra" | "maximum" | "unlimited";
export type ExtractionMode = "fast" | "readability" | "hybrid";

export interface CrawlRequest {
  urls: string[];
  preset?: CrawlPreset;
  extraction?: ExtractionMode;
  maxConcurrency?: number;
  maxCharsPerPage?: number;
  purify?: boolean;
  purifyMode?: PurifyMode;
}

export interface CrawlProgress {
  completed: number;
  total: number;
  succeeded: number;
  failed: number;
  bytesDownloaded: number;
  throughputMBps: number;
  etaSeconds: number;
}

export interface CrawledPage {
  url: string;
  title: string;
  html?: string;
  text: string;
  markdown?: string;
  extractionMode: ExtractionMode;
  purifyResult?: PurifyResult;
  status: "success" | "partial" | "failed";
  statusCode?: number;
  error?: string;
  charCount: number;
  fetchMs: number;
}

export interface CrawlResponse {
  pages: CrawledPage[];
  stats: {
    total: number;
    succeeded: number;
    failed: number;
    partial: number;
    totalBytes: number;
    totalChars: number;
    totalMs: number;
  };
}

// ============================================================
// 净化类型 (来自 HOLLOW content-purifier)
// ============================================================
export type PurifyMode = "conservative" | "balanced" | "aggressive";

export interface PurifyRequest {
  html: string;
  url?: string;
  mode?: PurifyMode;
  keepImages?: boolean;
  keepTables?: boolean;
  keepVideos?: boolean;
}

export interface PurifyResult {
  originalHtml: string;
  phase1Html?: string;
  extractedHtml?: string;
  markdown: string;
  text: string;
  title?: string;
  qualityScore: number;
  auditLog: AuditLogEntry[];
  stats: PurifyStats;
  charCount: number;
  processedMs: number;
}

export interface AuditLogEntry {
  action: "remove" | "protect" | "mark" | "skip";
  target: string;
  reason: string;
  confidence: number;
  phase: 1 | 2;
  timestamp: number;
}

export interface PurifyStats {
  originalSize: number;
  cleanedSize: number;
  noiseRatio: number;
  elementsRemoved: number;
  elementsProtected: number;
}

// ============================================================
// Evidence Pack 类型
// ============================================================
export interface EvidenceRequest {
  query: string;
  texts: EvidenceSource[];
  maxPassages?: number;
  minScore?: number;
  dedupSimilarity?: number;
}

export interface EvidenceSource {
  url: string;
  title: string;
  text: string;
  markdown?: string;
}

export interface EvidencePack {
  query: string;
  passages: EvidencePassage[];
  claims: Claim[];
  gaps: ResearchGap[];
  nextQueries: string[];
  sources: SourceSummary[];
  stats: EvidenceStats;
}

export interface EvidencePassage {
  text: string;
  sourceUrl: string;
  sourceTitle: string;
  score: number;
  charCount: number;
}

export interface Claim {
  text: string;
  sourceUrl: string;
  confidence: "high" | "medium" | "low";
  type?: "factual" | "opinion" | "statistical" | "citation";
}

export interface ResearchGap {
  description: string;
  severity: "critical" | "major" | "minor";
  category: "coverage" | "timeliness" | "source_diversity" | "evidence_quality" | "bias";
}

export interface SourceSummary {
  url: string;
  title: string;
  domain: string;
  passageCount: number;
  averageScore: number;
}

export interface EvidenceStats {
  totalChunks: number;
  scoredChunks: number;
  exactDeduped: number;
  nearDeduped: number;
  selectedPassages: number;
  claimsFound: number;
  gapsIdentified: number;
  totalSources: number;
  processingMs: number;
}

// ============================================================
// 研究管道类型 (完整链路)
// ============================================================
export interface ResearchRequest {
  query: string;
  mode?: SearchMode;
  searchLimit?: number;
  crawlPreset?: CrawlPreset;
  extraction?: ExtractionMode;
  purifyMode?: PurifyMode;
  maxEvidencePassages?: number;
  engines?: string[];
  supplement?: boolean;
}

export interface ResearchResponse {
  query: string;
  mode: SearchMode;
  search: {
    results: SearchResult[];
    tookMs: number;
  };
  crawl: {
    pages: CrawledPage[];
    stats: CrawlResponse["stats"];
  };
  evidence?: EvidencePack;
  totalMs: number;
  totalBytes: number;
}

// ============================================================
// 错误类型
// ============================================================
export type PipelineStage = "search" | "crawl" | "purify" | "evidence";

export interface PipelineError {
  ok: false;
  stage: PipelineStage;
  error: {
    code: string;
    message: string;
    recoverable: boolean;
  };
  partial?: unknown;
}

// ============================================================
// Agent 工具 Schema
// ============================================================
export interface AgentToolResult<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  errorCode?: string;
  stage?: PipelineStage;
  stats?: {
    stageMs: Record<string, number>;
    totalMs: number;
    bandwidthBytes: number;
  };
}

// ============================================================
// 服务状态
// ============================================================
export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  uptime: number;
  engines: string[];
  modes: SearchMode[];
  presets: CrawlPreset[];
  purifyModes: PurifyMode[];
}
