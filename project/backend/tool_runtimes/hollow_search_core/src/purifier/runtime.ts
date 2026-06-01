import { parseDOM } from './parser/dom-parser.js';
import { getModeConfig } from './config.js';
import { RuleEngine } from './rules/rule-engine.js';
import { runPhase1 } from './phase1/noise-remover.js';
import { extractContent } from './phase2/readability-extractor.js';
import { cleanResidualNoise } from './phase2/residual-cleaner.js';
import { sanitize } from './phase2/dom-cleaner.js';
import { buildMarkdown } from './output/markdown-builder.js';
import { calculateQualityScore } from './output/quality-scorer.js';
import { assembleEvidencePack } from './output/evidence-pack.js';
import { AuditLogger } from './audit/audit-logger.js';
import type {
  PurifyMode, PurifyOptions, PurifyResult, EvidencePack,
  ModeConfig, ExtractionConfig, DegradationLevel,
} from './types.js';

const MAX_PAGE_SIZE_BYTES = 5 * 1024 * 1024;

/**
 * PurifierRuntime — class-based entry point for the content purification pipeline.
 *
 * Wraps the functional purifyHtml() in a class that can hold configuration
 * and be reused across multiple purification calls. This matches the
 * architectural design in the research (sec11.2.1, agent_f_final_architecture.md).
 *
 * Research ref: agent_f_final_architecture.md line 279-333
 *
 * @example
 *   const runtime = new PurifierRuntime({ mode: 'balanced' });
 *   const result = await runtime.purify(html, { url: 'https://example.com' });
 *   console.log(result.markdown);
 */
export class PurifierRuntime {
  private config: ModeConfig;
  private ruleEngine: RuleEngine;
  private auditLogger: AuditLogger;
  private mode: PurifyMode;

  constructor(options: PurifyOptions = {}) {
    this.mode = options.mode || 'balanced';
    this.config = getModeConfig(this.mode);
    this.ruleEngine = new RuleEngine();
    this.auditLogger = new AuditLogger();
  }

  /**
   * Full three-phase purification pipeline.
   */
  async purify(html: string, overrides?: PurifyOptions): Promise<PurifyResult> {
    const startTime = Date.now();
    const opts = { ...{ mode: this.mode }, ...overrides };
    const mode: PurifyMode = opts.mode || 'balanced';
    const config = mode !== this.mode ? getModeConfig(mode) : this.config;
    const url = opts.url || 'about:blank';

    this.auditLogger.reset();

    // Quick bail
    if (!html || html.trim().length === 0) {
      return this.createEmptyResult(url, startTime, mode);
    }

    // Page size check
    if (html.length > MAX_PAGE_SIZE_BYTES) {
      return this.createEmptyResult(url, startTime, mode);
    }

    const originalTextLength = html.replace(/<[^>]*>/g, '').length;
    let degradationLevel: DegradationLevel = 0;
    let phase1Html: string = html;
    let phase1Succeeded = false;
    let protectedRegionsCount = 0;
    let phase1RemovedCount = 0;

    // ===== Phase 1 =====
    try {
      const $ = parseDOM(html);
      const phase1Result = runPhase1($, url, config);

      for (const entry of phase1Result.auditLog) {
        this.auditLogger.log(entry);
      }

      phase1Html = phase1Result.html;
      protectedRegionsCount = phase1Result.protectedRegions.length;
      phase1RemovedCount = phase1Result.removedCount;
      phase1Succeeded = true;
    } catch {
      degradationLevel = 1;
      phase1Html = html;
      this.auditLogger.logSkip('phase1', 'PHASE1_EXCEPTION_DEGRADED_TO_L1', 0, 'pre_readability');
    }

    // ===== Readability extraction =====
    const extractionConfig: ExtractionConfig = {
      charThreshold: config.charThreshold,
      linkDensityThreshold: config.linkDensityThreshold,
      cjkAdaptive: true,
      enableFallback: true,
    };

    let extraction;
    try {
      extraction = extractContent(phase1Html, url, extractionConfig);
    } catch {
      degradationLevel = Math.max(degradationLevel, 2) as DegradationLevel;
      extraction = { content: '', title: '', byline: '', excerpt: '', textLength: 0, qualityScore: 0 };
      this.auditLogger.logSkip('extraction', 'EXTRACTION_EXCEPTION_DEGRADED_TO_L2', 0, 'post_readability');
    }

    // ===== Phase 2: cleanup + sanitize =====
    let cleanHtml: string;
    let cleanText: string;
    let phase2Removed = 0;

    if (extraction.content) {
      const $2 = parseDOM(extraction.content);
      const phase2AuditLog = this.auditLogger.getEntries();

      phase2Removed = cleanResidualNoise(
        $2,
        [],
        config,
        phase2AuditLog,
        html,
      );

      if (opts.keepImages === false) $2('img').remove();
      if (opts.keepTables === false) $2('table').remove();
      if (opts.keepVideos === false) $2('video, iframe').remove();

      sanitize($2);

      cleanHtml = $2.html() || '';
      cleanText = $2.text().trim();
    } else {
      degradationLevel = Math.max(degradationLevel, 2) as DegradationLevel;
      cleanHtml = phase1Html;
      cleanText = phase1Html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
      this.auditLogger.logSkip('body', 'READABILITY_EXTRACTION_FAILED', 0, 'post_readability');
    }

    // ===== Markdown =====
    const markdown = buildMarkdown(cleanHtml, url);

    // ===== Quality =====
    const qualityScore = calculateQualityScore({
      cleanText,
      cleanHtml,
      originalTextLength,
      removedCount: phase1RemovedCount + phase2Removed,
      protectedCount: protectedRegionsCount,
    });

    const allAuditLog = this.auditLogger.getEntries();

    // ===== EvidencePack =====
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
      auditLog: opts.returnAuditLog !== false ? allAuditLog : [],
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
   * Update runtime mode without recreating the instance.
   */
  setMode(mode: PurifyMode): void {
    this.mode = mode;
    this.config = getModeConfig(mode);
  }

  /**
   * Get the internal rule engine for custom rule registration.
   */
  getRuleEngine(): RuleEngine {
    return this.ruleEngine;
  }

  /**
   * Get current mode.
   */
  getMode(): PurifyMode {
    return this.mode;
  }

  /**
   * Get current config (read-only copy).
   */
  getConfig(): Readonly<ModeConfig> {
    return { ...this.config };
  }

  private createEmptyResult(url: string, startTime: number, mode: PurifyMode): PurifyResult {
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
        processingTimeMs: Date.now() - startTime,
      },
    };
  }
}
