import { parseDOM } from './parser/dom-parser.js';
import { getModeConfig } from './config.js';
import { runPhase1 } from './phase1/noise-remover.js';
import { extractContent } from './phase2/readability-extractor.js';
import { cleanResidualNoise } from './phase2/residual-cleaner.js';
import { sanitize } from './phase2/dom-cleaner.js';
import { buildMarkdown } from './output/markdown-builder.js';
import { calculateQualityScore } from './output/quality-scorer.js';
import { assembleEvidencePack } from './output/evidence-pack.js';
import { AuditLogger } from './audit/audit-logger.js';
import type { PurifyOptions, PurifyResult, PurifyMode, ExtractionConfig, DegradationLevel } from './types.js';

/** Max page size in bytes (5 MB) — pages exceeding this are rejected. */
const MAX_PAGE_SIZE_BYTES = 5 * 1024 * 1024;

/**
 * Purify raw HTML — the main entry point.
 *
 * Full pipeline:
 *   raw HTML → Phase 1 (ad/noise removal) → Readability (content extraction)
 *   → Phase 2 (residual cleanup + sanitize) → Markdown rebuild → EvidencePack → PurifyResult
 *
 * Degradation strategy (sec15.1.2):
 *   L0: Network timeout / HTTP error — HANDLED BY CALLER (not in this library)
 *   L1: Phase 1 exception → skip Phase 1, go directly to Readability
 *   L2: Readability extraction failed → return stripped body text
 *   L0 (normal): Full pipeline success
 *
 * @param html    Raw HTML string
 * @param options Purification options (mode, URL, media preferences)
 * @returns PurifyResult with clean HTML, text, markdown, audit log, evidence pack, and stats
 */
export async function purifyHtml(
  html: string,
  options: PurifyOptions = {},
): Promise<PurifyResult> {
  const startTime = Date.now();
  const mode: PurifyMode = options.mode || 'balanced';
  const config = getModeConfig(mode);
  const url = options.url || 'about:blank';

  const auditLogger = new AuditLogger();

  // Quick bail: empty input
  if (!html || html.trim().length === 0) {
    return createEmptyResult(url, startTime, mode);
  }

  // Page size check (sec11.2.2)
  if (html.length > MAX_PAGE_SIZE_BYTES) {
    return createEmptyResult(url, startTime, mode);
  }

  const originalTextLength = html.replace(/<[^>]*>/g, '').length;
  let degradationLevel: DegradationLevel = 0;
  let phase1Html: string = html;

  // ===== Phase 1: DOM pre-processing =====
  let phase1Succeeded = false;
  let protectedRegionsCount = 0;
  let phase1RemovedCount = 0;

  try {
    const $ = parseDOM(html);
    const phase1Result = runPhase1($, url, config);

    for (const entry of phase1Result.auditLog) {
      auditLogger.log(entry);
    }

    phase1Html = phase1Result.html;
    protectedRegionsCount = phase1Result.protectedRegions.length;
    phase1RemovedCount = phase1Result.removedCount;
    phase1Succeeded = true;
  } catch (_err) {
    // L1 degradation (sec15.1.2): Phase 1 failed → skip filtering, use raw HTML
    degradationLevel = 1;
    phase1Html = html;
    auditLogger.logSkip('phase1', 'PHASE1_EXCEPTION_DEGRADED_TO_L1', 0, 'pre_readability');
  }

  // ===== Readability: Content extraction =====
  const extractionConfig: ExtractionConfig = {
    charThreshold: config.charThreshold,
    linkDensityThreshold: config.linkDensityThreshold,
    cjkAdaptive: true,
    enableFallback: true,
  };

  let extraction;
  try {
    extraction = extractContent(phase1Html, url, extractionConfig);
  } catch (_err) {
    // L2 degradation (sec15.1.2): extraction failed → return stripped body text
    degradationLevel = Math.max(degradationLevel, 2) as DegradationLevel;
    extraction = { content: '', title: '', byline: '', excerpt: '', textLength: 0, qualityScore: 0 };
    auditLogger.logSkip('extraction', 'EXTRACTION_EXCEPTION_DEGRADED_TO_L2', 0, 'post_readability');
  }

  // ===== Phase 2: Residual cleanup + sanitize =====
  let cleanHtml: string;
  let cleanText: string;
  let phase2Removed = 0;

  if (extraction.content) {
    const $2 = parseDOM(extraction.content);
    const phase2AuditLog = auditLogger.getEntries();

    phase2Removed = cleanResidualNoise(
      $2,
      phase1Succeeded ? [] : [], // protectedRegions not available if Phase 1 skipped
      config,
      phase2AuditLog,
      html, // original body text
    );

    // Handle image/table/media preferences
    if (options.keepImages === false) {
      $2('img').remove();
    }
    if (options.keepTables === false) {
      $2('table').remove();
    }
    if (options.keepVideos === false) {
      $2('video, iframe').remove();
    }

    // DOMCleaner: whitelist-based sanitization (sec11.2.7)
    sanitize($2);

    cleanHtml = $2.html() || '';
    cleanText = $2.text().trim();
  } else {
    // L2 degradation: Readability returned no content → strip tags from phase1Html
    degradationLevel = Math.max(degradationLevel, 2) as DegradationLevel;
    cleanHtml = phase1Html;
    // Strip tags for clean text
    cleanText = phase1Html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    auditLogger.logSkip('body', 'READABILITY_EXTRACTION_FAILED', 0, 'post_readability');
  }

  // ===== Markdown rebuild =====
  const markdown = buildMarkdown(cleanHtml, url);

  // ===== Quality scoring =====
  const qualityScore = calculateQualityScore({
    cleanText,
    cleanHtml,
    originalTextLength,
    removedCount: phase1RemovedCount + phase2Removed,
    protectedCount: protectedRegionsCount,
  });

  const allAuditLog = auditLogger.getEntries();

  // ===== EvidencePack (sec12.3.3) =====
  const evidencePack = assembleEvidencePack({
    sourceUrl: url,
    originalHtml: html,
    phase1Html,
    extractedHtml: extraction.content || '',
    markdown,
    auditEntries: allAuditLog,
    mode,
  });

  return {
    url,
    title: extraction.title || undefined,
    cleanHtml,
    cleanText,
    markdown,
    removedCount: phase1RemovedCount + phase2Removed,
    protectedCount: protectedRegionsCount,
    qualityScore,
    degradationLevel,
    auditLog: options.returnAuditLog !== false ? allAuditLog : [],
    evidencePack,
    stats: {
      originalHtmlLength: html.length,
      cleanHtmlLength: cleanHtml.length,
      originalTextLength,
      cleanTextLength: cleanText.length,
      removedNodes: phase1RemovedCount + phase2Removed,
      protectedNodes: protectedRegionsCount,
      processingTimeMs: Date.now() - startTime,
    },
  };
}

/**
 * Create a PurifierRuntime instance with pre-configured options.
 * Useful for batch processing with consistent settings.
 */
export function createPurifier(defaults: PurifyOptions = {}) {
  return {
    purify: (html: string, overrides?: PurifyOptions) =>
      purifyHtml(html, { ...defaults, ...overrides }),
  };
}

function createEmptyResult(url?: string, startTime?: number, mode?: PurifyMode): PurifyResult {
  return {
    url,
    cleanHtml: '',
    cleanText: '',
    markdown: '',
    removedCount: 0,
    protectedCount: 0,
    qualityScore: 0,
    degradationLevel: 0,
    auditLog: [],
    stats: {
      originalHtmlLength: 0,
      cleanHtmlLength: 0,
      originalTextLength: 0,
      cleanTextLength: 0,
      removedNodes: 0,
      protectedNodes: 0,
      processingTimeMs: startTime ? Date.now() - startTime : 0,
    },
  };
}

// Re-export types for consumers
export type { PurifyOptions, PurifyResult, PurifyMode, AuditLogEntry, PurifyStats, EvidencePack, DegradationLevel } from './types.js';
export { PriorityLevel } from './types.js';
export type { RuleRef, NetworkIndex, CosmeticIndex } from './types.js';

// Re-export PurifierRuntime class
export { PurifierRuntime } from './runtime.js';
