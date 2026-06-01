// 桥接文件 — 让 mini-searxng 旧代码的 import '../types.js' 无缝工作
// 注意：此文件只导出 mini-searxng 引擎层内部类型
// API 层类型请直接从 ./types/index.js 导入

// 不 re-export types/index 以避免 SearchRequest/SearchResult 命名冲突

// ─── mini-searxng 引擎层实际使用的类型 ───

/** 搜索引擎 buildRequest 返回的 HTTP 请求参数 */
export interface RequestParams {
  // 搜索参数
  query: string;
  pageno?: number;
  safesearch?: 0 | 1 | 2;
  time_range?: string;
  language?: string;
  categories?: string[];
  // HTTP 参数
  url?: string;
  method?: string;
  headers?: Record<string, string>;
  cookies?: Record<string, string>;
  data?: Record<string, string>;
  body?: string;
}

/** 搜索引擎配置 (引擎实例使用) */
export interface EngineConfig {
  name: string;
  shortcut: string;
  disabled: boolean;
  weight: number;
  timeout: number;
  categories: string[];
}

/** 搜索引擎返回的原始结果项 */
export interface RawResult {
  title: string;
  url: string;
  content?: string;
  position?: number;
  publishedDate?: string;
  thumbnail?: string;
  engine?: string;
  score?: number;
}

/** orchestrator.execute() 返回的引擎响应 */
export interface EngineResponse {
  results: RawResult[];
  engineName: string;
  elapsedMs: number;
  success: boolean;
  error?: string;
}

/** mini-searxng orchestrator 消费的内部 SearchRequest */
export interface SearchRequest {
  query: string;
  engines?: string[];
  limit?: number;
  timeout?: number;
  language?: string;
  safesearch?: number;
  pageno?: number;
  timeRange?: string;
  categories?: string[];
}

/** merger 返回的 SearchResult (mini-searxng 内部格式) */
export interface SearchResult {
  title: string;
  url: string;
  content?: string;
  engine: string;
  engines?: string[];
  positions?: number[];
  score: number;
  category?: string;
  publishedDate?: string;
  thumbnail?: string;
}

/** formatter 返回的 SearchResponse (mini-searxng 内部格式) */
export interface SearchResponse {
  query: string;
  numberOfResults: number;
  results: SearchResult[];
  timing: Record<string, number>;
  unresponsiveEngines: string[];
}
