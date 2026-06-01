// ===== Base Types =====

export type PurifyMode = 'conservative' | 'balanced' | 'aggressive';

// ===== Rule Engine Priority System (from AdGuard 7-level, research sec13.1.2) =====

export enum PriorityLevel {
  BASE = 1,
  TYPE = 50,
  DOMAIN = 100,
  REDIRECT = 1000,
  EXCEPTION = 10000,
  IMPORTANT = 100000,
}

export interface RuleRef {
  ruleId: string;
  priority: number;
  filterList: string;
}

export interface NetworkIndex {
  hostnameIndex: Map<string, RuleRef[]>;
  domainSuffixIndex: Map<string, RuleRef[]>;
  genericRules: RuleRef[];
}

export interface CosmeticIndex {
  hostnameSelectorIndex: Map<string, string[]>;
  safeGenericSelectors: string[];
  hostnameExceptionIndex: Map<string, string[]>;
}

export interface PurifyOptions {
  mode?: PurifyMode;
  url?: string;
  query?: string;
  keepImages?: boolean;
  keepVideos?: boolean;
  keepLinks?: boolean;
  keepTables?: boolean;
  returnAuditLog?: boolean;
}

// ===== Core Result Types =====

export type DegradationLevel = 0 | 1 | 2;

export interface PurifyResult {
  url?: string;
  title?: string;
  cleanHtml: string;
  cleanText: string;
  markdown: string;
  removedCount: number;
  protectedCount: number;
  qualityScore: number;
  degradationLevel: DegradationLevel;
  auditLog: AuditLogEntry[];
  stats: PurifyStats;
  evidencePack?: EvidencePack;
}

export interface EvidencePack {
  sourceUrl: string;
  originalHtml: string;
  phase1Html: string;
  extractedHtml: string;
  markdown: string;
  auditEntries: AuditLogEntry[];
  processedAt: string;
  mode: PurifyMode;
}

export interface AuditLogEntry {
  action: 'remove' | 'protect' | 'mark' | 'skip';
  selector?: string;
  tagName?: string;
  className?: string;
  reason: string;
  confidence: number;
  phase: 'pre_readability' | 'post_readability' | 'text_cleanup';
  snippet?: string;
  signals?: string[];
}

export interface PurifyStats {
  originalHtmlLength: number;
  cleanHtmlLength: number;
  originalTextLength: number;
  cleanTextLength: number;
  removedNodes: number;
  protectedNodes: number;
  processingTimeMs: number;
}

// ===== Content Protection Types =====

export interface ProtectedRegion {
  id: string;
  selector: string;
  type: 'semantic_tag' | 'class_signal' | 'text_density' | 'cjk_density' | 'heading_structure' | 'link_density';
  confidence: number;
  sourceSignals: ProtectionSignal[];
}

export interface ProtectionSignal {
  type: 'semantic_tag' | 'class_signal' | 'text_density' | 'cjk_density' | 'link_density' | 'heading_structure';
  confidence: number;
  weight: number;
  selector: string;
}

export interface DeletionDecision {
  allowed: boolean;
  reason: string;
  confidence: number;
  signals: string[];
}

// ===== Scoring Types =====

export interface ContentScore {
  baseScore: number;
  commaBonus: number;
  lengthBonus: number;
  cjkBonus: number;
  tagBonus: number;
  classWeight: number;
  total: number;
}

export interface CandidateNode {
  selector: string;
  score: number;
  density: number;
  textLength: number;
  depth: number;
}

// ===== Readability Types =====

export interface ExtractionConfig {
  charThreshold: number;
  linkDensityThreshold: number;
  cjkAdaptive: boolean;
  enableFallback: boolean;
}

export interface ExtractionResult {
  content: string;
  title: string;
  byline: string;
  excerpt: string;
  textLength: number;
  qualityScore: number;
}

// ===== Mode Config =====

export interface ModeConfig {
  mode: PurifyMode;
  /** Minimum confidence threshold for deletion. conservative:0.85, balanced:0.65, aggressive:0.45 */
  minConfidenceScore: number;
  /** Require >=2 independent signals for deletion */
  requireMultipleSignals: boolean;
  /** Character threshold for content extraction. conservative:300, balanced:500, aggressive:200 */
  charThreshold: number;
  /** Whether to use generic selectors beyond domain-specific ones */
  useGenericSelectors: boolean;
  /** Link density above which elements are considered navigational */
  linkDensityThreshold: number;
}

// ===== Ad Candidate Types =====

export interface AdCandidate {
  selector: string;
  tagName: string;
  text: string;
  noiseScore: number;
  elementHtml: string;
}

// ===== Rule Engine Types =====

export interface SafeSelector {
  pattern: RegExp;
  category: 'ad' | 'cookie' | 'subscribe' | 'social' | 'tracking' | 'comments' | 'popup';
  confidence: number;
}

export interface HostnameRuleEntry {
  hostname: string;
  selectors: string[];
}

// ===== Internal Phase Result Types =====

export interface Phase1Result {
  html: string;
  protectedRegions: ProtectedRegion[];
  removedCount: number;
  auditLog: AuditLogEntry[];
}
