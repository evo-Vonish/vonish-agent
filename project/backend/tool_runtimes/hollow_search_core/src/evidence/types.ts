/**
 * Evidence module — type definitions and constants.
 *
 * Provides the core types for evidence-pack generation including
 * chunking, scoring, deduplication, claim extraction, and result structures.
 *
 * @module types
 */

// ===== CrawledArticle (consumed from upstream crawler) =====

/** Article produced by the crawler that the evidence pipeline consumes. */
export interface CrawledArticle {
  id?: string;
  url: string;
  title?: string;
  text: string;
  searchProvider?: string;
  fetchedAt?: string;
}

// ===== SourceIndex =====

/** Indexed reference to a source article used in an evidence pack. */
export interface SourceIndex {
  id: string;
  title: string;
  url: string;
  provider?: string;
  fetchedAt: string;
  domain: string;
}

// ===== Chunk =====

/** A text slice produced by chunking an article. */
export interface Chunk {
  id: string;
  sourceId: string;
  text: string;
  startChar: number;
  endChar: number;
  charCount: number;
}

/** Options controlling the chunking behaviour. */
export interface ChunkOptions {
  /** Minimum characters per chunk. */
  minChars: number;
  /** Maximum characters per chunk. */
  maxChars: number;
  /** Overlap characters between consecutive chunks. */
  overlapChars: number;
}

/** Result returned by chunkText / chunkAll. */
export interface ChunkResult {
  /** All generated chunks. */
  chunks: Chunk[];
  /** Chunking statistics. */
  stats: {
    totalParagraphs: number;
    mergedChunks: number;
    splitChunks: number;
  };
}

// ===== ScoredChunk =====

/** A Chunk augmented with relevance and density scores. */
export interface ScoredChunk extends Chunk {
  relevanceScore: number;
  densityScore: number;
  noisePenalty: number;
  combinedScore: number;
  matchReason?: string;
}

// ===== SourcePassage =====

/** A selected passage from a source, ready for citation in a claim. */
export interface SourcePassage {
  id: string;
  sourceId: string;
  chunkId: string;
  text: string;
  startChar: number;
  endChar: number;
  score: number;
  reason?: string;
}

/** Options controlling passage selection. */
export interface PassageSelectionOptions {
  /** Maximum total passages to select. */
  maxPassages: number;
  /** Maximum passages per individual source. */
  maxPerSource: number;
  /** Maximum passages per domain. */
  maxPerDomain: number;
  /** MMR diversity trade-off (0 = relevance only, 1 = diversity only). */
  mmrLambda: number;
}

// ===== Deduplication =====

/** Options controlling deduplication behaviour. */
export interface DedupOptions {
  /** Whether to perform exact deduplication. */
  exactDedup: boolean;
  /** Jaccard similarity threshold for near-duplicate removal (0-1). */
  nearDedupThreshold: number;
}

/** Result returned by dedupChunks. */
export interface DedupResult {
  /** Chunks remaining after deduplication. */
  uniqueChunks: ScoredChunk[];
  /** Number of exact duplicates removed. */
  exactDuplicatesRemoved: number;
  /** Number of near-duplicates removed. */
  nearDuplicatesRemoved: number;
}

// ===== EvidenceClaim =====

/** A factual claim backed by one or more source passages. */
export interface EvidenceClaim {
  id: string;
  claim: string;
  passageIds: string[];
  sourceIds: string[];
  confidence: 'low' | 'medium' | 'high';
}

// ===== EvidencePack =====

/** Complete evidence package returned for a query. */
export interface EvidencePack {
  query: string;
  sources: SourceIndex[];
  passages: SourcePassage[];
  claims: EvidenceClaim[];
  summary?: string;
  gaps?: string[];
  nextQueries?: string[];
}

// ===== EvidencePackOptions =====

/** Configurable options that control evidence-pack generation. */
export interface EvidencePackOptions {
  minChars?: number;
  maxChars?: number;
  overlapChars?: number;
  densityWeight?: number;
  relevanceWeight?: number;
  maxPassages?: number;
  maxPerSource?: number;
  maxPerDomain?: number;
  exactDedup?: boolean;
  nearDedupThreshold?: number;
  mmrLambda?: number;
}

/** Fully-resolved configuration used internally by the pipeline. */
export interface EvidencePackConfig extends EvidencePackOptions {
  /** Preset name that was applied. */
  preset: string;
}

// ===== EVIDENCE_PRESETS =====

/**
 * Built-in evidence-pack presets that trade speed against depth.
 *
 * - **fast**  – Larger chunks, fewer passages. Best for quick answers.
 * - **balanced** – Moderate values, good default for most use-cases.
 * - **deep**  – Smaller chunks, more passages. Best for thorough research.
 */
export const EVIDENCE_PRESETS: Record<string, EvidencePackConfig> = {
  fast: {
    preset: 'fast',
    minChars: 800,
    maxChars: 1500,
    overlapChars: 100,
    densityWeight: 0.3,
    relevanceWeight: 0.7,
    maxPassages: 10,
    maxPerSource: 2,
    maxPerDomain: 3,
    exactDedup: true,
    nearDedupThreshold: 0.85,
    mmrLambda: 0.7,
  },
  balanced: {
    preset: 'balanced',
    minChars: 500,
    maxChars: 1200,
    overlapChars: 150,
    densityWeight: 0.3,
    relevanceWeight: 0.7,
    maxPassages: 20,
    maxPerSource: 3,
    maxPerDomain: 5,
    exactDedup: true,
    nearDedupThreshold: 0.75,
    mmrLambda: 0.5,
  },
  deep: {
    preset: 'deep',
    minChars: 400,
    maxChars: 1000,
    overlapChars: 200,
    densityWeight: 0.3,
    relevanceWeight: 0.7,
    maxPassages: 30,
    maxPerSource: 4,
    maxPerDomain: 7,
    exactDedup: true,
    nearDedupThreshold: 0.70,
    mmrLambda: 0.4,
  },
};

// ===== ProcessingStats =====

/** Detailed statistics collected during evidence-pack generation. */
export interface ProcessingStats {
  totalArticles: number;
  totalChunks: number;
  exactDuplicatesRemoved: number;
  nearDuplicatesRemoved: number;
  noiseFiltered: number;
  finalPassages: number;
  processingTimeMs: number;
  stageTiming: {
    chunkingMs: number;
    scoringMs: number;
    dedupMs: number;
    selectionMs: number;
    claimsMs: number;
  };
}

// ===== EvidencePackResult =====

/** Result wrapper containing both the evidence pack and processing statistics. */
export interface EvidencePackResult {
  pack: EvidencePack;
  stats: ProcessingStats;
}

// ===== Default options =====

/** Fully-resolved default options for evidence-pack generation. */
export const DEFAULT_OPTIONS: EvidencePackConfig = EVIDENCE_PRESETS.balanced;
