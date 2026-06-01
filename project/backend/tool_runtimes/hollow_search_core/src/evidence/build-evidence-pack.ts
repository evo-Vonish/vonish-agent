/**
 * Evidence Pack 主编排器。
 *
 * 编排整个处理流程（6 步骤），提供统一的入口函数 buildEvidencePack。
 *
 * @module build-evidence-pack
 */

import {
  type CrawledArticle,
  type SourceIndex,
  type EvidenceClaim,
  type EvidencePack,
  type EvidencePackOptions,
  type EvidencePackResult,
  type ProcessingStats,
  type EvidencePackConfig,
  type SourcePassage,
  DEFAULT_OPTIONS,
  EVIDENCE_PRESETS,
} from './types.js';

import { chunkAll } from './chunk-text.js';
import { scoreAllChunks } from './score-chunk.js';
import { dedupChunks } from './dedup-chunks.js';
import { selectPassages } from './select-passages.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Extract domain hostname from a URL string.
 *
 * @param url - The URL to parse
 * @returns The hostname, or 'unknown' on parse failure
 */
function extractDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return 'unknown';
  }
}

// ---------------------------------------------------------------------------
// Step 1 — buildSourceIndex
// ---------------------------------------------------------------------------

/**
 * Build source index entries from crawled articles.
 *
 * @param articles - Array of crawled articles
 * @returns Array of source index entries
 */
function buildSourceIndex(articles: CrawledArticle[]): SourceIndex[] {
  return articles.map((article, idx) => {
    const id = article.id || `src_${(idx + 1).toString().padStart(3, '0')}`;
    return {
      id,
      title: article.title || 'Untitled',
      url: article.url,
      provider: article.searchProvider,
      fetchedAt: article.fetchedAt || new Date().toISOString(),
      domain: extractDomain(article.url),
    };
  });
}

// ---------------------------------------------------------------------------
// Step 6a — buildClaims
// ---------------------------------------------------------------------------

/**
 * Heuristic check whether a sentence is likely to be a factual claim.
 *
 * @param sentence - The sentence to evaluate
 * @returns True if the sentence looks like a claim
 */
function isLikelyClaim(sentence: string): boolean {
  if (sentence.length < 15) return false;

  const indicators = [
    /(是|为|等于|相当于)\s*[^，。]{2,20}/,
    /(宣布|声明|表示|指出|确认|否认)/,
    /(数据|统计|报告显示)/,
    /(因此|所以|由此|这意味着)/,
    /\b(announced|confirmed|reported|stated)\b/i,
  ];

  return indicators.some(re => re.test(sentence));
}

/**
 * Extract claims from selected passages using sentence-level heuristics.
 *
 * @param passages - Selected source passages
 * @returns Array of extracted evidence claims
 */
function buildClaims(passages: SourcePassage[]): EvidenceClaim[] {
  const claims: EvidenceClaim[] = [];

  for (const passage of passages) {
    const sentences = passage.text.split(/(?<=[.!?])\s+/);
    for (const sent of sentences) {
      if (isLikelyClaim(sent)) {
        claims.push({
          id: `claim_${(claims.length + 1).toString().padStart(3, '0')}`,
          claim: sent.trim(),
          passageIds: [passage.id],
          sourceIds: [passage.sourceId],
          confidence:
            passage.score > 0.7
              ? 'high'
              : passage.score > 0.4
                ? 'medium'
                : 'low',
        });
      }
    }
  }

  return claims;
}

// ---------------------------------------------------------------------------
// Step 6b — generateSummary
// ---------------------------------------------------------------------------

/**
 * Generate a summary from selected passages.
 *
 * v0.1: 取前 3 个 passage 的首句，用 "；" 连接。
 *
 * @param passages - Selected source passages
 * @returns Summary string
 */
function generateSummary(passages: SourcePassage[]): string {
  if (passages.length === 0) return '';

  return passages
    .slice(0, 3)
    .map(p => p.text.split(/(?<=[.!?])\s+/)[0])
    .filter(s => s && s.trim().length > 0)
    .join('；');
}

// ---------------------------------------------------------------------------
// Step 6c — identifyGaps
// ---------------------------------------------------------------------------

/**
 * Identify information gaps in the evidence pack.
 *
 * @param query - The original query
 * @param passages - Selected passages
 * @param claims - Extracted claims
 * @returns Array of gap descriptions
 */
function identifyGaps(
  query: string,
  passages: SourcePassage[],
  claims: EvidenceClaim[],
): string[] {
  const gaps: string[] = [];

  const hasHighConfidence = claims.some(
    c => c.confidence === 'high' && c.claim.length > 20,
  );
  if (!hasHighConfidence) {
    gaps.push('缺少直接回答 query 的高置信度证据');
  }

  if (
    /\b\d{4}\b/.test(query) &&
    !passages.some(p => /\b\d{4}\b/.test(p.text))
  ) {
    gaps.push('缺少与 query 时间相关的信息');
  }

  const uniqueSources = new Set(passages.map(p => p.sourceId));
  if (uniqueSources.size < 3 && passages.length > 5) {
    gaps.push('来源覆盖不足，可能存在信息偏见');
  }

  return gaps;
}

// ---------------------------------------------------------------------------
// Step 6d — suggestNextQueries
// ---------------------------------------------------------------------------

/**
 * Suggest follow-up queries to fill information gaps.
 *
 * @param query - The original query
 * @param passages - Selected passages
 * @param claims - Extracted claims
 * @returns Array of suggested next queries
 */
function suggestNextQueries(
  query: string,
  passages: SourcePassage[],
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _claims: EvidenceClaim[],
): string[] {
  const suggestions: string[] = [];

  const hasOfficial = passages.some(p =>
    /(official|声明|公告|announcement)/i.test(p.text),
  );
  if (!hasOfficial) {
    suggestions.push(`${query} official statement`);
  }

  return suggestions.slice(0, 3);
}

// ---------------------------------------------------------------------------
// Main entry: buildEvidencePack
// ---------------------------------------------------------------------------

/**
 * Build an evidence pack from crawled articles for a given query.
 *
 * Orchestrates the 6-step processing pipeline:
 * 1. Build source index
 * 2. Chunk articles
 * 3. Score chunks
 * 4. Deduplicate chunks
 * 5. Select passages
 * 6. Build claims, summary, gaps, and next queries
 *
 * @param query - The search query
 * @param articles - Array of crawled articles
 * @param options - Optional overrides and preset selection
 * @returns EvidencePackResult containing the pack and processing stats
 */
export function buildEvidencePack(
  query: string,
  articles: CrawledArticle[],
  options?: EvidencePackOptions,
): EvidencePackResult {
  const t0 = Date.now();

  // Handle empty articles gracefully
  if (!articles || articles.length === 0) {
    const emptyPack: EvidencePack = {
      query,
      sources: [],
      passages: [],
      claims: [],
      summary: '',
      gaps: ['未提供任何文章，无法构建证据包'],
      nextQueries: [query],
    };

    const emptyStats: ProcessingStats = {
      totalArticles: 0,
      totalChunks: 0,
      exactDuplicatesRemoved: 0,
      nearDuplicatesRemoved: 0,
      noiseFiltered: 0,
      finalPassages: 0,
      processingTimeMs: Date.now() - t0,
      stageTiming: {
        chunkingMs: 0,
        scoringMs: 0,
        dedupMs: 0,
        selectionMs: 0,
        claimsMs: 0,
      },
    };

    return { pack: emptyPack, stats: emptyStats };
  }

  // 合并配置：preset + 用户覆盖
  const presetName =
    options && typeof options === 'object' ? (options as any).preset || 'balanced' : 'balanced';
  const preset = EVIDENCE_PRESETS[presetName] || EVIDENCE_PRESETS.balanced;

  const config = {
    ...DEFAULT_OPTIONS,
    ...preset,
    ...options,
  } as Required<EvidencePackConfig>;

  // Step 1: SourceIndex
  const t1 = Date.now();
  const sources = buildSourceIndex(articles);
  const domainMap = new Map(sources.map(s => [s.id, s.domain]));

  // Step 2: Chunking
  const t2 = Date.now();
  const { chunks: allChunks } = chunkAll(articles, {
    minChars: config.minChars ?? DEFAULT_OPTIONS.minChars,
    maxChars: config.maxChars ?? DEFAULT_OPTIONS.maxChars,
    overlapChars: config.overlapChars ?? DEFAULT_OPTIONS.overlapChars,
  });

  // Step 3: Scoring
  const t3 = Date.now();
  const scoredChunks = scoreAllChunks(query, allChunks, {
    relevanceWeight: config.relevanceWeight,
    densityWeight: config.densityWeight,
  });
  const noiseFiltered = scoredChunks.filter(c => c.noisePenalty > -3);
  const noiseFilteredCount = scoredChunks.length - noiseFiltered.length;

  // Step 4: Deduplication
  const t4 = Date.now();
  const { uniqueChunks, exactDuplicatesRemoved, nearDuplicatesRemoved } = dedupChunks(
    noiseFiltered,
    {
      exactDedup: config.exactDedup ?? DEFAULT_OPTIONS.exactDedup,
      nearDedupThreshold: config.nearDedupThreshold ?? DEFAULT_OPTIONS.nearDedupThreshold,
    },
  );

  // Step 5: Passage Selection
  const t5 = Date.now();
  const passages = selectPassages(uniqueChunks, domainMap, {
    maxPassages: config.maxPassages ?? DEFAULT_OPTIONS.maxPassages,
    maxPerSource: config.maxPerSource ?? DEFAULT_OPTIONS.maxPerSource,
    maxPerDomain: config.maxPerDomain ?? DEFAULT_OPTIONS.maxPerDomain,
    mmrLambda: config.mmrLambda ?? DEFAULT_OPTIONS.mmrLambda,
  });

  // Step 6: Claims, Summary, Gaps, NextQueries
  const t6 = Date.now();
  const claims = buildClaims(passages);
  const summary = generateSummary(passages);
  const gaps = identifyGaps(query, passages, claims);
  const nextQueries = suggestNextQueries(query, passages, claims);

  // Only include sources that are actually referenced by passages
  const usedSourceIds = new Set(passages.map(p => p.sourceId));
  const usedSources = sources.filter(s => usedSourceIds.has(s.id));

  const pack: EvidencePack = {
    query,
    sources: usedSources,
    passages,
    claims,
    summary,
    gaps,
    nextQueries,
  };

  const stats: ProcessingStats = {
    totalArticles: articles.length,
    totalChunks: allChunks.length,
    exactDuplicatesRemoved,
    nearDuplicatesRemoved,
    noiseFiltered: noiseFilteredCount,
    finalPassages: passages.length,
    processingTimeMs: Date.now() - t0,
    stageTiming: {
      chunkingMs: t3 - t2,
      scoringMs: t4 - t3,
      dedupMs: t5 - t4,
      selectionMs: t6 - t5,
      claimsMs: Date.now() - t6,
    },
  };

  return { pack, stats };
}
